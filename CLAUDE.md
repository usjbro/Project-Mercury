# Project MERCURY — repository guidance for Claude Code

- The authoritative design is `docs/mercury/TDD.md` and the documents it names as owners. Do not change design documents without an operator-approved amendment.
- **Building MERCURY** uses the temporary development orchestration system in `docs/mercury/development-orchestration/` (start with its `README.md`). The Principal Orchestrator runs as the main session (`claude --agent mdev-principal-orchestrator`); specialists are `.claude/agents/mdev-*.md`.
- This development system is **not** production MERCURY and must never weaken the production security model.
- Only the repository owner approves and merges pull requests into `main`. No agent merges, approves, enables auto-merge, or changes repository settings, rulesets, Apps or credentials.
- No privileged host changes (sudo, launchd installs, macOS users, Keychain): prepare scripts, the operator runs them.
