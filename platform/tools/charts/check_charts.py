#!/usr/bin/env python3
"""Offline checks of platform/deploy/charts (devplat, devplat-project). Every result claimed in
docs/mercury/development-orchestration/24-helm-and-gitops.md section 10 comes from this script.

    HELM=... KUBECONFORM=... [GO=...] python3 platform/tools/charts/check_charts.py [--out DIR]

Checks (each prints PASS/FAIL; exit 1 if any FAIL):
  1. lint            helm lint of both charts with the test values
  2. render          positive render cases | kubeconform -strict (Kubernetes 1.33.0; CRDs via the CRDs-catalog)
  3. negative        render cases that MUST fail, each with the expected error substring
  4. schema          values.yaml / test values against values.schema.json (jsonschema), plus mutations that must fail
  5. parity          devplat-project rendered for `mercury` (builds and proxy enabled) vs platform/deploy/base, field by
                     field, for every object in proj-mercury-* and every devplat-system object named *-mercury;
                     differences are
                     reported and compared with parity-expected.txt (any unlisted difference = FAIL)
  6. secret-pinning  every Secret a rendered platform pod references is pinned to that pod's ServiceAccount in base
                     VAP devplat-secret-pinning
  7. cel             (needs GO) compile the chart's own VAP expressions and evaluate cases; evaluate base VAPs
                     devplat-pod-hardening / -platform-placement / -secret-pinning / -image-pinning against every
                     rendered platform pod, plus a mis-pinned-Secret negative case
Not checked: admission on a real API server (OpenAPI typing), NetworkPolicy enforcement, anything needing a cluster.
Untrusted input: none (only repository files).
"""
import argparse, copy, json, os, re, subprocess, sys, tempfile

import yaml, jsonschema

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CH = os.path.join(ROOT, "platform", "deploy", "charts")
BASE = os.path.join(ROOT, "platform", "deploy", "base")
V = lambda f: os.path.join(HERE, "values", f)
HELM, KC, GO = os.environ.get("HELM", "helm"), os.environ.get("KUBECONFORM", "kubeconform"), os.environ.get("GO")
KCARGS = ["-strict", "-summary", "-kubernetes-version", "1.33.0", "-schema-location", "default", "-schema-location",
          "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"]
DP = ["template", "t", os.path.join(CH, "devplat"), "-n", "devplat-system", "--kube-version", "1.33.0"]
PJ = ["template", "m", os.path.join(CH, "devplat-project"), "--kube-version", "1.33.0"]
RESULTS = []


def result(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))


