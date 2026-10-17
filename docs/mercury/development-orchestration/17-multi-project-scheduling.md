# 17 — Dependency-Aware Multi-Project Scheduling and Admission

Status: **Proposed — Documented only** (Architecture Amendment 001, 2026-10-17). No scheduler code exists; all capacities and budgets below are **planning values**, not measurements.
Reuses / supersedes: **extends** `09-resources-and-costs.md` §2 (concurrency limits), §4 (adjustment rule) and §5 (cost controls) from one project to many; **keeps** `02-principal-orchestrator.md` §3 (READY rule) and §4 (priority order: critical path, then downstream count) and the devorch path-ownership check (`contract_errors` / `active_primary_paths` / `overlap` in `tools/devorch/devorch.py`). Hardware sizing complements `25-…`.

## 1. Kubernetes is not the application scheduler

kube-scheduler places a pod on a node that has room and matching taints, labels and RuntimeClass. ResourceQuota rejects objects that would exceed a namespace quota; it does not queue them. Neither knows about task dependencies, gates, path ownership, review capacity, LLM token budgets, fair share between projects, or the operator's review queue. **All of that is the devplat controller's admission** (this document). Kubernetes provides only the placement and the quota backstop (§7).

This is also unrelated to **Mercury's** own application-level scheduler (the TDD's scheduler/dispatcher inside `mercuryd`): devplat does not use it and Mercury does not use devplat's. A future Mercury scheduler is product code built *on* devplat, not part of it.

## 2. Admission algorithm

Runs in the controller leader on every relevant event (task READY, Job terminal, budget window rollover, operator action) and at least every 30 s. It is deterministic for a given database snapshot, and every decision (admit or hold, with reason) is recorded.

```text
admission_round(snapshot):
  cands  = READY tasks of all ACTIVE projects            # READY already includes G1 and dependencies (16-... step 1)
  usage  = running Jobs per project, per role, per resource; budget spent + reserved
  admitted = []
  loop:
    if count(running) + len(admitted) >= GLOBAL_MAX_JOBS: break
    P = argmin over projects with an unexamined candidate of  share(P) / weight(P)      # §5 fair share
        tie-break: P whose best candidate has the higher priority key (§4), then project id
    if none: break
    T = best unexamined candidate of P by priority key (§4)
    hold = first_failing_check(T):
      1  project paused / draining / target unhealthy            -> "project_state"
      2  hard preconditions for code kinds (DOD-02/03 facts of P)  -> "precondition"
      3  contract_errors port (kind->role, read-only paths, ids)  -> "contract_invalid" (escalate)
      4  path ownership / interface conflict (§9)                  -> "ownership"
      5  per-project max Jobs, per-role max (profile, project cfg) -> "project_cap" / "role_cap"
      6  review backpressure, human queue (§8)                     -> "review_backpressure" / "human_queue"
      7  token/cost budget incl. reservation (§6)                  -> "budget"
      8  resource fit on the exec pool and quota headroom (§6, §7) -> "capacity"
      9  approved image digest and role ConfigMap present          -> "image_unavailable"
    if hold: record_hold(T, hold); mark T examined; continue
    reserve(T): ownership, budget reservation, resources; record "assigned" (READY -> RUNNING); admitted += T
    share(P) += dominant_share(profile(T).requests)
  return admitted                                                # Job creation follows (16-... steps 3-7)
```

Rules:
1. **No speculative work.** Only READY tasks are candidates; an idle slot is never filled with non-READY work (v1 `02-…` §4).
2. **No preemption of agent Jobs.** A running LLM Job is never evicted to make room (lost work costs money). Agent pods use PriorityClass `devplat-agent` with `preemptionPolicy: Never`; platform pods use `devplat-platform` (higher), so agents can never evict the platform.
3. **Holds are visible.** Each held task shows its first failing check and since when, in the API and dashboard.
4. **Admission is idempotent.** Reservations and `assigned` are written in one transaction; a crash before Job creation leaves a RUNNING task without a Job, which the adoption rules turn into `env_retry` (`16-…` §3).

## 3. Concurrency limits

