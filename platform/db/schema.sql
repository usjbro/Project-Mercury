-- devplat PostgreSQL 16 schema — task state, append-only hash-chained events, Job runs, leases,
-- artifacts, authenticated operator facts, side-effect outbox, reconciliation runs.
--
-- Status: Proposed (Architecture Amendment 001). Design: docs/mercury/development-orchestration/19-postgresql-state.md.
-- Development platform only; NOT a Mercury production schema (separation rule S1).
--
-- The task state machine is a PORT of tools/devorch/devorch.py (T_FULL, T_SHORT, GATE_OF, REQUIRED_BEFORE,
-- LIMITS, check_transition/apply, verify_subtask). platform/db/test_schema.py checks that the `transitions`,
-- `gate_prerequisites` and `loop_counters` rows equal the Python tables.
--
-- Apply with psql (needs a role that may CREATE ROLE and owns the database, e.g. the CNPG superuser or a migration
-- role).  Role names can be overridden for isolated test runs:
--   psql -v role_owner=... -v role_controller=... -v role_api=... -v role_readonly=... -f schema.sql
-- The four roles are NOLOGIN group roles; login users (CNPG managed roles / cloud IAM users) are made members.
--
-- Writers:  devplat_controller — EXECUTE on the controller functions only; no INSERT/UPDATE/DELETE on any table.
--           devplat_api        — EXECUTE record_operator_fact() only; SELECT under row-level security.
--           devplat_readonly   — SELECT under row-level security (per-project grant roles, table project_grants).
-- Every write function is SECURITY DEFINER, owned by the NOLOGIN owner role, with a fixed search_path.

\set ON_ERROR_STOP on
\if :{?role_owner}
\else
\set role_owner devplat_owner
\endif
\if :{?role_controller}
\else
\set role_controller devplat_controller
\endif
\if :{?role_api}
\else
\set role_api devplat_api
\endif
\if :{?role_readonly}
\else
\set role_readonly devplat_readonly
\endif

SELECT format('CREATE ROLE %I NOLOGIN', r)
  FROM unnest(ARRAY[:'role_owner', :'role_controller', :'role_api', :'role_readonly']) AS r
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) \gexec
SELECT format('GRANT CREATE ON DATABASE %I TO %I', current_database(), :'role_owner') \gexec

SET ROLE :"role_owner";
BEGIN;
CREATE SCHEMA devplat;
SET LOCAL search_path = devplat, pg_catalog;
ALTER DEFAULT PRIVILEGES IN SCHEMA devplat REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- =====================================================================================================
-- 1. Reference tables (the ported rules). Read-only after migration.
-- =====================================================================================================
CREATE TABLE lifecycles (lifecycle text PRIMARY KEY CHECK (lifecycle IN ('FULL', 'SHORT')));
INSERT INTO lifecycles VALUES ('FULL'), ('SHORT');

CREATE TABLE states (state text PRIMARY KEY);
INSERT INTO states VALUES ('NEW'), ('BLOCKED'), ('READY'), ('RUNNING'), ('AWAITING_REVIEW'),
  ('AWAITING_INTEGRATION'), ('AWAITING_HUMAN'), ('COMPLETED'), ('FAILED'), ('CANCELLED');

-- devorch FULL_KINDS / SHORT_KINDS / READ_ONLY_KINDS / REVIEW_GATE; subtask id suffixes (check-contract rule).
CREATE TABLE task_kinds (
  kind              text PRIMARY KEY,
  lifecycle         text NOT NULL REFERENCES lifecycles,
  read_only         boolean NOT NULL,
  needs_g4          boolean NOT NULL,          -- devorch needs_g4(): every FULL kind (TDD DoD D6)
  is_review         boolean NOT NULL,
  operator_evidence boolean NOT NULL,          -- completion needs an authenticated operator fact
  subtask_suffix    text CHECK (subtask_suffix IN ('r', 's', 'i'))
);
INSERT INTO task_kinds VALUES
  ('implementation',     'FULL',  false, true,  false, false, NULL),
  ('test',               'FULL',  false, true,  false, false, NULL),
  ('reliability',        'FULL',  false, true,  false, false, NULL),
  ('design',             'FULL',  false, true,  false, false, NULL),
  ('release',            'FULL',  false, true,  false, false, NULL),
  ('code_review',        'SHORT', true,  false, true,  false, 'r'),
  ('design_review',      'SHORT', true,  false, true,  false, 'r'),
  ('reliability_review', 'SHORT', true,  false, true,  false, 'r'),
  ('security_review',    'SHORT', true,  false, true,  false, 's'),
  ('integration',        'SHORT', false, false, false, false, 'i'),
  ('planning',           'SHORT', true,  false, false, false, NULL),
  ('mac_validation',     'SHORT', true,  false, false, true,  NULL),
  ('operator_action',    'SHORT', true,  false, false, true,  NULL);

-- (lifecycle, from_state, event) -> to_state, gate.  Generated from devorch T_FULL / T_SHORT / GATE_OF
-- (gate only on FULL, or on 'unblocked' in both lifecycles).  86 rows.  Review-gate targets
-- (code_review_passed / security_review_passed) are resolved in record_event() exactly as in devorch.
CREATE TABLE transitions (
  lifecycle  text NOT NULL REFERENCES lifecycles,
  from_state text NOT NULL REFERENCES states,
  event      text NOT NULL,
  to_state   text NOT NULL REFERENCES states,
  gate       text CHECK (gate ~ '^G[1-7]$'),
  PRIMARY KEY (lifecycle, from_state, event)
);
INSERT INTO transitions (lifecycle, from_state, event, to_state, gate) VALUES
  ('FULL', 'AWAITING_HUMAN', 'cancelled', 'CANCELLED', NULL),
  ('FULL', 'AWAITING_HUMAN', 'contract_revised', 'BLOCKED', NULL),
  ('FULL', 'AWAITING_HUMAN', 'escalated', 'BLOCKED', NULL),
  ('FULL', 'AWAITING_HUMAN', 'human_changes_requested', 'RUNNING', NULL),
  ('FULL', 'AWAITING_HUMAN', 'human_merged', 'COMPLETED', 'G7'),
  ('FULL', 'AWAITING_HUMAN', 'interface_frozen', 'AWAITING_HUMAN', NULL),
  ('FULL', 'AWAITING_INTEGRATION', 'cancelled', 'CANCELLED', NULL),
  ('FULL', 'AWAITING_INTEGRATION', 'contract_revised', 'BLOCKED', NULL),
  ('FULL', 'AWAITING_INTEGRATION', 'escalated', 'BLOCKED', NULL),
  ('FULL', 'AWAITING_INTEGRATION', 'failed', 'FAILED', NULL),
  ('FULL', 'AWAITING_INTEGRATION', 'integration_failed', 'RUNNING', NULL),
  ('FULL', 'AWAITING_INTEGRATION', 'integration_verified', 'AWAITING_INTEGRATION', 'G5'),
  ('FULL', 'AWAITING_INTEGRATION', 'pr_prepared', 'AWAITING_HUMAN', 'G6'),
  ('FULL', 'AWAITING_INTEGRATION', 'stale_detected', 'AWAITING_INTEGRATION', NULL),
  ('FULL', 'AWAITING_REVIEW', 'cancelled', 'CANCELLED', NULL),
  ('FULL', 'AWAITING_REVIEW', 'code_review_changes_required', 'RUNNING', NULL),
  ('FULL', 'AWAITING_REVIEW', 'code_review_passed', 'AWAITING_REVIEW', 'G3'),
  ('FULL', 'AWAITING_REVIEW', 'contract_revised', 'BLOCKED', NULL),
  ('FULL', 'AWAITING_REVIEW', 'escalated', 'BLOCKED', NULL),
  ('FULL', 'AWAITING_REVIEW', 'failed', 'FAILED', NULL),
  ('FULL', 'AWAITING_REVIEW', 'security_review_blocked', 'RUNNING', NULL),
  ('FULL', 'AWAITING_REVIEW', 'security_review_passed', 'AWAITING_REVIEW', 'G4'),
  ('FULL', 'AWAITING_REVIEW', 'stale_detected', 'AWAITING_REVIEW', NULL),
  ('FULL', 'BLOCKED', 'cancelled', 'CANCELLED', NULL),
  ('FULL', 'BLOCKED', 'contract_revised', 'BLOCKED', NULL),
  ('FULL', 'BLOCKED', 'escalated', 'BLOCKED', NULL),
  ('FULL', 'BLOCKED', 'resumed', 'READY', NULL),
  ('FULL', 'BLOCKED', 'unblocked', 'READY', 'G1'),
  ('FULL', 'COMPLETED', 'closed', 'COMPLETED', NULL),
  ('FULL', 'COMPLETED', 'interface_frozen', 'COMPLETED', NULL),
  ('FULL', 'FAILED', 'cancelled', 'CANCELLED', NULL),
  ('FULL', 'FAILED', 'contract_revised', 'BLOCKED', NULL),
  ('FULL', 'NEW', 'created', 'BLOCKED', NULL),
  ('FULL', 'READY', 'assigned', 'RUNNING', NULL),
  ('FULL', 'READY', 'cancelled', 'CANCELLED', NULL),
  ('FULL', 'READY', 'contract_revised', 'BLOCKED', NULL),
  ('FULL', 'READY', 'escalated', 'BLOCKED', NULL),
  ('FULL', 'RUNNING', 'attempt_failed', 'RUNNING', NULL),
  ('FULL', 'RUNNING', 'cancelled', 'CANCELLED', NULL),
  ('FULL', 'RUNNING', 'contract_revised', 'BLOCKED', NULL),
  ('FULL', 'RUNNING', 'dispatched', 'RUNNING', NULL),
  ('FULL', 'RUNNING', 'env_retry', 'RUNNING', NULL),
  ('FULL', 'RUNNING', 'escalated', 'BLOCKED', NULL),
  ('FULL', 'RUNNING', 'failed', 'FAILED', NULL),
  ('FULL', 'RUNNING', 'implementation_completed', 'RUNNING', NULL),
  ('FULL', 'RUNNING', 'reclaimed', 'READY', NULL),
  ('FULL', 'RUNNING', 'stale_detected', 'RUNNING', NULL),
  ('FULL', 'RUNNING', 'started', 'RUNNING', NULL),
  ('FULL', 'RUNNING', 'tests_failed', 'RUNNING', NULL),
  ('FULL', 'RUNNING', 'tests_passed', 'AWAITING_REVIEW', 'G2'),
  ('SHORT', 'AWAITING_HUMAN', 'cancelled', 'CANCELLED', NULL),
  ('SHORT', 'AWAITING_HUMAN', 'contract_revised', 'BLOCKED', NULL),
  ('SHORT', 'AWAITING_HUMAN', 'escalated', 'BLOCKED', NULL),
  ('SHORT', 'AWAITING_INTEGRATION', 'cancelled', 'CANCELLED', NULL),
  ('SHORT', 'AWAITING_INTEGRATION', 'contract_revised', 'BLOCKED', NULL),
  ('SHORT', 'AWAITING_INTEGRATION', 'escalated', 'BLOCKED', NULL),
  ('SHORT', 'AWAITING_INTEGRATION', 'failed', 'FAILED', NULL),
  ('SHORT', 'AWAITING_INTEGRATION', 'stale_detected', 'AWAITING_INTEGRATION', NULL),
  ('SHORT', 'AWAITING_REVIEW', 'cancelled', 'CANCELLED', NULL),
  ('SHORT', 'AWAITING_REVIEW', 'contract_revised', 'BLOCKED', NULL),
  ('SHORT', 'AWAITING_REVIEW', 'escalated', 'BLOCKED', NULL),
  ('SHORT', 'AWAITING_REVIEW', 'failed', 'FAILED', NULL),
  ('SHORT', 'AWAITING_REVIEW', 'stale_detected', 'AWAITING_REVIEW', NULL),
  ('SHORT', 'BLOCKED', 'cancelled', 'CANCELLED', NULL),
  ('SHORT', 'BLOCKED', 'contract_revised', 'BLOCKED', NULL),
  ('SHORT', 'BLOCKED', 'escalated', 'BLOCKED', NULL),
  ('SHORT', 'BLOCKED', 'resumed', 'READY', NULL),
  ('SHORT', 'BLOCKED', 'unblocked', 'READY', 'G1'),
  ('SHORT', 'COMPLETED', 'closed', 'COMPLETED', NULL),
  ('SHORT', 'FAILED', 'cancelled', 'CANCELLED', NULL),
  ('SHORT', 'FAILED', 'contract_revised', 'BLOCKED', NULL),
  ('SHORT', 'NEW', 'created', 'BLOCKED', NULL),
  ('SHORT', 'READY', 'assigned', 'RUNNING', NULL),
  ('SHORT', 'READY', 'cancelled', 'CANCELLED', NULL),
  ('SHORT', 'READY', 'contract_revised', 'BLOCKED', NULL),
  ('SHORT', 'READY', 'escalated', 'BLOCKED', NULL),
  ('SHORT', 'RUNNING', 'attempt_failed', 'RUNNING', NULL),
  ('SHORT', 'RUNNING', 'cancelled', 'CANCELLED', NULL),
  ('SHORT', 'RUNNING', 'contract_revised', 'BLOCKED', NULL),
  ('SHORT', 'RUNNING', 'dispatched', 'RUNNING', NULL),
  ('SHORT', 'RUNNING', 'env_retry', 'RUNNING', NULL),
  ('SHORT', 'RUNNING', 'escalated', 'BLOCKED', NULL),
  ('SHORT', 'RUNNING', 'failed', 'FAILED', NULL),
  ('SHORT', 'RUNNING', 'reclaimed', 'READY', NULL),
  ('SHORT', 'RUNNING', 'result_accepted', 'COMPLETED', NULL),
  ('SHORT', 'RUNNING', 'stale_detected', 'RUNNING', NULL);

