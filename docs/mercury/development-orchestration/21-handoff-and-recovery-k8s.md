# 21 — Automatic Handoff and Recovery on Kubernetes (devplat)

Status: **Proposed.** The DB-level mechanisms this document relies on are **Implemented and tested** (`platform/db/test_schema.py`, `19-…` §13): fenced task leases, idempotent dispatch, duplicate-execution refusal, idempotent event append, outbox deduplication with fenced completion and backoff, budgets, append-only chain. Everything that involves Kubernetes, GitHub, Linear or the LLM APIs (reconciliation loops, adoption, classification, rate-limit handling) is **Documented only**. No cluster was available.
Reuses / supersedes: **keeps** `07-handoff-and-recovery.md` §1 handoff flow and rules 1–6 (every arrow is an event, bound reviews, results are files, file-based context, escalation routes), §2 failure taxonomy, §3 retry budgets and escalation conditions. Event names are unchanged. **Supersedes for the platform** §1 rule 7 (notification-driven main session → watch-driven controller), §4 stale ownership (→ §5 here), §5 idempotency table (→ §2, `19-…` §5) and §6 single-orchestrator LOCK (→ leases, `19-…` §6). In local mode, `07-…` applies unchanged.

## 1. Execution model

1. **At-least-once.** Any controller step may run twice: after a crash between a Kubernetes call and the DB commit, after a leader change, or after a lost API response. Every step is therefore idempotent or fenced.
2. **The DB decides, Kubernetes executes.** A Job exists because a `job_runs` row exists. A `job_runs` row without a Job is repaired by reconciliation. A Job without a row is an orphan (§3).
3. **One writer per task at a time.** The task lease plus fencing token (`19-…` §6): a stale leader's write is refused inside the transaction.
4. **Order within one step:** (a) commit intent (`dispatch_job` row, or outbox row) → (b) perform the external call with the deterministic name or dedup key → (c) observe → (d) `record_event` with an idempotency key. A crash at any point is repaired by repeating from (a): (a) and (d) are idempotent, and (b) uses `AlreadyExists` or lookup-before-create.

## 2. Idempotency per step

| Step | Key / name | Repeat behaviour | Tested |
|---|---|---|---|
| Plan dispatch | `job_runs.idempotency_key` (`jobspec.py`: `sha256(project‖core‖attempt)`) | Same row returned. **Two concurrent sessions → one row** | **Yes** (`test_idempotent_dispatch_concurrent`) |
| Second dispatch of the same slot with a different key | `UNIQUE(task_id, attempt, role, dispatch_no)` | Refused as a duplicate execution | **Yes** |
| Create Job | `dp-<project>-<task>-a<attempt>-d<dispatch>` (`16-…` §3) | `AlreadyExists` → adopt if the labels match (§3) | No (no cluster) |
| Job object replaced under the same name | `job_runs.k8s_job_uid` | A uid change is refused as a duplicate execution | **Yes** (`update_job_phase`) |
| Record event | `task_events.idempotency_key` | Returns the committed record (`replayed`) | **Yes** |
| GitHub / Linear call | `outbox.dedup_key` + lookup before create | One outbox row; the call is repeated only after a lookup | Dedup **yes**; external lookup no |

## 3. Job reconciliation after a controller restart

Run by the new leader before it admits new work, then every 60 s:

1. **List** Jobs in all `proj-*` namespaces with label selector `devplat.io/project` (one list per execution target cluster).
2. **Join** on `devplat.io/idempotency-key` with `job_runs`.

| Found | Condition | Action |
|---|---|---|
| Job + row, uid matches or row uid empty | Labels (`project`, `task`, `attempt`, `role`) equal the row; task RUNNING; attempt current | **Adopt:** set the uid, phase from Job status, continue collection |
| Job + row, uid differs | The Job was recreated outside the controller | `update_job_phase` refuses (tested) → event `stale_detected`, delete the foreign Job, `env_retry` |
| Job + row, attempt no longer current (task moved on) | Late or duplicate execution | Delete the Job; uploads are kept as `ephemeral`; never collected as a result |
| Job, no row | Created by an old controller whose DB commit was lost, or a foreign Job | **Orphan:** a Job carrying a devplat idempotency key but no row is deleted, never adopted, because adopting would bypass admission and budgets. Recorded in `reconciliation_runs.findings` |
| Row (created/running), no Job | The Job was deleted, garbage-collected or never created | Within 2 min of `created_at`: re-create (step b). Otherwise `lost` → `stale_detected` → `env_retry` |
| Row `planned` older than 5 min | The controller crashed between (a) and (b) | Create the Job (same name; idempotent) |

3. Every pass writes a `reconciliation_runs` row (kind `jobs`) with findings and actions.

