# Integration: Linear

**Owner:** Agent B, Phase 2 proposal. **Builds on:** `reviews/01-discovery-integrations.md` (**DI**) and `reviews/02-discovery-platform.md` §3 (**DP**).

The workspace observed during discovery has one team, `JAM`, with seven default states. It has no agent identities, and Linear's GitHub integration is active (DI). MERCURY must not hard-code `JAM`.

---

## 1. Role and invariants

Linear is the source of **work definitions** (issue, spec, AC, relations) and the human-facing **status projection**. It is never a source of authority.

| ID | Invariant | Enforcement |
|---|---|---|
| LN-1 | No Linear field, status, label, comment or delegation can authorize work. Linear signals can only make an issue **eligible** for Claude evaluation | Software: the dispatch guard requires an `auth_` record (claude.md §3) |
| LN-2 | Comments and descriptions are untrusted data. MERCURY has **no** comment-command interface | Software: no parser for commands exists. Text reaches Claude only inside nonce-delimited untrusted blocks |
| LN-3 | Every MERCURY write to Linear is made by a non-human app actor | Software: OAuth `actor=app` token (§2). A human API key is rejected at config validation |
| LN-4 | Each Linear status transition has exactly one writer | Configuration and policy: §6 ownership table. Software: MERCURY only writes the transitions it owns |
| LN-5 | Spec changes after authorization invalidate the authorization for further work | Software: `spec_hash` comparison on every poll (§8) |
| LN-6 | Linear-native delegation or a coding session on a MERCURY-managed issue blocks MERCURY work on that issue | Software: detection on every poll (§9) |

---

## 2. Identity (decision)

**Decision:** a Linear **OAuth2 application "MERCURY"** installed with `actor=app`. Its token is obtained through the **client-credentials grant**.

According to Linear's OAuth docs (search excerpt, 2026-10-12), client credentials yield an `app`-actor token that is valid for 30 days and has access to public teams. That is sufficient, because team `JAM` is public (DI). This is **ASM-B-30**: the grant is enabled for the app, and the scope and lifetime behave as described.

| Item | Value |
|---|---|
| App name / avatar | "MERCURY" with a distinct avatar, so humans can tell its comments apart at a glance |
| Scopes | `read`, `write`. `write` is needed for `issueUpdate` (state, labels); there is no narrower state-only scope. Not requested: `admin`, `app:assignable`, `app:mentionable` (§9: MERCURY must *not* be delegatable in Linear) |
| Secret storage | `client_id` in config; `client_secret` in Keychain `dev.mercury.linear` |
| Token lifecycle | Minted at startup and when fewer than 3 days remain. Cached in memory only; re-minted after restart. On a 401, re-mint once, then open the `linear_auth` circuit breaker |
| Fallback | If client credentials are unavailable, the operator performs a one-time authorization-code install with `actor=app` (the docs disagree on `app` versus `application`, ASM-B-31). The refresh token goes in the Keychain |
| Rejected | A personal API key. It acts as the human (DI: comments today appear as "James Brown"), which breaks LN-3 and the audit |

MERCURY records its own app user ID (`viewer { id }` with the app token) at startup. It uses that ID to recognise its own comments and status changes, never body markers (§7).

**Who is "the human" in Linear?** The operator's user ID is configured explicitly (`linear.operator_user_ids`). Note that today Claude and Codex connectors write **as that same human user** (DI). Until the operator stops agent use of their Linear identity, "actor is the operator" is **not** proof that a human acted. This is why Linear signals stay eligibility-only (LN-1). It is reported to Agent E as risk R-B-03.

---

## 3. What MERCURY reads

### 3.1 Polling queries (GraphQL, `https://api.linear.app/graphql`)

**Q1, incremental team sweep** (every 60 s while awake). Q1 deliberately does **not** filter on the label, so that label removals and state changes are seen.

