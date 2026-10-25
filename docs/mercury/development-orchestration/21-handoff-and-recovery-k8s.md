# 21 — Automatic Handoff and Recovery on Kubernetes (devplat)

Status: **Proposed (R6 fix round applied). Normative** for failure classification, Job adoption and orphans, reconciliation, human commits on PR branches and recovery targets (R6 D17, D21, D22, A-12, A-19, A-21); docs 16 and 17 point here. DB-level mechanisms are **Implemented and tested** (`platform/db/test_schema.py`, `19-…` §13): fenced leases and fence transfer, admission, idempotent dispatch, duplicate-execution refusal, event idempotency, platform-signal-only environmental classification, cost budgets across retries, outbox dedup with fenced completion and backoff. Everything involving Kubernetes, GitHub, Linear or LLM APIs is **Designed, unverified** (no cluster, no service code).
Reuses / supersedes: **keeps** `07-handoff-and-recovery.md` §1 handoff flow and rules 1–6, §2 failure taxonomy (re-stated below with platform signals), §3 retry budgets and escalation conditions; event names unchanged. **Supersedes for the platform** §1 rule 7 (notification-driven main session → watch-driven controller), §4 stale ownership (→ §5), §5 idempotency (→ §2, `19-…` §5), §6 single-orchestrator LOCK (→ leases, `19-…` §6). In local mode `07-…` applies unchanged.

## 1. Execution model and create protocol

1. **At-least-once.** Any controller step may run twice (crash between a Kubernetes call and the DB commit, leader change, lost response). Every step is idempotent or fenced.
2. **The DB decides, Kubernetes executes.** A Job exists because a `job_runs` row exists, which exists because an `admit` decision was consumed (`19-…` §7).
3. **One writer per task.** Task lease + fencing token; a stale leader's write is refused inside the transaction (DP002 → that replica steps down).
4. **Create protocol** (order): (a) `record_admission(admit)` → (b) `dispatch_job()` row with the `jobspec.py` name `dp-<project>-<task>-a<attempt>-<role>-d<dispatch>` and key → (c) `set_job_tokens()` (hashes of the per-Job model-gateway and artifact-gateway tokens) → (d) create the Job **suspended** → (e) owned ConfigMap and Secret `dp-<job>-io` → (f) unsuspend → (g) `record_event(dispatched)` with an idempotency key. A crash anywhere is repaired by repeating from the first incomplete step: (a)–(c) and (g) are idempotent in the DB, (d) uses `AlreadyExists` → adopt (§3).
5. **Environmental re-dispatch** within an attempt increments `dispatch_no` (new Job name, key, admission and tokens); it never reuses a Job name.

## 2. Idempotency per step

| Step | Key / name | Repeat | Tested |
|---|---|---|---|
| Admission | `admission_id` consumed by one Job | Second Job on the same admit refused | **Yes** |
| Plan dispatch | `job_runs.idempotency_key` | Same row; **two concurrent sessions → one row** | **Yes** |
| Same slot, other key | `UNIQUE(project, task, attempt, role, dispatch_no)` | Refused (duplicate execution) | **Yes** |
| Create Job | deterministic name | `AlreadyExists` → adopt if labels match (§3) | No |
| Job object replaced | `k8s_job_uid` | uid change refused | **Yes** |
| Record event | `(project, task, idempotency_key)` | Committed record returned | **Yes** |
| Budget reservation | `(job_id, request_id)` | Same reservation | **Yes** |
| Upload | `(job_id, name)` | Second upload refused | **Yes** |
| GitHub / Linear call | `outbox.dedup_key` + lookup-before-create | One row | Dedup **yes**; lookup no |

## 3. Job reconciliation after a restart or leader change (normative)

Run by the new leader **before** it admits new work, then every 60 s, per execution-target cluster: list Jobs in all `proj-*` namespaces by label `devplat.io/project`; join on `devplat.io/idempotency-key` with `job_runs`.

| Found | Condition | Action |
|---|---|---|
| Job + row | labels (project, task, attempt, dispatch, role) equal the row; uid equal or row uid empty; task RUNNING; attempt and dispatch current | **Adopt**: record the uid, phase from status, continue |
| Job + row, uid differs | Job recreated outside the controller | refused by `update_job_phase` (tested) → `stale_detected`, delete the Job, re-dispatch with `dispatch_no + 1` **only with a platform signal**; otherwise `attempt_failed` |
| Job + row, attempt/dispatch not current | late or duplicate | delete; uploads stay `ephemeral`; never collected |
| Job, no row | lost commit of an old leader, or foreign | **Orphan**: delete, never adopt (adoption would bypass admission and budgets); finding in `reconciliation_runs` |
| Row created/running, no Job | deleted or never created | within 2 min of `created_at`: create (step d); else phase `lost` → §6 |
| Row `planned` > 5 min | crash between (b) and (d) | create the Job (same name) |