## 4. Duplicate execution detection

A duplicate is two pods doing the same task attempt. Sources and controls:

| Source | Control |
|---|---|
| Kubernetes pod retry | `backoffLimit: 0`; `podFailurePolicy` `FailJob` on `DisruptionTarget` (`16-…`) |
| Controller double create | Deterministic name plus DB idempotency key (tested at the DB level) |
| Re-create after an apparent loss while the original pod still runs (API partition) | Phase `lost`, not `failed`, until the Job is confirmed gone. A late result from a lost Job is accepted only if the attempt is still current and no replacement was dispatched. Otherwise it is discarded |
| Effects of a duplicate that slipped through | Results are files in `runs/<uid>/`: one uid, one upload set, and only the current attempt's uid is collected. Pushes go only through gitbroker after validation, so a duplicate pod cannot push. The one-time fetch URL is consumed by the first pod, so a second pod of the same Job fails `fetch` |

## 5. Heartbeats and stale detection

1. **Signals:** Job and pod status from the watch; `runs/<uid>/progress.json`, rewritten by the runner every 60 s (turn count, last tool, token usage), which the controller polls; and model-gateway metering per Job token. Any of them refreshes `job_runs.last_heartbeat_at` through `job_heartbeat()` (tested).
2. **Stale** = an entry in the `stale_jobs` view: no heartbeat for `heartbeat_timeout_seconds` (default 300 s), or `activeDeadlineSeconds` reached.
3. **Response** (port of `07-…` §4, idempotent): `stale_detected` → collect whatever `runs/<uid>/` holds. If `result.json` exists, process it. Otherwise delete the Job, then `env_retry` with a new dispatch, or `reclaimed` → READY.
4. **Task-lease staleness:** a leader that stops renewing loses its tasks after the TTL (2 min). The new leader's token is `+1`, so the old leader's late writes are refused (tested).

## 6. Failure → event → action

| Failure | Detected by | Event (v1 names) | Action | Budget | Tested here |
|---|---|---|---|---|---|
| Controller pod crash / leader loss | K8s Lease expiry | — | New leader: reconcile Jobs (§3), outbox (§8), then admit | — | Lease fencing **yes** (DB) |
| Stale leader writes after takeover | `_check_lease` (DP002) | — (refused) | Old leader steps down on DP002 | — | **Yes** |
| Node failure / drain / preemption | Pod `DisruptionTarget`, node NotReady | `env_retry` | New dispatch (new uid) | env 5 | No |
| Container crash (non-zero exit, no result) | Job `Failed` | `attempt_failed` (task) or `env_retry` (exit 75, OOM, deadline; `16-…`) | Correction attempt +1 or re-dispatch | attempts / env | Budgets **yes** (DB) |
| Agent result invalid / missing / claims differ from git | gitbroker + controller validation | `attempt_failed` | Correction with findings as inputs | attempts | Budget **yes** |
| Tests fail at G2 re-run | Verifier Job | `tests_failed` | Correction | attempts | Budget **yes** |
| Review rejects | Review subtask result | `code_review_changes_required` / `security_review_blocked` | Correction, attempt +1 enforced | review 3 / security 2 | **Yes** (review budget, attempt+1) |
| Integration fails | Integration subtask | `integration_failed` | Correction | integration 2 | No (same code path as review) |
| Duplicate Job / uid change | §4 | `stale_detected` | Delete the foreign Job | — | DB refusal **yes** |
| Job vanished | §3 | `stale_detected` → `env_retry` | Re-dispatch | env 5 | No |
| LLM API 429/529/overloaded | model-gateway response; runner exit 75 | `env_retry` | Backoff 1/5/15/60/240 min (`07-…` §3); gateway also queues per project | env 5 | No |
| LLM budget exhausted (tokens/cost) | model-gateway refuses (`17-…`) | `escalated` (`budget`) | Operator raises the budget or re-splits the task | — | No |
| GitHub secondary rate limit / 403 / 5xx | gitbroker or outbox worker | — (outbox row) | `fail_outbox(retryable, retry_after)`: honour `Retry-After` / `x-ratelimit-reset`, at least 30 s·2^(n−1), capped at 1 h. Dead after 8 attempts → operator alert | outbox 8 | Backoff **yes** (DB) |
| Linear rate limit | Linear adapter | — (outbox) | Same as GitHub. **Linear writes are refused without DOD-05** | outbox 8 | DOD-05 gate **yes** |
| Lost agent session (pod gone mid-conversation) | §5 | `stale_detected` | No resume across pods: the Claude Code session dies with the pod. A new attempt gets the prior attempt's `result`/`progress` as inputs (file-based context, `07-…` §1 rule 5) | env 5 | No |
| Budget exhausted (any loop) | `record_event` refuses the counted event | `failed` or `escalated` | Operator decision; never raise budgets to pass | — | **Yes** |
| DB unavailable | Connection errors | — | Controller stops admitting and keeps Jobs running; uploads persist in the store; resume on reconnect | — | No |
| Object store unavailable | put/get errors | — | Keep the Job (TTL 24 h) and retry collection (`16-…`) | — | No |
| Contract / dependency change | Upstream event or frozen hash mismatch | `contract_revised` | → BLOCKED; counters reset | — | **Yes** (continuity) |

