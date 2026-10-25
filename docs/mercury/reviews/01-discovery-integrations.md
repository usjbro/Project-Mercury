# Discovery — External Integrations (Linear, GitHub, Slack)

Agent B (Solutions Architect), Phase 1. Collected 2026-10-12, strictly read-only (no writes, comments, reactions or labels in any system). No secrets or credential values are recorded. Message content is summarized, not quoted at length.

Legend: **[O]** = Observed directly in a tool result. **[I]** = Inferred from observations; must be verified before it is relied on.

---

## Summary

- **The Claude ↔ Codex workflow MERCURY replaces already exists and is mature, but lives in a different repository.** It runs against `usjbro/network_monitor` (Linear team `JAM`, Slack `#network-monitor`), driven by repo-local shell scripts (`coordination/scripts/*.sh`: `slack-notify.sh`, `create-gate.sh`, `approve-gate.sh`, `claim-gate-delegation.sh`, `reclaim-stale-gate.sh`, `new-task.sh`, `complete-task.sh`), gate files, task contracts, `.ai/` state files and per-task git worktrees. **[O]** (from Linear issue bodies JAM-155/160/161/251 and Slack posts). That repo is **outside this session's GitHub scope**, so the scripts themselves were not read.
- **`usjbro/project-mercury` is greenfield**: one commit on `main`, plus `claude/mercury-tdd`; only `README.md`; no PRs, issues, workflows, CODEOWNERS or PR template; no branch protection on either branch; single collaborator `usjbro` (admin). **[O]**
- **Identity separation is the largest gap.** The GitHub connector authenticates as the human owner `usjbro` (admin). Linear comments written by the Claude coordinator are authored as "James Brown" with `onBehalfOf: null`. Slack posts from connectors appear as the human (`theantimeridian`), including a Codex-authored plan-review request "Sent using ChatGPT" and an unattributed "Merge approved". All PRs in the existing repo are created by James Brown. **[O]** The operator already recorded this as a problem (JAM-160). An agent approval cannot be told apart from a human one today. **[I]**
- **Linear is plain**: one team (`JAM`), seven default workflow states, no templates, no Linear Documents, no agent skills, no delegated issues. Specs live **in issue descriptions** (Markdown: Context / Scope / Security / Tests / Acceptance criteria checkboxes / Size) and in repo files (`docs/superpowers/specs|plans/`). **[O]**
- **Slack pain points are documented by the operator**: missed thread replies, wrong-thread posting, multi-hour stalls with nobody noticing, connector posts indistinguishable from humans, test-suite token leak posting ~11 junk messages, notification failure from sandbox DNS needing manual retry, polling every 30 s only while a chat session is open, decisions made in chat not reflected in Slack. **[O]**

---

## Linear

### Workspace and teams [O]
| Item | Value |
|---|---|
| Workspace | name "james", URL slug `shmishmorshin` |
| Teams | One: **James**, key **`JAM`** (public, created 2026-09-18). Issue IDs are `JAM-<n>` (highest seen JAM-256). |
| Users | 2: James Brown (admin, display `jamesmbrownjr`) and the built-in "Linear" app user. **No agent/app users for Claude or Codex.** |
| Cycles | Not queried in depth (not relevant to flow). |

### Workflow states (team JAM) [O]
| Name | Type |
|---|---|
| Backlog | backlog |
| Todo | unstarted |
| In Progress | started |
| In Review | started |
| Done | completed |
| Canceled | canceled |
| Duplicate | duplicate |

No triage state, no custom states (e.g. no "Awaiting authorization" / "Plan review"). [O] MERCURY's ~18 internal states must be **mapped onto these 7** (or new states added by the human). [I]

### Labels [O]
- Workspace: `Feature`, `Bug`, `Improvement`.
- Team JAM: `Epic` (tracking issue), `Security` (security-sensitive), `Web` (Next.js relay/UI), `Rust` (capture agent), `Not Speced` ("Blocked on design/specification").
- **No agent-related labels** (nothing like `agent:codex`, `mercury`, `authorized`). No label groups.
- `Not Speced` is an existing eligibility signal MERCURY can honour (exclude from dispatch). [I]

### Projects [O]
22 projects (P-JAM-1 … P-JAM-22). Each epic issue maps 1:1 to a project ("Epic JAM-xxx"). Statuses used: Backlog, Planned, In Progress, Completed. No leads set. All are Network Monitor product work; **no MERCURY project exists**.

