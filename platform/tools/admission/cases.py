import json, copy, os, sys
D = json.load(open(sys.argv[1]))
NS, PARAMS = D["ns"], D["params"]
IMG = "registry.devplat.internal/devplat/agent@sha256:" + "a" * 64
BK = "registry.devplat.internal/mirror/moby/buildkit@sha256:" + "b" * 64
def req(kind, op="CREATE", ns="", user="system:serviceaccount:kube-system:job-controller"):
    return {"kind": {"group": "", "version": "v1", "kind": kind}, "operation": op, "namespace": ns, "userInfo": {"username": user}}
def agent_pod(ns="proj-mercury-exec", project="mercury"):
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "dp-mercury-dt-0001-a1-x", "namespace": ns,
            "labels": {"devplat.io/project": project, "devplat.io/role": "mdev-backend-engineer", "devplat.io/workload": "agent", "devplat.io/network-class": "deps"}},
            "spec": {"serviceAccountName": "mercury-agent", "automountServiceAccountToken": False, "runtimeClassName": "gvisor",
                     "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                     "initContainers": [{"name": "fetch", "image": IMG, "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}}],
                     "containers": [{"name": "agent", "image": IMG, "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                                     "env": [{"name": "RUN_TOKEN", "valueFrom": {"secretKeyRef": {"name": "dp-mercury-dt-0001-a1-run", "key": "token"}}}]}],
                     "volumes": [{"name": "ws", "emptyDir": {}}, {"name": "run", "secret": {"secretName": "dp-mercury-dt-0001-a1-run"}},
                                 {"name": "role", "configMap": {"name": "dp-mercury-dt-0001-a1-role"}}]}}
def build_pod(cname="buildkitd", image=BK):
    p = agent_pod("proj-mercury-build")
    p["metadata"]["labels"]["devplat.io/workload"] = "build"; p["metadata"]["labels"]["devplat.io/network-class"] = "none"; p["spec"]["serviceAccountName"] = "mercury-build"
    p["spec"]["initContainers"] = []
    p["spec"]["containers"] = [{"name": cname, "image": image, "securityContext": {"runAsNonRoot": True, "runAsUser": 1000,
        "allowPrivilegeEscalation": True, "seccompProfile": {"type": "Unconfined"}, "appArmorProfile": {"type": "Unconfined"}, "capabilities": {"drop": ["ALL"]}}}]
    p["spec"]["volumes"] = [{"name": "cache", "emptyDir": {}}]
    return p
def inp(obj, ns, kind="Pod", op="CREATE", user="system:serviceaccount:kube-system:job-controller", old=None):
    return {"object": obj, "oldObject": old, "namespaceObject": NS.get(ns), "params": PARAMS, "request": req(kind, op, ns, user)}
