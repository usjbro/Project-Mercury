# 04 — Agent Input and Output Contracts

| Contract | Schema (JSON Schema 2020-12) | Written by | Validated by |
|---|---|---|---|
| Task contract `devorch.task_contract.v1` | `schemas/task-contract.schema.json` | Orchestrator, in `$DEVORCH_HOME/tasks/<task_id>.json` | `devorch.py check-contract` before dispatch |
| Task result `devorch.task_result.v1` | `schemas/task-result.schema.json` | Specialist: `<evidence_dir>/result.json`, repeated as the final fenced JSON block | `devorch.py check-result <result> <contract>` |
| Handoff record `devorch.handoff.v1` | `schemas/handoff-record.schema.json` | `devorch.py record` only (`actor` principal-orchestrator or operator) | `devorch.py record` and `verify-ledger` (same transition rules, hash chain) |

Full validation needs `jsonschema` (pinned `jsonschema==4.26.0`); without it devorch runs structural checks only and says so in its output (`validation mode`).

**Not production schemas.** These contracts are deliberately disjoint from `docs/mercury/protocols/schemas/` (`mercury.*.v1`):

- different `schema` ids and fields;
- no shared identities;
- no authority over MERCURY's runtime.

Reusing production schemas would blur the two systems (separation rule S1).

## 1. Task contract — fields beyond the brief's conceptual contract

| Field | Why |
|---|---|
| `schema`, `contract_version` | Versioning. A revised contract invalidates results and gates of earlier versions |
| `kind` | Selects lifecycle (full or short, `01-…` §5), the assigned agent (`03-…` §1) and validation rules |
| `merc_issue` | Traceability to `planning/issue-breakdown.md`, and uniqueness: one active primary task per MERC issue. `null` for every subtask |
| `parent_task_id` | Review subtasks (`code_review`, `security_review`, `design_review`, `reliability_review`): the task they review. Ids `DT-nnnn-rN` (code/design/reliability review) and `DT-nnnn-sN` (security review) |
| `covers_tasks` | Integration subtasks: the task ids integrated. The id is `<first covers_tasks entry>-iN`; `check-contract` enforces this id convention for every subtask kind |
| `required_gates`, `mercury_gates`, `security_sensitive` | Gate enforcement (`08-…`). `mercury_gates` (G-S1…5, P0-n, SAC-n) is a copy for the specialist's information; `devorch.py ready` enforces the TDD gates from `assignments.json` `_tdd_gates` and the issue `Gates` field as operator facts, not from this field |
| `required_reviewers` | G3 needs a passed subtask of the matching review kind for each listed reviewer |
| `allowed_paths` | Globs relative to the repo root (`minItems: 0`). **`[]` for read-only kinds**: all review kinds, `planning`, `mac_validation`, `operator_action` |
| `branch` | Pattern `^dev/(merc-<id>\|dt-<nnnn>)-<slug>$`, slug `[a-z0-9-]{1,40}` (`06-…` §2) |
| `evidence_dir` | Absolute path **outside `$DEVORCH_HOME`**: `$DEVORCH_EVIDENCE/<task_id>/attempt-<N>/`. The only path outside the worktree an agent may write |
| `attempt` | 1…50; with `evidence_dir`, the only per-attempt fields (below) |
| `budget` | `max_attempts` (1…5), `max_turns`, `max_wall_minutes`, optional `max_cost_usd`. Loop limits (review 3, security 2, integration 2, env 5) are fixed in the tool |
| `review_target` | Required for review kinds. Binds a review to an exact `implementation_task_id`, `base_commit..head_commit`. A new head invalidates the review |
| `created_by` = `principal-orchestrator` | Only the orchestrator issues contracts |

`approved_design_refs` entries use the form `path§section@<commit>`, so the design version is pinned.

**Contract core.** Every ledger record carries `contract_core_sha256`: the SHA-256 of the canonical JSON of the contract **without** the per-attempt fields `status`, `attempt` and `evidence_dir` (`CONTRACT_MUTABLE` in `devorch.py`). Convention: on each correction attempt the orchestrator increments `attempt` and sets `evidence_dir` to `$DEVORCH_EVIDENCE/<task_id>/attempt-<N>` together. Any other field change alters the core and is accepted only with a `contract_revised` record (and a higher `contract_version`); `record` and `verify-ledger` refuse a core change without it.

## 2. Task result — mandatory content

The brief's list maps onto these fields:

| Brief item | Field |
|---|---|
| Task identifier | `task_id`, `contract_version`, `attempt` (1…50) |
| Execution status | `status` |
| Summary of completed work | `summary` |
| Modified files | `modified_files` |
| Commit identifiers | `commits`, `head_commit` |
| Test commands and outcomes | `tests[]` (with exit codes) |
| Discovered defects | `defects[]` |
| Outstanding dependencies | `outstanding_dependencies[]` |
| Blocking conditions | `blocking_conditions[]` |
| Recommended next action | `recommended_next_action` |
| Evidence references | `evidence_refs[]` (file paths under `evidence_dir`) |

Reviews add `findings[]`, `recommendation`, `gate_result` and **`reviewed_head_commit`** (must equal `review_target.head_commit`). Integration results add **`integrated_heads`**: one `DT-nnnn@<40-hex sha>` entry per covered task. Escalations add `escalation`. `usage` feeds cost tracking.

## 3. Handoff record

Required: `schema`, `seq`, `task_id`, `at`, `event`, `from_state`, `to_state`, `actor`, `evidence[]` (≥ 1), `prev_hash`, `hash`, `contract_core_sha256`. Optional: `contract_version`, `attempt`, `gate`, `note`, and:

