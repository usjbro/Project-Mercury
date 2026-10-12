# ADR-012: Migration from the Slack and script workflow — partition rules

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-10, OD-16)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent F owns stage sequencing and exit criteria (`planning/roadmap.md`, milestones M9a–M9c) |
| Related ADRs | [ADR-009](ADR-009-system-of-record-split.md), [ADR-016](ADR-016-filesystem-layout.md), [ADR-019](ADR-019-notifications-and-operator-presence.md) |

## Context
- The workflow MERCURY replaces runs on `usjbro/network_monitor` with `coordination/scripts/*.sh`, gate files, task contracts, `.ai/` state, `.worktrees/<slug>` and Slack `#network-monitor` (discovery fact 2).
- Agents currently take "the next Todo" as their queue (JAM-161), which conflicts with MERCURY's authorization rule (CON-004).
- The Slack bot token has leaked before (JAM-160).
- Two coordinators on the same issue would cause duplicate work and conflicting branches.
- Phase 3 found that this ADR's stage criteria disagreed with F's roadmap and that its stage names M1–M4 collided with F's milestone names (RA-25, RF-18).

## Decision
1. **Stage names** are `MIG-0` (inventory) to `MIG-4` (decommission), mapped to F's milestones:

   | Stage | Milestone | MERCURY | Slack and scripts |
   |---|---|---|---|
   | MIG-0 Inventory | Phase 0 | Read-only inventory of scripts, gate and contract formats, `.ai/` files, instruction files; list of conventions to keep | Unchanged |
   | MIG-1 Shadow | M9a | Polls and runs `triage` and `authorization` in dry-run; no Codex runs, no external writes | Authoritative |
   | MIG-2 Supervised pilot | M9b | Full lifecycle only for MERCURY-eligible issues | Must not touch MERCURY-eligible issues |
   | MIG-3 Cutover | M9c | All eligible issues | Slack coordination off; bot token revoked and rotated; scripts manual-only |
   | MIG-4 Decommission | after M9c | — | Scripts removed by PR; channel archived |

   **Entry and exit criteria, durations and the shadow agreement metric are defined only in `planning/roadmap.md`** (OD-16). The agreement metric is defined after MIG-0 has inventoried the legacy gate format.
2. **Partition by issue.** An issue is managed by exactly one system. MERCURY eligibility requires the operator-added label (OD-10).
3. **Legacy-claim refusal.** An issue with a legacy claim is **not eligible**: an existing `.worktrees/<slug>` for the issue in the operator's clone (read-only check), an open PR for the issue on a non-MERCURY branch, or a legacy gate marker identified in MIG-0. This is an eligibility exclusion at issue level (FR-002), so no task is created; one notification tells the operator why.
4. **No disk collision.** MERCURY's mirrors and worktrees live in `WORK_ROOT` ([ADR-016](ADR-016-filesystem-layout.md)), never in a repository's `.worktrees/`.
5. **No Slack integration** in MERCURY, not even a mirror. Notifications use the channels in [ADR-019](ADR-019-notifications-and-operator-presence.md).
6. **Shadow mode** is a Workflow-level dry-run switch: no Codex dispatch and no outbox drain. It is also used in tests.
7. **Rollback** at any stage: `mercury pause` (global) stops new dispatch; in-flight tasks finish or hold; the Slack workflow resumes on non-MERCURY issues.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Big-bang cutover | No comparison data; risk of duplicate execution on in-flight issues |
| MERCURY posts to Slack during transition | Keeps the old channel and the leaked-before token in use |
| Wrap the existing scripts inside MERCURY | Inherits gate files and Slack coupling; reuse conventions, not scripts |
| Stage criteria in this ADR (Phase 2 text) | Two sources of truth for the same criteria (RA-25) |
| `BLOCKED(legacy_claim)` task state (Phase 2 text) | Creates authority-less task rows for issues MERCURY must not manage; an eligibility exclusion is simpler |

## Consequences
- **Positive:** the two systems can never manage the same issue; rollback is a single command.
- **Negative:** the operator must stop using the legacy scripts for MERCURY-eligible issues, which is outside MERCURY's control.

## Related requirements
FR-002, FR-300, FR-301; OPS-008, OPS-009; CON-011.

## Related findings
RA-25, RF-18.

## Operator decisions
- **OD-10** eligibility signal.
- **OD-16** pilot scope, durations and Slack shutdown timing.

## Revision history
- Phase 4: criteria moved to the roadmap; stages renamed `MIG-n` and mapped to M9a–M9c; legacy claim became an eligibility exclusion.
