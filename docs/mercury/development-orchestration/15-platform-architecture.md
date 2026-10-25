# 15 — devplat Platform Architecture (Kubernetes-native, multi-project)

Status: **Proposed — Documented only** (Architecture Amendment 001, 2026-10-17; R6 fix round 2026-10-20; awaits operator approval, `12-amendments.md` DOD-11…DOD-24). Nothing in this document is deployed or tested on Kubernetes. Statements of the form "recommended" are proposals awaiting an operator decision, not decisions (R6 A-29). Capability status uses the amendment vocabulary plus "Designed, unverified" for parts whose components are not built (R6 D26) (§11).
Reuses / supersedes: **supersedes for the platform** `01-development-architecture.md` §2 (component view) and §3 (responsibilities); **keeps** `01-…` §1 (separation rules S1–S4, extended here as rules P1–P10), §4 (authoritative sources, re-targeted in §9), §5 (state machine and gates G1–G7, ported unchanged) and §6 (rationale, extended by ADR-022…024). v1 (docs 00–13) remains the **local mode** (`14-…` §3).

## 1. Scope and principles

**devplat** is a project-agnostic AI development platform. It builds software for registered projects; Mercury is the first and Jupiter is expected to be the second. devplat **is not Mercury**: Mercury's production design (TDD, ADR-001…020) is unchanged unless a separately approved ADR changes it (`27-…`). A change to devplat is never a change to Mercury production, and the reverse.

| # | Principle |
|---|---|
| P1 | **Authority is code, not an LLM.** Task state, gates, admission and dispatch are decided by `devplat-controller` (a deterministic port of devorch `check_transition` / `replay`). LLM roles (specialists and the `planner`) produce *results and proposals* only. |
| P2 | **One writer of task state.** Only the controller's database role writes `tasks` and `task_events`. Agents have no DB route and no DB credentials. |
| P3 | **Human authority is unchanged.** Draft PRs only; G7 is an observed human merge. No platform component *calls* a merge, approval, auto-merge or ruleset API. That is a code property, not a permission boundary: a GitHub App with `contents:write` + `pull_requests:write` **can** merge and approve through the API, so the preventive control is each project repository's ruleset (code-owner review, no bypass) and CI hardening, verified as that project's `DOD-02` fact (R6 D13). |
| P4 | **Agents hold no credentials.** No GitHub token (gitbroker), no LLM API key (model-gateway), no object-store credential or URL (artifact-gateway), no Kubernetes token, no DB password. A pod gets only per-Job, expiring capabilities: a one-time bundle URL (gitbroker-fetch), a one-time upload token (artifact-gateway) and a gateway token that binds it to its project and budget (R6 D10, D12). |
| P5 | **Infrastructure enforces, prompts advise.** NetworkPolicy, RBAC, admission policy, RuntimeClass and broker validation are the controls; `disallowedTools`, deny rules and the guard hook are tripwires. |
| P6 | **Evidence over claims.** Every gate needs evidence the controller produced or verified itself (re-run tests, gitbroker validation, GitHub facts). Port of `02-…` §2. |
| P7 | **Projects are configuration.** Nothing project-specific is compiled into the controller. A project = a versioned project config (`26-…`) + an execution target. |
| P8 | **The platform outlives its projects.** devplat runs, recovers and reports while Mercury or Jupiter code, CI or repositories are broken or absent (§8). |
| P9 | **Execution is disposable.** A Job, pod, workspace or ephemeral namespace may vanish at any moment; durable state is only in PostgreSQL, the artifact store and GitHub. |
| P10 | **Platform before projects.** devplat bootstraps from its own chart without any project code (`24-…`). |

## 2. Revised multi-agent development architecture

v1 put the whole loop into one Claude Code main session. v2 splits that session's two jobs: the **mechanical loop** (ledger, gates, dispatch, push, reconciliation) moves into the deterministic controller; the **reasoning** (writing contract proposals, triaging failures, drafting escalations) moves into short-lived `planner` Jobs.