-- devorch REQUIRED_BEFORE (applies to the FULL lifecycle on a state change).
CREATE TABLE gate_prerequisites (
  to_state text NOT NULL REFERENCES states,
  gate     text NOT NULL CHECK (gate ~ '^G[1-7]$'),
  PRIMARY KEY (to_state, gate)
);
INSERT INTO gate_prerequisites VALUES
  ('RUNNING', 'G1'),
  ('AWAITING_INTEGRATION', 'G1'), ('AWAITING_INTEGRATION', 'G2'), ('AWAITING_INTEGRATION', 'G3'), ('AWAITING_INTEGRATION', 'G4'),
  ('AWAITING_HUMAN', 'G1'), ('AWAITING_HUMAN', 'G2'), ('AWAITING_HUMAN', 'G3'), ('AWAITING_HUMAN', 'G4'), ('AWAITING_HUMAN', 'G5'), ('AWAITING_HUMAN', 'G6'),
  ('COMPLETED', 'G1'), ('COMPLETED', 'G2'), ('COMPLETED', 'G3'), ('COMPLETED', 'G4'), ('COMPLETED', 'G5'), ('COMPLETED', 'G6'), ('COMPLETED', 'G7');

-- devorch LIMITS; 'attempt' is bounded by the contract's max_attempts instead (NULL here).
CREATE TABLE loop_counters (counter text PRIMARY KEY, max_count int CHECK (max_count > 0));
INSERT INTO loop_counters VALUES ('attempt', NULL), ('review', 3), ('security', 2), ('integration', 2), ('env', 5);
CREATE TABLE event_counters (event text PRIMARY KEY, counter text NOT NULL REFERENCES loop_counters);
INSERT INTO event_counters VALUES ('attempt_failed', 'attempt'), ('tests_failed', 'attempt'),
  ('code_review_changes_required', 'review'), ('security_review_blocked', 'security'),
  ('integration_failed', 'integration'), ('env_retry', 'env');

-- verify_subtask(): which subtask kinds may provide which gate event.
CREATE TABLE gate_providers (event text NOT NULL, kind text NOT NULL REFERENCES task_kinds, PRIMARY KEY (event, kind));
INSERT INTO gate_providers VALUES ('code_review_passed', 'code_review'), ('code_review_passed', 'design_review'),
  ('code_review_passed', 'reliability_review'), ('security_review_passed', 'security_review'),
  ('integration_verified', 'integration');

-- devorch REVIEWER_KIND (contract required_reviewers -> subtask kind needed for G3).
CREATE TABLE reviewer_kinds (reviewer text PRIMARY KEY, kind text NOT NULL REFERENCES task_kinds);
INSERT INTO reviewer_kinds VALUES ('mdev-code-reviewer', 'code_review'), ('mdev-lead-architect', 'design_review'),
  ('mdev-reliability-engineer', 'reliability_review'), ('mdev-security-engineer', 'security_review');

-- Evidence kinds of handoff-record.schema.json plus 'operator_fact' (an authenticated operator_facts row).
-- is_file: the item must carry sha256 of an artifact registered for the task's project (port of verify_file_evidence).
CREATE TABLE evidence_kinds (kind text PRIMARY KEY, is_file boolean NOT NULL);
INSERT INTO evidence_kinds VALUES ('ci_run', true), ('commit', false), ('design_ref', false), ('github_merge', false),
  ('ledger', false), ('log', true), ('operator_statement', true), ('pr', false), ('result_file', true),
  ('review_file', true), ('subtask', false), ('test_run', true), ('operator_fact', false), ('job', false);

-- Operator facts that G1 of a lifecycle requires (devorch HARD_PRECONDITIONS).
CREATE TABLE hard_preconditions (fact_key text NOT NULL, lifecycle text NOT NULL REFERENCES lifecycles, PRIMARY KEY (fact_key, lifecycle));
INSERT INTO hard_preconditions VALUES ('DOD-02', 'FULL'), ('DOD-03', 'FULL');

-- Kubernetes Job phases as the controller records them.
CREATE TABLE job_phase_transitions (from_phase text NOT NULL, to_phase text NOT NULL, PRIMARY KEY (from_phase, to_phase));
INSERT INTO job_phase_transitions VALUES
  ('planned', 'created'), ('planned', 'failed'), ('planned', 'cancelled'),
  ('created', 'running'), ('created', 'succeeded'), ('created', 'failed'), ('created', 'lost'), ('created', 'cancelled'),
  ('running', 'succeeded'), ('running', 'failed'), ('running', 'lost'), ('running', 'cancelled'),
  ('lost', 'running'), ('lost', 'succeeded'), ('lost', 'failed'), ('lost', 'cancelled');

-- Side effects the platform may ever request. There is deliberately no merge / approve / ruleset operation.
CREATE TABLE outbox_operations (target text NOT NULL, operation text NOT NULL, PRIMARY KEY (target, operation));
INSERT INTO outbox_operations VALUES
  ('github', 'push_dev_branch'), ('github', 'open_draft_pr'), ('github', 'update_draft_pr_body'), ('github', 'comment_pr'),
  ('linear', 'comment_issue'), ('linear', 'update_issue_state');

-- Artifact kinds: size limit and default retention (20-artifact-storage.md §7).
CREATE TABLE artifact_kinds (
  kind                   text PRIMARY KEY,
  max_bytes              bigint NOT NULL CHECK (max_bytes > 0),
  default_retention_days int NOT NULL CHECK (default_retention_days > 0)
);
INSERT INTO artifact_kinds VALUES
  ('result', 1048576, 3650), ('review', 1048576, 3650), ('test_log', 268435456, 365), ('log', 268435456, 90),
  ('git_bundle', 2147483648, 365), ('sbom', 67108864, 3650), ('scan_report', 67108864, 3650),
  ('evidence_bundle', 2147483648, 3650), ('checkpoint', 16777216, 3650), ('operator_upload', 268435456, 3650),
  ('other', 67108864, 30);

-- =====================================================================================================
-- 2. Projects, execution targets, visibility
-- =====================================================================================================
CREATE TABLE projects (
  project_id      text PRIMARY KEY CHECK (project_id ~ '^[a-z][a-z0-9-]{1,30}$'),
  display_name    text NOT NULL,
  github_repo     text CHECK (github_repo ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
  linear_team     text,
  registry_ref    text NOT NULL,                -- <path in project registry>@<commit> of the project config
  artifact_bucket text NOT NULL CHECK (artifact_bucket ~ '^[a-z0-9][a-z0-9.-]{2,62}$'),
  limits          jsonb NOT NULL DEFAULT '{}',  -- e.g. heartbeat_timeout_seconds, max_concurrent_jobs
  status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'archived')),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Execution target = {cluster_ref, namespace_prefix}: moving a project to its own cluster (Option C) is a row change.
CREATE TABLE execution_targets (
  target_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id       text NOT NULL REFERENCES projects,
  name             text NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{0,30}$'),
  cluster_ref      text NOT NULL,
  namespace_prefix text NOT NULL CHECK (namespace_prefix ~ '^proj-[a-z0-9-]{1,40}$'),
  runtime_class    text NOT NULL DEFAULT 'gvisor',
  network_class    text NOT NULL DEFAULT 'none' CHECK (network_class IN ('none', 'deps', 'integration')),
  assurance        text NOT NULL DEFAULT 'standard' CHECK (assurance IN ('standard', 'reduced')),
  enabled          boolean NOT NULL DEFAULT true,
  UNIQUE (project_id, name)
);

-- Row visibility: a role sees a project's rows if it is a member of a role granted that project ('*' = all).
CREATE TABLE project_grants (
  project_id text NOT NULL,                     -- a project_id or '*'
  role_oid   regrole NOT NULL,
  PRIMARY KEY (project_id, role_oid)
);

CREATE FUNCTION can_see(p_project_id text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM devplat.project_grants g
                  WHERE g.project_id IN (p_project_id, '*') AND pg_has_role(g.role_oid::oid, 'MEMBER') IS TRUE)
$$;

-- =====================================================================================================
-- 3. Tasks, contracts, dependencies, events
-- =====================================================================================================
CREATE TABLE tasks (
  task_id          text PRIMARY KEY CHECK (task_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$'),
  project_id       text NOT NULL REFERENCES projects,
  kind             text NOT NULL REFERENCES task_kinds,
  lifecycle        text NOT NULL REFERENCES lifecycles,
  parent_task_id   text REFERENCES tasks,
  covers_tasks     text[] NOT NULL DEFAULT '{}',
  external_ref     text,                        -- e.g. MERC-101 or a Linear issue id (traceability only)
  state            text NOT NULL DEFAULT 'NEW' REFERENCES states,
  contract_version int,
  core_sha256      text,
  attempt          int,
  gates            text[] NOT NULL DEFAULT '{}',  -- gates since the last return to RUNNING (G1 survives)
  counts           jsonb NOT NULL DEFAULT '{"attempt":0,"review":0,"security":0,"integration":0,"env":0}',
  head_commit      text,                        -- tested head (G2)
  impl_head        text,                        -- head of the last checked implementation_completed
  pr_head          text,                        -- G6 head
  frozen_files     jsonb NOT NULL DEFAULT '{}',
  need_bump        boolean NOT NULL DEFAULT false,
  last_seq         int NOT NULL DEFAULT 0,
  last_hash        text NOT NULL DEFAULT 'GENESIS',
  lease_holder     text,
  lease_token      bigint NOT NULL DEFAULT 0,   -- fencing token, strictly increasing per task
  lease_expires_at timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, task_id)
);
CREATE INDEX tasks_project_state ON tasks (project_id, state);

CREATE TABLE task_contracts (
  task_id          text NOT NULL REFERENCES tasks,
  project_id       text NOT NULL REFERENCES projects,
  contract_version int NOT NULL CHECK (contract_version >= 1),
  core_sha256      text NOT NULL CHECK (core_sha256 ~ '^[0-9a-f]{64}$'),  -- devorch contract_core_sha
  body             jsonb NOT NULL,              -- the full devorch.task_contract.v1-style contract (validated by the controller)
  max_attempts     int NOT NULL CHECK (max_attempts BETWEEN 1 AND 5),
  registered_at    timestamptz NOT NULL DEFAULT now(),
  registered_by    text NOT NULL,
  PRIMARY KEY (task_id, contract_version),
  UNIQUE (task_id, core_sha256)                -- a new version must change the core
);

