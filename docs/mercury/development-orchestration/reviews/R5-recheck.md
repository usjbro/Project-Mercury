# R5 — Independent re-check of the R0 fix round

Reviewers:
- `mdev-security-engineer` and `mdev-code-reviewer`, dispatched read-only on 2026-10-15 against commit `7a7e020`.
- Neither could run `tools/devorch/` (by design).
- The security reviewer reproduced N-02 and N-03 with git 2.43 in scratch repositories.

Verdicts: security **Not closed**; code/reliability **changes_required, not ready for live dispatch**.

This file records their findings and what was done about them. Section 2 reports the commit and test count of the fix.

## 1. Guard hook in live dispatch: FAILED

| Probe | Expected | Observed |
|---|---|---|
| Security reviewer ran `python3 tools/devorch/devorch.py --help` | Refused by the guard | **Ran.** The agent was loaded from a definition older than the hook (stale scope text, no `hooks:` block) |
| Code reviewer ran guard-matching commands, plus an `echo` canary containing `.netrc`, `tools/devorch/` and `git push` | Refused | **Ran.** `$CLAUDE_PROJECT_DIR` was unset; no hook ran |

This turns the earlier open item ("hooks firing in a live dispatch not verified") into a **known failure in the authoring session**. Consequences:
- **Live canary.** RB-D2 now requires a canary after every session start and every change to `.claude/agents/`.
- **Dispatch rule.** No specialist is dispatched for worktree tasks until the canary passes.
- **Operator decision DOD-10.** If a restart does not fix it, choose between a project-level hook in `settings.json` gated on agent type, or no Bash for implementing specialists.

The main session did not add a project-level hook itself: that changes session configuration and is the operator's call.

## 2. Findings and dispositions

Commit: the R5 fix commit on `claude/dev-orchestration`. `test_devorch.py`: **30/30 pass**. The six new R5 tests were also run against the pre-fix `devorch.py`, where all six fail.

