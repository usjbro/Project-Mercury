# 06 — Worktree and Branch Isolation Strategy

## 1. Layout

```text
<parent>/
  Project-Mercury/            main checkout (orchestrator's cwd); never used for task edits
  mercury-devorch/            $DEVORCH_HOME: worktree of branch devorch/state (ledger, contracts,
                              imported evidence, facts, baseline, LOCK, ESCALATIONS.md); orchestrator only
  mercury-evidence/           $DEVORCH_EVIDENCE: agent-writable evidence root, OUTSIDE $DEVORCH_HOME
    DT-0042/attempt-1/        a contract's evidence_dir (result.json, logs)
  mercury-wt/DT-0042/         one worktree per full-lifecycle task
  mercury-wt/DT-0042-r1/      fresh detached checkouts at the reviewed head for review subtasks and for the G2 re-run
  mercury-wt/DT-0042-i1/      integration worktrees, created by the orchestrator
```

- **Evidence flow.** Specialists write only to their contract's `evidence_dir` under `$DEVORCH_EVIDENCE`. The orchestrator copies it into `$DEVORCH_HOME/evidence/<task>/attempt-N/` with `devorch.py import-evidence` (adds `MANIFEST.json` with SHA-256 per file). `check-contract` refuses an `evidence_dir` inside `$DEVORCH_HOME`.
- **Ledger worktree.** `devorch.py` requires `$DEVORCH_HOME` to be a worktree on `devorch/state` and refuses to run from inside `mercury-wt/` (task worktrees). The branch `devorch/state` does not exist yet; the operator creates it during bootstrap.
- **Worktree creation.** Only the orchestrator creates worktrees (the guard hook blocks `git worktree` for specialists), with repository hooks disabled:
  `git -c core.hooksPath=/dev/null worktree add -b <branch> <worktree> <base_commit>`.

Worktrees live **outside** the main checkout, so tools that walk the repository never see other tasks' files. On the operator's Mac the parent directory must not be in a TCC-protected folder (`~/Documents`, `~/Desktop`, `~/Downloads`; same reason as ADR-016).

## 2. Names

| Object | Convention | Example |
|---|---|---|
| Development task id | `DT-nnnn`; subtasks add `-rN` (code/design/reliability review), `-sN` (security review), `-iN` (integration) and set `parent_task_id` / `covers_tasks` | `DT-0042`, `DT-0042-r1`, `DT-0042-s1`, `DT-0042-i1` |
| Task branch | `dev/merc-<id>-<slug>` or `dev/dt-<nnnn>-<slug>` for non-MERC tasks; slug ≤ 40 chars `[a-z0-9-]` (schema pattern `^dev/(merc-[0-9a-z]+\|dt-[0-9]{4})-[a-z0-9-]{1,40}$`). Review subtasks name the parent's branch | `dev/merc-107-process-broker` |
| Integration branch | Must match the same schema pattern: `dev/dt-<nnnn>-int-<wave>-<n>`, where `DT-nnnn` is the integration subtask's base id. Local only: `devorch.py push --task` refuses it (no G1–G5) | `dev/dt-0042-int-w2-1` |
| Ledger branch | `devorch/state` (orphan history; never merged into `main`) | — |
| Worktree path | `<parent>/mercury-wt/<task_id>` | `../mercury-wt/DT-0042` |

`dev/*` branches never collide with production MERCURY's `mercury/*` branch namespace (github.md).

## 3. Commits

- **Subject format:** Conventional Commits: `<type>(<scope>): <summary>`.
- **Trailers, mandatory:**
  ```text
  Devorch-Task: DT-0042
  Devorch-Contract: 1
  Merc-Issue: MERC-107
  Devorch-Agent: mdev-security-engineer
  ```
  The ledger and git history can then be joined without trusting either alone.
- **Granularity:** one logical change per commit; no merge commits on task branches.

## 4. Base commit and file ownership

- **`base_commit`** is the tip of `main`, or the approved stack base (§6), at dispatch. It is recorded in the contract, and `check-result` enforces ancestry.
- **Path-ownership registry.** This is the union of `allowed_paths` over all primary (non-subtask, writing) tasks in RUNNING, AWAITING_REVIEW, AWAITING_INTEGRATION and AWAITING_HUMAN. `check-contract` refuses a contract whose `allowed_paths` overlap the registry (conservative literal-prefix test: when in doubt, conflict). Read-only kinds have `allowed_paths: []` and own nothing.
- **Shared files** need an explicit coordination strategy:

