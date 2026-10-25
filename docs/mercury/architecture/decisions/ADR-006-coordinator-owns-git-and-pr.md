# ADR-006: Coordinator owns git commit, push and PR creation

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-06)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent B owns the GitHub contract (`integrations/github.md`); Agent C owns the commit pipeline and worktree reset policy (`architecture/components.md` §9–§10) |
| Related ADRs | [ADR-005](ADR-005-codex-invocation-model.md), [ADR-008](ADR-008-agent-identities-and-merge-governance.md), [ADR-009](ADR-009-system-of-record-split.md), [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md), [ADR-016](ADR-016-filesystem-layout.md), [ADR-020](ADR-020-detached-runs-and-adoption.md) |

## Context
- Codex `workspace-write` protects `.git`; in a linked worktree a commit writes into the mirror's object store, so it is expected to fail (discovery fact 7).
- If an agent pushed or opened PRs, it would need a GitHub write token inside a process that executes model-generated commands and reads untrusted repository content.
- The brief requires distinct agent identities, and agent approvals must not impersonate human approvals (§E, §H).
- Phase 3 found that: (a) a bot `REQUEST_CHANGES` review leaves a PR un-mergeable because MERCURY may not dismiss reviews (RA-04, RB-03, RC-01); (b) coordinator git commands ran inside agent-writable worktrees, where attacker git config and a rewritten `.git` pointer can execute code or redirect a push (RE-03); (c) branch names containing the Linear ID are closing links, which ties branch naming to Linear status ownership (RA-10); (d) git objects were not flushed before the DB recorded their SHA (RD-05).
- The brief's step 9 says Codex "creates a PR". All designs have Codex prepare the *change* and the coordinator prepare the PR. This is a justified deviation (RA-38): it keeps credentials out of the execution context and works with Codex's `.git` protection.

## Decision
1. **Only `mercuryd`** creates commits, pushes and calls PR endpoints. Agents only edit files in their worktree.
2. **Repositories:** one coordinator-owned bare **mirror** per target repository and one linked worktree per task, under `WORK_ROOT` ([ADR-016](ADR-016-filesystem-layout.md); paths in `operations/macos-service.md` §7.1). The operator's own clones are never touched.
3. **Hardened git (RD-17; SEC-401/402).** The coordinator never runs git with configuration read from an agent-writable worktree:
   - commits are built with plumbing against the mirror (`GIT_DIR=<mirror>`, the worktree read as data), with hooks, fsmonitor and protocol helpers disabled and global/system config ignored (full flag set in `components.md` §9);
   - the worktree `.git` pointer is verified before every git invocation that touches the worktree;
   - **pushes happen from the mirror by SHA**, with `GIT_ASKPASS` reading a short-lived `mercury-bot` installation token from an inherited fd. There is one credential-delivery mechanism.
4. **Durability (RD-11):** the mirror uses `core.fsync=committed,reference`; the order is git commit → fsync → DB transaction recording the SHA ([ADR-020](ADR-020-detached-runs-and-adoption.md)).
5. **Branch naming follows the Linear status mode** ([ADR-009](ADR-009-system-of-record-split.md), OD-06):
   - `integration_owns_done` (pilot default): the branch contains the issue identifier, so Linear's integration links and closes the issue;
   - `mercury_owns_all`: the branch omits the identifier and the PR uses non-closing phrasing.
   The exact pattern is in `github.md`.
6. **Commits** are authored as the `mercury-bot` identity, one commit per implementation round, with `Mercury-Task`, `Mercury-Authorization`, `Mercury-Plan` and `Mercury-Run` trailers (`github.md`). Agent-authored text in commit messages and PR bodies passes the public-sink renderer (mentions, closing keywords and Linear magic words neutralised; RE-12).
7. **Pre-commit and pre-push controls** (deterministic, before any push): diff gate against the plan scope, instruction-file and protected-path checks, secret scan, `MERCURY / policy` pre-checks ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)). Lists live in `codex.md` §9 and `threat-model.md` (SEC-309, SEC-310, SEC-502).
8. **PRs open as drafts** and leave draft only when `MERCURY / claude-review` succeeds; the human review request is sent at that point (RD-18).
9. **Reviews are `COMMENT` only.** MERCURY never submits `APPROVE` or `REQUEST_CHANGES`, never dismisses reviews, and never calls merge, `update-branch` or auto-merge endpoints. The GitHub adapter enforces an endpoint allowlist (SEC-102). The merge gate is the required check run ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)).
10. **Base drift and conflicts:** the coordinator merges the base into the task branch only if conflict-free; otherwise the task goes to `CHANGES_REQUESTED(merge_conflict)` and a Claude `revision_request` run produces the instruction for Codex (`state-machine.md`). There is no `FAILURE_TRIAGE` path.
11. **Worktree reset** after a failed or interrupted step follows the single definition in `components.md` §9: archive uncommitted changes as a patch artifact, `reset --hard` to the last durable commit (or `base_sha`), `clean -ffd` (`-x` only when `deps_install` is re-queued). There are no checkpoint commits.
12. Force-push is used only on MERCURY's own task branch, and only where `github.md` allows it (for example the operator's `resume --reset` after a foreign push).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Codex commits and pushes (`gh` in the sandbox with network) | Credentials and network inside the untrusted execution context; mixed identities |
| Widen Codex writable roots to `.git/worktrees/<name>` so Codex commits locally | Lets Codex rewrite git metadata (hooks config, refs) |
| Claude opens PRs | Same credential objection; the reviewer should not author |
| Porcelain git inside the worktree (Phase 2 text) | Executes attacker-controlled config as the coordinator and can redirect a push with the token (RE-03) |
| Push credential through a control-socket helper or env variables | Turns the socket into a token dispenser; env is visible to same-uid `ps` (RE-03). Replaced by the fd-based askpass |
| Bot `REQUEST_CHANGES` reviews | Creates a blocking review that MERCURY cannot dismiss (RA-04) |
| Checkpoint commits during implementation | Pollute history and complicate the binding of reviews to SHAs; the patch archive covers the recovery need |

## Consequences
- **Positive:** agents hold no GitHub credentials; uniform trailers support audit reconstruction (AP-10); the App is always the last pusher, so only the operator's approval of the latest push counts.
- **Positive:** a hostile worktree cannot influence coordinator git execution or redirect a push.
- **Negative:** commit granularity is one commit per implementation round. The coordinator carries git plumbing code.
- **Negative:** draft-until-reviewed requires target repositories to run CI on draft PRs (an onboarding requirement in `github.md`).

## Related requirements
FR-120, FR-124, FR-140, FR-141, FR-142, FR-143, FR-165, FR-180, FR-184; CON-007, CON-008, CON-010; NFR-050; SEC-102, SEC-401, SEC-402, SEC-502.

## Related findings
RA-04, RA-10, RA-11, RA-38, RB-03, RC-01, RE-03, RE-12, RD-05.

## Operator decisions
- **OD-06** Linear `Done` owner, which fixes the branch naming pattern (default `integration_owns_done`).

## Revision history
- Phase 4: `COMMENT`-only reviews; hardened plumbing commits and mirror pushes; fd askpass; durability order; branch naming tied to OD-06; draft PRs; merge-conflict path via `revision_request`; single worktree reset policy; brief step 9 deviation recorded.
