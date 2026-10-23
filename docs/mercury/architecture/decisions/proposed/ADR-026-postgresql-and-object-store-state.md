# ADR-026 — PostgreSQL and an S3-compatible object store as devplat state

| | |
|---|---|
| Status | **Proposed** (Architecture Amendment 001; R6 fix round applied; requires operator approval) |
| Date | 2026-10-17, revised 2026-10-22 (R6 D1–D11, D17, D18, D22, D24) |
| Owner | Lead Architect (development platform) |
| Related ADRs | ADR-021 (extends its decision 2 for the platform; local mode unchanged), ADR-022, ADR-024, ADR-025, ADR-027 (none superseded). Mercury production ADR-001…020 are **not affected** |

## Context

devorch v2 keeps development state in a hash-chained JSONL ledger written by one orchestrator session (ADR-021 decision 2). The Kubernetes-native, multi-project platform (ADR-022) needs:

- two controller replicas with leader failover, a separate API and two gateways;
- concurrent Jobs across projects;
- at-least-once execution with idempotent dispatch;
- relational queries for READY, admission, budgets and fair share;
- authenticated operator facts (R5 N-06);
- evidence objects up to hundreds of MiB.

R5 §3.3 showed that the ledger writer's uid can forge a consistent v1 ledger. R6 found that the first DB port had lost devorch rules, was not project-agnostic, and gave the controller owner rights.

## Decision

1. **Task state in PostgreSQL 16**: CloudNativePG `Cluster` in-cluster, managed PostgreSQL in cloud. Schema: `platform/db/roles.sql` + `platform/db/schema.sql` (`19-…`).
2. **A port, not a redesign.** devorch `T_FULL`/`T_SHORT`, `GATE_OF`, `REQUIRED_BEFORE`, `LIMITS`, `check_transition`/`apply`, `verify_subtask`, `contract_errors`, `result_errors` and `contract_dep_blockers` become reference tables and `SECURITY DEFINER` functions. `record_event()` is the only way to append to `task_events` or change task state. A vendored copy of the rules (`platform/db/devorch_v2_rules.json`) keeps the SQL tables equal to the Python tables.
3. **Project-agnostic core** (R6 D1, D6). No project, role or v1 fact literal is in the schema:
   - roles come from the platform role catalogue (`platform/agents/execution-profiles.yaml`, loaded at deploy time);
   - enabled roles, hard preconditions (default `[DOD-02, DOD-13]` in the config schema) and the Linear write fact come from each project's configuration;
   - preconditions are satisfied only by **project-scoped** facts.
4. **Identity** `(project_id, task_id)` everywhere. Project status is `draft | onboarding | active | paused | archived`, and it gates task creation, dispatch and pushes (R6 D3, D4).
5. **Append-only, hash-chained `task_events`** carrying `config_version` and `assurance_mode`. Triggers refuse UPDATE, DELETE and TRUNCATE for every role. Authenticity against a DB superuser comes from **signed checkpoints exported outside the DB**.
6. **Roles** (R6 D9):
   - `devplat_owner` is NOLOGIN and owns everything.
   - `devplat_migrator` is the only login that migrates: a Helm pre-install/pre-upgrade Job with a pinned Secret, acting as CNPG `initdb.owner`.
   - `devplat_controller` writes only through functions, and never migrates.
   - `devplat_api` records facts only for allow-listed OIDC subjects (R6 D2).
   - `devplat_model_gateway` gets budget functions only; `devplat_artifact_gateway` gets upload-authorisation functions only.
   - `devplat_readonly` reads under per-project row-level security.
7. **Concurrency and money** (R6 D8, D17, D22):
   - task leases with fencing tokens, and fence transfer on leader election;
   - recorded admission decisions, each consumed by exactly one Job;
   - idempotency keys on events, Jobs, reservations, uploads, side effects and facts;
   - verifier `test_runs` required for G2;
   - atomic per-project-day and per-task cost reservations, with environmental retries charged to the same budget;
   - environmental classification only from platform signals.
8. **Operator control of contracts** (R6 D18). Planner-originated contracts and every revision need an operator approval fact before READY. A task gets at most 3 revisions until an operator reset.
9. **Artifacts in an S3-compatible store** (R6 D10, D11).
   - Layout (owned by `20-…`): bucket `devplat-<project>`; `runs/<job-uid>/{result.json, result.bundle, agent.stream.jsonl, runner.json, fetch.log}` with caps; immutable `sha256/<hex>`; `src/<project>/<sha>.bundle`; `manifests/<task>/<attempt>/<role>-d<dispatch>.json`.
   - **Pods never reach the store.** They upload only to `devplat-artifact-gateway`, with a per-Job one-time token that PostgreSQL authorises. The gateway writes with its own credential.
   - The store product is an operator decision: an external S3-compatible endpoint, or a filesystem/PVC on the workstation. MinIO is an option only, with the caveat in `20-…` §1.
10. **v1 stays the local mode.** Migration happens through an import tool that replays every v1 record through `record_event()`. v1 facts are not imported as authenticated.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Task CRDs in etcd with an operator | No durable audit history; object size limits; no relational queries; no atomic state + outbox + budget commit; a second source of truth |
| SQLite per controller | Not safe for multiple pods, the API and the gateways |
| Keep the git ledger as platform state | Single writer, push races, no concurrency or queries; forgeable by the writer's uid |
| Presigned upload URLs handed to pods (first draft) | Pods would need egress to the shared store endpoint, so a pod could PUT to any URL it is given (R6 S-2) |
| Seeded `mdev-*` roles and DOD keys in the schema (first draft) | Couples the platform core to Mercury and v1 (R6 A-04) |
| Controller as schema owner / startup migrations | The controller could rewrite the event log and disable triggers (R6 A-14, S-9) |
| Artifacts in PostgreSQL | Large bundles and logs bloat WAL and backups |
| MinIO as the bundled default | Community edition no longer maintained as binaries or images |

## Consequences

**Positive**
- Atomic, fenced, idempotent transitions under concurrency, with devorch's G1, result and contract rules enforced in the DB.
- Facts are bound to allow-listed human subjects and scoped per project.
- Per-project isolation of identity, rows, buckets and budgets.
- No pod path to the object store.

**Negative**
- PostgreSQL, the object store and two gateways become critical dependencies.
- The rules exist in Python (v1) and SQL until v1 retires; the vendored-rules test mitigates the drift.

**Limits**
- A DB superuser, or anyone with data files or backups, can rewrite history consistently. Detection rests on signed external checkpoints, which are **Designed, unverified**.
- The DB cannot check artifact content or GitHub facts; those remain controller, gitbroker and reconciliation duties.
- A compromised controller can still record forged gate references (`18-…` K-10).
- Without object lock, evidence immutability rests on credentials (reduced assurance).

## Verification status

- **Implemented and tested:** `platform/db/test_schema.py` runs 47 tests against PostgreSQL 16.15, with the schema applied by the migrator login. The tests ran on an ephemeral local instance because the shared scratch server was unreachable. Results are in the R6 hand-off and `19-…` §13.
- **Designed, unverified:** controller, api, gateways, migration Job, CNPG, backups and PITR, checkpoint signing and export, import tool, object store.
- **Unverified:** object lock per candidate store.

## Operator decisions requested

1. Approve PostgreSQL (CNPG in-cluster / managed in cloud) as devplat state.
2. Choose the object store per deployment profile (`20-…` §11).
3. Choose the checkpoint signing method and the evidence retention period.
4. Provide the operator allowlist (`allowedSubjects`, at least one entry).
