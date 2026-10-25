# ADR-005: Codex invoked as a supervised `codex exec` run under the agent uid

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-07, OD-09)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2 as provisional) |
| Owner | Agent A. Agent B owns the detailed contract (`integrations/codex.md`); Agent D owns `agent-exec` and the Seatbelt profiles (`operations/macos-service.md`) |
| Related ADRs | [ADR-006](ADR-006-coordinator-owns-git-and-pr.md), [ADR-013](ADR-013-agent-process-isolation.md), [ADR-016](ADR-016-filesystem-layout.md), [ADR-020](ADR-020-detached-runs-and-adoption.md) |

## Context
- Codex CLI 0.162.1: `codex exec` is the stable headless mode with `--json`, `--output-schema`, `-o`, `--cd`, `--sandbox` and `exec resume <thread_id>`. `exec` forces `approval_policy=never`, so **the sandbox is the real control**. `workspace-write` blocks network by default and protects `.git`, `.codex`, `.agents`. There is no whole-run timeout, and the exit code is only 0 or 1 (`02-discovery-agent-runtimes.md` §3).
- Phase 3 found that this ADR left open choices B had already made (fresh implementation thread, RA-36, RF-37), that `CODEX_HOME` was per run in some documents and per task in others (RA-08), and that Codex, the test runner and `deps_install` ran as the operator's uid (RE-01, RE-02).

## Decision
1. **Launch.** Every Codex run is started detached through `agent-exec` as `_mercuryagent` ([ADR-013](ADR-013-agent-process-isolation.md)), with file-based stdio, an environment allowlist, the OpenAI project key on fd 3, a pinned binary, and an argv validated against a fixed grammar per kind (`codex_plan`, `codex_implement`, `codex_revise`). Runs are adoptable after a coordinator restart ([ADR-020](ADR-020-detached-runs-and-adoption.md)).
2. **Planning:** read-only sandbox, `--cd` at the task worktree on `base_sha`, `--output-schema` (wire copy), JSONL events.
3. **Implementation:** a **fresh** Codex thread whose prompt carries the approved plan bytes and the plan hash (`plan_sha256`). It never resumes the planning thread. Sandbox `workspace-write`, **no network** (OD-09). Implementation revisions may resume the implementation thread (`codex.md` §3).
4. **Per-task `CODEX_HOME`** under `WORK_ROOT/codex-home/<task_id>/`: a coordinator-generated, read-only `config.toml` (regenerated and byte-verified before every run) and an agent-writable `sessions/` directory, archived at cleanup (RD-15; SEC-203 as amended).
5. **Forbidden flags** are rejected by the adapter's argv grammar and by `agent-exec`: `--dangerously-bypass-approvals-and-sandbox`, `danger-full-access`, `--dangerously-bypass-hook-trust` and equivalents (list in `codex.md`).
6. **Liveness and deadlines.** Liveness is stdout growth **or** process-group CPU-time progress, sampled through `agent-ctl stats` (RD-15). The stall threshold during a running command is at least the repository's test timeout. Hard deadlines are in credited awake time ([ADR-020](ADR-020-detached-runs-and-adoption.md)); values are in D's parameter table. Failure classes come from JSONL and stderr, not the exit code. Schema-rejection errors classify as `config_fatal`.
7. **Code Codex wrote is executed only as the agent uid, under a fail-closed Seatbelt profile** (RD-17):
   - `verify` (L2 tests) has **no network**. If no sandbox mechanism is available, L2 is recorded `not_run` and CI is the gate; it never runs unsandboxed.
   - `deps_install` is a separate coordinator step, not a Codex capability. It uses `--ignore-scripts`, a registry allowlist, and only lockfiles whose change the operator acknowledged through `MERCURY / policy` ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)).
8. **Toolchains** are provisioned per repository by `mercury toolchain sync` into `WORK_ROOT/toolchains` (coordinator-owned; agent read and execute only). The agent `HOME` holds caches only.
9. **Concurrency** defaults (OD-07) live in D's parameter table; raising Codex concurrency above 1 requires the Phase 0 parallel-run check.
10. Codex output files are untrusted until registered as artifacts. Instruction files (`AGENTS.md`, `.codex/`, `.claude/`, `.mcp.json`) and protected paths changed by Codex fail the diff gate or escalate through `MERCURY / policy` (`codex.md` §9; SEC-209, SEC-310).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| `@openai/codex-sdk` | Adds typed events but no control; direct exec gives exact argv for audit and for the `agent-exec` grammar |
| `codex app-server` (JSON-RPC) | Experimental and fast-changing |
| Codex Cloud | Not local; the worktree is not on the Mac (CON-016) |
| Resume the planning thread for implementation | Carries planning-phase context (possibly injected) into the write-capable run and weakens the binding to the approved plan bytes |
| Per-run `CODEX_HOME` | Deletes the session files that revision runs resume (RA-08) |
| Shared `CODEX_HOME` | Cross-task state and unverified concurrent safety |
| Codex or tests as the operator's uid with Seatbelt deny rules only | Seatbelt reads are broad; agent-executed code could read the operator's credentials (RE-01, RE-02). Allowed only on the sandbox repository before SEC-T-20 passes ([ADR-013](ADR-013-agent-process-isolation.md)) |
| `deps_install` with lifecycle scripts or open egress | A lockfile can exfiltrate through `resolved` URLs and scripts run attacker code (RE-02) |

## Consequences
- **Positive:** Codex can neither read credentials nor commit or push ([ADR-006](ADR-006-coordinator-owns-git-and-pr.md)); every Codex run is bound to one authorization and, for implementation, one plan hash.
- **Positive:** Codex runs survive a coordinator crash and are adopted, so work is not lost.
- **Negative:** per-repo toolchains must be provisioned for the agent uid; some repositories will need operator setup before onboarding.
- **Negative:** version drift is a key risk; the startup self-test checks required flags against the pinned version (NFR-090, NFR-093).

## Related requirements
FR-100, FR-103, FR-120, FR-121, FR-122, FR-123, FR-124, FR-125, FR-044; CON-005, CON-006, CON-016; NFR-083, NFR-090, NFR-093; SEC-201, SEC-203, SEC-209, SEC-703.

## Related findings
RA-02, RA-08, RA-36, RF-37, RE-01, RE-02, RD-13, RD-15, RD-26, RB-01, RB-07, RC-05.

## Operator decisions
- **OD-07** concurrency (default Codex 1, Claude 2, 1 per repository).
- **OD-09** Codex never has network; `deps_install` uses `--ignore-scripts`.
- Depends on **OD-18** (agent uid, adopted) through [ADR-013](ADR-013-agent-process-isolation.md).

## Revision history
- Phase 4: provisional status removed; fresh implementation thread; per-task `CODEX_HOME`; agent-uid launch; `verify` and `deps_install` as agent uid under Seatbelt; CPU-based liveness; toolchains; absorbs F's provisional ADR-P14 (dependency installation).
