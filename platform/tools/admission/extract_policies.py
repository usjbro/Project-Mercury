"""Validate platform/deploy/base against strict K8s v1.33 schemas + cross-reference + CEL checks."""
import json, sys, glob, os, re, subprocess, copy
import yaml, jsonschema
BASE, SCHEMAS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
def schema_file(d):
    g, _, v = d["apiVersion"].rpartition("/")
    grp = g.split(".")[0] if g else ""
    return f"{d['kind'].lower()}-{grp + '-' if grp else ''}{v}.json"
docs, errors, counts = [], [], {}
for f in sorted(glob.glob(os.path.join(BASE, "*.yaml"))):
    for i, d in enumerate(yaml.safe_load_all(open(f))):
        if d is None: continue
        docs.append((os.path.basename(f), i, d))
        sf = os.path.join(SCHEMAS, schema_file(d))
        sch = json.load(open(sf))
        v = jsonschema.Draft4Validator(sch)
        errs = sorted(v.iter_errors(d), key=lambda e: e.path)
        counts.setdefault(os.path.basename(f), [0, 0]); counts[os.path.basename(f)][0] += 1
        if errs:
            counts[os.path.basename(f)][1] += 1
            for e in errs: errors.append(f"SCHEMA {os.path.basename(f)}#{i} {d['kind']}/{d['metadata'].get('name')}: {list(e.path)} {e.message[:200]}")
print("Schema validation (strict, v1.33.0-standalone-strict):")
for f, (n, bad) in counts.items(): print(f"  {f}: {n} documents, {bad} invalid")
# ---- cross-reference checks ----
res_jobs = lambda r: "jobs" in r.get("resources", [])
key = lambda d: (d["kind"], d["metadata"].get("namespace", ""), d["metadata"]["name"])
seen = {}
for f, i, d in docs:
    k = key(d)
    if k in seen: errors.append(f"DUP {k} in {f} and {seen[k]}")
    seen[k] = f
nss = {d["metadata"]["name"] for _, _, d in docs if d["kind"] == "Namespace"}
ext_ns = {"kube-system", "cnpg-system"}
dns1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
for f, i, d in docs:
    m = d["metadata"]; n = m.get("namespace")
    if n and n not in nss: errors.append(f"NS {f} {key(d)} namespace {n} not declared")
    if not dns1123.match(m["name"]) or len(m["name"]) > 63: errors.append(f"NAME {key(d)} not DNS-1123 label")
    if d["kind"] in ("RoleBinding", "ClusterRoleBinding"):
        rr = d["roleRef"]; rk = (rr["kind"], n if rr["kind"] == "Role" else "", rr["name"])
        if rk not in seen and not (rr["kind"] == "ClusterRole" and rr["name"] in ("system:service-account-issuer-discovery",)): errors.append(f"REF {key(d)} roleRef {rk} missing")
        if d["kind"] == "ClusterRoleBinding" and rr["name"] not in ("devplat-namespacer", "devplat-dns", "system:service-account-issuer-discovery"): errors.append(f"POLICY unexpected ClusterRoleBinding {key(d)}")
        for s in d["subjects"]:
            if s["kind"] == "ServiceAccount" and ("ServiceAccount", s["namespace"], s["name"]) not in seen: errors.append(f"REF {key(d)} subject SA {s} missing")
    if d["kind"] == "ValidatingAdmissionPolicyBinding":
        if ("ValidatingAdmissionPolicy", "", d["spec"]["policyName"]) not in seen: errors.append(f"REF {key(d)} policy missing")
        pr = d["spec"].get("paramRef")
        if pr and pr.get("namespace") and ("ConfigMap", pr["namespace"], pr["name"]) not in seen: errors.append(f"REF {key(d)} paramRef missing")
        if pr and not pr.get("namespace") and not [k for k in seen if k[0] == "ConfigMap" and k[2] == pr["name"]]: errors.append(f"REF {key(d)} per-namespace paramRef {pr['name']} has no ConfigMap")
    if d["kind"] == "ValidatingAdmissionPolicy":
        if ("ValidatingAdmissionPolicyBinding", "", d["metadata"]["name"]) not in seen: errors.append(f"REF policy {key(d)} has no binding")
    if d["kind"] == "ResourceQuota":
        for e in d["spec"].get("scopeSelector", {}).get("matchExpressions", []):
            for pc in e["values"]:
                if not pc.startswith("system-") and ("PriorityClass", "", pc) not in seen: errors.append(f"REF {key(d)} PriorityClass {pc} missing")
    if d["kind"] == "NetworkPolicy":
        for sect in ("ingress", "egress"):
            for r in d["spec"].get(sect, []):
                for peer in r.get("from", []) + r.get("to", []):
                    nl = peer.get("namespaceSelector", {}).get("matchLabels", {}).get("kubernetes.io/metadata.name")
                    if nl and nl not in nss | ext_ns: errors.append(f"REF {key(d)} peer namespace {nl} unknown")
