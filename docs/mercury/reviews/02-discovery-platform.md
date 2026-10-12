# Discovery — Platform Capabilities (Phase 1)

Agents: **B (Solutions Architect)** and **D (DevOps/Platform Architect)**. Collected 2026-10-12, read-only research. Nothing on GitHub, Linear or any host was modified.

## How to read this document

Each claim has an evidence marker:

| Marker | Meaning |
|---|---|
| **[V]** | Verified against primary vendor text fetched today, cited as `[Sn]`. GitHub Docs were read from the `github/docs` source repo (the Markdown behind docs.github.com) because docs.github.com was blocked from this container. GitHub REST behaviour was read from GitHub's published OpenAPI description. |
| **[V~]** | Verified only through a search-engine excerpt of the vendor page, or a mirror of the vendor page (for example sqlite.org docsrc, a mirrored man page, Linear developer pages). The wording is vendor wording, but the full page was not loaded. Re-check before relying on exact numbers. |
| **[I]** | Inferred: drawn from engineering knowledge, a secondary source, or an older version of the doc. Treat as an assumption until it passes a Phase 0 check. |

Access limitations during this research:
- docs.github.com, linear.app/developers, sqlite.org and the man-page mirrors could not be reached from the container (DNS or egress policy).
- developer.apple.com (archive and JSON docs), nodejs.org and raw.githubusercontent.com could be reached.
- The `launchd.plist(5)` and `launchctl(1)` text quoted here comes from Apple's open-source launchd tree. That text is older than current macOS, so modern macOS may differ on details. Check with `man launchd.plist` on the Mac.

---

## Summary

1. **The repository is owned by a personal account, and this is the main governance finding.** `usjbro/Project-Mercury` is owned by a **User** account and is **public** [V, `gh api repos/...`].
   - Personal-account repositories have only two permission levels, owner and collaborator.
   - Collaborators always have push/write access and can "create, merge, and close pull requests" [V S9].
   - Bypass lists and "Restrict who can push" are **organization-only** features [V S3].
   - Team-based "Required reviewers" do not exist on user-owned repos [V S1].
   - Consequence: an agent identity that can push branches can also **merge** a PR once the human has approved it. Protection rules alone cannot express "human merges only" here.
   - Options: (a) move the repo to a GitHub organization, which unlocks restricted push/merge and bypass lists; or (b) accept a merge-identity check after the fact as a detective control.
2. **Human approval can be made non-forgeable with built-in protections.** Configure:
   - required approvals ≥ 1;
   - **Require review from Code Owners**, with `CODEOWNERS` = `* @<human>` only;
   - **Require approval of the most recent reviewable push**;
   - **Dismiss stale approvals**;
   - block force pushes;
   - "Do not allow bypassing" (or a ruleset with an empty bypass list).

   Code owners must be users or teams with write access [V S10], so a GitHub App bot cannot be a code owner. The agent that pushed last can never satisfy the last-push rule [V S1, S3].
3. **The agent must never act as the human.** A human-owned PAT or `gh auth` session in the coordinator would make the human the PR author. Authors cannot approve their own PRs [V~ S20], and the human's token could also merge (owner = admin). Agents need a **separate identity**: a GitHub App installed on the account (preferred) or a machine-user collaborator.
4. **Without inbound access, use polling.** Use ETag conditional requests: a `304` does not count against the primary rate limit [V S6]. Budgets are 5,000 requests/hour for a PAT or user, and ≥ 5,000/hour for an App installation [V S7]. Do not use the Events or Notifications APIs for control flow, because their latency is 30 s to 6 h [V S11]. Self-hosted runners are explicitly discouraged on public repos [V S21].
5. **Linear:**
   - GraphQL API with personal API keys (permission- and team-scoped) or OAuth apps.
   - The OAuth `actor=app` install gives a non-human app user, with `app:assignable` / `app:mentionable` scopes and Agent Session webhooks [V~ S13–S15].
   - Webhooks need a public HTTPS endpoint, so MERCURY must poll with `updatedAt` filters.
   - Linear's native GitHub integration moves issue status automatically on PR events. Its new **Coding sessions** and **Linear Agent** can themselves run Claude Code / Codex on delegated issues [V S12]. MERCURY must define which system owns which statuses and must ignore or forbid Linear-native delegation on MERCURY-managed teams.
6. **macOS runtime:**
   - A per-user **LaunchAgent** in `gui/<uid>` is the right host: it gets the login keychain and runs in the user context. It runs **only while the user is logged in** [V S16].
   - At logout and shutdown, launchd sends SIGTERM, then SIGKILL after `ExitTimeOut` (default 20 s in the OSS man page) [V S16, S17].
   - Power assertions stop *idle* sleep only. Lid close, Apple-menu sleep and low battery still sleep [V S18]. All processes are suspended during sleep.
   - Background `node` touching `~/Documents`, `~/Desktop` or `~/Downloads` hits TCC (Transparency, Consent and Control) prompts and EPERM errors [I/V~ S23].
7. **Persistence:**
   - SQLite in WAL mode is always consistent, but `synchronous=NORMAL` can lose the latest commits on power loss. `FULL` is durable [V~ S25].
   - On macOS, real power-loss durability also needs `PRAGMA fullfsync=ON` (or at least `checkpoint_fullfsync`), which is off by default [V~ S26].
   - `node:sqlite` is **Release Candidate (1.2) in Node 24 and 26**, and only **1.1 Active development in Node 22** [V S27].
   - The class was renamed from `DatabaseSync` (v22/v24) to `Database` (current docs) [V S27].
   - Node 24 is Active LTS until 2026-10-20, then Maintenance. **Node 26 becomes LTS on 2026-10-28** [V S29].

