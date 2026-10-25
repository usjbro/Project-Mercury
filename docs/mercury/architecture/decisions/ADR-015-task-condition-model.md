# ADR-015: Task condition model — states, holds, `BLOCKED` and the derived queue

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-27, OD-33)** |
| Date | 2026-10-12 |
| Owner | Agent A. Agent C owns the state list, transition table, hold kinds, block reason codes, timers and invariants (`architecture/state-machine.md` §1–§7) and the queue (`architecture/components.md` §7) |
| Related ADRs | [ADR-002](ADR-002-sqlite-store-and-queue.md), [ADR-009](ADR-009-system-of-record-split.md), [ADR-011](ADR-011-authorization-records-and-verification.md), [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md), [ADR-019](ADR-019-notifications-and-operator-presence.md) |

## Context
- The brief lists 18 candidate states, including `DISCOVERED` and `BLOCKED`.
- Phase 2 had two models for "work cannot proceed right now":
  - A: `BLOCKED` with a reason, auto-resuming when the condition clears;
  - C: **holds**, conditions orthogonal to state, and `BLOCKED` only when a human must act.
- Phase 2 also had two queue designs: A's `jobs` table and C's queue derived from task state (known disagreements 1 and 2).
- The Slack-era failures include a 14 h silent stall and floods of non-actionable messages. Both a state that never clears and a notification that needs no action are failures.
- Phase 3 added: holds never notify, so a hold that never clears recreates the silent stall (RA-30); security conditions must not auto-clear (RE-25); holds cannot emit outbox effects, so a hold cannot update the required check (RC-02); hold and block vocabularies differ between documents (RC-21, RC-23); a repo-wide pause after an integrity alert had no hold kind (RA-18).

## Decision
1. **State records workflow phase.** There are **17 task states** (`state-machine.md` §1.2). `DISCOVERED` is an issue-level status (`linear_issues.mercury_status`), not a task state. TDD §11 carries the brief-name → design mapping.
2. **Holds suspend dispatch without changing state.** Hold kinds include operator pause, host sleep grace, network down, rate limits, agent authentication, budgets, configuration, low disk, `spec_changed`, `dependency_unresolved`, `deprioritized`, `operator_hold` and repo-scoped `integrity_alert`. The canonical list, scopes, setters, clearers and `stop_runs` flags are only in `state-machine.md` §5.
3. **`BLOCKED` means a human must act.** It always carries a reason code from `state-machine.md` §6.1 and produces exactly one notification per (task, reason, resume epoch), with reminders.
4. **Amendments adopted from the reconciliation (RD-3):**
   - **Hold ageing.** A task-scoped hold that stays active longer than its threshold, measured in credited awake time, escalates **once** to `BLOCKED(needs_human_decision)` or a digest notification. Per-kind thresholds are in D's parameter table.
   - **Security conditions never auto-clear.** They are `BLOCKED(security_escalation)` (or another security reason code) or a global or repo-scoped `security_halt`, cleared only through the human-presence tier ([ADR-019](ADR-019-notifications-and-operator-presence.md)).
   - **Clearing a hold that re-enables Codex work goes through the authorization guard** ([ADR-011](ADR-011-authorization-records-and-verification.md)); clearing never bypasses it.
   - **Holds can emit outbox effects** (for example, setting `MERCURY / claude-review` to an action-required failure while `spec_changed` is active at PR stage, [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)).
5. **The queue is derived** from `tasks.state`, active holds, run leases and `next_action_at` ([ADR-002](ADR-002-sqlite-store-and-queue.md)). There is no `jobs` table.
6. **Timer rule (RD-14, extends C's invariant on timers):** a state timer may fire only after at least one attempt of the awaited action was made after the latest wake or start; durations are measured from first observation; on wake, due reminders and expiries are coalesced into one summary notification.
7. **Merge verification failure** is `BLOCKED(merge_verification_failed)`, scoped as in [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md) item 9. There is no `MERGE_UNVERIFIED` state, and `MERGED` is never left "with a flag".
8. **`mercury/policy` escalation** is `BLOCKED(policy_ack_required)` before human review, cleared by `mercury policy ack` (presence tier).
9. A task in `BLOCKED` past the abandonment TTL moves to `FAILED` (OD-27).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| `BLOCKED` with auto-resume for every condition (A's Phase 2 position) | Mixes "a person must act" with "the machine is waiting"; every sleep or rate limit would notify; the resume point needs a separate table |
| A new state per waiting condition (paused, sleeping, offline …) | Multiplies the transition table; conditions overlap (a task can be both rate-limited and spec-changed) |
| Holds without ageing or notification (C's Phase 2 text) | A hold that never clears is a silent stall (RA-30) |
| Auto-clearing security holds | An agent or a transient observation could clear a security condition with no human in the loop (RE-25) |
| `jobs` table | See [ADR-002](ADR-002-sqlite-store-and-queue.md) |
| `MERGE_UNVERIFIED` state or `MERGED` + flag | `MERGED` is a work state the dispatcher keeps trying to complete; a reason code on `BLOCKED` is enough |

## Consequences
- **Positive:** every `BLOCKED` notification is actionable; machine-resolvable conditions are silent until they age; the resume point is the unchanged state.
- **Positive:** one vocabulary for conditions across all documents (C's lists are canonical).
- **Negative:** the dispatcher and status views must combine state and holds; `mercury status` shows hold age.
- **Negative:** hold thresholds are judgement calls and need tuning after the shadow stage.

## Related requirements
FR-004, FR-024, FR-046, FR-047, FR-080, FR-082, FR-083, FR-182, FR-220, FR-221, FR-222; CON-009, CON-012; NFR-003; SEC-902.

## Related findings
RA-15, RA-18, RA-28, RA-30, RC-02, RC-17, RC-21, RC-23, RF-16, RF-27, RE-25; known disagreements 1, 2, 11, 12.

## Operator decisions
- **OD-27** `BLOCKED` TTL before `FAILED` (default in the OD register; value in D's parameter table).
- **OD-33** re-authorize on every spec edit (default yes; drives the `spec_changed` hold).
