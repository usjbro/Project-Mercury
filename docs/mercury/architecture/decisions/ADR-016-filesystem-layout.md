# ADR-016: Filesystem layout and ownership

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-18)** |
| Date | 2026-10-12 |
| Owner | Agent A. **Agent D owns the layout table** (`operations/macos-service.md` §7.1) and permissions (§7.2); every other document references it. Paths come from one constant module in the coordinator (`architecture/components.md`) |
| Related ADRs | [ADR-002](ADR-002-sqlite-store-and-queue.md), [ADR-005](ADR-005-codex-invocation-model.md), [ADR-006](ADR-006-coordinator-owns-git-and-pr.md), [ADR-013](ADR-013-agent-process-isolation.md), [ADR-017](ADR-017-claude-review-snapshot.md) |

## Context
- Phase 2 had five layouts: `~/MercuryWork` (A, C), `~/Library/Application Support/Mercury/checkouts` (B), `~/Library/Mercury` (D), `/Users/Shared/mercury` (E) (RA-03, RD-14, RE-19, RC-30).
- Under [ADR-013](ADR-013-agent-process-isolation.md) the agent uid must reach worktrees, snapshots, run directories and toolchains, but must not reach MERCURY's database, artifacts, config, control socket, or anything in the operator's home. The operator's home is 0700.
- Worktrees in the operator's home hold hostile files (`.vscode/tasks.json`, `.envrc`, untracked `.claude/` settings) that the operator's tools or interactive agents might open (RE-13).
- Codex project-trust keys and tool paths are fragile when paths contain spaces.
- TCC protects `~/Documents`, `~/Desktop` and `~/Downloads`; no MERCURY path may be inside them (NFR-092).

## Decision
Three roots (RD-2):

| Root | Location | Owner and mode | Holds | Agent access |
|---|---|---|---|---|
| `MERCURY_HOME` | `~/Library/Application Support/Mercury` | Operator uid, 0700 | Database, artifacts, config, control socket and tokens, `run/` state (lock, heartbeat, `fatal.json`) | **None** |
| `WORK_ROOT` | `/Users/Shared/MercuryWork` (no spaces) | Owner operator, group `mercury`, 0750 plus inherited group ACLs where agents write | Mirrors, task worktrees, review snapshots, per-task `CODEX_HOME`, per-run I/O, toolchains | Read where needed; **write only** to the task worktree, `CODEX_HOME/<task>/sessions` and run scratch directories |
| Logs | `~/Library/Logs/Mercury` | Operator uid | Coordinator logs | None |

1. The subdirectory structure, exact modes and ACL entries are defined **only** in `macos-service.md` §7.1–§7.2.
2. `~/MercuryWork` and `~/Library/Mercury` are **withdrawn**. Run directories formerly under `MERCURY_HOME/runs` move to `WORK_ROOT/runs`; artifacts (content-addressed results) stay in `MERCURY_HOME` and are written only by the coordinator.
3. All paths come from one constant module; no document or component hard-codes a second copy.
4. `mercury doctor` verifies the roots, modes, ACLs and the operator home's 0700 mode at every start; failure sets `config_fatal` for agent dispatch.
5. If the operator declines the agent uid (OD-18), `WORK_ROOT` stays at the same path with operator-only permissions, and the sandbox-only restriction of [ADR-013](ADR-013-agent-process-isolation.md) item 8 applies.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| `~/MercuryWork` (A, C Phase 2) | Inside the 0700 home, so unreachable by the agent uid; hostile worktree files sit in a visible home folder |
| `~/Library/Mercury` (D Phase 2) | Same reachability problem |
| `~/Library/Application Support/Mercury/checkouts` (B Phase 2) | Contains a space; inside the 0700 home; mixes agent-writable trees with coordinator state |
| `/opt/mercury` or other root-owned locations | Needs root for routine operations |
| A single root for everything | Either agents could reach the DB, or worktrees would be unreachable |

## Consequences
- **Positive:** a clean trust boundary on disk: agents cannot reach state, credentials or the operator's files; hostile worktree content is outside the operator's home.
- **Positive:** one source of truth for every path.
- **Negative:** `/Users/Shared` is visible to all local users; the 0750 mode and group restrict it to the operator and the agent uid.
- **Negative:** the operator must keep the home at 0700, which can affect other local sharing habits.

## Related requirements
NFR-092; SEC-201, SEC-205, SEC-405; FR-064, FR-120.

## Related findings
RA-03, RD-14, RE-13, RE-19, RC-30, RF-25 (F's provisional ADR-P15).

## Operator decisions
- **OD-18** agent uid (this layout assumes it).
