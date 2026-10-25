# ADR-007: Outbound polling instead of webhooks

| | |
|---|---|
| Status | **Accepted** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent B owns intervals, cursors and the retry matrix (`integrations/github.md`, `integrations/linear.md`) |
| Related ADRs | [ADR-009](ADR-009-system-of-record-split.md), [ADR-015](ADR-015-task-condition-model.md) |

## Context
- There is no public inbound access to the Mac (CON-002).
- GitHub conditional requests (`If-None-Match`) returning `304` do not count against the primary rate limit. The Events and Notifications APIs have 30 s to 6 h latency (discovery fact 9).
- Linear webhooks need a public HTTPS URL; polling with an `updatedAt` cursor works.
- Webhook relays (smee, `gh webhook forward`, a cloud relay) add a third party or a hosted component.
- The Mac sleeps, so anything event-based would miss deliveries and need reconciliation anyway.
- Phase 3 found that this ADR's interval values differed from B's (RA-35).

## Decision
1. **Poll** GitHub REST with ETags and Linear GraphQL with durable `updatedAt` cursors and an overlap window. Intervals, overlap and reconcile cadence are defined only in `linear.md` §3 and `github.md`; they are not restated here.
2. **Polling is level-triggered.** Pollers produce typed observations that the `InboxProcessor` applies through the `TransitionEngine`. A missed poll is harmless because the next one observes the current level. Deduplication keys follow B's catalogue (`github.md` §13), including an observation sequence so that A→B→A transitions are not lost.
3. **Full reconcile** runs at startup, after wake, and on a fixed cadence; values in D's parameter table and B's documents.
4. **Rate limits and errors** follow the single retry matrix in `github.md` Part B. Network-class failures do not consume run or outbox attempts while `network_down` is held (RD-18).
5. **Connectivity probe** is an authenticated, ETag-conditional request, never an unauthenticated GitHub call (RD-18).
6. **No webhook relay in v1.** A relay may be added later by a new ADR **only as a hint to poll immediately**, never as a source of truth (FR-901).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Webhooks through smee or `gh webhook forward` | Third-party transit; the channel URL is the only secret |
| Operator-owned cloud relay or queue | Violates "locally hosted" |
| GitHub Events or Notifications API | Too laggy for control flow |
| GitHub GraphQL for polling | Fewer round trips but no ETag; acceptable only for occasional reconcile |

## Consequences
- **Positive:** works identically after sleep and restart; no inbound attack surface.
- **Negative:** latency is bounded by poll intervals; the targets are NFR-040 and NFR-041 and are measured from the first awake-and-online instant after the event (RD-16).
- **Negative:** API budget is consumed continuously; bounded by NFR-081.

## Related requirements
CON-002; FR-001, FR-283, FR-901; NFR-005, NFR-040, NFR-041, NFR-081.

## Related findings
RA-35 (parameter drift), RB-10, RB-11 (dedup keys), RB-12 (probe), RD-09, RD-22.

## Operator decisions
None.

## Revision history
- Phase 4: all numeric values removed and referenced; dedup catalogue, retry matrix and probe rules referenced from B.
