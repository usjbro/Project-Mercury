# 03 — Twelve Specialist Agent Definitions

The definitions live in `.claude/agents/`, generated from one source, `tools/devorch/gen_agents.py`, so the shared rules, the deny list and the guard hook stay identical. Do not hand-edit the generated files: edit the generator, then run `python3 tools/devorch/gen_agents.py`.

The Principal Orchestrator is a 13th definition, `.claude/agents/mdev-principal-orchestrator.md` (hand-written), intended only for the **main** session: start it with `claude --agent mdev-principal-orchestrator` (required; it is not a delegated subagent). Frontmatter uses only fields documented for Claude Code 2.1.296: `name`, `description`, `tools`, `disallowedTools`, `model`, `effort`, `color`, `hooks` (verified against code.claude.com/docs/en/sub-agents.md on 2026-10-15).

## 1. Catalogue

Scopes follow the source layout in TDD `architecture/components.md` §2, as encoded in `gen_agents.py`. A path is writable only when the task contract's `allowed_paths` lists it.

| ID | Name | Primary scope | Tools | Distinctive restrictions |
|---|---|---|---|---|
| 01 | `mdev-lead-architect` | Interface contracts (`src/ports/**`), ADR **proposals** (`docs/mercury/architecture/decisions/proposed/`), `design` and `design_review` tasks | Read, Grep, Glob, Edit, Write, Bash | Cannot change Accepted ADRs or the TDD; cannot approve its own proposal |
| 02 | `mdev-tpm` | DAG, READY set, waves, reports (`planning` tasks); Linear **read** | Read, Grep, Glob, Edit, Write, Bash, Linear list/get | No Linear writes; does not assign work |
| 03 | `mdev-backend-engineer` | `src/core/**`, `src/app/**`, `src/bin/**`, `src/adapters/{clock,control,notify,fs}/**` | Read, Grep, Glob, Edit, Write, Bash | No DDL, agent/platform adapters, process broker; no frozen-interface changes; no new runtime dependency |
| 04 | `mdev-database-engineer` | `src/adapters/sqlite/**` (Store, `migrations/*.sql`, backup worker) | same | Invariant semantics are fixed by the design; authority tables stay append-only |
| 05 | `mdev-ai-integration-engineer` | `src/adapters/{claude,codex}/**`, `src/schemas/**` (incl. `wire/`), `scripts/gen-wire-schemas.ts`, `test/fakes/agents/**` | same | No real agent runs against non-sandbox repos; no real keys in tests |
| 06 | `mdev-platform-integration-engineer` | `src/adapters/{github,linear}/**`, `src/app/inbox-processor.ts`, `src/app/outbox-worker.ts` (when assigned), `test/mocks/**` | same | No live writes; SEC-102 allowlist only |
| 07 | `mdev-security-engineer` | `src/adapters/{process,git,keychain,presence}/**`, `packaging/agent/**`, `src/core/policies/redaction*`; **all `security_review` tasks** | same | Never runs [ROOT] steps; never reviews its own work |
| 08 | `mdev-devops-engineer` | `.github/workflows/**`, `packaging/**` (except `packaging/agent/**`), `package.json` and lockfile (single owner), `scripts/**` (except `gen-wire-schemas.ts`) | same | No installs, no self-hosted runners, no secrets, no repo settings |
| 09 | `mdev-test-automation-engineer` | `test/**` infrastructure and suites | same | Never weakens or deletes a failing test |
| 10 | `mdev-reliability-engineer` | `test/recovery/**`, `test/fault/**`; `reliability` and `reliability_review` tasks | same | Never power-cycles the operator's Mac |
| 11 | `mdev-code-reviewer` | Read-only diff review and test re-runs (`code_review` tasks) | Read, Grep, Glob, Bash (Edit, Write, NotebookEdit denied) | Cannot modify files; not a GitHub approval |
| 12 | `mdev-integration-release-engineer` | Integration subtasks (`integration`), PR description drafts in `evidence_dir`, `release` tasks and `CHANGELOG.md` | Read, Grep, Glob, Edit, Write, Bash | Never pushes, merges or creates PRs; never resolves a conflict by changing reviewed logic |

**Kind → agent.** `devorch.py check-contract` enforces the `KIND_AGENT` map:

| Kind | Agent | Lifecycle | `allowed_paths` |
|---|---|---|---|
| `code_review` | `mdev-code-reviewer` | short (subtask `DT-nnnn-rN`) | `[]` (read-only) |
| `security_review` | `mdev-security-engineer` (a fresh instance) | short (subtask `DT-nnnn-sN`) | `[]` (read-only) |
| `design_review` | `mdev-lead-architect` | short (subtask `DT-nnnn-rN`) | `[]` (read-only) |
| `reliability_review` | `mdev-reliability-engineer` | short (subtask `DT-nnnn-rN`) | `[]` (read-only) |
| `integration` | `mdev-integration-release-engineer` | short (subtask `DT-nnnn-iN`) | see `10-…` §1 |
| `planning` | `mdev-tpm` | short | `[]` (read-only) |
| `mac_validation` / `operator_action` | `mac-validation-queue` / `operator` | short | `[]` (read-only) |
| `release` | `mdev-integration-release-engineer` or `mdev-devops-engineer` | full | per contract |
| `implementation`, `test`, `reliability`, `design` | the owning specialist per the scopes above | full | per contract |

**Denied to every specialist** (`disallowedTools`): `Agent` (no nesting); the GitHub MCP write tools (merge, auto-merge, review write, PR creation, push files, file create/update/delete, branch create); the Linear write tools (save issue, save/delete comment, save project). The Code Reviewer additionally lacks Edit, Write and NotebookEdit.