| Actor | v1 equivalent | May | May not |
|---|---|---|---|
| Operator (OIDC-authenticated via `devplat-api`) | Operator | Approve designs, contracts that widen scope, budgets, projects; record facts and decisions (authenticated, closes R5 N-06); merge PRs on GitHub | — |
| `devplat-controller` | Orchestrator's mechanical loop + `devorch.py` | Validate and record transitions and gates; admit and create Jobs; collect results; request validation and pushes from gitbroker; reconcile GitHub, Linear, Jobs | Decide content; merge; approve; change GitHub settings; accept a gate without evidence |
| `planner` Jobs (role of the Principal Orchestrator) | Orchestrator's reasoning | Read the backlog, design and evidence; write **proposals** (contracts, triage, escalation drafts) to `/out` | Dispatch, record, push, call GitHub or Linear, spawn agents |
| 12 specialist Jobs (`mdev-*`) | Specialist subagents | Work in their workspace within `allowed_paths`; commit locally; write `result.json` | Push, reach GitHub, the DB or the Kubernetes API; see another task's workspace |
| `devplat-gitbroker` (exactly one replica) | `devorch.py push`, `check-result` git checks | Hold the dev-bot App key; write source bundles; validate result bundles; push `dev/*` fast-forward only; open **draft** PRs; read PR/merge facts | Call merge, approval or ruleset APIs (absent from its code; prevented by the DOD-02 ruleset, P3); push outside `dev/*`; force-push |
| `devplat-model-gateway` | (none) | Proxy LLM calls; inject the key; meter tokens and cost per Job and project; enforce budgets | Forward to non-allowlisted hosts |
| `devplat-gitbroker-fetch` (keyless) | — | Serve one-time source bundles to Job init containers | Hold any credential; write anything |
| `devplat-artifact-gateway` | `$DEVORCH_EVIDENCE` | Accept per-Job uploads under `runs/<job-uid>/` with caps; write them to the project bucket with its own credentials | Serve downloads to pods; accept writes outside the token's scope |
| Verifier Jobs (non-LLM) | Orchestrator's G2 re-run | Run `required_tests` at the validated head in a fresh workspace | Change code |
| macOS lane (operator Mac or macOS CI runner) | Mac validation queue | Produce T4 evidence for `mac_validation` tasks | Anything in the cluster |

The task state machine, lifecycles (FULL/SHORT), gates G1–G7, subtask ids (`-rN`, `-sN`, `-iN`), budgets, bound reviews and the contract-core hash are **ported unchanged** from `01-…` §5 and `tools/devorch/devorch.py` into PostgreSQL (`19-…`). Only the storage (git ledger → `task_events`) and the actor names (`principal-orchestrator` → `devplat-controller`; `operator` → an authenticated OIDC subject) change.

## 3. Three logical environments and their isolation

| | Env-A **Platform** (devplat) | Env-B **Mercury** | Env-C **Jupiter** |
|---|---|---|---|
| Purpose | Control plane, state, brokers, artifacts, observability | Agent, build and test execution for Mercury | Agent, build and test execution for Jupiter |
| Namespaces | `devplat-system`, `devplat-artifacts`, `devplat-observability` | `proj-mercury-exec`, `proj-mercury-build`, ephemeral `proj-mercury-t-<runid>` | `proj-jupiter-exec`, `proj-jupiter-build`, ephemeral `proj-jupiter-t-<runid>` |
| Node pool (Option B) | `control` | `exec` (tainted `devplat.io/exec=true:NoSchedule`) | `exec` (same pool, separate namespaces; dedicated pool or cluster possible, §7) |
| Status | Documented only | Documented only. Mercury **has no application code** yet | **Unresolved**: no repository, specification or tracker exists (`14-…` §1). Onboarding contract only (`26-…`); nothing about its stack is assumed |

**Isolation controls (each applies per project; specification of the security matrix in `18-…`).**