```graphql
query TeamSweep($teamId: ID!, $since: DateTimeOrDuration!, $after: String) {
  issues(
    first: 50, after: $after, includeArchived: true,
    orderBy: updatedAt,
    filter: { team: { id: { eq: $teamId } }, updatedAt: { gte: $since } }
  ) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id identifier title updatedAt archivedAt canceledAt completedAt
      priority branchName url
      state { id name type }
      labels { nodes { id name } }
      delegate { id name app }          # ASM-B-32: field names on User (app flag)
      assignee { id }
    }
  }
}
```

**Q2, full issue snapshot.** Run only for issues that Q1 shows changed and that are eligible or MERCURY-managed.

```graphql
query IssueSnapshot($id: String!) {
  issue(id: $id) {
    id identifier title description updatedAt priority estimate url branchName
    team { id key }  project { id name }  parent { identifier }
    state { id name type }
    labels { nodes { id name } }
    delegate { id name app }
    relations { nodes { type relatedIssue { id identifier state { type } } } }
    inverseRelations { nodes { type issue { id identifier state { type } } } }
    attachments { nodes { id url title sourceType createdAt } }
    comments(first: 50, orderBy: createdAt) {
      nodes { id body createdAt updatedAt
              user { id name app }  botActor { id name type }  externalUser { id name } }   # ASM-B-33
    }
    history(first: 50) {
      nodes { createdAt actor { id app }  botActor { name type }
              addedLabels { name } removedLabels { name }
              fromState { type } toState { type } }                    # ASM-B-34
    }
  }
}
```

- Dependency checks use `relations` (this issue blocks others) and `inverseRelations` with `type: blocks` (issues blocking this one) (DP §3).
- **Q3, reconciliation sweep.** Every 30 min, and after any wake or restart, MERCURY re-runs Q1 with `$since = now − 7 d` and also fetches Q2 for every non-terminal MERCURY task. Q1 normally starts from `cursor − 5 min`, so this catches anything the overlap window missed.

### 3.2 Cursor and dedup

- `linear_cursors(team_id PRIMARY KEY, since TEXT NOT NULL, updated_at TEXT)`. `since` is the max `updatedAt` seen. The next query uses `since − 5 min` (overlap), so clock skew and page boundaries cannot drop events.
- Dedup key per observed issue version: `ln:issue:<issue_uuid>:<updatedAt>`. If it is already in `inbound_events`, the version is skipped. A new key means a snapshot diff is computed (§8).
- Comments get the dedup key `ln:comment:<comment_uuid>:<updatedAt>`.
- **Paging stop rule:** stop at the first page whose last `updatedAt < since − 5 min`.
  - **ASM-B-35:** `orderBy: updatedAt` returns items in descending order. If the order is ascending, page to the end instead.

### 3.3 Rate limits

Published figures (DP §3; the search excerpt is current but numbers vary between doc versions):

- OAuth app: 5,000 requests/h.
- Complexity: about 2,000,000 points/h for OAuth apps.
- Quotas apply per user or app user.

Budget at 60 s polling:

- Q1: 60/h per team.
- Q2: about 1 per changed issue.
- Q3: 2/h plus N.
- Writes: under 50/h.

Expected total is under 300 requests/h, which is less than 10 % of the quota.

Handling:

- Read `X-RateLimit-Requests-Remaining` and `X-RateLimit-Complexity-Remaining`. When either drops below 10 %, widen the poll interval to 5 min.
- On a GraphQL error `extensions.code == "RATELIMITED"` (or HTTP 429, **ASM-B-36**), back off until the reset header time plus jitter.
- Keep `first:` at 50 or below, and keep comment and history connections at 50 or below, to stay well under per-query complexity caps.

---

## 4. Eligibility (how candidate issues are discovered)

An issue is **eligible** for Claude triage and authorization only if **all** of the following hold:

| # | Condition | Source |
|---|---|---|
| E1 | Team key is in `linear.teams` config | Q1 |
| E2 | Label `mercury` is present | Q1 |
| E3 | The **most recent** history entry adding `mercury` was made by an actor in `linear.operator_user_ids` and not by an app or bot actor | Q2 `history` (ASM-B-34). This blocks an app or agent from self-nominating; the human-identity caveat in §2 still applies |
| E4 | State type is `unstarted` (Todo) or `backlog`. Not started, completed or canceled | Q1 |
| E5 | No `Not Speced` label; no `mercury:hold` label | Q1 |
| E6 | `delegate` is null (§9) | Q1 |
| E7 | Description is non-empty and the AC section parses to at least 1 item (§5) | Q2 |
| E8 | Not already bound to a non-terminal MERCURY task | local DB |