---

## 1. GitHub governance & identities

### 1.1 Rulesets vs classic branch protection

| Capability | Branch protection | Rulesets | Evidence |
|---|---|---|---|
| Plan availability | Public repos on Free (user or org); private repos on Pro/Team/GHEC | Same availability. Push rulesets need Team/GHEC private repos | [V S2] |
| Multiple rules per branch | Only one protection rule applies | Many rulesets aggregate, and the **most restrictive** version of each rule wins. Rulesets also layer on top of branch protection | [V S2] |
| Visibility | Admins | Anyone with read access can view active rulesets (useful for audit) | [V S2] |
| Enforcement modes | On / off | Active / Evaluate / Disabled. Evaluate mode does not block merges | [V S1] |
| Required approvals (writers) | Yes. Approvals must come from reviewers with **write** permission | Same | [V S1, S3] |
| Dismiss stale approvals on push | Yes. Approval is tied to the approved diff state; new pushes, **Update branch**, or a related merge into the base dismiss it | Same | [V S1, S3] |
| Require Code Owner review | Yes. Any one listed owner satisfies it | Same | [V S1, S3] |
| Require approval of most recent reviewable push (approver ≠ last pusher) | Yes | Yes ("someone other than the last person to push") | [V S1, S3] |
| Restrict who can dismiss reviews | Yes | Yes (users, teams, Apps) | [V S1, S3] |
| Required conversation resolution | Yes | Yes | [V S1] |
| Allowed merge methods | n/a | Yes (merge / squash / rebase) | [V S1] |
| Required status checks (strict/loose), pinned to a source App | Yes; can pin the expected source App | Yes. App must have `statuses:write` and must have recently reported the check | [V S1, S3] |
| Require linear history | Yes | Yes; repo must allow squash or rebase merging | [V S1] |
| Block force pushes | Default on | Default on | [V S1, S3] |
| Restrict who can push | **Org repos only** (Team/GHEC, or public repos in Free orgs) | "Restrict updates/creations/deletions"; only bypass actors may perform them | [V S3, S1] |
| Bypass list | "Actors may only be added to bypass lists when the repository belongs to an organization." Admins bypass by default unless "Do not allow bypassing" is set | Eligible: repository admins, org/enterprise owners, maintain/write roles, teams, **GitHub Apps**, Dependabot, deploy keys (GHES). Option "For pull requests only" | [V S3, S4] |
| Team "Required reviewers" (per path) | n/a | Yes; teams with write access; **not available on user-owned repos** | [V S1] |
| Merge queue | Yes | Yes ("Require merge queue") | [V S1] |
| Extra approval for unattributed Copilot PRs | n/a | On by default | [V S1] |

Notes:
- Branch protection's "Do not allow bypassing the above settings" applies the rules to admins too [V S3]. **MERCURY needs this** because the human owner is an admin.
- Whether a ruleset bypass list can be populated on a *user-owned* repo is **not confirmed**; see Unknowns. Assume it cannot be.
- An open PR that points at the same head commit and has pending or rejected reviews blocks the merge [V S5].

### 1.2 Who can approve, and what counts

| Question | Answer | Marker |
|---|---|---|
| Can a PR author approve their own PR? | No. GitHub blocks self-approval; the REST call fails with 422. | [V~ S20] (vendor text quoted second-hand; long-standing behaviour) |
| Which approvals count? | Only approvals from users with **write** or higher permission. For "Code Owner review", the approver must be a listed code owner (a user or team with explicit write access). | [V S1, S3, S10] |
| Can a bot or App identity submit `APPROVE`? | Yes. `POST /repos/{o}/{r}/pulls/{n}/reviews` accepts `event ∈ {APPROVE, REQUEST_CHANGES, COMMENT}`, is enabled for GitHub Apps, and needs only `pull_requests:write`. **The token permission cannot be narrowed to "comment only".** | [V S11, S8] |
| Does an App or bot approval count toward "required approvals"? | Probably yes when the App has write-level access to the repo. Documentation found today does not state this explicitly. GitHub created the "Allow GitHub Actions to create and approve pull requests" control precisely because `GITHUB_TOKEN` approvals could otherwise satisfy required reviews. | [I] |
| Can an App approval satisfy "Require review from Code Owners"? | No. CODEOWNERS entries must be `@user` or `@org/team` with write access, and Apps cannot be listed. | [V S10] |
| Copilot reviews | Copilot reviews do not count toward required approvals. | [V~ S20] |
| "Allow GitHub Actions to create and approve pull requests" | Default **off** for new personal-account repositories; org repos inherit from org settings. Controls whether `GITHUB_TOKEN` may create or approve PRs. | [V S19] |

**How to make sure an agent's approval never satisfies the requirement.** Use defence in depth, relying only on software-enforced controls:
1. Enable `Require review from Code Owners` with `CODEOWNERS` = `* @usjbro` (the human only), and keep `CODEOWNERS` itself covered by `*` [V S10].
2. Enable `Require approval of the most recent reviewable push`. The agent identity is always the last pusher, so its approval can never satisfy the rule [V S1].
3. Enable `Dismiss stale approvals`, so a human approval is invalidated by any later agent push [V S1].
4. Set "Do not allow bypassing" (branch protection), or keep the ruleset bypass list empty [V S3].
5. Keep `Allow GitHub Actions to create and approve pull requests` OFF [V S19].
6. Policy layer: Claude posts its PR review with `event=COMMENT` (or `REQUEST_CHANGES`), never `APPROVE`. This is **policy-enforced only**, because `pull_requests:write` permits `APPROVE` [V S8]. Controls 1–4 make an accidental agent `APPROVE` harmless.
7. Detective control: on every merge, check that `merged_by.login == <human>` and that a review exists with `state=APPROVED`, `user.login == <human>` and `commit_id == head sha at merge`. Raise a security alert otherwise [V S11; `pull-request` has `merged`, `merged_by`, `merge_commit_sha`, `merged_at`; `pull-request-review` has `user`, `state`, `commit_id`, `submitted_at`, `author_association`].