| Layer | Control |
|---|---|
| Kubernetes namespace | One set of namespaces per project; the controller only creates Jobs in namespaces of the task's project (admission policy checks `devplat.io/project` label = namespace's project label) |
| Identity | Per-project ServiceAccount `<P>-agent` (in `proj-<P>-exec`) with **zero** RBAC and `automountServiceAccountToken: false` |
| Network | Default-deny ingress and egress in every `proj-*` namespace; allow only devplat-dns (no internet forwarding), model-gateway, artifact-gateway, gitbroker-fetch and (class `deps`) **this project's own** read-only registry proxy `devplat-registry-proxy-<P>` (R6 D14); no route to the object store, another project's namespaces or proxy, PostgreSQL, or the Kubernetes API. Classes: `none \| model-only \| deps` (R6 D5) |
| Compute | `ResourceQuota` + `LimitRange` per project namespace (backstop to controller admission, `17-…` §7); exec pool taint; gVisor `RuntimeClass` |
| Source | A GitHub App installation scoped to the project's repositories only; tokens minted by gitbroker per operation, never given to pods |
| Model | The per-Job gateway token binds the call to its project and budget (not the URL path); only `POST /v1/messages` and `/v1/messages/count_tokens`; server-side tools, `mcp_servers`, files and batches APIs refused (R6 D12) |
| Artifacts | Bucket `devplat-<P>`; uploads only through artifact-gateway with a one-time token scoped to `runs/<job-uid>/`; immutable evidence under `sha256/<hex>`; layout owned by `20-…` (R6 D10, D11) |
| Data | Task identity is `(project_id, task_id)` everywhere (R6 D3); the API enforces project scoping on operator queries (`19-…`) |
| Facts | Hard preconditions (`DOD-02`, `DOD-13` by default, from `review_gates.hard_preconditions`) and per-task required facts count only when recorded **for that project** by an allowlisted operator identity; a platform-wide fact never unlocks a project (R6 D1, D2) |
| Images | Allowed image prefixes per project and per namespace role; platform namespaces admit only platform images (R6 D15) |
| Secrets | Project test secrets (e.g. Mercury T3 sandbox App credentials) live only in that project's test namespace (`22-…`) |

Cross-project dependencies are allowed only when declared in project config and are evaluated by the controller like contract `dependencies[]` (`17-…` §9). No Job ever sees two projects' code.

## 4. Kubernetes deployment architecture

### 4.1 Components and workload types