Every pass writes `reconciliation_runs` (kind `jobs`).

## 4. Duplicate execution detection

| Source | Control |
|---|---|
| Kubernetes pod retry | `backoffLimit: 0`, `podReplacementPolicy: Failed`, `podFailurePolicy` `FailJob` (`16-…`) |
| Double create | name + DB key (tested at DB level) |
| Re-create while the original still runs (API partition) | phase `lost`, not `failed`, until confirmed gone; a late result counts only if attempt and dispatch are still current |
| Effects | One upload token per Job uid, one-time per object name (tested); pushes only via gitbroker after validation; the one-time fetch URL is consumed by the first pod |

## 5. Heartbeats, stale detection and recovery targets (R6 D22)

1. **Signals:** Job/pod watch; `runs/<uid>/runner.json` progress (via artifact-gateway); model-gateway metering for the Job's token. Each refreshes `job_heartbeat()`.
2. **Stale** = `stale_jobs` (no heartbeat for `heartbeat_timeout_seconds`, default 300 s) or the deadline reached → `stale_detected`, collect what exists, then classify (§6).
3. **Leader loss.** The new leader wins the Kubernetes Lease (≈ 15 s), takes the DB lease `controller-leader`, and calls `fence_transfer_task_leases()`: every task lease held by another holder moves to it with token + 1 at once (tested). The old leader's next write fails with DP002.
4. **RTO for task progress = task-lease TTL (2 min) + leader election (15 s)** as the upper bound; with fence transfer, ≈ leader election + one tick. Running Jobs are not interrupted by a leader change (they need no controller until collection).

## 6. Failure classification → event → action (normative, R6 D17)