### 1.3 Identity options for agents

Permissions needed, from GitHub's fine-grained permission tables [V S8]:

| Action | Endpoint | Permission (fine-grained PAT and App) |
|---|---|---|
| Push a branch | git over HTTPS, `POST /git/refs` | `contents:write` (`workflows:write` if `.github/workflows/**` is touched) |
| Open or update a PR | `POST/PATCH /pulls` | `pull_requests:write` |
| Post a review | `POST /pulls/{n}/reviews` | `pull_requests:write` |
| PR conversation comment | `POST /issues/{n}/comments` | `issues:write` **or** `pull_requests:write` |
| Read checks | `GET /commits/{ref}/check-runs` | `checks:read` (**not available to fine-grained PATs**: "Using fine-grained PAT to call the Checks API" is a listed gap) [V S9b] |
| Read commit statuses | `GET /commits/{ref}/status` | `commit_statuses:read` [I] |
| **Merge** | `PUT /pulls/{n}/merge` | **`contents:write`**; the same permission needed to push |
| Metadata | all | `metadata:read` (implicit) |

Comparison:

| Option | Pros | Cons / constraints |
|---|---|---|
| **GitHub App** installed on the `usjbro` account, selected repo only | Distinct bot identity (`<app>[bot]`). Installation token **expires after 1 hour** [V S12b], so minting is automatic. Can read the Checks API. Rate limit ≥ 5,000/h [V S7]. Cannot be a code owner, so it cannot satisfy human review [V S10]. Can be pinned as the expected source of status checks [V S1]. | The private key (PEM) is a long-lived secret and belongs in the Keychain. With `contents:write` it **can merge** once protections are satisfied (see §1.4). |
| **Machine user** (second GitHub account) added as collaborator | Real user identity; simple `gh` / git usage | Personal-repo collaborators always get write access (no read-only, no granular roles) [V S9]. **Fine-grained PATs do not work for repos where the user is only a collaborator** [V S9b], so a classic PAT is required, which is coarse (`repo` scope). Its approvals **would** count toward plain "required approvals", so Code Owner and last-push rules are mandatory. Extra account against GitHub ToS limits on machine accounts [I]. |
| **Human's fine-grained PAT** | Easy | **Reject.** It acts as the human, so the agent becomes the PR author (the human then cannot approve) and the agent can merge as admin. |
| `GITHUB_TOKEN` in Actions | Ephemeral | Only inside workflows; not usable by the Mac coordinator. |

Can `contents:write` bypass protection? No. Pushes and merges by a non-bypass actor still have to satisfy every rule. Only bypass-list actors, or admins when bypassing is allowed, can skip them [V S1, S3]. A GitHub App is admin-equivalent only if it is granted `administration:write`, and **MERCURY must never grant that** [I].

### 1.4 Gap: "only the human can merge" on a user-owned repo

- **Status quo (personal repo).** Any write-capable identity can merge after the human approves. Branch restrictions and bypass lists are org-only [V S3]. Merge queue and ruleset "Restrict updates" both depend on bypass actors.
  - Enforcement of "the human decides" is preventive: a merge cannot happen without the human's approval of the latest push.
  - Enforcement of "the human clicks merge" is only detective: a `merged_by` check plus alerting.
  - **Software-enforced:** approval. **Policy plus detection:** merge actor.
- **Recommended upgrade.** Transfer the repo to a GitHub **organization** (a Free org is enough for public repos; Team for private). Then:
  - add a branch restriction / ruleset "Restrict updates" whose only permitted actor is the human;
  - or enable a merge queue where only the human enqueues [V S1, S3].

  This makes "human merges" software-enforced. The cost is an org admin surface; record it as an ADR candidate.

---

## 2. GitHub event delivery without inbound access

| Option | Works without inbound? | Notes | Marker |
|---|---|---|---|
| **REST polling + conditional requests** | Yes | Keep the `etag` and send `If-None-Match`. A `304` is not charged to the primary rate limit if the request is authorized. Use stable, narrow queries (e.g. `GET /pulls?head=owner:branch`) and a stable sort; avoid `sort=updated`. GitHub's docs say to prefer webhooks, and when polling is unavoidable to use conditional requests, serialize requests, and space mutations ≥ 1 s apart. | [V S6] |
| GraphQL polling | Yes | Fewer round trips for PR + reviews + checks. Points-based limit (5,000 points/h for users) [I]. **No ETag/304 support** [I], so it is better for occasional reconciliation than for tight loops. | [I] |
| `gh` CLI | Yes | Wraps REST/GraphQL; `gh api` supports `-H 'If-None-Match: …'`. Convenient but harder to test than a typed client. | [I] |
| Events API / Notifications API | Yes | **Not real time:** "event latency can be anywhere from 30s to 6h". Do not use for control flow. | [V S11] |
| GitHub Actions as relay | Partly | Actions run in GitHub's cloud and cannot reach the Mac either. They can only reshape events into something the Mac polls (labels, statuses). Adds an attack surface for little gain. | [I] |
| Self-hosted runner on the Mac | Yes (outbound HTTPS 443 long-poll) | GitHub: "only use self-hosted runners with private repositories… forks of your public repository can potentially run dangerous code". **This repo is public, so reject.** | [V S21] |
| smee.io / webhook proxy / `gh webhook forward` | Yes (outbound SSE/WebSocket) | Payloads transit a third party. On smee the channel URL is the only secret, so anyone holding it can read or inject events; the HMAC signature must be checked locally. Intended for development. Treat any webhook payload only as a **hint** to poll, never as the source of truth. | [I] |
| Cloud relay owned by the operator (e.g. a small queue) | Yes | Adds a hosted component, contrary to "locally hosted"; out of scope unless an ADR approves it. | [I] |

