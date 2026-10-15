# 00 — Repository and Design Discovery Report

| | |
|---|---|
| Date | 2026-10-15 |
| Method | `git fetch --all`, branch/commit inspection, full read of the TDD and planning/security/testing documents, GitHub PR listing, Linear issue/project search (read-only), script analysis of `planning/issue-breakdown.md` (`tools/devorch/devorch.py dag`) |
| Environment | Claude Code 2.1.296 in a Linux cloud container (Claude Code on the web). **The operator's Mac is not reachable from this session.** |

## 1. Repository state (latest committed)

| Item | Observed |
|---|---|
| Branches | `main` (1 commit, `4cad0ef` "Initial commit": README only) and `claude/mercury-tdd` (39 commits ahead of `main`, head `88396a6` at discovery) |
| Authoritative design branch | **`claude/mercury-tdd`**. It holds `docs/mercury/TDD.md` v1.0-rc1 and all supporting documents. It has **not** been merged and has **no pull request**. |
| TDD status | "Conditionally ready for human review … Not approved for implementation" (TDD §32.3). Operator sign-off is pending. Conditions C1–C7 are open. |
| Pull requests | None (open or closed) |
| CI / workflows | None (`.github/` absent) |
| Agent configuration | None before this work (`.claude/` absent, no `CLAUDE.md`, no `AGENTS.md`) |
| Scripts | None in the repository. Phase 5 validation scripts exist only in an ephemeral session scratchpad (not durable) |
| Application code | **None.** No `src/`, `package.json`, migrations or tests exist |
| Linear | No project or issue matching "Mercury" or "MERC" (read-only search). The 82 MERC issues exist **only as proposals** in `planning/issue-breakdown.md` |
| Branch protection on `main` | Not configured (observed in the design-phase discovery; nothing has changed since) |

## 2. Existing architecture (summary of the authoritative TDD)

- **Production MERCURY**: a local Node.js 24 + TypeScript daemon (`mercuryd`) with SQLite (WAL) under a per-user LaunchAgent. It polls GitHub and Linear, runs Claude as a headless decision service and Codex as a supervised `codex exec`, both under a dedicated macOS uid `_mercuryagent`. The human operator is the sole approver and merger (TDD §1, §7, §15).
- **17 task states**, holds orthogonal to state, INV-01…27 invariants enforced partly by SQLite triggers (state-machine.md).
- **ADR-001…020** are Accepted (several pending operator decisions OD-01…37).
- **Security**: SEC-1xx…9xx, gates G-S1…G-S5, SAC-01…20 (threat-model.md §8.10, §10).
- **Plan**: phases P0a–P0d, M1–M8, M9a–c. 82 issues in 13 epics: 79 base and 3 conditional (MERC-1K1, MERC-3A1, MERC-807b). Planning P90 is about 216 engineer-days. The dependency critical path is about 51 P50 engineer-days (roadmap.md, issue-breakdown.md). **The counts were re-verified by script** (`data/dag.json`): 82 issues, 79 base, 3 conditional, 0 dependency cycles, critical path 51.0 P50 days through 26 issues.

## 3. Current implementation status

**Nothing is implemented.** All work is design. The first implementable issues are blocked on operator actions:

- MERC-020 (operator decision session)
- MERC-021 (GitHub Apps)
- MERC-001 (Mac read-only facts)
- MERC-010/011 (agent-uid install, **[ROOT]**)

## 4. Existing development workflow

There is none for this repository. The legacy Claude↔Codex workflow (Slack, gate scripts, `.worktrees/<slug>`) lives in `usjbro/network_monitor`, which is out of this session's scope. The design work itself was produced by a one-off, conversation-driven multi-agent process. Its state lived in conversation context and the git history of `claude/mercury-tdd`. That process repeatedly lost running subagents to API session limits and had to resume them by hand, which is direct evidence for the durability requirements below.

## 5. Existing agent capabilities (verified in this session)

| Capability | Status | Evidence |
|---|---|---|
| Project subagents in `.claude/agents/*.md` (YAML frontmatter: name, description, tools, disallowedTools, model, permissionMode, maxTurns, skills, mcpServers, hooks, memory, background, isolation, color, effort, initialPrompt, …) | Documented. **Config files not yet exercised by a session** (a newly created `agents/` directory needs a session restart) | code.claude.com/docs/en/sub-agents.md (via claude-code-guide agent, 2026-10-15) |
| Spawning subagents from the main session, parallel, in background, with completion notifications | **Verified in use** (the design phases ran 6 parallel agents) | This session's history |
| Resuming a finished or interrupted subagent with context (`SendMessage`) | **Verified in use** (agents resumed after API rate-limit interruptions) | Same |
| Subagent → subagent direct messaging | Documented for named agents with `SendMessage`. **Not used** by this design (all coordination goes through the orchestrator) | sub-agents.md |
| Nesting (subagents spawning subagents) | Documented, up to 3 levels. **Disabled for specialists** (`Agent` in `disallowedTools`) | sub-agents.md |
| `isolation: worktree` | Documented. It branches from the default branch (`main`), which lacks the design docs. **Not used**: the orchestrator creates explicit worktrees from a recorded base commit instead | worktrees.md |
| Background agents surviving a session/process restart | **UNVERIFIED** (docs only say transcripts persist and can be resumed by resuming the session) | sub-agents.md |
| Permission deny rules for subagents | Documented: deny rules apply to subagents. Bash rules match command text and are **not a security boundary** | permissions.md |
| Remote parallel sessions (`create_session`) | A tool exists in this session. Use for development work is **unverified and not configured** | Tool list |
| Linear and GitHub connectors | Available read/write in this session. **Write use is denied** for development agents by project settings | — |