def helm(args):
    p = subprocess.run([HELM] + args, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def docs(text):
    return [d for d in yaml.safe_load_all(text) if d]


# ---------------------------------------------------------------- 1 lint
def check_lint():
    for name, args in [("devplat", ["lint", os.path.join(CH, "devplat"), "-n", "devplat-system", "--kube-version", "1.33.0", "-f", V("devplat-test.yaml")]),
                       ("devplat-project", ["lint", os.path.join(CH, "devplat-project"), "--kube-version", "1.33.0"]),
                       ("devplat-project (full)", ["lint", os.path.join(CH, "devplat-project"), "--kube-version", "1.33.0", "-f", V("project-full.yaml")])]:
        rc, out, err = helm(args)
        result(f"lint {name}", rc == 0, (out + err).strip().splitlines()[-1] if (out + err).strip() else "")


# ---------------------------------------------------------------- 2 render
POSITIVE = [
    ("devplat test values", DP + ["-f", V("devplat-test.yaml")]),
    ("devplat external PG + ingress + OIDC", DP + ["-f", V("devplat-test.yaml"), "--set", "postgres.mode=external",
     "--set", "postgres.external.host=pg.example.invalid", "--set", "ingress.enabled=true", "--set", "ingress.host=devplat.example.invalid",
     "--set", "ingress.tlsSecretName=tls"]),
    ("devplat-project defaults (builds off, no proxy)", PJ),
    ("devplat-project full (builds, proxy, RuntimeClass pin)", PJ + ["-f", V("project-full.yaml")]),
    ("devplat-project mercury parity values", PJ + ["-f", V("project-mercury-parity.yaml")]),
]


def check_render(out):
    rendered = {}
    for name, args in POSITIVE:
        rc, o, e = helm(args)
        if rc != 0:
            result(f"render {name}", False, e.strip()[:200]); continue
        rendered[name] = o
        p = subprocess.run([KC] + KCARGS + ["-"], input=o, capture_output=True, text=True)
        last = (p.stdout.strip().splitlines() or [""])[-1]
        m = re.search(r"Valid: (\d+), Invalid: (\d+), Errors: (\d+), Skipped: (\d+)", last)
        ok = p.returncode == 0 and m and int(m.group(1)) > 0 and m.group(2) == m.group(3) == m.group(4) == "0"
        result(f"render {name} | kubeconform -strict", bool(ok), last)
    json.dump(rendered, open(os.path.join(out, "rendered.json"), "w"))
    return rendered


# ---------------------------------------------------------------- 3 negative renders
NEG = [
    ("devplat without image digests", DP + ["--set", "postgres.mode=external", "--set", "postgres.external.host=h", "--set", "api.oidc.allowedSubjects[0].issuer=https://i.invalid", "--set", "api.oidc.allowedSubjects[0].subject=s", "--set", "api.oidc.allowedSubjects[0].project="], "image.digest is empty"),
    ("devplat with empty allowedSubjects (D2)", DP + ["-f", V("devplat-test.yaml"), "--set", "api.oidc.allowedSubjects=null"], "allowedSubjects"),
    ("devplat outside devplat-system", ["template", "t", os.path.join(CH, "devplat"), "-n", "default", "--kube-version", "1.33.0", "-f", V("devplat-test.yaml")], "install into namespace devplat-system"),
    ("devplat ingress without OIDC issuer", DP + ["-f", V("devplat-test.yaml"), "--set", "api.oidc.issuerUrl=", "--set", "ingress.enabled=true", "--set", "ingress.host=x", "--set", "ingress.tlsSecretName=t"], "requires api.oidc.issuerUrl"),
    ("gitbroker draftPullRequestsOnly=false", DP + ["-f", V("devplat-test.yaml"), "--set", "gitbroker.draftPullRequestsOnly=false"], "schema"),
    ("gitbroker push prefix main", DP + ["-f", V("devplat-test.yaml"), "--set", "gitbroker.pushRefPrefix=main"], "schema"),
    ("Secret-name override (unknown key)", DP + ["-f", V("devplat-test.yaml"), "--set", "gitbroker.privateKeySecretRef.name=x"], "schema"),
    ("shared serviceAccount map (removed, S-24)", DP + ["-f", V("devplat-test.yaml"), "--set", "serviceAccount.annotations.a/b=c"], "schema"),
    ("identical SA annotations on two components (S-24)", DP + ["-f", V("devplat-test.yaml"), "--set", "api.serviceAccountAnnotations.iam\\.gke\\.io/gcp-service-account=x@p.iam", "--set", "controller.serviceAccountAnnotations.iam\\.gke\\.io/gcp-service-account=x@p.iam"], "S-24"),
    ("image outside devplat/ or mirror/ (D15)", DP + ["-f", V("devplat-test.yaml"), "--set", "api.image.name=projects/x/api"], "schema"),
    ("CNPG without operand digest (S-22)", DP + ["-f", V("devplat-test.yaml"), "--set", "postgres.cnpg.image.digest="], "schema"),
    ("cnpg backup enabled (not templated)", DP + ["-f", V("devplat-test.yaml"), "--set", "postgres.cnpg.backup.enabled=true"], "schema"),
    ("external PG without host", DP + ["-f", V("devplat-test.yaml"), "--set", "postgres.mode=external"], "schema"),
    ("model-gateway extra endpoint (D12)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.allowedEndpoints[2]=POST /v1/files"], "schema"),
    ("model-gateway server tools allowed (D12)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.rejectServerTools=false"], "schema"),
    ("model-gateway URL content source (RS-1)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.allowedContentSourceTypes[2]=url"], "schema"),
    ("model-gateway server tool type allowed (RS-1)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.allowedToolTypes[1]=web_fetch_20250910"], "schema"),
    ("model-gateway file references allowed (RS-1)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.rejectFileReferences=false"], "schema"),
    ("model-gateway extra content block type (C-1)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.allowedContentBlockTypes[7]=container_upload"], "schema"),
    ("model-gateway extra request field (C-1)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.allowedRequestFields[13]=mcp_servers"], "schema"),
    ("model-gateway second provider (RS-8)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.providers[1].name=openai", "--set", "modelGateway.providers[1].host=api.openai.com"], "schema"),
    ("model-gateway project from path (D12)", DP + ["-f", V("devplat-test.yaml"), "--set", "modelGateway.policy.projectFrom=path"], "schema"),
    ("gitbroker caller auth other than projected token (S-23)", DP + ["-f", V("devplat-test.yaml"), "--set", "gitbroker.callerAuth.mode=none"], "schema"),
    ("test-namespace quota over the base caps (D19)", PJ + ["--set-string", "test.quota.secrets=100"], "schema"),
    ("namespacer with 2 replicas", DP + ["-f", V("devplat-test.yaml"), "--set", "namespacer.replicas=2"], "schema"),
    ("project quota secrets=0", PJ + ["--set-string", "exec.quota.secrets=0"], "schema"),
    ("project services quota set", PJ + ["--set-string", "exec.quota.services=5"], "schema"),
    ("project prefix mismatch", PJ + ["--set", "project.id=other-x"], "namespacePrefix must equal"),
    ("project id too short / too long (D24)", PJ + ["--set", "project.id=ab", "--set", "project.namespacePrefix=proj-ab"], "schema"),
    ("project RuntimeClass runc", PJ + ["--set", "exec.requiredRuntimeClassName=runc"], "schema"),
    ("project platformNamespace kube-system", PJ + ["--set", "platformNamespace=kube-system"], "schema"),
    ("builds enabled without allowlist/profile (D20)", PJ + ["--set", "build.enabled=true"], "schema"),
    ("buildkit arg containing a space (D20)", PJ + ["-f", V("project-full.yaml"), "--set", "build.buildkit.args[0]=--a b"], "schema"),
    ("reduced mode without fact (D16)", PJ + ["--set", "assurance.mode=reduced"], "schema"),
    ("reduced mode with builds (D16)", PJ + ["-f", V("project-full.yaml"), "--set", "assurance.mode=reduced", "--set", "assurance.reducedAssuranceFact=REDUCED-ASSURANCE"], "schema"),
    ("registry proxy without uplinks (D14)", PJ + ["--set", "registryProxy.enabled=true", "--set", "registryProxy.image.digest=sha256:" + "0" * 64], "schema"),
]