**Rate-limit budget.** PAT/user: 5,000 requests/h, shared across every app acting for that user. App installation: 5,000/h, scaling to 12,500 (15,000 on GHEC) [V S7]. Polling 10 open PRs × 3 endpoints every 60 s ≈ 1,800 requests/h worst case. Most of those return `304`, which is free. Secondary limits return 403/429 with `retry-after`; honour it and back off exponentially [V S6b].

**Human notifications.** GitHub already notifies on review requests, @mentions and assignments, by email, on the web and in GitHub Mobile [I]. Linear can also push review requests and check failures to its inbox and mobile app [V S12c]. MERCURY should **request the human's review** on the PR (`POST /pulls/{n}/requested_reviewers`) and @mention only for escalations, rather than build its own channel.

**Merge verification recipe** [V S11]:
1. `GET /pulls/{n}` must show `merged=true`, a recorded `merged_at`, `merge_commit_sha`, and `merged_by.login`.
2. `GET /pulls/{n}/reviews` must contain an APPROVED review from the human whose `commit_id` equals the PR head at merge.
3. `GET /repos/{o}/{r}/commits/{merge_commit_sha}` must exist on the base branch.
4. Check runs for the head SHA must be all required = success.

The async merge API (`PUT /pulls/{n}/merge-async`) is now GitHub's recommended merge endpoint [V S11]. MERCURY does not merge, but should recognise merges done that way.

---

## 3. Linear API / integration

| Topic | Finding | Marker |
|---|---|---|
| API | Public GraphQL, the same API Linear uses internally; full mutation support | [V S12a] |
| Personal API keys | Admins may allow member keys. Each key can be **full access** or restricted to *Read, Write, Admin, Create issues, Create comments*, and **limited to specific teams** | [V S12a] |
| OAuth apps & `actor=app` | Adding `actor=app` to the authorization URL installs the integration as an **app user** instead of acting as the installing human. A workspace admin must install it, and it cannot request the `admin` scope. Opt-in scopes: `app:assignable` (can be delegated issues) and `app:mentionable`. Agents are not billable seats and cannot sign in or administer | [V~ S13, S14; V S12d] |
| Agent sessions | An `AgentSessionEvent` webhook fires on mention, delegation or user prompt, with `created` and `prompted` actions. The receiver must respond within ~5 s and should emit a `thought` activity within ~10 s. **This depends on webhooks, so it needs public inbound and is unusable directly on the Mac** | [V~ S14, S15] |
| Rate limits | Request- and complexity-based, **per user**: keys belonging to the same user share one quota. Current docs list API key 2,500 requests/h, OAuth app 5,000 requests/h, unauthenticated 600/h per IP. Complexity budgets are in the millions of points per hour. Headers include `X-RateLimit-Complexity-{Limit,Remaining,Reset}`. Some mutations have lower per-endpoint limits. *Numbers changed recently; re-verify.* | [V~ S16b] |
| Webhooks | Data-change events for Issues, Comments, Issue attachments, Documents, Reactions, Projects, Project updates, Cycles, Labels, Users, SLAs. Admin required to manage them. Payload includes previous values. Signed with HMAC (`Linear-Signature`). **Needs a public HTTPS URL** | [V S12a; V~ S15] |
| Polling alternative | `issues(filter: { updatedAt: { gt: $cursor } }, orderBy: updatedAt)` plus a per-team cursor saved in SQLite. Use overlapping windows and dedupe by `(id, updatedAt)` | [I] |
| Idempotency | Most `*Create` mutations accept a client-supplied `id` (UUID), so retries can use deterministic IDs. `attachmentCreate` is keyed on (issue, url): re-creating with the same URL updates the attachment | [I] |
| Relations | `issueRelationCreate(type: blocks \| duplicate \| related)`. "Blocked by" is the inverse side, read via `inverseRelations` | [I] |
| Comments / attachments | `commentCreate` with Markdown body; `attachmentCreate` / `attachmentLinkGitHubPR` for PR links | [I] |
| Native GitHub integration | Links PRs through branch names containing the issue ID, the issue ID in the PR title, or magic words in the description. Closing words: `close/fix/resolve/complete/implement` and variants. **Non-closing** words: `ref, references, part of, related to, contributes to, towards, updates`. Team-level workflow automation moves status on draft / open / review requested / ready for merge / **merge**, with branch-specific rules. Linkback comments are posted on the PR. Described from the GitLab page; the GitHub page is the same model | [V S12e (GitLab page), I for GitHub parity] |
| Linear Reviews / Coding sessions | Linear can show and review GitHub PRs, and **approve or merge them from Linear** under the human's GitHub identity. "Coding sessions" let **Linear Agent run Claude Code or Codex** on a delegated issue and open draft PRs. Triage automations can start them automatically | [V S12, S12c] |
| Agent attribution | A `<!-- linear:extension {"version":1,"plugins":[{"plugin":"onBehalfOf","agent":"claude"\|"codex",…}]} -->` block in a PR comment shows "on behalf of" attribution in Linear | [V S12] |

