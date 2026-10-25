import yaml, sys
docs = []
# Values sized for the Option B exec pool baseline; workstation overlay scales down (doc 18 §12). Jupiter values
# are placeholders equal to the generic onboarding defaults (no Jupiter requirements known).
SIZES = {
  "exec":  {"requests.cpu": "8", "limits.cpu": "16", "requests.memory": "16Gi", "limits.memory": "32Gi",
            "requests.ephemeral-storage": "60Gi", "limits.ephemeral-storage": "120Gi", "pods": "8",
            "count/jobs.batch": "40", "persistentvolumeclaims": "8", "requests.storage": "160Gi",
            "configmaps": "100", "secrets": "100", "services": "0", "services.loadbalancers": "0", "services.nodeports": "0"},
  "build": {"requests.cpu": "8", "limits.cpu": "16", "requests.memory": "16Gi", "limits.memory": "32Gi",
            "requests.ephemeral-storage": "100Gi", "limits.ephemeral-storage": "200Gi", "pods": "4",
            "count/jobs.batch": "20", "persistentvolumeclaims": "4", "requests.storage": "200Gi",
            "configmaps": "50", "secrets": "50", "services": "0", "services.loadbalancers": "0", "services.nodeports": "0"},
}
LIMITS = {
  "exec":  {"max": {"cpu": "4", "memory": "8Gi", "ephemeral-storage": "20Gi"},
            "min": {"cpu": "50m", "memory": "64Mi"},
            "default": {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "10Gi"},
            "defaultRequest": {"cpu": "500m", "memory": "1Gi", "ephemeral-storage": "2Gi"}, "pvc": "20Gi"},
  "build": {"max": {"cpu": "4", "memory": "8Gi", "ephemeral-storage": "50Gi"},
            "min": {"cpu": "50m", "memory": "64Mi"},
            "default": {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "20Gi"},
            "defaultRequest": {"cpu": "1", "memory": "2Gi", "ephemeral-storage": "5Gi"}, "pvc": "50Gi"},
}
for p in ["mercury", "jupiter"]:
    for tier in ["exec", "build"]:
        n = f"proj-{p}-{tier}"
        ann = {"devplat.io/sizing": "baseline; controller admission (global/project/role caps) is the primary limiter, quota is the backstop"}
        if p == "jupiter": ann["devplat.io/placeholder"] = "generic onboarding defaults; Jupiter requirements unresolved"
        docs.append({"apiVersion": "v1", "kind": "ResourceQuota",
                     "metadata": {"name": "devplat-compute", "namespace": n, "annotations": ann},
                     "spec": {"hard": SIZES[tier]}})
        docs.append({"apiVersion": "v1", "kind": "ResourceQuota",
                     "metadata": {"name": "devplat-no-platform-priority", "namespace": n,
                                  "annotations": {"devplat.io/purpose": "project workloads may not use the platform PriorityClass (pods hard 0 in that scope)"}},
                     "spec": {"hard": {"pods": "0"},
                              "scopeSelector": {"matchExpressions": [{"scopeName": "PriorityClass", "operator": "In",
                                                                      "values": ["devplat-platform", "system-cluster-critical", "system-node-critical"]}]}}})
        L = LIMITS[tier]
        docs.append({"apiVersion": "v1", "kind": "LimitRange",
                     "metadata": {"name": "devplat-defaults", "namespace": n},
                     "spec": {"limits": [
                         {"type": "Container", "max": L["max"], "min": L["min"], "default": L["default"], "defaultRequest": L["defaultRequest"]},
                         {"type": "PersistentVolumeClaim", "max": {"storage": L["pvc"]}}]}})
hdr = """# devplat base: ResourceQuota + LimitRange per project namespace. Status: Documented only / not deployed.
# Backstop for the controller's admission (doc 18 §8, scheduling doc). Ephemeral test namespaces receive a
# quota/limit range from devplat-namespacer at creation (sized from the project config).
# services: "0" in exec/build: agents and builds never expose Services. Generic ephemeral volumes count as PVCs.
# RuntimeClass overhead (gVisor/Kata) is added to pod requests and therefore counts against these quotas.
"""
open(sys.argv[1], "w").write(hdr + "".join("---\n" + yaml.safe_dump(d, sort_keys=False) for d in docs))
print(len(docs))
