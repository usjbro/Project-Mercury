# Phase 5 Validation C: Implementation Feasibility

| | |
|---|---|
| Validator | Agent C (Staff/Principal Software Engineer) |
| Date | 2026-10-13 |
| Scope | `architecture/state-machine.md`, `architecture/components.md` (§4–§6, §10), `protocols/messages.md` + `protocols/schemas/`, cross-references from `operations/recovery.md`, `integrations/github.md`, `security/threat-model.md`, `testing/verification-plan.md`, `planning/issue-breakdown.md`, and TDD §8, §11, §16, §17 |
| Method | Inspection, traces, and scripts run with `python3 -I` (sqlite3 3.45.1, jsonschema 4.26.0, referencing). Scripts are in the session scratchpad under `p5c/` (`sm.py`, `ddl.py`, `trg.py`, `happy.py`, `schemas.py`, `refs.py`). They are not committed |
| Status | In progress (written section by section) |

Finding IDs are `VC-nn`. Severity follows the Phase 5 common instructions. "Fixed in place" means the fix was applied in a file Agent C owns (state-machine, components, messages, schemas) during this validation.

---

## 1. Lifecycle determinism (state-machine §3)

**Method.** `sm.py` parses every row of the §3 tables (T01–T43, G1a–G6: 53 rows). It splits multi-event cells (`a / b`), expands set-valued sources (`any non-terminal`, `any work or gate state`, `X … Y` ranges in §1.2 order, explicit lists), and builds a matrix of 17 states × 53 events, i.e. 128 (state, event) entries. It then reports pairs with more than one rule, reachability from `∅`, and non-terminal states without exits. Pairs with no rule are rejected by the engine: `TransitionEngine.applyInTx` returns `no_rule` (components §4.4, §10.2), so a missing pair is an explicit rejection, not undefined behaviour. The open question is whether the rejection is the *intended* outcome.

**Results (before the fixes in this section).**

| Check | Result |
|---|---|
| Unreachable states | none: all 17 are reachable from T01 |
| Non-terminal states with no exit | none |
| Terminal states with exits | none (also enforced by `trg_tasks_terminal_final`, INV-08) |
| (state, event) pairs with more than one rule | 2: `(CLAUDE_PR_REVIEW, pr_review.passed)` → T24 / T24p; `(BLOCKED, operator.cancel)` → T38 / G1b |
| Every row has an initiator and a guard cell | yes (53/53), see §2 |

PR-event coverage per state (from the matrix; `-` = `no_rule`):

| State | `pr.merged` | `pr.foreign_push` | `pr.closed_by_other` | `pr.closed_by_operator` | `human_review.changes_requested` |
|---|---|---|---|---|---|
| `PLANNING`, `AWAITING_PLAN_REVIEW`, `PLAN_REVISION_REQUESTED`, `PLAN_APPROVED` (with a PR, after G4/T17/T30) | - | - | - | - | - |
| `IMPLEMENTING`, `TESTING`, `CHANGES_REQUESTED` | G3 | - | G6 | - | - |
| `PR_OPEN`, `CLAUDE_PR_REVIEW` | G3 | G5 | G6 | - | - |
| `AWAITING_HUMAN_APPROVAL` | T31 | G5 | G6 | T33 | T32 |
| `BLOCKED` (with PR) | G3 | - | - | - | - |

### Findings

**VC-01 (Medium) T24/T24p share `(from, event)`; SM §11 says rule lookup is by `(from, event)`.** The two rules are separated only by the policy guard (§8.7), and components §10.5 picks the rule explicitly (`policyGuard(...).ok ? T24 : T24p`), so behaviour is deterministic. But the engine contract does not say how a second rule on the same key is chosen, and the documentation-drift test (§11) would encode an ambiguous table. T38 and G1b are identical in effect (BLOCKED → CANCELLED, cancel protocol). *Fixed in place:* SM §11 now says that a `(from, event)` key may carry more than one rule only when their discriminating guards are complementary (T24/T24p: policy guard clear / open escalation), that the engine evaluates them in table order and applies the first one whose discriminating guard holds, and that `ruleHint` must agree with that choice. T38 is the BLOCKED-specific row of G1b (same effects).

