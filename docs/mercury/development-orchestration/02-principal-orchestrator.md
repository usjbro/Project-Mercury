# 02 — Principal Orchestrator Specification and Operating Procedure

The Principal Orchestrator is the **main Claude Code session**, started by the operator in this repository. It is defined in `.claude/agents/mdev-principal-orchestrator.md` and run with `claude --agent mdev-principal-orchestrator` (or by pasting §6 into a normal session). It is the only component that dispatches specialists, writes the ledger, pushes `dev/*` branches and opens PRs.

## 1. Responsibilities (brief Phase 2, items 1–18)

| # | Responsibility | How it is implemented |
|---|---|---|
| 1 | Understand the backlog | `devorch.py dag` → `dag.json`; Linear read (TPM) once issues exist |
| 2 | Read dependencies | `dag.json` `deps`, contract `dependencies[]` |
| 3 | Select eligible tasks | `devorch.py ready` plus the READY rule (§3) |
| 4 | Match agents | Dispatch table (§4) |
| 5 | Non-overlapping ownership | Path-ownership registry (`06-…` §4); a contract is refused if its `allowed_paths` overlap a RUNNING task's |
| 6 | Supervise concurrency | WIP limits (`09-…` §2); background subagents with completion notifications |
| 7 | Track states | Ledger (`devorch.py record`/`status`) |
| 8 | Collect structured outputs | Final JSON block → `evidence/<task>/attempt-N/result.json` → `check-result` |
| 9 | Automatic handoffs | Handoff protocol (`07-…` §1) |
| 10 | Dispatch failures for correction | Correction contracts (attempt+1) within budgets (`07-…` §3) |
| 11 | Enforce testing and review | Gates G1–G7 (`08-…`), enforced by `devorch.py record` prerequisites |
| 12 | Manage integration dependencies | Interface freezes (`INTERFACE_FROZEN` dependency type); Integration Engineer tasks |
| 13 | Prevent duplicate implementation | One task per MERC issue (contract `merc_issue` uniqueness); path ownership |
| 14 | Detect stalls | Stale-ownership checks (`07-…` §4) |
| 15 | Track resources and cost | `usage` in results; per-day cost ledger (`09-…` §3) |
| 16 | Progress reports | TPM report task daily or at each wave boundary |
| 17 | Escalate human decisions | Escalation queue `ledger/ESCALATIONS.md` + one message to the operator per batch |
| 18 | Auditability | Hash-chained ledger; commit trailers; evidence hashes |

## 2. Completion is never claimed, only evidenced

The orchestrator **re-verifies** every claim before recording a gate:

- **G2:** it runs the contract's `required_tests` itself in the task worktree and saves the logs.
- **G3/G4:** it requires a reviewer result, from a *different* agent instance, whose `review_target.head_commit` equals the current branch head.
- **G5:** it requires the integration result plus a `git range-diff`/patch-id equality check.
- **G7:** it reads GitHub. The PR must be `merged`, `merged_by` must be the operator, and the merged head must equal the head recorded at G6.

An agent's `status: completed` only permits the orchestrator to *start* these checks.

## 3. READY rule

A task is READY only when **all** of these hold:

1. Every `dependencies[]` entry has reached its `required_state` in the ledger (`COMPLETED`; or `INTERFACE_FROZEN` for interface-only dependencies; or `AWAITING_HUMAN` for stacked work, max stack depth 2, `06-…` §6).
2. Gate 1 is satisfied: the design refs are on an operator-approved commit (`12-…` DOD-01), and the interfaces the task uses are frozen.
3. Required operator authorization exists for the task class (DOD list; e.g. no M5+ non-sandbox runs before G-S2).
4. The Phase 0 prerequisites in the issue's `Gates` field are closed, or are explicitly mocked in the contract (`notes: "mocked: P0-xxx"`) for agent-only work that does not depend on the real result.
5. No path-ownership conflict with a RUNNING, AWAITING_REVIEW or AWAITING_INTEGRATION task.
6. Capacity is free: the agent lane, or the Mac/operator lane for Mac tasks.
7. Budget permits: daily cost cap and WIP limit (`09-…`).

## 4. Dispatch policy

**Priority order:**
1. critical path (longest remaining path in `dag.json`);
2. most downstream issues unblocked;
3. high-risk validation (security and recovery spikes, Phase 0 feasibility);
4. independent low-conflict tasks;
5. short blocker-removers.

**Never** dispatch because an agent is idle, and never run two agents on the same objective.

**Dispatch table:**

