# 24 — Helm Deployment, GitOps and Cluster Bootstrap

Status: **Proposed** (Architecture Amendment 001, 2026-10-17).
- The charts in `platform/deploy/charts/` are **Implemented (untested)**: rendered with `helm template` and strict-validated offline, never installed on a cluster.
- No devplat image exists. Every `image.digest` is empty, and the charts refuse to render until real digests are supplied.

Reuses / supersedes: v1 `13-…` RB-D1 (host bootstrap with a git ledger) stays as the **local mode** bootstrap. This document adds the cluster bootstrap. The v1 operator-only steps (DOD-02 ruleset, DOD-03 development identity, operator facts) are kept and move into §9 steps 4 and 8.

## 1. Chart layout and the boundary with `platform/deploy/base`

`platform/deploy/base/` (owned by `18-…`) is canonical for the security model. It has two layers:

| Layer | Content | Installed by |
|---|---|---|
| **Cluster prerequisites** | ClusterRoles `devplat-job-runner`, `devplat-test-runner`, `devplat-namespacer` (+ ClusterRoleBinding), `devplat-dns` (+ ClusterRoleBinding); all ValidatingAdmissionPolicies and the `devplat-admission-params` ConfigMap; RuntimeClasses; PriorityClasses; the namespaces `devplat-system`, `devplat-artifacts` and `devplat-observability` with their `default` ServiceAccounts; and every NetworkPolicy of those platform namespaces | **Operator, always from base** (bootstrap step 2), before any chart |
| **Namespace layer** | Platform ServiceAccounts and the controller's Roles in `devplat-system`/`devplat-artifacts`; per project: namespaces, quotas, LimitRanges, ServiceAccounts, the controller's RoleBindings to `devplat-job-runner`, NetworkPolicies | **Either** the charts (parameterized) **or** `kubectl apply` of base's static rendering for `proj-mercury-*` / `proj-jupiter-*`. Never both for the same namespace: Helm refuses to adopt objects it does not own |

The charts render the namespace layer, plus the Deployments that base does not contain. Rendered for project id `mercury`, `devplat-project` produces objects whose specs are **identical** to base's for every shared object (namespaces, quotas, LimitRanges, NetworkPolicies, RoleBindings, ServiceAccounts). This was checked by a field-by-field comparison on 2026-10-17 (§10).

```text
platform/deploy/charts/
├── devplat/                      # control plane: one release per cluster, namespace devplat-system (enforced)
│   ├── Chart.yaml                # apiVersion v2, kubeVersion >=1.30 (ValidatingAdmissionPolicy GA)
│   ├── values.yaml               # defaults = standard-assurance profile; no Secret names (fixed, doc 18 §8.1)
│   ├── values.schema.json        # draft-07, additionalProperties:false everywhere
│   └── templates/
│       ├── _helpers.tpl          # labels, digest-only image helper (fails on empty), security contexts,
│       │                         # fixed-name DB/S3 env, guards
│       ├── _workload.tpl         # shared Deployment + Service (+ PDB); priorityClassName devplat-platform
│       ├── serviceaccounts.yaml  # controller, api, gitbroker, gitbroker-fetch, model-gateway, dns, namespacer;
│       │                         # all automount false (controller and dns opt in at pod level)
│       ├── controller-rbac.yaml  # Roles in devplat-system: leader election (one Lease), impersonate
│       │                         # devplat-namespacer, service lookup; plus service lookup in devplat-artifacts.
│       │                         # NO ClusterRole or ClusterRoleBinding for the controller
│       ├── controller.yaml       # 2 replicas, Lease devplat-controller, admission limits, namespacer impersonation
│       ├── api.yaml              # OIDC operator auth (DOD-14)
│       ├── gitbroker.yaml        # GitHub App key (devplat-gitbroker-github-app); dev/* and draft PRs only;
│       │                         # ingress only from the controller
│       ├── gitbroker-fetch.yaml  # KEYLESS bundle server on :8081 for fetch init containers
│       ├── model-gateway.yaml    # :8080 for agents (classes model-only|deps), admin :9443; keys in
│       │                         # devplat-model-gateway-llm-keys
│       ├── dns.yaml              # devplat-dns: CoreDNS, kubernetes plugin only (no forward); pod 1053, Service 53
│       ├── postgres-cnpg.yaml    # CloudNativePG Cluster CR (postgres.mode=cnpg), managed roles from devplat-db-*
│       ├── ingress.yaml          # optional; refused without OIDC
│       └── NOTES.txt
└── devplat-project/              # per-project namespace layer: one release per project per execution target
    ├── Chart.yaml
    ├── values.yaml               # GENERATED from platform/projects/<id>.yaml (26-…); defaults = hypothetical example-a
    ├── values.schema.json
    └── templates/
        ├── namespaces.yaml       # proj-<P>-exec (PSA restricted), proj-<P>-build (PSA privileged + base VAPs);
        │                         # PSA versions pinned v1.33
        ├── quotas.yaml           # devplat-compute (per-run ConfigMaps/Secrets bounded, services 0),
        │                         # devplat-no-platform-priority, LimitRange devplat-defaults
        ├── serviceaccounts.yaml  # <P>-agent, <P>-build: zero RBAC, no token
        ├── controller-rolebindings.yaml  # controller -> ClusterRole devplat-job-runner, per namespace
        ├── networkpolicies.yaml  # default-deny-all; exec-base-egress (devplat-dns, gitbroker-fetch :8081,
        │                         # artifacts); model-egress (classes model-only|deps only); deps-egress;
        │                         # build-egress
        ├── admission-policies.yaml  # PROJECT-SPECIFIC only: builder allowlist; optional RuntimeClass pin
        ├── test-profile.yaml     # ConfigMap in devplat-system: profile the namespacer applies to proj-<P>-t-<8 hex>
        └── NOTES.txt
```

