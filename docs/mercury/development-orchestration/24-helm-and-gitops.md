# 24 — Helm Deployment, GitOps and Cluster Bootstrap

Status: **Proposed** (Architecture Amendment 001, 2026-10-17).
- The charts in `platform/deploy/charts/` are **Implemented (untested)**: rendered with `helm template` and strict-validated offline, never installed on a cluster.
- No devplat image exists. Every `image.digest` is empty, and the charts refuse to render until real digests are supplied.

Reuses / supersedes: v1 `13-…` RB-D1 (host bootstrap with a git ledger) stays as the **local mode** bootstrap. This document adds the cluster bootstrap. The v1 operator-only steps (DOD-02 ruleset, DOD-03 development identity, operator facts) are kept and move into §9 steps 4 and 8.

## 1. Chart layout

```text
platform/deploy/charts/
├── devplat/                      # control plane: one release per cluster, namespace devplat-system
│   ├── Chart.yaml                # apiVersion v2, kubeVersion >=1.30 (ValidatingAdmissionPolicy GA)
│   ├── values.yaml               # defaults = standard-assurance profile; secrets only as references
│   ├── values.schema.json        # draft-07, additionalProperties:false everywhere
│   └── templates/
│       ├── _helpers.tpl          # labels, digest-only image helper (fails on empty), security contexts, guards
│       ├── _workload.tpl         # shared Deployment + Service (+ PDB when replicas > 1)
│       ├── serviceaccounts.yaml  # one SA per component; token mounted only for the controller
│       ├── controller.yaml       # 2 replicas, Lease leader election, admission limits
│       ├── controller-rbac.yaml  # Lease Role; ClusterRole for Jobs/test namespaces (no Secrets, no RBAC, no exec)
│       ├── controller-scope-policy.yaml   # VAP: controller writes only into proj-* namespaces
│       ├── api.yaml              # OIDC operator auth
│       ├── gitbroker.yaml        # GitHub App key mounted read-only; dev/* and draft PRs only
│       ├── model-gateway.yaml    # provider keys mounted read-only; host allowlist; budgets
│       ├── postgres-cnpg.yaml    # CloudNativePG Cluster CR (postgres.mode=cnpg)
│       ├── networkpolicies.yaml  # default deny + explicit allows in devplat-system
│       ├── ingress.yaml          # optional; refused without OIDC
│       └── NOTES.txt
└── devplat-project/              # per-project bundle: one release per project per execution target
    ├── Chart.yaml
    ├── values.yaml               # GENERATED from platform/projects/<id>.yaml (26-…)
    ├── values.schema.json
    └── templates/
        ├── namespaces.yaml       # proj-<P>-exec (PSA restricted), proj-<P>-build (PSA baseline)
        ├── quotas.yaml           # ResourceQuota + LimitRange per namespace
        ├── networkpolicies.yaml  # default deny; egress to gitbroker, model-gateway (exec only), artifacts, proxy
        ├── serviceaccounts.yaml  # <P>-agent, <P>-build: zero RBAC, no token
        ├── admission-policies.yaml  # VAP: RuntimeClass + SA for agent pods; builder allowlist
        ├── test-profile.yaml     # ConfigMap in devplat-system: profile for proj-<P>-t-<runid>
        └── NOTES.txt
```

Generic cluster policies that every profile needs, and that are not project parameters (PSA defaults, RuntimeClass, PriorityClasses, baseline pod-hardening VAPs), live in `platform/deploy/base/` (owned by `15-…`/`18-…`). The charts do not duplicate them.

## 2. Values model

| Group | Key values | Rules enforced by schema or template |
|---|---|---|
| `platform` | `clusterRef`, `assuranceMode` (`standard` / `reduced`) | `networkPolicy.enabled=false` renders only with `reduced` (template `fail`) |
| Images | `<component>.image.repository`, `.digest` | Digest-only; empty digest ⇒ render fails with "no image has been published yet" |
| `controller` | replicas, Lease timings, global and per-project admission limits, test-namespace TTL | Ranges bounded |
| `api.oidc` | issuer, client id, allowed subjects | Ingress refused without an issuer |
| `gitbroker` | App id, key Secret reference, `pushRefPrefix`, `draftPullRequestsOnly` | `replicas` const 1; `pushRefPrefix` const `dev/`; `draftPullRequestsOnly` const `true`; there is deliberately no merge/approve key, and unknown keys are rejected |
| `modelGateway.providers[]` | name (`anthropic`, `openai`), host, key Secret reference | At least one provider |
| `postgres` | `mode` `cnpg` / `external`; instances, storage; external host and credentials | `external` needs a host and a Secret |
| `artifacts` | S3 endpoint, bucket prefix, credentials Secret | — |
| Project chart | `project.id` (≤ 24 chars), prefix (= `proj-<id>`), quotas, `exec.requiredRuntimeClassName`, `build.podSecurityLevel`, builder allowlist (digests), test profile, `sandboxEgress` | Prefix mismatch fails; `privileged` build needs `acceptUnconfined: true` |

**Secrets are never chart values.** The operator creates them out of band (or through an external secret store, §5):
- `devplat-github-app`
- `devplat-model-anthropic`
- `devplat-artifacts`
- `devplat-pg-controller` and `devplat-pg-api` (basic-auth Secrets)

## 3. Dependencies