CREATE TABLE task_dependencies (
  task_id     text NOT NULL REFERENCES tasks,
  depends_on  text NOT NULL REFERENCES tasks,
  project_id  text NOT NULL REFERENCES projects,
  requirement text NOT NULL DEFAULT 'completed' CHECK (requirement IN ('completed', 'interface_frozen')),
  PRIMARY KEY (task_id, depends_on),
  CHECK (task_id <> depends_on)
);

-- Append-only, hash-chained per task.  hash = sha256(event_canonical(row)), prev_hash = previous row's hash
-- ('GENESIS' for seq 1).  Written ONLY by record_event().
CREATE TABLE task_events (
  event_id             bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
  project_id           text NOT NULL,
  task_id              text NOT NULL,
  seq                  int NOT NULL CHECK (seq >= 1),
  at                   timestamptz NOT NULL,
  event                text NOT NULL,
  from_state           text NOT NULL REFERENCES states,
  to_state             text NOT NULL REFERENCES states,
  gate                 text,
  actor                text NOT NULL,           -- always 'devplat-controller'
  controller_id        text NOT NULL,           -- lease holder (controller pod identity)
  on_behalf_of         text,                    -- '<issuer>#<subject>' when an operator_fact is cited
  contract_version     int NOT NULL,
  contract_core_sha256 text NOT NULL,
  attempt              int NOT NULL,
  head_commit          text,
  evidence             jsonb NOT NULL,
  payload              jsonb NOT NULL DEFAULT '{}',
  idempotency_key      text,
  lease_token          bigint NOT NULL,
  prev_hash            text NOT NULL,
  hash                 text NOT NULL CHECK (hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (task_id, seq),
  UNIQUE (task_id, idempotency_key),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks (project_id, task_id)
);
CREATE INDEX task_events_project_at ON task_events (project_id, at);
CREATE INDEX task_events_evidence ON task_events USING gin (evidence jsonb_path_ops);

-- Canonical form for hashing: jsonb text of a fixed object (jsonb orders keys deterministically).
-- This is NOT devorch's Python canonical JSON and not RFC 8785; v1 hashes are kept in payload.v1_hash on import.
CREATE FUNCTION event_canonical(e task_events) RETURNS text
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT jsonb_build_object(
    'schema', 'devplat.task_event.v1', 'project_id', e.project_id, 'task_id', e.task_id, 'seq', e.seq,
    'at', to_char(e.at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'event', e.event, 'from_state', e.from_state, 'to_state', e.to_state, 'gate', e.gate,
    'actor', e.actor, 'controller_id', e.controller_id, 'on_behalf_of', e.on_behalf_of,
    'contract_version', e.contract_version, 'contract_core_sha256', e.contract_core_sha256,
    'attempt', e.attempt, 'head_commit', e.head_commit, 'evidence', e.evidence, 'payload', e.payload,
    'idempotency_key', e.idempotency_key, 'lease_token', e.lease_token, 'prev_hash', e.prev_hash)::text
$$;
CREATE FUNCTION event_hash(e task_events) RETURNS text
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT encode(sha256(convert_to(devplat.event_canonical(e), 'UTF8')), 'hex')
$$;

-- =====================================================================================================
-- 4. Job runs, leases, artifacts, operator facts, outbox, reconciliation, checkpoints
-- =====================================================================================================
CREATE TABLE job_runs (
  job_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id        text NOT NULL,
  task_id           text NOT NULL,
  attempt           int NOT NULL CHECK (attempt BETWEEN 1 AND 50),
  role              text NOT NULL,              -- agent role, 'planner' or 'verifier'
  dispatch_no       int NOT NULL DEFAULT 1 CHECK (dispatch_no >= 1),  -- env re-dispatch ordinal within an attempt
  idempotency_key   text NOT NULL UNIQUE CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{16,128}$'),
  target_id         bigint REFERENCES execution_targets,
  k8s_namespace     text NOT NULL CHECK (k8s_namespace ~ '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'),
  k8s_job_name      text NOT NULL CHECK (k8s_job_name ~ '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'),
  k8s_job_uid       uuid UNIQUE,
  phase             text NOT NULL DEFAULT 'planned'
                    CHECK (phase IN ('planned', 'created', 'running', 'succeeded', 'failed', 'lost', 'cancelled')),
  failure_class     text CHECK (failure_class IN ('task', 'environmental', 'platform', 'budget', 'cancelled')),
  detail            jsonb NOT NULL DEFAULT '{}',
  lease_token       bigint NOT NULL,            -- task fencing token at dispatch
  created_at        timestamptz NOT NULL DEFAULT now(),
  started_at        timestamptz,
  finished_at       timestamptz,
  last_heartbeat_at timestamptz,
  heartbeat_count   int NOT NULL DEFAULT 0,
  UNIQUE (k8s_namespace, k8s_job_name),
  UNIQUE (task_id, attempt, role, dispatch_no),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks (project_id, task_id)
);
CREATE INDEX job_runs_active ON job_runs (phase) WHERE phase IN ('planned', 'created', 'running', 'lost');

-- Named non-task leases (reconciler shards, outbox dispatcher, checkpoint exporter). The controller
-- LEADER is a Kubernetes coordination.k8s.io Lease, not this table.
CREATE TABLE leases (
  resource    text PRIMARY KEY,
  holder      text NOT NULL,
  token       bigint NOT NULL,
  acquired_at timestamptz NOT NULL,
  expires_at  timestamptz NOT NULL
);

CREATE TABLE artifacts (
  artifact_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id      text NOT NULL REFERENCES projects,
  sha256          text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  bucket          text NOT NULL,
  object_key      text NOT NULL,
  size_bytes      bigint NOT NULL CHECK (size_bytes >= 0),
  media_type      text NOT NULL,
  kind            text NOT NULL REFERENCES artifact_kinds,
  task_id         text REFERENCES tasks,
  job_id          bigint REFERENCES job_runs,
  gate            text CHECK (gate ~ '^G[1-7]$'),
  retention_class text NOT NULL CHECK (retention_class IN ('ephemeral', 'standard', 'evidence')),
  retain_until    timestamptz NOT NULL,
  legal_hold      boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, sha256),
  CHECK (object_key = 'sha256/' || sha256)     -- content addressed
);

CREATE TABLE oidc_issuers (
  issuer             text PRIMARY KEY,
  audience           text NOT NULL,
  subject_deny_regex text NOT NULL DEFAULT '^(system:|devplat-|dp-)',  -- workload identities are never operators
  max_auth_age_s     int NOT NULL DEFAULT 900 CHECK (max_auth_age_s BETWEEN 60 AND 86400),
  enabled            boolean NOT NULL DEFAULT true
);

-- Authenticated human statements (approvals, DOD facts, Mac/operator task evidence). Append-only;
-- a revocation is a newer fact with the same key. Written ONLY by record_operator_fact() (devplat_api).
CREATE TABLE operator_facts (
  fact_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id      text REFERENCES projects,     -- NULL = platform-wide
  fact_key        text NOT NULL CHECK (fact_key ~ '^[A-Za-z0-9._:-]{1,64}$'),
  value           jsonb NOT NULL,
  task_id         text REFERENCES tasks,
  statement       text,
  evidence_sha256 text CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
  subject         text NOT NULL,                -- OIDC 'sub' verified by devplat-api
  issuer          text NOT NULL REFERENCES oidc_issuers,
  email           text,
  auth_time       timestamptz NOT NULL,
  token_jti       text NOT NULL UNIQUE,         -- one fact per authenticated request (replay refused)
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  recorded_via    text NOT NULL                 -- DB session user of the API
);
CREATE INDEX operator_facts_key ON operator_facts (fact_key, project_id, fact_id DESC);

CREATE TABLE outbox (
  outbox_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id       text NOT NULL REFERENCES projects,
  target           text NOT NULL,
  operation        text NOT NULL,
  dedup_key        text NOT NULL UNIQUE CHECK (length(dedup_key) BETWEEN 8 AND 256),
  payload          jsonb NOT NULL,
  status           text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_flight', 'done', 'dead')),
  attempts         int NOT NULL DEFAULT 0,
  max_attempts     int NOT NULL DEFAULT 8,
  next_attempt_at  timestamptz NOT NULL DEFAULT now(),
  claimed_by       text,
  claim_expires_at timestamptz,
  last_error       text,
  external_ref     text,                        -- e.g. PR number / Linear comment id once done
  source_task_id   text,
  source_seq       int,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  done_at          timestamptz,
  FOREIGN KEY (target, operation) REFERENCES outbox_operations
);
CREATE INDEX outbox_due ON outbox (next_attempt_at) WHERE status IN ('pending', 'in_flight');

CREATE TABLE reconciliation_runs (
  run_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id    text REFERENCES projects,
  kind          text NOT NULL CHECK (kind IN ('jobs', 'github', 'linear', 'artifacts', 'chain', 'leases', 'outbox')),
  controller_id text NOT NULL,
  started_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz,
  status        text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'drift', 'error')),
  findings      jsonb NOT NULL DEFAULT '[]',
  actions       jsonb NOT NULL DEFAULT '[]'
);

-- Digest over every task's chain tail. Exported (signed, outside the DB) to the artifact store and git so a
-- consistent rewrite by a DB superuser is detectable (19-postgresql-state.md §8).
CREATE TABLE chain_checkpoints (
  checkpoint_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at    timestamptz NOT NULL DEFAULT now(),
  controller_id text NOT NULL,
  digest        text NOT NULL CHECK (digest ~ '^[0-9a-f]{64}$'),
  task_count    int NOT NULL,
  event_count   bigint NOT NULL,
  max_event_id  bigint
);
CREATE TABLE checkpoint_exports (
  checkpoint_id   bigint NOT NULL REFERENCES chain_checkpoints,
  artifact_sha256 text NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  signature_ref   text NOT NULL,                -- e.g. sigstore bundle / GPG signature location
  exported_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (checkpoint_id, artifact_sha256)
);

-- =====================================================================================================
-- 5. Immutability triggers
-- =====================================================================================================
CREATE FUNCTION forbid_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE = 'DP003',
    MESSAGE = format('refused: %s is append-only (%s forbidden)', TG_TABLE_NAME, TG_OP);
END $$;

CREATE TRIGGER task_events_append_only BEFORE UPDATE OR DELETE ON task_events FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER task_events_no_truncate BEFORE TRUNCATE ON task_events FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER task_contracts_append_only BEFORE UPDATE OR DELETE ON task_contracts FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER task_contracts_no_truncate BEFORE TRUNCATE ON task_contracts FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER operator_facts_append_only BEFORE UPDATE OR DELETE ON operator_facts FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER operator_facts_no_truncate BEFORE TRUNCATE ON operator_facts FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER chain_checkpoints_append_only BEFORE UPDATE OR DELETE ON chain_checkpoints FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER checkpoint_exports_append_only BEFORE UPDATE OR DELETE ON checkpoint_exports FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER tasks_no_delete BEFORE DELETE ON tasks FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER tasks_no_truncate BEFORE TRUNCATE ON tasks FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();

