# ADR-019: Notification channels, operator response and the human-presence tier

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-12, OD-30, OD-35)** |
| Date | 2026-10-12 |
| Owner | Agent A. Agent C owns `NotificationPolicy`, the control API principals and method classification (`architecture/components.md` §4.15, §5); Agent D owns the ops issue, heartbeat, watchdog and local notifications (`operations/macos-service.md` §11); Agent B owns GitHub and Linear message formats; Agent E owns the presence-tier security requirements |
| Related ADRs | [ADR-008](ADR-008-agent-identities-and-merge-governance.md), [ADR-010](ADR-010-launchd-launchagent.md), [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md), [ADR-015](ADR-015-task-condition-model.md) |

## Context
- The brief requires notifications through the operator's existing GitHub and Linear channels (iPhone and Mac), no new dashboard or app (CON-011), and no duplicate or noisy messages (brief §G).
- Phase 2 had no ADR for channels or for how the operator answers; every escalation resolution required the local CLI (RA-27).
- Any process running as the operator can read the control-socket token or obtain a TTY. That includes the operator's interactive Claude Code session, which reads untrusted PR text. Such a process could `ack-merge`, acknowledge a `MERCURY / policy` escalation (turning a required check green), grant budgets or resume a security block (RA-09, RE-04). The operator's interactive agents also hold human GitHub and Linear credentials (RE-08).
- Comments on the public ops issue can be posted by anyone, so forged "MERCURY" alerts are possible (RE-11).

## Decision
### Channels (RD-19)
| Channel | Used for | Identity |
|---|---|---|
| GitHub review request and @mention on the PR | PR ready for approval; CI or merge intervention needed | `mercury-bot` |
| Linear comment on the issue | Issue-level decisions (`decision_needed`), repeated plan-review failure, completion and merge verification | Linear app (`actor=app`) |
| `mercury-ops` issue in `project-mercury` | Daemon, ops and security halts; heartbeat; watchdog alerts (GitHub Mobile push) | `mercury-ops` |
| Local macOS notification | Credentials, Keychain, disk (conditions only the Mac can show) | Local |

1. No other channel exists. Adding one requires a new ADR. There is no Slack integration ([ADR-012](ADR-012-migration-from-slack-workflow.md)).
2. Deduplication and the per-class matrix belong to `NotificationPolicy` (`components.md` §4.15): one notification per (task, class, subject version), reminders on a fixed schedule, and wake-time coalescing ([ADR-015](ADR-015-task-condition-model.md) item 6).
3. **External liveness:** the daemon posts a heartbeat; an external watchdog (a scheduled GitHub Actions workflow in `project-mercury`, OD-30) alerts through the ops issue if the heartbeat is stale. A signed sleep-notification helper writes a final `mode: sleeping` heartbeat so sleep is not reported as an outage (thresholds in D's parameter table).
4. Ops-issue texts are fixed templates without actionable instructions; the operator is told to trust only the `mercury-ops` author and to act only through the CLI.

### Operator response
5. **Responses are local CLI only in v1** (OD-12). The operator can *see* escalations on the iPhone but must *resolve* them at the Mac. **GitHub and Linear text is never a control input** (FR-203).

### Human-presence tier (RD-12)
6. Control-socket methods are classified:
   - **`operator`** (0600 socket token is enough): status, trace, pause, cancel, request authorization or re-authorization, revoke.
   - **`operator-presence`**: `ack-merge`; security resume and un-halt; `adopt` after a foreign push; budget and revision `grant`; `policy ack`; un-pause after an automatic security pause; the ruleset-emergency runbook step. These require a **local user-presence confirmation** (Touch ID or the login password) through a small signed helper using LocalAuthentication; the daemon verifies the helper's result and records it in the control request audit row.
   A process running as the operator, including the operator's interactive Claude, can therefore **request** but never **clear** an escalation. Stopping work never needs presence; relaxing safety always does.
7. If Phase 0 shows the helper cannot run from the required context, the fallback is a TTY prompt with a typed nonce, recorded as a policy-level (not technical) control.
8. **Policy OD-35:** the operator restricts interactive agents from `gh pr review --approve`, `gh pr merge` and merge API calls, and removes Linear write connectors that act as the human. Approvals happen only in the GitHub UI or app.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Slack or a new chat channel | Recreates the Slack pains; violates CON-011 |
| Web dashboard or mobile app | Violates CON-011 and FR-900 |
| Respond by GitHub or Linear comment (verified author) | Any text channel readable by agents becomes an injection target; the human's account is also used by the operator's interactive agents. Deferred to a later ADR (OD-12) |
| Socket token only for all methods (C Phase 2) | Any same-uid process can clear human escalations (RA-09) |
| Presence tier for every command | Makes stopping work slower; stop commands must stay frictionless |
| Healthchecks-style third-party pinger | An extra third party; GitHub Actions already exists in the operator's setup (OD-30) |

## Consequences
- **Positive:** every human escalation needs a physically present human to clear it; agents can still ask.
- **Positive:** notifications reach the iPhone through apps the operator already uses.
- **Negative:** escalations cannot be resolved away from the Mac (accepted tradeoff, OD-12).
- **Negative:** a small signed helper binary must be built, pinned and verified in Phase 0.

## Related requirements
CON-003, CON-011; FR-203, FR-220, FR-221, FR-222, FR-223, FR-240, FR-241; NFR-007, NFR-043, NFR-063, NFR-073; SEC-106, SEC-601, SEC-902.

## Related findings
RA-09, RA-27, RE-04, RE-08, RE-11, RD-07; F's provisional ADR-P12.

## Operator decisions
- **OD-12** escalation response channel (default: local CLI only).
- **OD-30** external liveness backstop (default: GitHub Actions watchdog).
- **OD-35** policy checklist, including the interactive-agent restrictions.
