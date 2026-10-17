# ADR-026 — PostgreSQL and an S3-compatible object store as devplat state

| | |
|---|---|
| Status | **Proposed** (Architecture Amendment 001; requires operator approval) |
| Date | 2026-10-17 |
| Owner | Lead Architect (development platform) |
| Related ADRs | ADR-021 (extends its decision 2 for the platform; local mode unchanged), ADR-022, ADR-024, ADR-025, ADR-027 (none superseded). Mercury production ADR-001…020 are **not affected** |

## Context

devorch v2 keeps development state in a hash-chained JSONL ledger on branch `devorch/state`, written by one orchestrator session (ADR-021 decision 2). The Kubernetes-native, multi-project platform (ADR-022) changes the requirements:

- two controller replicas with leader failover, plus a separate API;
- concurrent Jobs across projects;
- at-least-once execution with idempotent dispatch;
- relational queries for READY, budgets and fair share;
- authenticated operator facts (R5 N-06);
- evidence objects up to GiB size.

R5 §3.3 also showed that anyone with the ledger writer's uid can forge a consistent v1 ledger.

## Decision

1. **Task state in PostgreSQL 16.** In-cluster, this is a CloudNativePG `Cluster`; in cloud, a managed PostgreSQL. The schema is `platform/db/schema.sql` (`19-…`).
2. **The state machine is a port, not a redesign.** `T_FULL`/`T_SHORT`, `GATE_OF`, `REQUIRED_BEFORE`, `LIMITS`, the subtask binding and the contract-core rule become reference tables plus one `SECURITY DEFINER` function `record_event()`. It is the only way to append to `task_events` or change task state. A test keeps the tables equal to `devorch.py`.
3. **Append-only, hash-chained `task_events`.** Triggers refuse UPDATE, DELETE and TRUNCATE for every role. The chain is verified by `verify_chain()`. Authenticity against a DB superuser comes from **signed checkpoints exported outside the DB** (artifact store with object lock, plus a git branch).
4. **Roles.** `devplat_controller` writes only through functions. `devplat_api` can only record OIDC-authenticated operator facts and read. `devplat_readonly` reads under row-level security per project. Agents have no DB route and no credentials.
5. **Concurrency.** Task leases with fencing tokens in the DB; the controller leader is a Kubernetes Lease. Jobs, events, side effects, artifacts and facts use idempotency or dedup keys. GitHub and Linear writes go through a transactional outbox whose operation list contains no merge, approve or settings operation; Linear writes need DOD-05.
6. **Artifacts in an S3-compatible store**, content-addressed (`sha256/<hex>`), one bucket per project. Agents upload only through per-Job presigned URLs under `runs/<job-uid>/`. The controller verifies and copies evidence into immutable storage, with object lock where the store supports it. **The store product is an operator decision.** The chart targets an external S3-compatible endpoint (cloud S3, GCS interoperability, R2 or a self-hosted store) plus a filesystem/PVC mode for the single workstation. MinIO is only an option, with the caveat in `20-…` §1 (community edition source-only; repository archived 2026-04-25).
7. **v1 stays the local mode.** Migration happens through an import tool that **replays** every v1 record through `record_event()`. v1 facts are not imported as authenticated.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Task CRDs in etcd with an operator | No durable audit history (compaction), object size limits, no relational queries, no atomic state + outbox + budget commit. It would be a second source of truth |
| SQLite per controller | Not safe for multiple pods or the separate API; no network writer |
| Keep the git ledger as platform state | Single writer, push races, no concurrency or queries; forgeable by the writer's uid |
| Event store product (e.g. Kafka) | Extra infrastructure; transactional coupling with state and outbox would need a second store anyway |
| Artifacts in PostgreSQL (bytea / large objects) | GiB-size bundles and logs bloat backups and WAL; no presigned per-Job upload |
| MinIO as the bundled in-cluster default | Community edition no longer maintained as binaries or images (repository archived 2026-04-25); would put an unmaintained component on the critical path |

## Consequences

- **Positive.** Atomic, fenced, idempotent transitions under concurrency; DB-enforced gates and budgets; operator facts bound to an authenticated OIDC subject that the controller cannot forge; per-project read isolation; evidence objects of any size with content addressing.
- **Negative.** PostgreSQL and an object store become critical dependencies with backup, PITR and upgrade duties. The rules exist in two places (Python and SQL) while v1 lives; the equality test mitigates this.
- **Limits.** A DB superuser, or anyone holding data files or backups, can rewrite history consistently. Detection depends on the signed external checkpoints, which are **not implemented yet**. The DB cannot check that a cited artifact's content is a valid result, or that GitHub facts are true. Those remain controller and reconciliation duties. Without object lock, immutability rests on IAM (reduced assurance).

## Verification status

- **Implemented and tested:** `platform/db/test_schema.py` — 21/21 against PostgreSQL 16.15, with mutation checks for the main rules (`19-…` §13). The tests ran on an ephemeral local instance because the shared scratch server had crashed (`19-…` §13).
- **Documented only:** CloudNativePG deployment, backup/PITR, migrations runner, checkpoint signing and export, import tool, object store.
- **Unverified:** object lock and POST-policy support on each candidate store.

## Operator decisions requested

1. Approve PostgreSQL (CloudNativePG in-cluster / managed in cloud) as devplat state.
2. Choose the object store per deployment profile (`20-…` §11).
3. Choose the checkpoint signing method (Sigstore keyless with workload identity, or a KMS key) and the retention period.
