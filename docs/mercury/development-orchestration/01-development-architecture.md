# 01 — Multi-Agent Development Architecture

Status: **Proposed** (requires operator approval; see `12-amendments.md` DOD-01). Scope: the *temporary* system used to **build** MERCURY. It is not the production MERCURY orchestrator and it changes no production design decision.

## 1. Two systems, kept apart

| | Development orchestration (this package) | Production MERCURY (TDD) |
|---|---|---|
| Purpose | Build the MERCURY code base | Coordinate Claude and Codex on target repos |
| Orchestrator | A Claude Code **main session** acting as Principal Orchestrator (`mdev-principal-orchestrator`) | `mercuryd`, a deterministic TypeScript daemon |
| Workers | 12 Claude Code project subagents `mdev-*` | Claude decision runs and Codex exec runs under `_mercuryagent` |
| Durable state | Git ledger branch `devorch/state` + GitHub PRs | SQLite (`MERCURY_HOME`) |
| Contracts | `devorch.task_contract.v1` / `devorch.task_result.v1` / `devorch.handoff.v1` | `mercury.*.v1` (protocols/schemas) |
| Identity | The operator's Claude Code session and its GitHub authorization (see DOD-03) | `mercury-bot`, `mercury-ops`, Linear app, `_mercuryagent` |
| Human authority | Operator approves and merges every PR into `main` | Operator approves and merges every PR on target repos |

**Separation rules.**
- **S1 — no reuse of production schemas or identities.** Development contracts never reuse production `mercury.*` schemas or identities.
- **S2 — no shared credentials.** Development agents never hold or use MERCURY's production credentials, which do not exist yet and are created by the operator in P0c.
- **S3 — production stays separate from development config.** Production MERCURY must never read `.claude/agents/mdev-*`, `CLAUDE.md` or `.devorch/`. Its Claude runs use `settingSources: []` (SEC-204), so they don't.
- **S4 — self-hosting changes nothing in development.** When MERCURY later works on its own repository (`11-self-hosting-transition.md`), production rules apply to the work MERCURY does, and `.claude/**` and `CLAUDE.md` become block- and escalate-class paths for it (SEC-310). The development system is not weakened by this.

## 2. Component view

```mermaid
flowchart TB
    OP["Operator (approves, merges, decides)"]
    subgraph CC["Claude Code session (cloud or Mac)"]
        PO["Principal Orchestrator (main session, mdev-principal-orchestrator)"]
        subgraph SA["Specialist subagents (no nesting, no direct messaging)"]
            A1["01 Lead Architect"] 
            A2["02 TPM"]
            IMP["03 Backend, 04 Database, 05 AI Integration, 06 Platform, 08 DevOps, 09 Test, 10 Reliability"]
            A7["07 Security"]
            A11["11 Code Reviewer (read-only)"]
            A12["12 Integration and Release"]
        end
    end
    DT["tools/devorch/devorch.py (validate, ledger, DAG, READY)"]
    LG[("devorch/state branch: tasks, ledger, evidence, dag")]
    WT[("Task worktrees ../mercury-wt/DT-nnnn")]
    GH["GitHub: PRs, CI, reviews, merges"]
    LN["Linear (read-only until DOD-05)"]
    MAC["Mac validation queue (operator-run)"]
    PO -->|"task contract"| SA
    SA -->|"task result JSON"| PO
    PO --> DT
    DT --> LG
    IMP --> WT
    A7 --> WT
    A12 --> WT
    PO -->|"push dev branches, open PR"| GH
    GH -->|"CI status, human review, merge"| PO
    A2 -.->|"read"| LN
    PO -->|"escalations, decisions"| OP
    PO -->|"Mac tasks"| MAC
    MAC -->|"evidence"| PO
    OP -->|"approve and merge"| GH
```

## 3. Responsibilities and authority

| Actor | May | May not |
|---|---|---|
| Operator | Approve the TDD and amendments; answer escalations; run Mac and [ROOT] steps; approve and merge PRs; create Linear issues | — |
| Principal Orchestrator | Select READY tasks, write contracts, dispatch specialists, verify results mechanically, record ledger transitions, push `dev/*` branches, open PRs, write progress reports | Merge, approve, change settings, protections or credentials; mark a gate passed without evidence; modify design documents outside an approved task |
| Specialists | Work inside their worktree and allowed paths; commit to their task branch; return results | Push, merge, spawn agents, message each other, pick work, change frozen interfaces |
| Code Reviewer | Read and re-run tests | Edit anything |
| `devorch.py` | Enforce the transition table, gate prerequisites, budgets, contract integrity, result checks and hash chain; push only `dev/*` with G1–G5 | Decide anything |

