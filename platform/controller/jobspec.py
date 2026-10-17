#!/usr/bin/env python3
"""Build the Kubernetes Job for one agent run (devplat controller; pure function, no cluster access).

Reference implementation of 16-agent-execution-and-job-lifecycle.md §4.1: `test_jobspec.py` asserts that
build_job() reproduces the documented example Job exactly, validates the output against the strict
Kubernetes v1.33 Job schema, and checks every security rule of 18-kubernetes-security-model.md that a
Job spec can carry (no service-account token, non-root, read-only root filesystem, no capabilities,
seccomp RuntimeDefault, no host namespaces or hostPath, exec node pool + RuntimeClass, digest-pinned images,
controller-owned retries, deadline, deterministic idempotent name).

Inputs are the versioned documents the controller already holds:
  contract  devorch.task_contract.v1 (task_id, kind, base_commit, contract_version, budget)
  project   devplat.project.v1 (project_id, execution_target.namespace_prefix)
  profile   one entry of platform/agents/execution-profiles.yaml (+ its `defaults`)
  run       facts chosen by the controller: attempt, contract_core_sha256, images, role ConfigMap,
            dns_ip (ClusterIP of devplat-dns, looked up by the controller)
"""
import hashlib, os, re

L = "devplat.io"
NAME_MAX = 63
DIGEST = re.compile(r".+@sha256:[0-9a-f]{64}")


def dns_label(s):
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")


def job_name(project_id, task_id, attempt, dispatch_no=1):
    """Deterministic: the same (project, task, attempt, dispatch) always gives the same name, so a controller
    retry after a crash gets AlreadyExists and adopts the existing Job instead of starting a second run.
    dispatch_no (job_runs.dispatch_no, 19-…) distinguishes environmental retries within one attempt, which must
    get a NEW Job rather than adopt the failed one."""
    base = f"dp-{dns_label(project_id)}-{dns_label(task_id)}-a{attempt}-d{dispatch_no}"
    if len(base) <= NAME_MAX - 9:          # leave room for the "-contract" ConfigMap suffix
        return base
    h = hashlib.sha256(base.encode()).hexdigest()[:10]
    return f"{base[:NAME_MAX - 9 - 11].rstrip('-')}-{h}"


def idempotency_key(project_id, task_id, contract_core_sha256, attempt, dispatch_no=1):
    return hashlib.sha256(f"{project_id}|{task_id}|{contract_core_sha256}|{attempt}|{dispatch_no}".encode()).hexdigest()[:40]


def _hardened():
    return {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}}


