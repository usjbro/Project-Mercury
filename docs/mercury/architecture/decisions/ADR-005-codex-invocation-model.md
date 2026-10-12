# ADR-005: Codex invoked as a supervised `codex exec` subprocess (provisional)

## Status
Proposed — **provisional**. Agent B owns the detailed contract in `integrations/codex.md`; this ADR fixes only the architectural constraints. Date 2026-10-12.

## Context
- Codex CLI 0.162.1: `codex exec` is the stable headless mode with `--json` (JSONL events), `--output-schema`, `-o`, `--cd`, `--sandbox`, `exec resume <thread_id>`. `exec` forces `approval_policy=never`; the **sandbox is the real control**. `workspace-write` blocks network by default and protects `.git`, `.codex`, `.agents`, `.aws`. `mcp-server` is removed; `app-server` is experimental. No whole-run timeout. Exit code is 0 or 1 only (`02-discovery-agent-runtimes.md` §3).
- The TS SDK only wraps `codex exec`.

## Decision
1. Run `codex exec` directly as a child process via the Process Supervisor: own process group, minimal `env` (`PATH`, `HOME`, `CODEX_HOME`, `CODEX_API_KEY`), no GitHub or Linear variables, pinned binary path, `--strict-config`.
2. **Planning:** `--sandbox read-only --cd <worktree at base SHA> --output-schema plan.schema.json -o <run>/output.json --json`.
3. **Implementation:** `codex exec resume <thread_id>` (or a fresh run with the approved plan in the prompt; Agent B decides) with `--sandbox workspace-write`, `-c sandbox_workspace_write.network_access=false`, minimal `shell_environment_policy`.
4. Forbidden flags, enforced by an argv allowlist in the adapter and (if possible) managed `requirements.toml`: `--dangerously-bypass-approvals-and-sandbox`, `--approve-for-me`, `--dangerously-bypass-hook-trust`, `danger-full-access`.
5. Deadlines in monotonic awake time; on expiry SIGINT → SIGTERM → SIGKILL to the process group. Failure classification from JSONL + stderr, not exit code.
6. Dependency installation, if needed, is a separate coordinator step with network (lockfile-based), not a Codex capability.
7. Concurrency 1 until shared-`CODEX_HOME` safety is verified (ASM-A-05); alternatively a per-task `CODEX_HOME`.
8. Codex output files are untrusted until registered as artifacts; instruction files (`AGENTS.md`, `.codex/`, `.claude/`) changed by Codex fail the diff guard unless the plan explicitly authorized them.

## Alternatives
- `@openai/codex-sdk`: acceptable for typed events, but adds no control; direct exec gives exact argv for audit.
- `codex app-server` (JSON-RPC): experimental, fast-changing. Rejected for now.
- Codex Cloud: not local; worktree not on the Mac (a documented past confusion). Rejected.

## Consequences
- Codex cannot commit or push ([ADR-006](ADR-006-coordinator-owns-git-and-pr.md)).
- Version drift is a key risk; startup self-test parses `codex exec --help` for required flags.

## Related requirements
Brief steps 5, 8, 9; §A (failure detection, orphaned processes), §F, §H (command execution restrictions); hard constraint "Codex cannot execute unapproved work"; AP-2.
