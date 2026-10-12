# ADR-008: Agent identities and merge governance

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12. Requires **operator decision OD-A-01**. Agent E owns the threat analysis; Agent B owns the exact GitHub settings list.

## Context
- Today every agent action uses the operator's identities: GitHub `usjbro` (admin), the Linear user, the Slack user (discovery fact 3). An agent approval cannot be told apart from a human one; and because PR authors cannot approve their own PRs, agent PRs authored as `usjbro` cannot receive the human's required approval.
- Target repos belong to a **personal account** and are public (discovery fact 4): collaborators always have write; "Restrict who can push" and bypass lists are org-only; a GitHub App cannot be a code owner; "Require approval of the most recent reviewable push" makes the last pusher's approval ineffective; `pull_requests:write` cannot be narrowed to "comment only" (`02-discovery-platform.md` §1).
- Hard constraint: no agent identity can satisfy required human approval or merge to a protected branch, enforced by GitHub configuration and token permissions.

## Decision
### Identities
| Actor | GitHub | Linear | Credentials location |
|---|---|---|---|
| `mercuryd` (all coordinator writes, including posting Claude's reviews) | **GitHub App "MERCURY"** installed on `usjbro` for selected repos only. Permissions: `contents:write`, `pull_requests:write`, `issues:write`, `checks:read`, `statuses:read`, `metadata:read`. **Never** `administration`, `workflows:write` (default), `members` | **OAuth app installed with `actor=app`** (non-human app user), team-scoped, scopes `read`, `write` (issues, comments) only | App private key and Linear token in login Keychain (ASM-A-02) |
| Claude | none (reviews are posted by `mercuryd` as the App with a "Claude review" header and `onBehalfOf`-style attribution marker) | none | Anthropic API key only |
| Codex | none | none | OpenAI API key only |
| Operator | `usjbro` — sole code owner and sole merger | own user | Never available to MERCURY |

One App for the MVP. A second App ("MERCURY Reviewer") for clearer author/reviewer attribution is an optional later refinement; it adds no security because neither App's approval can count (below).

### Protection on each target repo's default branch (ruleset or classic protection)
1. Require a pull request; ≥ 1 approval.
2. **Require review from Code Owners**; `CODEOWNERS` = `* @usjbro` (covers `CODEOWNERS` itself).
3. **Require approval of the most recent reviewable push.**
4. **Dismiss stale approvals** when new commits are pushed.
5. Required status checks, strict, pinned to their source App where possible.
6. Block force pushes and deletion; "Do not allow bypassing the above settings" / empty bypass list.
7. Repository setting "Allow GitHub Actions to create and approve pull requests" **off**.
8. Policy (not enforcement): the coordinator posts Claude reviews only as `COMMENT` or `REQUEST_CHANGES`, and its GitHub client has no `APPROVE` or merge method (static test).

### Merge verification (detective, always on)
After every merge of a MERCURY PR: `merged == true`; `merged_by.login == operator`; an `APPROVED` review by the operator with `commit_id == head SHA at merge`; merge commit on the base branch; required checks green. Any failure → security notification within 5 min, task not completed, Linear not moved to Done by MERCURY.

### Personal-account options (operator decision OD-A-01)
| Option | Human approves | Only human merges | Recommendation |
|---|---|---|---|
| G-1 Stay personal + App + protections above | Preventive | **Detective** (App has `contents:write`, could merge an already-approved PR) | **MVP default** |
| G-2 Transfer target repos to a free organization; add "Restrict who can push to matching branches" = operator (merges count) | Preventive | **Preventive** | **Target** before unattended overnight operation |
| G-3 Machine-user collaborator | Preventive only with CODEOWNERS + last-push | Detective | Reject (classic PAT, second account) |
| G-4 Operator's own token | None | None | Reject |

Under G-1 the residual risk is that a compromised coordinator merges a PR **the operator already approved at its current head**: timing, not content.

## Alternatives
Listed in the options table. Also considered: removing `contents:write` from the App and pushing to a fork — requires a second account to own the fork; rejected.

## Consequences
- Operator setup steps (out of MERCURY's scope to perform): create App, install on selected repos, set protections, add `CODEOWNERS`, create Linear OAuth app. Phase 0 must verify ASM-A-09 and ASM-A-11.
- Existing Linear GitHub integration and the `chatgpt-codex-connector` bot are unaffected; bot reviews never count toward required review.
- Linear `actor=app` makes MERCURY's comments distinguishable from the operator's — fixing JAM-160's identity confusion.

## Related requirements
Brief §E (branch protection, rulesets, token privileges, service identities, separation of duties), §H (agent identity, human approval enforcement); hard constraint 4; steps 12–13; NFR-SEC-02, NFR-SEC-03; AP-3.