| ID | Sev | Finding | Disposition | Test |
|---|---|---|---|---|
| N-01 / N0 | High/Crit | Guard hook not in effect | **Operator** (restart + canary, DOD-10). Tripwire only either way | RB-D2 canary |
| N-02 | High | A forged `.git` pointer or user git config (`core.fsmonitor`, credential helpers) runs commands in the orchestrator and spoofs refs | **Fixed.** `git()` runs with `core.fsmonitor=false`, `core.untrackedCache=false`, `protocol.ext.allow=never`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null` (user config only for push/fetch). `worktree_git()` checks that the `.git` pointer targets `<common>/worktrees/<name>` and points back, then all checks use explicit `--git-dir/--work-tree`. The baseline now covers `~/.gitconfig`, `~/.config/git/config`, `~/.claude/settings*.json` and git hook **contents**. The hook blocks `core.fsmonitor`, `GIT_DIR=`, `GIT_CONFIG*` and `.git` file writes | `test_forged_worktree_pointer_refused` |
| N-03 | High | A skip-worktree or assume-unchanged entry hides a committed change from status, tests and reviews | **Fixed.** `check-result` refuses hidden index entries. The G2 re-run and review subtasks use a **fresh detached checkout** created by the orchestrator. The hook blocks `update-index --skip-worktree/--assume-unchanged` | `test_skip_worktree_hidden_change_refused` |
| N-04 / N3 | High | Accepted results re-read from an agent-writable, unhashed file | **Fixed.** `record` reads each evidence file once, copies it to `$DEVORCH_HOME/evidence/<task>/records/` with its sha256, and refs that copy. `accepted_result` and replay verify the hash | `test_swapped_review_result_after_acceptance_refused` |
| N-05 / N2 | High | `verify-ledger` and `push` replayed without the live rules, so legal-looking forged records with fake subtasks verified | **Fixed.** `replay` applies the same checks as `record` by default: subtask binding, required reviewers, evidence hashes, and the contract file against the last record. `preflight` fetches `origin/devorch/state` before comparing. `verify-ledger --remote` reports ledgers deleted locally | `test_forged_legal_chain_with_fake_subtasks_fails_verify`, `test_contract_tamper_detected` |
| N-06 | High | Facts are self-asserted; DOD-02/03 preconditions were prompt-only | **Mechanical check fixed; authenticity Operator.** G1 (`record unblocked`), `ready` and `push` refuse full-lifecycle work without the `DOD-02` and `DOD-03` facts. **Residual:** `--actor operator` is self-asserted. Only a separate uid or signed facts make it authentic, so the operator reviews the `facts.jsonl` diff on `devorch/state` | `test_g1_requires_ready_including_hard_preconditions`, `test_push_requires_state_and_operator_facts` |
| N1 | High | G2 recordable without a checked result, or at a later head | **Fixed.** `tests_passed` requires a checked `implementation_completed` in the same attempt at the same head, and live, that the branch tip equals it. Integration also applies the covered tasks' `restricted_paths` | `test_g2_requires_checked_implementation_at_that_head` |
| N4 | High | Operator/Mac completion needed no operator | **Fixed (detective).** `result_accepted` for `mac_validation`/`operator_action` requires `actor operator` and a hashed evidence file | `test_short_lifecycle_operator_task_completes` |

**Code-review Medium items:**

| # | Item | Disposition |
|---|---|---|
| 1 | Hard preconditions | Now enforced (N-06) |
| 2 | G1 checked almost nothing | **Fixed:** `record unblocked` refuses unless the task is READY by the same `issue_blockers()` that `ready` uses (DAG deps, contract deps, frozen interface hashes, TDD gates, P0 facts, hard preconditions) |
| 3 | Revision version / attempt bump not enforced | **Fixed:** `contract_revised` needs a higher `contract_version`; a correction must be dispatched as attempt + 1 |
| 4 | G6 without CI | **Fixed:** `pr_prepared` needs `ci_run` evidence |
| 5 | Push ignored state | **Fixed:** push only from AWAITING_INTEGRATION, full-lifecycle kinds only, never `-int-` branches |
| 6 | `check-contract` optional | **Fixed:** `record` runs the contract rules on every record (ownership at `created`/`contract_revised`) |
| 7 | "Intersect restricted" | Documented as implemented: an allowed pattern may not fall inside a restricted one, and restricted wins on overlap at `check-result` |
| 7 | Stack depth ≤ 2 | Procedural (orchestrator rule), not tool-checked |
| 8 | Example drift | **Fixed:** `gen_examples.py --check` fails if the committed event sequences differ. `examples/home/` is a re-verifiable ledger home |
| 9 | verify-ledger blind spots | **Fixed:** remote-only (deleted) ledgers are reported, and contract edits after the last record are detected |
| 10 | Freeze claims | **Fixed:** `ctx.frozen` resets on `contract_revised`; `interface_contracts[].sha256` must equal the frozen hash; contract dependencies on INTERFACE_FROZEN / AWAITING_HUMAN now relax the matching DAG dependency |
| — | `tasks/` not filtered to `*.json` | **Fixed** |
| — | `evidence_dir` movable into HOME | **Fixed** (contract rules run on every record) |

**Security Medium items:**
- **Not denied:** `assign_copilot_to_issue`, `create_pull_request_with_copilot`, `label_write`, gists, and Notion/Gmail/Drive/Docs write tools in a normal session. These remain **open**: they are outside merge authority but are exfiltration and side-effect channels. Recommended for the next settings revision.
- **Hook regex gaps:** `/usr/bin/git push`, `\git push` and `$G push` are now matched. Text matching remains a tripwire.

## 3. What is still not closed

1. **The guard hook does not run in live dispatch** in the session that built this package (DOD-10, RB-D2 canary).
2. **Merge authority still rests on operator actions not yet taken.** It is only preventive once DOD-02 (ruleset, no bypass actors) and DOD-03 (development identity without merge/approve) are in place. DOD-09 (OS sandbox) is what makes the credential and network denies enforced.
3. **Single-writer ledger.** Any process running as the agent's uid can still write `$DEVORCH_HOME` and forge a *fully consistent* set of contracts, ledgers and hashed copies. Every R5 fix raises the bar for forgery and makes partial forgeries fail verification, but authenticity needs a separate uid for the ledger writer, or signed records. The pushed `devorch/state` history reviewed by the operator is the tamper reference.
4. **Re-review of this round.** These fixes have not been independently re-reviewed. A further independent pass (R6) is recommended before Stage A sign-off.
