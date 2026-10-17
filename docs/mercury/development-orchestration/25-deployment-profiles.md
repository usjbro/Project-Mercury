# 25 — Deployment Profiles: Local Development and Multi-Node Strategy

Status: **Proposed** (Architecture Amendment 001, 2026-10-17). Documented only. No profile has been installed or measured. Every sizing figure is a **planning estimate**.
Reuses / supersedes: extends v1 `09-…` §1 (where work runs) and §2 (concurrency limits). The v1 statement "MacBook Air M2 with 16 GB RAM" is kept as a **planning constraint, not a measurement**. Topology options A/B/C and the execution-target abstraction are defined in `15-…`. This document maps them to concrete environments.

## 1. Assurance modes

The chart value `platform.assuranceMode` is `standard` or `reduced`. It is recorded in every evidence item, so a gate can require `standard`.

| Mode | Required controls (all verified by the isolation probes, `22-…` §7) | Allowed work |
|---|---|---|
| **standard** | Enforced NetworkPolicy (default deny); PSA `restricted` for agent and test namespaces; admission policies active; agent pods under a sandboxing RuntimeClass (gVisor, or Kata where gVisor is unavailable); no agent credentials (gitbroker / model-gateway pattern); platform DB unreachable from agent pods | All task kinds, within v1 hard preconditions (DOD-02/03) |
| **reduced** | Anything less. Typically: no sandboxing RuntimeClass, or a CNI that does not enforce NetworkPolicy, or control-plane services and agent pods on one node and kernel without gVisor | Design, planning, fake-agent and platform development. **Code tasks on a real repository need an operator decision** (open question O-1), because agent code then shares the host kernel with gitbroker's GitHub App key |

Topology adds a dimension. **Option A** (one node or one pool) can reach `standard` only with gVisor/Kata, and even then the controls share a kernel boundary with the sandbox. **Option B** (separate tainted `exec` pool) is the target. **Option C** (separate cluster per project) is a configuration change of the execution target.

## 2. Profiles overview

| Profile | Typical stack | Topology | gVisor / sandbox | NetworkPolicy | Max achievable mode |
|---|---|---|---|---|---|
| P1 macOS workstation | Docker Desktop, Rancher Desktop, OrbStack or colima (Linux VM) + kind / k3d / minikube | A | Not available by default in the VM. Possible in principle via a custom node image or the minikube gVisor addon; **unverified** on macOS VMs (incl. arm64) | kind: kindnet now implements NetworkPolicy via kube-network-policies [S1] (version-dependent: install Calico/Cilium for certainty); k3d/k3s: embedded policy controller; minikube: `--cni=calico` | **reduced** (standard only if a sandbox runtime is proven by probe) |
| P2 Windows workstation | Docker Desktop (WSL2 backend) or Rancher Desktop + kind / k3d inside WSL2 | A | Same as P1; not verified | Same as P1 | **reduced** |
| P3 Linux workstation | k3s, kind, k3d or minikube on the host kernel | A (or 2 kind nodes, one tainted) | **Installable**: `runsc` + containerd shim on the host (k3s) or in kind node images; minikube gVisor addon [S2] | k3s built-in; kind/minikube with Calico/Cilium | **standard** (Option A) after the probes pass |
| P4 Single-node server | k3s (or kubeadm) on a Linux server or VM | A | Installable on the host | k3s built-in or Calico/Cilium | **standard** (Option A) |
| P5 Self-managed multi-node | k3s HA (embedded etcd), kubeadm, or Talos Linux | **B**: `control` pool + tainted `exec` pool (+ optional `build` pool) | Installable per node (Talos: via a system extension; verify) | Calico or Cilium (Cilium adds FQDN egress policies) | **standard** (Option B) |
| P6 Managed cloud | GKE, EKS, AKS | **B** (node pools); C by adding clusters | GKE: **GKE Sandbox** (gVisor) node pools; Container-Optimized OS only; privileged containers not supported in gVisor [S3]. EKS: no gVisor in default AMIs; custom launch template or AMI installing `runsc` [S4]. AKS: Kata-based **Pod Sandboxing** instead of gVisor [S4] | Provider CNI policy (GKE Dataplane V2 / Calico; EKS VPC CNI network policies or Calico; AKS Azure NPM / Cilium) | **standard** (Option B/C) |

## 3. Supported and unsupported controls per profile