Interaction with a coordinator that updates status:
- Two writers cause flapping: the native integration moves status on PR open and merge, and the coordinator would set the same fields.
- Rule: either (a) let the integration own `In Review → Done` and have the coordinator only *verify*, or (b) disable PR automations for MERCURY teams and let the coordinator own all transitions.
- Use **non-closing magic words** (`Part of ENG-123`) if the coordinator must own `Done` after its post-merge verification.
- Linear status changes are **never** authorization (hard constraint). Linear-native delegation or Coding sessions on MERCURY-managed issues would be a parallel, unauthorized execution path, so the design must detect it (a `delegate` set to a non-MERCURY agent) and refuse or flag it.

---

## 4. macOS launchd & sleep

### 4.1 LaunchAgent vs LaunchDaemon

| | LaunchAgent (`~/Library/LaunchAgents`, domain `gui/<uid>`) | LaunchDaemon (`/Library/LaunchDaemons`, `system`) |
|---|---|---|
| Context | Per-user; "specific to a given logged-in user and executes only while that user is logged in" | System; runs with no user logged in; root unless `UserName` |
| Login keychain | Available once the user's keychain is unlocked at login | Not available ("system process doesn't have access to any of the user keychains") |
| TCC | Attributed to the user session, but still subject to folder protection | Separate TCC context; often denied user folders |
| Stop | SIGTERM on logout | SIGTERM on shutdown |
| Evidence | [V S16, S17] | [V S16, S17; V~ S22] |

**Recommendation:** LaunchAgent with `LimitLoadToSessionType=Aqua` (the default) [V S17]. Consequences:
- **After a reboot, MERCURY does not run until the user logs in.** With FileVault on, automatic login is unavailable [I].
- Recovery must therefore be "resume at next login", and the human should be told when the coordinator was down for a long time.
- Since macOS 13, launch agents show up under System Settings › General › Login Items › "Allow in the Background", and **the user can switch them off** [I]. Phase 0 must check this.

### 4.2 Plist keys (OSS `launchd.plist(5)`) [V S18m]