-- State columns of tasks change only inside record_event() (defence in depth against owner-level bugs).
CREATE FUNCTION guard_task_state() RETURNS trigger
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  IF coalesce(current_setting('devplat.writer', true), '') <> 'record_event' AND
     (NEW.task_id, NEW.project_id, NEW.kind, NEW.lifecycle, NEW.parent_task_id, NEW.covers_tasks, NEW.state,
      NEW.contract_version, NEW.core_sha256, NEW.attempt, NEW.gates, NEW.counts, NEW.head_commit, NEW.impl_head,
      NEW.pr_head, NEW.frozen_files, NEW.need_bump, NEW.last_seq, NEW.last_hash)
     IS DISTINCT FROM
     (OLD.task_id, OLD.project_id, OLD.kind, OLD.lifecycle, OLD.parent_task_id, OLD.covers_tasks, OLD.state,
      OLD.contract_version, OLD.core_sha256, OLD.attempt, OLD.gates, OLD.counts, OLD.head_commit, OLD.impl_head,
      OLD.pr_head, OLD.frozen_files, OLD.need_bump, OLD.last_seq, OLD.last_hash) THEN
    RAISE EXCEPTION USING ERRCODE = 'DP003', MESSAGE = 'refused: task state changes only through record_event()';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END $$;
CREATE TRIGGER tasks_guard_state BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION guard_task_state();

-- Artifacts: identity columns immutable; retention may only be extended; deletion only by expire_artifacts().
CREATE FUNCTION guard_artifact() RETURNS trigger
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF coalesce(current_setting('devplat.writer', true), '') <> 'expire_artifacts'
       OR OLD.legal_hold OR OLD.retain_until > now() THEN
      RAISE EXCEPTION USING ERRCODE = 'DP003', MESSAGE = 'refused: artifact is retained';
    END IF;
    RETURN OLD;
  END IF;
  IF (NEW.project_id, NEW.sha256, NEW.bucket, NEW.object_key, NEW.size_bytes, NEW.created_at)
     IS DISTINCT FROM (OLD.project_id, OLD.sha256, OLD.bucket, OLD.object_key, OLD.size_bytes, OLD.created_at)
     OR NEW.retain_until < OLD.retain_until THEN
    RAISE EXCEPTION USING ERRCODE = 'DP003', MESSAGE = 'refused: artifact identity is immutable and retention can only grow';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER artifacts_guard BEFORE UPDATE OR DELETE ON artifacts FOR EACH ROW EXECUTE FUNCTION guard_artifact();

-- =====================================================================================================
-- 6. Internal helpers (not granted to anyone)
-- =====================================================================================================
CREATE FUNCTION _refuse(p_msg text, p_code text DEFAULT 'DP001') RETURNS void
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE = p_code, MESSAGE = 'refused: ' || p_msg;
END $$;

CREATE FUNCTION _check_lease(t tasks, p_holder text, p_token bigint) RETURNS void
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  IF t.lease_holder IS DISTINCT FROM p_holder OR t.lease_token IS DISTINCT FROM p_token
     OR t.lease_expires_at IS NULL OR t.lease_expires_at <= clock_timestamp() THEN
    PERFORM devplat._refuse(format('stale or missing task lease for %s (presented %s/%s, current %s/%s until %s)',
      t.task_id, p_holder, p_token, t.lease_holder, t.lease_token, t.lease_expires_at), 'DP002');
  END IF;
END $$;

CREATE FUNCTION _fact_satisfied(p_project_id text, p_key text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT coalesce((SELECT f.value->>'status' = 'satisfied' FROM devplat.operator_facts f
                    WHERE f.fact_key = p_key AND (f.project_id = p_project_id OR f.project_id IS NULL)
                    ORDER BY f.fact_id DESC LIMIT 1), false)
$$;

CREATE FUNCTION _enqueue_outbox(p_project_id text, p_target text, p_operation text, p_dedup_key text,
                                p_payload jsonb, p_task_id text, p_seq int)
RETURNS TABLE (r_outbox_id bigint, r_created boolean)
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE v_id bigint; v_old outbox%ROWTYPE;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM outbox_operations o WHERE o.target = p_target AND o.operation = p_operation) THEN
    PERFORM _refuse(format('side effect %s.%s is not an allowed outbox operation', p_target, p_operation));
  END IF;
  IF p_target = 'linear' AND NOT _fact_satisfied(p_project_id, 'DOD-05') THEN
    PERFORM _refuse('Linear writes need operator fact DOD-05');
  END IF;
  INSERT INTO outbox (project_id, target, operation, dedup_key, payload, source_task_id, source_seq)
  VALUES (p_project_id, p_target, p_operation, p_dedup_key, coalesce(p_payload, '{}'), p_task_id, p_seq)
  ON CONFLICT (dedup_key) DO NOTHING RETURNING outbox_id INTO v_id;
  IF v_id IS NOT NULL THEN
    RETURN QUERY SELECT v_id, true; RETURN;
  END IF;
  SELECT * INTO v_old FROM outbox o WHERE o.dedup_key = p_dedup_key;
  IF v_old.project_id <> p_project_id OR v_old.target <> p_target OR v_old.operation <> p_operation THEN
    PERFORM _refuse('dedup key reused for a different side effect');
  END IF;
  RETURN QUERY SELECT v_old.outbox_id, false;
END $$;

-- =====================================================================================================
-- 7. Controller API (SECURITY DEFINER; EXECUTE granted to the controller role only)
-- =====================================================================================================
CREATE FUNCTION upsert_project(p_project_id text, p_display_name text, p_github_repo text, p_linear_team text,
                               p_registry_ref text, p_artifact_bucket text, p_limits jsonb DEFAULT '{}')
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  INSERT INTO projects (project_id, display_name, github_repo, linear_team, registry_ref, artifact_bucket, limits)
  VALUES (p_project_id, p_display_name, p_github_repo, p_linear_team, p_registry_ref, p_artifact_bucket, coalesce(p_limits, '{}'))
  ON CONFLICT (project_id) DO UPDATE SET display_name = EXCLUDED.display_name, github_repo = EXCLUDED.github_repo,
    linear_team = EXCLUDED.linear_team, registry_ref = EXCLUDED.registry_ref, limits = EXCLUDED.limits, updated_at = now()
  WHERE projects.artifact_bucket = EXCLUDED.artifact_bucket;
  IF NOT FOUND THEN
    PERFORM _refuse('artifact_bucket of an existing project cannot change');
  END IF;
END $$;

CREATE FUNCTION upsert_execution_target(p_project_id text, p_name text, p_cluster_ref text, p_namespace_prefix text,
                                        p_runtime_class text, p_network_class text, p_assurance text, p_enabled boolean)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE v_id bigint;
BEGIN
  INSERT INTO execution_targets (project_id, name, cluster_ref, namespace_prefix, runtime_class, network_class, assurance, enabled)
  VALUES (p_project_id, p_name, p_cluster_ref, p_namespace_prefix, p_runtime_class, p_network_class, p_assurance, p_enabled)
  ON CONFLICT (project_id, name) DO UPDATE SET cluster_ref = EXCLUDED.cluster_ref, namespace_prefix = EXCLUDED.namespace_prefix,
    runtime_class = EXCLUDED.runtime_class, network_class = EXCLUDED.network_class, assurance = EXCLUDED.assurance,
    enabled = EXCLUDED.enabled
  RETURNING target_id INTO v_id;
  RETURN v_id;
END $$;

-- Task lease: returns the fencing token, or NULL if another holder's lease is unexpired. The same holder
-- renews (same token); a takeover after expiry increments the token, invalidating the old holder's writes.
CREATE FUNCTION acquire_task_lease(p_task_id text, p_holder text, p_ttl_seconds int)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE; v_token bigint;
BEGIN
  IF p_ttl_seconds NOT BETWEEN 1 AND 3600 THEN PERFORM _refuse('lease ttl must be 1..3600 s'); END IF;
  SELECT * INTO t FROM tasks WHERE task_id = p_task_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s', p_task_id)); END IF;
  IF t.lease_holder = p_holder AND t.lease_expires_at > clock_timestamp() THEN
    UPDATE tasks SET lease_expires_at = clock_timestamp() + make_interval(secs => p_ttl_seconds) WHERE task_id = p_task_id;
    RETURN t.lease_token;
  END IF;
  IF t.lease_holder IS NOT NULL AND t.lease_expires_at > clock_timestamp() THEN
    RETURN NULL;
  END IF;
  UPDATE tasks SET lease_holder = p_holder, lease_token = t.lease_token + 1,
                   lease_expires_at = clock_timestamp() + make_interval(secs => p_ttl_seconds)
   WHERE task_id = p_task_id RETURNING lease_token INTO v_token;
  RETURN v_token;
END $$;