| Control | P1 macOS | P2 Windows | P3 Linux ws | P4 single node | P5 multi-node | P6 cloud |
|---|---|---|---|---|---|---|
| PSA restricted, VAP (K8s ≥ 1.30) | ✓ (kind/k3d/minikube current versions) | ✓ | ✓ | ✓ | ✓ | ✓ (check provider minor) |
| Enforced NetworkPolicy | ✓ with a capable CNI, **proved by probe N12** | ✓ same | ✓ | ✓ | ✓ | ✓ |
| FQDN egress policy | Only with Cilium | Only with Cilium | Cilium | Cilium | Cilium | Provider-specific (e.g. GKE FQDN network policy, Cilium-based offerings); otherwise app-level allowlists only |
| gVisor RuntimeClass `gvisor` | ✗ (unverified) | ✗ (unverified) | ✓ installable | ✓ | ✓ | GKE ✓; EKS custom; AKS ✗ (Kata instead) |
| Separate `exec` node pool | ✗ (single VM; k3d/kind multi-node shares the VM kernel) | ✗ | Partial (same kernel) | ✗ | ✓ | ✓ |
| Kubernetes user namespaces (`hostUsers: false`) | Depends on VM kernel ≥ 6.3 and containerd ≥ 2.0 [S5] | Same | Host-dependent | Host-dependent | Node-OS-dependent | Provider-dependent |
| Rootless BuildKit (`22-…` §9) | Possible (VM kernel); not needed for Mercury | Same | ✓ | ✓ | ✓ dedicated `build` pool | ✓ (GKE Sandbox: not inside gVisor) |
| Workload identity for cloud APIs | n/a | n/a | n/a | n/a | n/a | GKE Workload Identity Federation, EKS Pod Identity / IRSA, AKS Workload Identity: annotations through `serviceAccount.annotations` (devplat chart) for **platform components only**, never agent ServiceAccounts |
| Mercury T4 (macOS lane) | **The operator's Mac is the lane** (outside the cluster) | n/a | n/a | n/a | n/a | n/a |

Rule: a control counts only if the probe for it passes on that installation. Profile tables state what is **possible**, not what is in place.

## 4. Resource sizing (planning estimates, not measurements)

| Component | Requests (est.) | Notes |
|---|---|---|
| Kubernetes system (kind/k3s, CNI, DNS) | 0.5–1 CPU, 1–1.5 GiB | Depends on the distribution |
| devplat-controller ×2, api, gitbroker, model-gateway ×2 | 0.6 CPU, ≈ 0.8 GiB (chart defaults: 100m / 128Mi each) | Limits up to 1 CPU / 512Mi each |
| PostgreSQL (CNPG, 1 instance) | 0.25–0.5 CPU, 0.5–1 GiB, 10 GiB disk | 3 instances in P5/P6 |
| CNPG operator, S3-compatible store | 0.2 CPU, 0.5 GiB | In-cluster store optional |
| **One agent Job** (Claude Code headless, workspace emptyDir) | 1 CPU, 2 GiB request; 2 CPU, 4 GiB limit (`devplat-project` LimitRange defaults) | **Unmeasured**; refit after 10 Jobs (as in v1 `09-…` §4) |
| One test namespace (Mercury T0–T2 shard) | 1–4 CPU, 2–8 GiB | Per suite configuration |
| gVisor overhead | Extra memory per sandbox and syscall overhead | Unmeasured; measure in the P3/P5 spike |

| Profile | Suggested capacity | Initial concurrency (controller admission) |
|---|---|---|
| P1/P2 workstation (16 GB host) | VM 6–8 GiB, 4 vCPU | 1–2 agent Jobs + 1 test namespace |
| P3 Linux workstation (32 GB) | Host | 3 agent Jobs + 2 test namespaces |
| P4 single server (8–16 vCPU, 32–64 GB) | Host | 3–6 agent Jobs + 2 test namespaces |
| P5 multi-node | `control` 2 × (2 vCPU, 8 GB); `exec` N × (8 vCPU, 32 GB) | 3 per project (v1 model: no gain beyond 3 for Mercury), global by capacity |
| P6 cloud | As P5; autoscaled `exec` pool with a max node count = cost cap | Same, plus daily cost budget through model-gateway |

## 5. Planning example: MacBook Air M2, 16 GB (planning example only)

This is **not** a recommendation to run the platform on that machine and **not** a measurement.

| Item | Plan |
|---|---|
| Stack | OrbStack, Rancher Desktop or colima VM: 4 vCPU, 7 GiB. **k3d** single server (built-in NetworkPolicy controller) or kind with Calico. Images native **arm64** |
| Budget | ≈ 1.5 GiB Kubernetes, ≈ 2 GiB platform + PostgreSQL, ≈ 3.5 GiB for **1–2 agent Jobs**, no in-cluster builds |
| Mode | **reduced** (no gVisor in the VM unless proven). Planning, design and fake-agent work; code tasks per O-1 |
| Conflict | The same Mac is Mercury's **T4 macOS lane**. T4 runs (launchd, Keychain, Seatbelt, sleep and wake) must not share the machine with a busy cluster. Stop the cluster VM during Mac-lane sessions; v1 `09-…` §3 memory-pressure thresholds apply |
| Better fit | Run the cluster elsewhere (P4/P5/P6, or a cloud session for planning only) and keep the Mac for the macOS lane. This matches v1 DOD-04's recommendation |