| Key | Behaviour | MERCURY use |
|---|---|---|
| `KeepAlive` (bool or dict) | `true` keeps the job alive unconditionally. Dict conditions (`SuccessfulExit`, `PathState`, `OtherJobEnabled`, `Crashed`…) are ORed. Jobs that exit fast and often are throttled | `{SuccessfulExit: false}`: restart on crash, allow clean stop. `NetworkState` is documented in the OSS page but is believed to be no longer honoured [I] |
| `RunAtLoad` | Start once at load. Default false | `true` |
| `ThrottleInterval` | Respawn no more than once per N s; **default 10 s** | Keep the default or 30 s; add backoff in the app |
| `ExitTimeOut` | Seconds between SIGTERM and SIGKILL; **default 20 s**; 0 = infinite | 30–60 s. Shutdown/logout may still cut it short [I] |
| `ProcessType` | `Background` = CPU/IO throttled; `Standard` = default light limits; also `Adaptive`, `Interactive` | `Standard` (or `Adaptive`); never `Background` for the coordinator |
| `StandardOutPath` / `StandardErrorPath` | stdio redirection | Log files under `~/Library/Logs/Mercury/`, with rotation done by MERCURY |
| `EnvironmentVariables`, `WorkingDirectory`, `Umask` | As named. Umask needs a **decimal** value | Explicit `PATH` (launchd's default `PATH` is minimal [I]); no secrets in the plist |
| `SoftResourceLimits` / `HardResourceLimits` | setrlimit keys (`NumberOfFiles`, `NumberOfProcesses`, …) | Raise `NumberOfFiles` |
| `AbandonProcessGroup` | By default, **when the job dies launchd kills the remaining processes in its process group** | Children spawned `detached` (new session) **escape** this, so MERCURY must reap them itself |

### 4.3 `launchctl` (modern subcommands) [V~ S19m]

```
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/<label>.plist   # load
launchctl bootout   gui/$(id -u)/<label>                                # unload
launchctl kickstart -k gui/$(id -u)/<label>                             # restart (kill existing)
launchctl print     gui/$(id -u)/<label>                                # state, pid, last exit
launchctl enable|disable gui/$(id -u)/<label>
```
`load`/`unload` are legacy. "Bootstrap failed: 5: Input/output error" usually means the job is already loaded [V~ S19m].

### 4.4 Sleep, App Nap and wake

- During system sleep, user processes do not run. Timers stop firing and sockets may be torn down. Treat every sleep as an indefinite pause [I].
- `IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleSystemSleep)`:
  - prevents **idle** sleep only;
  - "The system may still sleep for lid close, Apple menu, low battery, or other sleep reasons";
  - "does not put the system into Dark Wake";
  - needs no privileges [V S20a].
- `caffeinate -i` prevents idle sleep. `-s` prevents system sleep but **only on AC power**. `-w <pid>` holds the assertion until that PID exits [V~ S21m].
- `pmset`:
  - processes can override settings with assertions, listed by `pmset -g assertions`;
  - changing settings needs root;
  - `pmset -g log` shows sleep and wake history [V~ S22m].
- Power Nap / DarkWake does not schedule third-party user processes [I].
- **App Nap** applies to *apps* (not foreground, no visible drawing, no power or NSProcessInfo assertion). It throttles CPU and timer frequency. A launchd job is governed by `ProcessType` instead. Holding a power assertion also exempts an app [V S24].
- Clamshell: closing the lid sleeps the Mac unless it is in clamshell mode (external display + power + input) [I].
- **Wake detection.** Compare wall-clock time (`Date.now()`) with monotonic time (`process.hrtime.bigint()`). On macOS the monotonic clock is believed to **not advance during sleep**, so a gap between the two means the machine slept [I; verify in Phase 0]. Also re-check the network after wake: probe `api.github.com` / `api.linear.app` with backoff, because DNS and Wi-Fi typically need seconds [I].

### 4.5 Keychain & TCC

- From a LaunchAgent, `security find-generic-password -s <service> -a <account> -w` works once the login keychain is unlocked.
- If the item's ACL would trigger a prompt, it fails with `errSecInteractionNotAllowed (-25308)`. Create items with `-T /usr/bin/security` (or the coordinator binary) instead of `-A` [V~ S22; I].
- A LaunchDaemon cannot read the login keychain [V~ S22].
- Passing a secret on argv exposes it to `ps`. Read it through stdin or a pipe, or use the Security framework via a native helper [I].
- **TCC.** Desktop, Documents and Downloads (and iCloud Drive and removable volumes) are protected. A launchd-run `node` gets **EPERM ("Operation not permitted")**. Full Disk Access can only be granted to app bundles or binaries through System Settings, and the grant follows the *responsible process* [V~ S23].
  - **Constraint:** place the DB, logs, artifacts and worktrees outside the protected folders, e.g. `~/Library/Application Support/Mercury/` and `~/Developer/mercury-worktrees/`.
  - Do not require Full Disk Access.

---

## 5. Persistence & Node runtime

### 5.1 SQLite

| Topic | Finding | Marker |
|---|---|---|
| WAL + `synchronous` | WAL with `NORMAL` is always **consistent**, but "WAL mode does lose durability": the latest commits can roll back after power loss or an OS crash. `FULL` adds a WAL sync after every commit, which makes commits durable. All modes survive an *application* crash | [V~ S25] |
| macOS fsync | `fsync` on macOS does not force the drive cache. `PRAGMA fullfsync=ON` uses `F_FULLFSYNC` for every sync; `checkpoint_fullfsync` applies it to checkpoints only. Both are **off by default**. Measurable write-latency cost | [V~ S26] |
| Recommendation | `journal_mode=WAL`, `synchronous=FULL`, `fullfsync=ON` for the coordinator DB. Write volume is low (events, not telemetry), and a lost commit could mean duplicate execution | [I] |
| Concurrency | One writer at a time. Take the write lock up front with `BEGIN IMMEDIATE` to avoid deadlock-style `SQLITE_BUSY` on upgrade. Set `busy_timeout` (Node: `timeout` option). Recommend a single writer process (the coordinator); other processes are read-only or go through IPC | [I; Node `timeout` = busy timeout V S27] |
| Backup | Online backup API (Node `sqlite.backup(db, path, {rate})`, async, page-batched) or `VACUUM INTO 'file'`. Both are safe on a live WAL database | [V S27 for Node API; I for VACUUM INTO] |
| Integrity | `PRAGMA quick_check` at start-up, `PRAGMA integrity_check` daily and before migrations | [I] |
| Migrations | `PRAGMA user_version` + forward-only numbered migrations, each inside `BEGIN IMMEDIATE … COMMIT`, with a backup before each one | [I] |
| Defensive | Node `node:sqlite` enables `SQLITE_DBCONFIG_DEFENSIVE` by default in recent versions; extension loading off by default; `setAuthorizer()` is available | [V S27] |

### 5.2 Node.js

| Topic | Finding | Marker |
|---|---|---|
| LTS status (2026-10-12) | v22 "Jod": Maintenance until **2027-04-30**. v24 "Krypton": Active LTS until **2026-10-20**, then Maintenance until 2028-04-30 (latest 24.21.0, 2026-09-07). v26: Current (26.11.1), **LTS from 2026-10-28** until 2029-04-30. v20: EOL 2026-04-30 | [V S29] |
| `node:sqlite` stability | v22 docs: **1.1 Active development**. v24 docs: **1.2 Release candidate**. Latest docs: 1.2 RC (made RC in v25.7.0) | [V S27] |
| API churn | v22/v24: `DatabaseSync` / `StatementSync`. Latest docs: `Database` / `Statement`. `timeout` option added in v24.0.0 / v22.16.0. `sqlite.backup()` signature changed (`destination` → `path`) | [V S27] |
| `better-sqlite3` | Mature synchronous native addon with prebuilt binaries per Node ABI. Must be rebuilt or re-downloaded on Node major upgrades. Supply-chain surface (install scripts) | [I] |
| Recommendation | Target **Node 24 LTS** now and plan to move to 26 LTS. Use `node:sqlite` behind a thin repository interface, which absorbs the class rename and allows a fallback to `better-sqlite3` if RC behaviour regresses. Pin the exact Node version | [I] |
| `spawn` with `detached` | On POSIX, the child becomes **leader of a new process group and session** (setsid) | [V S28] |
| Killing trees | `process.kill(-pgid, 'SIGTERM')` signals the whole group (POSIX `kill(2)` with a negative pid). Escalate to `SIGKILL` after a grace period. Record `pid`, `pgid` and the process start time in SQLite so PID reuse cannot cause the wrong kill after a restart | [I; signal default `SIGTERM` V S28b] |
| Signals | SIGTERM and SIGINT have default handlers on non-Windows; adding a listener removes the default exit behaviour, so the handler must exit explicitly | [V S28b] |

---

## 6. Design implications (constraints MERCURY must respect)

**GitHub**
- **G1.** Agents must **never** use the human's GitHub credentials (no `gh auth` as `usjbro`, no human PAT) in the coordinator, Codex or Claude processes.
- **G2.** Use a dedicated **GitHub App** (preferred) or a machine user. Minimum permissions: `contents:write`, `pull_requests:write`, `issues:write` (optional), `checks:read`, `statuses:read`, `metadata:read`. **Never** `administration`, `workflows:write` (unless explicitly approved), or `members`.
- **G3.** Required protection on `main`:
  - PR required;
  - ≥ 1 approval;
  - **Code Owner review** with `CODEOWNERS: * @usjbro`;
  - **approval of most recent reviewable push**;
  - **dismiss stale approvals**;
  - required status checks (strict) pinned to the expected App where possible;
  - linear history (optional);
  - block force push and deletion;
  - "Do not allow bypassing" / empty bypass list;
  - Actions-approve setting OFF.
- **G4.** Claude reviews are posted as `COMMENT` / `REQUEST_CHANGES` only. This is **policy**; G3 makes a violation harmless.
- **G5.** On the current personal repo, *human merges* is enforced only by detection (`merged_by` check plus alert). Software enforcement needs an **org-owned repo** with restricted updates. Raise this as an ADR and an operator decision.
- **G6.** The coordinator never calls a merge endpoint. Any merge not done by the human is a security incident.
- **G7.** Merge verification must check `merged`, `merged_by`, `merge_commit_sha` on the base branch, the human's APPROVED review on the final head SHA, and the required checks.

**Event delivery**
- **E1.** Poll GitHub REST with ETag/`If-None-Match`, one request at a time, ≥ 1 s between mutations, and honour `retry-after`. Webhook-style relays are hints only, never the source of truth.
- **E2.** No self-hosted Actions runner on the Mac while the repo is public.
- **E3.** Poll Linear with `updatedAt` cursors stored durably, with overlap and dedupe. Do not depend on Agent Session webhooks.

**Linear**
- **L1.** A Linear status change can mark an issue "eligible for Claude evaluation", never authorization.
- **L2.** Pick a single owner for each Linear status transition. Either disable the integration's PR automations for MERCURY teams, or use non-closing magic words and let the coordinator verify and set `Done`.
- **L3.** Detect and refuse Linear-native delegation or Coding sessions on MERCURY-managed issues.
- **L4.** Use deterministic client IDs for creates, so retries are idempotent.
- **L5.** Use a team-scoped API key with minimum permissions, or an `actor=app` OAuth app, so MERCURY's writes are attributable to a non-human actor.

**macOS**
- **M1.** Run as a per-user LaunchAgent in `gui/<uid>` with `KeepAlive{SuccessfulExit:false}`, `RunAtLoad`, `ProcessType=Standard`, explicit `PATH`, and `ExitTimeOut` ≥ 30.
- **M2.** Handle SIGTERM by checkpointing state and signalling child groups within `ExitTimeOut`.
- **M3.** Assume no execution while asleep, logged out, or after a reboot until login. Every state with a timeout uses **wall-clock deadlines checked on wake** and treats sleep gaps as pauses, not failures.
- **M4.** Power assertions (`caffeinate -i -w <pid>`) may be held while an agent run is active to stop *idle* sleep. They are never relied on for correctness.
- **M5.** Keep secrets in the login Keychain and read them from the LaunchAgent without printing them. Never use argv, plists or logs.
- **M6.** Keep all MERCURY paths outside TCC-protected folders, and do not require Full Disk Access.
- **M7.** Phase 0 check: the "Allow in the Background" toggle for the agent.

**Persistence and runtime**
- **P1.** Use SQLite WAL with `synchronous=FULL`, `fullfsync=ON`, a single writer, `BEGIN IMMEDIATE`, and `busy_timeout` ≥ 5 s.
- **P2.** Checks: `quick_check` at start-up, `user_version` migrations with a backup taken before each, and a daily online backup.
- **P3.** Target Node 24 LTS, moving to 26 LTS. Wrap `node:sqlite` behind an interface. Pin versions.
- **P4.** Spawn agent CLIs `detached` in their own process groups. Persist pid, pgid and start time. Reap orphans on start-up. Kill trees with `-pgid`, SIGTERM then SIGKILL.

---

## 7. Unknowns (for Phase 0 or later verification)

1. Can a ruleset **bypass list** be populated on a **user-owned** repository (e.g. the "Repository admin" role)? Branch-protection docs say bypass actors require an org [S3]; the rulesets docs are silent.
2. Explicit GitHub documentation that **GitHub App `APPROVE` reviews count** toward "required approvals". Assumed yes; G3 neutralises it either way.
3. The operator's GitHub plan, and whether the repo will stay public. Both affect rulesets on private repos and the self-hosted runner stance.
4. Whether the operator accepts moving the repo to an **organization** (G5).
5. Exact current Linear rate-limit numbers, and whether `attachmentCreate` / `*Create` idempotency-by-ID holds for all entities MERCURY uses.
6. Linear plan and team workflow automations currently configured, whether the GitHub integration is installed, and whether Linear Coding sessions are enabled.
7. macOS version, FileVault and auto-login state, whether the Mac is a laptop (lid / AC) or a desktop, `pmset -g` settings, and the Login Items background toggle.
8. Whether Node's monotonic clock pauses during sleep on the operator's macOS / Apple Silicon (`process.hrtime` vs `Date.now()` experiment).
9. Current `launchd.plist(5)` defaults on the installed macOS (`ExitTimeOut`, `ThrottleInterval`, `NetworkState` support).
10. Where the operator keeps repositories (inside `~/Documents`?), which determines TCC exposure.
11. Node version installed on the Mac, and whether `node:sqlite` in that version exposes `backup()` and `timeout`.

---

## 8. Sources

GitHub (read from `github/docs` main branch source and `github/rest-api-description`, 2026-10-12):
- **S1** Available rules for rulesets: `content/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets.md` (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- **S2** About rulesets, plus `data/reusables/gated-features/repo-rules.md` and `protected-branches.md` (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- **S3** About protected branches (https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- **S4** Creating rulesets for a repository, and `data/reusables/repositories/rulesets-bypass-step.md`, `rulesets-branch-tag-bypass-optional-step.md`
- **S5** `data/reusables/pull_requests/required-reviews-for-prs-summary.md`, `data/reusables/repositories/review-policy-overlapping-commits.md`
- **S6** Best practices for using the REST API (conditional requests, avoid polling) (https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api); **S6b** secondary-limit handling, same file and the rate-limits page
- **S7** Rate limits for the REST API, plus reusables `primary-rate-limit-authenticated-users.md` and `primary-rate-limit-github-app-installations.md` (https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
- **S8** Fine-grained PAT and server-to-server permission tables: `src/github-apps/data/fpt-2022-11-28/{fine-grained-pat-permissions,server-to-server-permissions}.json`
- **S9** Permission levels for a personal account repository (https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository); **S9b** Managing your personal access tokens: fine-grained PAT limitations (https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- **S10** About code owners (https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- **S11** GitHub REST OpenAPI description (`api.github.com.json`): pulls/reviews/merge/merge-async endpoints; `pull-request` and `pull-request-review` schemas; Notifications latency note
- **S12b** Authenticating as a GitHub App installation, which documents the 1 h token expiry (https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/authenticating-as-a-github-app-installation)
- **S19** Managing GitHub Actions settings for a repository: "Preventing GitHub Actions from creating or approving pull requests" (https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
- **S20** Secondary and vendor-quoting search excerpts on self-approval and Copilot reviews: https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews ; https://zenn.dev/inaniwaudon/articles/09f20fbec91f27 ; https://github.blog/changelog/2022-01-13-github-actions-prevent-github-actions-from-approving-pull-requests
- **S21** Self-hosted runner security: `data/reusables/actions/self-hosted-runner-security.md`; `content/actions/reference/runners/self-hosted-runners.md`
- Repository facts: `gh api repos/usjbro/Project-Mercury` → `owner.type=User`, `visibility=public`

Linear:
- **S12** Linear Docs, Reviews / Diffs (https://linear.app/docs/diffs); **S12a** API and Webhooks (https://linear.app/docs/api-and-webhooks); **S12c** Coding settings (https://linear.app/docs/code-and-reviews) and Coding sessions (https://linear.app/docs/coding-sessions); **S12d** AI Agents (https://linear.app/docs/agents-in-linear); **S12e** GitLab integration (magic words, automation) (https://linear.app/docs/gitlab). These were retrieved through Linear's documentation search tool.
- **S13** Linear Developers, Agents (https://linear.app/developers/agents) [search excerpt]
- **S14** Linear Developers, Agent interaction (https://linear.app/developers/agent-interaction) [search excerpt]
- **S15** Hookdeck, building Linear agents (https://hookdeck.com/webhooks/platforms/how-to-build-linear-agents-with-hookdeck-cli) [secondary]
- **S16b** Linear Developers, Rate limiting (https://linear.app/developers/rate-limiting) [search excerpt]

Apple / macOS:
- **S16** Apple, Creating Launch Daemons and Agents (https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
- **S17** Apple, Designing Daemons and Services (https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/DesigningDaemons.html); TN2083 Daemons and Agents (https://developer.apple.com/library/archive/technotes/tn2083/_index.html)
- **S18m** `launchd.plist(5)`, Apple OSS (https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5) [older than current macOS]
- **S19m** `launchctl(1)` mirrors: https://leancrew.com/all-this/man/man1/launchctl.html , https://unix.com/man-page/mojave/1/launchctl/ [search excerpt]
- **S20a** IOKit `IOPMAssertionCreateWithName` and `kIOPMAssertionTypePreventUserIdleSystemSleep` (https://developer.apple.com/documentation/iokit/1557134-iopmassertioncreatewithname , https://developer.apple.com/documentation/iokit/kiopmassertiontypepreventuseridlesystemsleep)
- **S21m** `caffeinate(8)` mirror: https://sudo.is/docs/macos/man_caffeinate.html [search excerpt]
- **S22m** `pmset(1)` mirror: https://sudo.is/docs/macos/man_pmset.html [search excerpt]
- **S22** Apple Developer Forums, daemon keychain access: https://developer.apple.com/forums/thread/656000 , https://developer.apple.com/forums/thread/685967 [secondary]
- **S23** Apple Developer Forums, TCC and daemons: https://developer.apple.com/forums/thread/118508 , https://developer.apple.com/forums/thread/661178 [secondary]
- **S24** Apple, Energy Efficiency Guide for Mac Apps: App Nap (https://developer.apple.com/library/archive/documentation/Performance/Conceptual/power_efficiency_guidelines_osx/AppNap.html)

SQLite / Node:
- **S25** SQLite `PRAGMA synchronous` docs text (https://www.sqlite.org/pragma.html#pragma_synchronous; docsrc mirror https://www.sqlite.org/docsrc/info/bcf687da9c172292) [search excerpt]
- **S26** SQLite `fullfsync` / `checkpoint_fullfsync` (https://www.sqlite.org/docsrc/info/b5201ace8f761b5a ; forum https://sqlite.org/forum/info/b94afa45dda82aae8cbf49f9d511a00b332870fc926cba18954acd889bbfb7cd) [search excerpt]
- **S27** Node.js `node:sqlite` docs: latest (https://nodejs.org/api/sqlite.md), v24 (https://nodejs.org/docs/latest-v24.x/api/sqlite.md), v22 (https://nodejs.org/docs/latest-v22.x/api/sqlite.md)
- **S28** Node.js `child_process` (`options.detached`) (https://nodejs.org/api/child_process.md); **S28b** Node.js `process` (signals, `process.kill`) (https://nodejs.org/api/process.md)
- **S29** Node.js release schedule (https://raw.githubusercontent.com/nodejs/Release/main/schedule.json) and dist index (https://nodejs.org/dist/index.json)