## 4. Authoritative source per state category

| Category | Authoritative source | Notes |
|---|---|---|
| Design (requirements, contracts, ADRs) | `docs/mercury/**` on `main` after operator merge. Before that, the approved design commit recorded in each contract (`approved_design_refs …@<sha>`) | — |
| Backlog definition | `planning/issue-breakdown.md` (DAG via `devorch.py dag`) until Linear issues exist, **then Linear** (DOD-05) | — |
| Development task state (READY…CLOSED), attempts, gate records | **Ledger** (`devorch/state:ledger/<task>.jsonl`, hash-chained, replay-verified, compared with the pushed branch) | Pushed history is the tamper reference (`verify-ledger --remote`) |
| Code, branches, commits | Git (task branches; reviewed head SHAs recorded in the ledger) | — |
| CI results | GitHub Checks | — |
| Human approval and merge | **GitHub only** (`merged_by`, approving review on the merged head) | — |
| Mac validation evidence, TDD gate status (G-S1…G-S5), Phase 0 checks, development identity | Operator-recorded facts (`devorch.py fact`, `facts.jsonl`) plus evidence files imported into the ledger branch | Only the operator records facts |

A Linear status change never starts development work. Only a ledger `assigned` record, written by the orchestrator for a READY task, does.

## 5. Development task state machine

Two lifecycles, selected by contract `kind`. The machine-readable source is `T_FULL` / `T_SHORT` and `check_transition()` in `tools/devorch/devorch.py`. `record` and `verify-ledger` run the **same** rules, so a ledger that was not produced by those rules fails verification.

**Full lifecycle**: `implementation`, `test`, `reliability`, `design`, `release`. These kinds produce code and a PR.

```mermaid
stateDiagram-v2
    [*] --> BLOCKED: created
    BLOCKED --> READY: unblocked, G1 design refs approved, deps, facts
    READY --> RUNNING: assigned
    RUNNING --> RUNNING: dispatched, started, env_retry, attempt_failed, tests_failed
    RUNNING --> AWAITING_REVIEW: tests_passed G2 (orchestrator re-run, head recorded)
    AWAITING_REVIEW --> AWAITING_REVIEW: code_review_passed G3 or security_review_passed G4
    AWAITING_REVIEW --> AWAITING_INTEGRATION: both G3 and G4 recorded
    AWAITING_REVIEW --> RUNNING: changes required or security block
    AWAITING_INTEGRATION --> AWAITING_INTEGRATION: integration_verified G5
    AWAITING_INTEGRATION --> RUNNING: integration_failed
    AWAITING_INTEGRATION --> AWAITING_HUMAN: pr_prepared G6 (pushed head equals reviewed head)
    AWAITING_HUMAN --> RUNNING: human changes requested
    AWAITING_HUMAN --> COMPLETED: human_merged G7
    RUNNING --> READY: reclaimed
    RUNNING --> FAILED: failed (budget exhausted)
    FAILED --> BLOCKED: contract_revised
    BLOCKED --> READY: resumed
    COMPLETED --> [*]
    CANCELLED --> [*]
```

**Short lifecycle**: `code_review`, `security_review`, `design_review`, `reliability_review`, `integration` subtasks, plus `planning`, `mac_validation` and `operator_action`.

```mermaid
stateDiagram-v2
    [*] --> BLOCKED: created
    BLOCKED --> READY: unblocked G1
    READY --> RUNNING: assigned
    RUNNING --> RUNNING: dispatched, env_retry, attempt_failed
    RUNNING --> COMPLETED: result_accepted (validated result or operator evidence)
    RUNNING --> READY: reclaimed
    COMPLETED --> [*]
```

**Edges not drawn above.**
- **Any non-terminal state:** → `BLOCKED` (`escalated`, `contract_revised`) and → `CANCELLED`.
- **RUNNING, AWAITING_REVIEW, AWAITING_INTEGRATION:** → `FAILED`, plus `stale_detected` self-loops.
- **FAILED:** → `CANCELLED`.
- **AWAITING_HUMAN or COMPLETED:** `interface_frozen` self-loops on design tasks, recording the frozen file hashes.

