# 24 — Helm Deployment, GitOps and Cluster Bootstrap

Status: **Proposed** (Architecture Amendment 001, 2026-10-17; R6 fix round 2026-10-22: D2, D9, D10, D12, D14–D16, D19, D20, D24, S-13, S-22, S-24).
- The charts in `platform/deploy/charts/` are **Implemented (untested)**. They are rendered and checked offline by `platform/tools/charts/run.sh` (§10) and have never been installed on a cluster.
- No devplat image exists. Every image digest is empty, and the charts refuse to render until real digests are supplied.

Reuses / supersedes: v1 `13-…` RB-D1 (host bootstrap with a git ledger) stays as the **local mode** bootstrap. This document adds the cluster bootstrap. The v1 operator-only steps (ruleset, development identity, operator facts) are kept as per-project facts (D1) in §9.

## 1. Chart layout and the boundary with `platform/deploy/base`

`platform/deploy/base/` (owned by `18-…`) is canonical for the security model. It has two layers:

| Layer | Content | Installed by |
|---|---|---|
| **Cluster prerequisites** | ClusterRoles `devplat-job-runner`, `devplat-test-runner`, `devplat-namespacer` (+ ClusterRoleBinding), `devplat-dns` (+ ClusterRoleBinding); all ValidatingAdmissionPolicies, `devplat-cluster-params` and the `devplat-admission-params` of the platform namespaces; RuntimeClasses; PriorityClasses; the namespaces `devplat-system`, `devplat-artifacts` and `devplat-observability` with their `default` ServiceAccounts; every NetworkPolicy of those platform namespaces | **Operator, always from base** (bootstrap step 1), before any chart |
| **Namespace layer** | Platform ServiceAccounts and the controller's Roles in `devplat-system`. Per project: namespaces, quotas, LimitRanges, ServiceAccounts, the controller's RoleBindings, NetworkPolicies, the per-namespace `devplat-admission-params`, and the registry-proxy NetworkPolicy `registry-proxy-<P>` | **Either** the charts (parameterized) **or** `kubectl apply` of base's static rendering for `proj-mercury-*` / `proj-jupiter-*`. Never both for the same namespace: Helm refuses to adopt objects it does not own |

The charts render the namespace layer, plus the workloads that base does not contain. `platform/tools/charts/run.sh` compares the shared objects field by field with base (§10). The intended differences are listed with their reasons in `platform/tools/charts/parity-expected.txt` and `parity-platform-expected.txt`. Any other difference fails the run.