def check_negative():
    for name, args, want in NEG:
        rc, o, e = helm(args)
        msg = (e or o)
        ok = rc != 0 and want in msg
        result(f"negative: {name}", ok, "" if ok else f"rc={rc} {msg.strip()[:160]}")


# ---------------------------------------------------------------- 4 schema
def check_schema():
    for chart, files in [("devplat", ["devplat-test.yaml"]), ("devplat-project", ["", "project-full.yaml"])]:
        sch = json.load(open(os.path.join(CH, chart, "values.schema.json")))
        jsonschema.Draft7Validator.check_schema(sch)
        base = yaml.safe_load(open(os.path.join(CH, chart, "values.yaml")))
        for f in files:
            v = copy.deepcopy(base)
            if f:
                deep_merge(v, yaml.safe_load(open(V(f))))
            errs = [e.message for e in jsonschema.Draft7Validator(sch).iter_errors(v)]
            result(f"schema {chart} values{(' + ' + f) if f else ''}", not errs, "; ".join(errs)[:160])
    # the chart defaults of devplat MUST fail (empty operator identities, D2; CNPG digest, S-22)
    sch = json.load(open(os.path.join(CH, "devplat", "values.schema.json")))
    errs = [e.message for e in jsonschema.Draft7Validator(sch).iter_errors(yaml.safe_load(open(os.path.join(CH, "devplat", "values.yaml"))))]
    result("schema devplat bare defaults are rejected (D2, S-22)", len(errs) >= 1, "; ".join(errs)[:120])