# D10: project pods never reach the object store (in-cluster devplat-artifacts or any ipBlock)
for f, i, d in docs:
    if d["kind"] == "NetworkPolicy" and d["metadata"]["namespace"].startswith("proj-"):
        for r in d["spec"].get("egress", []):
            for peer in r.get("to", []):
                if "ipBlock" in peer: errors.append(f"D10 {key(d)} project egress to ipBlock {peer['ipBlock']}")
                if peer.get("namespaceSelector", {}).get("matchLabels", {}).get("kubernetes.io/metadata.name") == "devplat-artifacts": errors.append(f"D10 {key(d)} project egress to the object store")
# every managed namespace has default deny
for n in nss:
    if ("NetworkPolicy", n, "default-deny-all") not in seen: errors.append(f"NETPOL {n} lacks default-deny-all")
    if n.startswith("proj-"):
        for q in ("devplat-compute", "devplat-no-platform-priority"):
            if ("ResourceQuota", n, q) not in seen: errors.append(f"QUOTA {n} lacks {q}")
        if ("LimitRange", n, "devplat-defaults") not in seen: errors.append(f"LIMITRANGE {n} missing")
        if ("RoleBinding", n, "devplat-controller-job-runner") not in seen: errors.append(f"RBAC {n} lacks controller binding")
# SAs: all automount false
for f, i, d in docs:
    if d["kind"] == "ServiceAccount" and d.get("automountServiceAccountToken") is not False: errors.append(f"SA {key(d)} automount not false")
# RBAC: forbidden verbs/resources anywhere
for f, i, d in docs:
    if d["kind"] in ("Role", "ClusterRole"):
        for r in d["rules"]:
            if "*" in r.get("verbs", []) or "*" in r.get("resources", []) or "*" in r.get("apiGroups", []): errors.append(f"RBAC wildcard in {key(d)}")
            for res in r.get("resources", []):
                if res in ("pods/exec", "pods/attach", "pods/portforward", "pods/ephemeralcontainers") : errors.append(f"RBAC {key(d)} grants {res}")
                if res == "secrets" and set(r["verbs"]) - {"create", "get", "delete"}: errors.append(f"RBAC {key(d)} secrets verbs {r['verbs']}")
                if res == "pods" and set(r["verbs"]) & {"create", "update", "patch", "delete"}: errors.append(f"RBAC {key(d)} pod write")
            if res_jobs(r) and set(r["verbs"]) & {"update"}: errors.append(f"RBAC {key(d)} job update")
            if set(r.get("verbs", [])) & {"escalate", "impersonate"}: errors.append(f"RBAC escalate/impersonate in {key(d)} (R6 D19: no impersonation)")
# ---- CEL extraction ----
items, pols = [], []
for f, i, d in docs:
    if d["kind"] != "ValidatingAdmissionPolicy": continue
    sp = d["spec"]; pn = d["metadata"]["name"]
    for v in sp.get("variables", []): items.append({"Policy": pn, "Kind": "variable", "Name": v["name"], "Expr": v["expression"]})
    for j, v in enumerate(sp.get("validations", [])): items.append({"Policy": pn, "Kind": "validation", "Name": str(j), "Expr": v["expression"]})
    for v in sp.get("matchConditions", []): items.append({"Policy": pn, "Kind": "matchCondition", "Name": v["name"], "Expr": v["expression"]})
    pols.append({"Name": pn, "Variables": [{"Name": v["name"], "Expr": v["expression"]} for v in sp.get("variables", [])],
                 "Validations": [v["expression"] for v in sp["validations"]],
                 "Conditions": [v["expression"] for v in sp.get("matchConditions", [])]})
json.dump(items, open(os.path.join(OUT, "cel-items.json"), "w"))
# Params: per-namespace devplat-admission-params (paramRef without namespace, D15) and the cluster params.
nsparams = {d["metadata"]["namespace"]: d for _, _, d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "devplat-admission-params"}
cluster = [d for _, _, d in docs if d["kind"] == "ConfigMap" and d["metadata"]["name"] == "devplat-cluster-params"][0]
nsobj = {d["metadata"]["name"]: d for _, _, d in docs if d["kind"] == "Namespace"}
for n in nsobj:
    if n not in nsparams: errors.append(f"PARAMS namespace {n} lacks ConfigMap devplat-admission-params (image pinning would deny everything)")
# Binding paramRefs: which params each policy uses.
binding_params = {}
for _, _, d in docs:
    if d["kind"] == "ValidatingAdmissionPolicyBinding" and d["spec"].get("paramRef"):
        pr = d["spec"]["paramRef"]; binding_params[d["spec"]["policyName"]] = pr.get("namespace") or "<request namespace>"
json.dump({"pols": pols, "nsparams": nsparams, "cluster": cluster, "ns": nsobj, "bindingParams": binding_params},
          open(os.path.join(OUT, "pol-data.json"), "w"))
print("Cross-reference/invariant checks:", "PASS" if not [e for e in errors if not e.startswith("SCHEMA")] else "FAIL")
for e in errors: print("  ", e)
print("TOTAL errors:", len(errors))
sys.exit(1 if errors else 0)