```text
platform/deploy/charts/
├── devplat/                      # control plane: one release per cluster, namespace devplat-system (enforced)
│   ├── values.yaml / values.schema.json   # draft-07, additionalProperties:false; images <registry>/{devplat|mirror}/…
│   └── templates/
│       ├── _helpers.tpl, _workload.tpl    # digest-only images, security contexts, fixed-name Secret env, guards
│       │                                  # (empty operator identities, wrong namespace, shared SA annotations)
│       ├── serviceaccounts.yaml  # one SA per component, automount false, per-component annotations (S-24)
│       ├── controller-rbac.yaml  # Lease, events, service lookup; namespacer reads test profiles. No ClusterRole,
│       │                         # no impersonation
│       ├── controller.yaml       # 2 replicas, Lease; NEVER migrates (DEVPLAT_RUN_MIGRATIONS=never)
│       ├── migrator-job.yaml     # Helm hook Job + its SA: migrations as devplat_migrator (D9)
│       ├── operator-identities.yaml  # hook ConfigMap: api.oidc.allowedSubjects -> operator_identities (D2)
│       ├── api.yaml              # OIDC operator auth (DOD-14)
│       ├── gitbroker.yaml        # GitHub App key; dev/* and draft PRs only; ingress only from the controller
│       ├── gitbroker-fetch.yaml  # keyless source-bundle server :8081
│       ├── artifact-gateway.yaml # :8082 uploads (project pods), :9444 admin (controller); writes S3 itself (D10)
│       ├── namespacer.yaml       # :8083, test namespaces from a fixed template (D19)
│       ├── model-gateway.yaml    # :8080 / admin :9443; policy ConfigMap: endpoint allowlist, server-tool and
│       │                         # MCP rejection, project from token (D12); separate key for reduced projects
│       ├── dns.yaml              # devplat-dns: CoreDNS, kubernetes plugin only (no forward)
│       ├── postgres-cnpg.yaml    # Cluster devplat-pg, digest-pinned operand image, initdb owner devplat_migrator
│       ├── ingress.yaml          # optional; refused without OIDC
│       └── NOTES.txt
└── devplat-project/              # per-project namespace layer: one release per project per execution target
    ├── values.yaml / values.schema.json   # GENERATED from platform/projects/<id>.yaml; defaults = example-a
    └── templates/
        ├── namespaces.yaml       # proj-<P>-exec (PSA restricted), proj-<P>-build (PSA privileged + base VAPs)
        ├── quotas.yaml, serviceaccounts.yaml, controller-rolebindings.yaml
        ├── admission-params.yaml # per-namespace devplat-admission-params: image prefixes (D15), build switches (D20)
        ├── networkpolicies.yaml  # default deny; devplat-dns, gitbroker-fetch :8081, artifact-gateway :8082;
        │                         # model-gateway only for classes model-only|deps; this project's proxy only
        ├── registry-proxy.yaml   # devplat-registry-proxy-<P>: read-only npm proxy + its NetworkPolicy (D14)
        ├── admission-policies.yaml  # project-specific only: builder allowlist; optional RuntimeClass pin
        ├── test-profile.yaml     # parameters the namespacer applies to proj-<P>-t-<8 hex> (D19)
        ├── project-settings.yaml # assurance mode, builds, proxy, LLM key variant (D16)
        └── NOTES.txt
```

## 2. Values model

| Group | Key values | Rules enforced by schema or template |
|---|---|---|
| `platform` | `clusterRef` (`default`), `assuranceMode` | `reduced` also needs each project's `REDUCED-ASSURANCE` fact (D16) |
| Release | — | `devplat` renders only in namespace `devplat-system` (template `fail`) |
| Images | `imageRegistry`; `<component>.image.name`, `.digest` | Name must start with `devplat/` or `mirror/` (D15); digest-only; an empty digest fails the render; CNPG operand image required in `cnpg` mode (S-22) |
| ServiceAccount annotations | `<component>.serviceAccountAnnotations` | No shared map (S-24): unknown key `serviceAccount` is rejected, and identical non-empty annotations on two components fail the render |
| `controller` | replicas, Lease timings (Lease name fixed), admission limits | Ranges bounded |
| `migrator` | image, deadline | Hook Job; see §6 |
| `api.oidc` | issuer, client id, **`allowedSubjects`** `[{issuer, subject, project}]` | `minItems: 1`; an empty list fails the render (D2). Synced into `operator_identities`, which `record_operator_fact` checks; `project: ""` means all projects |
| `gitbroker` | `pushRefPrefix`, `draftPullRequestsOnly`, `callerAuth` | Consts `dev/` and `true`; one replica; `callerAuth.mode` const `projected-token`. The controller presents a projected ServiceAccount token for audience `devplat-gitbroker`; gitbroker verifies it against the cluster's ServiceAccount issuer keys, which it fetches from the apiserver with its **own** projected token (default apiserver audience), authorized only by base `system:service-account-issuer-discovery` (S-23; doc 18 §19 change 6; mTLS is the alternative, not templated). These are gitbroker's own behaviour, not a merge control (§4) |
| `artifactGateway` | replicas, per-run caps | Ports fixed: uploads :8082 (project pods), admin :9444 (controller). Caps may only be lowered below the D11 limits |
| `namespacer` | image | Exactly one replica |
| `modelGateway` | providers; `policy` | `allowedEndpoints` ⊆ {`POST /v1/messages`, `POST /v1/messages/count_tokens`}; `rejectServerTools`, `rejectMcpServers`, `rejectContainer`, `rejectFilesAndBatches` const `true`; `projectFrom` const `token`; only the beta-header allowlist is free (D12) |
| `postgres` | `cnpg` (instances, image, storage) / `external` | Cluster name fixed `devplat-pg` (S-22); `backup.enabled` const false (§7) |
| `artifacts` | S3 endpoint for platform components | `bucketPrefix` const `devplat-` (D11) |
| Project chart | `project.id` `^[a-z][a-z0-9-]{1,22}[a-z0-9]$` (D24); `imageRegistry`; `assurance`; `registryProxy`; quotas; `exec.requiredRuntimeClassName`; `build` (off by default); test profile | Prefix = `proj-<id>`; `reduced` needs a fact id and forbids builds (D16); enabled builds need an allowlist and a Localhost profile (D20); an enabled proxy needs uplinks and a digest (D14); `secrets`/`configmaps` quota 1–200; `services*` always 0 |