**VC-02 (Medium) PR-scoped global transitions do not cover every state in which a PR exists.** The §2.2 diagram says G3/G5/G6 apply to "any state where a PR exists", but the §3.7 table lists explicit states. After G4, T17 or T30 a task re-enters the planning states with its PR still open (G4 sets CR `action_required`; it does not close the PR). `pr.closed_by_operator` is handled only in `AWAITING_HUMAN_APPROVAL` (T33). In `PR_OPEN`, `CLAUDE_PR_REVIEW` and `CHANGES_REQUESTED` an operator who closes the PR gets `no_rule`, and the inbox marks the fact processed. The task keeps working on a closed PR until `github.pr.upsert` reconciles a closed PR (components §10.7: "inbox routes to G6 / T33"), which again finds no rule. A foreign push in `IMPLEMENTING`/`TESTING`/`CHANGES_REQUESTED` is caught later by the push compare-and-set (github.md §4.3) and then by G5 from `PR_OPEN`, so it is safe but implicit. A merge in a planning state is blocked by the required CR check, but G3 is meant as the defensive path. *Fixed in place:* G3, G5 and G6 now apply to every non-terminal state except `MERGED` while `pull_requests.state = open` (G5 and G6 also exclude `BLOCKED`, where the fact is recorded and the resume guards of §6.3 re-check head and PR state). A new row **G7** sends `pr.closed_by_operator` from every with-PR state other than `AWAITING_HUMAN_APPROVAL` (T33) to `CANCELLED` with `cancel_reason = pr_closed_by_human`. §3.7 also states the rule for facts with no matching rule: the inbox records them `ignored` with outcome `no_rule`, and the level snapshot keeps the observed value so the guards of the next state see it.

**VC-03 (Medium) Operator cancel or Claude revoke is allowed from `MERGED`.** G1a/G1b apply to "any non-terminal" state, which includes `MERGED` (only G1c excludes it). Cancelling a merged task would skip merge verification M1–M8 and leave merged, unverified code recorded as `CANCELLED`. That defeats the detective control under G-DETECT. If verification stalls, the §7.3 timer already produces `BLOCKED(external_state_conflict)`, and from `BLOCKED` cancel is allowed after a human has looked. *Fixed in place:* G1a and G1b now read "any non-terminal except `MERGED`".

**VC-04 (Medium) G2 (`guard.failed`) is not defined from decision points or `AWAITING_HUMAN_APPROVAL`.** T12, T28, T42 and T37 evaluate the authorization guard, and the review-binding recon (INV-06) runs on every poll in `AWAITING_HUMAN_APPROVAL`. Also `linear.delegate_changed → G2(foreign_agent)` (components §10.9) can arrive in any state. Today a `fail(...)` result in those states has no rule. *Fixed in place:* G2's source set is now "any work, gate or decision-point state, or `AWAITING_HUMAN_APPROVAL`".