def deep_merge(a, b):
    for k, x in b.items():
        if isinstance(x, dict) and isinstance(a.get(k), dict):
            deep_merge(a[k], x)
        else:
            a[k] = x


# ---------------------------------------------------------------- 5 parity with base
def norm(v):
    if isinstance(v, dict): return {k: norm(x) for k, x in v.items()}
    if isinstance(v, list): return [norm(x) for x in v]
    return str(v)


def parity(rendered, which):
    """which = 'project' (devplat-project for mercury vs base project objects) or 'platform' (devplat chart's
    ServiceAccounts, Roles and RoleBindings in devplat-system vs base)."""
    k = lambda d: f"{d['kind']}/{d['metadata'].get('namespace') or '-'}/{d['metadata']['name']}"
    base = [d for f in ("namespaces", "quotas", "serviceaccounts", "rbac", "networkpolicies") for d in docs(open(os.path.join(BASE, f + ".yaml")).read())]
    if which == "project":
        ch = docs(rendered["devplat-project mercury parity values"])
        sel = lambda d: (d['metadata'].get('namespace') or d['metadata']['name']).startswith('proj-mercury') or \
            (d['metadata'].get('namespace') == 'devplat-system' and d['metadata']['name'].endswith('-mercury'))
        base += [d for d in docs(open(os.path.join(BASE, "admission-policies.yaml")).read()) if d['kind'] == 'ConfigMap']
        ef, title = "parity-expected.txt", "parity devplat-project(mercury) vs platform/deploy/base"
    else:
        ch = docs(rendered["devplat test values"])
        sel = lambda d: d['kind'] in ('ServiceAccount', 'Role', 'RoleBinding') and d['metadata'].get('namespace') in ('devplat-system', 'devplat-artifacts') \
            and not d['metadata']['name'].endswith(('-mercury', '-jupiter')) and d['metadata']['name'] != 'default' and 'prometheus' not in d['metadata']['name']
        ef, title = "parity-platform-expected.txt", "parity devplat (SAs, Roles, RoleBindings) vs platform/deploy/base"
    B = {k(d): d for d in base if sel(d)}
    C = {k(d): d for d in ch if sel(d)}
    diffs = []
    for key in sorted(set(B) | set(C)):
        if key not in C: diffs.append(f"ONLY-BASE {key}"); continue
        if key not in B: diffs.append(f"ONLY-CHART {key}"); continue
        b, c = B[key], C[key]
        if b['kind'] == 'Namespace':
            bl = {x: y for x, y in b['metadata']['labels'].items() if x != 'app.kubernetes.io/part-of'}
            cl = {x: y for x, y in c['metadata']['labels'].items() if x in bl}
            if bl != cl: diffs.append(f"DIFF {key} labels")
            continue
        for f in ('spec', 'rules', 'roleRef', 'subjects', 'automountServiceAccountToken', 'data'):
            if norm(b.get(f)) != norm(c.get(f)): diffs.append(f"DIFF {key} .{f}")
    expected = set()
    ef = os.path.join(HERE, ef)
    if os.path.exists(ef):
        expected = {l.split("#")[0].strip() for l in open(ef) if l.split("#")[0].strip()}
    unexpected = [d for d in diffs if d not in expected]
    stale = sorted(expected - set(diffs))
    for d in diffs: print(f"      {'(expected) ' if d in expected else 'UNEXPECTED '}{d}")
    for d in stale: print(f"      (expected but not seen - remove from {os.path.basename(ef)}) {d}")
    same = len(set(B) & set(C)) - len({d.split(' ')[1] for d in diffs if d.startswith('DIFF')})
    result(title, not unexpected and not stale, f"{same} identical, {len(diffs)} differences ({len(unexpected)} unexpected, {len(stale)} stale)")
    return diffs


# ---------------------------------------------------------------- 6 secret pinning
def base_policies():
    return {d['metadata']['name']: d for d in docs(open(os.path.join(BASE, "admission-policies.yaml")).read()) if d['kind'] == 'ValidatingAdmissionPolicy'}


def pinned_map():
    pol = base_policies()['devplat-secret-pinning']
    expr = [v['expression'] for v in pol['spec']['variables'] if v['name'] == 'pinned'][0]
    return json.loads(expr.replace("'", '"'))