## 6. Task dependencies

The DAG is generated from `planning/issue-breakdown.md` into `data/dag.json`:

- No cycles.
- The top unblockers are MERC-020 (70 downstream), MERC-021 (68), MERC-030 (64), MERC-101 (63), MERC-102 (56), MERC-103 (46), MERC-104 (44), MERC-001 (43), MERC-106 (40) and MERC-010 (40).
- 38 of the 79 base issues need the Mac or the operator: 20 entirely and 18 for a validation step. Only 41 issues (≈ 89 P50 engineer-days) are executable purely by agents.

## 7. Current limitations

1. **The design is not approved.** Gate 1 (design validation) cannot pass for any implementation task until the operator signs off the TDD or a scoped part of it.
2. **There is one Mac and one operator.** Every T4/T5/ⓗ/[ROOT] task serializes on that lane, so the lane, not agent count, sets the pace.
3. **No branch protection on `main`, and no non-human GitHub identity for development agents.** In this environment, Git pushes and PRs go out under the operator's GitHub authorization, so a PR opened by a development agent may appear as authored by the operator, who then cannot approve it (GitHub forbids self-approval). An operator decision is needed (§8 of `08-quality-gates-and-security.md`, DOD-03).
4. **Session state is volatile.** Subagents do not persist and are lost on interruption. Durable state must live in git (ledger branch) and GitHub.
5. **No toolchain in the repository yet** (no Node project). MERC-030 (repo bootstrap) is a prerequisite for all code.
6. **The cloud container is Linux.** macOS-specific behaviour (launchd, Keychain, Seatbelt, `F_FULLFSYNC`) can only be validated on the Mac, a macOS VM, or GitHub-hosted macOS runners (which cannot run nested VMs).

## 8. Missing orchestration capabilities (what this package adds)

- A durable task ledger and verifier, recovery after context loss, explicit worktree and branch isolation, structured contracts and results, mechanical result validation (diff ⊆ allowed paths, commits exist, tests re-run), gate records, and a resource and cost policy.

## 9. Opportunities for safe parallel development

These follow from `05-dependency-and-critical-path.md` §3.

- **After MERC-101/102 land:**
  - MERC-112 (fakes and scenario runner) parallel with MERC-103/104;
  - MERC-402a (mirror and hardened git) parallel with MERC-103;
  - MERC-303 (decision schemas and wire copies) as soon as MERC-112 exists.
- **After MERC-106:** MERC-201 (GitHub client), MERC-202 (Linear client) and MERC-109 (scheduler) in parallel, with MERC-704 (audit trace) any time after MERC-103.
- **Phase 0 operator lane in parallel with code:** MERC-001/002/003 and MERC-010/011/012 can run on the Mac while agents build M1 against fakes. MERC-107 (process broker) needs MERC-011.
- **Interface-first:** freezing `src/ports/*.ts` (store, process, agents, github, linear, clock) at the start of M1 unlocks adapter work against fakes before the concrete store exists.

## 10. Constraints that prevent parallel development

- The strict M1 chain MERC-101 → 102 → 103 → 104 → 106: each step changes the foundation the next builds on.
- **Shared files.** The DDL migration `0001_initial.sql`, the transition table and the ports directory are single-owner, frozen-before-use artifacts.
- **Security gates**, which cannot be bypassed:
  - G-S2 (SEC-T-20 credential canaries on the real Mac) before any non-sandbox write run;
  - G-S3 before the first push;
  - G-S5 (G-ORG + OD-36) before unattended operation.
- **Root-consent steps** (MERC-010, 011, 107 install parts) and all ⓗ tasks wait on the operator.
- **The approval queue.** Every PR to `main` waits for the human. If the approval queue is large, review quality drops (threat-model RISK-22).

## 11. Unresolved operator decisions relevant to development

- **From the TDD:** OD-01…37, especially OD-01 (merge mode), OD-03/04 (API keys), OD-17, OD-18 (agent uid), OD-20, OD-35 and OD-36.
- **New development-orchestration decisions:** DOD-01…08 (`12-amendments.md` §3).

## 12. Security and infrastructure prerequisites

1. Operator sign-off of the TDD (or a scoped approval for M1).
2. A GitHub ruleset on `project-mercury` `main` requiring a PR and an operator approval (P0d, MERC-030) before the first development PR is merged.
3. A development-agent GitHub identity decision (DOD-03).
4. Phase 0 Mac checks executed by the operator.
5. No real model keys for MERCURY's production adapters until P0c (development agents use the operator's own Claude Code subscription, which is a different system).
