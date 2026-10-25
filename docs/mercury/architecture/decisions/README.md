# MERCURY Architecture Decision Records

Owner: Agent A (Principal AI Systems Architect). Index revised in Phase 4 (2026-10-12) against the binding reconciliation in [`reviews/30-reconciliation.md`](../../reviews/30-reconciliation.md).

ADR numbers `ADR-001` to `ADR-020` are canonical (RD-10). The provisional keys `ADR-P01`…`ADR-P15` used in early planning drafts are retired; the mapping is at the end of this file.

## Status vocabulary

| Status | Meaning |
|---|---|
| Accepted | Binding for implementation |
| Accepted (pending operator decisions: OD-xx) | Binding; the design adopts the listed defaults and must work under every listed option unless the ADR says otherwise. The OD register is in `planning/traceability.md` (TDD §30) |
| Superseded by ADR-nnn | Kept for history; no longer binding |

## Index

| ADR | Title | Status | Supersedes / revises | Related ADRs | Reconciliation decisions |
|---|---|---|---|---|---|
| [ADR-001](ADR-001-coordinator-runtime-and-language.md) | Coordinator runtime and language: Node.js 24 LTS + TypeScript | Accepted | Revised in Phase 4 (dependency set) | 002, 010, 013 | RD-11 |
| [ADR-002](ADR-002-sqlite-store-and-queue.md) | SQLite as the durable store, with a queue derived from task state | Accepted | Revised: `jobs` table withdrawn | 015, 018, 020 | RD-3, RD-11 |
| [ADR-003](ADR-003-coordinator-mediated-agent-communication.md) | Coordinator-mediated agent communication; no direct agent-to-agent channel | Accepted | Revised: no MCP in v1; revision-request rule | 004, 005, 017 | RD-8, RD-15 |
| [ADR-004](ADR-004-claude-invocation-model.md) | Claude invoked by the coordinator as a headless decision service | Accepted (pending OD-17, OD-29, OD-34) | Revised: canonical decision types, agent uid, snapshots | 003, 011, 013, 017, 020 | RD-1, RD-7, RD-18, RD-20 |
| [ADR-005](ADR-005-codex-invocation-model.md) | Codex invoked as a supervised `codex exec` run under the agent uid | Accepted (pending OD-07, OD-09) | Revised: provisional status removed; absorbs ADR-P14 | 006, 013, 016, 020 | RD-1, RD-15, RD-17 |
| [ADR-006](ADR-006-coordinator-owns-git-and-pr.md) | Coordinator owns git commit, push and PR creation | Accepted (pending OD-06) | Revised: `COMMENT` only, hardened git, mirror pushes | 005, 008, 009, 014, 016, 020 | RD-5, RD-9, RD-11, RD-17, RD-18 |
| [ADR-007](ADR-007-polling-over-webhooks.md) | Outbound polling instead of webhooks | Accepted | Revised: values by reference | 009, 015 | RD-16, RD-18 |
| [ADR-008](ADR-008-agent-identities-and-merge-governance.md) | Identity inventory | Accepted (pending OD-02, OD-03, OD-04, OD-05, OD-20) | Revised: governance half superseded by ADR-014; file name kept for link stability | 013, 014, 018, 019 | RD-6 |
| [ADR-009](ADR-009-system-of-record-split.md) | Linear for spec and intent; coordinator for execution and authority; GitHub for code and approval | Accepted (pending OD-06, OD-10, OD-33) | Revised: two Linear status modes, `spec_hash`, hold-based drift | 006, 007, 011, 015 | RD-9, RD-13, RD-14 |
| [ADR-010](ADR-010-launchd-launchagent.md) | Run the coordinator as a per-user launchd LaunchAgent | Accepted (pending OD-14, OD-36) | Revised: coordinator-only scope; values by reference | 013, 016, 020 | RD-1, RD-11 |
| [ADR-011](ADR-011-authorization-records-and-verification.md) | Immutable, hash-bound authorization and approval records, verified at dispatch and at result application | Accepted (pending OD-08) | Revised: reauthorize/amend/revoke contract; integrity moved to ADR-018 | 004, 009, 015, 018, 020 | RD-4, RD-13 |
| [ADR-012](ADR-012-migration-from-slack-workflow.md) | Migration from the Slack and script workflow — partition rules | Accepted (pending OD-10, OD-16) | Revised: criteria moved to the roadmap; stages `MIG-0…4` | 009, 016, 019 | — |
| [ADR-013](ADR-013-agent-process-isolation.md) | Agent process isolation under a dedicated macOS uid | Accepted (pending OD-18, OD-31, OD-36) | New; replaces the "future option" text in ADR-010 and overview §8.6 | 004, 005, 008, 010, 016, 020 | RD-1 |
| [ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md) | Merge-actor enforcement and required MERCURY checks | Accepted (pending OD-01, OD-21, OD-22, OD-28, OD-35) | New; supersedes the governance half of ADR-008 | 006, 008, 015, 019 | RD-5, RD-14 |
| [ADR-015](ADR-015-task-condition-model.md) | Task condition model — states, holds, `BLOCKED` and the derived queue | Accepted (pending OD-27, OD-33) | New | 002, 009, 011, 014, 019 | RD-3, RD-14 |
| [ADR-016](ADR-016-filesystem-layout.md) | Filesystem layout and ownership | Accepted (pending OD-18) | New; replaces overview §5.4 (Phase 2) | 002, 005, 006, 013, 017 | RD-2 |
| [ADR-017](ADR-017-claude-review-snapshot.md) | Claude reads git-object snapshots, never checkouts | Accepted | New | 004, 011, 013, 016 | RD-7 |
| [ADR-018](ADR-018-audit-integrity.md) | Audit integrity — hash chain, off-host anchors, HMAC on authority rows | Accepted (pending OD-15, OD-20, OD-24) | New; takes over the integrity items of ADR-011 | 002, 008, 010, 011, 013 | RD-4 |
| [ADR-019](ADR-019-notifications-and-operator-presence.md) | Notification channels, operator response and the human-presence tier | Accepted (pending OD-12, OD-30, OD-35) | New | 008, 010, 014, 015 | RD-12, RD-19 |
| [ADR-020](ADR-020-detached-runs-and-adoption.md) | Detached agent runs, adoption after restart, and lost runs | Accepted | New | 004, 005, 006, 010, 011, 013 | RD-11 |