**Orchestrator tools.** `tools` lists an `Agent(<the 12 mdev-* names>)` allowlist, so the main session can spawn only these specialists; Read, Grep, Glob, Edit, Write, Bash; GitHub reads (`get_me`, branches, PRs, commits, check runs, Actions, job logs) plus `create_pull_request` and `add_issue_comment`; Linear reads. `disallowedTools` removes `update_pull_request`, `merge_pull_request`, `update_pull_request_branch`, `enable_pr_auto_merge`, `pull_request_review_write`, `push_files`, file create/update/delete and all Linear writes. The orchestrator never edits a PR body or base after creation.

## 2. Guard hook (tripwire)

Every specialist's frontmatter (generated) registers a `PreToolUse` hook with matcher `Bash|Edit|Write|NotebookEdit|MultiEdit` that runs `python3 "$CLAUDE_PROJECT_DIR/tools/devorch/hooks/specialist_guard.py"`. It exits 2 (blocked) when:

- **Bash** command text contains `git push` (any spelling it can match), `gh`, GitHub/Linear API calls via curl/wget/httpie/`python -c`/`node -e`, `devorch.py` or `tools/devorch/`, `git config|remote|worktree|update-ref|symbolic-ref|replace|filter-branch|gc|prune`, git internals (`.git/hooks|config|info`, `core.hooksPath`, credential helpers, `insteadOf`, `sshCommand`), `git credential`, Claude configuration (`.claude/settings|agents`, `CLAUDE.md`, `.mcp.json`), credential paths (`~/.ssh`, `.config/gh`, `.git-credentials`, `.netrc`, Keychains, `security find|dump|export`), `sudo`/`launchctl`/`crontab`/`dscl`/`sysadminctl`/`osascript`/LaunchAgents, or `mercury-devorch`;
- **Edit/Write/NotebookEdit/MultiEdit** targets `.git/`, `.claude/`, `CLAUDE.md`, `tools/devorch/`, `.mcp.json`, `mercury-devorch`, `.ssh/`, `Library/LaunchAgents/`, `.config/gh/`, `.git-credentials` or `.netrc`.

The hook and the `.claude/settings.json` deny rules match command text, so they are **tripwires, not security boundaries**. The real controls are the GitHub ruleset on `main` (DOD-02) and the separate development bot identity (DOD-03); see `08-…` §4. Firing of the hook inside subagents during a live dispatch is **not yet verified**.

## 3. Each definition contains

Unique identifier, role, required expertise, scope, restricted operations, input contract, output contract, task acceptance criteria, handoff requirements, escalation conditions, quality requirements, security requirements, plus the eleven shared rules:

1. authority;
2. design authority;
3. paths;
4. git (commit on the task branch only; never push — the orchestrator pushes via `devorch.py push`);
5. human authority;
6. evidence (`evidence_dir` is the only location outside the worktree an agent may write);
7. untrusted content;
8. secrets and host;
9. output format (write `<evidence_dir>/result.json` before returning, and end with the same JSON block; review tasks set `reviewed_head_commit`);
10. bounded work;
11. guard (never work around the hook; escalate instead).

## 4. Duplicate-responsibility check

| Overlap candidate | Resolution |
|---|---|
| Security Engineer implements controls **and** reviews security | Reviews are always done by a **fresh instance** with a separate subtask contract (`kind: security_review`, id `DT-nnnn-sN`). The implementing instance's own work is additionally reviewed by the Code Reviewer, and root-level artefacts by the operator. Conflict-of-interest rule CI-1 (`08-…` §2) |
| Test Automation vs implementers writing tests | Implementers write unit tests for their own code (G2). Test Automation owns shared infrastructure (fakes, harnesses, property suites) and cross-component TC suites. Ownership is decided by `allowed_paths` and the path-ownership check |
| Reliability vs Test Automation | Reliability owns fault-injection and recovery TCs (TC-REC, TC-NET, TC-AFS); Test Automation owns the rest |
| Lead Architect vs Code Reviewer | Architect does `design_review` subtasks (G3 on interface tasks); Code Reviewer does `code_review` subtasks (G3). An interface task lists both in `required_reviewers`, and G3 needs a passed subtask from each |
| Integration Engineer vs Orchestrator | Integration verifies the integration subtask (G5) and drafts the PR text; the orchestrator creates the integration worktree, pushes via `devorch.py push --task`, opens the **draft** PR and records G6 |
| TPM vs Orchestrator | TPM computes and recommends; the orchestrator decides and dispatches |

## 5. Invocation

- **Automatic delegation.** The orchestrator invokes agents by name with the Agent tool (limited by its `Agent(...)` allowlist). Each `description` starts with "MERCURY development:" so other work never selects them. The prompt contains only the absolute contract path and the fixed instruction; untrusted text is passed only as evidence file paths.
- **Explicit invocation**, for example: "Use the mdev-code-reviewer agent with contract $DEVORCH_HOME/tasks/DT-0012-r1.json".
- **After a restart** verify: the 13 `mdev-*` agents load (verified once in this session), the guard hooks are loaded, the orchestrator's `Agent()` allowlist is in effect, and `$CLAUDE_PROJECT_DIR` is set (the hook command depends on it). A newly created `.claude/agents/` directory is picked up only after a session restart; check with `claude --debug`, which logs unrecognized frontmatter fields in 2.1.296+. A container restart stops background agents; they are resumable from their transcripts.