| Component | Namespace | Workload type | Why this type |
|---|---|---|---|
| `devplat-controller` | `devplat-system` | **Deployment**, 2 replicas, leader election (`coordination.k8s.io` Lease) | Stateless: all state is in PostgreSQL. Two replicas for fast failover; only the leader reconciles; a new leader may fence-transfer task leases (R6 D22). Never runs migrations (R6 D9) |
| `devplat-api` (REST + dashboard backend, OIDC) | `devplat-system` | **Deployment**, 2 replicas | Stateless request handling; operator facts only from allowlisted identities (R6 D2) |
| `devplat-gitbroker` | `devplat-system` | **Deployment, exactly 1 replica** | Sole holder of the dev-bot App key; one writer of pushes keeps ordering simple. Its mirror cache is an `emptyDir`, rebuildable from GitHub plus the bundles in the artifact store |
| `devplat-gitbroker-fetch` | `devplat-system` | **Deployment**, 2 replicas, **keyless** | Serves one-time source bundles (`src/<project>/<sha>.bundle`) to init containers; holds no GitHub credential, so the only component agents talk to about source cannot push |
| `devplat-artifact-gateway` | `devplat-system` | **Deployment** | The only artifact path for agent, build and test pods (port 8082, one-time per-Job upload token, caps); writes to the store with its own credentials (R6 D10) |
| `devplat-model-gateway` | `devplat-system` | **Deployment**, 2 replicas | Stateless proxy; budget reservations and counters in PostgreSQL through its own DB role (R6 D8) |
| `devplat-dns` | `devplat-system` | **Deployment**, 2 replicas | Cluster-internal DNS for project pods without internet forwarding (no DNS tunnelling) |
| `devplat-namespacer` | `devplat-system` | **Deployment**, 1 replica | Creates and deletes ephemeral `proj-<P>-t-<runid>` namespaces from a **fixed template** only; the controller cannot submit free-form NetworkPolicy or quota content (R6 D19) |
| `devplat-registry-proxy-<P>` (one per project) | `devplat-system` | **Deployment** + cache volume, installed by the project chart | Read-only package proxy (publish and adduser disabled), upstreams from the project's `registries_allowlist`; no cross-project cache (R6 D14) |
| Migrations | `devplat-system` | **Helm pre-install/pre-upgrade Job** with the dedicated `devplat_migrator` login | Schema changes need owner rights that no long-running component holds (R6 D9) |
| PostgreSQL | `devplat-system` | **Operator-managed** (CloudNativePG `Cluster`) or managed PostgreSQL (DOD-19) | Failover, WAL archiving and backups are operator concerns; a hand-written StatefulSet would re-implement them |
| Object store | outside the cluster (default) | **External S3-compatible endpoint**; filesystem/PVC only for a reduced-assurance workstation. The chart installs no store; MinIO is not installed (DOD-22) | `20-…` §1. Only platform components reach it |
| Specialist and planner runs | `proj-<P>-exec` | **Job** per dispatch (`backoffLimit: 0`) | Run-to-completion, deadline, TTL, failure policy; retries owned by the controller (`16-…`) |
| Verifier runs (G2, review re-runs, integration tests) | `proj-<P>-exec` / `proj-<P>-t-<runid>` | **Job** | Same reasons; integration and e2e in disposable namespaces |
| Image builds | `proj-<P>-build` | **Job** (BuildKit rootless); **disabled by default** (R6 D20) | No Docker socket; `hostUsers: false` and a Localhost seccomp profile when enabled (`22-…`) |
| Log/metrics collection | `devplat-observability` | Deployment + DaemonSet | Node-level collection needs a DaemonSet |

**Why not a Task CRD and operator.** Task state needs an append-only, hash-chained audit log with relational queries (READY computation, budgets, fair share). etcd is not an audit store, and a CRD would create a second source of truth next to PostgreSQL. The controller is still *operator-style* (level-triggered reconciliation), but over PostgreSQL state; the only Kubernetes objects it owns are Jobs, their per-Job ConfigMap/Secret, and ephemeral namespaces. **Why not CronJobs for the loop.** A tick loop inside the leader gives sub-minute reaction to Job events via watches; CronJobs would add latency and duplicate-tick races.

### 4.2 Component diagram

```mermaid
flowchart LR
    OP["Operator (browser / CLI, OIDC)"]
    GH["GitHub (repos, PRs, CI, ruleset)"]
    LLM["LLM API (Anthropic)"]
    LN["Linear"]
    S3[("External S3-compatible store: devplat-P buckets, runs/, sha256/, src/")]
    MAC["macOS lane (operator Mac / macOS runner)"]
    subgraph SYS["devplat-system (control pool)"]
        API["devplat-api + dashboard"]
        CTL["devplat-controller (leader-elected)"]
        GB["devplat-gitbroker (App key, 1 replica)"]
        GF["devplat-gitbroker-fetch (keyless)"]
        AG["devplat-artifact-gateway"]
        MG["devplat-model-gateway (API key, budgets)"]
        NSR["devplat-namespacer (fixed template)"]
        DNS["devplat-dns (no forwarding)"]
        RP["devplat-registry-proxy-P (read-only, per project)"]
        PG[("PostgreSQL: tasks, task_events, artifacts, budgets")]
    end
    subgraph EXEC["proj-P-exec (exec pool, gVisor)"]
        JOB["Agent / planner / verifier Jobs"]
    end
    OP --> API
    API --> PG
    CTL --> PG
    MG --> PG
    CTL -->|"create/watch Jobs"| JOB
    CTL --> NSR
    CTL --> GB
    CTL --> S3
    CTL -.->|"read-only until DOD-05"| LN
    GB --> GH
    GB --> S3
    GF --> S3
    AG --> S3
    GH -->|"webhooks / polling"| CTL
    JOB -->|"one-time bundle URL"| GF
    JOB -->|"upload token"| AG
    JOB -->|"per-Job token"| MG
    JOB -.->|"deps class only"| RP
    JOB --> DNS
    MG --> LLM
    CTL -->|"mac_validation tasks"| MAC
    MAC -->|"evidence via API"| API
```

