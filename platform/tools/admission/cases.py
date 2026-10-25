"""Behavioural cases for the ValidatingAdmissionPolicies in platform/deploy/base (evaluated by main.go `eval`).

Each case is one admission request (untyped JSON, no API defaulting) and the expected decision per policy:
allow | deny | skip (matchConditions do not select the request). Params are resolved like the bindings do:
per-namespace `devplat-admission-params` (paramRef without namespace) or `devplat-system/devplat-cluster-params`.

Sections: baseline cases (R5), R6 fix-round cases, and the R6 security reviewer's exploit cases E1-E11
(platform/tools/admission/exploit_cases.py of the review), which are kept here as regressions expecting DENY.
"""
import json, copy, os, re, sys

import yaml

D = json.load(open(sys.argv[1]))
NS, NSP, CLUSTER, BP = D["ns"], D["nsparams"], D["cluster"], D["bindingParams"]
IMG = "registry.devplat.internal/devplat/agent@sha256:" + "a" * 64
BK = "registry.devplat.internal/mirror/moby/buildkit@sha256:" + "b" * 64
PROFILE = "profiles/devplat-buildkit.json"
TNS = "proj-mercury-t-3fa9c01b"
NSR = "system:serviceaccount:devplat-system:devplat-namespacer"
CTL = "system:serviceaccount:devplat-system:devplat-controller"


def tns(name=TNS, project="mercury", **over):
    L = {"devplat.io/managed-by": "devplat-controller", "devplat.io/ns-role": "test", "devplat.io/project": project,
         "pod-security.kubernetes.io/enforce": "restricted"}
    L.update(over)
    return {"metadata": {"name": name, "labels": {k: v for k, v in L.items() if v is not None}}}


NS[TNS] = tns()
# What devplat-namespacer creates in a test namespace (content checked by devplat-namespacer-scope).
RB = CLUSTER["data"]["registryBase"]
NSP[TNS] = {"metadata": {"name": "devplat-admission-params", "namespace": TNS}, "immutable": True,
            "data": {"allowedImagePrefixes": f"{RB}devplat/,{RB}projects/mercury/,{RB}mirror/"}}


def params_for(ns, override=None):
    """paramsByPolicy as the bindings resolve them."""
    out = {}
    for pol, where in BP.items():
        out[pol] = CLUSTER if where == "devplat-system" and pol not in ("devplat-image-pinning", "devplat-build-exceptions") else NSP.get(ns)
    if override:
        out.update(override)
    return out


def req(kind, op="CREATE", ns="", user="system:serviceaccount:kube-system:job-controller"):
    return {"kind": {"group": "", "version": "v1", "kind": kind}, "operation": op, "namespace": ns, "userInfo": {"username": user}}


def inp(obj, ns, kind="Pod", op="CREATE", user="system:serviceaccount:kube-system:job-controller", old=None, override=None):
    return {"object": obj, "oldObject": old, "namespaceObject": NS.get(ns), "params": None,
            "paramsByPolicy": params_for(ns, override), "request": req(kind, op, ns, user)}


def pods(name, obj, ns, expect, override=None):
    return {"Name": name, "Input": inp(obj, ns, override=override), "Expect": expect}


def agent_pod(ns="proj-mercury-exec", project="mercury"):
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "dp-mercury-dt-0001-a1-x", "namespace": ns,
            "labels": {"devplat.io/project": project, "devplat.io/role": "mdev-backend-engineer", "devplat.io/workload": "agent", "devplat.io/network-class": "deps"}},
            "spec": {"serviceAccountName": f"{project}-agent", "automountServiceAccountToken": False, "runtimeClassName": "gvisor",
                     "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                     "initContainers": [{"name": "fetch", "image": IMG, "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}}],
                     "containers": [{"name": "agent", "image": IMG, "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                                     "env": [{"name": "RUN_TOKEN", "valueFrom": {"secretKeyRef": {"name": "dp-mercury-dt-0001-a1-io", "key": "token"}}}]}],
                     "volumes": [{"name": "ws", "emptyDir": {}}, {"name": "run", "secret": {"secretName": "dp-mercury-dt-0001-a1-io"}},
                                 {"name": "role", "configMap": {"name": "dp-mercury-dt-0001-a1-role"}}]}}


