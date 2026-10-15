# 03 — Twelve Specialist Agent Definitions

The definitions live in `.claude/agents/`, generated from one source, `tools/devorch/gen_agents.py`, so the shared rules stay identical. Do not hand-edit the generated files: edit the generator, then run `python3 tools/devorch/gen_agents.py`.

The Principal Orchestrator is a 13th definition, `.claude/agents/mdev-principal-orchestrator.md`, intended only for the **main** session. Frontmatter uses only fields documented for Claude Code 2.1.296: `name`, `description`, `tools`, `disallowedTools`, `model`, `effort`, `color` (verified against code.claude.com/docs/en/sub-agents.md on 2026-10-15).

## 1. Catalogue

| ID | Name | Primary scope (paths are allowed only when the contract lists them) | Tools | Distinctive restrictions |
|---|---|---|---|---|
| 01 | `mdev-lead-architect` | Interface contracts (`src/ports/**`), ADR **proposals**, design reviews | Read, Grep, Glob, Edit, Write, Bash | Cannot change Accepted ADRs or the TDD; cannot approve its own proposal |
| 02 | `mdev-tpm` | DAG, READY set, waves, reports; Linear **read** | Read, Grep, Glob, Edit, Write, Bash, Linear list/get | No Linear writes; does not assign work |
| 03 | `mdev-backend-engineer` | `src/core`, `src/app`, `src/cli` | Read, Grep, Glob, Edit, Write, Bash | No DDL, adapters, broker code; no frozen-interface changes |
| 04 | `mdev-database-engineer` | `src/store`, `migrations` | same | Invariant semantics are fixed by the design |
| 05 | `mdev-ai-integration-engineer` | `src/adapters/{claude,codex}`, wire copies, fake agents | same | No real agent runs against non-sandbox repos; no real keys in tests |
| 06 | `mdev-platform-integration-engineer` | `src/adapters/{github,linear}`, pollers, outbox handlers, mocks | same | No live writes; allowlist only |
| 07 | `mdev-security-engineer` | `src/security`, agent-exec/agent-ctl, sandbox profiles; **all security reviews** | same | Never runs [ROOT] steps; never reviews its own work |
| 08 | `mdev-devops-engineer` | MERCURY's own CI, packaging, scripts, ops code | same | No installs, no self-hosted runners, no secrets, no repo settings |
| 09 | `mdev-test-automation-engineer` | `test/**` infrastructure and suites | same | Never weakens or deletes a failing test |
| 10 | `mdev-reliability-engineer` | Fault injection, recovery suites | same | Never power-cycles the operator's Mac |
| 11 | `mdev-code-reviewer` | Read-only diff review and test re-runs | Read, Grep, Glob, Bash (Edit/Write denied) | Cannot modify files; not a GitHub approval |
| 12 | `mdev-integration-release-engineer` | Local `devint/*` integration branches, PR drafts, release notes | Read, Grep, Glob, Edit, Write, Bash | Never pushes or merges; never resolves a conflict by changing reviewed logic |

**Denied to every specialist** (`disallowedTools`): `Agent` (no nesting), and the GitHub MCP write tools: merge, auto-merge, review write, PR creation, push files, file create/update/delete, branch create. Also the Linear write tools: save issue, comment, project. The orchestrator additionally lacks merge, auto-merge, review write and update-branch.

## 2. Each definition contains

Unique identifier, role, required expertise, scope, restricted operations, input contract, output contract, task acceptance criteria, handoff requirements, escalation conditions, quality requirements, security requirements, plus the ten shared rules:

1. authority;
2. design authority;
3. paths;
4. git;
5. human authority;
6. evidence;
7. untrusted content;
8. secrets and host;
9. output format;
10. bounded work.

## 3. Duplicate-responsibility check

| Overlap candidate | Resolution |
|---|---|
| Security Engineer implements controls **and** reviews security | Reviews are always done by a **fresh instance** with a separate contract (`kind: security_review`). The implementing instance's own work is additionally reviewed by the Code Reviewer, and root-level artefacts by the operator. Recorded as conflict-of-interest rule CI-1 (`08-…` §2) |
| Test Automation vs implementers writing tests | Implementers write unit tests for their own code (Gate 2). Test Automation owns shared infrastructure (fakes, harnesses, property suites) and cross-component TC suites. Ownership is decided by `allowed_paths` in each contract |
| Reliability vs Test Automation | Reliability owns fault-injection and recovery TCs (TC-REC, TC-NET, TC-AFS); Test Automation owns the rest |
| Lead Architect vs Code Reviewer | Architect reviews design conformance (G1, and G3 on interface tasks); Code Reviewer reviews implementation (G3). An interface task needs both |
| Integration Engineer vs Orchestrator | Integration builds and verifies the integration branch (G5) and drafts the PR; only the orchestrator pushes and opens the PR (G6) |
| TPM vs Orchestrator | TPM computes and recommends; the orchestrator decides and dispatches |

## 4. Invocation

- **Automatic delegation.** The orchestrator invokes agents by name with the Agent tool. Each `description` starts with "MERCURY development:" so other work never selects them.
- **Explicit invocation**, for example: "Use the mdev-code-reviewer agent with contract $DEVORCH_HOME/tasks/DT-0012-r1.json".
- **New-directory caveat.** A newly created `.claude/agents/` directory is picked up only after a session restart. Verify with `claude --debug`, which logs unrecognized frontmatter fields in 2.1.296+, and `claude plugin validate .claude` where available.