Agent pods have no edge to gitbroker (the key holder), the object store, PostgreSQL or the Kubernetes API.

### 4.3 Namespaces and node pools (Option B)

```mermaid
flowchart TB
    subgraph CL["One cluster"]
        subgraph CP["Node pool 'control' (no taint)"]
            NS1["devplat-system"]
            NS2["devplat-artifacts"]
            NS3["devplat-observability"]
        end
        subgraph EP["Node pool 'exec' (taint devplat.io/exec=true:NoSchedule, RuntimeClass gvisor)"]
            M1["proj-mercury-exec"]
            M2["proj-mercury-build (BuildKit; disabled by default)"]
            M3["proj-mercury-t-runid (ephemeral)"]
            J1["proj-jupiter-exec"]
            J2["proj-jupiter-build"]
            J3["proj-jupiter-t-runid (ephemeral)"]
        end
    end
    NS1 -->|"Jobs, quotas, NetworkPolicy"| M1
    NS1 --> J1
```

Placement rules: platform pods carry no toleration for the exec taint, so agent code never shares a node with the controller, gitbroker key or model-gateway key. Agent pods carry the toleration and `nodeSelector devplat.io/pool=exec`. An admission policy (`ValidatingAdmissionPolicy`, `18-…`) rejects any pod in `proj-*` namespaces without the gVisor RuntimeClass (except in the declared reduced-assurance mode), with a service account token, host namespaces, hostPath, privileged mode or added capabilities. If BuildKit cannot run under gVisor, builds use a third pool `build` without gVisor and with its own taint (`22-…`).

## 5. Multi-project execution architecture

```mermaid
sequenceDiagram
    participant R as Project registry (project config YAML, versioned)
    participant C as devplat-controller
    participant DB as PostgreSQL
    participant T as Execution target (cluster_ref, namespace_prefix)
    R->>C: project config vN (validated against project-config schema)
    C->>DB: projects row: config hash, target, budgets, weights
    loop every tick / event
        C->>DB: READY set across all projects (port of devorch ready + issue_blockers)
        C->>C: admission: deps, ownership, quotas, budgets, fair share (17-...)
        C->>T: create Job in namespace_prefix-exec on cluster_ref
        T-->>C: Job status (watch)
        C->>DB: task_events (only writer)
    end
```

1. **Project registry.** Each project is a versioned config (`platform/projects/<P>.yaml`, schema in `26-…`): repositories, role set, path scopes per role, toolchain image, test environments, budgets, fair-share weight, concurrency caps and the execution target. Changing it is an operator-approved change.
2. **Execution target** `{cluster_ref, namespace_prefix}`. `cluster_ref` names a kubeconfig/credential entry held by the controller (`default` = the cluster the controller runs in, as in `26-…`); `namespace_prefix` defaults to `proj-<P>`. Every Job, quota and ephemeral namespace is addressed through it, so moving a project to another cluster (Option C) changes config, not code.
3. **One scheduler for all projects.** READY computation, admission and fair share are global (`17-…`); per-project limits and budgets are enforced inside it.
4. **Platform role catalogue, per-project enablement** (R6 D6). Roles and the kind→role map are data in `platform/agents/execution-profiles.yaml`, loaded into the DB `roles` table at registration; no role literal is seeded in platform code. A project config only **enables** catalogue roles and bounds their path scopes. The `mdev-` prefix is historical. The 12 definitions are Mercury-derived; whether Jupiter enables them is **unresolved**.
5. **Project health is isolated.** A broken project (failing CI, revoked App installation, exhausted budget) is paused by the controller; other projects continue.

