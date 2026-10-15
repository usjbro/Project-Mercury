# R0 — Dispositions of Critical and High review findings (R1–R4)

Scope: every Critical and High finding of the four independent reviews. Medium and Low findings were addressed where they touched the same code or text; they are not individually tracked here.

**Status values:**
- **Fixed + tested** — a regression test in `tools/devorch/test_devorch.py` reproduces the finding and now passes.
- **Fixed** — the change is in the named file, with no automated test.
- **Mitigated** — a tripwire or procedure reduces the risk; the residual risk is stated.
- **Operator** — the finding cannot be closed without an operator decision or action (named in `12-amendments.md`).

Verification at this commit:
- `python3 tools/devorch/test_devorch.py` reports 30 tests, OK (after the R5 round).
- `python3 tools/devorch/gen_examples.py --check` reports the scenario OK.
- All schemas and examples validate under jsonschema 4.26.0 (Draft 2020-12).
- The generated agent files are byte-identical to the output of `gen_agents.py`.

## R1 — Lead Architect

| ID | Sev | Finding (short) | Disposition | Where |
|---|---|---|---|---|
| C-01 | Critical | Operator/Mac tasks could never reach COMPLETED, so 40–70 dependents were blocked forever | **Fixed + tested.** Short lifecycle for `planning`, `mac_validation`, `operator_action` and the subtask kinds: `result_accepted` → COMPLETED. Operator/Mac completion needs operator-provided evidence | `devorch.py` `T_SHORT`, `check_transition`; `01` §5; test `test_short_lifecycle_operator_task_completes` |
| H-01 | High | Git checks were skipped when a result reported `commits: []` | **Fixed + tested.** Checks always run against `rev-list base..tip`; commits must equal it; the worktree must be clean and at the tip. `record` re-runs the same checks for `implementation_completed` / `result_accepted` | `devorch.py` `result_errors`; tests `test_empty_commits_cannot_hide_restricted_change`, `test_dirty_worktree_rejected` |
| H-02 | High | Interface freeze could not complete | **Fixed.** Freezing is a `design` task on the full lifecycle. `interface_frozen` is a self-loop allowed from AWAITING_HUMAN or COMPLETED and records `frozen_files` hashes. Dependents wait on `INTERFACE_FROZEN` | `devorch.py`; `01` §5; `04`; `06` |
| H-03 | High | FAILED was terminal; RB-D7 was impossible | **Fixed + tested.** FAILED → `contract_revised` (→ BLOCKED) or `cancelled` | `devorch.py`; `07`; `13`; test `test_failed_can_be_revised` |
| H-04 | High | LOCK/ESCALATIONS in `ledger/` broke `verify-ledger` | **Fixed + tested.** Both now live at `$DEVORCH_HOME/LOCK` and `$DEVORCH_HOME/ESCALATIONS.md`; the ledger reads only `*.jsonl`; `--repair-tail` handles a torn last line | `devorch.py`; `02`; `07`; tests `test_lock_and_escalations_do_not_break_verify`, `test_partial_tail_detected_and_repairable` |
| H-05 | High | Subtask contracts collided with primary contracts in `ready` | **Fixed.** `ready` considers primary contracts only and reports duplicates. Subtasks have `merc_issue: null`, `parent_task_id` / `covers_tasks`, and enforced ids `<parent>-rN/-sN`, `<first covered>-iN` | `devorch.py` `cmd_ready`, `cmd_check_contract`; schema; `04`; `06` |
| H-06 | High | Agent scopes did not follow the TDD source layout | **Fixed.** Scopes are regenerated from components.md §2 | `gen_agents.py`; `.claude/agents/*`; `03` |
| H-07 | High | DoD D6–D8 could not be satisfied (`docs/mercury/**` forbidden; G4 only when security-sensitive) | **Fixed (D6) / Operator (D7–D8).** G4 is required for every full-lifecycle task. D7–D8: option set out in DOD-01 (list non-normative status/evidence paths in a contract with a Lead Architect conformance review) | `devorch.py` `needs_g4`; `08` §2; `12` DOD-01 |
| H-08 | High | ADR-014/P0d governance and RISK-45 contradicted; MERC-030 mis-assigned | **Fixed (text) / Operator (action).** Code PRs require the development bot identity (DOD-03 a) and the ruleset (DOD-02) as hard preconditions. MERC-030 is split into DevOps files and operator settings, with an operator bootstrap before MERC-030 (RA-D9). A time-boxed exception to "governed like a target" applies until Stage D | `12`; ADR-021; `assignments.json` `_notes`; orchestrator rule 0 |

