# Examples — contracts, results and ledgers (devorch v2)

Every file here except `result-escalation.json` is **generated** by `tools/devorch/gen_examples.py`. The generator runs a real devorch v2 scenario in a scratch repository, using `check-contract`, `check-result` and `record`, then copies the outputs here. Paths (`/tmp/devorch-test-…`), commit SHAs and timestamps come from that run. The structure and the rules applied are those of the tool at the commit that generated them.

```bash
python3 tools/devorch/gen_examples.py --check   # replay the scenario, write nothing
python3 tools/devorch/gen_examples.py           # regenerate this directory
python3 tools/devorch/test_devorch.py -v        # 23 regression tests (rejection behaviour)
```

`DEVORCH_TEST_MODE=1` (set by the generator and the tests) skips **only** the check that `DEVORCH_HOME` is a worktree of `devorch/state`. All other rules apply unchanged.

## Scenario: DT-0001 = MERC-101, with one correction loop

| Seq | Event | State | Gate | Attempt |
|---|---|---|---|---|
| 1 | `created` | → BLOCKED | | 1 |
| 2 | `unblocked` (three `design_ref` evidence items) | → READY | G1 | 1 |
| 3–4 | `assigned`, `dispatched` (session) | → RUNNING | | 1 |
| 5 | `implementation_completed` (record re-ran check-result: VALID) | RUNNING | | 1 |
| 6 | `tests_passed` (orchestrator re-run, `head_commit` recorded) | → AWAITING_REVIEW | G2 | 1 |
| 7 | `code_review_changes_required`: review `DT-0001-r1` found blocking finding CR-DT0001-01 | → RUNNING (G2 cleared) | | 1 |
| 8–9 | `dispatched`, `implementation_completed`: correction attempt; only `attempt` and `evidence_dir` changed, so the contract core hash is unchanged | RUNNING | | 2 |
| 10 | `tests_passed` on the new head | → AWAITING_REVIEW | G2 | 2 |
| 11 | `code_review_passed`, evidence `subtask:DT-0001-r2` (bound to the new head) | AWAITING_REVIEW | G3 | 2 |
| 12 | `security_review_passed`, evidence `subtask:DT-0001-s1` | → AWAITING_INTEGRATION | G4 | 2 |
| 13 | `integration_verified`, evidence `subtask:DT-0001-i1` (`integrated_heads` = tested head) | AWAITING_INTEGRATION | G5 | 2 |
| 14 | `pr_prepared` (PR URL placeholder, head = tested head) | → AWAITING_HUMAN | G6 | 2 |
| 15 | `human_merged` (`github_merge` evidence placeholder, head = G6 head) | → COMPLETED | G7 | 2 |
| 16 | `closed` | COMPLETED | | 2 |

Each subtask ledger (`ledger-DT-0001-{r1,r2,s1,i1}.jsonl`) is the short lifecycle: `created` → `unblocked` (G1) → `assigned` → `result_accepted` (record re-ran check-result).

## Files

| File | What it shows |
|---|---|
| `contract-implementation.json` | The MERC-101 contract as it stands at attempt 2 (`evidence_dir` …/attempt-2) |
| `contract-code-review.json` | Review subtask `DT-0001-r1`: `parent_task_id`, `review_target` at the attempt-1 head, `allowed_paths []`, `merc_issue null` |
| `contract-integration.json` | Integration subtask `DT-0001-i1` with `covers_tasks` and a local `dev/dt-0001-int-w1-1` branch |
| `result-implementation.json` | Attempt-2 result: commits, modified_files and tests equal git and the contract |
| `result-review-changes-required.json` | A `changes_required` review with `reviewed_head_commit` and a blocking finding |
| `result-integration.json` | Integration result with `integrated_heads` `"DT-0001@<sha>"` |
| `result-escalation.json` | Hand-written escalation for a design change; schema-valid (Draft 2020-12), not part of the scenario |
| `ledger-*.jsonl` | Hash-chained `devorch.handoff.v1` records; each carries `contract_core_sha256` |
| `status.txt` | `devorch.py status` at the end of the scenario |

All `.json` files validate against `../schemas/` (jsonschema 4.26.0, Draft 2020-12), and every ledger record validates against `handoff-record.schema.json`. The generator ends with `verify-ledger`, which replays every record through the same transition and gate rules as `record`.

The PR URL (`github.com/OWNER/REPO/pull/1`) and `merged_by=<repository owner>` are placeholders. A real G7 is recorded only after the orchestrator reads the merge from GitHub.

**Rejection behaviour** is covered by the regression tests rather than these examples. The tests cover:
- an empty-commit or rename hiding a restricted change, and a dirty worktree;
- a skipped G4, a review of a stale head, a forged actor, and a forged or replayed ledger;
- contract tampering, review and attempt budgets, and duplicate gates;
- an integration result claiming a head it does not contain;
- `evidence_dir` inside `DEVORCH_HOME`, and path-ownership conflicts.
