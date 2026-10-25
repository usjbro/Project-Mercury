# ADR-009: Linear for spec and intent; coordinator for execution state and authority; GitHub for code and human approval

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-06, OD-10, OD-33)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent B owns the Linear mapping, `spec_hash` and status modes (`integrations/linear.md` §5–§8); Agent C owns states and holds (`architecture/state-machine.md`) |
| Related ADRs | [ADR-006](ADR-006-coordinator-owns-git-and-pr.md), [ADR-007](ADR-007-polling-over-webhooks.md), [ADR-011](ADR-011-authorization-records-and-verification.md), [ADR-015](ADR-015-task-condition-model.md) |

## Context
- Linear has 7 workflow states; MERCURY has 17 task states plus an issue-level `discovered` status. Specs live in Linear issue descriptions with acceptance-criteria checkboxes; relations are used heavily.
- Linear's GitHub integration moves issues to In Review and Done on PR events. **A branch name that contains the issue identifier is a closing link**, whatever the PR text says, so "the coordinator closes the issue" is incompatible with identifier-bearing branch names (RA-10, ASM-A-07 withdrawn).
- Linear coding sessions can start agents on delegated issues: a second, unauthorized start path.
- Phase 3 found three designs for spec drift (block, hold, interrupt-and-move-back) and three different hashes (RA-01, RC-04, RF-16).

## Decision
1. **System of record** (table in `architecture/overview.md` §9.1):
   - **Linear:** issue content, spec, acceptance criteria, labels, relations, and the operator's **eligibility** signal (OD-10).
   - **Coordinator:** authorizations, task state, runs, holds, plans, approvals, reviews, audit, and the projection of coarse status to Linear.
   - **GitHub:** code, branches, PRs, checks, the operator's approval and the merge.
2. **Direction rules.** Inbound observations may **stop, pause or invalidate** work; they may never **start or approve** it (CON-004, FR-203). Outbound writes are idempotent projections with deterministic IDs and markers.
3. **Linear status ownership has two modes, configured per team** (RD-9, OD-06):
   - `integration_owns_done` (**pilot default**): branches keep the issue identifier; Linear's integration moves In Review and Done; MERCURY writes `In Progress` and comments only, and posts a verification comment after merge verification.
   - `mercury_owns_all`: branch names without the identifier and non-closing PR phrasing; MERCURY sets `Done` only after merge verification.
   - **In both modes Linear `Done` is never proof of merge.** The dependency guard requires a MERCURY `COMPLETED` for MERCURY-managed blockers.
4. **Spec binding (RD-13).** An authorization binds `spec_hash`, defined once in `linear.md` §5 (normalized title, description, acceptance criteria and eligibility-relevant labels). A change after authorization sets the task's `spec_changed` **hold** ([ADR-015](ADR-015-task-condition-model.md)); there is no backward transition. Results of runs that finish after the change are **not acted upon** until Claude re-authorizes against the new hash: the authorization guard checks `spec_hash` at result-application time, not only at dispatch. PR-stage tasks keep the PR open and need re-authorization before further Codex work. Re-authorization is a new authorization version and also invalidates the plan approval binding ([ADR-011](ADR-011-authorization-records-and-verification.md)). Checkbox ticks do not change `spec_hash`.
5. **`DISCOVERED` is issue-level** (`linear_issues.mercury_status`), not a task state (RD-14). A task row exists only once triage shortlists an issue or the operator requests an authorization.
6. **Conflict handling** follows `overview.md` §9.3, using C's holds and block reason codes, including refusal to dispatch while a non-MERCURY Linear agent is delegated on the issue.
7. **Back-references** (trailers, PR body, Linear comments) let an observer reconstruct history. They never restore authority after DB loss.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Linear as the full state store | No transactions or leases; fields writable by humans and integrations; forgeable authority |
| Coordinator forces an exact mirror in Linear | Fights the operator and the integration (flapping) |
| Coordinator closes issues with `Part of JAM-n` while branches keep the identifier (Phase 2 text) | The branch name already closes the issue (RA-10) |
| Disable Linear's GitHub PR automations | Changes the operator's workflow for non-MERCURY issues; available to the operator but not required |
| Spec drift → `BLOCKED(spec_changed)` (Phase 2 text) | `BLOCKED` means a human must act; a spec change is resolved by Claude. Produces non-actionable notifications |
| Spec drift → interrupt runs and return to `AWAITING_AUTHORIZATION` | A backward transition outside the table; loses in-flight work that Claude may confirm as still valid |
| Hash of description only | Misses title and acceptance-criteria label changes; a separate hash per document caused RA-01 |

## Consequences
- **Positive:** the operator keeps writing specs and choosing eligibility in Linear; MERCURY never edits issue descriptions.
- **Positive:** spec drift cannot produce merged stale-spec work: the hold blocks result application, and the PR-stage check keeps the PR unmergeable until re-authorized ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)).
- **Negative:** in the default mode Linear may show `Done` before MERCURY has verified the merge; MERCURY's verification comment and its own `COMPLETED` are authoritative.
- **Negative:** every spec edit costs a Claude re-authorization run (OD-33).

## Related requirements
CON-004, CON-011; FR-002, FR-004, FR-005, FR-024, FR-183, FR-200, FR-201, FR-202, FR-203; NFR-005; SEC-307.

## Related findings
RA-01, RA-10, RA-21, RA-28, RC-04, RC-11, RC-23, RF-08, RF-16, RB-14, RE-14.

## Operator decisions
- **OD-06** Linear `Done` owner (default `integration_owns_done` in the pilot).
- **OD-10** eligibility signal (default: operator-added `mercury` label).
- **OD-33** re-authorize on every spec edit (default: yes).

## Revision history
- Phase 4: two status modes (RD-9); `spec_hash` and hold-based drift (RD-13); `DISCOVERED` at issue level (RD-14); `Part of` premise withdrawn.