No ADR is currently in status "Superseded" as a whole. ADR-008's Phase 2 merge-governance section was superseded by ADR-014 and removed from ADR-008.

## ADR template (Phase 4)

Each ADR contains: header table (Status, Date, Owner, Related ADRs, Supersedes where relevant); Context; Decision; Alternatives considered (with the reason each was rejected); Consequences (positive and negative); Related requirements (IDs from `planning/traceability.md` and `security/threat-model.md`); Related findings (Phase 3 review IDs); Operator decisions (OD-nn). Revised ADRs end with a Revision history.

ADRs reference values and contracts owned elsewhere instead of restating them: operational parameters (`operations/macos-service.md` parameter table), filesystem layout (`operations/macos-service.md` §7.1), DDL (`architecture/components.md` §6), schemas (`protocols/`), retry matrix (`integrations/github.md` Part B), SEC statements (`security/threat-model.md`), requirement IDs (`planning/traceability.md`).

## Retired provisional keys

| Provisional key | Final ADR |
|---|---|
| ADR-P01 runtime | ADR-001 |
| ADR-P02 store/queue | ADR-002 + ADR-015 |
| ADR-P03 polling | ADR-007 |
| ADR-P04 identities | ADR-008 |
| ADR-P05 merge governance | ADR-014 |
| ADR-P06 coordinator owns git | ADR-006 |
| ADR-P07 Claude invocation | ADR-004 |
| ADR-P08 Codex invocation | ADR-005 |
| ADR-P09 LaunchAgent | ADR-010 |
| ADR-P10 Linear status ownership | ADR-009 |
| ADR-P11 authorization records | ADR-011 + ADR-018 |
| ADR-P12 notifications | ADR-019 |
| ADR-P13 communication | ADR-003 |
| ADR-P14 dependency install | ADR-005 (item 7) |
| ADR-P15 filesystem layout | ADR-016 |

Note: `reviews/25-review-F-coverage.md` §6.5 proposed different numbers for the new ADRs (for example ADR-013 for notifications). The numbering above follows the reconciliation assignment (RD-1…RD-19) and is canonical.