Dependency status (blocked or unblocked) is **not** an eligibility filter. It is computed and passed to Claude: an issue may be authorized for planning while its blockers are still open, if Claude decides so. The default authorization rule set in claude.md says "decline or defer if any blocker is not `completed`".

Losing eligibility after authorization:

| Change | MERCURY reaction |
|---|---|
| `mercury` label removed | Cancel request: the task moves to `CANCELLED` at the next safe point. A running Codex run is interrupted. An open PR is converted to draft and commented on, not closed |
| `mercury:hold` added | Pause (`BLOCKED` with reason `operator_hold`) after the current run |
| `Not Speced` added | Treated as spec drift (§8) |
| State moved to Canceled or Duplicate by a human | Cancel |

All of these only **stop** or pause work. That is a fail-safe direction, so they need no authentication beyond Linear.

---

## 5. Spec extraction and `spec_hash`

The coordinator parses the description into sections, matching the existing JAM conventions (DI): `## Context`, `## Scope`, `## Security`, `## Tests…`, `## Acceptance criteria`, `**Size:**` and `**Blocks:**`.

- **AC items** are `- [ ]` / `- [x]` lines under the AC heading. Each gets an ID `AC-<n>` (1-based, by order), a text, and a `sha256(text)`.
- `spec_hash = sha256(canonical_json({ title, description_normalized, ac_texts[], labels_spec_relevant[], blocking_issue_ids[] }))`, where:
  - `description_normalized` has whitespace collapsed, and every checkbox state is normalized to `[ ]`. Ticking boxes is progress tracking, not a spec change.
  - `labels_spec_relevant` is `Security`, `Not Speced` and any label in `linear.spec_labels`.
- The spec snapshot (full Q2 JSON, redacted) is stored as an artifact. `auth_` records reference `spec_snapshot_id` and `spec_hash`.

---

## 6. Status ownership (decision)

The 7 default states stay as they are. The human may later add states, but MERCURY does not require it.

**Decision (default mode `integration_owns_pr_states`):**

- **MERCURY owns the pre-PR transitions.**
- **Linear's GitHub integration owns `In Review` and `Done`**, because MERCURY branch names contain the issue ID (github.md §4.1).
- MERCURY *verifies* the result and only *comments*. It never writes `In Review` or `Done` itself in this mode.

| Transition (Linear) | Trigger | Owner (sole writer) | MERCURY action |
|---|---|---|---|
| Backlog/Todo → (eligible) | Human adds the `mercury` label | Human | Read only |
| Todo/Backlog → **In Progress** | MERCURY task reaches `AUTHORIZED` | **MERCURY** (app actor) | `issueUpdate(stateId)` plus an authorization comment (§7.2). Idempotent: skipped if already a `started` type |
| In Progress → **In Review** | PR opened / marked ready (draft PRs: per team automation) | **Linear GitHub integration** | MERCURY verifies within 10 min after PR ready. If the state is still not In Review, MERCURY posts a warning to the event log only (no write) |
| In Review → **Done** | PR merged (closing link via branch name) | **Linear GitHub integration** | After merge verification (github.md §8): success means a verification comment; failure means a security comment and escalation. MERCURY does **not** revert `Done` |
| Any → **Canceled** | Human | Human | MERCURY cancels the task |
| Failure / blocked | MERCURY `FAILED` / `BLOCKED` | **MERCURY** writes no state; it adds the label `mercury:needs-human` and posts a comment | Label removed by MERCURY when the task resumes |

**Alternative mode `mercury_owns_all`** (configurable; requires operator workspace changes):

