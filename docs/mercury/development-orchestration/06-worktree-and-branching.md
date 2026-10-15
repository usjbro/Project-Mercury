# 06 — Worktree and Branch Isolation Strategy

## 1. Layout

```text
<parent>/
  Project-Mercury/            main checkout (orchestrator's cwd); never used for task edits
  mercury-devorch/            worktree of branch devorch/state (ledger, contracts, evidence)
  mercury-wt/DT-0042/         one worktree per implementation-type task
  mercury-wt/devint-W2/       integration worktrees (Integration and Release Engineer)
```

Worktrees live **outside** the main checkout, so tools that walk the repository never see other tasks' files. On the operator's Mac the parent directory must not be in a TCC-protected folder (`~/Documents`, `~/Desktop`, `~/Downloads`; same reason as ADR-016).

## 2. Names

| Object | Convention | Example |
|---|---|---|
| Development task id | `DT-nnnn` (with suffix `-rN` for review tasks and `-iN` for integration) | `DT-0042`, `DT-0042-r1` |
| Task branch | `dev/merc-<id>-<slug>` or `dev/dt-<nnnn>-<slug>` for non-MERC tasks; slug ≤ 40 chars `[a-z0-9-]` | `dev/merc-107-process-broker` |
| Integration branch | `devint/<wave>-<n>` (local; pushed only if the operator asks) | `devint/w2-1` |
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
- **Path-ownership registry.** This is the union of `allowed_paths` over all tasks in RUNNING, AWAITING_REVIEW and AWAITING_INTEGRATION. The orchestrator refuses a contract whose `allowed_paths` intersect the registry (glob intersection, checked conservatively: when in doubt, conflict).
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
- Before G5: the Integration Engineer merges all wave tasks onto `devint/<wave>` from current `main`.
  - **Textual conflicts** fail G5 for the later task.
  - **Semantic conflicts** are caught by the full test suite on the integration head.
  - **`git range-diff` / patch-id** proves that each integrated commit equals its reviewed commit.
- After a human merge to `main`: every open task branch whose base is behind `main` is rebased by its owner in a correction attempt (attempt+1 counts as **environmental**, with no budget charge). Its reviews must be redone if the rebase changed the patch.

## 6. PRs, stacking and protected branches

- **One PR per task** to `main` by default. The orchestrator opens it as a **draft** after G6 and marks it ready when CI is green. The operator approves and merges.
- **Stacking**, limited to depth 2, keeps agents productive while human review is pending. A task may use a dependency's head as `base_commit` when that dependency is `AWAITING_HUMAN` with G1–G6 recorded. The stacked PR targets the dependency's branch until that merges, then is retargeted to `main` (rebase + re-review if the patch changed).
- **Nothing reaches `main` without the operator.**
  - Required control: a GitHub ruleset on `main` requiring a PR, ≥ 1 approval by the operator, no force-push, no deletion, and required CI checks (DOD-02, to be applied by the operator in MERC-030).
  - Supplementary controls: the settings deny rules and `disallowedTools` in this package. Deny rules match command text and are **not a security boundary**.

## 7. Cleanup

- **After `human_merged`:** `git worktree remove ../mercury-wt/<task>`; the remote branch is deleted by the operator's GitHub "delete branch on merge" setting, or kept.
- **After `cancelled` or `failed`:** first archive uncommitted changes (`git -C <wt> diff > evidence/<task>/attempt-N/uncommitted.patch`), then remove the worktree. The branch stays for 30 days.
- **Never** run `git worktree remove --force` on a worktree with unarchived changes.

## 8. Recovery

| Situation | Action |
|---|---|
| Worktree missing but branch exists | `git worktree add <wt> <branch>` |
| Worktree locked by a dead session | `git worktree unlock <wt>` after confirming no agent is running (stale rule `07-…` §4) |
| Branch moved unexpectedly (not by the assigned agent) | Record `escalated` (possible foreign change); compare against the last recorded head |
| Base commit no longer on `main` (force-push upstream — should be impossible with the ruleset) | Stop all dispatch; escalate |
