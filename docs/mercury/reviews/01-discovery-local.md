# Discovery — Local Execution Environment (orchestrator observation)

Collected 2026-10-12 by the orchestrating session, read-only.

| Item | Observed | Implication |
|---|---|---|
| Host where this design session runs | Linux x86_64 cloud container (`Linux 6.18.44`), ephemeral, managed by Claude Code on the web | **The operator's Mac is not reachable from this session.** No macOS facts (version, launchd, pmset, Keychain, sleep settings, directories) could be observed. |
| Claude Code in this container | `2.1.296 (Claude Code)` at `/opt/node22/bin/claude` | Confirms a recent 2.x line exists; the Mac's installed version is **unknown**. |
| Codex CLI in this container | Not installed (`codex: command not found`) | Codex version, config (`~/.codex/config.toml`), AGENTS.md, auth mode on the Mac are **unknown**. |
| Node.js | `v22.22.0` | Node 22 LTS assumed viable baseline; Mac version unknown. |
| sqlite3 CLI / launchctl | Not present (Linux) | Not evidence about the Mac. |
| `~/.claude` in container | Cloud-session scaffolding only (`skills/session-start-hook`, plugins) — not the operator's Mac configuration | Operator's agents/skills/hooks/CLAUDE.md on the Mac are **unknown**. |
| Repository `usjbro/project-mercury` | Contains only `README.md` (one "Initial commit") | Greenfield. No existing coordinator, scripts, CI, or settings to inherit. |

## Consequence for the design
All statements about the Mac runtime, local Claude/Codex configuration, and the existing local Slack bridge (if any) are **assumptions** until verified on the Mac. The TDD must carry a "Phase 0 — environment verification" milestone with a read-only checklist the operator (or a locally running Claude session) executes before implementation.
