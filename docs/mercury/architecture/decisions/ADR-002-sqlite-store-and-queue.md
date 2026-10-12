# ADR-002: SQLite as durable store and job queue

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12.

## Context
- MERCURY must recover every unfinished task after restart, never execute a task twice, and keep a complete audit trail (brief §A, §F, §I; hard constraints).
- Expected load is tiny: ≤ 3 concurrent tasks, a few thousand rows per day, one host.
- Discovery (`02-discovery-platform.md` §5.1): WAL is crash-consistent; `synchronous=FULL` makes commits durable; macOS also needs `fullfsync=ON` for power-loss durability; SQLite allows one writer at a time; `BEGIN IMMEDIATE` avoids lock-upgrade deadlocks.
- The key correctness property is that a state transition and the effects it schedules are committed **atomically**. A separate broker cannot join that transaction.

## Decision
1. One SQLite database file, `~/Library/Application Support/Mercury/mercury.db`, mode `0600`, holds **state, job queue, outbox, artifact metadata and audit log**.
2. Pragmas at open: `journal_mode=WAL`, `synchronous=FULL`, `fullfsync=ON`, `checkpoint_fullfsync=ON`, `foreign_keys=ON`, `busy_timeout=5000`, `trusted_schema=OFF`.
3. **Single writer**: only `mercuryd`'s Store module writes. The CLI opens read-only (`mode=ro`) or sends commands over the control socket.
4. Every write transaction uses `BEGIN IMMEDIATE`. A transition writes `tasks`, `events`, `audit_log`, `jobs` and `outbox` rows together.
5. **Queue semantics** (`jobs` table): `status`, `due_at`, `lease_owner`, `lease_expires_at`, `fence` (monotonic integer incremented on every claim), `attempt`. A job is claimed with one `UPDATE … WHERE status='ready' AND due_at<=now RETURNING`. Effects carry the fence and are rejected if a newer fence exists.
6. **Duplicate prevention in the schema**:
   ```sql
   CREATE UNIQUE INDEX one_active_run_per_task
     ON agent_runs(task_id) WHERE status IN ('starting','running');
   CREATE UNIQUE INDEX one_run_per_attempt
     ON agent_runs(task_id, phase, attempt);
   CREATE UNIQUE INDEX one_effect_per_key ON outbox(dedup_key);
   ```
7. **Immutability by trigger** for `authorizations`, `plan_approvals`, `reviews`, `audit_log`, `artifacts`:
   ```sql
   CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
   BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
   ```
8. Integrity and backup: `PRAGMA quick_check` at startup; `integrity_check` daily and before migrations; online backup daily (keep 14) and before every migration; forward-only migrations keyed by `PRAGMA user_version`.
9. Artifact *contents* live in files (content-addressed), not BLOBs, to keep the DB small; the DB stores hash, size, media type and path.

## Alternatives
- **Redis/BullMQ**: extra service, separate durability tuning, no atomic state + queue commit. Rejected.
- **Temporal**: durable timers and retries, but a heavy second service. Rejected for scale and footprint ([ADR-001](ADR-001-coordinator-runtime-and-language.md)).
- **Files on disk (JSON per task, like today's `.ai/` state and gate files)**: no transactions, race-prone, the current failure mode. Rejected.
- **PostgreSQL locally**: durable and multi-writer, but a server process to run and upgrade on a laptop for no needed capability. Rejected.
- **`synchronous=NORMAL`**: faster, but can lose the last commits on power loss, which could re-run a Codex start. Rejected.

## Consequences
- Positive: one file to back up, inspect and restore; atomic transitions; duplicate prevention enforced by the database, not by code discipline.
- Negative: one host and one writer (accepted); `fullfsync` costs some write latency (ASM-A-03); `node:sqlite` is RC, so a repository interface and fallback to `better-sqlite3` are required.
- Agent C owns the full DDL; Agent D owns backup, restore and integrity procedures.

## Related requirements
Brief §A (duplicate prevention, recovery), §F (DB integrity, durable checkpoints), §I; NFR-REL-01, NFR-REL-03, NFR-REL-04, NFR-REL-05, NFR-AUD-02; AP-4.