**Secrets are never chart values, and their names are fixed** (doc 18 §8.1). Base VAP `devplat-secret-pinning` pins each name to one ServiceAccount. The operator creates them out of band (or through an external secret store, §5):

| Secret | Keys | Consumer |
|---|---|---|
| `devplat-gitbroker-github-app` | `app-id`, `private-key.pem` | gitbroker |
| `devplat-model-gateway-llm-keys` | `<provider>-api-key`, `<provider>-api-key-reduced` (separate spend-limited key, D16) | model-gateway |
| `devplat-db-migrator` | basic-auth; the only login that changes the schema (D9) | migrator hook Job |
| `devplat-db-controller`, `devplat-db-api`, `devplat-db-model-gateway`, `devplat-db-artifact-gateway` | basic-auth (also CNPG managed-role passwords) | controller, api, model-gateway, artifact-gateway |
| `devplat-artifacts-controller`, `-gitbroker`, `-gitbroker-fetch`, `-api`, `-artifact-gateway` | `access-key-id`, `secret-access-key` (scoped per prefix; workload identity preferred in cloud) | the named component |
| `devplat-oidc-client`, `devplat-linear-token` (optional) | `client-secret`, `token` | api |

Per-run objects are created by the controller, never by the charts: Job `dp-<project>-<task>-a<attempt>-<role>-d<dispatch>`, ConfigMap `<job>-contract`, and Secret `<job>-io`. The Secret holds the one-time fetch token, the artifact-gateway upload token (TTL = Job deadline + 15 min) and the per-Job gateway token. All three objects are owner-referenced to the Job (base VAP `devplat-controller-run-objects`).

## 3. Dependencies

| Dependency | Decision | Reason |
|---|---|---|
| **`platform/deploy/base` cluster prerequisites** (§1) | **Prerequisite**, applied by the operator with an overlay that replaces the placeholders (kube-apiserver IPs, external S3 CIDR, `registryBase`, ingress namespace label, `cnpg-system`) | Canonical security model; cluster-scoped objects must not be owned by an application release |
| **CloudNativePG operator** | **Prerequisite**, installed separately (pinned version). The devplat chart only creates the `Cluster` `devplat-pg` | Operators own cluster-scoped CRDs and webhooks; bundling couples upgrades and makes `helm uninstall devplat` dangerous. Its cluster-wide Secret rights are residual risk R-18-3 (doc 18 §7) |
| Managed PostgreSQL (RDS, Cloud SQL, Azure DB) | `postgres.mode=external` | Cloud profiles (`25-…`) |
| **S3-compatible object store** | External endpoint, or an in-cluster store installed separately into `devplat-artifacts`. Reached **only by platform components**; project pods use `devplat-artifact-gateway` (D10) | The MinIO community edition went **source-only in late 2025, and its GitHub repository was archived on 2026-04-25** [S1]. In-cluster candidates (none verified): a maintained S3-compatible server, Rook/Ceph RGW, or cloud object storage |
| Ingress controller | Optional (`ingress.enabled`), any class | Workstations use `kubectl port-forward` |
| Per-project registry proxy | `devplat-project` renders `devplat-registry-proxy-<P>` (Verdaccio, npm only, read-only) when enabled (D14) | The OCI pull-through on :5000 that base's NetworkPolicy allows is **not templated**; other package ecosystems are unresolved |
| gVisor / Kata RuntimeClass | Cluster prerequisite (node-level install + base `runtimeclasses.yaml`) | Node OS dependent (`25-…`) |