### Templates, documents, agent features [O]
- `list_templates` → **empty** (no issue/project/document templates).
- `list_documents` → **empty** (no Linear Documents). Specs are not in Linear docs.
- `list_agent_skills` → **empty**.
- `delegate` field is null on every sampled issue: **Linear's agent delegation is unused.**
- `list_diffs` shows Linear's GitHub PR mirror is active for `usjbro/network_monitor` (PR #277–#281 visible with head/base SHAs, reviewers). The only reviewer listed is **`chatgpt-codex-connector`** (external user "Codex"), decision `commented` — i.e. the Codex GitHub review bot is installed on that repo.

### Issue structure (sampled JAM-204, JAM-255, JAM-251, JAM-160, JAM-161, JAM-155, 40-issue listing) [O]
- **Description format**: Markdown with `## Context` / `## Current state`, `## Scope` (numbered), `## Security`, `## Tests (write them failing first)` with checkboxes, `## Acceptance criteria` with `- [ ]` checkboxes, trailing `**Size:** S|M` and sometimes `**Blocks:**`. Severity prefixes in titles: `[P1]`, `[P2]`, `[P3]`. Spikes titled `Spike: …`; epics `Epic: …`.
- **Relations are used heavily**: `blocks`, `blockedBy`, `relatedTo` (e.g. JAM-255 blocks 7 issues; JAM-204 blocks JAM-24/205). Parent/child via `parentId` (epics → tasks; roadmap root JAM-31).
- Some dependencies are still **prose references to old GitHub issue numbers** (`#154`, `#83`) from a migration; the coordinator flagged that these are misleading (JAM-117 review). [O]
- **Assignee**: only James Brown, often null even on Done issues. Assignment is not used to signal agent ownership.
- **Git branch names** are Linear-generated: `jamesmbrownjr/jam-<n>-<slug>`. PRs in the existing repo use these branches. [O]
- **Attachments**: GitHub PR links attached to issues (Linear GitHub integration). [O]
- **State history**: e.g. JAM-204 Backlog → In Progress (when gate approved) → In Review (PR opened) → Done (merge). Linear's GitHub integration moved an issue to Done on merge (Slack shows "*GitHub* changed issue status to Done"). [O]

### Existing agent activity in Linear [O]
- Claude ("Claude Code (coordinator)") posts **spec-readiness review comments** with a bold header naming itself, but the comment `author` is **James Brown** and `onBehalfOf` is null (JAM-17). Identity is conveyed only by text in the body.
- Issue descriptions refer to "the coordinator", "the work queue (which takes 'the next Todo')", gates and task contracts — i.e. Linear `Todo` is **currently** the queue signal for agents (JAM-161). [O] This conflicts with MERCURY's hard constraint that a status change alone must never start work. [I]

---

## GitHub (`usjbro/project-mercury` only)

| Item | Observation |
|---|---|
| Connector identity (`get_me`) | **[O]** User `usjbro` (personal account, human). The same account is repo **admin** and sole collaborator. No GitHub App / bot identity in use by this connector. |
| Branches | **[O]** `main` (4cad0ef, "Initial commit") and `claude/mercury-tdd` (44b7733). Both report `protected: false`. |
| Collaborators | **[O]** 1 — `usjbro`, role `admin`. |
| PRs | **[O]** None (open or closed). |
| Issues | **[O]** None. |
| Actions workflows | **[O]** 0. |
| Repo contents | **[O]** `README.md` only on `main` (locally also `docs/mercury/reviews/*` on the design branch). No `.github/`, no CODEOWNERS, no PR template, no `AGENTS.md`/`CLAUDE.md`. |
| Labels | **[O]** GitHub default label set present (`bug` confirmed). |
| Rulesets | **Unknown** — no ruleset tool is available; `protected:false` indicates no classic branch protection, rulesets not observable. |
| Owner type | **[I]** `usjbro` is a personal account, not an organization. Consequences: no org-level teams, no org rulesets; branch protection/rulesets must be set per repo; GitHub Apps can still be installed on a personal account. |