## 7. GitHub reconciliation

The source of truth for code, CI, PRs and merges is GitHub. Every 5 minutes, and on each webhook (webhooks are hints, never trusted alone):

1. For every task in AWAITING_HUMAN: read the PR by branch (`head=<owner>:dev/…`, `state=all`). **Merged** with `merge_commit`/head equal to the G6 head and `merged_by` an operator identity (not the bot) → `human_merged` (G7) with `github_merge` evidence. **Closed unmerged** → `escalated`. **New commits by a human or review "changes requested"** → `human_changes_requested`.
2. For AWAITING_INTEGRATION and later: if the `dev/*` branch tip differs from the recorded head, raise a finding and an operator alert. The bot cannot push elsewhere, so a different tip means human or foreign activity.
3. Check that the `main` ruleset (DOD-02) is still present. If it is missing, suspend G6 and G7 for every project and raise a blocking alert (the controller cannot revoke the DOD-02 fact itself; only the operator can, through the api).
4. Write the result to `reconciliation_runs` (kind `github`).

## 8. Outbox processing and Linear

1. Leader-only worker, singleton through `acquire_lease('outbox:<target>')`.
2. `claim_outbox(holder, n)` with `FOR UPDATE SKIP LOCKED`. A claim expires after 120 s, so a crashed worker's rows are re-claimed (tested). `complete_outbox` by a stale claimer returns false (tested).
3. **Lookup before create.** For example, `open_draft_pr` first lists PRs for the head branch, `comment_pr` searches for a marker `<!-- devplat:<dedup_key> -->`, and Linear comments carry the same marker. This makes the external effect idempotent even though execution is at-least-once.
4. Linear: read-only reconciliation always (issue state, assignee, links to tasks, findings only). Writes (`comment_issue`, `update_issue_state`) are allowed only after the operator fact DOD-05 (tested at enqueue).
5. Merge, approve, ruleset and settings operations do not exist in `outbox_operations`. An attempt to enqueue them is refused (tested for `merge_pr`).

## 9. Recovery after a database restore (PITR)

1. Restore, run `verify_chain()`, and compare `chain_digest()` with the last exported checkpoint (`19-…` §8). Events after the restore point are missing; the gap shows as missing tails relative to the checkpoint.
2. Do not admit new work. Run the Job reconciliation (§3): Jobs without rows are orphans and are deleted. Their uploads remain in `runs/` and in the store.
3. Run the GitHub reconciliation (§7): PRs, pushes and merges that happened after the restore point are re-observed. The operator decides per task whether to re-record (with fresh evidence) or reset.
4. Run outbox reconciliation: rows lost in the restore are re-derived by lookup; the markers prevent duplicates.

## 10. What is tested vs proposed

| Mechanism | Status |
|---|---|
| Fenced task lease; expired lease lost; takeover token +1 | **Implemented and tested** (DB) |
| Idempotent dispatch under real concurrency (two psql sessions) | **Implemented and tested** (DB) |
| Duplicate execution refusal (slot unique, uid change) | **Implemented and tested** (DB) |
| Event idempotency key replay | **Implemented and tested** (DB) |
| Budgets and attempt +1 on correction | **Implemented and tested** (DB) |
| Outbox dedup, fenced completion, retry backoff, DOD-05 gate, no merge operation | **Implemented and tested** (DB) |
| Heartbeat function | **Implemented and tested** (one call) |
| `stale_jobs` view | Implemented (untested) |
| Job list/adopt/orphan reconciliation, podFailurePolicy classification | Documented only |
| GitHub and Linear reconciliation loops, lookup-before-create | Documented only |
| LLM rate-limit handling in model-gateway | Documented only |
| PITR recovery procedure | Documented only |

## 11. Known gap

`env_retry` re-dispatches **within the same attempt** (not charged, `07-…` §3) with a new `dispatch_no`. The Job name `dp-<project>-<task>-a<attempt>-d<dispatch>` and the idempotency key both include it (`jobspec.py`, test `test_env_retry_gets_a_new_job_not_the_failed_one`), so a retry gets a new Job and a crashed controller re-creating the same dispatch adopts it. **Resolved.**