def platform_pods(rendered):
    pods = []
    for name in ("devplat test values",):
        for d in docs(rendered[name]):
            if d['kind'] in ('Deployment', 'Job'):
                pods.append((d['kind'] + "/" + d['metadata']['name'], d['spec']['template']))
    return pods


def check_pinning(rendered):
    pinned = pinned_map()
    bad, n = [], 0
    for name, tpl in platform_pods(rendered):
        sp = tpl['spec']; sa = sp['serviceAccountName']
        refs = {v['secret']['secretName'] for v in sp.get('volumes', []) if 'secret' in v}
        for c in sp['containers'] + sp.get('initContainers', []):
            for e in c.get('env', []):
                r = e.get('valueFrom', {}).get('secretKeyRef')
                if r: refs.add(r['name'])
        for r in sorted(refs):
            n += 1
            if r not in pinned: bad.append(f"{name}: {r} NOT IN BASE PINNING MAP")
            elif sa not in pinned[r]: bad.append(f"{name}: {r} pinned to {pinned[r]}, used by {sa}")
    for b in bad: print("      " + b)
    result("secret-pinning: rendered platform pods vs base devplat-secret-pinning", not bad, f"{n} references, {len(bad)} problems")


# ---------------------------------------------------------------- 6b DB paths (R6 re-check RS-4)
DB_COMPONENTS = {"controller": "devplat_controller", "api": "devplat_api", "model-gateway": "devplat_model_gateway",
                 "artifact-gateway": "devplat_artifact_gateway"}   # every runtime group of platform/db/roles.sql


def check_db_paths(rendered):
    """Each component the DB authorizes must be able to reach it: credentials, CNPG login, NetworkPolicy both ways."""
    rd = list(docs(rendered["devplat test values"]))
    cluster = next(d for d in rd if d["kind"] == "Cluster")
    logins = {r["name"]: r.get("passwordSecret", {}).get("name") for r in cluster["spec"]["managed"]["roles"] if r.get("login")}
    base_np = {d["metadata"]["name"]: d for d in docs(open(os.path.join(BASE, "networkpolicies.yaml")).read())
               if d["metadata"]["namespace"] == "devplat-system"}
    pg_in = [pe.get("podSelector", {}).get("matchLabels", {}).get("app.kubernetes.io/name")
             for r in base_np["postgres"]["spec"]["ingress"] for pe in r["from"]]
    bad = []
    for comp, role in DB_COMPONENTS.items():
        name, secret = f"devplat-{comp}", f"devplat-db-{comp}"
        wl = next((d for d in rd if d["kind"] == "Deployment" and d["metadata"]["name"] == name), None)
        env = [e for c in (wl or {}).get("spec", {}).get("template", {}).get("spec", {}).get("containers", []) for e in c.get("env", [])]
        if not any(e.get("valueFrom", {}).get("secretKeyRef", {}).get("name") == secret for e in env):
            bad.append(f"{name}: no DB credentials from {secret}")
        if logins.get(role) != secret:
            bad.append(f"CNPG managed role {role}: login with passwordSecret {secret} missing")
        if name not in pg_in:
            bad.append(f"base NetworkPolicy postgres: no ingress from {name}")
        own = base_np.get(comp, {}).get("spec", {}).get("egress", [])
        if not any(5432 in [p_["port"] for p_ in r.get("ports", [])] and any("cnpg.io/cluster" in str(t) for t in r.get("to", [])) for r in own):
            bad.append(f"base NetworkPolicy {comp}: no egress to PostgreSQL 5432")
    for x in bad: print("      " + x)
    result("db-paths: every DB-authorized component has credentials, a CNPG login and network paths", not bad,
           f"{len(DB_COMPONENTS)} components, {len(bad)} problems")


# ---------------------------------------------------------------- 7 CEL
def celcheck_bin(out):
    if not GO:
        return None
    b = os.path.join(out, "celcheck")
    p = subprocess.run([GO, "build", "-o", b, "."], cwd=os.path.join(ROOT, "platform", "tools", "admission"), capture_output=True, text=True)
    if p.returncode != 0:
        result("cel: build celcheck", False, p.stderr[:200]); return None
    return b


