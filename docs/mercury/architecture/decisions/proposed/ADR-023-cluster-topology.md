# ADR-023 — devplat cluster topology: one cluster with dedicated node pools

| | |
|---|---|
| Status | **Proposed** (Architecture Amendment 001; requires operator approval) |
| Date | 2026-10-17 |
| Owner | Lead Architect (development platform) |
| Related ADRs | ADR-022 (platform), ADR-024 (Job execution), ADR-025 (security, proposed separately). Mercury ADR-001…020: none affected |

## Context

devplat runs three logical environments: the platform (Env-A), Mercury execution (Env-B) and Jupiter execution (Env-C, not yet specified). Agent Jobs run untrusted, LLM-directed code; platform pods hold the GitHub App key and the LLM API key. Installations range from a single MacBook Air M2 with 16 GB (planning example) to a home server, a multi-node cluster and cloud. Three topologies were evaluated (`15-platform-architecture.md` §7):

- **A** — one cluster, isolation by namespaces only;
- **B** — one cluster, a `control` node pool for platform services and a tainted `exec` pool for agent, build and test Jobs;
- **C** — separate clusters for the platform and for each project.

## Decision

1. **Option B is the proposed target topology** (a recommendation until DOD-11 is decided). Namespaces `devplat-system`, `devplat-artifacts`, `devplat-observability` on the `control` pool; per project `proj-<P>-exec`, `proj-<P>-build` and ephemeral `proj-<P>-t-<runid>` on the `exec` pool, tainted `devplat.io/exec=true:NoSchedule`. Untrusted code runs under the gVisor `RuntimeClass` `gvisor` where the node OS supports it (Kata as an alternative). If BuildKit cannot run under gVisor, builds use a separate tainted `build` pool without gVisor.
2. **Option A only for a single workstation, as an explicit reduced-assurance mode.** It is declared in platform config, recorded on every task event (`assurance: reduced`), shown on the dashboard and in every PR body; gVisor may be absent. Gates do not change; isolation claims do.
3. **Option C is reachable by configuration.** Every project addresses execution through an **execution target** `{cluster_ref, namespace_prefix}`. Moving a project to its own cluster changes the project config and installs the exec-side chart there; controller code does not change. Cross-cluster access to model-gateway and the artifact store then needs authenticated (mTLS) ingress.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Option A everywhere | A sandbox escape can land on a node that holds the gitbroker or model-gateway key |
| Option C from the start | Highest cost and operational burden (N control planes, upgrades, cross-cluster credentials) for a single-operator platform; no workstation fit |
| Per-project node pools inside Option B by default | Idle capacity per project; available later per project through the execution target or a node-selector in project config |

## Consequences

- **Positive:** no agent pod shares a node with platform secrets; capacity scales by growing the exec pool; topology changes are config changes.
- **Negative:** two pools to operate; gVisor support depends on the node OS and must be verified (unverified on an arm64 workstation VM); on a single host running two VMs the hypervisor is the shared boundary.
- **Residual risk:** exec-node kubelet credentials and the CNI's NetworkPolicy enforcement are the remaining isolation dependencies (`18-…`).

## Status of the decision's elements

All elements are **Documented only**; gVisor and BuildKit-under-gVisor feasibility are **unverified assumptions**. No cluster has been created.

## Related requirements

Amendment 001 topology and isolation requirements (`14-…` §2 rows 2–3). Production MERCURY requirements are unaffected.
