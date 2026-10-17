#!/usr/bin/env python3
"""Build the Kubernetes Job for one agent run (devplat controller, pure function — no cluster access).

Inputs are the three versioned documents the controller already holds:
  contract  devorch.task_contract.v1  (docs/mercury/development-orchestration/schemas/task-contract.schema.json)
  project   devplat.project.v1        (platform/schemas/project-config.schema.json)
  profile   one entry of platform/agents/execution-profiles.yaml
plus run facts chosen by the controller (attempt, one-time URLs, image digest).

The function encodes the security rules of 16-agent-execution-and-job-lifecycle.md and
18-kubernetes-security-model.md so that they are testable without a cluster:
no service-account token, non-root, read-only root filesystem, no capabilities, seccomp RuntimeDefault,
no host namespaces or hostPath, exec node pool + RuntimeClass, controller-owned retries (backoffLimit 0),
deadline and TTL, deterministic idempotent name. `test_jobspec.py` validates the output against the strict
Kubernetes v1.33 Job schema and checks every rule.
"""
import hashlib, re

LABEL = "devplat.io"
NAME_MAX = 63


def dns_label(s):
    s = re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")
    return s


def job_name(project_id, task_id, attempt):
    """Deterministic and idempotent: the same (project, task, attempt) always yields the same name, so a
    controller retry after a crash gets AlreadyExists and adopts the Job instead of starting a second run."""
    base = f"dp-{dns_label(project_id)}-{dns_label(task_id)}-a{attempt}"
    if len(base) <= NAME_MAX:
        return base
    h = hashlib.sha256(base.encode()).hexdigest()[:10]
    return f"{base[:NAME_MAX - 11].rstrip('-')}-{h}"


def idempotency_key(project_id, contract_core_sha256, attempt):
    return hashlib.sha256(f"{project_id}|{contract_core_sha256}|{attempt}".encode()).hexdigest()


def build_job(contract, project, profile, run):
    """run = {attempt, contract_core_sha256, agent_image (digest-pinned), fetch_url_secret, upload_url_secret,
              contract_configmap, role_configmap}"""
    pid = project["project_id"]
    ns = project["execution_target"]["namespace_prefix"] + "-exec"
    name = job_name(pid, contract["task_id"], run["attempt"])
    labels = {
        f"{LABEL}/project": dns_label(pid),
        f"{LABEL}/task": dns_label(contract["task_id"]),
        f"{LABEL}/attempt": str(run["attempt"]),
        f"{LABEL}/role": dns_label(profile["role"]),
        f"{LABEL}/managed-by": "devplat-controller",
    }
    annotations = {
        f"{LABEL}/idempotency-key": idempotency_key(pid, run["contract_core_sha256"], run["attempt"]),
        f"{LABEL}/contract-core-sha256": run["contract_core_sha256"],
        f"{LABEL}/base-commit": contract["base_commit"],
    }
    if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", run["agent_image"]):
        raise ValueError("agent image must be pinned by digest")
    res = profile["resources"]
    secctx = {
        "runAsNonRoot": True, "runAsUser": 65532, "runAsGroup": 65532,
        "allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "privileged": False,
        "capabilities": {"drop": ["ALL"]}, "seccompProfile": {"type": "RuntimeDefault"},
    }
    ws_mounts = [{"name": "workspace", "mountPath": "/workspace"}, {"name": "tmp", "mountPath": "/tmp"}]
    pod_spec = {
        "serviceAccountName": f"{dns_label(pid)}-agent",
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        "restartPolicy": "Never",
        "hostNetwork": False, "hostPID": False, "hostIPC": False,
        "securityContext": {"runAsNonRoot": True, "fsGroup": 65532, "seccompProfile": {"type": "RuntimeDefault"}},
        "nodeSelector": {f"{LABEL}/pool": "exec"},
        "tolerations": [{"key": f"{LABEL}/exec", "operator": "Equal", "value": "true", "effect": "NoSchedule"}],
        "initContainers": [{
            "name": "fetch",
            "image": run["agent_image"],
            "command": ["/devplat/bin/fetch-workspace"],
            "args": ["--base-commit", contract["base_commit"], "--branch", contract["branch"], "--dest", "/workspace/src"],
            "env": [{"name": "DEVPLAT_FETCH_URL", "valueFrom": {"secretKeyRef": {"name": run["fetch_url_secret"], "key": "url"}}}],
            "securityContext": secctx,
            "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "500m", "memory": "512Mi"}},
            "volumeMounts": ws_mounts,
        }],
        "containers": [{
            "name": "agent",
            "image": run["agent_image"],
            "command": ["/devplat/bin/run-agent"],
            "args": ["--contract", "/devplat/contract/contract.json", "--role", f"/devplat/role/{profile['agent_definition']}",
                     "--workspace", "/workspace/src", "--out", "/workspace/out"],
            "env": [
                {"name": "DEVPLAT_UPLOAD_URLS", "valueFrom": {"secretKeyRef": {"name": run["upload_url_secret"], "key": "urls"}}},
                {"name": "ANTHROPIC_BASE_URL", "value": "http://devplat-model-gateway.devplat-system.svc:8080"},
                {"name": "HOME", "value": "/tmp"},
            ],
            "securityContext": secctx,
            "resources": {"requests": dict(res["requests"]), "limits": dict(res["limits"])},
            "volumeMounts": ws_mounts + [
                {"name": "contract", "mountPath": "/devplat/contract", "readOnly": True},
                {"name": "role", "mountPath": "/devplat/role", "readOnly": True},
            ],
        }],
        "volumes": [
            {"name": "workspace", "emptyDir": {"sizeLimit": profile["workspace_size"]}},
            {"name": "tmp", "emptyDir": {"sizeLimit": "1Gi"}},
            {"name": "contract", "configMap": {"name": run["contract_configmap"]}},
            {"name": "role", "configMap": {"name": run["role_configmap"]}},
        ],
    }
    if profile.get("runtime_class") and profile["runtime_class"] != "default":
        pod_spec["runtimeClassName"] = profile["runtime_class"]
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": ns, "labels": labels, "annotations": annotations},
        "spec": {
            "backoffLimit": 0,                       # retries are decided by the controller (budgets), never by Kubernetes
            "activeDeadlineSeconds": int(profile["max_wall_minutes"]) * 60,
            "ttlSecondsAfterFinished": 3600,         # evidence is uploaded before exit; the Job object is disposable
            "podFailurePolicy": {"rules": [
                {"action": "FailJob", "onExitCodes": {"containerName": "agent", "operator": "In", "values": [2]}},
                {"action": "Ignore", "onPodConditions": [{"type": "DisruptionTarget", "status": "True"}]},
            ]},
            "template": {"metadata": {"labels": labels, "annotations": annotations}, "spec": pod_spec},
        },
    }