## 6. Five things that are easy to confuse

| Concept | What it is | Where it lives | Lifetime | Who changes it | Example |
|---|---|---|---|---|---|
| **Claude Code subagent definition** (role) | Prompt, scope, `tools` / `disallowedTools`, hooks for one role | Definition source repository (today `.claude/agents/mdev-*.md`); in the cluster an immutable ConfigMap generated from it at a pinned commit with the devplat runtime preamble (`16-…` §9) | Versioned with its repository | Operator-approved change | `mdev-backend-engineer.md` |
| **Agent image** (OCI) | The runtime: devplat-runner, Claude Code CLI pinned, project toolchain (e.g. Node 24 for Mercury) | Registry, referenced **by digest** | Immutable per digest | DevOps build Job + operator approval of the digest | `devplat/agent-node24@sha256:…` |
| **Kubernetes Job** | One dispatch of one attempt of one task by one role | `proj-<P>-exec` | Minutes to hours; deleted after collection | Only the controller | `dp-mercury-dt-0001-a2-d1` (name from `jobspec.py`, normative) |
| **Task record** | Durable task state, contract, events, gates, evidence | PostgreSQL `tasks`, `task_events`, `artifacts` (`19-…`), keyed by `(project_id, task_id)` | Until the project is archived | Only the controller (state); operator via API (facts, approvals) | `(mercury, DT-0001)` in RUNNING, attempt 2 |
| **Project config** | What the project is and how it may be built | `platform/projects/<P>.yaml` (project registry) | Versioned | Operator-approved change | `mercury.yaml` with target `{default, proj-mercury}` |
| *(and)* **Role catalogue + execution profile** | Which kinds a role executes; how it becomes a Job: resources, deadline, network, runtime, writes | `platform/agents/execution-profiles.yaml` | Versioned | Operator-approved change | `mdev-code-reviewer`: kind `code_review`, `writes_allowed: false` |

One task has many attempts; one attempt has one or more dispatches (environmental retries), each exactly one Job (plus verifier and review Jobs bound to its head). A role has one definition and one profile; many Jobs use them. An image serves many roles.

## 7. Cluster topology options

| | **Option A** — one cluster, namespaces only | **Option B** — one cluster, dedicated node pools (**recommended**) | **Option C** — separate clusters (platform + per-project) |
|---|---|---|---|
| Shape | Platform and agent pods may share nodes; isolation by namespace, NetworkPolicy, quotas, gVisor | `control` pool for platform services; tainted `exec` pool for agent, build, test Jobs; gVisor | Platform cluster; one execution cluster per project (or per trust level) |
| Security | Lowest: a sandbox escape lands on a node that may host the gitbroker key or model-gateway key | Escape lands on an exec node that holds no platform secrets; kubelet credentials of exec nodes are the residual risk | Strongest blast-radius limit: an escape reaches only one project's cluster |
| Cost | Lowest (one pool, no idle capacity) | Moderate: the control pool is always on; exec can scale to zero in cloud | Highest: one control plane (and its fees or nodes) per cluster |
| Operational burden | Lowest | Moderate: two pools, taints, RuntimeClass on exec nodes | Highest: N clusters, upgrades, cross-cluster credentials, controller holding several kubeconfigs |
| Single workstation (M2 Air 16 GB) | **Fits** (only realistic choice) — as **reduced-assurance mode** | Not meaningful (one node) | No |
| Home/office server | Fits | **Fits** with two VMs or two nodes on one host | Overkill |
| Multi-node cluster | Wasteful of isolation | **Fits** | Fits if trust differs strongly between projects |
| Cloud | Possible | **Fits** (managed node pools, autoscaling exec pool) | Fits; recommended when projects have separate owners or compliance needs |

