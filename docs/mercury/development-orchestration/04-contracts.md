# 04 — Agent Input and Output Contracts

| Contract | Schema (JSON Schema 2020-12) | Written by | Validated by |
|---|---|---|---|
| Task contract `devorch.task_contract.v1` | `schemas/task-contract.schema.json` | Orchestrator | `devorch.py check-contract` before dispatch |
| Task result `devorch.task_result.v1` | `schemas/task-result.schema.json` | Specialist (final fenced JSON block) | `devorch.py check-result <result> <contract>` |
| Handoff record `devorch.handoff.v1` | `schemas/handoff-record.schema.json` | `devorch.py record` only | `devorch.py verify-ledger` (hash chain + legal transitions) |

**Not production schemas.** These contracts are deliberately disjoint from `docs/mercury/protocols/schemas/` (`mercury.*.v1`):

- different `schema` ids and fields;
- no shared identities;
- no authority over MERCURY's runtime.

Reusing production schemas would blur the two systems (separation rule S1).

## 1. Task contract — fields beyond the brief's conceptual contract

| Field | Why |
|---|---|
| `schema`, `contract_version` | Versioning. A revised contract invalidates results and gates of earlier versions |
| `kind` | Selects validation rules (e.g. review tasks need `review_target`) |
| `merc_issue` | Traceability to `planning/issue-breakdown.md`, and uniqueness: one active task per MERC issue |
| `required_gates`, `mercury_gates`, `security_sensitive` | Gate enforcement (`08-…`), including TDD G-S gates and P0 checks |
| `evidence_dir` | The only path outside the worktree an agent may write |
| `budget` (attempts, turns, wall minutes, optional cost) | Bounded work; retry budget |
| `review_target` | Binds a review to an exact `base..head` range. A new head commit invalidates the review |
| `created_by` = `principal-orchestrator` | Only the orchestrator issues contracts |

`approved_design_refs` entries use the form `path§section@<commit>`, so the design version is pinned.

## 2. Task result — mandatory content

The brief's list maps onto these fields:

| Brief item | Field |
|---|---|
| Task identifier | `task_id`, `contract_version`, `attempt` |
| Execution status | `status` |
| Summary of completed work | `summary` |
| Modified files | `modified_files` |
| Commit identifiers | `commits`, `head_commit` |
| Test commands and outcomes | `tests[]` (with exit codes) |
| Discovered defects | `defects[]` |
| Outstanding dependencies | `outstanding_dependencies[]` |
| Blocking conditions | `blocking_conditions[]` |
| Recommended next action | `recommended_next_action` |
| Evidence references | `evidence_refs[]` |

Reviews add `findings[]`, `recommendation` and `gate_result`. Escalations add `escalation`. `usage` feeds cost tracking.

## 3. Validation rules (malformed or incomplete output never advances state)

`check-result` rejects a result when any of these holds:

1. It fails the schema.
2. Its `task_id`, `contract_version` or `attempt` doesn't match the contract.
3. The `agent` isn't the assigned agent.
4. `base_commit` isn't an ancestor of `head_commit`.
5. The task branch doesn't point at `head_commit`.
6. Any listed commit doesn't exist.
7. A changed file falls outside `allowed_paths`, or inside `restricted_paths`.
8. `modified_files` ≠ `git diff --name-only base..head`.
9. A required test isn't reported as passed with exit code 0.
10. `recommendation: accept` comes with blocking findings.
11. `status: escalated` has no `escalation` object.

A VALID result only allows the orchestrator to begin gate verification; it is never itself a gate. Rejections are demonstrated in `examples/README.md`.

## 4. Examples

| File | Shows |
|---|---|
| `examples/contract-implementation.json` | MERC-101 implementation by the Backend Engineer |
| `examples/contract-code-review.json` | Code review bound to the exact commit range |
| `examples/result-implementation.json` | A valid implementation result |
| `examples/result-review-changes-required.json` | A blocking review finding |
| `examples/result-escalation.json` | Escalation for a design change |
| `examples/ledger-DT-0001.jsonl` | A complete, hash-chained handoff history from `created` to `human_merged` |

All examples validate against the schemas. Evidence: `examples/README.md`.
