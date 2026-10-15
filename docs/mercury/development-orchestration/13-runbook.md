# 13 — Operational Runbook (development orchestration)

All commands run from the repository root unless stated. `T=tools/devorch/devorch.py`.

## RB-D1 One-time setup (Stage A, after DOD-01)

```bash
# 1. Install the validator dependency (optional but recommended; enables full schema validation)
python3 -m pip install --user jsonschema
# 2. Create the ledger branch and worktree (orphan history)
git worktree add --orphan -b devorch/state ../mercury-devorch     # git >= 2.42
mkdir -p ../mercury-devorch/{tasks,ledger,evidence,reports}
echo "# MERCURY development ledger (generated; do not edit by hand)" > ../mercury-devorch/README.md
export DEVORCH_HOME=$(cd ../mercury-devorch && pwd)
python3 $T dag                      # writes $DEVORCH_HOME/dag.json; must print cycles=0
git -C ../mercury-devorch add -A && git -C ../mercury-devorch commit -m "devorch: init" && git -C ../mercury-devorch push -u origin devorch/state
# 3. Restart Claude Code in the repo so .claude/agents/ is loaded; check for ignored fields:
claude --debug   # look for 'does not recognize' lines mentioning mdev-*; there must be none
# 4. Operator applies the main ruleset (DOD-02) and the development identity (DOD-03) in GitHub settings.
```

## RB-D2 Start or resume a session

```bash
cd Project-Mercury && export DEVORCH_HOME=$(cd ../mercury-devorch && pwd)
claude --agent mdev-principal-orchestrator
# then: "Resume development orchestration."
```

The orchestrator follows `02-principal-orchestrator.md` §6: pull the ledger, verify it, check status, handle stale tasks, then continue.

## RB-D3 Daily operator routine (≈ 15 min)

1. Read `$DEVORCH_HOME/reports/latest.md` and `ledger/ESCALATIONS.md`, and answer OPEN items.
2. Review the PRs in AWAITING_HUMAN. Approve and merge only if the head SHA equals the "Human gate" SHA in the PR body.
3. Run the scheduled Mac-lane scripts (RA-D4) and hand the outputs to the orchestrator.

## RB-D4 Pause / stop everything

- Tell the orchestrator "pause dispatch", or end the session. Running background subagents finish or are lost, and either outcome is recoverable.
- Hard stop: close the session. Nothing runs without a session, and the ledger is safe on the branch.

## RB-D5 Cancel a task

```bash
python3 $T record --task DT-0042 --event cancelled --actor operator --evidence operator_statement:"cancel: reason"
git worktree remove ../mercury-wt/DT-0042    # after archiving: git -C ../mercury-wt/DT-0042 diff > $DEVORCH_HOME/evidence/DT-0042/uncommitted.patch
```

## RB-D6 Ledger verification fails

1. Stop dispatching.
2. Run `git -C $DEVORCH_HOME log -p ledger/<task>.jsonl` and find the first bad record.
3. If a record was edited, restore it from the pushed history (`git checkout origin/devorch/state -- ledger/<task>.jsonl`) and re-verify.
4. If two orchestrators wrote records, keep the earliest valid chain. Re-derive the later work from git and GitHub facts, and re-record it with a note.

## RB-D7 A specialist keeps failing

After the budget is exhausted the task is FAILED and escalated. Then:

1. Read the attempt evidence.
2. Either revise the contract (split it, clarify it, add design refs), which records `contract_revised` → BLOCKED → READY, or
3. Re-assign the work to a different specialist.

Never raise `max_attempts` to make a task pass.

## RB-D8 Self-hosting stage change

Follow `11-self-hosting-transition.md`. Each stage needs an `operator_decision` entry in `ESCALATIONS.md` with the evidence checklist attached.

## RB-D9 Retire the development orchestrator

Only after Stage E has run for 30 days:

1. Stop dispatching.
2. Archive the ledger branch (tag `devorch/final`).
3. Keep `.claude/agents/` and `tools/devorch/` as the fallback (rollback path).