BUILD_ON = copy.deepcopy(NSP["proj-mercury-build"]); BUILD_ON["data"]["buildsEnabled"] = "true"
BON = {"devplat-build-exceptions": BUILD_ON}


def build_pod(cname="buildkitd", image=BK):
    """D20-conformant rootless buildkitd: user namespace, pinned Localhost seccomp, pinned args."""
    p = agent_pod("proj-mercury-build")
    p["metadata"]["labels"]["devplat.io/workload"] = "build"; p["metadata"]["labels"]["devplat.io/network-class"] = "none"
    p["spec"]["serviceAccountName"] = "mercury-build"; p["spec"]["hostUsers"] = False
    p["spec"]["initContainers"] = []
    p["spec"]["containers"] = [{"name": cname, "image": image, "args": BUILD_ON["data"]["buildkitArgs"].split(" "),
                                "securityContext": {"runAsNonRoot": True, "runAsUser": 1000, "allowPrivilegeEscalation": True,
                                                    "seccompProfile": {"type": "Localhost", "localhostProfile": PROFILE},
                                                    "appArmorProfile": {"type": "RuntimeDefault"}, "capabilities": {"drop": ["ALL"]}}}]
    p["spec"]["volumes"] = [{"name": "cache", "emptyDir": {}}]
    return p


ALLP = {"devplat-pod-hardening": "allow", "devplat-proj-pod-identity": "allow", "devplat-proj-runtime-placement": "allow", "devplat-image-pinning": "allow"}
cases = []
A = cases.append

