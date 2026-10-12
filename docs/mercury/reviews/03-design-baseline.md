# Design Baseline — Shared Vocabulary for Phase 2 (orchestrator-issued)

Purpose: give the six independent design agents a common vocabulary so their proposals can be compared and reconciled. **This is not a design decision.** Any agent may argue against any item here; disagreements must be stated explicitly in the agent's report under "Alternatives considered" and will be reconciled in Phase 4.

## Working names
| Term | Meaning |
|---|---|
| **MERCURY / coordinator** (`mercuryd`) | The continuously running local process on the Mac. Executes and tracks; never decides what to build. |
| **Claude (decision role)** | Claude Code invoked by the coordinator for decisions: triage/prioritization, authorization, plan review, PR review, security review. |
| **Codex (execution role)** | Codex CLI invoked by the coordinator for planning and implementation in an isolated worktree. |
| **Operator** | The human. Sole merge authority. |
| **Task** | One unit of work bound to exactly one Linear issue and one target repository. |
| **Authorization** | An immutable, versioned record by which Claude permits the coordinator to run Codex on a task, with scope and limits. |
| **Run** / **execution** | One invocation of an agent process (Claude or Codex) with its own `run_id`. |
| **Artifact** | An immutable, content-hashed output (plan, review, test report, diff summary) referenced by ID + SHA-256. |

## Identifier conventions (proposed)
- All IDs are ULIDs with a type prefix: `tsk_`, `auth_`, `run_`, `pln_` (plan version), `rev_` (review), `evt_`, `msg_`.
- Every message carries: `schema` (e.g. `mercury.plan.v1`), `message_id`, `correlation_id` (= task_id), `causation_id`, `dedup_key`, `occurred_at` (RFC 3339 UTC), `issue` (Linear identifier, e.g. `ENG-123`), `repo` (`owner/name`), `run_id` where applicable.

## Candidate state names (from the brief; may be revised with justification)
DISCOVERED, AWAITING_AUTHORIZATION, AUTHORIZED, PLANNING, AWAITING_PLAN_REVIEW, PLAN_REVISION_REQUESTED, PLAN_APPROVED, IMPLEMENTING, TESTING, PR_OPEN, CLAUDE_PR_REVIEW, CHANGES_REQUESTED, AWAITING_HUMAN_APPROVAL, MERGED, COMPLETED, FAILED, BLOCKED, CANCELLED.

## Working technology hypothesis (to be evaluated, not assumed)
Node.js (LTS) + TypeScript coordinator, SQLite (WAL) as the durable local store and job queue, agents invoked as supervised child processes, launchd LaunchAgent for supervision, GitHub and Linear accessed by outbound polling (no inbound webhooks).

## Authority invariants (from the brief; not negotiable)
1. No Codex run without a valid, unrevoked Claude authorization bound to the exact task and repo.
2. No implementation run without a Claude approval bound to the exact plan artifact hash.
3. A Linear status change alone never starts work.
4. No agent identity can satisfy GitHub's required human approval or merge to a protected branch — enforced by GitHub configuration and token permissions, not by prompts.

## File ownership in Phase 2 (write only your own files)
| Agent | Owns |
|---|---|
| A Principal Architect | `architecture/overview.md`, `architecture/decisions/ADR-*.md` (drafts), `reviews/10-agent-A-report.md` |
| B Solutions Architect | `integrations/{claude,codex,linear,github}.md`, `reviews/11-agent-B-report.md` |
| C Staff Engineer | `architecture/components.md`, `architecture/state-machine.md`, `protocols/messages.md`, `protocols/schemas/*.schema.json`, `reviews/12-agent-C-report.md` |
| D DevOps/Platform | `operations/macos-service.md`, `operations/recovery.md`, `reviews/13-agent-D-report.md` |
| E Security | `security/threat-model.md`, `reviews/14-agent-E-report.md` (initial assessment; `security/security-review.md` is written in Phase 5) |
| F TPM | `planning/traceability.md` (requirements + RTM), `testing/verification-plan.md` (acceptance criteria skeleton; other agents contribute in later phases), `reviews/15-agent-F-report.md` |
