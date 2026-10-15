# 13 — Operational Runbook (development orchestration)

All commands run from the main checkout (never from a task worktree; `devorch.py` refuses to run under `/mercury-wt/`). `T=tools/devorch/devorch.py`. Flags are those printed by `python3 $T <command> --help`. Steps marked **operator** are run by the operator, not by an agent.

## RB-D1 One-time setup (operator bootstrap, Stage A, after DOD-01 and before MERC-030)

```bash
# 1. Validator dependency, pinned (full JSON Schema validation; without it devorch reports structural-only checks)
python3 -m pip install --user jsonschema==4.26.0
# 2. Ledger branch and worktree (orphan history; git >= 2.42), agent evidence root OUTSIDE the ledger worktree
git -c core.hooksPath=/dev/null worktree add --orphan -b devorch/state ../mercury-devorch
mkdir -p ../mercury-devorch/{tasks,ledger,evidence,reports} ../mercury-evidence
echo "# MERCURY development ledger (generated; do not edit by hand)" > ../mercury-devorch/README.md
git -c core.hooksPath=/dev/null -C ../mercury-devorch add -A
git -c core.hooksPath=/dev/null -C ../mercury-devorch commit -m "devorch: init"   # the branch must exist before devorch runs
export DEVORCH_HOME=$(cd ../mercury-devorch && pwd) DEVORCH_EVIDENCE=$(cd ../mercury-evidence && pwd)
python3 $T dag                      # writes $DEVORCH_HOME/dag.json; must print cycles=0
python3 $T git-baseline record      # hashes .git/config, git hooks, .claude, CLAUDE.md, tools/devorch, .gitignore
git -c core.hooksPath=/dev/null -C "$DEVORCH_HOME" add -A
git -c core.hooksPath=/dev/null -C "$DEVORCH_HOME" commit -m "devorch: dag and git baseline"
python3 $T push --ledger            # verifies the baseline, then pushes devorch/state
git -C "$DEVORCH_HOME" fetch origin devorch/state && git -C "$DEVORCH_HOME" branch -u origin/devorch/state
# 3. Self-test of the specialist guard hook (must print a "Blocked …" line and exit=2)
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin HEAD"}}' | python3 tools/devorch/hooks/specialist_guard.py; echo "exit=$?"
# 4. Restart Claude Code in the repo so .claude/agents/ is loaded; check for ignored fields:
claude --debug   # look for 'does not recognize' lines mentioning mdev-*; there must be none
```

5. **Operator, in GitHub:** apply the ruleset on `main` (DOD-02) and create the development bot identity (DOD-03). Then record both as facts and commit them:

```bash
python3 $T fact --kind decision --id DOD-02 --status verified --actor operator --evidence "<ruleset id or URL>"
python3 $T fact --kind identity --id DOD-03 --status verified --actor operator --evidence "login=<bot login>"
git -C "$DEVORCH_HOME" add facts.jsonl && git -C "$DEVORCH_HOME" commit -m "facts: DOD-02, DOD-03" && python3 $T push --ledger
```

Until both facts exist and `get_me` returns that identity, the orchestrator runs only design, planning and Mac-lane preparation tasks (`02-…` §3). The settings deny rules and the guard hook are tripwires, not security boundaries; the ruleset and the separate identity are the real controls. On a personal repository an exclusively human merge is only detectable after the fact (G7 `merged_by`); an organization (G-ORG) is recommended.

## RB-D2 Start or resume a session

```bash
cd Project-Mercury
export DEVORCH_HOME=$(cd ../mercury-devorch && pwd) DEVORCH_EVIDENCE=$(cd ../mercury-evidence && pwd)
claude --agent mdev-principal-orchestrator     # required; never run the orchestrator in a normal session
# then: "Resume development orchestration."
```

**After every start or restart, verify before any dispatch** (the orchestrator does this in `02-…` §6 step 2; the operator checks the answer):

| Check | How | If it fails |
|---|---|---|
| Agents loaded | `/agents` lists the 13 `mdev-*` agents | Fix the definitions; restart |
| `Agent()` allowlist | The orchestrator's `Agent` tool offers exactly the 12 specialist names, and no general-purpose agent | The session was not started with `--agent`; restart as above |
| Hooks | Each specialist's frontmatter has the `PreToolUse` guard (`Bash\|Edit\|Write\|NotebookEdit\|MultiEdit`); the RB-D1 step 3 self-test exits 2. Firing inside a live dispatch is **not yet verified**: until a dispatched specialist has reported a guard block, reports state the guard as unverified | Stop dispatch; escalate |
| `$CLAUDE_PROJECT_DIR` | `echo "$CLAUDE_PROJECT_DIR"` in the orchestrator's Bash prints the main checkout (the hook command is resolved through it) | Restart from the main checkout |
| Identity | `mcp__github__get_me` returns the DOD-03 identity | Code/PR tasks stay paused (`02-…` §3) |

The orchestrator then follows `02-principal-orchestrator.md` §6: ledger worktree, `lock`, `preflight`, `status`, stale tasks, then the main loop.

## RB-D3 Daily operator routine (≈ 15 min)

