# ADR-014: Merge-actor enforcement and required MERCURY checks

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-01, OD-21, OD-22, OD-28, OD-35)** |
| Date | 2026-10-12 |
| Owner | Agent A. Agent B owns the ruleset contents, check-run posting and merge verification recipe (`integrations/github.md` §6, §8, §9); Agent C owns the transitions and guards (`architecture/state-machine.md` T22–T26, T34–T35, §8.5); Agent E owns the policy list for `MERCURY / policy` and the proof (`security/threat-model.md` SEC-100…110, SEC-309/310, §5.2) |
| Supersedes | The merge-governance half of [ADR-008](ADR-008-agent-identities-and-merge-governance.md) (Phase 2 options G-1 to G-4) |
| Related ADRs | [ADR-006](ADR-006-coordinator-owns-git-and-pr.md), [ADR-008](ADR-008-agent-identities-and-merge-governance.md), [ADR-015](ADR-015-task-condition-model.md), [ADR-019](ADR-019-notifications-and-operator-presence.md) |

## Context
- Target repositories belong to the personal account `usjbro` (discovery fact 4). On personal repositories collaborators always have write; "Restrict who can push" and bypass lists are organization-only; a GitHub App cannot be a code owner; "Require approval of the most recent reviewable push" makes the last pusher's approval ineffective.
- `mercury-bot` needs `contents:write` to push task branches. On a personal repository it could therefore merge a PR the operator already approved at its current head. The merge actor is then only detectively controlled.
- Phase 3 found:
  - three names for the same governance options (A's G-1/G-2, E's G-ORG/G-SPLIT/G-DETECT, B's detect-after) (known disagreement 6);
  - bot `REQUEST_CHANGES` reviews create a blocking state MERCURY cannot clear (RA-04, RB-03, RC-01, RE-15);
  - no transition created or concluded the required `MERCURY / claude-review` check, so with B's ruleset no MERCURY PR could ever merge (RC-02);
  - E's `mercury/policy` escalation had no posting design and nothing that physically blocked the merge (RE-05, RF-07);
  - two gate mechanisms (check runs vs commit statuses) and inconsistent permissions (RA-06).

## Decision
1. **Governance modes** (E's names):
   - **G-ORG:** target repositories live in an organization; a ruleset restricts updates of `main` to the operator; merges count as pushes. Merge actor **preventive**.
   - **G-SPLIT:** no MERCURY credential has merge capability (pushes by deploy key, PR operations by an App without `contents:write`). Allowed only if Phase 0 verifies ASM-E-01, ASM-E-02, ASM-E-07 and B's two pinning tests (RB-06).
   - **G-DETECT:** personal repository; merge actor verified after the fact.
2. **Mode by stage (OD-01):** G-DETECT is acceptable for the sandbox and the supervised pilot **with written operator risk acceptance**. **G-ORG is required before unattended or overnight operation** on target repositories.
3. **Ruleset in all modes** (rulesets, not classic protection, so drift is readable by `mercury-ops`): PR required; 1 approval; Code Owner review with `CODEOWNERS` naming only the operator; approval of the most recent reviewable push; dismiss stale approvals; no bypass; block force-push and deletion; `allow_auto_merge=false`; review-thread resolution per OD-22; and the two required checks below. The exact ruleset JSON is in `github.md` §9.
4. **Two required check runs**, created by `mercury-bot` and **pinned to its integration id**:
   - **`MERCURY / claude-review`**: `success` only when both the Claude code review and the Claude security review pass for the exact head SHA. Any new push resets it.
   - **`MERCURY / policy`**: deterministic pre-checks only (protected paths, dependency and lockfile changes, build scripts, instruction files; list in `threat-model.md` SEC-310). It stays `neutral` or `failure` until the operator acknowledges the change through `mercury policy ack`, a **human-presence** command ([ADR-019](ADR-019-notifications-and-operator-presence.md)). Until acknowledged, the task is `BLOCKED(policy_ack_required)` and no `deps_install` uses a changed lockfile.
   `mercury-bot` therefore needs `checks:write`. Phase 0 verifies whether pinning additionally needs `statuses:write` and grants it only if so (RB-05).
5. **Check runs are written by outbox effects** attached to transitions **and holds** ([ADR-015](ADR-015-task-condition-model.md)): `in_progress` when reviews are claimed, `success`/`failure` at review conclusion, `failure` with an action-required summary while a `spec_changed` hold is active at PR stage.
6. **Claude reviews are posted as `COMMENT` only.** MERCURY never submits `APPROVE` or `REQUEST_CHANGES`, never dismisses reviews, and never calls merge, `update-branch` or auto-merge endpoints. The GitHub adapter enforces an endpoint allowlist (SEC-102). The gate is the check run, not the review.
7. **Waiting for CI (T22) considers only non-MERCURY required checks**, derived from `GET /rules/branches/{base}` at each evaluation, so MERCURY never waits on its own checks.
8. **Security findings on public PRs:** details for medium and below; critical, high and pre-existing findings withheld behind a generic line and a local report ID (OD-21).
9. **Merge verification** after every merge uses one recipe (B's M1–M7 merged with C's checks, in `state-machine.md` §8.5). Failure → `BLOCKED(merge_verification_failed)`, scoped by the failed check:
   - wrong merge actor, or merge commit not on the base branch → **global `security_halt`**;
   - approval, content or review-ordering mismatch → repo-scoped `integrity_alert` hold plus `BLOCKED`;
   - the operator merged before Claude's review finished (`merged_unreviewed_head`) → a policy notice, not a security incident.
   Exit is `ack-merge` (presence tier) or a successful re-verify.
10. **MERCURY down:** MERCURY PRs cannot merge without the MERCURY checks. Default is to wait. An emergency merge requires an audited ruleset edit through the runbook in `operations/recovery.md`, itself a presence-tier action.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Commit statuses `mercury/policy` and `mercury/claude-review` (E's Phase 2 text) | Any token with `statuses:write` can set a status; a check run can only be created by an App and can be pinned to the integration id, which is a stronger source binding |
| Bot `REQUEST_CHANGES` as the gate | Leaves a blocking review MERCURY cannot dismiss; the PR stays un-mergeable (RA-04) |
| Bot `APPROVE` plus human approval | An App approval never counts toward Code Owner review; adds a misleading signal |
| Detect-only governance without required checks (B's Phase 2 fallback) | "The human merges only Claude-reviewed SHAs" would be advisory. Required checks make it preventive in every mode |
| G-ORG mandatory from the start | Delays the sandbox and pilot for a repository transfer; the risk in G-DETECT is timing, not content, and is acceptable with written acceptance while supervised |
| Machine-user collaborator (Phase 2 G-3) or the operator's token (G-4) | See [ADR-008](ADR-008-agent-identities-and-merge-governance.md) |
| Auto-merge after Claude passes | Removes the human merge decision (CON-007, FR-902) |

## Consequences
- **Positive:** in every mode, the operator can only merge a head SHA that Claude reviewed and whose policy escalations a human acknowledged. In G-ORG, even a fully compromised coordinator cannot merge.
- **Positive:** a single, preventive gate replaces the review-state trap.
- **Negative:** when MERCURY is down, MERCURY PRs wait (accepted tradeoff).
- **Negative:** G-DETECT leaves a residual risk of a coordinator-initiated merge of an already-approved head; detected within the NFR bound and halts dispatch globally.
- **Negative:** target repositories must run CI on draft PRs (onboarding requirement in `github.md`).

## Related requirements
CON-007, CON-014; FR-161, FR-162, FR-164, FR-165, FR-180, FR-181, FR-182, FR-902; NFR-044; OPS-003; SEC-100, SEC-102, SEC-108, SEC-109, SEC-309, SEC-310, SEC-904, SEC-905. (FR-162's "COMMENT or REQUEST_CHANGES" wording is corrected to `COMMENT` by F.)

## Related findings
RA-04, RA-06, RA-17, RA-18, RB-03, RB-04, RB-05, RB-06, RC-01, RC-02, RC-17, RE-05, RE-15, RE-16, RF-07, RF-27; E's A-SEC-1.

## Operator decisions
- **OD-01** governance mode (default: G-DETECT with written acceptance for sandbox and pilot; G-ORG before unattended operation).
- **OD-21** security findings on public PRs.
- **OD-22** require review-thread resolution (default on).
- **OD-28** operator merges before the Claude review (default: verification policy notice and `ack-merge`).
- **OD-35** policy checklist (ruleset, Actions settings, interactive-agent restrictions).