- The PR body uses only the contributing word (`Part of JAM-123`).
- The branch name must **not** contain the issue ID, because branch-name links are closing links, per Linear docs on identifier collisions. Branch format becomes `mercury/t-<task-ulid-suffix>-<slug>`.
- MERCURY sets `Done` only after merge verification succeeds.
- **Trade-off:** `Done` then means "verified human merge", but the existing branch convention and familiar auto-linking are lost.
- Recommended only if Phase 0 shows the operator wants a verified `Done`. This is OQ-B-06.

MERCURY never toggles a state back. Its writes are compare-and-set: it re-reads the state and writes only if the current state equals the expected source state. Otherwise it records `linear_state_conflict` and does nothing.

---

## 7. What MERCURY writes

### 7.1 Write operations

| Operation | Mutation | Idempotency |
|---|---|---|
| Comment | `commentCreate(input: { id: <uuidv5(dedup_key)>, issueId, body })` | Client-supplied `id` (DP §3, ASM-B-37). A retry with the same ID returns "already exists", which counts as success |
| State change | `issueUpdate(id, input: { stateId })` | Compare-and-set (§6) |
| Label add/remove | `issueUpdate(id, input: { addedLabelIds / removedLabelIds })` (**ASM-B-38**: field names) | Set semantics |
| PR link | Not written by MERCURY in the default mode; the GitHub integration attaches PRs. In `mercury_owns_all` mode: `attachmentLinkGitHubPR` / `attachmentCreate(url = PR URL)` | Keyed on (issue, url) (DP §3) |

MERCURY-owned labels must exist beforehand. The human creates them once during Phase 0: `mercury`, `mercury:hold`, `mercury:needs-human`. The app never creates labels.

### 7.2 Comment catalogue

Comments are low-volume and change-only. They follow the operator's "report only on change" rule (DI). Each comment starts with a one-line headline, then a compact details block, then a hidden marker `<!-- mercury:v1 {"kind":"…","task":"tsk_…","dedup":"…"} -->`. The marker is only a convenience for humans and tools. **MERCURY identifies its own comments by author ID, never by marker**, because markers are forgeable.

| Kind | When | Content |
|---|---|---|
| `authorized` | Task authorized | Authorization ID and version, scope summary, limits, spec_hash (short), "Claude authorized; this is not a human approval" |
| `declined` / `deferred` | Claude declined | Reason, what would make it eligible |
| `plan_approved` | Plan approved | Plan version and hash (short), AC coverage summary |
| `escalation` | Revision budget exhausted, needs-human, security | What is needed from the human, and where (PR link or local CLI) |
| `pr_ready` | Claude review passed and human review requested | PR link (GitHub also notifies) |
| `completed` | Merge verified | Merge SHA, approver, verification result |
| `merge_verification_failed` | Verification failed | Facts only; security escalation |
| `spec_drift` | Drift detected after authorization (§8) | What changed (field names), action taken |
| `foreign_agent_detected` | §9 | Delegation or coding session found; MERCURY paused |