## 4. Install, configure, operate: separation of duties

| Phase | Who | What | Never |
|---|---|---|---|
| **Install** (cluster-scoped) | **Operator** (cluster admin) | Cluster, node pools and taints, CNI, RuntimeClass, CloudNativePG operator, base cluster prerequisites, `helm install devplat`, `helm install devplat-project` per project | Agents or the platform installing cluster-scoped objects |
| **Configure** | **Operator** | Secrets; per repository: GitHub App installation (DOD-13) and ruleset + CI hardening (DOD-02, D13); OIDC client (DOD-14); operator identities (`allowedSubjects`); budgets; project configuration approval | Configuration through agent PRs that take effect without operator review |
| **Migrate** | migrator hook Job, triggered by the operator's `helm install/upgrade` | Forward-only schema migrations, grants, `operator_identities` sync | The controller migrating; any runtime role with DDL rights |
| **Operate** | devplat-controller; devplat-namespacer on its request | Jobs and per-run objects; test namespaces from the fixed template; reconciliation; gate records | Changing its own RBAC, policies, charts or platform secrets |
| **Change** | PR to the chart or values repository → operator review → operator applies (or GitOps sync, §8) | Every change to `platform/**` is a restricted path for agent tasks (`23-…` §5.3) | Self-modification by the platform |

The controller has **no cluster-wide grant and no impersonation** (doc 18 §7, D19). Its rights are:
- **Project namespaces:** a RoleBinding to `devplat-job-runner`, rendered by `devplat-project`. This allows Jobs create/get/list/watch/patch/delete (patch only to unsuspend), ConfigMaps and Secrets create/get/delete, pods get/list/watch, pods/log get, and reading events.
- **Test namespaces:** a request `{project, runid}` to `devplat-namespacer`. The namespacer applies its fixed template plus the project's test profile. Its cluster-scoped rights are confined by base VAP `devplat-namespacer-scope`, which checks names, labels, NetworkPolicy peers/ports, quota caps and the computed admission params.
- **`devplat-system`:** one Lease, events, and `get` on named platform Services. Each `devplat-project` release adds `get` on its own proxy Service.

**Merge authority (D13).** gitbroker has no merge or approve code path, and the chart pins `dev/` and draft PRs. But the development App's `contents:write` + `pull_requests:write` **can** merge and approve through the GitHub API. The preventive control is each repository's ruleset (required code-owner review, no bypass; DOD-02), not this chart. Probe N10 attempts both actions in the sandbox repository (`22-…` §7).

## 5. Secrets handling

1. Created by the operator: `kubectl create secret …` from the operator's machine, or an external secret store (External Secrets Operator with cloud secret managers, or Sealed Secrets for GitOps). An external store is recommended for multi-node and cloud profiles.
2. Each Secret is referenced only by its one consumer (table in §2), enforced by base VAP `devplat-secret-pinning`. `run.sh` checks that every Secret referenced by a rendered platform pod is pinned to that pod's ServiceAccount in base, and evaluates the policy on a pod of `devplat-api` that mounts `devplat-gitbroker-github-app`: it is denied (§10). Key material (GitHub App key, LLM keys) is mounted as read-only files (mode `0400`). DB and S3 credentials are environment variables, because the client libraries read them from there.
3. Project namespaces hold **only per-run Secrets** `dp-<job>-io`, bounded by quota (`secrets` 1–200; default 100 in exec, 50 in build). None of them holds an object-store credential (D10). Base VAP `devplat-proj-pod-identity` lets project pods reference only `dp-*` Secrets, so a pod spec naming a platform Secret is rejected even inside a project namespace. Test Secrets (Mercury T3 sandbox credentials) exist only in a `sandbox`-class test namespace (`22-…` §4.3).
4. Rotation: replace the Secret, then `kubectl rollout restart` the consumer. The GitHub App key is rotated in GitHub first (two keys valid during the overlap).

## 6. Upgrades, rollback, uninstall and teardown

