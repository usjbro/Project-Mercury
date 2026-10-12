# ADR-008: Identity inventory

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-02, OD-03, OD-04, OD-05, OD-20)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2 as "Agent identities and merge governance") |
| Owner | Agent A. Agent B owns exact GitHub and Linear permission settings (`integrations/github.md` §2, `integrations/linear.md`); Agent D owns Keychain item names (`operations/macos-service.md` §9); Agent E owns the threat analysis (`security/threat-model.md` §6) |
| Supersedes | The merge-governance half of this ADR's Phase 2 text, now [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md). The file name is kept for link stability |
| Related ADRs | [ADR-013](ADR-013-agent-process-isolation.md), [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md), [ADR-018](ADR-018-audit-integrity.md), [ADR-019](ADR-019-notifications-and-operator-presence.md) |

## Context
- Today every agent action uses the operator's identities: GitHub `usjbro` (admin), the Linear user and the Slack user (discovery fact 3). An agent approval cannot be told apart from a human one.
- GitHub App permissions apply to **every repository the App is installed on**. Heartbeat and ops alerts need `issues:write` on `project-mercury`, the audit anchor needs `contents:write` on a private anchor repository, and the ruleset drift monitor needs to read rulesets on target repositories. Adding these to the App used on target repositories would widen it everywhere (RA-07, RE-10).
- Phase 3 found three incompatible permission sets for the main App (RA-06): this ADR granted neither `checks:write` nor `statuses:write`, so it could post neither gate.
- Hard constraint: no agent identity can satisfy required human approval or merge to a protected branch (CON-007, CON-008).

## Decision
**Every identity MERCURY uses is listed here. No coordinator or agent path ever uses the operator's GitHub, Linear or Slack credentials.** Each credential is a separate Keychain item read once by `mercuryd` at start and on `mercury reload-credentials` (RD-18), under the single prefix defined by D.

| Identity | Kind | Installed on / scope | Permissions | Used by | Never |
|---|---|---|---|---|---|
| **`mercury-bot`** | GitHub App | Target repositories only (selected repos) | `contents:write`, `pull_requests:write`, `checks:write`, `metadata:read`; plus `statuses:write` **only if** the Phase 0 pinning test requires it (RD-5) | Push task branches, open and update PRs, post `COMMENT` reviews, create the `MERCURY / claude-review` and `MERCURY / policy` check runs | `administration`, `workflows`, `actions`, `issues`; APPROVE, REQUEST_CHANGES, dismiss, merge, update-branch, auto-merge (endpoint allowlist, SEC-102) |
| **`mercury-ops`** | GitHub App | `project-mercury`, the private anchor repository, and target repositories (read-only) | `issues:write` on `project-mercury` (heartbeat issue, ops alerts); `contents:write` on the anchor repository; `metadata:read` on targets for the ruleset drift monitor (reads `/rulesets`) | Ops alerts, heartbeat, daily audit anchor ([ADR-018](ADR-018-audit-integrity.md)), governance drift monitor (SEC-108) | Any write to a target repository |
| **Linear app** | OAuth app, `actor=app` | MERCURY's Linear teams | Read issues and relations; write comments, `In Progress` and (in `mercury_owns_all` mode) `Done`; MERCURY labels | Linear projection and comments | Edit issue descriptions; any action as the human user |
| **Anthropic key** | Dedicated API workspace key with a spend limit | Claude decision runs | Model API only | Passed to the Claude run on fd 3 per run | Written to a file, argv, a log, or any other process's environment |
| **OpenAI key** | Dedicated project key with a spend limit | Codex runs | Model API only | Passed to the Codex run on fd 3 per run | Same as above |
| **`_mercuryagent`** | Hidden macOS role account (group `mercury`) | The Mac | No Keychain, no GitHub or Linear credential, home holds caches only | Every process that executes model-directed or repository-derived code ([ADR-013](ADR-013-agent-process-isolation.md)) | Read `MERCURY_HOME`, the operator's home or any Keychain |
| **Operator** | Human: GitHub `usjbro`, Linear user | Everything | Sole code owner, sole approver, sole merger; local CLI principal with the presence tier ([ADR-019](ADR-019-notifications-and-operator-presence.md)) | Approve and merge in the GitHub UI or app; CLI | Credentials are never available to MERCURY |
| **Deploy key** (only in G-SPLIT) | Repository deploy key | Target repositories | Push to `mercury/*` | Pushes, if G-SPLIT is chosen ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)) | Exists in G-ORG or G-DETECT |

Rules:
1. Installation tokens are minted per purpose with the narrowest repository and permission set the API allows.
2. Governance on target repositories uses **rulesets**, not classic branch protection, because `mercury-ops` reads `/rulesets` with `metadata:read` (RB-16). The ruleset content is in [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md).
3. Claude's reviews are posted by `mercury-bot` with a "Claude review" header; Claude itself has no GitHub identity.
4. The operator's own interactive agents are outside MERCURY but hold human credentials. Policy OD-35 restricts them ([ADR-019](ADR-019-notifications-and-operator-presence.md)).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| One App with all permissions (Phase 2 text) | Permissions are App-wide, so `issues:write` and anchor `contents:write` would reach every target repository (RA-07) |
| A third read-only "auditor" App for drift monitoring (RA-07 proposal) | `metadata:read` on `mercury-ops` is enough to read rulesets; a third identity adds setup and a Keychain item for no extra separation |
| Machine-user account with a PAT | Classic PAT needed on personal repos; a second human-like account; can be a collaborator with write |
| Operator's own token | Agent PRs authored as the human cannot be approved by the human; the token can merge as admin (today's state) |
| Linear personal API key | Writes appear as the human (the JAM-160 identity confusion) |
| Model keys through subscription logins | Interactive token expiry breaks unattended runs; no per-project spend limits (OD-03/OD-04) |

## Consequences
- **Positive:** every external write is attributable to a non-human identity; the target-repo App has no issue, workflow or admin permissions; ops and anchor writes cannot touch code.
- **Positive:** model spend is bounded per key by the provider.
- **Negative:** the operator creates two Apps, one Linear OAuth app and two model keys in Phase 0, and keeps them rotated (procedures in `threat-model.md` and `macos-service.md` §9).
- **Negative:** `mercury-bot` still holds `contents:write`, so on personal repositories the merge actor is only detectively controlled unless G-ORG is in place ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)).

## Related requirements
CON-007, CON-008, CON-010; FR-140, FR-180, FR-201; OPS-002, OPS-007; SEC-102, SEC-108, SEC-202, SEC-604, SEC-801.

## Related findings
RA-06, RA-07, RE-10, RF-10, RB-03, RB-05, RB-15, RB-16, RD-08.

## Operator decisions
- **OD-02** GitHub agent identity (default: GitHub Apps, no machine user).
- **OD-03 / OD-04** model billing (default: dedicated API keys with spend limits).
- **OD-05** Linear identity (default: OAuth `actor=app`).
- **OD-20** `mercury-ops` App (default: create it).

## Revision history
- Phase 4: became the identity inventory (RD-6); governance moved to ADR-014; `mercury-bot` gains `checks:write` and loses `issues:write`; `mercury-ops` added; model keys and the agent uid listed.
