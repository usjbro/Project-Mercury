# ADR-018: Audit integrity — hash chain, off-host anchors, HMAC on authority rows

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-15, OD-20, OD-24)** |
| Date | 2026-10-12 |
| Owner | Agent A. Agent C owns the `audit_log`, `anchors` and `audit_epochs` tables and the outbox effect (`architecture/components.md` §4.16, §6); Agent D owns startup verification, restore and new-Mac flows (`operations/recovery.md`); Agent E owns SEC-601…606 |
| Related ADRs | [ADR-002](ADR-002-sqlite-store-and-queue.md), [ADR-008](ADR-008-agent-identities-and-merge-governance.md), [ADR-010](ADR-010-launchd-launchagent.md), [ADR-011](ADR-011-authorization-records-and-verification.md), [ADR-013](ADR-013-agent-process-isolation.md) |

## Context
- The brief requires a complete audit trail that answers ten questions (§I), including which authorization permitted a run and what Claude reviewed.
- Phase 2 positions differed: A and C made HMAC optional, E required it; nobody specified off-host anchoring storage, credential or failure semantics; chain verification was absent from startup recovery (known disagreement 3; RA-19, RA-20, RE-09, RF-10).
- A restored or rolled-back DB has a chain tip behind the last anchor, so every legitimate restore would look like tampering (RC-15).
- Under [ADR-013](ADR-013-agent-process-isolation.md) agents cannot write the DB at all. The remaining tamper sources are processes running as the operator and tampered or restored backups.

## Decision
1. **Hash-chained `audit_log` — MUST.** Every transition, decision, run, external effect and operator command appends an entry whose hash covers the previous entry's hash. Append-only by trigger (`components.md` §6.4).
2. **Off-host anchoring of the chain head — MUST before unattended operation (milestone M7).** The head `(seq, hash)` is carried in App-posted artifacts that already exist:
   - the `MERCURY / claude-review` check-run output summary — **private repositories only**, never on public repositories (Addendum B, OD-24);
   - the Linear completion comment per task;
   - a daily anchor commit in a **private anchor repository**, written by `mercury-ops` ([ADR-008](ADR-008-agent-identities-and-merge-governance.md)).
   Anchors are outbox effects with natural-key reconciliation and are recorded in the `anchors` table. Embedding the head in public PR comments beyond the check summary is OD-24.
3. **HMAC `record_mac` on authority rows — SHOULD.** Authorizations, plan approvals and review verdicts carry an HMAC over canonical JSON with a Keychain-held key. With agents unable to reach the DB, it defends only against restored or tampered backups; the column may be null when HMAC is disabled.
4. **Startup verifies the chain** since the last anchor ([ADR-010](ADR-010-launchd-launchagent.md) startup order). Failure → **safe mode** (no dispatch) plus one SECURITY notification. An anchoring outage (anchors overdue) raises an ops alert but does not stop work.
5. **Restore and new-Mac flows** record an operator-initiated `audit.restore_epoch` event in a new `audit_epochs` row. Verification accepts divergence from the last anchor only at a recorded epoch boundary and reports it. Authority that cannot be verified after a restore maps to `BLOCKED(reauthorization_required)`, never to `guard_integrity_failure` ([ADR-011](ADR-011-authorization-records-and-verification.md)).
6. **Retention** of audit entries, artifacts and transcripts follows OD-15 (values in `traceability.md` NFR-061 and D's parameter table). Deletion beyond retention is itself audited.
7. **Honest limit:** a process running as the operator can rewrite the local DB. The anchored chain makes such rewriting **detectable**, not impossible. The GitHub controls ([ADR-014](ADR-014-merge-actor-enforcement-and-required-checks.md)) remain the preventive backstop.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Chain only, no anchor | A same-uid attacker can rewrite the whole chain consistently |
| HMAC as MUST (E Phase 2) | Little value once agents cannot open the DB; the key is readable by the same uid that could tamper |
| No HMAC at all | Cheap protection for backups is lost; kept as SHOULD |
| Anchor via a machine-user PAT (E Phase 2) | Machine users are rejected ([ADR-008](ADR-008-agent-identities-and-merge-governance.md)); CON-008 forbids human credentials |
| Anchor in a public gist or issue | Leaks activity cadence; spoofable comments on public issues |
| Halt on overdue anchors | An anchor outage would stop all work; detection, not availability, is the goal |
| Treat any divergence after restore as tampering | Every legitimate restore would trigger a security halt (RC-15) |

## Consequences
- **Positive:** history tampering after the last anchor is detected at the next start; restores are explicit, audited events.
- **Negative:** `mercury-ops` and a private anchor repository must exist before M7.
- **Negative:** chain verification adds startup time, bounded by the anchor interval.

## Related requirements
FR-260, FR-261; NFR-060, NFR-061; SEC-601, SEC-602, SEC-603, SEC-604, SEC-605, SEC-606.

## Related findings
RA-19, RA-20, RD-06, RE-09, RF-10, RC-15; known disagreement 3; F's provisional ADR-P11 (integrity half).

## Operator decisions
- **OD-15** retention.
- **OD-20** `mercury-ops` App and anchor repository; HMAC as SHOULD.
- **OD-24** public chain-head embedding (default: no, beyond the check summary).