def pol_entry(d):
    s = d['spec']
    return {"Name": d['metadata']['name'], "Variables": [{"Name": v['name'], "Expr": v['expression']} for v in s.get('variables', [])],
            "Validations": [v['expression'] for v in s['validations']], "Conditions": [m['expression'] for m in s.get('matchConditions', [])]}


def run_cel(binary, out, tag, policies, cases):
    items = [{"Policy": p["Name"], "Kind": "variable", "Name": v["Name"], "Expr": v["Expr"]} for p in policies for v in p["Variables"]]
    items += [{"Policy": p["Name"], "Kind": "validation", "Name": str(i), "Expr": e} for p in policies for i, e in enumerate(p["Validations"])]
    f1, f2 = os.path.join(out, f"{tag}-items.json"), os.path.join(out, f"{tag}-suite.json")
    json.dump(items, open(f1, "w")); json.dump({"Policies": policies, "Cases": cases}, open(f2, "w"))
    p1 = subprocess.run([binary, f1], capture_output=True, text=True)
    result(f"cel compile {tag}", p1.returncode == 0, p1.stdout.strip().splitlines()[-1] if p1.stdout.strip() else p1.stderr[:120])
    p2 = subprocess.run([binary, "eval", f2], capture_output=True, text=True)
    lines = p2.stdout.strip().splitlines()
    for l in lines:
        if l.startswith("BAD"): print("      " + l)
    result(f"cel eval {tag}", p2.returncode == 0 and lines and lines[-1].startswith("eval: 0"), lines[-1] if lines else p2.stderr[:120])