1. Read `$DEVORCH_HOME/reports/latest.md` and `$DEVORCH_HOME/ESCALATIONS.md`, and answer OPEN items (edit to `ANSWERED: …` and commit in `$DEVORCH_HOME`, or answer in chat).
2. Review the PRs in AWAITING_HUMAN. Approve and merge only if the PR head SHA equals the `head_commit` of the task's `pr_prepared` (G6) record on the pushed ledger branch, never a SHA quoted in agent-written PR text:
   `git fetch origin devorch/state && git show origin/devorch/state:ledger/DT-0042.jsonl | grep '"pr_prepared"'`
3. Run the scheduled Mac-lane scripts (RA-D4) and hand the outputs to the orchestrator.
4. Record verified TDD gates and Phase 0 checks as facts (operator only), then commit `facts.jsonl`:
   `python3 $T fact --kind tdd_gate --id G-S1 --status verified --actor operator --evidence "<evidence path>"`
   `python3 $T fact --kind p0_check --id P0-012 --status verified --actor operator --evidence "<evidence path>"`
   A fact is withdrawn with `--status revoked` (or `failed`).

## RB-D4 Pause / stop everything

- Tell the orchestrator "pause dispatch", or end the session. Running background subagents finish or are stopped; both are recoverable (`07-…` §4).
- On a clean stop the orchestrator runs `python3 $T lock release --session <sid>`, commits and runs `python3 $T push --ledger`.
- Hard stop: close the session. Nothing runs without a session, and the pushed ledger is safe on the branch.

## RB-D5 Cancel a task

Pause the orchestrator first (or ask it to do this), so that only one writer touches the ledger.

```bash
git -C ../mercury-wt/DT-0042 diff > $DEVORCH_HOME/evidence/DT-0042/attempt-N/uncommitted.patch   # archive first
python3 $T record --task DT-0042 --event cancelled --actor operator --evidence operator_statement:"cancel: reason"
git worktree remove ../mercury-wt/DT-0042
git -C "$DEVORCH_HOME" add -A && git -C "$DEVORCH_HOME" commit -m "cancel DT-0042" && python3 $T push --ledger
```

## RB-D6 Ledger verification or preflight fails

1. Stop dispatching (`preflight` failure already forbids it).
2. Run `python3 $T verify-ledger --remote origin/devorch/state` and `git -C $DEVORCH_HOME log -p ledger/<task>.jsonl` to find the first bad record.
3. **Unterminated final line** (crash during an append): after checking that no pushed record is lost, run `python3 $T verify-ledger --repair-tail`.
4. **Edited or truncated record** ("not an extension of origin/devorch/state"): restore it from the pushed history (`git -C $DEVORCH_HOME checkout origin/devorch/state -- ledger/<task>.jsonl`) and re-verify.
5. **Uncommitted changes in `$DEVORCH_HOME`**: inspect them; commit operator edits (e.g. `ESCALATIONS.md`), discard anything else and escalate.
6. If two orchestrators wrote records, keep the earliest valid chain. Re-derive the later work from git and GitHub facts, and re-record it with a note.

## RB-D7 A specialist keeps failing

When a budget is exhausted, `record` refuses further retries, and the task is recorded `failed` (→ FAILED) or `escalated` (→ BLOCKED). Then:

1. Read the attempt evidence (`$DEVORCH_HOME/evidence/<task>/attempt-*/`).
2. Either revise the contract (split it, clarify it, add design refs, or re-assign it to a different specialist): raise `contract_version`, record `contract_revised` (FAILED or BLOCKED → BLOCKED; budget counters reset), then `resumed` (→ READY); or
3. Cancel it (`cancelled`) and create a replacement task.

Never raise `max_attempts` to make a task pass. A plain correction attempt changes only `attempt` and `evidence_dir`; every other change is a revision.

## RB-D8 Self-hosting stage change

Follow `11-self-hosting-transition.md`. Each stage needs an `operator_decision` entry in `ESCALATIONS.md` with the evidence checklist attached.

## RB-D9 Retire the development orchestrator

Only after Stage E has run for 30 days:

1. Stop dispatching and release the lock.
2. **Operator:** archive the ledger branch (tag `devorch/final`).
3. Keep `.claude/agents/` and `tools/devorch/` as the fallback (rollback path).

## RB-D10 Lock held by another session

`lock acquire` or `preflight` reports a LOCK naming another session. Whatever its age, confirm that the other session has ended (no running Claude Code session on the ledger), then let the new session run `python3 $T lock acquire --session <sid> --force`, commit and `push --ledger`. Never force while the other session may still be alive.

## RB-D11 Git baseline violation

`git-baseline verify` (run by `preflight` and `push`) reports a change to `.git/config`, git hooks, `.claude/**`, `CLAUDE.md`, `tools/devorch/**` or `.gitignore` of the main checkout.

1. Stop everything; do not push. Treat it as a possible tampering incident (S-05).
2. **Operator:** inspect the change. If it is an approved change (e.g. a merged PR updating `tools/devorch/`), restart Claude Code and re-record with `python3 $T git-baseline record`, then commit and push the ledger. Otherwise revert it and escalate as a security incident.
