# ADR-006: Coordinator owns git commit, push and PR creation

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12. Agent B owns the GitHub contract (`integrations/github.md`).

## Context
- Codex `workspace-write` protects `.git`; in a linked worktree a commit writes into the main clone's `.git/worktrees/…` and object store, so it is expected to fail (discovery fact 7; unverified).
- If an agent pushed or opened PRs, it would need a GitHub write token inside a process that executes model-generated commands and reads untrusted repository content.
- The brief requires distinct agent identities and that agent approvals cannot impersonate human approvals (§E, §H).

## Decision
1. **Only `mercuryd`'s Git Publisher** runs `git add/commit/push` and calls the PR endpoints. Agents only edit files in their worktree.
2. Clones are **coordinator-owned** under `~/MercuryWork/clones/<owner>/<repo>`; worktrees under `~/MercuryWork/worktrees/<repo>/<task_id>`. The operator's own clones are never touched.
3. Branch: `mercury/<issue-identifier-lowercase>-<slug>` (e.g. `mercury/jam-123-add-retry`) — contains the Linear identifier so Linear's integration links the PR. Agent B may refine.
4. Commits: authored and committed as the GitHub App bot identity; one commit per implementation round; message body includes trailers:
   ```
   Mercury-Task: tsk_01J…
   Mercury-Authorization: auth_01J… (v2)
   Mercury-Plan: pln_01J… sha256:9f2c…
   Mercury-Run: run_01J…
   Part of JAM-123
   ```
5. Before committing, the Workspace Manager runs **diff guards**: no changes under `.git*` metadata, `.github/workflows/**` (unless authorized and the App has `workflows:write`, which is off by default), instruction files (`AGENTS.md`, `CLAUDE.md`, `.claude/**`, `.codex/**`, `.mcp.json`) unless the plan lists them, no files above size limit, secret scan clean.
6. Push uses a 1-hour App installation token passed through `GIT_ASKPASS` or an in-memory credential helper — never in the remote URL, argv or on disk.
7. The coordinator pushes only to `mercury/*` branches; force-push only to its own task branch after operator choice (conflict C7). It **never** calls merge endpoints.
8. PR body is generated from a template including the authorization summary, approved plan link (artifact hash), test report summary and `Part of JAM-n`.

## Alternatives
- **Codex commits and pushes** (`gh` inside sandbox with network): requires credentials + network in the untrusted execution context; mixes identities. Rejected.
- **Widen Codex writable roots to `.git/worktrees/<name>`** so Codex commits locally, coordinator pushes: possible; gains granular commits, but lets Codex rewrite git metadata (hooks config, refs). Rejected for MVP; revisit if Phase 0 shows it is safe.
- **Claude opens PRs via `gh`**: same credential objection; Claude is the reviewer and should not author.

## Consequences
- Positive: agents hold no GitHub credentials; uniform trailers make audit reconstruction possible (AP-10); the App is always "last pusher", so the operator's approval of the latest push is the only one that counts.
- Negative: commit granularity is per round, not per logical change; coordinator carries git-handling code (conflicts, rebases are out of scope: on base drift the coordinator rebases only if conflict-free, otherwise blocks for a Claude `FAILURE_TRIAGE` decision).

## Related requirements
Brief §E (branch/worktree naming, commit conventions, PR template, token privileges, separation of duties), §H; hard constraint 4 (agent approvals cannot impersonate human approvals); AP-2, AP-3.