def pods(name, obj, ns, expect): return {"Name": name, "Input": inp(obj, ns), "Expect": expect}
ALLP = {"devplat-pod-hardening": "allow", "devplat-proj-pod-identity": "allow", "devplat-proj-runtime-placement": "allow", "devplat-image-pinning": "allow"}
cases = [pods("good-agent-pod", agent_pod(), "proj-mercury-exec", dict(ALLP))]
p = agent_pod(); p["spec"]["volumes"].append({"name": "sock", "hostPath": {"path": "/var/run/docker.sock"}})
cases.append(pods("docker-sock-hostpath", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny", "devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["hostNetwork"] = True; cases.append(pods("hostNetwork", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod(); p["spec"]["containers"][0]["securityContext"]["privileged"] = True; cases.append(pods("privileged", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod(); p["spec"]["ephemeralContainers"] = [{"name": "dbg", "image": IMG}]; cases.append(pods("ephemeral-container", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod(); del p["spec"]["automountServiceAccountToken"]; cases.append(pods("automount-unset", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["serviceAccountName"] = "jupiter-agent"; cases.append(pods("other-project-sa", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["volumes"].append({"name": "tok", "projected": {"sources": [{"serviceAccountToken": {"path": "t"}}]}}); cases.append(pods("projected-sa-token", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); p["spec"]["volumes"][1]["secret"]["secretName"] = "devplat-gitbroker-github-app"; cases.append(pods("non-run-secret", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(project="jupiter"); cases.append(pods("cross-project-label", p, "proj-mercury-exec", {"devplat-proj-pod-identity": "deny"}))
p = agent_pod(); del p["spec"]["runtimeClassName"]; cases.append(pods("no-runtimeclass-exec", p, "proj-mercury-exec", {"devplat-proj-runtime-placement": "deny", "devplat-proj-pod-identity": "allow"}))
p = agent_pod(); p["spec"]["containers"][0]["image"] = "registry.example.invalid/devplat/agent:latest"; cases.append(pods("tag-not-digest", p, "proj-mercury-exec", {"devplat-image-pinning": "deny"}))
p = agent_pod(); p["spec"]["containers"][0]["image"] = "docker.io/library/alpine@sha256:" + "c" * 64; cases.append(pods("foreign-registry", p, "proj-mercury-exec", {"devplat-image-pinning": "deny"}))
cases.append(pods("buildkitd-rootless", build_pod(), "proj-mercury-build", {**ALLP, "devplat-build-exceptions": "allow"}))
cases.append(pods("unconfined-not-buildkitd", build_pod("evil", BK), "proj-mercury-build", {"devplat-build-exceptions": "deny"}))
cases.append(pods("buildkitd-name-other-image", build_pod("buildkitd", IMG), "proj-mercury-build", {"devplat-build-exceptions": "deny"}))
p = build_pod(); p["spec"]["containers"][0]["securityContext"]["capabilities"] = {"drop": ["NET_RAW"]}; cases.append(pods("build-no-drop-all", p, "proj-mercury-build", {"devplat-build-exceptions": "deny"}))
p = build_pod(); del p["spec"]["runtimeClassName"]; cases.append(pods("build-unsandboxed-off-pool", p, "proj-mercury-build", {"devplat-proj-runtime-placement": "deny"}))
p = build_pod(); del p["spec"]["runtimeClassName"]; p["spec"]["nodeSelector"] = {"devplat.io/pool": "build"}; cases.append(pods("build-on-build-pool", p, "proj-mercury-build", {"devplat-proj-runtime-placement": "allow"}))
# platform pods
def plat(sa, secret):
    return {"metadata": {"name": "x", "namespace": "devplat-system", "labels": {}}, "spec": {"serviceAccountName": sa,
            "containers": [{"name": "c", "image": IMG}], "volumes": [{"name": "k", "secret": {"secretName": secret}}]}}
cases.append(pods("gitbroker-key-by-gitbroker", plat("devplat-gitbroker", "devplat-gitbroker-github-app"), "devplat-system", {"devplat-secret-pinning": "allow", "devplat-platform-placement": "allow"}))
cases.append(pods("gitbroker-key-by-api", plat("devplat-api", "devplat-gitbroker-github-app"), "devplat-system", {"devplat-secret-pinning": "deny"}))
p = plat("devplat-api", "x"); p["spec"]["containers"][0]["env"] = [{"name": "K", "valueFrom": {"secretKeyRef": {"name": "devplat-model-gateway-llm-keys", "key": "anthropic"}}}]
cases.append(pods("llm-key-env-by-api", p, "devplat-system", {"devplat-secret-pinning": "deny"}))
p = plat("devplat-api", "x"); p["spec"]["tolerations"] = [{"operator": "Exists"}]; cases.append(pods("platform-wildcard-toleration", p, "devplat-system", {"devplat-platform-placement": "deny"}))
p = plat("devplat-api", "x"); p["spec"]["tolerations"] = [{"key": "node.kubernetes.io/not-ready", "operator": "Exists", "effect": "NoExecute", "tolerationSeconds": 300}]; cases.append(pods("platform-default-toleration", p, "devplat-system", {"devplat-platform-placement": "allow"}))
# jobs
def job():
    L = {"devplat.io/project": "mercury", "devplat.io/task": "dt-0001", "devplat.io/attempt": "1", "devplat.io/role": "mdev-backend-engineer", "devplat.io/network-class": "deps"}
    return {"metadata": {"name": "dp-mercury-dt-0001-a1", "namespace": "proj-mercury-exec", "labels": dict(L, **{"devplat.io/idempotency-key": "k1"})},
            "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 7200, "ttlSecondsAfterFinished": 3600, "parallelism": 1, "completions": 1,
                     "template": {"metadata": {"labels": dict(L, **{"devplat.io/workload": "agent"})}, "spec": {"automountServiceAccountToken": False, "containers": [{"name": "agent", "image": IMG}]}}}}
cases.append({"Name": "good-job", "Input": inp(job(), "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "allow"}})
j = job(); j["spec"]["backoffLimit"] = 6; cases.append({"Name": "job-backoff-6", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); del j["spec"]["activeDeadlineSeconds"]; cases.append({"Name": "job-no-deadline", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); j["spec"]["manualSelector"] = True; cases.append({"Name": "job-manual-selector", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); j["metadata"]["labels"]["devplat.io/project"] = "jupiter"; j["spec"]["template"]["metadata"]["labels"]["devplat.io/project"] = "jupiter"
cases.append({"Name": "job-cross-project", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
j = job(); j["metadata"]["name"] = "dp-" + "x" * 70; cases.append({"Name": "job-name-too-long", "Input": inp(j, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "deny"}})
# namespacer
NSR = "system:serviceaccount:devplat-system:devplat-namespacer"
def tns(name="proj-mercury-t-3fa9c01b", **over):
    L = {"devplat.io/managed-by": "devplat-controller", "devplat.io/ns-role": "test", "devplat.io/project": "mercury",
         "pod-security.kubernetes.io/enforce": "restricted"}; L.update(over)
    return {"metadata": {"name": name, "labels": {k: v for k, v in L.items() if v is not None}}}
def nsr(name, obj, kind="Namespace", op="CREATE", ns="", old=None, user=NSR):
    return {"Name": name, "Input": {"object": obj, "oldObject": old, "namespaceObject": None, "params": None, "request": req(kind, op, ns, user)}, "Expect": {"devplat-namespacer-scope": "allow" if name.startswith("ok-") else ("skip" if name.startswith("skip-") else "deny")}}
cases += [nsr("ok-create-test-ns", tns()),
          nsr("create-devplat-system", tns("devplat-system")),
          nsr("create-other-project-name", tns("proj-jupiter-t-3fa9c01b")),
          nsr("create-privileged-psa", tns(**{"pod-security.kubernetes.io/enforce": "privileged"})),
          nsr("create-no-managed-by", tns(**{"devplat.io/managed-by": None})), nsr("create-runid-not-hex", tns("proj-mercury-t-zzzzzzzz")),
          nsr("ok-delete-test-ns", None, op="DELETE", old=tns()),
          nsr("delete-proj-mercury-exec", None, op="DELETE", old={"metadata": {"name": "proj-mercury-exec", "labels": NS["proj-mercury-exec"]["metadata"]["labels"]}}),
          nsr("delete-unlabelled-lookalike", None, op="DELETE", old=tns(**{"devplat.io/managed-by": None})),
          nsr("ok-rolebinding-test-runner", {"metadata": {"name": "c"}, "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "devplat-test-runner"},
                                             "subjects": [{"kind": "ServiceAccount", "name": "devplat-controller", "namespace": "devplat-system"}]}, "RoleBinding", ns="proj-mercury-t-3fa9c01b"),
          nsr("rolebinding-cluster-admin", {"metadata": {"name": "c"}, "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "cluster-admin"},
                                             "subjects": [{"kind": "ServiceAccount", "name": "devplat-controller", "namespace": "devplat-system"}]}, "RoleBinding", ns="proj-mercury-t-3fa9c01b"),
          nsr("rolebinding-in-devplat-system", {"metadata": {"name": "c"}, "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "devplat-test-runner"},
                                             "subjects": [{"kind": "ServiceAccount", "name": "devplat-controller", "namespace": "devplat-system"}]}, "RoleBinding", ns="devplat-system"),
          nsr("netpol-in-proj-exec", {"metadata": {"name": "allow-all"}, "spec": {}}, "NetworkPolicy", ns="proj-mercury-exec"),
          nsr("skip-other-user", tns("devplat-system"), user="system:serviceaccount:devplat-system:devplat-controller")]
# procMount exception
p = build_pod(); p["spec"]["containers"][0]["securityContext"]["procMount"] = "Unmasked"; cases.append(pods("buildkitd-unmasked-no-userns", p, "proj-mercury-build", {"devplat-pod-hardening": "deny"}))
p = build_pod(); p["spec"]["hostUsers"] = False; p["spec"]["containers"][0]["securityContext"]["procMount"] = "Unmasked"; cases.append(pods("buildkitd-unmasked-userns", p, "proj-mercury-build", {"devplat-pod-hardening": "allow"}))
p = agent_pod(); p["spec"]["hostUsers"] = False; p["spec"]["containers"][0]["securityContext"]["procMount"] = "Unmasked"; cases.append(pods("agent-unmasked-userns", p, "proj-mercury-exec", {"devplat-pod-hardening": "deny"}))
p = agent_pod("proj-mercury-build"); p["metadata"]["labels"]["devplat.io/workload"] = "build"; p["spec"]["serviceAccountName"] = "mercury-build"; p["metadata"]["labels"]["devplat.io/network-class"] = "model-only"
cases.append(pods("build-with-model-class", p, "proj-mercury-build", {"devplat-proj-pod-identity": "deny"}))
# controller job update / run objects
CTL = "system:serviceaccount:devplat-system:devplat-controller"
def upd(name, new, old, expect):
    return {"Name": name, "Input": {"object": new, "oldObject": old, "namespaceObject": NS["proj-mercury-exec"], "params": None, "request": req("Job", "UPDATE", "proj-mercury-exec", CTL)}, "Expect": {"devplat-controller-job-update": expect}}
o = job(); o["spec"]["suspend"] = True
n = copy.deepcopy(o); n["spec"]["suspend"] = False; cases.append(upd("ok-unsuspend", n, o, "allow"))
n = copy.deepcopy(n); n["spec"]["template"]["spec"]["containers"][0]["image"] = "registry.devplat.internal/devplat/evil@sha256:" + "d" * 64; cases.append(upd("unsuspend-and-swap-image", n, o, "deny"))
o2 = copy.deepcopy(o); o2["spec"]["suspend"] = False; n = copy.deepcopy(o2); n["spec"]["suspend"] = True; cases.append(upd("resuspend", n, o2, "deny"))
n = copy.deepcopy(o); n["spec"]["template"]["spec"]["nodeSelector"] = {"kubernetes.io/hostname": "control-1"}; cases.append(upd("move-to-control-node-while-suspended", n, o, "deny"))
def ro(name, obj, op, old, expect, kind="Secret"):
    return {"Name": name, "Input": {"object": obj, "oldObject": old, "namespaceObject": NS["proj-mercury-exec"], "params": None, "request": req(kind, op, "proj-mercury-exec", CTL)}, "Expect": {"devplat-controller-run-objects": expect}}
own = [{"apiVersion": "batch/v1", "kind": "Job", "name": "dp-mercury-dt-0001-a1", "uid": "u", "controller": True}]
cases += [ro("ok-run-secret", {"metadata": {"name": "dp-mercury-dt-0001-a1-io", "ownerReferences": own}, "immutable": True}, "CREATE", None, "allow"),
          ro("run-secret-mutable", {"metadata": {"name": "dp-mercury-dt-0001-a1-io", "ownerReferences": own}}, "CREATE", None, "deny"),
          ro("run-secret-no-owner", {"metadata": {"name": "dp-mercury-dt-0001-a1-io"}, "immutable": True}, "CREATE", None, "deny"),
          ro("secret-in-system-name", {"metadata": {"name": "devplat-gitbroker-github-app", "ownerReferences": own}, "immutable": True}, "CREATE", None, "deny"),
          ro("delete-foreign-secret", None, "DELETE", {"metadata": {"name": "devplat-db-api"}}, "deny"),
          ro("ok-delete-stale-run-cm", None, "DELETE", {"metadata": {"name": "dp-mercury-dt-0001-a1-contract"}}, "allow", "ConfigMap")]
# doc 16 example Job, as written (cross-check)
import yaml, re
txt = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "docs/mercury/development-orchestration/16-agent-execution-and-job-lifecycle.md")).read()
m = re.search(r"```yaml\n(# Rendered by devplat-controller.*?)```", txt, re.S)
dj = yaml.safe_load(m.group(1))
cases.append({"Name": "doc16-example-job", "Input": inp(dj, "proj-mercury-exec", "Job"), "Expect": {"devplat-job-shape": "allow"}})
dp = {"metadata": dict(dj["spec"]["template"]["metadata"], namespace="proj-mercury-exec"), "spec": dj["spec"]["template"]["spec"]}
# doc 16 now uses the canonical `<project>-agent` ServiceAccount (I-7 resolved), so the example pod passes every policy
cases.append(pods("doc16-example-pod-as-written", dp, "proj-mercury-exec", {"devplat-pod-hardening": "allow", "devplat-proj-pod-identity": "allow", "devplat-proj-runtime-placement": "allow", "devplat-image-pinning": "allow"}))
dp2 = copy.deepcopy(dp); dp2["spec"]["serviceAccountName"] = "mercury-agent"
cases.append(pods("doc16-example-pod-sa-renamed", dp2, "proj-mercury-exec", {"devplat-pod-hardening": "allow", "devplat-proj-pod-identity": "allow", "devplat-proj-runtime-placement": "allow", "devplat-image-pinning": "allow"}))
json.dump({"Policies": D["pols"], "Cases": cases}, open(sys.argv[2], "w"))
print(len(cases), "cases")