## 2. Values model

| Group | Key values | Rules enforced by schema or template |
|---|---|---|
| `platform` | `clusterRef` (`default`), `assuranceMode` (`standard` / `reduced`) | — |
| Release | — | `devplat` renders only in namespace `devplat-system` (template `fail`), because base RBAC, NetworkPolicies and Secret pinning are bound to it |
| Images | `<component>.image.repository`, `.digest` for controller, api, gitbroker, gitbrokerFetch, modelGateway, dns | Digest-only; empty digest ⇒ render fails with "no image has been published yet". The repository prefix must be listed in base's `devplat-admission-params.allowedImagePrefixes` |
| `controller` | replicas, Lease timings (the Lease name is fixed: `devplat-controller`), global and per-project admission limits, test-namespace TTL | Ranges bounded |
| `api.oidc` | issuer, client id, allowed subjects | Ingress refused without an issuer |
| `gitbroker` | `pushRefPrefix`, `draftPullRequestsOnly` | Exactly one replica (not configurable); `pushRefPrefix` const `dev/`; `draftPullRequestsOnly` const `true`; no merge/approve key; unknown keys (e.g. a Secret-name override) rejected |
| `gitbrokerFetch`, `dns` | replicas, image, resources | — |
| `modelGateway.providers[]` | name (`anthropic`, `openai`), host | At least one provider; key `<name>-api-key` in the fixed Secret |
| `postgres` | `mode` `cnpg` / `external`; instances, storage; external host, port, database, sslmode | `external` needs a host; `cnpg.backup.enabled` const false (not templated, §7) |
| `artifacts` | S3 endpoint, region, bucket prefix | — |
| Project chart | `project.id` (≤ 24 chars), prefix (= `proj-<id>`), `platformNamespace` (const `devplat-system`), quotas, LimitRanges, `exec.requiredRuntimeClassName` (`""` / `gvisor` / `kata`), builder allowlist (digests), test profile, `sandboxEgress` | Prefix mismatch fails; `configmaps`/`secrets` quota must be 1–200 (never 0, doc 18 I-5); `services*` are always 0 and cannot be set |

**Secrets are never chart values, and their names are fixed** (doc 18 §8.1). Base VAP `devplat-secret-pinning` pins each name to one ServiceAccount. The operator creates them out of band (or through an external secret store, §5):