| Level | Source | Initial value (server profile B, §11) |
|---|---|---|
| Global max concurrent Jobs (agent + verifier) | Platform config | 6 |
| Per project max concurrent Jobs | Project config `resources.max_concurrent.jobs` | Mercury 5 (3 implementation + 2 review, `26-…`); Jupiter 3 (placeholder; Jupiter unresolved) |
| Per role per project | `max_concurrent_per_project` in `platform/agents/execution-profiles.yaml`; a project may lower it | Backend 2, Security 2, Code Reviewer 2, all others 1, planner 1 |
| Per project implementation (writing) Jobs | Project config | 3 (v1 scenario B: no gain beyond 3, `05-…` §4) |
| Open PRs awaiting the operator | Platform (one human) and project config | Global 6; per project 4 (v1 `09-…` §2) |
| Mac-lane tasks | Platform | 1 (one operator, one Mac) |

Verifier Jobs (G2 re-runs) count toward the global and per-project limits but not toward role limits.

## 4. Priority within a project

Lexicographic key, highest first:

| # | Key | Why |
|---|---|---|
| k1 | **Finish before start**: review, security-review, integration and verifier work for a task already in flight | Completes gates of resources already spent; shortens the human queue latency; limits WIP |
| k2 | **Critical path**: longest remaining path (P50 days) from the task to the end of the project DAG; subtasks inherit their parent's value | v1 priority 1 (`02-…` §4) |
| k3 | **Downstream count**: number of tasks transitively unblocked | v1 priority 2 |
| k4 | High-risk validation flag (security/recovery spikes, feasibility) from project config | v1 priority 3 |
| k5 | Age in READY (aging) | Prevents starvation inside a project |

The critical path is computed per project from its DAG (Mercury: `data/dag.json` via `devorch.py dag`). Cross-project critical paths are not merged; a declared cross-project dependency raises the upstream task's k3 by the downstream project's dependent count.

## 5. Weighted fair share across projects

- **Share** of project P = Σ over P's running Jobs of the **dominant resource fraction** of the Job's requests (max of CPU/allocatable CPU and memory/allocatable memory of the exec pool), divided by P's `priority_weight` (project config `resources.priority_weight`, default 1). This is dominant-resource fairness on requests.
- The next slot goes to the project with the lowest share that has an admissible candidate (§2). A project with no candidates does not accumulate credit.
- **Guarantee:** a project with candidates waits at most one admission per other active project before it is examined.
- Fair share decides *which project* gets the next slot; §4 decides *which task* of that project. Token/cost budgets (§6) are separate per project and are not traded between projects.

## 6. Budgets

| Dimension | Measured by | Admission check | Enforcement |
|---|---|---|---|
| CPU, memory | Exec-pool node allocatable minus requests of running pods (controller watch) | `requests` must fit on at least one exec node; Σ memory **limits** of running Jobs ≤ allocatable memory (no memory overcommit — OOM in a sandbox loses the attempt); CPU limits may overcommit up to 2× | kube-scheduler (placement); ResourceQuota (§7) |
| Ephemeral storage | Node allocatable ephemeral storage; workspace `sizeLimit` | `requests.ephemeral-storage` fits | Kubelet eviction on `sizeLimit` → classified `env_retry` (`16-…` §6) |
| Artifact storage | Bucket usage per project | Hold at ≥ 90 % of the project's bucket quota | Store quota |
| API tokens and cost | **model-gateway metering** (authoritative, not agent-reported) per Job, project, day | `spent_today + reserved + reservation(T) ≤ 80 %` of the project's daily cap (v1 DOD-08 rule: new dispatch stops at 80 %, running work finishes). `reservation(T)` = `min(contract budget.max_cost_usd, project per-Job cap)`; refunded to actual use at Job end | Gateway refuses calls beyond the Job's reservation (runner exit 75 with reason `job_budget` → `attempt_failed`, charged: the task was too large) and beyond the project's daily cap |
| Provider rate limits (tokens/min, requests/min at the API org) | Gateway | Global token-rate limiter; admission holds new Jobs when the limiter is saturated for > 5 min | Gateway queues/429 → runner `env_retry` |
| Platform total cost | Gateway | Global daily cap across projects (operator-set) | As above |