Volume target: at most 6 comments per task on the happy path (`authorized`, `plan_approved`, `pr_ready`, `completed`, plus Linear's own GitHub linkbacks). Low-level progress goes only to the local event log.

---

## 8. Edits after authorization (spec drift)

On each new issue version (§3.2), MERCURY recomputes `spec_hash`. If it differs from the authorization's `spec_hash`:

| Task state at detection | Action |
|---|---|
| `AUTHORIZED`, `PLANNING`, `AWAITING_PLAN_REVIEW`, `PLAN_REVISION_REQUESTED` | Interrupt any running Codex or Claude run. Mark the authorization `superseded_by_spec_change`. Return to `AWAITING_AUTHORIZATION` with the new snapshot. Claude re-authorizes; `auth_` version+1. The old plan is invalid unless the new authorization explicitly carries it forward (`carry_forward_plan_sha256`, which `plan_review` must re-approve) |
| `PLAN_APPROVED`, `IMPLEMENTING`, `TESTING` | Interrupt the run at the next safe point (SIGINT, then wait for exit). Move to `BLOCKED(spec_drift)` → re-authorization → plan review against the new spec. The worktree is preserved; Codex may continue from it if the new plan approves |
| `PR_OPEN`, `CLAUDE_PR_REVIEW`, `CHANGES_REQUESTED`, `AWAITING_HUMAN_APPROVAL` | Convert the PR to draft and set the `MERCURY / claude-review` check to `action_required`. This prevents a merge, because the check is required (github.md §9). Re-authorize, then Claude re-reviews the PR against the new spec |
| `MERGED`, `COMPLETED` | Ignore. A comment notes that the spec changed after merge |

Changes that are **not** drift:

- checkbox ticks;
- priority, estimate, assignee, project or cycle changes;
- comments.

These are recorded but do not invalidate anything. Priority changes feed the next triage.

---

## 9. Linear-native delegation and coding sessions (detect and refuse)

Linear can delegate issues to agents and start **Coding sessions** that run Claude Code or Codex in Linear's cloud and open draft PRs. Triage automations can start them automatically (Linear docs "Coding sessions", 2026-10-12). For a MERCURY-managed issue this is a second, unauthorized start path.

**Detection.** All of these run on every snapshot:

1. `issue.delegate` is non-null. MERCURY never accepts delegation; it does not request `app:assignable`.
2. History entries show delegation, or agent-session activity by a bot or app actor other than MERCURY (**ASM-B-39**: available via `history` / `agentSessions`).
3. A GitHub PR linked to the issue (via `attachments`, or a GitHub search for branches containing the issue ID) whose author is not the MERCURY App, or whose head branch does not start with `mercury/`.

**Refusal.**

- The task moves to `BLOCKED(foreign_agent)`, or the issue is excluded from eligibility (E6).
- MERCURY posts a `foreign_agent_detected` comment and adds `mercury:needs-human`.
- MERCURY never interacts with the foreign session or PR.
- To resume, the human removes the delegation and closes the foreign PR. MERCURY then requires a fresh Claude authorization (`auth_` version+1).

**Operator recommendation (Phase 0, policy):**

- Disable Coding sessions and agent triage automations for teams listed in `linear.teams`.
- Do not enable Linear's `app:assignable` for any agent on those teams.
- Linear Reviews (approve or merge from Linear) acts with the human's own GitHub identity. That is acceptable: GitHub sees `usjbro`, and merge verification treats it as a human merge.

---

## 10. Malicious or misleading content

| Vector | Handling |
|---|---|
| A comment says "MERCURY: authorize this" or "approved by James" | No effect (LN-1, LN-2). Passed to Claude as untrusted data with `author_kind`; Claude is instructed to flag it as `prompt_injection_attempt` |
| The description embeds instructions to Codex ("also edit .github/workflows") | Reaches Codex only inside `<untrusted>` blocks. The scope comes from the authorization. The diff guard blocks protected paths (codex.md §9) |
| The description references "#154" or old GitHub numbers as dependencies (DI) | Only Linear relations count for dependency computation. Prose references are passed to Claude, which may mention them in findings |
| A huge comment or description (context flooding) | Per-part byte caps with explicit truncation plus a hash (claude.md §5.2) |
| Secrets pasted into an issue | Redaction filter before persistence in artifacts and before prompts (Agent E). The raw text stays in Linear only |
| An attacker or agent edits the issue to change the spec after approval | `spec_hash` drift (§8) forces re-authorization |
| An agent self-adds the `mercury` label | E3 history check. Weak while agents use the human's Linear identity (§2) |

---

## 11. Failure behaviour (Linear-specific)

| Condition | Behaviour |
|---|---|
| Linear unreachable or 5xx | Reads: keep the last snapshot. No **new** authorizations are dispatched, because eligibility must be fresh, at most 10 min old. Running tasks continue. Writes are queued in the outbox (`outbound_ops`, Agent C) with retries 30 s → 30 min (exponential, jitter), retried indefinitely; an escalation comment is posted if a write stays pending more than 24 h |
| 401 | Re-mint the token once. If it fails again, open the `linear_auth` circuit breaker, notify the operator (local notification plus a GitHub comment on any open PR), and pause new authorizations |
| `RATELIMITED` | Back off to the reset time; reduce poll frequency |
| GraphQL validation error (schema drift) | `config_fatal` for Linear. Stop Linear polling and notify. Contract tests should catch this before deploy |