| Dependency | Decision | Reason |
|---|---|---|
| **CloudNativePG operator** | **Prerequisite**, installed separately by the operator (its own Helm chart or manifest, pinned version). The devplat chart only creates the `Cluster` CR (`postgres.mode=cnpg`) | Operators own cluster-scoped CRDs and webhooks. Bundling them as a subchart couples upgrades and makes `helm uninstall devplat` dangerous. Several releases must not fight over CRDs |
| Managed PostgreSQL (RDS, Cloud SQL, Azure DB) | `postgres.mode=external` | Cloud profiles (`25-…`) |
| **S3-compatible artifact store** | **External endpoint only** in the chart. In-cluster stores are installed separately into `devplat-artifacts` | The MinIO community edition went **source-only in late 2025, and its GitHub repository was archived on 2026-04-25** [S1]. Pinning it as a subchart would ship an unmaintained dependency. Candidates for an in-cluster store (evaluate; none verified here): a maintained S3-compatible server, Rook/Ceph RGW for multi-node, or cloud object storage |
| Ingress controller | Optional (`ingress.enabled`), any class | Workstations use `kubectl port-forward` |
| Package-registry proxy, in-cluster OCI registry | Optional, separate releases | Only when `deps` network class or in-cluster builds are enabled (`22-…` §9) |
| gVisor RuntimeClass | Cluster prerequisite (node-level install) | Node OS dependent (`25-…`) |

## 4. Install, configure, operate: separation of duties

| Phase | Who | What | Never |
|---|---|---|---|
| **Install** (cluster-scoped) | **Operator** (cluster admin) | Cluster, node pools and taints, CNI, RuntimeClass, CloudNativePG operator, `platform/deploy/base`, `helm install devplat`, `helm install devplat-project` per project | Agents or the platform installing cluster-scoped objects |
| **Configure** | **Operator** | Secrets, GitHub App (DOD-03), ruleset (DOD-02), OIDC client, budgets, project configuration approval | Configuration through agent PRs that take effect without operator review |
| **Operate** | devplat-controller (automatic) | Jobs, test namespaces, reconciliation, gate records | Changing its own RBAC, policies, charts or secrets |
| **Change** | PR to the chart or values repository → operator review → operator applies (or GitOps sync, §7) | Every change to `platform/**` is a restricted path for agent tasks (`23-…` §5.3) | Self-modification by the platform |

The controller's RBAC (`controller-rbac.yaml`) has no verbs on RBAC objects, Secrets, CRDs, webhooks, admission policies or nodes. It therefore cannot widen its own permissions. The `devplat-controller-scope` policy narrows its cluster-wide Job and namespace rights to `proj-*` namespaces.

## 5. Secrets handling

1. Created by the operator: `kubectl create secret …` from the operator's machine, or an external secret store (External Secrets Operator with cloud secret managers, or Sealed Secrets for GitOps). An external store is recommended for multi-node and cloud profiles.
2. Each Secret is mounted only into its one consumer:
   - GitHub App key → gitbroker;
   - provider keys → model-gateway;
   - DB role secrets → controller and api;
   - artifact credentials → controller.

   Mounts are read-only files (mode `0400`), not environment variables, except the DB and S3 credentials that the client libraries read from the environment.
3. Project namespaces have a `secrets: "0"` quota. Admission refuses Secret and projected volumes in agent and build pods.
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
| 2 | **Node and network prerequisites** | NetworkPolicy-enforcing CNI; gVisor `RuntimeClass` where supported (or record `assuranceMode: reduced`); `platform/deploy/base` (PSA defaults, PriorityClasses, base VAPs) | Operator | **Yes**: cluster-scoped objects | Probe N12 shows enforcement; `kubectl get runtimeclass gvisor` |
| 3 | **Cluster dependencies** | CloudNativePG operator (pinned); S3-compatible store or external bucket; optional ingress and OIDC provider | Operator | **Yes** | Operator pods Ready; bucket reachable |
| 4 | **Identities and secrets** | Development bot GitHub App with `contents:write` on `dev/*` only, `pull_requests:write`, no `administration` or `workflows` (DOD-13, the Kubernetes-mode form of DOD-03 (a)); model API key with a spend limit; DB role secrets; artifact credentials; OIDC client (DOD-14) | **Operator only** | **Yes**: credentials | Secrets exist; App permission screenshot or API listing stored as evidence |
| 5 | **Install the platform** | `helm install devplat platform/deploy/charts/devplat -n devplat-system -f <profile values with real digests>` (or the GitOps commit) | Operator | **Yes** | `helm status`; pods Ready; leader Lease held |
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
bin/helm lint platform/deploy/charts/devplat --kube-version 1.33.0
bin/helm template t platform/deploy/charts/devplat -n devplat-system --kube-version 1.33.0 \
  --set controller.image.digest=$D,api.image.digest=$D,gitbroker.image.digest=$D,modelGateway.image.digest=$D \
  | bin/kubeconform -strict -summary -kubernetes-version 1.33.0 \
      -schema-location default \
      -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
bin/helm template m platform/deploy/charts/devplat-project --kube-version 1.33.0 | bin/kubeconform -strict -summary
```

Result on 2026-10-17:
- devplat 28/28 resources valid, devplat-project 17/17 valid; variant matrix valid.
- Negative cases fail as designed: empty digest, `draftPullRequestsOnly=false`, unknown key, NetworkPolicy off in standard mode, ingress without OIDC, privileged build without acceptance, prefix mismatch.
- Not covered: CEL compilation, admission behaviour, and anything that needs a cluster.

## 11. Capability status

| Capability | Status |
|---|---|
| `devplat` and `devplat-project` charts | **Implemented (untested)**: rendered and schema-validated offline; never installed |
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