Operator and Mac tasks (MERC-001, 020, …) complete through `result_accepted` with operator evidence. This lets their 40–70 dependents become READY.

**Gate rules enforced by the tool:**

| Gate | Rule |
|---|---|
| G1 | Recorded at `unblocked`, needs `design_ref` evidence; required before RUNNING |
| G2 | Needs `test_run` evidence from the orchestrator's own re-run (in a fresh detached checkout) and records `head_commit`, which must equal the head of a checked `implementation_completed` in the same attempt and the branch tip |
| G3 / G4 | Need a COMPLETED review subtask whose accepted result has `reviewed_head_commit` = the recorded head, `recommendation` accept, and no blocking finding. G3 also needs every reviewer listed in `required_reviewers`. **G4 is required for every full-lifecycle task**: TDD DoD D6 asks for a security review on every issue, kept light for non-sensitive changes |
| G5 | Needs a COMPLETED integration subtask that covers the task at the same head |
| G6 | Needs `pr` and `ci_run` evidence; pushed head = reviewed head. `devorch.py push` pushes only full-lifecycle tasks in AWAITING_INTEGRATION and only once the DOD-02 and DOD-03 operator facts exist |
| G7 | `github_merge` evidence at the G6 head |
| Reset | A return to RUNNING clears G2–G7 (G1 survives); duplicate gates are refused |
| Contract integrity | The contract core (everything except the per-attempt fields `status`, `attempt` and `evidence_dir`) is hashed into every record. Changing it without `contract_revised` is refused |
| Budgets | `budget.max_attempts`, 3 review cycles, 2 security cycles, 2 integration cycles and 5 environmental retries are counted from the ledger, and refused beyond the limit |
| Writers | `actor` ∈ {principal-orchestrator, operator}; operator/Mac completions require `actor operator`. Agents never write the ledger; the specialist guard hook blocks the tool for them (tripwire: `--actor` is self-asserted) |
| Evidence | `record` reads each evidence file once, copies it to `$DEVORCH_HOME/evidence/<task>/records/` and stores its sha256; the ledger trusts only that copy. Replay re-checks every hash, the subtask bindings, the required reviewers (each record against the contract snapshot of its own core, `04-contracts.md`) and the contract file against the last record, so `verify-ledger` and `record` apply the same rules |

**Evidence stages required by the brief → ledger events:**

| Stage | Event | Gate |
|---|---|---|
| Task assigned | `assigned` | — |
| Task started | `dispatched` / `started` | — |
| Implementation completed | `implementation_completed` (`check-result` VALID) | — |
| Tests passed | `tests_passed` | G2 |
| Code review completed | `code_review_passed` | G3 |
| Security review completed | `security_review_passed` | G4 |
| Integration verified | `integration_verified` | G5 |
| Pull request prepared | `pr_prepared` | G6 |
| Awaiting human approval | state `AWAITING_HUMAN` | — |
| Human-approved and merged | `human_merged` | G7 |
| Closed | `closed` (worktree removed, dependents re-evaluated) | — |

## 6. Why this shape (decisions and alternatives)

| Decision | Alternatives rejected | Reason |
|---|---|---|
| Orchestrator = main session, not a subagent | An orchestrator subagent | Subagents cannot outlive their task or reliably hold the loop. The main session can be resumed and re-reads the ledger. |
| No subagent nesting, no peer messaging | Peer-to-peer handoffs via `SendMessage` | One audited coordinator. Peer messages are not durable and would bypass the ledger. |
| Git ledger branch | Linear as state store; conversation memory | Durable across container loss (pushed), reviewable and diffable. Linear writes are not authorized yet. Conversation memory is lost on interruption. |
| Mechanical result verification | Trust agent reports | The brief forbids completion on claims alone. `check-result` compares claims with git. |
| Explicit worktrees from a recorded base | `isolation: worktree` | The built-in option branches from `main`, which lacks the design. Explicit base commits make reviews reproducible. |
| 12 specialists, most used rarely | Fewer, generalist agents | Specialization only where the expertise pays (review, security, DB). The dispatch policy (`02-…` §4) avoids launching agents to keep them busy. |
| Small stdlib tool | Implementing parts of MERCURY early to run development | It would violate "no implementation before approval" and confuse the two systems (S1–S4). |