CREATE FUNCTION release_task_lease(p_task_id text, p_holder text, p_token bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  UPDATE tasks SET lease_holder = NULL, lease_expires_at = NULL
   WHERE task_id = p_task_id AND lease_holder = p_holder AND lease_token = p_token;
  RETURN FOUND;
END $$;

CREATE FUNCTION acquire_lease(p_resource text, p_holder text, p_ttl_seconds int)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE l leases%ROWTYPE; v_token bigint;
BEGIN
  IF p_ttl_seconds NOT BETWEEN 1 AND 3600 THEN PERFORM _refuse('lease ttl must be 1..3600 s'); END IF;
  INSERT INTO leases VALUES (p_resource, p_holder, 1, clock_timestamp(), clock_timestamp() + make_interval(secs => p_ttl_seconds))
  ON CONFLICT (resource) DO NOTHING RETURNING token INTO v_token;
  IF v_token IS NOT NULL THEN RETURN v_token; END IF;
  SELECT * INTO l FROM leases WHERE resource = p_resource FOR UPDATE;
  IF l.holder = p_holder AND l.expires_at > clock_timestamp() THEN
    UPDATE leases SET expires_at = clock_timestamp() + make_interval(secs => p_ttl_seconds) WHERE resource = p_resource;
    RETURN l.token;
  END IF;
  IF l.expires_at > clock_timestamp() THEN RETURN NULL; END IF;
  UPDATE leases SET holder = p_holder, token = l.token + 1, acquired_at = clock_timestamp(),
                    expires_at = clock_timestamp() + make_interval(secs => p_ttl_seconds)
   WHERE resource = p_resource RETURNING token INTO v_token;
  RETURN v_token;
END $$;

-- Create a task (state NEW) and give the caller its first lease. Enforces devorch's subtask id convention:
-- reviews <parent>-rN, security reviews <parent>-sN, integration <first covers_tasks entry>-iN.
CREATE FUNCTION create_task(p_project_id text, p_task_id text, p_kind text, p_parent_task_id text,
                            p_covers_tasks text[], p_external_ref text, p_holder text, p_ttl_seconds int)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE k task_kinds%ROWTYPE; p tasks%ROWTYPE; v_old tasks%ROWTYPE; v_cov text;
BEGIN
  SELECT * INTO k FROM task_kinds WHERE kind = p_kind;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown kind %s', p_kind)); END IF;
  IF NOT EXISTS (SELECT 1 FROM projects WHERE project_id = p_project_id AND status = 'active') THEN
    PERFORM _refuse(format('project %s is not active', p_project_id));
  END IF;
  IF k.subtask_suffix IN ('r', 's') THEN
    SELECT * INTO p FROM tasks WHERE task_id = p_parent_task_id;
    IF NOT FOUND OR p.project_id <> p_project_id OR p.lifecycle <> 'FULL' THEN
      PERFORM _refuse('a review subtask needs a FULL-lifecycle parent in the same project');
    END IF;
    IF p_task_id !~ ('^' || regexp_replace(p_parent_task_id, '([.\-])', '\\\1', 'g') || '-' || k.subtask_suffix || '[0-9]+$') THEN
      PERFORM _refuse(format('subtask id must be %s-%sN', p_parent_task_id, k.subtask_suffix));
    END IF;
  ELSIF k.subtask_suffix = 'i' THEN
    IF coalesce(cardinality(p_covers_tasks), 0) = 0 OR p_parent_task_id IS NOT NULL THEN
      PERFORM _refuse('an integration subtask needs covers_tasks and no parent');
    END IF;
    FOREACH v_cov IN ARRAY p_covers_tasks LOOP
      IF NOT EXISTS (SELECT 1 FROM tasks WHERE task_id = v_cov AND project_id = p_project_id) THEN
        PERFORM _refuse(format('covered task %s not found in project', v_cov));
      END IF;
    END LOOP;
    IF p_task_id !~ ('^' || regexp_replace(p_covers_tasks[1], '([.\-])', '\\\1', 'g') || '-i[0-9]+$') THEN
      PERFORM _refuse(format('integration id must be %s-iN', p_covers_tasks[1]));
    END IF;
  ELSIF p_parent_task_id IS NOT NULL OR coalesce(cardinality(p_covers_tasks), 0) > 0 THEN
    PERFORM _refuse('only subtasks have a parent or covers_tasks');
  END IF;
  INSERT INTO tasks (task_id, project_id, kind, lifecycle, parent_task_id, covers_tasks, external_ref,
                     lease_holder, lease_token, lease_expires_at)
  VALUES (p_task_id, p_project_id, p_kind, k.lifecycle, p_parent_task_id, coalesce(p_covers_tasks, '{}'), p_external_ref,
          p_holder, 1, clock_timestamp() + make_interval(secs => p_ttl_seconds))
  ON CONFLICT (task_id) DO NOTHING;
  IF FOUND THEN RETURN 1; END IF;
  -- at-least-once: an identical re-create by the current holder returns its token
  SELECT * INTO v_old FROM tasks WHERE task_id = p_task_id;
  IF v_old.project_id = p_project_id AND v_old.kind = p_kind AND v_old.parent_task_id IS NOT DISTINCT FROM p_parent_task_id
     AND v_old.lease_holder = p_holder AND v_old.lease_expires_at > clock_timestamp() THEN
    RETURN v_old.lease_token;
  END IF;
  PERFORM _refuse(format('task %s already exists', p_task_id));
END $$;

CREATE FUNCTION register_contract(p_task_id text, p_contract_version int, p_core_sha256 text, p_body jsonb,
                                  p_max_attempts int, p_holder text, p_token bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE; k task_kinds%ROWTYPE; v_old task_contracts%ROWTYPE;
BEGIN
  SELECT * INTO t FROM tasks WHERE task_id = p_task_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s', p_task_id)); END IF;
  PERFORM _check_lease(t, p_holder, p_token);
  SELECT * INTO v_old FROM task_contracts WHERE task_id = p_task_id AND contract_version = p_contract_version;
  IF FOUND THEN
    IF v_old.core_sha256 = p_core_sha256 THEN RETURN false; END IF;      -- idempotent re-registration
    PERFORM _refuse('contract version already registered with a different core');
  END IF;
  IF EXISTS (SELECT 1 FROM task_contracts WHERE task_id = p_task_id AND contract_version > p_contract_version) THEN
    PERFORM _refuse('contract versions must increase');
  END IF;
  SELECT * INTO k FROM task_kinds WHERE kind = t.kind;
  IF p_body ? 'kind' AND p_body->>'kind' <> t.kind THEN PERFORM _refuse('contract kind differs from task kind'); END IF;
  IF k.is_review AND coalesce(p_body->'review_target'->>'head_commit', '') !~ '^[0-9a-f]{40}$' THEN
    PERFORM _refuse('a review contract needs review_target.head_commit');
  END IF;
  IF k.read_only AND jsonb_array_length(coalesce(p_body->'allowed_paths', '[]')) > 0 THEN
    PERFORM _refuse('read-only kinds have empty allowed_paths');
  END IF;
  INSERT INTO task_contracts (task_id, project_id, contract_version, core_sha256, body, max_attempts, registered_by)
  VALUES (p_task_id, t.project_id, p_contract_version, p_core_sha256, p_body, p_max_attempts, p_holder);
  RETURN true;
END $$;

CREATE FUNCTION add_dependency(p_task_id text, p_depends_on text, p_requirement text, p_holder text, p_token bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE;
BEGIN
  SELECT * INTO t FROM tasks WHERE task_id = p_task_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s', p_task_id)); END IF;
  PERFORM _check_lease(t, p_holder, p_token);
  IF t.state NOT IN ('NEW', 'BLOCKED') THEN PERFORM _refuse('dependencies are added before G1'); END IF;
  INSERT INTO task_dependencies VALUES (p_task_id, p_depends_on, t.project_id, p_requirement) ON CONFLICT DO NOTHING;
END $$;

-- -----------------------------------------------------------------------------------------------------
-- record_event: the ONLY way to append to task_events / change task state. Port of devorch
-- check_transition() + apply() + verify_subtask(); refusals raise SQLSTATE DP001 (rule) / DP002 (lease).
-- -----------------------------------------------------------------------------------------------------
CREATE FUNCTION record_event(
  p_task_id text, p_event text, p_contract_version int, p_attempt int,
  p_lease_holder text, p_lease_token bigint,
  p_evidence jsonb DEFAULT '[]', p_head_commit text DEFAULT NULL, p_payload jsonb DEFAULT '{}',
  p_idempotency_key text DEFAULT NULL, p_outbox jsonb DEFAULT '[]')
RETURNS TABLE (r_seq int, r_from_state text, r_to_state text, r_gate text, r_hash text, r_replayed boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $fn$
DECLARE
  t tasks%ROWTYPE; k task_kinds%ROWTYPE; c task_contracts%ROWTYPE; st tasks%ROWTYPE; sk task_kinds%ROWTYPE;
  v_old task_events%ROWTYPE; e task_events%ROWTYPE; v_fact operator_facts%ROWTYPE;
  v_to text; v_gate text; v_have text[]; v_kinds text[]; v_counter text; v_max int; v_need text[];
  v_subs text[]; v_sub text; v_res jsonb; v_item jsonb; v_on_behalf text; v_rk text; v_ob jsonb;
  v_gates text[]; v_counts jsonb; v_impl text; v_head text; v_pr text; v_frozen jsonb; v_bump boolean;
  v_payload jsonb := coalesce(p_payload, '{}');
BEGIN
  SELECT * INTO t FROM tasks WHERE task_id = p_task_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s', p_task_id)); END IF;

  -- at-least-once controller: the same idempotency key returns the already-committed record
  IF p_idempotency_key IS NOT NULL THEN
    SELECT * INTO v_old FROM task_events te WHERE te.task_id = p_task_id AND te.idempotency_key = p_idempotency_key;
    IF FOUND THEN
      IF v_old.event <> p_event OR v_old.attempt <> p_attempt OR v_old.contract_version <> p_contract_version THEN
        PERFORM _refuse(format('idempotency key %s already used for a different record (seq %s)', p_idempotency_key, v_old.seq));
      END IF;
      RETURN QUERY SELECT v_old.seq, v_old.from_state, v_old.to_state, v_old.gate, v_old.hash, true;
      RETURN;
    END IF;
  END IF;

  PERFORM _check_lease(t, p_lease_holder, p_lease_token);
  SELECT * INTO k FROM task_kinds WHERE kind = t.kind;
  SELECT * INTO c FROM task_contracts tc WHERE tc.task_id = p_task_id AND tc.contract_version = p_contract_version;
  IF NOT FOUND THEN PERFORM _refuse(format('contract version %s of %s is not registered', p_contract_version, p_task_id)); END IF;

  SELECT tr.to_state, tr.gate INTO v_to, v_gate FROM transitions tr
   WHERE tr.lifecycle = t.lifecycle AND tr.from_state = t.state AND tr.event = p_event;
  IF NOT FOUND THEN
    PERFORM _refuse(format('illegal transition for kind %s: %s --%s-->', t.kind, t.state, p_event));
  END IF;

  -- evidence shape and references
  IF jsonb_typeof(p_evidence) IS DISTINCT FROM 'array' OR jsonb_array_length(p_evidence) < 1 OR jsonb_array_length(p_evidence) > 100 THEN
    PERFORM _refuse('1..100 evidence items are required');
  END IF;
  IF pg_column_size(v_payload) > 65536 THEN PERFORM _refuse('payload over 64 KiB: store it as an artifact'); END IF;
  FOR v_item IN SELECT x FROM jsonb_array_elements(p_evidence) x LOOP
    IF jsonb_typeof(v_item) <> 'object' OR coalesce(v_item->>'ref', '') = '' THEN
      PERFORM _refuse('evidence items need kind and a non-empty ref');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM evidence_kinds ek WHERE ek.kind = v_item->>'kind') THEN
      PERFORM _refuse(format('unknown evidence kind %s', v_item->>'kind'));
    END IF;
    IF (SELECT ek.is_file FROM evidence_kinds ek WHERE ek.kind = v_item->>'kind') THEN
      IF coalesce(v_item->>'sha256', '') !~ '^[0-9a-f]{64}$' OR NOT EXISTS (
           SELECT 1 FROM artifacts a WHERE a.project_id = t.project_id AND a.sha256 = v_item->>'sha256') THEN
        PERFORM _refuse(format('file evidence %s is not a registered artifact of project %s', v_item->>'ref', t.project_id));
      END IF;
    END IF;
    IF v_item->>'kind' = 'operator_fact' THEN
      IF v_item->>'ref' !~ '^[0-9]{1,18}$' THEN PERFORM _refuse('operator_fact ref must be a fact_id'); END IF;
      SELECT * INTO v_fact FROM operator_facts f WHERE f.fact_id = (v_item->>'ref')::bigint;
      IF NOT FOUND OR (v_fact.project_id IS NOT NULL AND v_fact.project_id <> t.project_id) THEN
        PERFORM _refuse(format('operator fact %s not found for project %s', v_item->>'ref', t.project_id));
      END IF;
      v_on_behalf := v_fact.issuer || '#' || v_fact.subject;
    END IF;
  END LOOP;
  v_kinds := ARRAY(SELECT DISTINCT x->>'kind' FROM jsonb_array_elements(p_evidence) x);

  IF p_head_commit IS NOT NULL AND p_head_commit !~ '^[0-9a-f]{40}$' THEN PERFORM _refuse('head_commit must be a 40-hex sha'); END IF;
  IF p_attempt IS NULL OR p_attempt NOT BETWEEN 1 AND 50 THEN PERFORM _refuse('attempt must be 1..50'); END IF;

  -- contract-core continuity (devorch: core changes only through contract_revised with a higher version)
  IF p_event = 'contract_revised' THEN
    IF t.contract_version IS NOT NULL AND p_contract_version <= t.contract_version THEN
      PERFORM _refuse('contract_revised needs a higher contract_version');
    END IF;
    IF t.core_sha256 IS NOT NULL AND c.core_sha256 = t.core_sha256 THEN
      PERFORM _refuse('contract_revised but the contract core did not change');
    END IF;
  ELSIF t.contract_version IS NOT NULL AND (p_contract_version <> t.contract_version OR c.core_sha256 <> t.core_sha256) THEN
    PERFORM _refuse('contract changed without a contract_revised record');
  END IF;

  -- attempt discipline
  IF p_event = 'dispatched' AND t.attempt IS NOT NULL THEN
    IF p_attempt < t.attempt THEN PERFORM _refuse('attempt number went backwards'); END IF;
    IF t.need_bump AND p_attempt <> t.attempt + 1 THEN
      PERFORM _refuse(format('a correction must be dispatched as attempt %s', t.attempt + 1));
    END IF;
  ELSIF p_event NOT IN ('created', 'contract_revised') AND t.attempt IS NOT NULL AND p_attempt <> t.attempt THEN
    PERFORM _refuse(format('attempt %s differs from the current attempt %s (only dispatched advances it)', p_attempt, t.attempt));
  END IF;

  IF p_event = 'implementation_completed' AND t.lifecycle = 'FULL' THEN
    IF p_head_commit IS NULL THEN PERFORM _refuse('implementation_completed must record head_commit (the result''s head)'); END IF;
    IF NOT 'result_file' = ANY (v_kinds) THEN PERFORM _refuse('implementation_completed needs a result_file'); END IF;
  END IF;

  -- budgets
  IF p_event IN ('attempt_failed', 'tests_failed') AND (t.counts->>'attempt')::int + 1 >= c.max_attempts THEN
    PERFORM _refuse(format('attempt budget %s exhausted: record failed or escalated', c.max_attempts));
  END IF;
  SELECT ec.counter, lc.max_count INTO v_counter, v_max
    FROM event_counters ec JOIN loop_counters lc ON lc.counter = ec.counter WHERE ec.event = p_event;
  IF v_counter IS NOT NULL AND v_max IS NOT NULL AND (t.counts->>v_counter)::int + 1 > v_max THEN
    PERFORM _refuse(format('%s loop budget %s exhausted: record failed or escalated', v_counter, v_max));
  END IF;

  -- duplicate gates
  IF v_gate IS NOT NULL AND v_gate = ANY (t.gates) THEN
    PERFORM _refuse(format('gate %s already recorded since the last correction', v_gate));
  END IF;
  v_have := CASE WHEN v_gate IS NULL THEN t.gates ELSE array_append(t.gates, v_gate) END;

  -- gate-specific evidence
  IF p_event = 'unblocked' THEN
    IF NOT 'design_ref' = ANY (v_kinds) THEN PERFORM _refuse('G1 needs design_ref evidence (operator-approved design commit)'); END IF;
    FOR v_rk IN SELECT hp.fact_key FROM hard_preconditions hp WHERE hp.lifecycle = t.lifecycle ORDER BY hp.fact_key LOOP
      IF NOT _fact_satisfied(t.project_id, v_rk) THEN
        PERFORM _refuse(format('not READY, refusing G1: hard precondition %s is not a satisfied operator fact', v_rk));
      END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM task_dependencies d JOIN tasks dt ON dt.task_id = d.depends_on
                WHERE d.task_id = p_task_id
                  AND NOT (dt.state = 'COMPLETED' OR (d.requirement = 'interface_frozen'
                           AND dt.frozen_files <> '{}'::jsonb AND dt.state IN ('AWAITING_HUMAN', 'COMPLETED')))) THEN
      PERFORM _refuse('not READY, refusing G1: dependencies not satisfied');
    END IF;
  END IF;
  IF p_event = 'tests_passed' THEN
    IF p_head_commit IS NULL THEN PERFORM _refuse('tests_passed must record head_commit (the tested tip)'); END IF;
    IF NOT 'test_run' = ANY (v_kinds) THEN PERFORM _refuse('tests_passed needs test_run evidence from the verifier re-run'); END IF;
    IF t.impl_head IS DISTINCT FROM p_head_commit THEN
      PERFORM _refuse('tests_passed head is not the head of a checked implementation_completed in this attempt');
    END IF;
  END IF;
  IF p_event IN ('code_review_passed', 'security_review_passed', 'integration_verified') THEN
    v_subs := ARRAY(SELECT x->>'ref' FROM jsonb_array_elements(p_evidence) x WHERE x->>'kind' = 'subtask');
    IF cardinality(v_subs) = 0 THEN
      PERFORM _refuse(format('%s needs subtask evidence (a COMPLETED review/integration task)', p_event));
    END IF;
    FOREACH v_sub IN ARRAY v_subs LOOP
      SELECT * INTO st FROM tasks WHERE task_id = v_sub;
      IF NOT FOUND OR st.project_id <> t.project_id THEN PERFORM _refuse(format('subtask %s not found in project', v_sub)); END IF;
      IF NOT EXISTS (SELECT 1 FROM gate_providers gp WHERE gp.event = p_event AND gp.kind = st.kind) THEN
        PERFORM _refuse(format('subtask %s kind %s cannot provide %s', v_sub, st.kind, p_event));
      END IF;
      IF st.kind <> 'integration' AND st.parent_task_id IS DISTINCT FROM t.task_id THEN
        PERFORM _refuse(format('subtask %s does not belong to %s', v_sub, t.task_id));
      END IF;
      IF st.state <> 'COMPLETED' THEN PERFORM _refuse(format('subtask %s is %s, not COMPLETED', v_sub, st.state)); END IF;
      SELECT te.payload->'result' INTO v_res FROM task_events te
       WHERE te.task_id = v_sub AND te.event = 'result_accepted' ORDER BY te.seq DESC LIMIT 1;
      IF v_res IS NULL THEN PERFORM _refuse(format('%s has no accepted result', v_sub)); END IF;
      SELECT * INTO sk FROM task_kinds WHERE kind = st.kind;
      IF sk.is_review THEN
        IF coalesce(v_res->>'recommendation', '') NOT IN ('accept', 'accept_with_conditions') THEN
          PERFORM _refuse(format('review %s did not accept', v_sub));
        END IF;
        IF coalesce((v_res->>'blocking_findings')::int, 0) > 0 THEN PERFORM _refuse(format('review %s has blocking findings', v_sub)); END IF;
        IF v_res->>'reviewed_head_commit' IS DISTINCT FROM t.head_commit OR
           (SELECT tc.body->'review_target'->>'head_commit' FROM task_contracts tc
             WHERE tc.task_id = v_sub AND tc.contract_version = st.contract_version) IS DISTINCT FROM t.head_commit THEN
          PERFORM _refuse(format('review %s is not bound to the current tested head %s', v_sub, t.head_commit));
        END IF;
      ELSE
        IF NOT t.task_id = ANY (st.covers_tasks) THEN PERFORM _refuse(format('integration %s does not cover %s', v_sub, t.task_id)); END IF;
        IF coalesce(v_res->>'status', '') <> 'completed' OR coalesce(v_res->>'recommendation', '') NOT IN ('accept', 'accept_with_conditions') THEN
          PERFORM _refuse(format('integration %s did not pass', v_sub));
        END IF;
        IF NOT coalesce(v_res->'integrated_heads', '[]') ? (t.task_id || '@' || coalesce(t.head_commit, '')) THEN
          PERFORM _refuse(format('integration %s integrated a different head of %s', v_sub, t.task_id));
        END IF;
      END IF;
    END LOOP;
  END IF;
  IF p_event = 'code_review_passed' THEN
    FOR v_rk IN SELECT rk.kind FROM jsonb_array_elements_text(coalesce(c.body->'required_reviewers', '[]')) rr(reviewer)
                  JOIN reviewer_kinds rk ON rk.reviewer = rr.reviewer WHERE rk.kind <> 'security_review' LOOP
      IF NOT EXISTS (SELECT 1 FROM tasks s WHERE s.task_id = ANY (v_subs) AND s.kind = v_rk) THEN
        PERFORM _refuse(format('G3 requires a passed %s (required_reviewers)', v_rk));
      END IF;
    END LOOP;
  END IF;
  IF p_event = 'pr_prepared' THEN
    IF NOT ('pr' = ANY (v_kinds) AND 'ci_run' = ANY (v_kinds)) OR p_head_commit IS NULL THEN
      PERFORM _refuse('pr_prepared needs pr and ci_run evidence and head_commit');
    END IF;
    IF p_head_commit IS DISTINCT FROM t.head_commit THEN PERFORM _refuse('pushed head differs from the tested and reviewed head'); END IF;
  END IF;
  IF p_event = 'human_merged' THEN
    IF NOT 'github_merge' = ANY (v_kinds) OR p_head_commit IS DISTINCT FROM t.pr_head THEN
      PERFORM _refuse('human_merged needs github_merge evidence and head_commit equal to the G6 head');
    END IF;
  END IF;
  IF p_event = 'result_accepted' THEN
    IF k.operator_evidence THEN
      IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(p_evidence) x JOIN operator_facts f
                        ON f.fact_id = CASE WHEN x->>'kind' = 'operator_fact' THEN (x->>'ref')::bigint END
                     WHERE f.task_id = p_task_id) THEN
        PERFORM _refuse('operator/Mac task completion needs an authenticated operator fact for this task');
      END IF;
    ELSE
      IF NOT 'result_file' = ANY (v_kinds) THEN PERFORM _refuse('result_accepted needs a validated result_file'); END IF;
      IF jsonb_typeof(v_payload->'result') IS DISTINCT FROM 'object' THEN
        PERFORM _refuse('result_accepted needs payload.result (controller-validated result summary)');
      END IF;
      IF k.is_review AND (v_payload->'result'->>'reviewed_head_commit') IS DISTINCT FROM (c.body->'review_target'->>'head_commit') THEN
        PERFORM _refuse('reviewed_head_commit differs from review_target.head_commit');
      END IF;
    END IF;
  END IF;
  IF p_event = 'interface_frozen' AND (jsonb_typeof(v_payload->'frozen_files') IS DISTINCT FROM 'object'
                                       OR v_payload->'frozen_files' = '{}'::jsonb) THEN
    PERFORM _refuse('interface_frozen needs payload.frozen_files {path: sha256}');
  END IF;

  -- resolve the review-gate target and check gate prerequisites (REQUIRED_BEFORE)
  IF p_event IN ('code_review_passed', 'security_review_passed') THEN
    v_to := CASE WHEN 'G3' = ANY (v_have) AND (NOT k.needs_g4 OR 'G4' = ANY (v_have))
                 THEN 'AWAITING_INTEGRATION' ELSE 'AWAITING_REVIEW' END;
  END IF;
  v_need := ARRAY(SELECT gp.gate FROM gate_prerequisites gp WHERE gp.to_state = v_to AND NOT gp.gate = ANY (v_have) ORDER BY gp.gate);
  IF t.lifecycle = 'FULL' AND v_to <> t.state AND cardinality(v_need) > 0 THEN
    IF NOT (v_to = 'AWAITING_INTEGRATION' AND v_need = ARRAY['G4'] AND NOT k.needs_g4) THEN
      PERFORM _refuse(format('cannot enter %s: missing gates %s', v_to, v_need));
    END IF;
  END IF;
  IF t.lifecycle = 'SHORT' AND v_to = 'RUNNING' AND NOT 'G1' = ANY (v_have) THEN
    PERFORM _refuse('cannot enter RUNNING without G1');
  END IF;

  -- apply (devorch apply())
  v_gates := t.gates; v_counts := t.counts; v_impl := t.impl_head; v_head := t.head_commit; v_pr := t.pr_head;
  v_frozen := t.frozen_files; v_bump := t.need_bump;
  IF v_to = 'RUNNING' AND t.state <> 'RUNNING' THEN
    v_gates := ARRAY(SELECT g FROM unnest(v_gates) g WHERE g = 'G1');
    v_impl := NULL;
    IF t.state IN ('AWAITING_REVIEW', 'AWAITING_INTEGRATION', 'AWAITING_HUMAN') THEN v_bump := true; END IF;
  END IF;
  IF v_gate IS NOT NULL THEN v_gates := array_append(v_gates, v_gate); END IF;
  IF p_event IN ('attempt_failed', 'tests_failed') THEN v_impl := NULL; v_bump := true; END IF;
  IF p_event = 'dispatched' THEN v_bump := false; END IF;
  IF p_event = 'implementation_completed' THEN v_impl := p_head_commit; END IF;
  IF p_event = 'tests_passed' THEN v_head := p_head_commit; END IF;
  IF p_event = 'pr_prepared' THEN v_pr := p_head_commit; END IF;
  IF p_event = 'interface_frozen' THEN v_frozen := v_frozen || (v_payload->'frozen_files'); END IF;
  IF v_counter IS NOT NULL THEN
    v_counts := jsonb_set(v_counts, ARRAY[v_counter], to_jsonb((v_counts->>v_counter)::int + 1));
  END IF;
  IF p_event = 'contract_revised' THEN
    v_counts := '{"attempt":0,"review":0,"security":0,"integration":0,"env":0}';
    v_gates := ARRAY(SELECT g FROM unnest(v_gates) g WHERE g = 'G1');
    v_frozen := '{}'; v_impl := NULL; v_bump := false;
  END IF;

  e.project_id := t.project_id; e.task_id := p_task_id; e.seq := t.last_seq + 1; e.at := clock_timestamp();
  e.event := p_event; e.from_state := t.state; e.to_state := v_to; e.gate := v_gate;
  e.actor := 'devplat-controller'; e.controller_id := p_lease_holder; e.on_behalf_of := v_on_behalf;
  e.contract_version := p_contract_version; e.contract_core_sha256 := c.core_sha256; e.attempt := p_attempt;
  e.head_commit := p_head_commit; e.evidence := p_evidence; e.payload := v_payload;
  e.idempotency_key := p_idempotency_key; e.lease_token := p_lease_token; e.prev_hash := t.last_hash;
  e.hash := event_hash(e);
  INSERT INTO task_events (project_id, task_id, seq, at, event, from_state, to_state, gate, actor, controller_id,
                           on_behalf_of, contract_version, contract_core_sha256, attempt, head_commit, evidence,
                           payload, idempotency_key, lease_token, prev_hash, hash)
  VALUES (e.project_id, e.task_id, e.seq, e.at, e.event, e.from_state, e.to_state, e.gate, e.actor, e.controller_id,
          e.on_behalf_of, e.contract_version, e.contract_core_sha256, e.attempt, e.head_commit, e.evidence,
          e.payload, e.idempotency_key, e.lease_token, e.prev_hash, e.hash);

  PERFORM set_config('devplat.writer', 'record_event', true);
  UPDATE tasks SET state = v_to, contract_version = p_contract_version, core_sha256 = c.core_sha256, attempt = p_attempt,
                   gates = v_gates, counts = v_counts, head_commit = v_head, impl_head = v_impl, pr_head = v_pr,
                   frozen_files = v_frozen, need_bump = v_bump, last_seq = e.seq, last_hash = e.hash
   WHERE task_id = p_task_id;
  PERFORM set_config('devplat.writer', '', true);

  -- transactional outbox: side effects become visible exactly when the event commits
  FOR v_ob IN SELECT x FROM jsonb_array_elements(coalesce(p_outbox, '[]')) x LOOP
    PERFORM _enqueue_outbox(t.project_id, v_ob->>'target', v_ob->>'operation', v_ob->>'dedup_key',
                            coalesce(v_ob->'payload', '{}'), p_task_id, e.seq);
  END LOOP;

  RETURN QUERY SELECT e.seq, e.from_state, e.to_state, e.gate, e.hash, false;
END $fn$;

-- Job dispatch with an idempotency key: concurrent or repeated calls yield exactly one row.
CREATE FUNCTION dispatch_job(p_task_id text, p_attempt int, p_role text, p_dispatch_no int, p_idempotency_key text,
                             p_target_id bigint, p_k8s_namespace text, p_k8s_job_name text, p_holder text, p_token bigint)
RETURNS TABLE (r_job_id bigint, r_created boolean, r_k8s_job_name text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE; v_id bigint; j job_runs%ROWTYPE;
BEGIN
  SELECT * INTO t FROM tasks WHERE task_id = p_task_id FOR SHARE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s', p_task_id)); END IF;
  PERFORM _check_lease(t, p_holder, p_token);
  IF t.state <> 'RUNNING' THEN PERFORM _refuse(format('task %s is %s; Jobs are dispatched only in RUNNING', p_task_id, t.state)); END IF;
  IF t.attempt IS NOT NULL AND p_attempt <> t.attempt AND NOT (t.need_bump AND p_attempt = t.attempt + 1) THEN
    PERFORM _refuse(format('attempt %s is not dispatchable (current %s)', p_attempt, t.attempt));
  END IF;
  IF p_target_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM execution_targets et
       WHERE et.target_id = p_target_id AND et.project_id = t.project_id AND et.enabled
         AND p_k8s_namespace LIKE et.namespace_prefix || '-%') THEN
    PERFORM _refuse('namespace is not in an enabled execution target of the task''s project');
  END IF;
  INSERT INTO job_runs (project_id, task_id, attempt, role, dispatch_no, idempotency_key, target_id,
                        k8s_namespace, k8s_job_name, lease_token)
  VALUES (t.project_id, p_task_id, p_attempt, p_role, p_dispatch_no, p_idempotency_key, p_target_id,
          p_k8s_namespace, p_k8s_job_name, p_token)
  ON CONFLICT (idempotency_key) DO NOTHING RETURNING job_id INTO v_id;
  IF v_id IS NOT NULL THEN
    RETURN QUERY SELECT v_id, true, p_k8s_job_name; RETURN;
  END IF;
  SELECT * INTO j FROM job_runs jr WHERE jr.idempotency_key = p_idempotency_key;
  IF j.task_id <> p_task_id OR j.attempt <> p_attempt OR j.role <> p_role OR j.k8s_job_name <> p_k8s_job_name THEN
    PERFORM _refuse('idempotency key collision with a different job');
  END IF;
  RETURN QUERY SELECT j.job_id, false, j.k8s_job_name;
END $$;

CREATE FUNCTION update_job_phase(p_job_id bigint, p_phase text, p_k8s_uid uuid, p_failure_class text, p_detail jsonb,
                                 p_holder text, p_token bigint)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE j job_runs%ROWTYPE; t tasks%ROWTYPE;
BEGIN
  SELECT * INTO j FROM job_runs WHERE job_id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown job %s', p_job_id)); END IF;
  SELECT * INTO t FROM tasks WHERE task_id = j.task_id;
  PERFORM _check_lease(t, p_holder, p_token);
  IF p_k8s_uid IS NOT NULL AND j.k8s_job_uid IS NOT NULL AND j.k8s_job_uid <> p_k8s_uid THEN
    PERFORM _refuse(format('duplicate execution: Job %s/%s has uid %s, observed %s', j.k8s_namespace, j.k8s_job_name, j.k8s_job_uid, p_k8s_uid));
  END IF;
  IF j.phase = p_phase THEN RETURN j.phase; END IF;
  IF NOT EXISTS (SELECT 1 FROM job_phase_transitions WHERE from_phase = j.phase AND to_phase = p_phase) THEN
    PERFORM _refuse(format('illegal job phase change %s -> %s', j.phase, p_phase));
  END IF;
  UPDATE job_runs SET phase = p_phase, k8s_job_uid = coalesce(k8s_job_uid, p_k8s_uid),
         failure_class = coalesce(p_failure_class, failure_class), detail = detail || coalesce(p_detail, '{}'),
         started_at = CASE WHEN p_phase = 'running' THEN coalesce(started_at, clock_timestamp()) ELSE started_at END,
         finished_at = CASE WHEN p_phase IN ('succeeded', 'failed', 'cancelled') THEN clock_timestamp() ELSE finished_at END
   WHERE job_id = p_job_id;
  RETURN p_phase;
END $$;

-- Heartbeat observed by the controller (pod/Job status, runner progress object); agents never write the DB.
CREATE FUNCTION job_heartbeat(p_job_id bigint, p_k8s_uid uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  UPDATE job_runs SET last_heartbeat_at = clock_timestamp(), heartbeat_count = heartbeat_count + 1
   WHERE job_id = p_job_id AND phase IN ('created', 'running') AND k8s_job_uid IS NOT DISTINCT FROM p_k8s_uid;
  RETURN FOUND;
END $$;

CREATE FUNCTION register_artifact(p_project_id text, p_sha256 text, p_bucket text, p_size_bytes bigint, p_media_type text,
                                  p_kind text, p_task_id text, p_job_id bigint, p_gate text, p_retention_class text)
RETURNS TABLE (r_artifact_id bigint, r_created boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE ak artifact_kinds%ROWTYPE; v_id bigint; a artifacts%ROWTYPE; v_until timestamptz;
BEGIN
  SELECT * INTO ak FROM artifact_kinds WHERE kind = p_kind;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown artifact kind %s', p_kind)); END IF;
  IF p_size_bytes > ak.max_bytes THEN PERFORM _refuse(format('%s artifact over %s bytes', p_kind, ak.max_bytes)); END IF;
  IF NOT EXISTS (SELECT 1 FROM projects WHERE project_id = p_project_id AND artifact_bucket = p_bucket) THEN
    PERFORM _refuse('bucket is not the project''s artifact bucket');
  END IF;
  v_until := now() + make_interval(days => CASE p_retention_class WHEN 'ephemeral' THEN 7 ELSE ak.default_retention_days END);
  INSERT INTO artifacts (project_id, sha256, bucket, object_key, size_bytes, media_type, kind, task_id, job_id, gate,
                         retention_class, retain_until)
  VALUES (p_project_id, p_sha256, p_bucket, 'sha256/' || p_sha256, p_size_bytes, p_media_type, p_kind, p_task_id, p_job_id,
          p_gate, p_retention_class, v_until)
  ON CONFLICT (project_id, sha256) DO NOTHING RETURNING artifact_id INTO v_id;
  IF v_id IS NOT NULL THEN RETURN QUERY SELECT v_id, true; RETURN; END IF;
  SELECT * INTO a FROM artifacts x WHERE x.project_id = p_project_id AND x.sha256 = p_sha256 FOR UPDATE;
  IF a.size_bytes <> p_size_bytes THEN PERFORM _refuse('same sha256 registered with a different size'); END IF;
  IF v_until > a.retain_until THEN       -- the same content cited again: retention only grows
    UPDATE artifacts SET retain_until = v_until,
           retention_class = CASE WHEN p_retention_class = 'evidence' THEN 'evidence' ELSE retention_class END
     WHERE artifact_id = a.artifact_id;
  END IF;
  RETURN QUERY SELECT a.artifact_id, false;
END $$;

-- Rows whose retention ended and that no event cites; the controller then deletes the objects.
CREATE FUNCTION expire_artifacts(p_limit int)
RETURNS TABLE (r_bucket text, r_object_key text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  PERFORM set_config('devplat.writer', 'expire_artifacts', true);
  RETURN QUERY
  WITH d AS (
    DELETE FROM artifacts a WHERE a.artifact_id IN (
      SELECT x.artifact_id FROM artifacts x
       WHERE x.retain_until < now() AND NOT x.legal_hold
         AND NOT EXISTS (SELECT 1 FROM task_events te WHERE te.project_id = x.project_id
                           AND te.evidence @> jsonb_build_array(jsonb_build_object('sha256', x.sha256)))
       ORDER BY x.retain_until LIMIT p_limit)
    RETURNING a.bucket, a.object_key)
  SELECT d.bucket, d.object_key FROM d;
  PERFORM set_config('devplat.writer', '', true);
END $$;

CREATE FUNCTION enqueue_outbox(p_project_id text, p_target text, p_operation text, p_dedup_key text, p_payload jsonb)
RETURNS TABLE (r_outbox_id bigint, r_created boolean)
LANGUAGE sql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT * FROM devplat._enqueue_outbox(p_project_id, p_target, p_operation, p_dedup_key, p_payload, NULL, NULL)
$$;

CREATE FUNCTION claim_outbox(p_holder text, p_limit int, p_claim_seconds int DEFAULT 120)
RETURNS SETOF outbox LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  RETURN QUERY
  WITH c AS (
  UPDATE outbox o SET status = 'in_flight', claimed_by = p_holder, attempts = o.attempts + 1, updated_at = clock_timestamp(),
         claim_expires_at = clock_timestamp() + make_interval(secs => p_claim_seconds)
   WHERE o.outbox_id IN (SELECT x.outbox_id FROM outbox x
                          WHERE (x.status = 'pending' AND x.next_attempt_at <= clock_timestamp())
                             OR (x.status = 'in_flight' AND x.claim_expires_at < clock_timestamp())
                          ORDER BY x.next_attempt_at, x.outbox_id LIMIT p_limit FOR UPDATE SKIP LOCKED)
  RETURNING o.*)
  SELECT * FROM c;
END $$;

CREATE FUNCTION complete_outbox(p_outbox_id bigint, p_holder text, p_external_ref text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  UPDATE outbox SET status = 'done', external_ref = p_external_ref, done_at = clock_timestamp(), updated_at = clock_timestamp(),
                    claim_expires_at = NULL
   WHERE outbox_id = p_outbox_id AND status = 'in_flight' AND claimed_by = p_holder;
  RETURN FOUND;
END $$;

-- Retryable failures back off 30 s * 2^(attempts-1), capped at 1 h; then 'dead' (operator-visible).
CREATE FUNCTION fail_outbox(p_outbox_id bigint, p_holder text, p_error text, p_retryable boolean, p_retry_after_s int DEFAULT NULL)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE o outbox%ROWTYPE; v_status text;
BEGIN
  SELECT * INTO o FROM outbox WHERE outbox_id = p_outbox_id AND status = 'in_flight' AND claimed_by = p_holder FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  v_status := CASE WHEN p_retryable AND o.attempts < o.max_attempts THEN 'pending' ELSE 'dead' END;
  UPDATE outbox SET status = v_status, last_error = left(p_error, 2000), claim_expires_at = NULL, updated_at = clock_timestamp(),
         next_attempt_at = clock_timestamp() + make_interval(secs => greatest(coalesce(p_retry_after_s, 0),
                                                                     least(30 * power(2, greatest(o.attempts - 1, 0)), 3600)))
   WHERE outbox_id = p_outbox_id;
  RETURN v_status;
END $$;

CREATE FUNCTION start_reconciliation(p_kind text, p_project_id text, p_controller_id text)
RETURNS bigint LANGUAGE sql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
  INSERT INTO devplat.reconciliation_runs (kind, project_id, controller_id) VALUES (p_kind, p_project_id, p_controller_id)
  RETURNING run_id
$$;

CREATE FUNCTION finish_reconciliation(p_run_id bigint, p_status text, p_findings jsonb, p_actions jsonb)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
  UPDATE devplat.reconciliation_runs SET status = p_status, findings = coalesce(p_findings, '[]'),
         actions = coalesce(p_actions, '[]'), finished_at = clock_timestamp()
   WHERE run_id = p_run_id AND status = 'running'
$$;

-- =====================================================================================================
-- 8. Verification (read-only; callable by every role)
-- =====================================================================================================
-- Recompute every task's chain: seq contiguity, prev_hash links, row hash, from_state continuity,
-- legality of each (lifecycle, from_state, event), and the tasks row against the tail.
-- An empty result means the stored rows are internally consistent. It CANNOT detect a consistent rewrite
-- by a DB superuser; compare chain_digest() with an exported checkpoint for that.
CREATE FUNCTION verify_chain(p_task_id text DEFAULT NULL)
RETURNS TABLE (v_task_id text, v_seq int, v_problem text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE tk tasks%ROWTYPE; e task_events%ROWTYPE; v_prev text; v_n int; v_state text; v_tr transitions%ROWTYPE;
BEGIN
  FOR tk IN SELECT * FROM tasks WHERE p_task_id IS NULL OR task_id = p_task_id ORDER BY task_id LOOP
    v_prev := 'GENESIS'; v_n := 0; v_state := 'NEW';
    FOR e IN SELECT * FROM task_events te WHERE te.task_id = tk.task_id ORDER BY te.seq LOOP
      v_n := v_n + 1;
      IF e.seq <> v_n THEN RETURN QUERY SELECT tk.task_id, e.seq, 'seq gap (expected ' || v_n || ')'; v_n := e.seq; END IF;
      IF e.prev_hash <> v_prev THEN RETURN QUERY SELECT tk.task_id, e.seq, 'prev_hash does not link to the previous record'; END IF;
      IF event_hash(e) <> e.hash THEN RETURN QUERY SELECT tk.task_id, e.seq, 'hash mismatch (row altered)'; END IF;
      IF e.from_state <> v_state THEN RETURN QUERY SELECT tk.task_id, e.seq, 'from_state does not follow the previous to_state'; END IF;
      SELECT * INTO v_tr FROM transitions tr WHERE tr.lifecycle = tk.lifecycle AND tr.from_state = e.from_state AND tr.event = e.event;
      IF NOT FOUND OR (e.to_state <> v_tr.to_state AND NOT (e.event IN ('code_review_passed', 'security_review_passed')
                                                            AND e.to_state = 'AWAITING_INTEGRATION')) THEN
        RETURN QUERY SELECT tk.task_id, e.seq, 'not a legal transition';
      END IF;
      v_prev := e.hash; v_state := e.to_state;
    END LOOP;
    IF tk.last_seq <> v_n OR tk.last_hash <> v_prev THEN
      RETURN QUERY SELECT tk.task_id, NULL::int, 'tasks row does not match the chain tail (rows removed or added?)';
    END IF;
    IF tk.state <> v_state THEN RETURN QUERY SELECT tk.task_id, NULL::int, 'tasks.state differs from the chain'; END IF;
  END LOOP;
END $$;

CREATE FUNCTION chain_digest()
RETURNS TABLE (r_digest text, r_task_count int, r_event_count bigint, r_max_event_id bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
  WITH tails AS (SELECT DISTINCT ON (task_id) task_id, seq, hash FROM devplat.task_events ORDER BY task_id, seq DESC)
  SELECT encode(sha256(convert_to(coalesce(string_agg(task_id || ':' || seq || ':' || hash, E'\n' ORDER BY task_id), ''), 'UTF8')), 'hex'),
         (SELECT count(*)::int FROM tails), (SELECT count(*) FROM devplat.task_events), (SELECT max(event_id) FROM devplat.task_events)
    FROM tails
$$;

CREATE FUNCTION create_checkpoint(p_controller_id text)
RETURNS bigint LANGUAGE sql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
  INSERT INTO devplat.chain_checkpoints (controller_id, digest, task_count, event_count, max_event_id)
  SELECT p_controller_id, d.r_digest, d.r_task_count, d.r_event_count, d.r_max_event_id FROM devplat.chain_digest() d
  RETURNING checkpoint_id
$$;

CREATE FUNCTION record_checkpoint_export(p_checkpoint_id bigint, p_artifact_sha256 text, p_signature_ref text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
  INSERT INTO devplat.checkpoint_exports (checkpoint_id, artifact_sha256, signature_ref) VALUES (p_checkpoint_id, p_artifact_sha256, p_signature_ref)
$$;

-- =====================================================================================================
-- 9. devplat-api: authenticated operator facts (the controller can NOT call this)
-- =====================================================================================================
CREATE FUNCTION record_operator_fact(p_project_id text, p_fact_key text, p_value jsonb, p_task_id text, p_statement text,
                                     p_subject text, p_issuer text, p_email text, p_auth_time timestamptz,
                                     p_token_jti text, p_evidence_sha256 text DEFAULT NULL)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE i oidc_issuers%ROWTYPE; v_id bigint;
BEGIN
  SELECT * INTO i FROM oidc_issuers WHERE issuer = p_issuer AND enabled;
  IF NOT FOUND THEN PERFORM _refuse(format('issuer %s is not an enabled operator identity provider', p_issuer)); END IF;
  IF coalesce(p_subject, '') = '' OR p_subject ~ i.subject_deny_regex THEN
    PERFORM _refuse(format('subject %s is not a human operator identity', p_subject));
  END IF;
  IF p_auth_time IS NULL OR p_auth_time > now() + interval '60 seconds'
     OR p_auth_time < now() - make_interval(secs => i.max_auth_age_s) THEN
    PERFORM _refuse('operator authentication is not fresh (re-authenticate)');
  END IF;
  IF p_task_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tasks WHERE task_id = p_task_id AND project_id IS NOT DISTINCT FROM p_project_id) THEN
    PERFORM _refuse('task not found in project');
  END IF;
  INSERT INTO operator_facts (project_id, fact_key, value, task_id, statement, evidence_sha256, subject, issuer, email,
                              auth_time, token_jti, recorded_via)
  VALUES (p_project_id, p_fact_key, p_value, p_task_id, p_statement, p_evidence_sha256, p_subject, p_issuer, p_email,
          p_auth_time, p_token_jti, session_user)
  RETURNING fact_id INTO v_id;
  RETURN v_id;
END $$;

-- =====================================================================================================
-- 10. Views
-- =====================================================================================================
CREATE VIEW stale_jobs WITH (security_invoker = true) AS
  SELECT j.job_id, j.project_id, j.task_id, j.attempt, j.role, j.k8s_namespace, j.k8s_job_name, j.phase,
         coalesce(j.last_heartbeat_at, j.started_at, j.created_at) AS last_seen
    FROM job_runs j JOIN projects p ON p.project_id = j.project_id
   WHERE j.phase IN ('created', 'running')
     AND coalesce(j.last_heartbeat_at, j.started_at, j.created_at)
         < now() - make_interval(secs => coalesce((p.limits->>'heartbeat_timeout_seconds')::int, 300));

-- =====================================================================================================
-- 11. Row-level security and grants
-- =====================================================================================================
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['projects', 'execution_targets', 'tasks', 'task_contracts', 'task_dependencies', 'task_events',
                           'job_runs', 'artifacts', 'outbox'] LOOP
    EXECUTE format('ALTER TABLE devplat.%I ENABLE ROW LEVEL SECURITY', r);
    EXECUTE format('CREATE POLICY %I ON devplat.%I FOR SELECT USING (devplat.can_see(project_id))', r || '_visible', r);
  END LOOP;
  FOREACH r IN ARRAY ARRAY['operator_facts', 'reconciliation_runs'] LOOP
    EXECUTE format('ALTER TABLE devplat.%I ENABLE ROW LEVEL SECURITY', r);
    EXECUTE format('CREATE POLICY %I ON devplat.%I FOR SELECT USING (project_id IS NULL OR devplat.can_see(project_id))', r || '_visible', r);
  END LOOP;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA devplat FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA devplat FROM PUBLIC;
GRANT USAGE ON SCHEMA devplat TO :"role_controller", :"role_api", :"role_readonly";

-- reads (RLS applies to all three; controller and api see '*')
GRANT SELECT ON lifecycles, states, task_kinds, transitions, gate_prerequisites, loop_counters, event_counters,
  gate_providers, reviewer_kinds, evidence_kinds, hard_preconditions, job_phase_transitions, outbox_operations,
  artifact_kinds, projects, execution_targets, project_grants, tasks, task_contracts, task_dependencies, task_events,
  job_runs, artifacts, operator_facts, outbox, reconciliation_runs, chain_checkpoints, checkpoint_exports, stale_jobs
  TO :"role_controller", :"role_api", :"role_readonly";
GRANT SELECT ON leases, oidc_issuers TO :"role_controller";
GRANT SELECT ON oidc_issuers TO :"role_api";
GRANT EXECUTE ON FUNCTION can_see(text), verify_chain(text), chain_digest(), event_canonical(task_events), event_hash(task_events)
  TO :"role_controller", :"role_api", :"role_readonly";

-- controller writes: functions only
GRANT EXECUTE ON FUNCTION
  upsert_project(text, text, text, text, text, text, jsonb),
  upsert_execution_target(text, text, text, text, text, text, text, boolean),
  acquire_task_lease(text, text, int), release_task_lease(text, text, bigint), acquire_lease(text, text, int),
  create_task(text, text, text, text, text[], text, text, int),
  register_contract(text, int, text, jsonb, int, text, bigint),
  add_dependency(text, text, text, text, bigint),
  record_event(text, text, int, int, text, bigint, jsonb, text, jsonb, text, jsonb),
  dispatch_job(text, int, text, int, text, bigint, text, text, text, bigint),
  update_job_phase(bigint, text, uuid, text, jsonb, text, bigint),
  job_heartbeat(bigint, uuid),
  register_artifact(text, text, text, bigint, text, text, text, bigint, text, text),
  expire_artifacts(int),
  enqueue_outbox(text, text, text, text, jsonb), claim_outbox(text, int, int), complete_outbox(bigint, text, text),
  fail_outbox(bigint, text, text, boolean, int),
  start_reconciliation(text, text, text), finish_reconciliation(bigint, text, jsonb, jsonb),
  create_checkpoint(text), record_checkpoint_export(bigint, text, text)
  TO :"role_controller";

-- api writes: authenticated operator facts only
GRANT EXECUTE ON FUNCTION record_operator_fact(text, text, jsonb, text, text, text, text, text, timestamptz, text, text) TO :"role_api";

INSERT INTO project_grants VALUES ('*', :'role_controller'::regrole), ('*', :'role_api'::regrole);

COMMIT;
RESET ROLE;