## R2 — Security

| ID | Sev | Finding (short) | Disposition | Where |
|---|---|---|---|---|
| S-01 | Critical | No ruleset on `main`; operator's GitHub authorization is shared by every agent process | **Operator + enforced precondition.** No code or PR task is dispatched until the operator has recorded `fact --kind decision --id DOD-02` (ruleset verified) and `--kind identity` (dev bot, DOD-03), and `get_me` returns that identity. Until then only design, planning and Mac-prep tasks run. **Residual:** on a personal repository an exclusively human merge is only detectable after the fact (G7 `merged_by`); an organization (G-ORG) is recommended | Orchestrator rule 0; `08`; `11` Stage A; `12` DOD-02/03 |
| S-02 | Critical | Credential reads were claimed to be "prevented" | **Mitigated; matrix corrected.** Read/Edit denies and Bash denies (`git credential*`, credential config reads, curl/wget to `api.github.com`) are documented as **tripwires**. Specialists also hit the guard hook *if it runs* (R5: it did not, DOD-10). **Residual:** subprocesses that open files themselves bypass deny rules, and so does the main session's Bash. The only enforcing control is Claude Code's OS sandbox, which is **not enabled**; recommended as operator decision DOD-09 for the Mac. The real protection is S-01's identity without merge/approve rights | `.claude/settings.json` (119 denies); `hooks/specialist_guard.py`; `08` matrix; `12` |
| S-03 | Critical | GitHub/Linear write tools not denied; normal sessions not covered | **Fixed.** All GitHub write tools, Linear and Slack writes, and the plugin server prefixes are denied project-wide. The "paste §6 into a normal session" option was removed: `claude --agent mdev-principal-orchestrator` is required. Verified live: the denied MCP tools disappeared from the session. **Residual:** the plugin server-level deny name format is unverified (those servers currently fail to connect); claude.ai connector prefixes are covered only by the tool names enumerated | `.claude/settings.json`; `13` RB-D2; `02` |
| S-04 | High | Push denies matched one spelling | **Mitigated.** Settings deny `main` refspecs, force, `--mirror`, `--all` and `--delete` in several spellings. Specialists are blocked from any `git push` by the guard hook. The orchestrator pushes only via `devorch.py push`, which checks `dev/*`, tip == tested head, G1–G5 and the git baseline. **Residual:** text matching is not a boundary; DOD-02's ruleset is | settings; hook; `devorch.py push` |
| S-05 | High | Shared git dir lets a specialist plant hooks or config | **Mitigated.** Edit/Write denies cover `**/.git/hooks/**` and `**/.git/config`. The hook blocks `.git/` writes and git internals. Worktrees are created and pushes made with `core.hooksPath=/dev/null`. `git-baseline verify` (config hash, hooks list, `.claude`, `CLAUDE.md`, `tools/devorch`) runs in `preflight` and before every push | settings; hook; `devorch.py git-baseline`, `push`, `preflight`; `06` |
| S-06 | High | Unkeyed hash chain; agents could write the ledger | **Mitigated + tested.** `actor` ∈ {orchestrator, operator}. The guard hook blocks `devorch.py` and `tools/devorch/` for specialists. `evidence_dir` must be outside `DEVORCH_HOME`, and evidence is imported with a MANIFEST. `verify-ledger` replays every rule and compares with the pushed branch (`--remote`). **Residual:** the chain is unkeyed by design; the pushed history is the tamper reference | `devorch.py`; tests `test_forged_actor_refused`, `test_forged_ledger_detected_by_replay`, `test_evidence_dir_inside_home_refused` |

## R3 — TPM

| ID | Sev | Finding (short) | Disposition | Where |
|---|---|---|---|---|
| R3-01 | High | Priority inversion on the operator/Mac lane | **Fixed.** Schedule model v2: one priority queue per resource, ordered by longest remaining path | `schedule_model.py`; `05` §4 |
| R3-02 | High | Operator PR review and merge not modelled | **Fixed.** Every code-producing issue has an operator review/merge step (0.10–0.25 d); dependents start after the merge (stacking shown as sensitivity) | `schedule_model.py`; `05` |
| R3-03 | High | M9 calendar contradicted roadmap §6 / OD-16 | **Fixed.** Shadow 10 days and pilot 15–30 days; the end-point is cutover start; the 30-day watch is reported separately | `schedule_model.py`; `05` |
| R3-04 | High | Operator-availability assumption inconsistent with RA-D4 | **Fixed.** Availability is a model parameter. Expected 92 working days at full time, 118 at 50 % and 219 at 20 %. Recommendation: operator ≥ 50 % in W0–W1 and gate weeks (RA-D4 revised) | `05` sensitivity; `12` RA-D4 |