**VC-05 (Medium) `amend_scope` while a plan awaits review leaves the task stuck.** §8.1.1 says that pre-plan states release the hold and that G4 applies from `PLAN_APPROVED` on. In `AWAITING_PLAN_REVIEW` the stored plan carries the old `scope_version`. The next review run is claimed under the new authorization version, so AG@apply does not discard it. On `approve`, components §10.4 inserts `plan_approvals.scope_version = a.scope_version` (new). `trg_plan_approvals_binding` requires `p.scope_version = NEW.scope_version` (old), so it aborts the transaction, including the run finish. The run is then re-finalized every tick (a livelock). Even without the trigger, approvalGuard (§8.2) would fail at T14 with `guard_integrity_failure`, a security block that allows only cancel or abandon. *Fixed in place:* G4 now also applies from `AWAITING_PLAN_REVIEW` (`AWAITING_PLAN_REVIEW`, `PLAN_APPROVED` … `AWAITING_HUMAN_APPROVAL`), and §8.1.1 lists the pre-plan states explicitly (`AUTHORIZED`, `PLANNING`, `PLAN_REVISION_REQUESTED`: release the hold; a `PLANNING` run's deferred result is discarded and the dispatcher re-runs planning under the new version). The §2.2 diagram and components §10.3 `POSTPLAN` were updated to match.

**VC-06 (Low) Re-authorization outcomes from `BLOCKED` are incomplete.** T37 accepts the reasons `reauthorization_required` and `needs_human_decision` (from a re-authorization), but components §10.3 applies T37 only for `reauthorization_required`. `amend_scope` decided while the task is `BLOCKED` has no rule. *Fixed in place:* components §10.3 applies T37 for both reasons named in its guard. SM §8.1.1 now says that `amend_scope` from `BLOCKED` records the new version and sets `resume_state = PLAN_REVISION_REQUESTED` when `blocked_from_state` is at or after `AWAITING_PLAN_REVIEW` (the operator then resumes; T36 re-checks every guard).

**VC-07 (Low) An operator `CHANGES_REQUESTED` review submitted before `AWAITING_HUMAN_APPROVAL` is only recorded.** components §10.9 acts on it only in `AWAITING_HUMAN_APPROVAL`, and the T32 guard ("on the current head") is not re-evaluated when the state is entered. Because the PR is a draft until T24, this is unusual, and GitHub still holds the changes-requested review against the merge, so it is safe. *Fixed in place:* entering `AWAITING_HUMAN_APPROVAL` (T24, T42) now evaluates T32 against stored `github_reviews` on the current head.

---

## 2. Initiator and authorization rule for every transition

**Method.** `sm.py` checks that the Initiator cell of each of the 53 rows is non-empty and that each initiator maps to a `core/states.ts` `Initiator` kind. Each ★ method was traced to the components §5.2/§5.4 principal table and to INV-22.

**Result: pass.** Every row names an initiator from {Claude, Codex-result, Coordinator, Operator, Operator★, GitHub, Linear}, and each maps to an `Initiator.kind` (`operator_presence` for ★). Authorization rules:

- Claude rows require a validated decision run (V1–V4 plus the model-used check) and DecisionRecorder recording, enforced by the INV-18 triggers.
- Codex-result rows require AG@apply.
- Operator rows require a socket principal (§5.2).
- ★ rows (T36 for ★ reasons, T40, T42, `grant`, `unhalt`, `restore --confirm`) require `operator_presence`. INV-19 makes the engine reject an `operator` initiator on a ★ rule (`initiator_not_allowed`).
- GitHub and Linear rows require a dedup-keyed inbox fact. INV-17 limits Linear to cancel, hold and release.

Two mixed rows use "Claude / Coordinator" (T11, T26, T13, T29) or "Codex-result + Coordinator" (T15, T22). Their initiator lists are sets, which `TransitionRule.initiators: Initiator[]` supports.

**VC-08 (Low) The INV-22 DB backstop covers only `policy_acks`.** The components §6.3 comment says "policy acks and grants reference a presence control request", but only `trg_policy_ack_presence` exists. `budget_grants` and `merge_verifications(result = waived)` (T40) have no equivalent trigger. *Fixed in place:* added `trg_budget_grant_presence` and `trg_mvf_waiver_presence` to §6.4 with the same predicate.

---
## 3. Referenced tables, columns and triggers exist in components §6 DDL

**Method.** `ddl.py` extracts the two `sql` fences of components §6.3–§6.4, loads them into an in-memory SQLite, and dumps every table, column, trigger and index to `schema.json`. `refs.py` then scans state-machine, recovery, github, threat-model, verification-plan, components, linear, claude, codex and macos-service for:

- `table.column` tokens whose table exists;
- `trg_*`, `ux_*`, `ix_*` names;
- withdrawn alias names (`jobs`, `inbound_events`, `outbound_ops`, `side_effects`, `agent_runs`, `instance_lease`, `audit_events`);
- backticked snake_case identifiers that look like table names.

The github.md outbox ops and the GH-DEDUP §13.3 catalogue were compared row by row with components §4.14, and M1–M8 with `merge_verifications`.

**Results.**

| Source | Resolved references | Not found in DDL | Assessment |
|---|---|---|---|
| state-machine.md | 30 `table.column`; every table named in guards and effects (`tasks`, `runs`, `authorizations`, `operator_revocations`, `plans`, `plan_reviews`, `plan_approvals`, `pr_reviews`, `github_reviews`, `findings`, `revision_requests`, `test_results`, `policy_escalations`, `policy_acks`, `merge_verifications`, `budget_grants`, `holds`, `outbox`, `messages`, `events_inbox`, `linear_issues`, `issue_relations`, `pull_requests`, `gate_checks`, `orphan_remote_objects`, `control_requests`) | none | pass |
| recovery.md | all tables; outbox status aliases `failed`/`abandoned` are mapped by a DDL comment | none | pass |
| github.md | `events_inbox`, `outbox`, `observation_seqs`, `pull_requests.local_head_sha`, `tasks.last_commit_sha`; M2–M8 → `merge_verifications.m2_…m8_*`; M1 is the precondition (merge observed) and M4's `last_reviewed_head_sha` → `head_sha_reviewed` | none (one false positive: the file name `messages.md`) | pass |
| threat-model.md, verification-plan.md | table names in prose only (`audit_log`, `anchors`, `audit_epochs`, `control_requests`, `holds`, …) | none | pass |
| codex.md | `tasks.codex_*_thread_id` | **`runs.codex_thread_id`** (codex.md §3, line 98). The DDL stores the thread id in `runs.session_id` and `tasks.codex_{plan,impl}_thread_id` | **VC-11** |
| macos-service.md, linear.md | `instance_lease` (only in "No `instance_lease` row"); `outbox.pending_escalation`, `runs.retention_d`, `snapshots.retention_h` are parameter names, not columns | none | pass |
| Triggers and indexes named anywhere (`ux_tasks_active_issue`, `ux_runs_active_mutating`, `ux_runs_active_kind`, …) | all exist | none | pass |
| GH-DEDUP outbound keys vs components §4.14 ops | all ops present except two keys without an op | `out:gh:pr:body:*`, `out:ops:heartbeat:*` | **VC-12** |

**VC-11 (Low, report to Agent B).** codex.md names a non-existent column `runs.codex_thread_id`. *Proposed fix:* replace it with `runs.session_id`.

**VC-12 (Low) Two GH-DEDUP outbound keys had no op in the components §4.14 catalogue.** *Fixed in place:* added the `ops.heartbeat` op, and stated that `github.pr.upsert` uses the PR-body key when it updates the body.

---

## 4. DDL is valid SQLite

**Method.**

- `ddl.py` runs the extracted DDL with `executescript` and then statement by statement (using `sqlite3.complete_statement`). It also checks every foreign-key target table and column.
- Because SQLite does not resolve names in trigger bodies at `CREATE TRIGGER` time (shown with a deliberately bogus trigger: the CREATE succeeds and the error appears only at prepare), `trg.py` compiles every trigger program by preparing a zero-row `INSERT … SELECT … WHERE 0`, `UPDATE … WHERE 0` or `DELETE … WHERE 0` on its table.
- `happy.py` drives one task with `foreign_keys = ON` through T01 → T02 → T05 → T06 → T09 → T14, a same-scope re-authorization (v2), a PR review insert and two audit-chain rows. It also runs six negative probes.

**Results (after the §1–§2 fixes).**

| Check | Result |
|---|---|
| Statements | 97 parsed and executed, 0 errors (SQLite 3.45.1) |
| Objects | 44 tables, 26 triggers, 27 explicit indexes |
| Foreign keys | every `REFERENCES` target table and column exists; `PRAGMA foreign_key_check` empty |
| Trigger bodies | 26/26 compile (no unknown table or column) |
| Happy path | 9/9 steps pass with all INV triggers active |
| Negative probes | each rejected by the intended trigger: state change without transition row (INV-07); implementation run with a wrong approval (INV-04); UPDATE of `authorizations` (INV-13); Codex run under a superseded authorization version (INV-03); broken audit chain |

**VC-13 (Low) Several triggers are specified as "one pair per table, generated by the migration" but only one instance is written out.** The append-only pair is written for `authorizations` only, and the vocabulary trigger for `holds.kind` only. The generation rule names the tables and columns explicitly, so this is implementable without guessing. The DDL block cannot be executed as the complete migration, though, and SMT/CT tests must assert the generated set. *Proposed (not changed):* M1 issue MERC acceptance criteria should require a test that lists `sqlite_master` triggers and compares them with the INV-13 table list and the 8 vocabulary columns.

**UNVERIFIABLE IN DESIGN.** Behaviour under `node:sqlite` (Node 24) rather than CPython's SQLite build; `fullfsync` and `checkpoint_fullfsync` on APFS (Phase 0 P0-0xx, ASM-C-01).

---

## 5. JSON Schemas after Phase 4

**Method (`schemas.py`).**

1. Metaschema check of all 26 files (Draft 2020-12 for messages, Draft-07 for `output.*`).
2. Resolution of all 153 `$ref`s through a `referencing` registry keyed by `$id` and file name.
3. Strict-subset lint of the 8 output contracts: closed objects, `required` = all properties, `enum` with `type`, bounded strings and arrays, no `$ref`/`oneOf`/`anyOf`/`allOf`/`if`/`const`/`not`.
4. Bounds lint of the message schemas.
5. Fixtures: a generator builds a maximal instance (every property, minimum arrays, regex-derived strings) for each of the 25 non-`common` schemas and validates it with `FormatChecker`. It then checks that an unknown top-level field and an unknown `payload` field are rejected.

There are no fixture files in the repository: the generated fixtures are in the scratchpad `p5c/fixtures/`.

| Check | Result |
|---|---|
| Metaschema | 26/26 pass |
| `$ref` resolution | 153/153 resolve |
| Strict subset (output contracts) | 8/8 pass |
| Generated fixtures valid | 25/25 |
| Unknown fields rejected | every message schema rejects unknown top-level and payload fields (`allOf` envelope + `unevaluatedProperties: false`). `envelope.schema.json` alone is open by design (base schema) |
| Bounds | one unbounded string: `task.failed.payload.notification_kind` |
| Cross-schema vocabularies | `decision` ∈ {approve, revise, reject, needs_human} is identical in `output.plan_review`, `output.code_review`, `output.security_review`, the three message schemas and the DDL `CHECK`s; finding severities agree with `findings.severity` |

**VC-14 (Low) `task.failed` schema details.** `notification_kind` is unbounded and has no vocabulary. `allowed_actions` has `maxItems: 10` while its enum (and `presence_required_actions`, `maxItems: 14`, documented as a subset of it) has 14 values. *Fixed in place:* `notification_kind` now has `maxLength: 64` and pattern `^[a-z_]{3,64}$`; `allowed_actions.maxItems` is 14.

---

## 6. Every component interface used in pseudocode is defined

**Method.** A script extracts every `object.method(` call in components §10 and checks it against the TypeScript interfaces and tables of §4–§5. `tx.<repo>.<method>` calls are checked against the repository list of §4.3.

**Result before fixes.** 34 calls resolve. The rest fall into three groups:

- **Repositories used in §10 but missing from the §4.3 list:** `transitions`, `controlRequests`, `gateChecks`, `instances`, `leases`, `facts`.
- **Service methods called but not declared:** `Store.open`, `CredentialBroker.loadOnce`, `HoldService.set`/`release` (non-transactional), `RunManager.markDeferredReady`, `GitHubPoller`/`LinearPoller.fullReconcile`, `pollers.scheduleImmediateFullReconcile`, `Clock.monoNowMs`, `powerHelper.reportedAwakeThroughout`, `Supervisor.loop`/`loopSafe`. The Clock, Poller and power-helper ports had no interface at all; the Clock port had only its fake's capabilities (§14.1).
- **A column that does not exist:** §10.5 read `run.scope_version`, but `runs` has no such column.

**VC-09 (Low) Interface gaps.** *Fixed in place:* §4.3 now lists every repository used in §10 and states that repository methods are thin single-statement wrappers. `Store.open`, `HoldService.set`/`release`, `RunManager.markDeferredReady` and `CredentialBroker.loadOnce`/`reload` are declared. §4.17 adds `Clock`, `GitHubPoller`/`LinearPoller`, `InboxProcessor`, `PowerHelperClient` and the Supervisor internals.

**VC-10 (Low) §10.5 used a non-existent `runs.scope_version`.** *Fixed in place:* the review's `scope_version` is now read from the authorization version recorded on the review run at claim.

---