## 6. Managed cloud specifics

| Topic | GKE | EKS | AKS |
|---|---|---|---|
| Node pools | `control` (standard COS) + `exec` (GKE Sandbox, taint `devplat.io/exec=true:NoSchedule`) | Managed node groups: `control` + `exec` (custom launch template with `runsc`, taint) | System and user node pools; `exec` with Pod Sandboxing |
| Sandbox | gVisor via `runtimeClassName: gvisor`. Autopilot runs sandboxed Pods when requested [S3] | gVisor self-installed (unsupported by AWS); Kata alternative | Kata-based Pod Sandboxing; set `exec.requiredRuntimeClassName` to the AKS runtime class |
| Workload identity | Workload Identity Federation: only `devplat-controller` (bucket, backups) and `devplat-api` (secret store) bind cloud identities | EKS Pod Identity or IRSA, same scope | AKS Workload Identity, same scope |
| PostgreSQL | Cloud SQL (`postgres.mode=external`) or CNPG | RDS / Aurora PostgreSQL or CNPG | Azure Database for PostgreSQL or CNPG |
| Artifacts | GCS through the S3 interoperability API, or S3-compatible proxy | S3 | Blob storage through an S3-compatible gateway |
| Arm64 | Check whether GKE Sandbox supports Arm machine types (not confirmed) | Graviton node groups (gVisor arm64 builds exist; untested here) | Arm64 VMs; check Pod Sandboxing support |
| Cost control | Max node count on `exec`; model-gateway daily budget; idle scale-to-zero of `exec` | Same | Same |

## 7. Portability rules

1. **No OS-specific dependencies in the platform core.** Controller, api, gitbroker and model-gateway are Linux OCI images with no host paths, no host binaries and no Docker socket. Profiles differ only in Helm values and cluster prerequisites.
2. **OCI images only**, referenced by digest. Architectures: `linux/amd64` and `linux/arm64`, and **only where verified** on native nodes (`22-…` §9.4). An unverified architecture is not claimed.
3. **Kubernetes API floor:** 1.30 (ValidatingAdmissionPolicy GA). Validation target 1.33.
4. **No provider lock-in in templates.** Cloud identity, storage classes, ingress classes and runtime classes are values. A provider-specific feature (GKE Sandbox, Pod Identity) is only ever reached through a value.
5. **Same probes everywhere.** The isolation probes (`22-…` §7) are identical on every profile. The assurance mode comes from probe results, not from the profile name.
6. **Execution targets, not hostnames.** Projects reference `{cluster_ref, namespace_prefix}` (`15-…`). Moving a project to its own cluster (Option C) means installing `devplat-project` there and changing `cluster_ref`.
7. **macOS is never a cluster node.** Mac-only validation is an external execution target (`external_manual`), whatever the profile.
8. **Local mode remains.** v1 devorch (git ledger, one Claude Code session) stays available on any workstation without a cluster (`14-…` §3 rule 4).

## 8. Capability status

| Capability | Status |
|---|---|
| Profiles P1–P6 | **Documented only**; none installed |
| gVisor on macOS/Windows VMs | **Unverified assumption** (treated as unavailable) |
| gVisor on Linux hosts / GKE Sandbox | **Documented only** (vendor documentation; not exercised) |
| NetworkPolicy enforcement per CNI | **Unverified** until probe N12 runs on the installation |
| Sizing figures | **Unverified assumption** (estimates) |
| `assuranceMode` value and its template guard | **Implemented (untested)**: chart guard rendered offline (`24-…` §10) |

## 9. Open questions

1. **O-1:** Are code tasks on a real repository allowed in **reduced** mode (e.g. P1 without gVisor), or only in standard mode?
2. **O-2:** Target first profile: P4 single server (recommended for Phase 1) or P6 GKE (fastest route to gVisor and node pools)?
3. **O-3:** Is a second machine available, so that the M2 Mac stays dedicated to the macOS lane?

## Sources (accessed 2026-10-17; untrusted web content, used as data)

- [S1] kindnet network policies: <https://kindnet.sigs.k8s.io/docs/user/network-policies/>
- [S2] gVisor Kubernetes quick start (GKE Sandbox, minikube addon, containerd shim): <https://github.com/google/gvisor/blob/master/g3doc/user_guide/quick_start/kubernetes.md>
- [S3] GKE Sandbox concepts (COS only; privileged not supported under gVisor; Autopilot behaviour): <https://cloud.google.com/kubernetes-engine/docs/concepts/sandbox-pods> (via search results)
- [S4] gVisor on EKS (custom node setup): <https://devopscube.com/set-up-gvisor-on-aws-eks/> (third-party); AKS Pod Sandboxing / confidential containers overview: <https://docs.azure.cn/es-es/aks/confidential-containers-overview>
- [S5] Kubernetes user namespaces: <https://kubernetes.io/docs/concepts/workloads/pods/user-namespaces/>
