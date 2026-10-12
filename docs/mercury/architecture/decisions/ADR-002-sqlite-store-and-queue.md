# ADR-002: SQLite as the durable store, with a queue derived from task state

| | |
|---|---|
| Status | **Accepted** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent C owns the DDL (`architecture/components.md` §6) and the claim protocol (§7). Agent D owns backup, restore, integrity and migration procedures (`operations/macos-service.md` §13–§14, `operations/recovery.md`) |
| Related ADRs | [ADR-015](ADR-015-task-condition-model.md) (holds, `BLOCKED`, derived queue), [ADR-018](ADR-018-audit-integrity.md) (audit chain), [ADR-020](ADR-020-detached-runs-and-adoption.md) (durability ordering with git) |

## Context
- MERCURY must recover every unfinished task after a restart, never execute a step twice, and keep a complete audit trail (brief §A, §F, §I).
- Load is tiny: a few concurrent tasks, a few thousand rows per day, one host.
- Discovery (`02-discovery-platform.md` §5.1): WAL is crash-consistent; `synchronous=FULL` makes commits durable; macOS also needs `fullfsync=ON` for power-loss durability; SQLite has one writer at a time; `BEGIN IMMEDIATE` avoids lock-upgrade deadlocks.
- The key correctness property is that a state transition and the effects it schedules commit **atomically**. A separate broker cannot join that transaction.
- Phase 3 found two queue designs: a `jobs` table (this ADR's Phase 2 text) and a queue derived from `tasks.state` (C). A second record of "what should happen next" can diverge from the task state (RA-15).

## Decision
1. **One SQLite database** in `MERCURY_HOME` ([ADR-016](ADR-016-filesystem-layout.md); path in `operations/macos-service.md` §7.1) holds task state, runs, holds, the outbox, artifact metadata and the audit log. Artifact *contents* are content-addressed files, not BLOBs.
2. **Pragmas:** `journal_mode=WAL`, `synchronous=FULL`, `fullfsync=ON`, `checkpoint_fullfsync=ON`, `foreign_keys=ON`, `trusted_schema=OFF`, with a busy timeout. The startup self-check refuses to run with other values (NFR-050).
3. **Single writer.** Only `mercuryd`'s `Store` writes. The CLI talks to the daemon over the control socket, or opens the file read-only for offline status. Agents run under a separate uid ([ADR-013](ADR-013-agent-process-isolation.md)) and cannot open `MERCURY_HOME` at all.
4. **Atomic transitions.** Every write transaction uses `BEGIN IMMEDIATE`. A transition writes the task row, the transition event, the audit entry and any outbox rows in one transaction (AP-4).
5. **The queue is derived, not stored.** There is no `jobs` table. The next action for a task is computed from `tasks.state`, active holds, run leases and `next_action_at` (`components.md` §7.1, [ADR-015](ADR-015-task-condition-model.md)). Each claim creates a `runs` row with a lease and a fencing token in the same transaction. Polling and housekeeping are timers, not queue entries.
6. **Duplicate prevention lives in the schema**, as unique partial indexes and triggers defined only in `components.md` §6.3–§6.4. The rules they enforce are:
   - at most one active **mutating** run per task;
   - at most one active run per (task, run kind), so read-only Claude code and security reviews may run in parallel;
   - one outbox row per idempotency key.
   The invariant IDs (INV-nn) are C's, in `state-machine.md` §4.
7. **Immutability by trigger** for authority tables, the audit log and artifact metadata (`components.md` §6.4).
8. **Backup, integrity checks, retention and migrations** follow D's procedures (`macos-service.md` §13–§14). Their values (backup cadence, retention counts) are in D's parameter table, not here. Migrations follow D's expand/contract model.
9. Git objects are not in SQLite. The ordering between a git commit, its fsync and the DB transaction that records the SHA is fixed by [ADR-020](ADR-020-detached-runs-and-adoption.md).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Explicit `jobs` table with leases (Phase 2 text) | Duplicates the information in `tasks.state` and `runs`. Two records of "what is next" can diverge after a partial failure. The derived queue keeps the atomic property with one fewer table |
| Redis/BullMQ | An extra service with separate durability tuning, and no atomic state-plus-queue commit |
| Temporal | Durable timers and retries, but a heavy second service ([ADR-001](ADR-001-coordinator-runtime-and-language.md)) |
| JSON files on disk (like today's `.ai/` state and gate files) | No transactions; race-prone; the current failure mode |
| Local PostgreSQL | A server to run and upgrade on a laptop, for no needed capability |
| `synchronous=NORMAL` | Can lose the last commits on power loss, which could re-run a Codex start |

## Consequences
- **Positive:** one file to back up, inspect and restore. Atomic transitions. Duplicate prevention is enforced by the database, not by code discipline.
- **Positive:** the derived queue removes a class of "job exists but task moved on" bugs, and recovery reasons only about tasks, runs and holds.
- **Negative:** one host and one writer (accepted, FR-903). `fullfsync` costs write latency (ASM-A-03). `node:sqlite` is RC, so the `Store` port and the fallback driver are required.
- **Negative:** the dispatcher must evaluate a query over tasks and holds every tick instead of popping a queue. At MERCURY's scale this is negligible (NFR-080).

## Related requirements
FR-040, FR-041, FR-043, FR-063, FR-064; NFR-001, NFR-020, NFR-023, NFR-050, NFR-052, NFR-091 (IDs per `planning/traceability.md`).

## Related findings
RA-15 (`jobs` vs derived queue), RA-16 (active-run rule), RA-32 (table names), RA-33 (backup and migration policy), RC-18 (active-run property).

## Operator decisions
None.

## Revision history
- Phase 4: `jobs` table removed in favour of C's derived queue; SQL removed (DDL lives only in `components.md`); one-active-*mutating*-run rule; backups and migrations delegated to D; table names follow C.
