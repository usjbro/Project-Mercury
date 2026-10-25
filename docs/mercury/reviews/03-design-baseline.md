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

## Discovery facts every Phase 2 agent must account for (added after Phase 1)
Sources: `01-discovery-local.md`, `01-discovery-integrations.md`, `02-discovery-agent-runtimes.md`, `02-discovery-platform.md`.
1. The Mac was not observable; all Mac facts are assumptions → Phase 0 verification milestone required.
2. The workflow MERCURY replaces exists in `usjbro/network_monitor` (Linear team `JAM`, Slack `#network-monitor`) using shell scripts, gate files, `.ai/` state and `.worktrees/<slug>`. MERCURY must coordinate work on **target repositories** such as `network_monitor`; `project-mercury` holds MERCURY itself.
3. Today agents act under the **human's own identities** (GitHub `usjbro` admin, Linear user, Slack user). Separate agent identities are a prerequisite for the approval boundary.
4. Target repos are on a **personal GitHub account** (public): every collaborator has write; bypass lists/push restrictions are org-only → "human approves" is enforceable (CODEOWNERS=human + required code-owner review + require approval of most recent push + dismiss stale), but "only human clicks merge" is detect-after-the-fact unless repos move to an organization. Needs an ADR + operator decision.
5. Linear: one team (`JAM-n`), 7 default states, specs in issue descriptions with AC checkboxes, heavy blocks/blocked-by usage, Linear GitHub integration auto-moves status on PR events, Linear "coding sessions" can start Claude/Codex on delegated issues (a second, unauthorized start path to detect/refuse). Agents today use "next Todo" as the queue (conflicts with constraint).
6. Claude headless/Agent SDK runs execute repo-provided hooks / `.mcp.json` unless isolated (`settingSources: []` / `--bare`, `--strict-mcp-config`, explicit tool allowlist, hooks disabled). Claude Agent SDK offers `canUseTool`, hooks, structured output, interrupt, budgets.
7. Codex `exec` runs with approval policy `never`; sandbox mode is the real control. `workspace-write` blocks network by default and protects `.git` → Codex likely **cannot commit** in a worktree (verify). `codex mcp-server` removed in 0.162.x; app-server experimental. `--output-schema` gives structured final output.
8. Neither agent CLI enforces a whole-run timeout; coordinator must enforce deadlines and kill process groups.
9. No inbound: poll GitHub REST with ETags (304s are free); Events/Notifications APIs too laggy for control flow; poll Linear by `updatedAt`. Self-hosted runner on public repo discouraged.
10. launchd LaunchAgent (runs only while user logged in); SIGTERM then SIGKILL after ExitTimeOut; caffeinate only prevents idle sleep; keep files out of TCC-protected folders; detached children escape launchd cleanup.
11. SQLite WAL + `synchronous=FULL` + `fullfsync` on macOS; single writer; Node 24 LTS target; wrap `node:sqlite`/`better-sqlite3` behind an interface.
12. Slack pain points: missed replies, unnoticed stalls (14h), human relays, decisions not recorded, leaked bot token, monitoring only while a chat session is open.