All money values are operator decisions (DOD-08 per project). Until measured, the per-Job cap is the reservation; `est_cost_usd_p80` in the profile schema is filled only from measured gateway data (§10).

## 7. Kubernetes quota backstops

The backstop exists so that a controller defect cannot exceed a project's share; normal operation never hits it.

| Object | Namespace | Contents |
|---|---|---|
| `ResourceQuota` | `proj-<P>-exec` | `count/jobs.batch` and `pods` = per-project max + 2; `requests.cpu`, `requests.memory`, `limits.memory`, `requests.ephemeral-storage` = per-project max × largest profile; `count/secrets`, `count/configmaps` bounded |
| `ResourceQuota` | `proj-<P>-build`, each `proj-<P>-t-<runid>` | Build and test sizes from project config; created together with the ephemeral namespace |
| `LimitRange` | every `proj-*` namespace | Default and **maximum** container requests/limits (largest profile), so a pod without resources or with oversized ones is rejected |
| `PriorityClass` | cluster | `devplat-platform` (high), `devplat-agent` (`preemptionPolicy: Never`) |

## 8. Review, security-review and human capacity

Every full-lifecycle task needs G3 (code review) **and** G4 (security review, `08-…` §1), and finally the operator (G7). These are the scarce resources, not CPU.

1. **Reserved security-review slot.** Of the `mdev-security-engineer` role limit (2 per project), at least 1 is reserved for `security_review` subtasks; security *implementation* tasks may use only the remainder.
2. **Review backpressure.** If a project has ≥ 2 × (its security-review slots) tasks in AWAITING_REVIEW without G4, new **writing** tasks of that project are held (`review_backpressure`); reviews, verifiers and integration still run (k1).
3. **Human queue.** If a project has ≥ its `max_concurrent.open_prs_awaiting_human` (Mercury 4) tasks in AWAITING_HUMAN, or all projects together have ≥ 6 (one operator), new writing tasks are held (`human_queue`). Stacked work counts (stack depth ≤ 2, `06-…` §6).
4. **Independence.** A security-review Job never runs in the author's workspace and is never the author's Job (CI-1); fair share treats it like any other Job.

## 9. File ownership and interface conflicts (port of devorch path ownership)

1. **Scope.** Ownership is per **repository**. Two projects never share a repository (project config validation refuses it); if that ever becomes necessary, both are one ownership domain.
2. **Owners.** A primary task in RUNNING, AWAITING_REVIEW, AWAITING_INTEGRATION or AWAITING_HUMAN owns its `allowed_paths`. Subtasks and read-only kinds own nothing (devorch `active_primary_paths`).
3. **Conflict test.** devorch's conservative literal-prefix `overlap()`: two pattern sets conflict if any literal prefixes are prefix-related (`src/core/**` conflicts with `src/core/config/**`).
4. **When checked.** At contract creation and revision (as in v1) **and again at admission** (§2 check 4), because ownership can change between `created` and `assigned`. Two READY tasks that conflict with each other: the higher-priority one is admitted, the other is held `ownership`.
5. **Single-owner files.** Files with one designated owner role (Mercury: `package.json` and the lockfile → DevOps; migrations → Database) are expressed as `restricted_paths` for every other role in the project config; the admission check then also catches them.
6. **Interfaces.** A task that depends on an interface (`INTERFACE_FROZEN`) is READY only when the frozen hash matches `interface_contracts[].sha256`; a re-freeze with a new hash revises dependent contracts (`contract_revised` → BLOCKED). Cross-project interfaces are declared in both project configs with the providing task id and frozen file hashes, and are checked the same way.

## 10. Queue management and calibration

- **States shown:** READY (with hold reason and age), ADMITTED (`assigned`, Job pending), RUNNING, waiting on review / human. Operator actions through `devplat-api` (authenticated, recorded): pause, resume, drain a project (no new admissions, running Jobs finish); raise a task's priority (recorded decision, applied as a k1-level override); cancel.
- **Alarms:** a task READY > 24 h without admission; a project at its budget hold; the human queue at its cap; rate-limiter saturation.
- **Calibration** (v1 `09-…` §4 rule, per project and globally): any red resource metric → lower the limit by 1; all green, at capacity > 50 % of the period, READY ≥ 2 × workers and human queue below cap → raise by 1. Resource requests are re-fitted from measured P95 usage after 10 Jobs per role; `est_cost_usd_p80` from gateway data after 10 Jobs per role. All changes are operator-approved edits of profiles or project config.