**Recommendation.**
1. **Option B** is the recommended target topology for any server, multi-node or cloud installation (ADR-023, proposed; operator decision DOD-11).
2. **Option A** is recommended only for a single workstation, as an explicit **reduced-assurance mode**. It is per project and needs that project's operator fact `REDUCED-ASSURANCE` with a reason (R6 D16), declared in its config as `security.reduced_assurance`. In that mode: the dev-bot App is installed on a **sandbox repository only** (no pushes to the real project repository), the project uses a separate spend-limited LLM key, builds are disabled, gVisor may be absent (`runtime_class: default` is admitted only then), and every task event carries `assurance_mode: reduced`; the dashboard and every PR body state the mode. Gates do not change; isolation claims do.
3. **Option C** needs no redesign: every project already addresses execution through its **execution target**. Moving Jupiter to its own cluster = adding a `cluster_ref` credential to the controller, installing the exec-side chart (namespaces, quotas, NetworkPolicy, RuntimeClass, the project's registry proxy and the route to model-gateway, artifact-gateway and gitbroker-fetch) in the new cluster, and changing `mercury.yaml` / `jupiter.yaml`. Cross-cluster egress from exec pods to model-gateway, artifact-gateway and gitbroker-fetch then needs an authenticated ingress (mTLS, DOD-21) instead of in-cluster Services — **Designed, unverified**.

## 8. Independence from Mercury and Jupiter

devplat contains no Mercury or Jupiter code, does not import their schemas (separation rule S1 kept), and none of its components depends on their artefacts at runtime.

| Failure | Effect on devplat | What keeps working |
|---|---|---|
| Mercury repository has a broken `main`, failing CI, or no code at all | Mercury tasks fail G2/G6 or wait; project health → `degraded` | Controller, API, Jupiter execution, reconciliation, reporting |
| Mercury's agent image cannot be built | Mercury Jobs cannot be admitted (`image_unavailable` hold) | Everything else; previous image digests stay usable if still approved |
| GitHub App installation for one project revoked | That project paused (`credentials_or_permissions` escalation) | Other projects |
| A project exhausts its budget | Admission stops for that project at 80 %, hard stop at 100 % (`17-…`) | Other projects' budgets are separate |
| Jupiter not onboarded (today) | No Jupiter namespaces, no Jupiter tasks | Everything; Env-C exists only as config schema and onboarding steps |
| Mercury production (once it exists) is down | **No effect.** devplat never calls Mercury | Everything |

Rules: (1) devplat images, code and tests are built from `platform/` only: no platform code or test imports `tools/devorch` or depends on `docs/mercury` (the only read is the optional doc-sync check in `test_jobspec.py`, which skips when the doc is absent); what the platform needs from v1 is vendored under `platform/` with provenance (the guard hook `platform/agents/hooks/`, the job example `platform/controller/testdata/`, the DB rule tables) (R6 A-04). (2) The controller's READY computation for project P reads only P's config and P's tasks (plus declared cross-project dependencies). (3) A project's failure is never escalated as a platform failure. (4) Mercury self-hosting (`11-…`) does not make devplat depend on Mercury: if Mercury later builds itself, it does so as a *project* on devplat or outside it, never as devplat's control plane.

## 9. What survives from v1 and what changes

| v1 element | v2 | Status |
|---|---|---|
| Separation rules S1–S4 | **Kept**, extended by P1–P10 | Documented only |
| Task lifecycles, transition table, gates G1–G7, reset rule, budgets, subtask ids, bound reviews, contract-core hash | **Kept**, ported to PostgreSQL (`19-…`) | v1: Implemented+tested (30 tests); port: Documented only (schema work in `platform/db`, see `19-…`) |
| Contracts `devorch.task_contract.v1` / `task_result.v1` / `handoff.v1` | **Generalized** to `devplat.task_contract.v2`, `devplat.task_result.v2`, `devplat.handoff.v2` (`platform/schemas/`: project id, project-neutral ids, catalogue roles, planner); v1 stays readable for local mode | v1: Implemented+tested; v2: Configured (schemas + validated examples) |
| `check-result` git checks (`result_errors`) | **Kept**, moved into gitbroker bundle validation | Documented only |
| Path ownership (`active_primary_paths`, `overlap`) | **Kept**, per project, re-checked at admission (`17-…` §9) | Documented only |
| 12 role definitions | **Kept unchanged in the repository**; the generated ConfigMap adds the devplat runtime preamble and the vendored hook path (`16-…` §9, R6 D23) | Configured (v1); generator Implemented+tested offline |
| Principal Orchestrator main session | **Changed**: loop → controller; reasoning → `planner` Jobs | Documented only |
| Git ledger `devorch/state`, LOCK, single-session rule | **Changed**: `task_events` in PostgreSQL + Lease-based leader election + task leases | Documented only |
| Operator facts via `devorch.py fact --actor operator` (self-asserted) | **Changed**: recorded only through `devplat-api` by an allowlisted OIDC subject, **per project** (R6 D1, D2) | Designed, unverified; OIDC provider open (DOD-14) |
| Worktrees `../mercury-wt/<task>` | **Changed**: per-Job `emptyDir` workspace from a gitbroker bundle | Documented only |
| Specialist guard hook and settings denies as the main in-session controls | **Changed**: tripwire only; controls are NetworkPolicy, no credentials, gitbroker validation | Hook: Configured, did not fire in v1 live dispatch (R5) |
| Push via `devorch.py push`, PR via MCP | **Changed**: gitbroker with the dev-bot GitHub App, fast-forward only; human commits on a PR branch become the next base (`16-…` §7.3) | Awaiting operator approval (DOD-13; DOD-02 per repository) |
| Mac validation queue | **Kept** as the external macOS lane (`mac_validation` tasks) | Blocked on the operator |
| WIP limits, cost cap (`09-…`) | **Extended** to multi-project admission and budgets (`17-…`) | Documented only |
| Local mode (single Claude Code session) | **Kept** for use before a cluster exists | v1 status unchanged |

## 10. Rules

1. No component other than `devplat-controller` creates, mutates or deletes Jobs in `proj-*` namespaces (RBAC + admission policy).
2. No pod in `proj-*` namespaces mounts a ServiceAccount token, a GitHub credential, an LLM API key or a DB credential.
3. Every project-addressed operation goes through the project's execution target.
4. Every task event carries `project_id`, actor, evidence, the contract-core hash, `config_version` and `assurance_mode` (`devplat.handoff.v2`; R6 D8).
5. A topology change (A→B, B→C) is a config and chart change recorded as an operator decision; it never changes task semantics.
6. No project pod reaches the object store, PostgreSQL, gitbroker or another project's registry proxy.

## 11. Capability status

| Capability | Status |
|---|---|
| Platform architecture, environments, topology evaluation (this document) | Documented only |
| Controller, api, gitbroker, gitbroker-fetch, artifact-gateway, model-gateway, namespacer | Designed, unverified (not built; chart templates exist, `24-…`) |
| Role catalogue, contract/result/handoff v2 schemas | Configured; validated offline (`validate_projects.py`, schema examples) |
| Namespaces, quotas, NetworkPolicy, RuntimeClass manifests | See `platform/deploy/base` and `24-…` (other deliverables); none applied to any cluster |
| gVisor on the exec pool | Unverified assumption (node OS, arm64 support on the workstation VM, BuildKit compatibility) |
| Option C via execution targets | Designed, unverified; cross-cluster mTLS ingress (DOD-21) |
| Human merge authority | Awaiting operator approval (DOD-02 ruleset + CI hardening per repository, DOD-13) |
| Reduced-assurance mode | Designed, unverified; needs the per-project `REDUCED-ASSURANCE` fact |
| Jupiter environment | Blocked (Jupiter unresolved) |
| macOS lane | Blocked on the operator |

## 12. Open questions

1. OIDC provider for `devplat-api` (DOD-14 in `12-…`).
2. Which CloudNativePG version is pinned (DOD-19) and which external S3-compatible store is used (DOD-22).
3. Whether Jupiter reuses the `mdev-*` role set or brings its own (unresolved with Jupiter).
4. When the platform moves to its own repository (DOD-12), where the definition source repository for the 12 roles lives (today this repository's `.claude/agents/`).