## R4 — Code / Reliability

| ID | Sev | Finding (short) | Disposition | Where |
|---|---|---|---|---|
| F01 | High | = H-01 | **Fixed + tested** | as H-01 |
| F02 | High | Rename detection hid a restricted source path | **Fixed + tested.** `git diff --no-renames -z` lists both sides | `devorch.py` `changed_files`; test `test_rename_out_of_restricted_path_detected` |
| F03 | High | A security-sensitive task could skip G4 | **Fixed + tested.** G4 is required for every full-lifecycle task, and AWAITING_INTEGRATION requires G1–G4 | `devorch.py`; test `test_security_review_cannot_be_skipped` |
| F04 | High | = H-04 | **Fixed + tested** | as H-04 |
| F05 | High | Self-certification and tampering passed verification | **Fixed + tested.** `verify-ledger` replays `check_transition` (actor, gates, evidence, budgets, contract core). The contract core hash is in every record | tests `test_forged_ledger_detected_by_replay`, `test_contract_tamper_detected`, `test_correction_attempt_keeps_contract_core` |
| F06 | High | = H-05 | **Fixed** | as H-05 |
| F07 | High | = H-03 | **Fixed + tested** | as H-03 |
| F08 | High | = H-02 | **Fixed** | as H-02 |
| F09 | High | Review was not bound to the head commit | **Fixed + tested.** Review contracts carry `review_target.head_commit`. Results must set `reviewed_head_commit` to it. G3/G4 require a COMPLETED subtask bound to the parent's current tested head. A new head clears G2–G7 | `devorch.py` `verify_subtask`; schemas; tests `test_full_happy_path_with_bound_reviews`, `test_review_of_stale_head_refused` |

## Defects found during the fix round (not in R1–R4)

| ID | Defect | Fix |
|---|---|---|
| R0-01 | `evidence_dir` (named per attempt) was part of the hashed contract core, so a correction attempt needed a spurious `contract_revised` | `CONTRACT_MUTABLE` = status, attempt, evidence_dir; test `test_correction_attempt_keeps_contract_core` |
| R0-02 | `result_accepted` accepted any existing result file; the integration result in the happy-path test would have failed `check-result` | `record` re-runs `result_errors` for `implementation_completed` / `result_accepted`; integration scope = union of covered tasks; integrated heads must be in the tip and equal the tested heads; test `test_result_accepted_requires_checking_result` |
| R0-03 | Integration branch `devint/*` did not match the contract branch pattern | `dev/dt-<nnnn>-int-<wave>-<n>`, local only |
| R0-04 | `preflight` required a clean `DEVORCH_HOME`, but `lock acquire/refresh` rewrites `LOCK` there | The clean check ignores `LOCK` only; it is committed and pushed with the ledger each tick; test `test_preflight_tolerates_own_lock_but_not_foreign_changes` |

## Residual risks and items only the operator can close

1. **Merge authority:** DOD-02 (ruleset on `main`) and DOD-03 (development bot identity without merge/approve rights). These are hard preconditions for any code or PR task. On a personal repository, G-ORG (move to an organization) is needed to make "only the owner merges" preventive rather than detective.
2. **Enforcing sandbox (DOD-09):** Claude Code's OS sandbox for the Mac sessions (S-02) is not enabled. All deny rules and the guard hook remain tripwires.
3. **Unverified mechanisms:**
   - hooks firing inside subagents during a live dispatch;
   - the plugin server-level deny name format;
   - the `devorch/state` ledger branch (not created yet).
   These are listed in `13-…` as first-run checks (RB-D1/RB-D2).
4. **TDD approval and DoD D7–D8 interpretation:** DOD-01.
5. **Schedule:** operator availability dominates (`05` §4). The plan holds only if the operator is ≥ 50 % available in W0–W1 and gate weeks.

**R5 re-check (`R5-recheck.md`):**
- **Rejected four closures:** S-01, S-05, S-06 and F05/F09 were only partial.
- **New findings:** N-01…N-06 and N1…N4. All except N-01 are now fixed in code, each with a regression test, apart from the operator-only residuals listed there.
- **Guard hook:** shown not to fire in live dispatch in the authoring session (DOD-10).

Where this table and R5 differ, R5 is current.
