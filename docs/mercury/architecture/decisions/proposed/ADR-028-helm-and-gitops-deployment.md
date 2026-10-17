# ADR-028 — Helm packaging, GitOps option and bootstrap of the development platform

| | |
|---|---|
| Status | **Proposed** (requires operator approval; Architecture Amendment 001) |
| Date | 2026-10-17 |
| Owner | Lead Architect (devplat, development platform) |
| Related | ADR-021, ADR-023 (topology), ADR-026 (persistence); `development-orchestration/24-helm-and-gitops.md`, `25-deployment-profiles.md`; charts in `platform/deploy/charts/` |
| Scope | **Development platform (devplat) only.** MERCURY's production deployment (operator-installed macOS service, `operations/macos-service.md`) is unchanged |

## Context

The platform must be declarative, installable on profiles from a workstation to managed cloud, and bootstrapped without Mercury or Jupiter. Only the operator may change the platform, rulesets or credentials. Cluster-scoped dependencies (CloudNativePG operator, RuntimeClass, CNI) differ per profile. The MinIO community edition, a common in-cluster S3 choice, went source-only in late 2025, and its repository was archived on 2026-04-25.

## Decision

1. **Two Helm charts (apiVersion v2, Kubernetes ≥ 1.30):**
   - `devplat`: control plane in `devplat-system` (controller ×2 with Lease, api with OIDC, gitbroker, model-gateway, optional CloudNativePG `Cluster`, NetworkPolicies, controller-scope admission policy);
   - `devplat-project`: one release per project per execution target. Namespaces, quotas, default-deny NetworkPolicies, zero-RBAC ServiceAccounts, per-project admission policies and the test-namespace profile. Its values are generated from the project configuration.
2. **Strict values contract.**
   - `values.schema.json` rejects unknown keys.
   - Images by digest only; rendering fails while no image exists.
   - Safety properties are constants: gitbroker `pushRefPrefix: dev/`, `draftPullRequestsOnly: true`, single replica. There is no merge/approve setting.
   - NetworkPolicy off renders only in `reduced` assurance mode. Ingress is refused without OIDC.
3. **No subchart dependencies.** CloudNativePG, the object store, the ingress controller and gVisor are cluster prerequisites, installed and upgraded separately by the operator.
4. **Separation of duties.**
   - The operator installs and configures: cluster-scoped objects, secrets, App, ruleset, OIDC.
   - The controller only operates: Jobs and test namespaces, constrained by RBAC and the `devplat-controller-scope` policy. It cannot change its own RBAC, policies or secrets.
   - `platform/**` is a restricted path for agent tasks.
5. **GitOps is optional.**
   - Workstation and single node: plain Helm by the operator.
   - Multi-node and cloud: Flux or Argo CD from a deployment repository protected by its own ruleset, with read-only Git credentials, pinned chart versions and digests, and no automatic image updates. The tool is chosen by the operator.
6. **Bootstrap steps 1–10** as in `24-…` §9: establish the cluster → … → recover from a simulated worker failure. Steps needing operator authorization are marked there. Dispatch of code tasks stays disabled until all ten pass and the v1 hard preconditions (DOD-02, DOD-03) are recorded as authenticated operator facts (OIDC, DOD-14; the bot App is DOD-13). Cluster creation needs DOD-15.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| One umbrella chart including CloudNativePG and MinIO subcharts | Couples cluster-scoped operator/CRD lifecycles to the app; `helm uninstall` becomes destructive; MinIO community is archived |
| Kustomize only | Fine for `platform/deploy/base`, but weaker for generated per-project bundles and parameter validation (no values schema) |
| A Kubernetes operator (CRDs) for devplat itself | More code and cluster-scoped privilege before the platform exists. May replace `devplat-project` later |
| Mandatory GitOps | Adds a cluster-wide privileged controller on 16 GB workstations; not needed for a single operator |

## Consequences

- **Positive:**
  - one install path for all profiles;
  - misconfiguration that would weaken a control fails at render time;
  - moving a project to its own cluster (Option C) = installing `devplat-project` there.
- **Negative:**
  - prerequisites are manual operator steps;
  - CloudNativePG backups are not templated yet (the chart refuses `backup.enabled`);
  - CEL policies are not validated until a cluster exists.
- **Status:** charts Implemented (untested). Rendered with helm v3.17.3 (built from source) and strict-validated with kubeconform against Kubernetes 1.33 schemas: devplat 28/28, devplat-project 17/17; negative cases fail as designed. Never installed. Images Blocked (none exist).

## Verification required before acceptance

1. Install both charts in a kind cluster with an enforcing CNI in devplat CI (`23-…` §5).
2. Isolation probes N1–N12 green.
3. Upgrade N-1 → N and rollback rehearsed.
4. Bootstrap steps 1–10 executed once on the first target profile, with the operator's authorizations recorded.
