# ADR-028 — Helm packaging, GitOps option and bootstrap of the development platform

| | |
|---|---|
| Status | **Proposed** (requires operator approval; Architecture Amendment 001; revised in the R6 fix round, 2026-10-22: D2, D9, D10, D12, D14–D16, D19, D20, D24, S-22, S-23, S-24) |
| Date | 2026-10-17 |
| Owner | Lead Architect (devplat, development platform) |
| Related | ADR-021, ADR-023 (topology), ADR-026 (persistence); `development-orchestration/24-helm-and-gitops.md`, `25-deployment-profiles.md`; charts in `platform/deploy/charts/` |
| Scope | **Development platform (devplat) only.** MERCURY's production deployment (operator-installed macOS service, `operations/macos-service.md`) is unchanged |

## Context

The platform must be declarative, installable on profiles from a workstation to managed cloud, and bootstrapped without Mercury or Jupiter. Only the operator may change the platform, rulesets or credentials. Cluster-scoped dependencies (CloudNativePG operator, RuntimeClass, CNI) differ per profile. The MinIO community edition, a common in-cluster S3 choice, went source-only in late 2025, and its repository was archived on 2026-04-25.

## Decision

1. **Two Helm charts (apiVersion v2, Kubernetes ≥ 1.30), on top of the canonical `platform/deploy/base`:**
   - **Base cluster prerequisites** (operator, always from base): ClusterRoles `devplat-job-runner`, `devplat-test-runner`, `devplat-namespacer`, `devplat-dns`; all ValidatingAdmissionPolicies and their params; RuntimeClasses; PriorityClasses; platform namespaces and their NetworkPolicies. The charts never render these.
   - `devplat`: control plane in `devplat-system` (render refused elsewhere):
     - controller ×2 with Lease; it never migrates;
     - a Helm **migrator hook Job** running as `devplat-migrator` with login `devplat_migrator` (D9); the schema owner role is NOLOGIN;
     - api with OIDC, plus an operator-identity allowlist that cannot be empty (D2);
     - gitbroker (the only GitHub App key holder; ingress from the controller only; the caller is authenticated with a projected, audience-bound token, S-23);
     - keyless gitbroker-fetch :8081;
     - **artifact-gateway** :8082 / admin :9444, the only artifact path for project pods (D10);
     - **namespacer** Deployment :8083 with a fixed template (D19);
     - model-gateway with a fixed request policy: endpoint allowlist, server-tool/MCP/container/Files/Batches rejection, project bound to the token (D12);
     - devplat-dns;
     - optional CloudNativePG `Cluster` `devplat-pg` with a digest-pinned operand image (S-22);
     - the controller's namespaced Roles.

     There is no cluster-wide controller grant and no impersonation. Images come only from `<registry>/devplat/` and `<registry>/mirror/` (D15). ServiceAccount annotations are per component; a shared workload identity fails the render (S-24).
   - `devplat-project`: one release per project per execution target. It renders the per-project namespace layer that base shows statically:
     - namespaces with PSA pinned to v1.33;
     - quotas with bounded per-run Secrets, and LimitRanges;
     - zero-RBAC ServiceAccounts `<P>-agent`/`<P>-build`;
     - the controller's RoleBindings;
     - NetworkPolicies: artifact-gateway only, no object store; model-gateway only for classes model-only/deps;
     - per-namespace image params (D15) and build switches (`buildsEnabled: "false"` by default, D20);
     - the project's read-only registry proxy (D14);
     - the namespacer test profile (doc 18 §9.3);
     - project settings (D16);
     - project-specific admission only: builder allowlist, optional RuntimeClass pin.

     Its values are generated from the project configuration; the project id must be ≤ 24 characters (D24).
   - `platform/tools/charts/run.sh` compares the shared objects with base field by field. Intended differences are listed with reasons, and any other difference fails.
2. **Strict values contract.**
   - `values.schema.json` rejects unknown keys.
   - Images by digest only; rendering fails while no image exists.
   - Secret names are fixed to doc 18 §8.1, so base Secret pinning applies; no name can be overridden.
   - Safety properties are constants: gitbroker `pushRefPrefix: dev/`, `draftPullRequestsOnly: true`, single replica. There is no merge/approve setting. This constrains gitbroker only: the App's permissions could merge and approve, and the repository ruleset is the preventive control (D13).
   - Ingress is refused without OIDC.
3. **No subchart dependencies.** CloudNativePG, the object store, the ingress controller and gVisor are cluster prerequisites, installed and upgraded separately by the operator.
4. **Separation of duties.**
   - The operator installs and configures: cluster-scoped objects, secrets, App, ruleset, OIDC.
   - The migrator hook alone changes the schema. The controller only operates Jobs and per-run objects; test namespaces come from the namespacer's fixed template. Both are constrained by per-namespace RBAC and base VAPs. Neither can change its own RBAC, policies or platform secrets.
   - `platform/**` is a restricted path for agent tasks.
5. **GitOps is optional.**
   - Workstation and single node: plain Helm by the operator.
   - Multi-node and cloud: Flux or Argo CD from a deployment repository protected by its own ruleset, with read-only Git credentials, pinned chart versions and digests, and no automatic image updates. The tool is chosen by the operator.
6. **Bootstrap steps 1–10** as in `24-…` §9: establish the cluster → … → recover from a simulated worker failure. Steps needing operator authorization are marked there. The step names are the amendment's own. Code tasks for a project are dispatched only after all ten steps pass, the project is `active`, and its **per-project** facts `DOD-02` (ruleset plus CI hardening, D13) and `DOD-13` are recorded by an allowlisted operator identity (D1, D2). Cluster creation needs DOD-15.

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
  - with in-cluster PostgreSQL the migrator runs post-install on the first install, because the `Cluster` belongs to the release; D9's pre-install hook works only with external PostgreSQL;
  - hook resources (migrator ServiceAccount, operator-identities ConfigMap) are not removed by `helm uninstall`;
  - CEL is compiled and evaluated offline only; admission is not exercised until a cluster exists;
  - base and charts overlap in the namespace layer, so each namespace is owned by exactly one install path (Helm or kubectl), never both.
- **Status:** charts **Implemented (untested)**. `platform/tools/charts/run.sh` (`24-…` §10) lints and renders them, validates the output strict against Kubernetes 1.33, runs 30 negative renders, checks the values schema, compares them with base (intended differences listed with reasons), checks Secret pinning and evaluates the chart's and base's CEL policies offline. Never installed. Images **Blocked** (none exist). The new components (migrator, artifact-gateway, namespacer, registry proxy) are templated but not built: **Designed, unverified**.

## Verification required before acceptance

1. Install both charts in a kind cluster with an enforcing CNI in devplat CI (`23-…` §5).
2. Isolation probes N1–N13 green, including N10 (merge, approve, auto-merge, push to `main` and a ruleset change refused by the ruleset) and N6b (no object-store access from project pods).
3. Upgrade N-1 → N and rollback rehearsed.
4. Bootstrap steps 1–10 executed once on the first target profile, with the operator's authorizations recorded.