**Upgrade (N-1 → N)**
1. Read the release notes, compatibility matrix and digests (`23-…` §6).
2. Pause dispatch through the API: running Jobs finish, and no new admissions happen.
3. Take a CloudNativePG backup (or a managed snapshot).
4. `helm upgrade devplat … --atomic --timeout 10m`. The **pre-upgrade hook Job** `devplat-migrate-r<rev>` applies the forward-only migrations as `devplat_migrator` and syncs `operator_identities`. If it fails, the upgrade stops before any Deployment changes. The controller **never** migrates. It refuses to become ready while the schema version differs from the version it was built for.
   - On a first install with `postgres.mode=cnpg` the hook runs **post-install**, because the `Cluster` is part of the release; the controller stays unready until the hook has finished.
   - D9 asks for pre-install. That is only possible with `external` PostgreSQL.
5. Smoke tests and isolation probes (§9 steps 7–9).
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
2. Then `helm uninstall devplat`. Hook resources (`devplat-migrator` ServiceAccount, `devplat-operator-identities` ConfigMap, the last migrate Job) are not owned by the release; delete them explicitly.
3. The CloudNativePG `Cluster` is deleted with the release, but its PVCs follow the operator's reclaim policy. **Take a final backup first.**
4. Cluster prerequisites (CloudNativePG operator, RuntimeClass, base policies) are removed separately, last.

**Teardown of a workstation cluster** = `kind delete cluster` / `k3d cluster delete`, after exporting evidence and backups. GitHub state (branches, draft PRs) is unaffected and is reconciled by a new installation.

## 7. Disaster recovery

| Loss | Recovery | RPO / RTO (targets, unmeasured) |
|---|---|---|
| Controller pod or node | Second replica takes the Lease (≤ lease duration, 15 s default) and may fence-transfer task leases (token + 1) instead of waiting for them to expire. Jobs are reconciled by label selector (`21-…`, D22) | 0 / task progress resumes within task-lease TTL (2 min) + election (15 s) |
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

## 9. Bootstrap procedure (Amendment 001 §9, steps 1–10)

The step names are the amendment's own (`amendments/AMENDMENT-001-a.md` §9). The platform is bootstrapped **without Mercury or Jupiter**. Steps 1–9 use only the synthetic project `example-a` and the fake agent image.