## 11. Worked admission example (the amendment's mix)

Setting: **profile B** (§12), exec pool allocatable **11.5 CPU / 45 GiB**; global max 6; Mercury max 5, Jupiter max 3; `priority_weight` 1 : 1; budgets below 80 %; no conflicts; nothing running. The two **Jupiter tasks are hypothetical** — Jupiter has no backlog, stack or role set yet; the example assumes it reuses the `mdev-*` profiles.

| Candidate | Role (profile requests) | Dominant share | k1 | k2 crit. path (d) | k3 downstream |
|---|---|---|---|---|---|
| M1 Mercury DT-0102 | backend (1 CPU, 2 GiB) | 1/11.5 = **0.087** | — | 14 | 30 |
| M2 Mercury DT-0105 | backend (1 CPU, 2 GiB) | 0.087 | — | 9 | 12 |
| M3 Mercury DT-0110 | test automation (1.5 CPU, 3 GiB) | 1.5/11.5 = **0.130** | — | 6 | 4 |
| J1 Jupiter (hyp.) | database (1 CPU, 2 GiB) | 0.087 | — | 8 | 5 |
| J2 Jupiter (hyp.) | code reviewer (0.5 CPU, 1.5 GiB) | 0.5/11.5 = **0.043** | ✓ (review of in-flight task) | inherits parent | — |

| Round | Shares before (M / J) | Chosen project | Task | Checks | Shares after |
|---|---|---|---|---|---|
| 1 | 0 / 0 | tie → Jupiter (best candidate has k1) | J2 | all pass | 0 / 0.043 |
| 2 | 0 / 0.043 | Mercury | M1 (k2 = 14) | backend 1/2 | 0.087 / 0.043 |
| 3 | 0.087 / 0.043 | Jupiter | J1 | database 1/1 | 0.087 / 0.130 |
| 4 | 0.087 / 0.130 | Mercury | M2 (k2 = 9) | backend 2/2; ownership vs M1 checked | 0.174 / 0.130 |
| 5 | 0.174 / 0.130 | Jupiter has no candidate → Mercury | M3 | test 1/1 | 0.304 / 0.130 |

Result: all five admitted (5 ≤ 6). Requests 5 CPU / 10.5 GiB; memory **limits** 4+4+6+4+3 = 21 GiB ≤ 45 GiB (no overcommit). Each admitted writing task reserves its per-Job budget.

Variations, same snapshot:
- **A third Mercury backend task** becomes READY → held `role_cap` (backend 2/2) until M1 or M2 finishes; it does not take Jupiter's slot.
- **M2's `allowed_paths` is `src/core/**` while M1 owns `src/core/config/**`** → round 4 holds M2 (`ownership`), and the next Mercury candidate (M3) is examined instead.
- **Mercury has spent 70 % of its daily cap** and each reservation is 6 % → M1 admitted (76 %), M2 would reach 82 % > 80 % → held `budget`, and so is M3; Jupiter is unaffected.
- **Workstation profile A** (global max 2): rounds 1–2 admit J2 and M1; J1, M2, M3 are held `capacity`.
- **Mercury has 4 tasks in AWAITING_HUMAN** → M1, M2, M3 (all writing) are held `human_queue`; J2 and J1 proceed.

## 12. Recommendations by installation profile

