# ADR-007: Outbound polling instead of webhooks

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12.

## Context
- No public inbound access to the Mac (brief).
- GitHub: conditional requests with `ETag`/`If-None-Match` returning `304` are not charged to the primary rate limit; Events and Notifications APIs have 30 s – 6 h latency; self-hosted runners discouraged on public repos (discovery fact 9).
- Linear: webhooks need a public HTTPS URL; polling via `issues(filter: {updatedAt: {gt: cursor}})` works.
- Webhook relays (smee, `gh webhook forward`, cloud relay) add a third party or a hosted component.
- The Mac sleeps; anything event-based would miss deliveries anyway and need reconciliation.

## Decision
1. Poll GitHub REST with ETags and Linear GraphQL with durable `updatedAt` cursors (overlapping window 2 min, dedupe by `(id, updatedAt)`).
2. Adaptive intervals (defaults; Agent B tunes):

   | Watch | Interval |
   |---|---|
   | Linear eligible-issue scan (team) | 60 s |
   | PR with checks pending or coordinator just pushed | 30 s |
   | PR awaiting operator review/merge | 60 s for 1 h, then 5 min |
   | Full reconcile of all non-terminal tasks | 15 min, at startup, and after a wake gap > 60 s |
3. One request at a time per integration; ≥ 1 s between mutations; honour `retry-after` and secondary limits with exponential backoff and jitter.
4. Polling results become typed **facts** applied by the Workflow Engine (level-triggered). A missed poll is harmless.
5. No webhook relay in the MVP. If latency becomes a problem, a relay may be added later **only as a hint to poll immediately**, never as a source of truth.

## Alternatives
- Webhooks via smee / `gh webhook forward`: third-party transit; channel URL is the only secret. Rejected for MVP.
- Operator-owned cloud relay/queue: violates "locally hosted"; rejected unless a later ADR approves.
- GitHub Events/Notifications API: too laggy for control flow.
- GraphQL for GitHub: fewer round trips but no ETag; use only for occasional reconcile if needed.

## Consequences
- Latency bounded by intervals (see NFR-LAT-03/05); API budget within NFR-RES-02/03.
- Works identically after sleep and restart; no inbound attack surface.

## Related requirements
Brief "No public inbound access", §F (retry after connectivity loss); NFR-LAT-03, NFR-LAT-05, NFR-RES-02, NFR-RES-03; AP-5, AP-8.