| Field | Use |
|---|---|
| `actor` | `principal-orchestrator` or `operator`. Agents never write the ledger |
| `head_commit` | Required on `tests_passed` (G2, the tested tip), `pr_prepared` (G6) and `human_merged` (G7) |
| `session` | Agent session id on `dispatched` |
| `frozen_files` | `{path: sha256}`, required on `interface_frozen` |
| `contract_core_sha256` | See §1 |

`event` includes `dispatched`, `env_retry` and `result_accepted` (short-lifecycle completion) in addition to the gate events of `01-…` §5. Evidence `kind` ∈ `ci_run, commit, design_ref, github_merge, ledger, log, operator_statement, pr, result_file, review_file, subtask, test_run`; `subtask` names a COMPLETED review or integration subtask for G3/G4/G5. File evidence (`result_file`, `review_file`, `test_run`, `log`) gets its `sha256` computed by `record`.

**Canonical JSON.** Records are hashed over `json.dumps(record without "hash", sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, chained per task via `prev_hash` (`GENESIS` for seq 1). The same serialization computes `contract_core_sha256`. This is documented canonical JSON, **not** RFC 8785.

## 4. Validation rules (malformed or incomplete output never advances state)

**`check-contract`** rejects a contract when:

1. It fails the schema.
2. `worktree` or `evidence_dir` is not absolute, or `evidence_dir` lies inside `$DEVORCH_HOME`.
3. `assigned_agent` does not match the kind → agent map (`03-…` §1).
4. A subtask has a `merc_issue`; a review subtask lacks `parent_task_id`; an integration subtask lacks `covers_tasks`; a review kind lacks `review_target`.
5. A read-only kind has non-empty `allowed_paths`.
6. An `allowed_paths` entry falls inside `restricted_paths`.
7. Its `allowed_paths` overlap (conservative literal-prefix test) those of an active primary task in RUNNING, AWAITING_REVIEW, AWAITING_INTEGRATION or **AWAITING_HUMAN** (subtasks and read-only kinds are not owners).

**`check-result`** first validates the contract (an invalid contract fails the check), then rejects the result when any of these holds:

1. It fails the schema.
2. Its `task_id`, `contract_version` or `attempt` doesn't match the contract, or `agent` isn't the assigned agent.
3. It was not read from `<evidence_dir>/result.json` (only `--allow-copy`, for tests and examples, relaxes this).
4. `base_commit` isn't an ancestor of the task branch tip.
5. **Writing kinds:** the worktree has uncommitted or untracked changes; worktree `HEAD` ≠ branch tip; `head_commit` ≠ tip; `commits` ≠ `git rev-list base..tip` (so an empty commit cannot be hidden); `modified_files` ≠ `git diff --no-renames --name-only base..tip` (so a rename out of a restricted path shows both sides); a changed file is outside `allowed_paths` or inside `restricted_paths`.
6. **Integration:** the effective scope is its own `allowed_paths` plus those of every task in `covers_tasks`; `integrated_heads` must name every covered task, each head must be contained in the integration tip and equal that task's tested (G2) head.
7. **Read-only kinds:** commits are reported, the branch moved off `review_target.head_commit`, or the worktree was modified.
8. **Review kinds:** `reviewed_head_commit` ≠ `review_target.head_commit`; no `recommendation`; `accept`/`accept_with_conditions` with a blocking finding or a failing required test; a completed review that omits a required test's outcome.
9. Other completed kinds (except `planning`, `mac_validation`, `operator_action`): a required test isn't reported as passed with exit code 0.
10. `status: escalated` has no `escalation` object.

Globs use git-like semantics: `**/` matches zero or more directories, `**` anything, `*` and `?` never match `/`.

`record` runs the same checks live for `implementation_completed` and `result_accepted` (except `mac_validation` / `operator_action`, which need operator evidence) and additionally requires result `status: completed`.

A VALID result only lets the orchestrator import the evidence (`devorch.py import-evidence`, copied with a `MANIFEST.json` into `$DEVORCH_HOME/evidence/<task>/attempt-N/`) and begin gate verification; it is never itself a gate. Gate binding at record time (subtask COMPLETED, `reviewed_head_commit` and `integrated_heads` equal to the parent's tested head) is described in `01-…` §5 and `08-…`. Rejections are demonstrated in `examples/README.md` and `tools/devorch/test_devorch.py`.

## 5. Examples

| File | Shows |
|---|---|
| `examples/contract-implementation.json` | MERC-101 implementation by the Backend Engineer (security-sensitive, three required tests) |
| `examples/contract-code-review.json` | Code review subtask `DT-0001-r1` bound to the tested head of attempt 1 |
| `examples/contract-integration.json` | Integration subtask `DT-0001-i1` covering DT-0001 |
| `examples/result-implementation.json` | The accepted attempt-2 implementation result |
| `examples/result-review-changes-required.json` | A blocking review finding that sent DT-0001 back to RUNNING |
| `examples/result-integration.json` | Integration result with `integrated_heads` |
| `examples/result-escalation.json` | Escalation for a design change (hand-written, schema-checked) |
| `examples/ledger-DT-0001*.jsonl` | The hash-chained ledgers of the task and its four subtasks, from `created` to `closed` |

All files except `result-escalation.json` are produced by `tools/devorch/gen_examples.py` running devorch itself, so they cannot drift from the tool. Evidence for the examples: `examples/README.md`.