| | **A — single workstation** (MacBook Air M2, 16 GB; *planning example only*) | **B — home/office server** | **C — multi-node cluster** | **D — cloud** |
|---|---|---|---|---|
| Topology | Option A, **reduced assurance** (`15-…` §7) | Option B on one host: two VMs (control, exec) | Option B | Option B (Option C per project if needed) |
| Nodes | One Linux VM (4 vCPU, 8 GiB) with a single-node distribution (k3s or similar; choice open); the rest stays with macOS | Host 16 cores / 64 GiB / 1 TB NVMe: control VM 4 vCPU / 12 GiB; exec VM 12 vCPU / 48 GiB (tainted) | 3 control nodes 4 vCPU / 16 GiB (HA control plane, PG replicas); 3 exec nodes 16 vCPU / 64 GiB; optional build node 8 vCPU / 32 GiB without gVisor | Control pool 2 × 4 vCPU / 16 GiB always on; exec pool autoscaling 0–6 × 8 vCPU / 32 GiB; managed PostgreSQL and object storage |
| Platform footprint (estimate) | ≈ 3–3.5 GiB (Kubernetes ≈ 0.8, PG 1, MinIO 0.5, services ≈ 1); minimal observability | ≈ 6 GiB incl. observability | Distributed | Mostly managed services |
| Max concurrent Jobs | **2** (1 writing + 1 review/verifier); profile limits lowered to ≤ 2 GiB per Job by project config | **6** | **12–18** (≈ 6 per exec node) | Budget-bound; start at 12, raise by the §10 rule |
| gVisor | Unverified in an arm64 VM; expect `runtime_class: default` (reduced assurance) | Expected on the exec VM (verify) | Exec nodes (verify per OS) | Provider sandbox where offered (e.g. GKE Sandbox is gVisor-based); otherwise self-managed — verify per provider |
| Expected bottlenecks | RAM (macOS swap), fanless thermal throttling under sustained builds, contention with the **Mac lane** (Mercury T4 runs on the same Mac: stop the VM during Mac-lane sessions) | Model API rate limits and cost; security-review slots; operator review; disk I/O of dependency installs (registry-proxy cache) | Operator review queue (one human); API org rate limits; security reviews | Cost; exec-node cold start (minutes); egress charges; operator review |

Common to all: per-project throughput is bounded by the project's DAG width and the operator; v1's Mercury model showed no gain beyond 3 concurrent implementation agents (`05-…` §4). More projects raise total throughput, not Mercury's.

## 13. Kueue (evaluated, optional later)

| Kueue offers | Fit for devplat |
|---|---|
| Queues of suspended Jobs; `ClusterQueue` quotas per `ResourceFlavor` (≈ node pool); cohorts and borrowing; fair sharing; priorities; `AdmissionCheck` extension point | Good for the **resource** layer when exec capacity is shared with non-devplat workloads or across clusters |
| No knowledge of DAG dependencies, gates, path ownership, review/human capacity or token budgets | The controller's admission (§2) is needed **in any case**; Kueue could only replace checks 5 and 8 |
| Kueue owns `spec.suspend` | Conflicts with devplat's suspended-setup protocol (`16-…` §3); adoption would move per-Job ConfigMap/Secret creation before admission and key upload prefixes by Job name + nonce instead of uid |

**Decision:** not adopted now (one more operator to install and upgrade, no capability gain at ≤ 18 Jobs on dedicated pools). Re-evaluate when exec capacity is shared beyond devplat, when Option C spreads execution over several clusters, or above ≈ 20 concurrent Jobs. Status: **Documented only** (evaluated from Kueue's documented features; not installed or tested).

## 14. Capability status

| Capability | Status |
|---|---|
| Admission algorithm, priority, fair share, budgets, review/human backpressure (this document) | Documented only |
| Path-ownership rule being ported | Implemented+tested in v1 (`devorch.py`, single project) |
| Execution profiles with per-role concurrency | Configured (`platform/agents/execution-profiles.yaml`, schema-validated) |
| ResourceQuota / LimitRange / PriorityClass manifests | Owned by `platform/deploy/base` (`24-…`); not applied to any cluster |
| Gateway metering and budgets | Documented only |
| Hardware profiles A–D | Planning estimates (A is a planning example only; nothing measured) |
| Kueue | Documented only (evaluated, not adopted) |
| Jupiter parameters | Blocked (Jupiter unresolved) |

## 15. Open questions

1. Operator values: daily caps per project and globally, per-Job caps (DOD-08 per project).
2. Fair-share weights for Mercury and Jupiter (default 1 : 1).
3. Whether the global human-queue cap (6) is right for one operator across projects.
4. Workstation VM technology and whether gVisor is usable there at all (determines whether profile A is ever more than reduced assurance).
