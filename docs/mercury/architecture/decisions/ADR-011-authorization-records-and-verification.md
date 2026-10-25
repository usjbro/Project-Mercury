# ADR-011: Immutable, hash-bound authorization and approval records, verified at dispatch and at result application

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-08)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent C owns the schemas (`protocols/schemas/task.authorization.schema.json`, `plan.approval.schema.json`, `output.task_authorization_decision.schema.json`), the DDL and triggers (`architecture/components.md` §6.3–§6.4) and the guards (`architecture/state-machine.md` §8). Agent E evaluates threat coverage |
| Related ADRs | [ADR-004](ADR-004-claude-invocation-model.md), [ADR-009](ADR-009-system-of-record-split.md), [ADR-015](ADR-015-task-condition-model.md), [ADR-018](ADR-018-audit-integrity.md), [ADR-020](ADR-020-detached-runs-and-adoption.md) |

## Context
- Hard constraints: no Codex run without a valid, unrevoked Claude authorization bound to the task, issue and repository (CON-005); no implementation without a Claude approval bound to the exact plan hash, and a plan revision invalidates earlier approval (CON-006); authorization is a versioned record.
- Under [ADR-004](ADR-004-claude-invocation-model.md) Claude never writes the DB; the coordinator records Claude's verdicts. The question is how the coordinator is prevented from fabricating or misapplying authority.
- Phase 3 found: no contract for re-authorization, revocation or scope amendment (RA-05); HMAC described as optional in three places and required in one (RA-19); authority checked only at dispatch, so a result produced under a since-changed spec or a revoked authorization could still be applied (RE-07, RE-14, RD-13).
- With agents under a separate uid ([ADR-013](ADR-013-agent-process-isolation.md)) no agent process can open the DB at all.

## Decision
1. **Records are immutable and versioned.** An authorization version binds: task, issue, repository and base branch, `spec_hash` ([ADR-009](ADR-009-system-of-record-split.md)), scope and `scope_version`, limits, expiry, and a decision block (Claude `run_id`, model actually used, prompt template hash, input digest, output hash, transcript hash). Plan approvals bind `{auth_id, plan_id, plan_sha256, spec_hash}`. Review verdicts bind the head SHA and the snapshot tree SHA ([ADR-017](ADR-017-claude-review-snapshot.md)). Field lists are defined only in the schemas named above.
2. **Supersession and revocation are new rows**, never updates. Revocation may come from a Claude decision or from an operator CLI command (the operator can always stop work, never start it, CON-003).
3. **Re-authorization contract.** An `authorization` decision in `reauthorize` mode returns one of: confirm same scope, amend scope, revoke, or needs human (exact enum in `output.task_authorization_decision.schema.json`).
   - confirm → a new authorization version that supersedes the old one and clears the `spec_changed` hold;
   - amend → a new version with a new `scope_version`;
   - revoke → the task is cancelled through the global cancel transition;
   - needs human → `BLOCKED(needs_human_decision)`.
   Triggers are spec drift, expiry and an operator `request-reauth`. Claude never revokes unprompted. **A new authorization version invalidates existing plan approvals** (they bind `spec_hash`), so a new `plan_review` is required; Claude may approve the same `plan_sha256` again.
4. **Database-enforced provenance.** Triggers reject any authority insert that does not reference a succeeded Claude decision run of the matching type whose output hash and decision match the record, and reject `UPDATE`/`DELETE` on authority tables. The SQL lives only in `components.md` §6.4.
5. **Single writer module.** Only the `DecisionRecorder` holds the insert statements (lint rule and test).
6. **Guards run twice:**
   - at **dispatch**, inside the claim transaction (`state-machine.md` §8.1–§8.2);
   - at **result application**: before a run's output is acted on (including an adopted run after a restart, [ADR-020](ADR-020-detached-runs-and-adoption.md)), the authorization guard re-checks that the authorization is current, unrevoked, unexpired and bound to the current `spec_hash`. If not, the result is stored but not applied.
7. **Integrity layers** are defined by [ADR-018](ADR-018-audit-integrity.md): hash-chained audit log (MUST), off-host anchoring (MUST before unattended operation), HMAC `record_mac` on authority rows (SHOULD).
8. **After a DB restore or new-Mac migration**, authority that cannot be verified maps to `BLOCKED(reauthorization_required)`, never to `guard_integrity_failure` ([ADR-018](ADR-018-audit-integrity.md)).
9. **External back-references:** commit trailers and the PR body carry `auth_id` and version and the plan hash; a Linear comment records each authorization summary. They support reconstruction, never authority.
10. Default expiry and revision budgets are operator decision OD-08; values live in D's parameter table and `state-machine.md` §9.

## How much this matters
With agents unable to reach the DB, the residual threats are coordinator bugs that open a second start path, a process running as the operator (including the operator's interactive agents), and tampered backups. Items 4–6 handle bugs completely. Same-uid tampering is detected, not prevented, by the anchored audit chain ([ADR-018](ADR-018-audit-integrity.md)). **The enforcement backstop is GitHub** ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)): a forged authorization can at worst produce an unwanted PR, never unreviewed code on a protected branch.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Claude signs its own decisions | The key would live in a process that reads untrusted text; no real gain |
| Authorizations stored in Linear | Writable by the human identity and integrations; forgeable |
| Mutable `status` column on authorizations | Loses history; supersession rows are cheap |
| Check authority only at dispatch (Phase 2 text) | A run that finishes after a spec change, revocation or expiry would still be applied (RD-13, RE-07) |
| Keep plan approvals across re-authorization | The approval was judged against the old spec (RA-05c) |
| HMAC as a MUST | Agents cannot write the DB under ADR-013; HMAC then protects only restored or tampered backups. Kept as SHOULD (RD-4) |

## Consequences
- **Positive:** every Codex run is traceable to one authorization version and, for implementation, one plan hash; spec edits, plan revisions, revocation and expiry invalidate both dispatch and result application without special code paths.
- **Negative:** re-authorization forces a new plan review even for unchanged plans (one extra Claude run).
- Contract tests must try to insert forged records and confirm the triggers abort, and must apply a result after revocation and confirm it is not acted on.

## Related requirements
CON-003, CON-005, CON-006; FR-021, FR-022, FR-023, FR-024, FR-102, FR-165; NFR-060; SEC-305, SEC-307, SEC-601, SEC-603.

## Related findings
RA-05, RA-19, RA-21, RE-07, RE-09, RE-14, RD-13, RF-16.

## Operator decisions
- **OD-08** revision budgets and authorization expiry (defaults in the OD register; values in D's parameter table and `state-machine.md` §9).

## Revision history
- Phase 4: re-authorization, amendment and revocation contract; approvals bind `spec_hash`; guard at result application; integrity layers moved to ADR-018 with HMAC as SHOULD; SQL removed (DDL only in `components.md`); restore semantics.