def check_cel(rendered, out):
    b = celcheck_bin(out)
    if not b:
        print("SKIP  cel checks (set GO=/path/to/go)"); RESULTS.append(("cel (skipped: no GO)", None)); return
    # (a) the chart's own project-specific VAPs (builder allowlist, RuntimeClass pin)
    pf = docs(rendered["devplat-project full (builds, proxy, RuntimeClass pin)"])
    pols = [pol_entry(d) for d in pf if d['kind'] == 'ValidatingAdmissionPolicy']
    bk = "registry.devplat.internal/mirror/moby/buildkit@sha256:" + "0" * 63 + "1"
    BP, RC = "devplat-example-a-builder-allowlist", "devplat-example-a-runtime-class"
    cases = [
        {"Name": "allowlisted builder", "Input": {"object": {"spec": {"containers": [{"name": "buildkitd", "image": bk}]}}}, "Expect": {BP: "allow"}},
        {"Name": "foreign init image", "Input": {"object": {"spec": {"containers": [{"name": "buildkitd", "image": bk}], "initContainers": [{"name": "x", "image": "evil@sha256:" + "1" * 64}]}}}, "Expect": {BP: "deny"}},
        {"Name": "kata pod", "Input": {"object": {"spec": {"runtimeClassName": "kata", "containers": []}}}, "Expect": {RC: "allow"}},
        {"Name": "gvisor when kata pinned", "Input": {"object": {"spec": {"runtimeClassName": "gvisor", "containers": []}}}, "Expect": {RC: "deny"}},
        {"Name": "no runtime class", "Input": {"object": {"spec": {"containers": []}}}, "Expect": {RC: "deny"}},
    ]
    run_cel(b, out, "chart-vaps", pols, cases)
    # (a2) base devplat-build-exceptions driven by the params ConfigMap this chart renders for the build namespace
    bp = base_policies()
    if "devplat-build-exceptions" in bp:
        cm = lambda rend: [d for d in docs(rend) if d['kind'] == 'ConfigMap' and d['metadata']['name'] == 'devplat-admission-params' and d['metadata']['namespace'].endswith('-build')][0]
        on, off = cm(rendered["devplat-project full (builds, proxy, RuntimeClass pin)"]), cm(rendered["devplat-project defaults (builds off, no proxy)"])
        def bkpod(**o):
            c = {"name": "buildkitd", "image": on['data']['buildkitImagePrefix'] + "0" * 63 + "1", "args": on['data']['buildkitArgs'].split(' '),
                 "securityContext": {"runAsNonRoot": True, "capabilities": {"drop": ["ALL"]}, "allowPrivilegeEscalation": True,
                                     "seccompProfile": {"type": "Localhost", "localhostProfile": on['data']['buildkitSeccompProfile']}}}
            c.update(o.pop("c", {})); spec = {"hostUsers": False, "securityContext": {"runAsNonRoot": True}, "containers": [c]}; spec.update(o)
            return spec
        mk = lambda name, spec, params, want: {"Name": name, "Input": {"object": {"metadata": {}, "spec": spec}, "params": {"data": params['data']}}, "Expect": {"devplat-build-exceptions": want}}
        cases = [mk("buildkitd per chart params", bkpod(), on, "allow"),
                 mk("builds disabled (chart default params)", bkpod(), off, "deny"),
                 mk("buildkitd in host user namespace", bkpod(hostUsers=True), on, "deny"),
                 mk("buildkitd Unconfined seccomp", bkpod(c={"securityContext": {"runAsNonRoot": True, "capabilities": {"drop": ["ALL"]}, "seccompProfile": {"type": "Unconfined"}}}), on, "deny"),
                 mk("buildkitd extra arg", bkpod(c={"args": on['data']['buildkitArgs'].split(' ') + ["--debug"]}), on, "deny")]
        run_cel(b, out, "base-build-exceptions-with-chart-params", [pol_entry(bp["devplat-build-exceptions"])], cases)
    else:
        result("cel base devplat-build-exceptions present", False, "missing in base")
    # (b) base VAPs against the rendered platform pods
    want = ["devplat-pod-hardening", "devplat-platform-placement", "devplat-secret-pinning", "devplat-image-pinning"]
    pols = [pol_entry(bp[w]) for w in want if w in bp]
    missing = [w for w in want if w not in bp]
    if missing: result("cel base policies present", False, f"missing in base: {missing}")
    params = {"data": {"allowedImagePrefixes": "registry.devplat.internal/devplat/,registry.devplat.internal/mirror/", "buildkitImagePrefix": "x"}}
    nsobj = {"metadata": {"name": "devplat-system", "labels": {"devplat.io/ns-role": "system", "kubernetes.io/metadata.name": "devplat-system"}}}
    cases = []
    for name, tpl in platform_pods(rendered):
        pod = {"metadata": {"labels": tpl['metadata'].get('labels', {}), "namespace": "devplat-system"}, "spec": tpl['spec']}
        cases.append({"Name": name, "Input": {"object": pod, "namespaceObject": nsobj, "params": params, "request": {"operation": "CREATE", "namespace": "devplat-system"}},
                      "Expect": {p["Name"]: "allow" for p in pols}})
    api = copy.deepcopy([c for c in cases if c["Name"] == "Deployment/devplat-api"][0])
    api["Name"] = "api mounting the GitHub App key"
    api["Input"]["object"]["spec"].setdefault("volumes", []).append({"name": "k", "secret": {"secretName": "devplat-gitbroker-github-app"}})
    api["Expect"] = {"devplat-secret-pinning": "deny"}
    proj = copy.deepcopy(cases[0]); proj["Name"] = "platform pod with a project image"
    proj["Input"]["object"]["spec"]["containers"][0]["image"] = "registry.devplat.internal/projects/mercury/x@sha256:" + "2" * 64
    proj["Expect"] = {"devplat-image-pinning": "deny"}
    cases += [api, proj]
    run_cel(b, out, "base-vaps-vs-chart-pods", pols, cases)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=None); a = ap.parse_args()
    out = a.out or tempfile.mkdtemp(prefix="devplat-charts-")
    os.makedirs(out, exist_ok=True)
    check_lint(); r = check_render(out); check_negative(); check_schema()
    if "devplat-project mercury parity values" in r: parity(r, "project")
    if "devplat test values" in r: parity(r, "platform")
    if "devplat test values" in r: check_pinning(r); check_db_paths(r); check_cel(r, out)
    fails = [n for n, ok in RESULTS if ok is False]
    print(f"\n{sum(1 for _, ok in RESULTS if ok)} passed, {len(fails)} failed, {sum(1 for _, ok in RESULTS if ok is None)} skipped; outputs in {out}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