| Secret | Keys | Consumer |
|---|---|---|
| `devplat-gitbroker-github-app` | `app-id`, `private-key.pem` | gitbroker |
| `devplat-model-gateway-llm-keys` | `<provider>-api-key` | model-gateway |
| `devplat-db-controller`, `devplat-db-api`, `devplat-db-model-gateway` | basic-auth `username`, `password` (also CNPG managed-role passwords) | controller, api, model-gateway |
| `devplat-artifacts-controller`, `-gitbroker`, `-gitbroker-fetch`, `-api` | `access-key-id`, `secret-access-key` (scoped per prefix; workload identity preferred in cloud) | the named component |
| `devplat-oidc-client`, `devplat-linear-token` (optional) | `client-secret`, `token` | api |

Per-run objects are created by the controller, never by the charts:
- Job `dp-<project>-<task>-a<attempt>-d<dispatch>`;
- ConfigMap `<job>-contract`;
- Secret `<job>-io`: the one-time fetch URL, presigned upload targets and the per-Job gateway token.

These objects are owner-referenced to the Job (base VAP `devplat-controller-run-objects`).

## 3. Dependencies

| Dependency | Decision | Reason |
|---|---|---|
| **`platform/deploy/base` cluster prerequisites** (§1) | **Prerequisite**, applied by the operator with an overlay that replaces the placeholders (kube-apiserver IPs, external S3 CIDR, image prefixes, ingress namespace label, `cnpg-system`) | Canonical security model; cluster-scoped objects must not be owned by an application release |
| **CloudNativePG operator** | **Prerequisite**, installed separately by the operator (its own Helm chart or manifest, pinned version). The devplat chart only creates the `Cluster` CR (`postgres.mode=cnpg`) | Operators own cluster-scoped CRDs and webhooks. Bundling them as a subchart couples upgrades and makes `helm uninstall devplat` dangerous. Several releases must not fight over CRDs. Its operator role's cluster-wide Secret rights are residual risk R-18-3 (doc 18 §7) |
| Managed PostgreSQL (RDS, Cloud SQL, Azure DB) | `postgres.mode=external` | Cloud profiles (`25-…`) |
| **S3-compatible artifact store** | **External endpoint**, or an in-cluster store installed separately into `devplat-artifacts` (Service `devplat-artifacts:9000`, as base's NetworkPolicies expect) | The MinIO community edition went **source-only in late 2025, and its GitHub repository was archived on 2026-04-25** [S1]. Pinning it as a subchart would ship an unmaintained dependency. Candidates for an in-cluster store (evaluate; none verified here): a maintained S3-compatible server, Rook/Ceph RGW for multi-node, or cloud object storage |
| Ingress controller | Optional (`ingress.enabled`), any class | Workstations use `kubectl port-forward` |
| Package-registry proxy (`devplat-registry-proxy`, 4873 / OCI mirror 5000) | Separate release; not in this chart yet | Needed for network class `deps` and builds. Base already defines its ServiceAccount and NetworkPolicies |
| gVisor / Kata RuntimeClass | Cluster prerequisite (node-level install + base `runtimeclasses.yaml`) | Node OS dependent (`25-…`) |

## 4. Install, configure, operate: separation of duties

| Phase | Who | What | Never |
|---|---|---|---|
| **Install** (cluster-scoped) | **Operator** (cluster admin) | Cluster, node pools and taints, CNI, RuntimeClass, CloudNativePG operator, base cluster prerequisites, `helm install devplat`, `helm install devplat-project` per project | Agents or the platform installing cluster-scoped objects |
| **Configure** | **Operator** | Secrets, GitHub App (DOD-13), ruleset (DOD-02), OIDC client (DOD-14), budgets, project configuration approval | Configuration through agent PRs that take effect without operator review |
| **Operate** | devplat-controller (automatic) | Jobs, per-run ConfigMaps/Secrets, test namespaces (as `devplat-namespacer`), reconciliation, gate records | Changing its own RBAC, policies, charts or platform secrets |
| **Change** | PR to the chart or values repository → operator review → operator applies (or GitOps sync, §8) | Every change to `platform/**` is a restricted path for agent tasks (`23-…` §5.3) | Self-modification by the platform |

The controller has **no cluster-wide grant** (doc 18 §7, I-1). Its rights are:
- **Project namespaces:** a RoleBinding to `devplat-job-runner`, rendered by `devplat-project`. Jobs create/get/list/watch/patch/delete (patch only to unsuspend, base VAP `devplat-controller-job-update`); ConfigMaps and Secrets create/get/delete (no list, watch or update); pods get/list/watch; pods/log get; events read.
- **Test namespaces:** it impersonates `devplat-namespacer` to create them. The namespacer's cluster-scoped rights are confined by base VAP `devplat-namespacer-scope` to `^proj-<P>-t-[0-9a-f]{8}$` with mandatory labels, and it binds `devplat-test-runner` for the controller inside each test namespace.
- **`devplat-system`:** one Lease, impersonation of exactly one ServiceAccount, and `get` on named Services.

It has no verbs on RBAC objects (except through the namespacer's single RoleBinding shape), CRDs, webhooks, admission policies or nodes. It therefore cannot widen its own permissions. Impersonation separates the namespacer's writes in the audit log and lets admission target them. It is **not** a privilege boundary against a compromised controller (doc 18 Q-18-1).

## 5. Secrets handling

1. Created by the operator: `kubectl create secret …` from the operator's machine, or an external secret store (External Secrets Operator with cloud secret managers, or Sealed Secrets for GitOps). An external store is recommended for multi-node and cloud profiles.
2. Each Secret is referenced only by its one consumer (table in §2), enforced by base VAP `devplat-secret-pinning`. Example: a pod of `devplat-api` that mounts `devplat-gitbroker-github-app` is denied; this case was evaluated offline (§10). Key material (GitHub App key, LLM keys) is mounted as read-only files (mode `0400`). DB and S3 credentials are environment variables, because the client libraries read them from there.
3. Project namespaces hold **only per-run Secrets** `dp-<job>-io`, bounded by quota (`secrets` 1–200; default 100 in exec, 50 in build). Base VAP `devplat-proj-pod-identity` lets project pods reference only `dp-*` Secrets, so a pod spec naming a platform Secret is rejected even inside a project namespace. Test Secrets (Mercury T3 sandbox credentials) exist only in a `sandbox`-class test namespace (`22-…` §4.3).
4. Rotation: replace the Secret, then `kubectl rollout restart` the consumer. The GitHub App key is rotated in GitHub first (two keys valid during the overlap).

## 6. Upgrades, rollback, uninstall and teardown

**Upgrade (N-1 → N)**
1. Read the release notes, compatibility matrix and digests (`23-…` §6).
2. Pause dispatch through the API: running Jobs finish, and no new admissions happen.
3. Take a CloudNativePG backup (or a managed snapshot).
4. `helm upgrade devplat … --atomic --timeout 10m`. The controller runs forward-only migrations at startup under the leader Lease. The standby replica waits.
5. Smoke tests and isolation probes (§9 steps 6–7).
6. Resume dispatch.

**Rollback.**
- `helm rollback devplat <rev>` is safe only if the release did **not** run a migration. Release notes say which releases migrate.
- After a migration, rollback = restore the pre-upgrade backup into a new `Cluster`, then roll back the chart. Task events written after the backup are replayed from GitHub and Job reconciliation (`21-…`). The operator decides on this.
- Rollback is rehearsed in CI (`23-…` §6 step 5).

**Uninstall a project** (`helm uninstall devplat-project-<P>`)
1. Pause the project and wait for its Jobs to end.
2. Export its evidence.
3. Uninstall. This deletes the project's namespaces, and with them its running pods.
4. The project's task history stays in PostgreSQL and its bucket is kept, until the operator deletes them explicitly.

**Uninstall the platform.**
1. Uninstall every project first.
2. Then `helm uninstall devplat`.
3. The CloudNativePG `Cluster` is deleted with the release, but its PVCs follow the operator's reclaim policy. **Take a final backup first.**
4. Cluster prerequisites (CloudNativePG operator, RuntimeClass, base policies) are removed separately, last.

**Teardown of a workstation cluster** = `kind delete cluster` / `k3d cluster delete`, after exporting evidence and backups. GitHub state (branches, draft PRs) is unaffected and is reconciled by a new installation.

## 7. Disaster recovery

| Loss | Recovery | RPO / RTO (targets, unmeasured) |
|---|---|---|
| Controller pod or node | Second replica takes the Lease (≤ lease duration, 15 s default). Jobs reconciled by label selector | 0 / < 1 min |
| PostgreSQL primary (CNPG, 3 instances) | Automatic failover to a replica | ≈ 0 / minutes |
| PostgreSQL total loss | Restore the latest base backup + WAL from object storage into a new `Cluster`. Verify the `task_events` hash chain. Reconcile against GitHub (branches, PRs, merges) and the evidence bucket | Backup interval / < 1 h |
| Artifact store | Restore the bucket from replication or backup. Evidence rows store content hashes, so a restored object is verified, and a missing one is reported, never silently accepted | Per store |
| Whole cluster | New cluster (§9 steps 1–5), restore DB and artifacts, install the charts at the recorded versions, run steps 6–7, resume. GitHub remains authoritative for code, CI and human approval, so no merge state is lost | Hours |

**Backups.** Recent CloudNativePG releases deprecate the in-tree object-store backup (`barmanObjectStore`) in favour of the Barman Cloud plugin (to be confirmed for the chosen version). The chart therefore refuses `postgres.cnpg.backup.enabled=true` until that configuration is templated and tested (open question O-2). Until then backups are configured by the operator next to the chart.

## 8. GitOps option

| | Plain Helm by the operator | **Argo CD** | **Flux** |
|---|---|---|---|
| Model | Imperative `helm upgrade` from the operator's machine | Pull-based Application CRs; UI; sync waves; drift detection | Pull-based controllers (`HelmRelease`, `Kustomization`); CLI-first; drift correction |
| Pros | Fewest moving parts; nothing in-cluster with repository write access; fits a workstation | Clear visibility of desired vs live state; audit of every sync; easy rollback to a Git revision | Light; native Helm and OCI chart support; SOPS decryption; good for multi-cluster through Git |
| Cons | Drift is not detected; the operator's machine holds cluster-admin access | Its own privileged controller (cluster-admin-like) and UI, with its own attack surface and SSO; heavier on a 16 GB laptop | Also a cluster-wide privileged controller; no built-in UI |
| Fit with "only the operator changes the platform" | Direct | **Yes, if** the GitOps repository's `main` is protected like Mercury's (ruleset, operator approval) and the GitOps controller has **read-only** Git credentials | Same condition |

**Recommendation.**
- **Workstation and single-node profiles:** plain Helm, run by the operator.
- **Multi-node and cloud:** Flux (lighter, OCI charts, SOPS) or Argo CD (if the operator wants the UI).
- Either way: a separate deployment repository (or path) with its own ruleset; read-only deploy keys; image digests and chart versions pinned in Git; the GitOps controller excluded from project namespaces' admission exemptions; no automatic image updates.

The choice is an operator decision (ADR-028).

## 9. Bootstrap procedure (amendment steps 1–10)

The platform is bootstrapped **without Mercury or Jupiter**: steps 1–7 use only synthetic fixtures and the fake agent.

| # | Step | Commands / content (outline) | Done by | Needs operator authorization | Exit evidence |
|---|---|---|---|---|---|
| 1 | **Establish the cluster** for the chosen profile (`25-…`) | e.g. `kind create cluster --config …` (workstation) / k3s / managed cluster with `control` and tainted `exec` node pools | Operator | **Yes** (DOD-15): host changes, cloud spend | `kubectl get nodes -L devplat.io/pool` shows the pools and taints |
| 2 | **Node and network prerequisites** | NetworkPolicy-enforcing CNI; gVisor/Kata on exec nodes where supported (otherwise the workstation overlay relaxes only `devplat-proj-runtime-placement` and records `assuranceMode: reduced`); **base cluster prerequisites** with the overlay placeholders replaced (§1): ClusterRoles incl. `devplat-namespacer`, VAPs and `devplat-admission-params`, RuntimeClasses, PriorityClasses, platform namespaces and their NetworkPolicies. Deploy VAP bindings first as `[Warn, Audit]` and check `status.typeChecking` before `Deny` | Operator | **Yes**: cluster-scoped objects | Probe N12 shows enforcement; `kubectl get runtimeclass gvisor`; VAP type checks empty |
| 3 | **Cluster dependencies** | CloudNativePG operator (pinned); S3-compatible store or external bucket; optional ingress and OIDC provider | Operator | **Yes** | Operator pods Ready; bucket reachable |
| 4 | **Identities and secrets** | Development bot GitHub App with `contents:write` on `dev/*` only, `pull_requests:write`, no `administration` or `workflows` (DOD-13, the Kubernetes-mode form of DOD-03 (a)); model API key with a spend limit; DB role secrets; artifact credentials; OIDC client (DOD-14) | **Operator only** | **Yes**: credentials | Secrets exist; App permission screenshot or API listing stored as evidence |
| 5 | **Install the platform** | `helm install devplat platform/deploy/charts/devplat -n devplat-system -f <profile values with real digests>` (or the GitOps commit). Installs controller, api, gitbroker, gitbroker-fetch, model-gateway, devplat-dns | Operator | **Yes** | `helm status`; pods Ready; leader Lease held; `devplat-dns` resolves cluster names and refuses external names |
| 6 | **Deployment smoke tests** | Health and readiness, migrations at the expected version, Lease holder, gitbroker dry-run token mint (no push), model-gateway health with budget 0 | Automated (operator triggers) | No (read-only) | Smoke report in evidence |
| 7 | **Isolation probes** N1–N12 (`22-…` §7) with a synthetic project (`helm install devplat-project-example-a`) | Probe Jobs; **dispatch stays disabled until all pass** | Automated (operator triggers) | No | Probe report; any success at a forbidden action = stop |
| 8 | **Register the first real project and record facts** | Approve `platform/projects/mercury.yaml` (`26-…`), including its still-`unresolved` namespace quotas; render its `devplat-project` values from it; `helm install devplat-project-mercury`; record DOD-02 (ruleset verified) and DOD-13/DOD-03 (identity) as operator facts through `devplat-api` with an OIDC subject | Operator | **Yes**: project approval, facts | Facts with authenticated subject; project namespaces with quotas |
| 9 | **First end-to-end run** | (a) Fake-agent planning task end to end (no LLM, no push). (b) One real `planning` task (LLM spend under the budget, no push). (c) A `dev/*` push and a **draft** PR on a sandbox repository, then verify that the App cannot merge (probe N10) | Platform, with the operator approving each sub-step | **Yes**: LLM spend (b), first push (c) | Task events, gate records, the draft PR URL; no merge capability |
| 10 | **Recover from a simulated worker failure** | During a running fake-agent Job: delete the agent pod; cordon and drain its `exec` node; delete the controller leader pod. Expect: the Job failure is classified and retried by the controller (not by Kubernetes, `backoffLimit: 0`); the standby takes the Lease; Jobs are adopted by label; no duplicate push or PR (idempotency keys); test namespaces are garbage-collected | Automated chaos Job; the operator triggers it | **Yes** (disruptive; non-production cluster only) | Recovery report: 0 duplicate effects, 0 lost tasks, time to the new leader |

Only after steps 1–10 pass may the operator enable dispatch of Mercury code tasks, and only within the v1 hard preconditions (`08-…` §0): DOD-02 and DOD-03 recorded.

*Note on step names:* steps 1 ("establish cluster") and 10 ("recover from simulated worker failure") are the amendment's endpoints as quoted in the drafting brief. Steps 2–9 are this document's decomposition and must be checked against the amendment text.

## 10. Offline validation (reproducible)

```bash
# helm and kubeconform built from source through the Go module proxy (no binaries were installed)
GOBIN=$PWD/bin go install helm.sh/helm/v3/cmd/helm@v3.17.3
GOBIN=$PWD/bin go install github.com/yannh/kubeconform/cmd/kubeconform@v0.6.7
D=$(printf 'sha256:%064d' 0)   # test-only digest; no real image exists
SET=controller.image.digest=$D,api.image.digest=$D,gitbroker.image.digest=$D,gitbrokerFetch.image.digest=$D,modelGateway.image.digest=$D,dns.image.digest=$D
bin/helm lint platform/deploy/charts/devplat -n devplat-system --kube-version 1.33.0 --set $SET
bin/helm template t platform/deploy/charts/devplat -n devplat-system --kube-version 1.33.0 --set $SET \
  | bin/kubeconform -strict -summary -kubernetes-version 1.33.0 \
      -schema-location default \
      -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
bin/helm template m platform/deploy/charts/devplat-project --kube-version 1.33.0 | bin/kubeconform -strict -summary
```

Results on 2026-10-17 (after reconciliation with doc 18 and `platform/deploy/base`):

| Check | Result |
|---|---|
| `helm lint` both charts | Pass |
| `devplat` strict schema validation | 33/33 valid (incl. the CNPG `Cluster` against the datreeio CRDs-catalog schema); external PG + ingress + OIDC variant 33/33 |
| `devplat-project` strict schema validation | 21/21 valid; no-build + RuntimeClass-pin variant 13/13; builder-allowlist variant 21/21 |
| `values.yaml` vs `values.schema.json` (jsonschema 4.26.0) | 0 errors, both charts |
| **Parity with base** (project id `mercury`) | Every shared object identical in spec: 2 Namespaces (labels incl. PSA v1.33), 4 ResourceQuotas, 2 LimitRanges, 6 NetworkPolicies, 2 RoleBindings, 2 ServiceAccounts. Intended differences: chart adds the test-profile ConfigMap and the builder-allowlist VAP; base also re-declares the `default` SAs (§1) |
| Controller Roles/RoleBindings in `devplat-system`/`devplat-artifacts` vs base | Identical (rules, roleRef, subjects) |
| Base VAPs evaluated against the rendered platform pods (CEL, k8s 1.33 environment, offline evaluator) | `devplat-pod-hardening`, `devplat-platform-placement`, `devplat-secret-pinning`, `devplat-image-pinning` allow all 6 Deployments (with the chart's image prefixes in the params); api mounting the GitHub App key is denied |
| Chart CEL (project-specific VAPs) | 4 expressions compile; 5 evaluation cases (allowlisted builder, foreign init image, pinned RuntimeClass, wrong class, no class) behave as intended |
| Negative renders (must fail) | Empty digest; namespace ≠ `devplat-system`; ingress without OIDC; `draftPullRequestsOnly=false`; Secret-name override (unknown key); `cnpg.backup.enabled=true`; external PG without host; quota `secrets=0`; setting `services` quota; prefix mismatch; RuntimeClass `runc`; `platformNamespace≠devplat-system` |
| Not covered | Admission on a real API server (OpenAPI typing of CEL), NetworkPolicy enforcement, anything needing a cluster |

## 11. Capability status

| Capability | Status |
|---|---|
| `devplat` and `devplat-project` charts | **Implemented (untested)**: rendered, schema-validated and compared with base offline; never installed |
| Keyless `devplat-gitbroker-fetch`, `devplat-dns` | **Implemented (untested)** as chart templates; no images |
| Images referenced by the charts | **Blocked**: no images exist (placeholders `ghcr.io/OWNER/devplat-<component>@sha256:…`) |
| CloudNativePG `Cluster` template | **Implemented (untested)**: valid against a community CRD schema; operator version not chosen |
| CNPG backups | **Documented only** (template refuses) |
| GitOps (Flux / Argo CD) | **Documented only**; choice **awaiting operator approval** |
| Bootstrap steps 1–10 | **Documented only**; steps 1–5, 8, 9b/c and 10 **need operator authorization** |
| Disaster recovery targets | **Unverified assumption** (not measured) |

## 12. Open questions

1. **O-1:** Which S3-compatible store for workstation and single-node profiles, now that MinIO community is archived?
2. **O-2:** CloudNativePG version and backup plugin configuration (Barman Cloud plugin).
3. **O-3:** GitOps tool, and whether the deployment repository is separate.
4. **O-4:** Exact wording of amendment bootstrap steps 2–9 (see the note in §9).

## Sources (accessed 2026-10-17; untrusted web content, used as data)

- [S1] MinIO repository: <https://github.com/minio/minio> (archived 2026-04-25; "community edition is now distributed as source code only"), as reported by search results; related report: 36kr (October 2025).
- CloudNativePG releases (v1.30.0, 2026-06): <https://pkg.go.dev/github.com/cloudnative-pg/cloudnative-pg@v1.30.0>.