| Work type | Agent |
|---|---|
| Interface contracts, ADR proposals, design review | 01 Lead Architect |
| Backlog/critical path/reports | 02 TPM |
| Core logic (`src/core`, `src/app`, CLI) | 03 Backend |
| Store, DDL, migrations, triggers | 04 Database |
| Claude/Codex adapters, schemas, wire copies | 05 AI Integration |
| GitHub/Linear clients, pollers, outbox handlers | 06 Platform Integration |
| agent-exec/agent-ctl, sandbox profiles, redaction, presence; all security reviews | 07 Security |
| CI, packaging, launchd files, scripts | 08 DevOps |
| Test infrastructure and suites | 09 Test Automation |
| Fault injection, recovery validation | 10 Reliability |
| Diff review | 11 Code Reviewer |
| Integration branches, PR drafts, releases | 12 Integration and Release |
| T4/T5/ⓗ/[ROOT] steps | Mac validation queue (operator) |

The mapping from MERC issues to agents is in `05-dependency-and-critical-path.md` §5.

## 5. Main loop (one iteration = one "tick", run when woken by a notification or by the operator)

```text
1. git -C $DEVORCH_HOME pull --ff-only; devorch.py verify-ledger            # stop on failure
2. devorch.py status; read ledger/ESCALATIONS.md for answered items -> resume tasks
3. For each RUNNING task: check for a completed subagent notification;
     if result present -> save result.json -> devorch.py check-result
        INVALID -> record attempt_failed (or failed if budget exhausted)
        VALID   -> record implementation_completed; run G2 checks; record tests_passed|tests_failed
     if no result and stale (07 §4) -> record stale_detected; resume or reclaim
4. For AWAITING_REVIEW tasks without an active reviewer: dispatch 11 (and 07 if security_sensitive)
5. For AWAITING_INTEGRATION: batch ready tasks of one wave -> dispatch 12; on pass push dev branch, open draft PR (G6)
6. For AWAITING_HUMAN: poll the PR; merged by operator at the recorded head -> human_merged (G7) -> closed -> clean up worktree
7. devorch.py ready -> apply §3 -> create contracts (check-contract) -> create worktrees -> record assigned -> dispatch in background
8. Commit and push $DEVORCH_HOME (one commit per tick, message "tick <ts>: <summary>")
9. If nothing is running and nothing is READY: write a status report and end the turn (wait for the operator / notifications)
```

The orchestrator never sleeps or polls in a loop. It ends its turn and is woken by subagent completion notifications or by the operator.

## 6. Resume after context loss or session restart (normative)

The conversation is **never** the source of truth. To resume:

1. Start a session in the repository (`claude --agent mdev-principal-orchestrator`). Say: "Resume development orchestration."
2. Ensure the ledger worktree exists:
   `git fetch origin devorch/state && git worktree add ../mercury-devorch devorch/state`. If it already exists: `git -C ../mercury-devorch pull --ff-only`.
3. Run `python3 tools/devorch/devorch.py verify-ledger`. Any failure → stop and escalate (`ESCALATIONS.md`, kind `cannot_continue`).
4. Run `python3 tools/devorch/devorch.py status`.
5. **For every task in RUNNING:** the subagent from the lost session is gone (verified: a container restart stops background agents). If the platform offers to resume a stopped agent by id, prefer `SendMessage` to that id; it continues from its transcript under the same contract and attempt.
   - If the task branch has commits beyond `base_commit` and `evidence/<task>/attempt-N/result.json` exists, continue at loop step 3.
   - Otherwise record `stale_detected`, then either:
     - `reclaimed` (back to READY; the worktree is kept and its uncommitted changes are archived as a patch to `evidence/<task>/attempt-N/uncommitted.patch`); or
     - a new attempt with the same contract version (attempt+1, counts against budget only if the interruption was not environmental; `07-…` §3).
6. **For AWAITING_REVIEW, AWAITING_INTEGRATION or AWAITING_HUMAN:** re-derive pending work from the recorded gates and continue the loop.
7. Re-read `ESCALATIONS.md` and `reports/latest.md` for context. Never re-dispatch a task that already has a valid result for its current contract version and attempt.

This procedure is idempotent: running it twice produces no duplicate dispatches, because `assigned` is only legal from READY.

## 7. Escalation format (`ledger/ESCALATIONS.md`, one entry per question)

```markdown
## ESC-0007 — DT-0042 (MERC-107) — operator_decision — OPEN
Question: Approve running P0-026…031 sudoers install script on the Mac?
Options: (a) approve as written (b) approve with changes (c) defer
Recommended: (a) — scripts reviewed by Security (DT-0041, G4 pass)
Consequence of no answer: MERC-107, 108, 302, 401 stay BLOCKED; critical path slips day for day.
Evidence: evidence/DT-0041/attempt-1/security-review.json
```

The operator answers by editing the entry to `ANSWERED: (a)` (or in chat; the orchestrator then transcribes the answer and commits it, quoting the operator). Silence is never authorization.