| Shared artefact | Owner | Strategy |
|---|---|---|
| `src/ports/**` (interfaces) | Lead Architect | Freeze task (`interface_frozen` event records file SHA-256); consumers depend on `INTERFACE_FROZEN`; changes require a new design task + operator approval if it alters an approved contract |
| `migrations/0001_initial.sql` and later migrations | Database Engineer | Single-writer; other agents request changes via escalation |
| Transition table (`src/core/transitions.ts`) | Backend Engineer | Single-writer |
| `package.json`, lockfile | DevOps Engineer | Others request dependencies in `outstanding_dependencies`; a DevOps task adds them; lockfile changes are security-reviewed (supply chain, SEC-7xx) |
| `test/fakes/**` | Test Automation | Others extend via contracts that list the specific file |
| `docs/mercury/**` | Operator-approved amendments only | Never in implementation contracts |

## 5. Conflict detection and integration

- Before dispatch: the path-ownership check.
- Before G5: the Integration Engineer, in an orchestrator-created integration worktree, merges all covered tasks onto the integration branch from current `main` (`10-…` §1).
  - **Textual conflicts** fail G5 for the later task.
  - **Semantic conflicts** are caught by the full test suite on the integration head.
  - **`git range-diff` / patch-id** proves that each integrated commit equals its reviewed commit.
- After a human merge to `main`: an open task whose base is behind `main` and must move gets a new `base_commit`. That changes the contract core, so the orchestrator records `contract_revised` (version +1, to BLOCKED; budgets reset; G2–G7 cleared, G1 kept), and the owner rebases in the next attempt. Reviews are redone because the head changes.

## 6. PRs, stacking and protected branches

- **One draft PR per task** to `main`. G6 follows this fixed order:
  1. `devorch.py push --task <id>`: refuses unless the branch is `dev/*`, its tip equals the tested head (G2), G1–G5 are recorded and `git-baseline verify` passes. The orchestrator never runs `git push` directly; specialists cannot push at all.
  2. Create a **draft** PR (`create_pull_request`) with the template in `10-…` §2.
  3. Wait for CI on that head.
  4. `record --event pr_prepared --head <sha>` with `pr` evidence; refused unless the head equals the tested head.
  The orchestrator never edits a PR body or base after creation (`update_pull_request` is disallowed). The operator marks ready, approves and merges; G7 (`human_merged`) needs `github_merge` evidence at the G6 head, with `merged_by` checked.
- **Stacking**, limited to depth 2, keeps agents productive while human review is pending. A task may use a dependency's head as `base_commit` when that dependency is `AWAITING_HUMAN` with G1–G6 recorded. The stacked PR targets the dependency's branch until that merges; retargeting to `main` is done by the operator (the orchestrator cannot edit a PR base), followed by rebase + re-review if the patch changed.
- **Nothing reaches `main` without the operator.**
  - Required control: a GitHub ruleset on `main` requiring a PR, ≥ 1 approval by the operator, no force-push, no deletion, and required CI checks (DOD-02, to be applied by the operator in MERC-030).
  - Required control: a separate development bot identity for all agent pushes and PRs (DOD-03). No code or PR task runs until the operator has recorded `fact --kind identity` and `fact --kind decision --id DOD-02`.
  - Tripwires, not security boundaries: the settings deny rules, `disallowedTools` and the specialist guard hook. They match command text.
- **Git baseline.** `devorch.py git-baseline record` hashes `.git/config`, the list of active git hooks, `.claude/`, `CLAUDE.md`, `tools/devorch/` and `.gitignore`. `git-baseline verify` runs in every `preflight` and before every `push`; a violation stops dispatch and is escalated (S-05).

## 7. Cleanup

- **After `human_merged`:** the orchestrator runs `git worktree remove ../mercury-wt/<task>`; the remote branch is deleted by the operator's GitHub "delete branch on merge" setting, or kept.
- **After `cancelled` or `failed`:** first archive uncommitted changes (`git -C <wt> diff > $DEVORCH_EVIDENCE/<task>/attempt-N/uncommitted.patch`, then `import-evidence`), then remove the worktree. The branch stays for 30 days.
- **Never** run `git worktree remove --force` on a worktree with unarchived changes.

## 8. Recovery

| Situation | Action |
|---|---|
| Worktree missing but branch exists | Orchestrator: `git -c core.hooksPath=/dev/null worktree add <wt> <branch>` |
| Worktree locked by a dead session | `git worktree unlock <wt>` after confirming no agent is running (stale rule `07-…` §4) |
| Branch moved unexpectedly (not by the assigned agent) | Record `escalated` (possible foreign change); compare against the last recorded head |
| Base commit no longer on `main` (force-push upstream — should be impossible with the ruleset) | Stop all dispatch; escalate |