def build_job(contract, project, profile, defaults, run):
    for img in (run["fetch_image"], run["agent_image"]):
        if not DIGEST.fullmatch(img):
            raise ValueError(f"image must be pinned by digest: {img}")
    pid, tid, att, dno = project["project_id"], contract["task_id"], run["attempt"], run.get("dispatch_no", 1)
    name = job_name(pid, tid, att, dno)
    ns = project["execution_target"]["namespace_prefix"] + "-exec"
    role = profile["role"]
    net = profile["network_class"]
    wall_min = min(contract["budget"]["max_wall_minutes"], profile["max_wall_minutes"])
    turns = min(contract["budget"]["max_turns"], profile["max_turns"])
    sel = {f"{L}/project": dns_label(pid), f"{L}/task": dns_label(tid), f"{L}/attempt": str(att),
           f"{L}/dispatch": str(dno), f"{L}/role": role}
    labels = {"app.kubernetes.io/managed-by": "devplat-controller", **sel, f"{L}/kind": contract["kind"],
              f"{L}/network-class": net,
              f"{L}/idempotency-key": idempotency_key(pid, tid, run["contract_core_sha256"], att, dno)}
    annotations = {f"{L}/contract-core-sha256": run["contract_core_sha256"],
                   f"{L}/contract-version": str(contract["contract_version"]),
                   f"{L}/base-commit": contract["base_commit"],
                   f"{L}/role-definition-sha256": run["role_definition_sha256"],
                   f"{L}/profile": f"{role}@devplat.execution_profiles.v1"}
    defn = os.path.basename(profile["agent_definition"])
    res = profile["resources"]
    pod = {
        "restartPolicy": "Never",
        "serviceAccountName": f"{dns_label(pid)}-agent",   # zero RBAC bindings (18-… §7)
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        # devplat-dns only: no internet forwarding, so DNS cannot be used to tunnel data out (18-… §10)
        "dnsPolicy": "None",
        "dnsConfig": {"nameservers": [run["dns_ip"]],
                      "searches": [f"{ns}.svc.cluster.local", "svc.cluster.local", "cluster.local"],
                      "options": [{"name": "ndots", "value": "5"}]},
        "runtimeClassName": profile["runtime_class"],
        "priorityClassName": defaults["priority_class"],
        "terminationGracePeriodSeconds": defaults["termination_grace_seconds"],
        "nodeSelector": {f"{L}/pool": "exec"},
        "tolerations": [{"key": f"{L}/exec", "operator": "Equal", "value": "true", "effect": "NoSchedule"}],
        "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "fsGroup": 10001,
                            "seccompProfile": {"type": "RuntimeDefault"}},
        "initContainers": [{
            "name": "fetch", "image": run["fetch_image"],
            "args": ["--io=/etc/devplat/io", "--contract=/etc/devplat/contract/contract.json", "--dest=/workspace/repo"],
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi", "ephemeral-storage": "64Mi"},
                          "limits": {"cpu": "500m", "memory": "512Mi", "ephemeral-storage": "256Mi"}},
            "securityContext": _hardened(),
            "volumeMounts": [{"name": "workspace", "mountPath": "/workspace"},
                             {"name": "io", "mountPath": "/etc/devplat/io", "readOnly": True},
                             {"name": "contract", "mountPath": "/etc/devplat/contract", "readOnly": True},
                             {"name": "tmp", "mountPath": "/tmp"}],
        }],
        "containers": [{
            "name": "agent", "image": run["agent_image"], "workingDir": "/workspace/repo",
            "args": ["--contract=/etc/devplat/contract/contract.json", f"--role={role}", "--io=/etc/devplat/io",
                     "--out=/out", f"--max-turns={turns}", f"--wall-seconds={wall_min * 60}"],
            "env": [{"name": "HOME", "value": "/home/agent"},
                    {"name": "ANTHROPIC_BASE_URL", "value": f"http://devplat-model-gateway.devplat-system.svc:8080/p/{dns_label(pid)}"},
                    {"name": "ANTHROPIC_AUTH_TOKEN", "valueFrom": {"secretKeyRef": {"name": f"{name}-io", "key": "gateway_token"}}}]
                   + ([{"name": "NPM_CONFIG_REGISTRY", "value": "http://devplat-registry-proxy.devplat-system.svc:4873/"}]
                      if net == "deps" else [])
                   + [{"name": "DISABLE_AUTOUPDATER", "value": "1"},
                      {"name": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "value": "1"}],
            "resources": {"requests": dict(res["requests"]), "limits": dict(res["limits"])},
            "securityContext": _hardened(),
            "volumeMounts": [{"name": "workspace", "mountPath": "/workspace"},
                             {"name": "home", "mountPath": "/home/agent"},
                             {"name": "role", "mountPath": "/home/agent/.claude/agents", "readOnly": True},
                             {"name": "role-settings", "mountPath": "/etc/claude-code", "readOnly": True},
                             {"name": "contract", "mountPath": "/etc/devplat/contract", "readOnly": True},
                             {"name": "io", "mountPath": "/etc/devplat/io", "readOnly": True},
                             {"name": "out", "mountPath": "/out"},
                             {"name": "tmp", "mountPath": "/tmp"}],
        }],
        "volumes": [
            {"name": "workspace", "emptyDir": {"sizeLimit": profile["workspace_size"]}},
            {"name": "home", "emptyDir": {"sizeLimit": "512Mi"}},
            {"name": "out", "emptyDir": {"sizeLimit": "256Mi"}},
            {"name": "tmp", "emptyDir": {"sizeLimit": "1Gi"}},
            {"name": "role", "configMap": {"name": run["role_configmap"], "items": [{"key": defn, "path": defn}]}},
            {"name": "role-settings", "configMap": {"name": run["role_configmap"],
                                                    "items": [{"key": f"managed-settings.{role}.json", "path": "managed-settings.json"}]}},
            {"name": "contract", "configMap": {"name": f"{name}-contract"}},
            {"name": "io", "secret": {"secretName": f"{name}-io", "defaultMode": 0o400}},
        ],
    }
    if pod["runtimeClassName"] == "default":   # reduced-assurance workstation mode (ADR-023): no sandbox runtime
        del pod["runtimeClassName"]
    return {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": name, "namespace": ns, "labels": labels, "annotations": annotations},
        "spec": {
            "suspend": True,                 # unsuspended only after the owned ConfigMap and Secret exist (16-… §2 step 7)
            "backoffLimit": 0,               # no Kubernetes retries: attempts and budgets belong to the controller
            "completions": 1, "parallelism": 1,
            "activeDeadlineSeconds": wall_min * 60 + defaults["setup_grace_seconds"],
            "ttlSecondsAfterFinished": defaults["ttl_seconds_after_finished"],
            "podReplacementPolicy": "Failed",
            "podFailurePolicy": {"rules": [
                {"action": "FailJob", "onPodConditions": [{"type": "DisruptionTarget", "status": "True"}]},
                {"action": "FailJob", "onExitCodes": {"containerName": "fetch", "operator": "NotIn", "values": [0]}},
                {"action": "FailJob", "onExitCodes": {"containerName": "agent", "operator": "In", "values": [64, 65, 75]}},
            ]},
            "template": {"metadata": {"labels": {**sel, f"{L}/network-class": net, f"{L}/workload": "agent"}},
                         "spec": pod},
        },
    }