# ---------------- baseline (R5) ----------------
A(pods("good-agent-pod", agent_pod(), "proj-mercury-exec", dict(ALLP)))
p = agent_pod(); p["spec"]["volumes"].append({"name": "sock", "hostPath": {"path": "/var/run/docker.sock"}})
A(pods("docker-sock-hostpath", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny", "devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["hostNetwork"] = True; A(pods("hostNetwork", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod(); p["spec"]["containers"][0]["securityContext"]["privileged"] = True; A(pods("privileged", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod(); p["spec"]["ephemeralContainers"] = [{"name": "dbg", "image": IMG}]; A(pods("ephemeral-container", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod(); del p["spec"]["automountServiceAccountToken"]; A(pods("automount-unset", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["serviceAccountName"] = "jupiter-agent"; A(pods("other-project-sa", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["volumes"].append({"name": "tok", "projected": {"sources": [{"serviceAccountToken": {"path": "t"}}]}}); A(pods("projected-sa-token", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["volumes"][1]["secret"]["secretName"] = "devplat-gitbroker-github-app"; A(pods("non-run-secret", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
A(pods("cross-project-label", agent_pod(project="jupiter"), "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); del p["spec"]["runtimeClassName"]; A(pods("no-runtimeclass-exec", p, "proj-mercury-exec", {"devplat-proj-runtime-placement": "deny", "devplat-proj-pod-identity": "allow"}))
p = agent_pod(); p["spec"]["containers"][0]["image"] = "registry.devplat.internal/devplat/agent:latest"; A(pods("tag-not-digest", p, "proj-mercury-exec", {"devplat-image-pinning": "deny"}))
p = agent_pod(); p["spec"]["containers"][0]["image"] = "docker.io/library/alpine@sha256:" + "c" * 64; A(pods("foreign-registry", p, "proj-mercury-exec", {"devplat-image-pinning": "deny"}))
A(pods("buildkitd-rootless-userns-localhost", build_pod(), "proj-mercury-build", {**ALLP, "devplat-build-exceptions": "allow"}, BON))
A(pods("builds-disabled-by-default", build_pod(), "proj-mercury-build", {"devplat-build-exceptions": "deny"}))
p = build_pod("evil", BK); p["spec"]["containers"][0]["securityContext"]["seccompProfile"] = {"type": "Unconfined"}
A(pods("unconfined-not-buildkitd", p, "proj-mercury-build", {"devplat-build-exceptions": "deny"}, BON))
A(pods("buildkitd-name-other-image", build_pod("buildkitd", IMG), "proj-mercury-build", {"devplat-build-exceptions": "deny"}, BON))
p = build_pod(); p["spec"]["containers"][0]["securityContext"]["capabilities"] = {"drop": ["NET_RAW"]}; A(pods("build-no-drop-all", p, "proj-mercury-build", {"devplat-build-exceptions": "deny"}, BON))
p = build_pod(); del p["spec"]["runtimeClassName"]; A(pods("build-unsandboxed-off-pool", p, "proj-mercury-build", {"devplat-proj-runtime-placement": "deny"}))
p = build_pod(); del p["spec"]["runtimeClassName"]; p["spec"]["nodeSelector"] = {"devplat.io/pool": "build"}; A(pods("build-on-build-pool", p, "proj-mercury-build", {"devplat-proj-runtime-placement": "allow", "devplat-build-exceptions": "allow"}, BON))


def plat(sa, secret):
    return {"metadata": {"name": "x", "namespace": "devplat-system", "labels": {}}, "spec": {"serviceAccountName": sa,
            "containers": [{"name": "c", "image": IMG}], "volumes": [{"name": "k", "secret": {"secretName": secret}}]}}


A(pods("gitbroker-key-by-gitbroker", plat("devplat-gitbroker", "devplat-gitbroker-github-app"), "devplat-system", {"devplat-secret-pinning": "allow", "devplat-platform-placement": "allow", "devplat-image-pinning": "allow"}))
A(pods("gitbroker-key-by-api", plat("devplat-api", "devplat-gitbroker-github-app"), "devplat-system", {"devplat-secret-pinning": "deny"}))
p = plat("devplat-api", "x"); p["spec"]["containers"][0]["env"] = [{"name": "K", "valueFrom": {"secretKeyRef": {"name": "devplat-model-gateway-llm-keys", "key": "anthropic"}}}]
A(pods("llm-key-env-by-api", p, "devplat-system", {"devplat-secret-pinning": "deny"}))
p = plat("devplat-api", "x"); p["spec"]["tolerations"] = [{"operator": "Exists"}]; A(pods("platform-wildcard-toleration", p, "devplat-system", {"devplat-platform-placement": "deny"}))
p = plat("devplat-api", "x"); p["spec"]["tolerations"] = [{"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300}]; A(pods("platform-default-toleration", p, "devplat-system", {"devplat-platform-placement": "allow"}))


def job():
    L = {"devplat.io/project": "mercury", "devplat.io/task": "dt-0001", "devplat.io/attempt": "1", "devplat.io/role": "mdev-backend-engineer", "devplat.io/network-class": "deps"}
    return {"metadata": {"name": "dp-mercury-dt-0001-a1", "namespace": "proj-mercury-exec", "labels": dict(L, **{"devplat.io/idempotency-key": "k1"})},
            "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 7200, "ttlSecondsAfterFinished": 3600, "parallelism": 1, "completions": 1,
                     "template": {"metadata": {"labels": dict(L, **{"devplat.io/workload": "agent"})}, "spec": {"automountServiceAccountToken": False, "containers": [{"name": "agent", "image": IMG}]}}}}


A({"Name": "good-job", "Input": inp(job(), "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "allow"}})
j = job(); j["spec"]["backoffLimit"] = 6; A({"Name": "job-backoff-6", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); del j["spec"]["activeDeadlineSeconds"]; A({"Name": "job-no-deadline", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); j["spec"]["manualSelector"] = True; A({"Name": "job-manual-selector", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); j["metadata"]["labels"]["devplat.io/project"] = "jupiter"; j["spec"]["template"]["metadata"]["labels"]["devplat.io/project"] = "jupiter"
A({"Name": "job-cross-project", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); j["metadata"]["name"] = "dp-" + "x" * 70; A({"Name": "job-name-too-long", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})


# ---------------- namespacer (D19) ----------------
def nsr(name, obj, kind="Namespace", op="CREATE", ns="", old=None, user=NSR):
    exp = "allow" if name.startswith("ok-") else ("skip" if name.startswith("skip-") else "deny")
    i = inp(obj, ns, kind, op, user, old)
    i["paramsByPolicy"]["devplat-namespacer-scope"] = CLUSTER
    return {"Name": name, "Input": i, "Expect": {"devplat-namespacer-scope": exp}}


def peer(app):
    return {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "devplat-system"}}, "podSelector": {"matchLabels": {"app.kubernetes.io/name": app}}}


def netpol(name, spec):
    return {"metadata": {"name": name, "namespace": TNS}, "spec": spec}


GOOD_QUOTA = {"metadata": {"name": "devplat-compute"}, "spec": {"hard": {"pods": "10", "requests.cpu": "4", "limits.cpu": "8", "requests.memory": "8Gi", "limits.memory": "16Gi",
              "requests.ephemeral-storage": "20Gi", "limits.ephemeral-storage": "40Gi", "services": "10", "secrets": "20", "configmaps": "20",
              "services.loadbalancers": "0", "services.nodeports": "0", "persistentvolumeclaims": "0"}}}
GOOD_LR = {"metadata": {"name": "devplat-defaults"}, "spec": {"limits": [{"type": "Container", "max": {"cpu": "2", "memory": "4Gi"}, "default": {"cpu": "1", "memory": "2Gi"}}]}}
RB_OK = {"metadata": {"name": "c"}, "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "devplat-test-runner"},
         "subjects": [{"kind": "ServiceAccount", "name": "devplat-controller", "namespace": "devplat-system"}]}
cases += [
    nsr("ok-create-test-ns", tns()),
    nsr("create-devplat-system", tns("devplat-system")),
    nsr("create-other-project-name", tns("proj-jupiter-t-3fa9c01b")),
    nsr("create-privileged-psa", tns(**{"pod-security.kubernetes.io/enforce": "privileged"})),
    nsr("create-no-managed-by", tns(**{"devplat.io/managed-by": None})),
    nsr("create-runid-not-hex", tns("proj-mercury-t-zzzzzzzz")),
    nsr("create-with-assurance-override", tns(**{"devplat.io/assurance": "reduced"})),
    nsr("ok-delete-test-ns", None, op="DELETE", old=tns()),
    nsr("delete-proj-mercury-exec", None, op="DELETE", old={"metadata": {"name": "proj-mercury-exec", "labels": NS["proj-mercury-exec"]["metadata"]["labels"]}}),
    nsr("delete-unlabelled-lookalike", None, op="DELETE", old=tns(**{"devplat.io/managed-by": None})),
    nsr("ok-rolebinding-test-runner", RB_OK, "RoleBinding", ns=TNS),
    nsr("rolebinding-cluster-admin", dict(RB_OK, roleRef={"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "cluster-admin"}), "RoleBinding", ns=TNS),
    nsr("rolebinding-in-devplat-system", RB_OK, "RoleBinding", ns="devplat-system"),
    nsr("netpol-in-proj-exec", netpol("default-deny-all", {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}), "NetworkPolicy", ns="proj-mercury-exec"),
    nsr("ok-netpol-default-deny", netpol("default-deny-all", {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}), "NetworkPolicy", ns=TNS),
    nsr("ok-netpol-intra-namespace", netpol("allow-intra-namespace", {"podSelector": {}, "policyTypes": ["Ingress", "Egress"],
        "ingress": [{"from": [{"podSelector": {}}]}], "egress": [{"to": [{"podSelector": {}}]}]}), "NetworkPolicy", ns=TNS),
    nsr("ok-netpol-fetch-and-artifacts", netpol("allow-fetch-and-artifacts", {"podSelector": {}, "policyTypes": ["Egress"],
        "egress": [{"to": [peer("devplat-gitbroker-fetch")], "ports": [{"protocol": "TCP", "port": 8081}]},
                   {"to": [peer("devplat-artifact-gateway")], "ports": [{"protocol": "TCP", "port": 8082}]}]}), "NetworkPolicy", ns=TNS),
    nsr("ok-netpol-deps-own-proxy", netpol("allow-deps", {"podSelector": {"matchLabels": {"devplat.io/network-class": "deps"}}, "policyTypes": ["Egress"],
        "egress": [{"to": [peer("devplat-registry-proxy-mercury")], "ports": [{"protocol": "TCP", "port": 4873}]}]}), "NetworkPolicy", ns=TNS),
    nsr("netpol-other-projects-proxy", netpol("allow-deps", {"podSelector": {}, "policyTypes": ["Egress"],
        "egress": [{"to": [peer("devplat-registry-proxy-jupiter")], "ports": [{"protocol": "TCP", "port": 4873}]}]}), "NetworkPolicy", ns=TNS),
    nsr("netpol-model-gateway", netpol("allow-fetch-and-artifacts", {"podSelector": {}, "policyTypes": ["Egress"],
        "egress": [{"to": [peer("devplat-model-gateway")], "ports": [{"protocol": "TCP", "port": 8080}]}]}), "NetworkPolicy", ns=TNS),
    nsr("netpol-unlisted-name", netpol("extra", {"podSelector": {}, "policyTypes": ["Egress"], "egress": [{"to": [{"podSelector": {}}]}]}), "NetworkPolicy", ns=TNS),
    nsr("netpol-ipblock-internet", netpol("allow-deps", {"podSelector": {}, "policyTypes": ["Egress"],
        "egress": [{"to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}], "ports": [{"protocol": "TCP", "port": 443}]}]}), "NetworkPolicy", ns=TNS),
    nsr("netpol-system-peer-without-ports", netpol("allow-fetch-and-artifacts", {"podSelector": {}, "policyTypes": ["Egress"],
        "egress": [{"to": [peer("devplat-gitbroker-fetch")]}]}), "NetworkPolicy", ns=TNS),
    nsr("netpol-ingress-from-other-namespace", netpol("allow-intra-namespace", {"podSelector": {}, "policyTypes": ["Ingress"],
        "ingress": [{"from": [{"namespaceSelector": {}}]}]}), "NetworkPolicy", ns=TNS),
    nsr("ok-quota-within-caps", GOOD_QUOTA, "ResourceQuota", ns=TNS),
    nsr("quota-missing-key", {"metadata": {"name": "q"}, "spec": {"hard": {"pods": "10"}}}, "ResourceQuota", ns=TNS),
    nsr("quota-with-scope", {"metadata": {"name": "q"}, "spec": dict(GOOD_QUOTA["spec"], scopes=["BestEffort"])}, "ResourceQuota", ns=TNS),
    nsr("quota-nodeports", {"metadata": {"name": "q"}, "spec": {"hard": dict(GOOD_QUOTA["spec"]["hard"], **{"services.nodeports": "5"})}}, "ResourceQuota", ns=TNS),
    nsr("ok-limitrange-within-caps", GOOD_LR, "LimitRange", ns=TNS),
    nsr("limitrange-over-cap", {"metadata": {"name": "l"}, "spec": {"limits": [{"type": "Container", "max": {"cpu": "64", "memory": "4Gi"}}]}}, "LimitRange", ns=TNS),
    nsr("limitrange-no-container-max", {"metadata": {"name": "l"}, "spec": {"limits": [{"type": "PersistentVolumeClaim", "max": {"storage": "1Gi"}}]}}, "LimitRange", ns=TNS),
    nsr("ok-params-configmap", NSP[TNS], "ConfigMap", ns=TNS),
    nsr("params-configmap-other-projects-images", dict(NSP[TNS], data={"allowedImagePrefixes": f"{RB}devplat/,{RB}projects/,{RB}mirror/"}), "ConfigMap", ns=TNS),
    nsr("params-configmap-mutable", {k: v for k, v in NSP[TNS].items() if k != "immutable"}, "ConfigMap", ns=TNS),
    nsr("configmap-other-name", dict(NSP[TNS], metadata={"name": "x"}), "ConfigMap", ns=TNS),
    nsr("skip-other-user", tns("devplat-system"), user=CTL),
]

# ---------------- build/runtime/procMount ----------------
p = build_pod(); p["spec"]["hostUsers"] = True; p["spec"]["containers"][0]["securityContext"]["procMount"] = "Unmasked"
A(pods("buildkitd-unmasked-no-userns", p, "proj-mercury-build", {"devplat-pod-hardening": "deny"}))
p = build_pod(); p["spec"]["containers"][0]["securityContext"]["procMount"] = "Unmasked"; A(pods("buildkitd-unmasked-userns", p, "proj-mercury-build", {"devplat-pod-hardening": "allow"}))
p = agent_pod(); p["spec"]["hostUsers"] = False; p["spec"]["containers"][0]["securityContext"]["procMount"] = "Unmasked"; A(pods("agent-unmasked-userns", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod("proj-mercury-build"); p["metadata"]["labels"]["devplat.io/workload"] = "build"; p["spec"]["serviceAccountName"] = "mercury-build"; p["metadata"]["labels"]["devplat.io/network-class"] = "model-only"
A(pods("build-with-model-class", p, "proj-mercury-build", {"devplat-proj-pod-identity": "deny"}))
p = build_pod(); p["spec"]["containers"][0]["args"] = ["--oci-worker-no-process-sandbox", "--allow-insecure-entitlement", "security.insecure"]
A(pods("D20-buildkitd-args-not-pinned", p, "proj-mercury-build", {"devplat-build-exceptions": "deny"}, BON))
p = build_pod(); p["spec"]["containers"][0]["securityContext"]["seccompProfile"] = {"type": "Localhost", "localhostProfile": "profiles/other.json"}
A(pods("D20-buildkitd-other-localhost-profile", p, "proj-mercury-build", {"devplat-build-exceptions": "deny"}, BON))
p = build_pod(); p["spec"]["containers"][0]["command"] = ["/bin/sh", "-c", "id"]
A(pods("D20-buildkitd-command-override", p, "proj-mercury-build", {"devplat-build-exceptions": "deny"}, BON))
# D16 reduced assurance
RED = copy.deepcopy(CLUSTER); RED["data"]["reducedProjects"] = "mercury"
p = agent_pod(); del p["spec"]["runtimeClassName"]
A(pods("D16-reduced-project-unsandboxed-agent", p, "proj-mercury-exec", {"devplat-proj-runtime-placement": "allow"}, {"devplat-proj-runtime-placement": RED}))
A(pods("D16-reduced-project-no-builds", build_pod(), "proj-mercury-build", {"devplat-proj-runtime-placement": "deny"}, {"devplat-proj-runtime-placement": RED}))
p = agent_pod("proj-jupiter-exec", "jupiter"); del p["spec"]["runtimeClassName"]; p["spec"]["containers"][0]["image"] = p["spec"]["initContainers"][0]["image"]
A(pods("D16-other-project-still-sandboxed", p, "proj-jupiter-exec", {"devplat-proj-runtime-placement": "deny"}, {"devplat-proj-runtime-placement": RED}))
# D15 per-namespace image prefixes
p = plat("devplat-api", "x"); p["spec"]["containers"][0]["image"] = "registry.devplat.internal/projects/mercury/tool@sha256:" + "f" * 64
A(pods("D15-project-image-in-platform-namespace", p, "devplat-system", {"devplat-image-pinning": "deny"}))
p = agent_pod(); p["spec"]["containers"][0]["image"] = "registry.devplat.internal/projects/mercury/toolchain@sha256:" + "f" * 64
A(pods("ok-D15-own-project-image", p, "proj-mercury-exec", {"devplat-image-pinning": "allow"}))
p = agent_pod(ns=TNS); p["metadata"]["labels"]["devplat.io/workload"] = "test"; p["metadata"]["labels"]["devplat.io/network-class"] = "none"; p["spec"]["serviceAccountName"] = "default"
A(pods("ok-test-pod-in-test-namespace", p, TNS, dict(ALLP)))
# S-19 more PV binding paths
p = agent_pod(); p["spec"]["volumes"].append({"name": "pvc", "persistentVolumeClaim": {"claimName": "devplat-registry-proxy-cache"}})
A(pods("S19-pvc-by-name", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["volumes"].append({"name": "e", "ephemeral": {"volumeClaimTemplate": {"spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": "standard", "dataSource": {"kind": "VolumeSnapshot", "name": "snap", "apiGroup": "snapshot.storage.k8s.io"}, "resources": {"requests": {"storage": "1Gi"}}}}}})
A(pods("S19-ephemeral-from-snapshot", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["volumes"].append({"name": "e", "ephemeral": {"volumeClaimTemplate": {"spec": {"accessModes": ["ReadWriteOnce"], "storageClassName": "standard", "resources": {"requests": {"storage": "1Gi"}}}}}})
A(pods("ok-S19-fresh-ephemeral", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "allow"}))
# S-21 pod-level SELinux
p = agent_pod(); p["spec"]["securityContext"]["seLinuxOptions"] = {"user": "system_u", "role": "system_r", "type": "container_t"}
A(pods("S21-pod-selinux-user-role", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
# S-20 Services
def svc(name, spec, ns=TNS):
    return {"Name": name, "Input": inp({"metadata": {"name": "s", "namespace": ns}, "spec": spec}, ns, "Service"),
            "Expect": {"devplat-service-restrictions": "allow" if name.startswith("ok-") else "deny"}}
cases += [svc("ok-S20-clusterip-fixture", {"type": "ClusterIP", "ports": [{"port": 5432}], "selector": {"app": "db"}}),
          svc("S20-externalIPs", {"type": "ClusterIP", "ports": [{"port": 80}], "externalIPs": ["10.0.0.1"]}),
          svc("S20-externalName", {"type": "ExternalName", "externalName": "api.github.com"}),
          svc("S20-nodeport", {"type": "NodePort", "ports": [{"port": 80}]}),
          svc("S20-loadbalancer-in-system", {"type": "LoadBalancer", "ports": [{"port": 80}]}, "devplat-system")]


# ---------------- controller Job update / run objects ----------------
def upd(name, new, old, expect):
    return {"Name": name, "Input": inp(new, "proj-mercury-exec", "Job", "UPDATE", CTL, old), "Expect": {"devplat-controller-job-update": expect}}


o = job(); o["spec"]["suspend"] = True
n = copy.deepcopy(o); n["spec"]["suspend"] = False; A(upd("ok-unsuspend", n, o, "allow"))
n2 = copy.deepcopy(n); n2["spec"]["template"]["spec"]["containers"][0]["image"] = "registry.devplat.internal/devplat/evil@sha256:" + "d" * 64; A(upd("unsuspend-and-swap-image", n2, o, "deny"))
o2 = copy.deepcopy(o); o2["spec"]["suspend"] = False; n3 = copy.deepcopy(o2); n3["spec"]["suspend"] = True; A(upd("resuspend", n3, o2, "deny"))
n4 = copy.deepcopy(o); n4["spec"]["template"]["spec"]["nodeSelector"] = {"kubernetes.io/hostname": "control-1"}; A(upd("move-to-control-node-while-suspended", n4, o, "deny"))
n5 = copy.deepcopy(o); n5["spec"]["podFailurePolicy"] = {"rules": [{"action": "Ignore", "onPodConditions": [{"type": "DisruptionTarget"}]}]}; A(upd("S18-add-podFailurePolicy", n5, o, "deny"))
n6 = copy.deepcopy(o); n6["spec"]["completions"] = 5; A(upd("S18-raise-completions", n6, o, "deny"))


def ro(name, obj, op, old, expect, kind="Secret"):
    return {"Name": name, "Input": inp(obj, "proj-mercury-exec", kind, op, CTL, old), "Expect": {"devplat-controller-run-objects": expect}}


own = [{"apiVersion": "batch/v1", "kind": "Job", "name": "dp-mercury-dt-0001-a1", "uid": "u", "controller": True}]
cases += [ro("ok-run-secret", {"metadata": {"name": "dp-mercury-dt-0001-a1-io", "ownerReferences": own}, "type": "Opaque", "immutable": True}, "CREATE", None, "allow"),
          ro("run-secret-mutable", {"metadata": {"name": "dp-mercury-dt-0001-a1-io", "ownerReferences": own}}, "CREATE", None, "deny"),
          ro("run-secret-no-owner", {"metadata": {"name": "dp-mercury-dt-0001-a1-io"}, "immutable": True}, "CREATE", None, "deny"),
          ro("secret-in-system-name", {"metadata": {"name": "devplat-gitbroker-github-app", "ownerReferences": own}, "immutable": True}, "CREATE", None, "deny"),
          ro("delete-foreign-secret", None, "DELETE", {"metadata": {"name": "devplat-db-api"}}, "deny"),
          ro("controller-replaces-params-configmap", {"metadata": {"name": "devplat-admission-params", "ownerReferences": own}, "immutable": True}, "CREATE", None, "deny", "ConfigMap"),
          ro("S17-dockerconfig-secret", {"metadata": {"name": "dp-mercury-dt-0001-a1-io", "ownerReferences": own}, "type": "kubernetes.io/dockerconfigjson", "immutable": True}, "CREATE", None, "deny"),
          ro("ok-delete-stale-run-cm", None, "DELETE", {"metadata": {"name": "dp-mercury-dt-0001-a1-contract"}}, "allow", "ConfigMap")]

# ---------------- doc 16 example Job, as written (cross-check) ----------------
# reads the vendored fixture (platform-only; R6 A-04), which test_jobspec.py keeps equal to doc 16 §4.1 and to build_job()
dj = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "controller", "testdata", "job-example.yaml")))
A({"Name": "doc16-example-job", "Input": inp(dj, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "allow"}})
dp = {"metadata": dict(dj["spec"]["template"]["metadata"], namespace="proj-mercury-exec"), "spec": dj["spec"]["template"]["spec"]}
A(pods("doc16-example-pod-as-written", dp, "proj-mercury-exec", dict(ALLP)))

# ---------------- R6 reviewer exploit cases E1-E11: regressions, every one must be DENIED ----------------
A(nsr("R6-E1-netpol-allow-all-egress-in-test-ns", netpol("allow-intra-namespace", {"podSelector": {}, "policyTypes": ["Egress"], "egress": [{}]}), "NetworkPolicy", ns=TNS))
A(nsr("R6-E2-quota-unbounded", {"metadata": {"name": "q"}, "spec": {"hard": dict(GOOD_QUOTA["spec"]["hard"], pods="100000", **{"requests.cpu": "100000"})}}, "ResourceQuota", ns=TNS))
sat = {"metadata": {"name": "dp-mercury-dt-0001-a1-io", "ownerReferences": own, "annotations": {"kubernetes.io/service-account.name": "mercury-agent"}}, "type": "kubernetes.io/service-account-token", "immutable": True}
A(ro("R6-E3-sa-token-secret", sat, "CREATE", None, "deny"))
# E4 (pod mounting a dp-* SA-token Secret) is closed at the source: E3 makes such a Secret impossible to create
# through the controller; pods may mount only dp-* names, so no other Secret type can appear there.
o = job(); n = copy.deepcopy(o); n["spec"]["parallelism"] = 50
A(upd("R6-E5-raise-parallelism", n, o, "deny"))
p = build_pod("helper", BK); c = p["spec"]["containers"][0]["securityContext"]; c["seccompProfile"] = {"type": "RuntimeDefault"}; c["allowPrivilegeEscalation"] = False; c["seLinuxOptions"] = {"type": "spc_t"}
A(pods("R6-E6-build-selinux-spc_t", p, "proj-mercury-build", {"devplat-pod-hardening": "deny"}, BON))
p = build_pod(); p["spec"]["hostUsers"] = True; del p["spec"]["runtimeClassName"]; p["spec"]["nodeSelector"] = {"devplat.io/pool": "build"}
p["spec"]["containers"][0]["securityContext"]["seccompProfile"] = {"type": "Unconfined"}; p["spec"]["containers"][0]["securityContext"]["appArmorProfile"] = {"type": "Unconfined"}
A(pods("R6-E7-buildkitd-unconfined-host-userns", p, "proj-mercury-build", {"devplat-build-exceptions": "deny"}, BON))
p = agent_pod(); p["spec"]["volumes"].append({"name": "steal", "ephemeral": {"volumeClaimTemplate": {"spec": {"accessModes": ["ReadWriteOnce"], "volumeName": "pvc-registry-proxy-cache", "storageClassName": "", "resources": {"requests": {"storage": "1Gi"}}}}}})
A(pods("R6-E8-ephemeral-volumeName", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["containers"][0]["image"] = "registry.devplat.internal/projects/jupiter/built@sha256:" + "e" * 64
A(pods("R6-E9-cross-project-image", p, "proj-mercury-exec", {"devplat-image-pinning": "deny"}))
A(nsr("R6-E10-lookalike-ns", tns("proj-mercury-t-deadbeef-t-12345678")))
p = agent_pod(); del p["metadata"]["labels"]["devplat.io/network-class"]
A(pods("R6-E11-no-network-class", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))

json.dump({"Policies": D["pols"], "Cases": cases}, open(sys.argv[2], "w"))
print(len(cases), "cases,", sum(len(c["Expect"]) for c in cases), "decisions,", sum(1 for c in cases if c["Name"].startswith("R6-E")), "R6 exploit regressions")