**Rule.** A failure is **environmental** (`env_retry`: not charged to attempts, budget env 5, backoff 1/5/15/60/240 min) **only** when a **platform signal** explains it. The signals are the rows of `env_signals`: `gateway_429`, `gateway_5xx` (model-gateway-confirmed, for this Job's token), `node_failure`, `pod_eviction`, `preemption`, `image_pull_error` (Kubernetes), `fetch_failure` (gitbroker-fetch codes). The DB refuses `failure_class = environmental` without such a signal and refuses `env_retry` unless it cites a Job of this task classified with the same signal (tested). **Everything the pod reports itself** — runner exit 75, `status: partial`, "rate limited" in a log — is a **charged attempt** (`attempt_failed`) unless a platform signal of the same Job explains it. **Env retries consume the cost budget**: model-gateway reservations are counted over all Jobs of the task (tested), so free retries cannot exceed `budget.max_cost_usd` or the project-day cap.

| Failure | Platform signal / detection | Event | Action | Budget | Tested |
|---|---|---|---|---|---|
| Node failure, drain, preemption, eviction | node NotReady, `DisruptionTarget`, eviction event | `env_retry` | new dispatch (`dispatch_no + 1`) | env 5 + cost | DB **yes** |
| Image pull error | pod `ErrImagePull`/`ImagePullBackOff` | `env_retry`; admission hold `image_unavailable` | re-dispatch after the image is available | env 5 | DB **yes** (signal) |
| Fetch failure | gitbroker-fetch error code | `env_retry` | re-dispatch with a new bundle URL | env 5 | DB **yes** (signal) |
| LLM 429 / 5xx | model-gateway-confirmed for this token | `env_retry` | backoff; gateway queues per project | env 5 + cost | DB **yes** |
| LLM budget exhausted | `reserve_budget()` refused | `escalated` (`budget`) | operator raises the budget or re-splits | — | DB **yes** |
| Container exit ≠ 0 without a platform signal (incl. exit 75), `partial`, no result | Job `Failed`, `runner.json` | `attempt_failed` | correction attempt + 1 | attempts + cost | DB **yes** (charged) |
| Result invalid / claims differ from git | gitbroker + `_result_errors` | `attempt_failed` | correction with findings | attempts | **Yes** |
| Tests fail at G2 | verifier `test_runs` | `tests_failed` | correction | attempts | **Yes** (G2 refused) |
| Review rejects | review subtask | `code_review_changes_required` / `security_review_blocked` | correction, attempt + 1 enforced | review 3 / security 2 | **Yes** |
| Integration fails | integration subtask | `integration_failed` | correction | integration 2 | No (same path) |
| Job vanished | §3 | `stale_detected` → by signal: `env_retry`, else `attempt_failed` | | | No |
| Duplicate Job / uid change | §3, §4 | `stale_detected` | delete foreign Job | — | DB **yes** |
| Controller crash / leader loss | Kubernetes Lease | — | §5.3 fence transfer, §3 reconcile, then admit | — | **Yes** (DB) |
| GitHub secondary rate limit / 403 / 5xx | outbox worker | — | `fail_outbox(retryable, retry_after)` ≥ `Retry-After`, 30 s·2^(n−1) ≤ 1 h; dead after 8 | outbox 8 | DB **yes** |
| Linear rate limit | adapter | — | as GitHub; writes only with the project's configured write fact | outbox 8 | DB **yes** |
| Lost agent session | §5 | per signal | no cross-pod resume; next attempt gets prior result/progress as inputs | | No |
| Any loop budget exhausted | `record_event` refusal | `failed` or `escalated` | operator decision; never raise budgets to pass | — | **Yes** |
| Contract / dependency change | upstream event, frozen hash mismatch | `contract_revised` (max 3, then operator reset; approval before READY, R6 D18) | → BLOCKED | revisions 3 | **Yes** |
| DB unavailable | connection errors | — | stop admitting; Jobs continue; uploads persist; resume on reconnect | — | No |
| Object store unavailable | artifact-gateway / controller errors | — | Jobs keep their result locally until the deadline; the controller retries collection (TTL 24 h) | — | No |

## 7. GitHub reconciliation and human commits (R6 D21)

Every 5 minutes and on each webhook (a hint, never trusted alone):

1. **AWAITING_HUMAN:** read the PR by head branch (`state=all`). Merged with merge commit containing the G6 head, `merged_by` an operator identity (not the bot) and the required approval → `human_merged` (G7). Closed unmerged → `escalated`.
2. **Human commits on a `dev/*` branch** (remote tip ≠ last gitbroker push; any state up to AWAITING_HUMAN): the controller **never force-pushes** (gitbroker has no force option). It records `human_changes_requested` (→ RUNNING; G2–G7 cleared, G1 kept), asks gitbroker to fetch the new tip and validate it like an agent bundle (contract scope, restricted paths, `fsck`, no gitlinks). Valid → the tip becomes the **base of the next attempt**, and every gate is re-earned at the new head. **Non-fast-forward** (remote history rewritten) or a scope violation → `escalated` (`operator_decision`); nothing is pushed until the operator resolves it.
3. **Rulesets:** if the project's ruleset (DOD-02) or App installation (DOD-13) check fails, G6/G7 and pushes are suspended for that project and a blocking alert is raised; the controller cannot revoke facts (only the operator, through devplat-api). gitbroker independently re-checks both against GitHub before every push.
4. Results go to `reconciliation_runs` (kind `github`).

## 8. Outbox processing and Linear

1. Leader-only worker, singleton through `acquire_lease('outbox:<target>')`.
2. `claim_outbox()` with `FOR UPDATE SKIP LOCKED`; claims expire after 120 s; a stale claimer cannot complete (tested).
3. **Lookup before create** (PR by head branch; comment marker `<!-- devplat:<dedup_key> -->`).
4. **Pushes and draft PRs** (`push_dev_branch`, `open_draft_pr`) are refused unless the project is `active` and every hard precondition is a satisfied project fact (tested). Merge, approve and ruleset operations do not exist (tested for `merge_pr`).
5. Linear: read-only reconciliation always; writes only after the project's configured write fact is satisfied (tested).

## 9. Recovery after a database restore (PITR)

1. Restore; `verify_chain()`; compare `chain_digest()` with the last exported checkpoint (`19-…` §8).
2. Admit nothing; run §3 (Jobs without rows are orphans and are deleted; their uploads remain).
3. Run §7: pushes, PRs and merges after the restore point are re-observed; the operator decides per task whether to re-record (fresh evidence) or reset.
4. Outbox: lost rows are re-derived by lookup; markers prevent duplicates. Budget reservations lost in the restore are re-derived from model-gateway metering logs (**Designed, unverified**).

## 10. Tested vs designed

| Mechanism | Status |
|---|---|
| Fenced task lease; expiry; takeover token + 1; fence transfer on election | **Implemented and tested** (DB) |
| Admission consumed once; holds recorded with reason | **Implemented and tested** (DB) |
| Idempotent dispatch under concurrency; duplicate-slot and uid-change refusal | **Implemented and tested** (DB) |
| Environmental only from platform signals; env retries charged to cost budget | **Implemented and tested** (DB) |
| Atomic budget reservation (parallel sessions) | **Implemented and tested** (DB) |
| Event idempotency; budgets; revision limit and approval | **Implemented and tested** (DB) |
| Outbox dedup, fenced completion, backoff, push and Linear gates | **Implemented and tested** (DB) |
| `stale_jobs` view | Implemented (untested) |
| Job adopt/orphan loop, podFailurePolicy, collection, GitHub/Linear loops, human-commit handling, gateway signal reporting | **Designed, unverified** |
| PITR recovery | **Designed, unverified** |

## 11. Resolved gap

The v1 gap (an env re-dispatch within one attempt collided with the per-attempt Job name) is closed: `jobspec.py` names Jobs `…-a<attempt>-<role>-d<dispatch>` and includes the role and `dispatch_no` in the idempotency key (the role since the R6 re-check RA-1: the assigned role and the verifier run Jobs in the same attempt), matching `job_runs.dispatch_no` (`19-…`).