| # | Amendment step | Content in devplat | Done by | Operator authorization | Exit evidence |
|---|---|---|---|---|---|
| 1 | **Establish the Kubernetes environment** | Cluster for the chosen profile (`25-…`) with a `control` pool and a tainted `exec` pool. NetworkPolicy-enforcing CNI. gVisor/Kata on exec nodes, or a declared reduced-assurance project (D16). **Base cluster prerequisites** with the overlay placeholders replaced; VAP bindings first as `[Warn, Audit]`, then `Deny` once `status.typeChecking` is empty | Operator | **Yes** (DOD-15): host changes, cloud spend, cluster-scoped objects | Pools and taints; RuntimeClass present; VAP type checks empty |
| 2 | **Install required platform dependencies** | CloudNativePG operator (pinned); S3-compatible store or external bucket; optional ingress; OIDC provider (DOD-14) | Operator | **Yes** | Operator pods Ready; bucket reachable from platform namespaces only |
| 3 | **Deploy persistent services** | Secrets (§2 table); `helm install devplat` creates `Cluster devplat-pg` (initdb owner `devplat_migrator`), and the migrator hook applies the schema and syncs `operator_identities` (≥ 1 entry, D2) | Operator | **Yes**: credentials, identities | Hook Job succeeded; schema version recorded; `devplat_owner` NOLOGIN |
| 4 | **Deploy the development controller** | Same release: controller ×2, api, gitbroker, gitbroker-fetch, artifact-gateway, namespacer, model-gateway, devplat-dns | Operator | **Yes** (part of step 3's install) | Pods Ready; Lease held; controller ready only at the expected schema version |
| 5 | **Register agent definitions** | Role catalogue from `platform/agents/execution-profiles.yaml` loaded into the DB `roles` table (D6); role ConfigMaps generated at a pinned commit | Operator triggers (api) | **Yes** | `roles` rows with content hashes |
| 6 | **Register project configurations** | `example-a` first. Later Mercury: approve `platform/projects/mercury.yaml` (`26-…`; its namespace quotas are still `unresolved`), render its `devplat-project` values, `helm install devplat-project-mercury`. Project status `onboarding` (D4) | Operator | **Yes**: project approval | Namespaces, quotas, params, NetworkPolicies present |
| 7 | **Validate security restrictions** | Deployment smoke tests, then isolation probes N1–N13 (`22-…` §7) in `example-a`. N10 attempts merge **and** approve with the development App on the sandbox repository, and must be refused by the ruleset (D13). **Dispatch stays disabled until all pass** | Automated (operator triggers) | No (read-only), except N10 on the sandbox repository | Probe report; any success at a forbidden action = stop |
| 8 | **Execute a sample agent Job** | (a) Fake-agent planning Job end to end (no LLM, no push). (b) One real `planning` Job under a small budget (no push) | Platform; the operator approves (b) | **Yes**: LLM spend (b) | Job, result uploaded through artifact-gateway, gate records |
| 9 | **Verify results are persisted** | `task_events` hash chain verifies; evidence objects `sha256/<hex>` and manifest present; controller restart does not change replayed state | Automated | No | Verification report |
| 10 | **Recover from a simulated worker failure** | During a running fake-agent Job: delete the agent pod; cordon and drain its `exec` node; delete the controller leader pod. Expected: the controller classifies the failure from platform signals (`21-…`, D17) and retries (`backoffLimit: 0`); the standby takes the Lease and fence-transfers task leases; Jobs are adopted by label; there is no duplicate push or PR; test namespaces are garbage-collected | Automated chaos Job; the operator triggers it | **Yes** (disruptive; non-production cluster only) | Recovery report: 0 duplicate effects, 0 lost tasks, time to new leader |

Code tasks for a project are dispatched only after steps 1–10 have passed, the project is `active`, and its **per-project** facts `DOD-02` (ruleset and CI hardening on that repository, D13) and `DOD-13` (App installed for that repository) are recorded by an identity in `operator_identities` (D1, D2). A reduced-assurance project also needs its `REDUCED-ASSURANCE` fact. In that mode the App may be installed on a sandbox repository only, and builds stay disabled (D16).

## 10. Offline validation (reproducible)

Every result in this section comes from one runner. Nothing here is claimed unless it runs:

```bash
# helm v3.17.3 and kubeconform v0.6.7 built from source through the Go module proxy (checksums via sum.golang.org)
GOBIN=$PWD/bin go install helm.sh/helm/v3/cmd/helm@v3.17.3
GOBIN=$PWD/bin go install github.com/yannh/kubeconform/cmd/kubeconform@v0.6.7
HELM=$PWD/bin/helm KUBECONFORM=$PWD/bin/kubeconform GO=$(command -v go) platform/tools/charts/run.sh
```

What `platform/tools/charts/check_charts.py` checks. Test values are in `platform/tools/charts/values/`; they use placeholder digests and a fake operator identity.

| # | Check | What exactly |
|---|---|---|
| 1 | `helm lint` | `devplat` (test values), `devplat-project` (defaults), `devplat-project` (all options on) |
| 2 | Render + `kubeconform -strict` (Kubernetes 1.33.0; the CNPG `Cluster` against the datreeio CRDs-catalog schema) | 5 positive renders: devplat test values; devplat with external PostgreSQL + ingress + OIDC; devplat-project defaults; devplat-project with builds, registry proxy and RuntimeClass pin; devplat-project for `mercury` (parity values) |
| 3 | Negative renders | 30 cases that must fail with an expected message, e.g. missing digests, empty `allowedSubjects` (D2), wrong namespace, ingress without OIDC, gitbroker consts, Secret-name override, shared or identical SA annotations (S-24), image outside `devplat/`/`mirror/` (D15), CNPG without operand digest (S-22), model-gateway policy relaxations (D12), quota `secrets=0`, project id length (D24), builds without allowlist/profile (D20), reduced mode without fact or with builds (D16), proxy without uplinks (D14), gitbroker caller auth other than the projected token (S-23), test quota over the base caps (D19). The list is in the script |
| 4 | Values schema (jsonschema 4.26.0) | Chart values + test values pass; bare `devplat` defaults are rejected (no operator identity, no CNPG digest) |
| 5 | **Parity with base** | `devplat-project` rendered for `mercury` vs every `proj-mercury-*` and `devplat-system/*-mercury` object of base, field by field; the `devplat` chart's ServiceAccounts, Roles and RoleBindings vs base. Allowed differences: `parity-expected.txt`, `parity-platform-expected.txt` (each with its reason). Unlisted or stale entries fail |
| 6 | Secret pinning | Every Secret referenced by a rendered platform pod (Deployments and the migrator Job) is pinned to that pod's ServiceAccount in base `devplat-secret-pinning` |
| 7 | CEL (needs `GO`) | Built from `platform/tools/admission` (Kubernetes 1.33 CEL environment, untyped inputs). (a) The chart's own VAPs compile and behave on 5 cases. (b) Base `devplat-build-exceptions`, driven by the **params the chart renders**, on 5 build-pod cases (allowed pod, builds disabled, host user namespace, Unconfined seccomp, extra arg). (c) Base `devplat-pod-hardening`, `-platform-placement`, `-secret-pinning`, `-image-pinning` allow every rendered platform pod, deny a mis-pinned Secret and deny a project image in `devplat-system` |

Last run: 2026-10-22, against the base as of that day: **51 passed, 0 failed, 0 skipped** (with `GO`). Without `GO`, step 7 is reported as **skipped**, never as passed.

**Not covered:** admission on a real API server (OpenAPI typing of CEL, defaulting), NetworkPolicy enforcement, image behaviour, and anything that needs a cluster.

## 11. Capability status

| Capability | Status |
|---|---|
| `devplat` and `devplat-project` charts | **Implemented (untested)**: rendered and checked offline (§10); never installed |
| Migrator hook, artifact-gateway, namespacer, keyless gitbroker-fetch, devplat-dns, per-project registry proxy | **Implemented (untested)** as chart templates. The components themselves are **not built** (no images); their behaviour is **Designed, unverified** |
| Model-gateway request policy (D12) | **Implemented (untested)** as values and ConfigMap; enforcement code not built (**Designed, unverified**) |
| Operator-identity allowlist (D2) | Chart side **Implemented (untested)**; the DB check in `record_operator_fact` is the DB group's (`19-…`) |
| Images referenced by the charts | **Blocked**: no images exist |
| CloudNativePG `Cluster` template | **Implemented (untested)**: valid against a community CRD schema; operator version not chosen |
| CNPG backups | **Documented only** (template refuses) |
| GitOps (Flux / Argo CD) | **Documented only**; choice **awaiting operator approval** |
| Bootstrap steps 1–10 | **Documented only**; steps 1–6, the N10 part of 7, 8b and 10 **need operator authorization** |
| Disaster recovery targets | **Unverified assumption** (not measured) |

## 12. Open questions

1. **O-1:** Which S3-compatible store for workstation and single-node profiles, now that MinIO community is archived?
2. **O-2:** CloudNativePG version and backup plugin configuration (Barman Cloud plugin).
3. **O-3:** GitOps tool, and whether the deployment repository is separate.
4. **O-4:** Registry proxy for non-npm ecosystems, and the OCI pull-through on :5000 (not templated).
5. **O-5:** First install with in-cluster PostgreSQL runs the migrator post-install (D9 asks for pre-install). Accept, or create the `Cluster` in a separate release first?

## Sources (accessed 2026-10-17; untrusted web content, used as data)

- [S1] MinIO repository: <https://github.com/minio/minio> (archived 2026-04-25; "community edition is now distributed as source code only"), as reported by search results; related report: 36kr (October 2025).
- CloudNativePG releases (v1.30.0, 2026-06): <https://pkg.go.dev/github.com/cloudnative-pg/cloudnative-pg@v1.30.0>.
