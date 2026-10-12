# ADR-012: Migration from the Slack and script workflow

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12. Agent F sequences this in the roadmap.

## Context
- The workflow MERCURY replaces runs on `usjbro/network_monitor` with `coordination/scripts/*.sh`, gate files, task contracts, `.ai/` state, `.worktrees/<slug>` and Slack `#network-monitor` (discovery fact 2). Its scripts were not readable in Phase 1.
- Agents currently take "the next Todo" as their queue (JAM-161), which conflicts with MERCURY's authorization rule.
- The Slack bot token has leaked before (JAM-160 incident).
- Running two coordinators on the same issue would cause duplicate work and conflicting branches.

## Decision
Staged migration with a strict **partition by issue**:

| Stage | MERCURY | Slack/scripts | Exit criteria | Rollback |
|---|---|---|---|---|
| **M0 Inventory** (Phase 0) | — | unchanged | Read-only inventory of scripts, gate/contract formats, `.ai/` files, `AGENTS.md`, `CLAUDE.md`, `.codex/hooks.json`; list conventions to keep (`docs/superpowers/plans/`, AC format, `[P1]–[P3]`, `Not Speced`, `Security` checklist) | n/a |
| **M1 Shadow** | Polls Linear/GitHub; runs `TRIAGE`/`AUTHORIZE` in dry-run (records `would_authorize`); **no Codex, no external writes** | authoritative | ≥ 2 weeks; ≥ 90 % agreement with actual gate decisions; 0 coordinator crashes unrecovered | stop `mercuryd` |
| **M2 Pilot** | Full lifecycle **only for issues labelled `mercury`** in one repo | must not touch `mercury` issues | 10 tasks merged; 0 duplicate executions; 0 unauthorized runs; notification volume accepted | `mercury pause --all`; remove labels |
| **M3 Cutover** | All eligible issues (label applied by default by the operator) | Slack posting disabled; Slack bot token revoked/rotated; scripts manual-only | 30 days stable | re-enable scripts on unlabelled issues |
| **M4 Decommission** | — | scripts removed via a PR in `network_monitor`; channel archived | — | — |

Safeguards during coexistence:
1. MERCURY refuses an issue (task → `BLOCKED(legacy_claim)`) if a legacy claim exists: an existing `.worktrees/<slug>` for the issue in the operator's clone (read-only check), an open PR for the issue not on a `mercury/*` branch, or a legacy gate marker found in M0.
2. MERCURY's worktrees and clones live in `~/MercuryWork`, never in the repo's `.worktrees/`, so the two never collide on disk.
3. No Slack integration in MERCURY (not even a mirror): notifications go through GitHub and Linear (brief).

## Alternatives
- **Big-bang cutover**: fastest, but no comparison data and risk of duplicate execution on in-flight issues. Rejected.
- **MERCURY posts to Slack during transition**: keeps the old channel alive and the token in use. Rejected.
- **Wrap the existing scripts** inside MERCURY: inherits gate files and Slack coupling. Rejected; reuse conventions, not scripts.

## Consequences
- Requires the operator to change the legacy scripts (or simply stop using them for `mercury` issues) — outside MERCURY's scope.
- Shadow mode needs a dry-run switch in the Workflow Engine (no Codex dispatch, no outbox drain), which is also useful for testing.

## Related requirements
Brief mission ("replaces Slack"), §G (avoid duplicate notifications); discovery facts 2, 5, 12; NFR-REL-03.