### Related repo (out of scope, evidence via Linear/Slack only)
`usjbro/network_monitor` [O via Linear `list_diffs` and attachments]: PRs ~#219–#281, squash merges, ≥9 CI checks incl. CodeQL, PR author always James Brown, Codex bot reviewer `chatgpt-codex-connector`, `@codex review` used to request reviews. Branch protection/rulesets there are **unknown**.

---

## Slack handoff workflow

### Channels [O]
User is a member of 3 channels: `#general`, `#random`, **`#network-monitor` (C0C39FJT9DX)** — the single coordination channel. No dedicated per-agent or per-task channels; no private channels observed.

### Posters [O]
| Display in Slack | What it is |
|---|---|
| **"Claude Code"** app posts with an owner tag `*claude-code*`, `*codex*` or `*gate*` | Output of `slack-notify.sh` via bot token + `chat.postMessage` (introduced by JAM-160). Both agents post through the same app, distinguished only by the owner text/username. |
| **`theantimeridian`** (the human's own account) | Both genuine human messages (e.g. "Merge approved") **and** agent posts made through the Slack connector (e.g. a Codex → Claude plan-review request footed "Sent using ChatGPT"; older Codex/Claude status posts from Sep 25–26). |
| **Linear** integration | Issue created / status changed / comment mirror (Claude's spec reviews appear here as "James Brown commented"). |
| **GitHub** (via Linear) | "GitHub changed issue status to Done" on merge. |
| "Coordination Gate" | Legacy webhook username (seen in the JAM-160 junk-message incident). |

### Message shapes [O]
Status posts use a fixed template: `:<emoji>: *<owner>* — task \`<slug>\` → *<status>*` then a one-paragraph body. Statuses seen: `awaiting-approval` (gate), `started` (includes worktree path), `feedback` (used for assignments, plan reviews, PR reviews), `review`, `pr-opened`, `done`, `idle`. Task slugs: `jam-<n>__<slug>` for gates, `<slug>` for tasks.

Typical lifecycle (JAM-204, 2026-10-07/08):
1. Gate post `awaiting-approval` with a dense spec summary; approved "under James's standing instruction in chat".
2. Claude `feedback` "NEXT TASK FOR CODEX (queue item N)" assignment (also tells Codex to clean up the previous worktree).
3. Codex `started` (~30 min later).
4. ~3.5 h gap; Claude posts twice (task thread and gate thread) that it has **not received a plan** and inspected the worktree for plan files/commits.
5. Codex `feedback`: plan ready at `docs/superpowers/plans/<date>-<slug>.md` (plan is a **file in the worktree**, the Slack message only points to it).
6. Claude plan review with findings coded M1–M5 / S1–S5; Codex revises; Claude re-review approves.
7. Codex `pr-opened` (PR #276); CI fix; Claude reviews on the PR; human merges; Linear → Done via GitHub integration.

Other shapes: Claude PR review summaries ("no blocking findings; all 9 checks green; merge state CLEAN; waiting on James"), "Merge not performed" disclaimers, Codex `slack-monitor` task "monitoring every 30 seconds while this chat session is active".

### Cadence [O]
Bursty, tied to open chat sessions: dozens of posts in an evening, then silence. Example 2026-10-11: ~25 Linear-mirror and agent posts between 16:34 and 17:56 ET. Gate-to-PR for JAM-204 ≈ 8 h; PR-to-merge ≈ 14.5 h (overnight, waiting on human).

### Failure patterns (operator-documented [O], in JAM-160/161/251 and Slack)
1. **Identity confusion** — connector posts appear as the human; one Claude session mistook another Claude session's post for the user's. Gate approvals typed in Slack cannot be trusted as human; JAM-160 moved gate approvals to chat.
2. **Lost / unseen replies** — top-level channel reads and paginated thread reads missed replies "for hours"; agents posted in the gate thread vs task thread inconsistently; Claude called a PR untested on macOS 46 min after Codex reported passing in the same thread.
3. **Stalls without detection** — a Codex-thread question unanswered for 14 h while Claude was active; assigned-but-unclaimed and claimed-but-silent tasks; JAM-161 added a 60-min no-PR auto-reclaim exception.
4. **Manual relays** — human asked an agent to post a review request "at James's explicit request"; decisions made in chat not propagated to Slack threads; Claude cannot see Codex's own chat.
5. **Delivery failures** — a gate notification failed with a sandbox DNS error and had to be retried by hand; webhooks could not thread.
6. **Duplicate / junk posts** — test suite leaked the bot token and posted ~11 live test messages; repeated "status unchanged" posts led to the "report only on change" rule.
7. **Environment split** — Codex sometimes worked in a cloud worktree (`/workspace/...`) that is not a checkout on the Mac; agents disagree about what exists.
8. **Evidence vs claims** — the playbook rule "judge progress by commits, worktree mtimes, PRs and Slack, not by claims" exists because claims were unreliable.

### What MERCURY must solve (inferred) [I]
Durable, addressable message delivery with acknowledgements; distinct, unforgeable agent identities; a single authoritative state per task (not a thread to be re-read); stall/timeout detection that works when no chat session is open; human approval captured through a channel agents cannot write to; plan/review artifacts versioned and linked to the task, not "a file in a worktree mentioned in Slack".

---

## Constraints for MERCURY

1. **Identifiers**: Linear issue IDs are `JAM-<n>` today (single team); MERCURY must not hard-code the prefix (the brief's example `ENG-123` is illustrative). Repo IDs as `owner/name`. [O]/[I]
2. **Branch naming**: Linear's generated `jamesmbrownjr/jam-<n>-<slug>` is the existing convention and drives Linear's PR auto-linking; MERCURY branch names should keep the issue identifier in the branch so the Linear GitHub integration continues to link PRs. [O]/[I]
3. **Linear GitHub automation already moves issues** (In Review on PR, Done on merge). MERCURY's post-merge Linear update must be idempotent against that and not fight it. [O]/[I]
4. **Only 7 Linear states**; MERCURY's detailed state lives locally; Linear gets a coarse projection (and optionally labels/comments). Adding states is a human workspace decision. [I]
5. **`Todo` is currently the agents' queue signal** (JAM-161). MERCURY must replace this with explicit, versioned Claude authorization; a status change must only make an issue *eligible*. [O]/[I]
6. **No separate agent identities exist** in GitHub, Linear or Slack today. A bot/GitHub App identity for agents and a human-only approver are prerequisites for enforceable separation of duties; with the current single admin token, any agent can approve/merge. [O]/[I]
7. **Personal GitHub account, sole admin collaborator**: GitHub forbids a PR author approving their own PR, so if agents push/open PRs as `usjbro`, the human cannot provide the required approval on those PRs. Agents must author PRs under a different identity (GitHub App or machine user) for "require 1 approval" to work. [I — verify against GitHub rules on the target plan]
8. **Codex GitHub review bot (`chatgpt-codex-connector`) and `@codex review`** already exist on the other repo; MERCURY's review records must not count bot reviews as human approvals. [O]/[I]
9. **Existing conventions worth preserving**: issue description sections + AC checkboxes; `[P1]–[P3]` severity; `Not Speced` label; `Security` label → mandatory security plan review (checklist in JAM-251); "ask-first" categories (wire changes, new dependencies) from `AGENTS.md`; plans in `docs/superpowers/plans/`, specs in `docs/superpowers/specs/`; squash merges; one branch / one PR per issue; worktrees under `<repo>/.worktrees/<slug>`. [O]
10. **Untrusted content**: Linear comments and Slack messages are written by agents under the human's name; MERCURY must not treat any Linear/Slack text as an authorization or human approval. [I]
11. **Slack must be retired gradually**: the scripts in `network_monitor` post to Slack; a migration/coexistence plan is needed (e.g. MERCURY read-only mirror or disable `slack-notify.sh`). [I]

---

## Unknowns

| Unknown | Why not observable |
|---|---|
| Contents of `coordination/scripts/*`, `AGENTS.md`, `CLAUDE.md`, gate/task-contract formats, `.ai/` files, `.codex/hooks.json` in `usjbro/network_monitor` | GitHub access scoped to `project-mercury` only; described only indirectly in Linear/Slack. |
| Branch protection / rulesets / required checks on `network_monitor` | Out of scope repo; no ruleset tool. |
| Rulesets on `project-mercury` | No ruleset API tool available; only `protected:false` observed. |
| Connector token type and scopes (classic PAT vs fine-grained vs OAuth app) | `get_me` exposes the user only; not exposed and must not be probed. |
| Whether `usjbro` has a paid plan (affects protection on private repos) / repo visibility | Not returned by the tools used. |
| Slack bot token scopes, app configuration, other installed apps | Slack connector exposes messages, not app admin. |
| Whether "Merge approved" and other `theantimeridian` posts were typed by the human | Exactly the ambiguity JAM-160 documents; no reliable field via this connector. |
| Linear API key / OAuth app usage by the existing scripts; Linear webhooks | Not visible via MCP. |
| Codex CLI mode on the Mac (local vs cloud), config, approval policy | Not visible from these systems; see `01-discovery-local.md`. |
| DMs / private channels involved in handoffs | Only channel listing of public/private memberships; DMs not searched to avoid personal data. |

---

## Evidence log

| # | Tool call | Result (summary) |
|---|---|---|
| L1 | `Linear.get_workspace` | Workspace "james", slug `shmishmorshin`. |
| L2 | `Linear.list_teams` | 1 team: James / `JAM`. |
| L3 | `Linear.list_agent_skills` | Empty. |
| L4 | `Linear.list_templates` | Empty. |
| L5 | `Linear.list_issue_statuses(JAM)` | 7 states (table above). |
| L6 | `Linear.list_issue_labels` (workspace, then team JAM) | 3 workspace + 5 team labels; no groups; no agent labels. |
| L7 | `Linear.list_projects` | 22 projects, all Network Monitor epics. |
| L8 | `Linear.list_users` | James Brown (admin) + "Linear" app user. |
| L9 | `Linear.list_documents` | Empty. |
| L10 | `Linear.list_issues(limit 40)` | JAM-* issues; branch names `jamesmbrownjr/jam-n-…`; delegate always null; assignee James or null. |
| L11 | `Linear.get_issue` JAM-251, JAM-255, JAM-204 (relations, stateHistory, attachments) | Description conventions; heavy blocks/relatedTo; PR attachments to `network_monitor`; coordination lessons. |
| L12 | `Linear.list_comments` JAM-204, JAM-255 | Empty. JAM-17: one Claude coordinator review, author James Brown, `onBehalfOf` null. |
| L13 | `Linear.list_issues(query mercury)` | None. `query codex` → JAM-155/160/161/251 (coordination tooling issues) + product issues. |
| L14 | `Linear.list_diffs(limit 5)` | `network_monitor` PRs #277–#281, creator James Brown, reviewer `chatgpt-codex-connector`. |
| L15 | `Linear.list_issues(state In Review)` | None currently. |
| L16 | `Linear.get_issue` JAM-160, JAM-161, JAM-155 | Operator's own failure analysis of Slack coordination, claim protocol, 60-min reclaim, shared skills layout. |
| G1 | `github.get_me` | `usjbro` (human user). |
| G2 | `github.list_branches` | `main`, `claude/mercury-tdd`; both unprotected. |
| G3 | `github.list_repository_collaborators` | `usjbro` admin only. |
| G4 | `github.list_pull_requests(all)` | Empty. |
| G5 | `github.list_issues` | Empty. |
| G6 | `github.actions_list(list_workflows)` | 0 workflows. |
| G7 | `github.get_file_contents(/)` | `README.md` only. |
| G8 | `github.list_commits` | One "Initial commit" by `usjbro`. |
| G9 | `github.get_label(bug)` | Default label present. |
| S1 | `Slack.slack_list_user_channels` | `#general`, `#random`, `#network-monitor`. |
| S2 | `Slack.slack_read_channel(#network-monitor, 40)` | Recent activity 2026-10-09 → 10-11: Linear mirror posts, Claude Code app status posts, coordinator spec reviews, Codex plan-review request via human identity, "Merge approved". |
| S3 | `Slack.search(gate, is:thread)` | Gate/assignment threads from 2026-09-25 to 10-11; earlier posts as `theantimeridian`. |
| S4 | `Slack.search(jam-204)` ascending | Full JAM-204 lifecycle incl. 3.5 h "no plan received" gap. |
| S5 | `Slack.search(missed)`, `(duplicate)`, `(stale)` | Review corrections, coordination-kit bug fixes, stale worktrees, reclaim protocol. |
| S6 | `Slack.slack_search_users(claude)` | No user found — Claude posts via an app, not a user. |
| R1 | Local `git log` / file listing | Branch `claude/mercury-tdd` adds `docs/mercury/reviews/00-brief.md`, `01-discovery-local.md`, `03-design-baseline.md`. |

No write tools were called in any system.
