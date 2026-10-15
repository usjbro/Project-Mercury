# Examples — contracts, results and a complete ledger

| File | Validation (reproduce with the commands below) |
|---|---|
| `contract-implementation.json` | `devorch.py check-contract` → VALID (full JSON Schema mode) |
| `contract-code-review.json` | VALID; `review_target` binds the review to `main..2a4b6c8…` |
| `result-implementation.json`, `result-review-changes-required.json`, `result-escalation.json` | Schema-valid (jsonschema Draft 2020-12) |
| `ledger-DT-0001.jsonl` | 14 hash-chained records: `created` → … → `code_review_changes_required` (correction loop) → `tests_passed` → G3 → G4 → G5 → G6 → `human_merged` (G7) → `closed`; `devorch.py verify-ledger` → `ledger OK` |

The SHAs in the result examples are illustrative, so `check-result` against a real repository would correctly reject them (commits do not exist).

**Rejection behaviour.** Checked on 2026-10-15 in a scratch repository: `check-result` returned INVALID for a commit touching a file outside `allowed_paths`, and for `modified_files` not matching `git diff`. `record` refused `pr_prepared` from `AWAITING_REVIEW`, and refused entry to AWAITING_INTEGRATION without G4 for a security-sensitive contract. `verify-ledger` reported "hash, transition" for a tampered record.

**Correction attempts.** Before re-dispatching a correction, the orchestrator increments `attempt` in `$DEVORCH_HOME/tasks/<task>.json`. The contract version is unchanged unless scope changed.

```bash
export DEVORCH_HOME=$(mktemp -d); mkdir -p $DEVORCH_HOME/tasks
T=tools/devorch/devorch.py; EX=docs/mercury/development-orchestration/examples
python3 $T check-contract $EX/contract-implementation.json
cp $EX/contract-implementation.json $DEVORCH_HOME/tasks/DT-0001.json
mkdir -p $DEVORCH_HOME/ledger && cp $EX/ledger-DT-0001.jsonl $DEVORCH_HOME/ledger/DT-0001.jsonl
python3 $T verify-ledger && python3 $T status
```
