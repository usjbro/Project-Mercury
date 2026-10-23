-- devplat PostgreSQL 16 schema — task state, append-only hash-chained events, Job runs, leases, admission,
-- budgets, test runs, artifacts and run uploads, authenticated operator facts, side-effect outbox, reconciliation.
--
-- Status: Proposed (Architecture Amendment 001, R6 fix round). Design: docs/mercury/development-orchestration/19-postgresql-state.md.
-- Development platform only; NOT a Mercury production schema (separation rule S1). Project-agnostic: no project,
-- role or v1 fact literal is seeded here (R6 A-04, D1, D6). Roles come from the platform role catalogue
-- (platform/agents/execution-profiles.yaml -> load_role_catalogue()); hard preconditions and enabled roles come
-- from each project's configuration (upsert_project()).
--
-- The task state machine is a PORT of devorch v2 (T_FULL, T_SHORT, GATE_OF, REQUIRED_BEFORE, LIMITS,
-- check_transition/apply, verify_subtask, contract_errors, result_errors, contract_dep_blockers). A vendored copy of
-- the Python tables, platform/db/devorch_v2_rules.json, is what platform/db/test_schema.py checks this file against.
--
-- Apply (R6 D9): roles.sql once per cluster (administrator), then this file as the migrator login, which is the
-- database owner and a member of the NOLOGIN owner role:
--   psql -U devplat_migrator [-v role_owner=... -v role_controller=... ...] -f schema.sql
-- The controller never runs migrations.

\set ON_ERROR_STOP on
\if :{?role_owner}
\else
\set role_owner devplat_owner
\endif
\if :{?role_migrator}
\else
\set role_migrator devplat_migrator
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
\if :{?role_model_gateway}
\else
\set role_model_gateway devplat_model_gateway
\endif
\if :{?role_artifact_gateway}
\else
\set role_artifact_gateway devplat_artifact_gateway
\endif

-- preconditions: roles.sql has run; the owner role cannot log in
SELECT format('DO $x$ BEGIN IF (SELECT rolcanlogin FROM pg_roles WHERE rolname = %L) IS DISTINCT FROM false THEN '
              'RAISE EXCEPTION ''owner role %s must exist and be NOLOGIN (run roles.sql)''; END IF; END $x$',
              :'role_owner', :'role_owner') \gexec
SELECT format('GRANT CREATE ON DATABASE %I TO %I', current_database(), :'role_owner') \gexec

SET ROLE :"role_owner";
BEGIN;
CREATE SCHEMA devplat;
SET LOCAL search_path = devplat, pg_catalog;
ALTER DEFAULT PRIVILEGES IN SCHEMA devplat REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- =====================================================================================================
-- 1. Platform rule tables (the ported devorch semantics; no project or role literals)
-- =====================================================================================================
CREATE TABLE lifecycles (lifecycle text PRIMARY KEY CHECK (lifecycle IN ('FULL', 'SHORT')));
INSERT INTO lifecycles VALUES ('FULL'), ('SHORT');

CREATE TABLE states (state text PRIMARY KEY);
INSERT INTO states VALUES ('NEW'), ('BLOCKED'), ('READY'), ('RUNNING'), ('AWAITING_REVIEW'),
  ('AWAITING_INTEGRATION'), ('AWAITING_HUMAN'), ('COMPLETED'), ('FAILED'), ('CANCELLED');

-- devorch FULL_KINDS / SHORT_KINDS / READ_ONLY_KINDS / REVIEW_GATE; subtask id suffixes (check-contract rule).
-- plan_proposal is the one devplat kind not in devorch (planner Jobs, doc 16 §10): SHORT, read-only, suffix p.
CREATE TABLE task_kinds (
  kind              text PRIMARY KEY,
  lifecycle         text NOT NULL REFERENCES lifecycles,
  read_only         boolean NOT NULL,
  needs_g4          boolean NOT NULL,          -- devorch needs_g4(): every FULL kind (TDD DoD D6)
  is_review         boolean NOT NULL,
  operator_evidence boolean NOT NULL,          -- completion needs an authenticated operator fact
  subtask_suffix    text CHECK (subtask_suffix IN ('r', 's', 'i', 'p'))
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
  ('plan_proposal',      'SHORT', true,  false, false, false, 'p'),
  ('mac_validation',     'SHORT', true,  false, false, true,  NULL),
  ('operator_action',    'SHORT', true,  false, false, true,  NULL);

-- (lifecycle, from_state, event) -> to_state, gate.  devorch T_FULL / T_SHORT / GATE_OF (gate only on FULL, or on
-- 'unblocked' in both lifecycles).  86 rows.  Review-gate targets are resolved in record_event() as in devorch.
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

-- devorch REQUIRED_BEFORE (FULL lifecycle, on a state change).
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

-- Evidence kinds of the handoff record plus 'operator_fact' (an authenticated operator_facts row) and 'job'.
-- is_file: the item must carry sha256 of an artifact registered for the task's project (verify_file_evidence).
CREATE TABLE evidence_kinds (kind text PRIMARY KEY, is_file boolean NOT NULL);
INSERT INTO evidence_kinds VALUES ('ci_run', true), ('commit', false), ('design_ref', false), ('github_merge', false),
  ('ledger', false), ('log', true), ('operator_statement', true), ('pr', false), ('result_file', true),
  ('review_file', true), ('subtask', false), ('test_run', true), ('operator_fact', false), ('job', false);

-- Fact statuses (devorch satisfied_facts()).
CREATE TABLE fact_statuses (status text PRIMARY KEY, satisfies boolean NOT NULL);
INSERT INTO fact_statuses VALUES ('verified', true), ('accepted', true), ('recorded', true), ('approved', true),
  ('revoked', false), ('failed', false), ('rejected', false);

-- Platform signals that may classify a failure as environmental (R6 D17, doc 21 §6). Nothing an agent reports.
CREATE TABLE env_signals (signal text PRIMARY KEY, source text NOT NULL CHECK (source IN ('model-gateway', 'kubernetes', 'gitbroker')));
INSERT INTO env_signals VALUES ('gateway_429', 'model-gateway'), ('gateway_5xx', 'model-gateway'),
  ('node_failure', 'kubernetes'), ('pod_eviction', 'kubernetes'), ('preemption', 'kubernetes'),
  ('image_pull_error', 'kubernetes'), ('fetch_failure', 'gitbroker');

CREATE TABLE job_phase_transitions (from_phase text NOT NULL, to_phase text NOT NULL, PRIMARY KEY (from_phase, to_phase));
INSERT INTO job_phase_transitions VALUES
  ('planned', 'created'), ('planned', 'failed'), ('planned', 'cancelled'),
  ('created', 'running'), ('created', 'succeeded'), ('created', 'failed'), ('created', 'lost'), ('created', 'cancelled'),
  ('running', 'succeeded'), ('running', 'failed'), ('running', 'lost'), ('running', 'cancelled'),
  ('lost', 'running'), ('lost', 'succeeded'), ('lost', 'failed'), ('lost', 'cancelled');

-- Side effects the platform may ever request. No merge / approve / ruleset operation exists.
CREATE TABLE outbox_operations (
  target    text NOT NULL,
  operation text NOT NULL,
  is_push   boolean NOT NULL,                  -- needs project 'active' + hard preconditions (R6 D4)
  PRIMARY KEY (target, operation)
);
INSERT INTO outbox_operations VALUES
  ('github', 'push_dev_branch', true), ('github', 'open_draft_pr', true), ('github', 'update_draft_pr_body', false),
  ('github', 'comment_pr', false), ('linear', 'comment_issue', false), ('linear', 'update_issue_state', false);

-- Evidence artifact kinds (sha256/<hex>): size limit and default retention (doc 20 §7).
CREATE TABLE artifact_kinds (
  kind                   text PRIMARY KEY,
  max_bytes              bigint NOT NULL CHECK (max_bytes > 0),
  default_retention_days int NOT NULL CHECK (default_retention_days > 0)
);
INSERT INTO artifact_kinds VALUES
  ('result', 1048576, 3650), ('result_bundle', 268435456, 365), ('log', 67108864, 90), ('test_report', 67108864, 365),
  ('evidence_manifest', 16777216, 3650), ('sbom', 67108864, 3650), ('scan_report', 67108864, 3650),
  ('checkpoint', 16777216, 3650), ('operator_upload', 268435456, 3650);

-- Per-run upload objects (runs/<job-uid>/<name>) and their caps (R6 D11; doc 20 §2). Total per run: 512 MiB.
CREATE TABLE run_object_caps (name text PRIMARY KEY, max_bytes bigint NOT NULL CHECK (max_bytes > 0));
INSERT INTO run_object_caps VALUES ('result.json', 1048576), ('result.bundle', 268435456),
  ('agent.stream.jsonl', 67108864), ('runner.json', 67108864), ('fetch.log', 67108864);

-- =====================================================================================================
-- 2. Role catalogue (platform), projects, execution targets, identities, visibility
-- =====================================================================================================
-- Loaded from platform/agents/execution-profiles.yaml by load_role_catalogue() (migrator, deploy time).
-- The `mdev-` prefix is historical and kept for compatibility (R6 D6).
CREATE TABLE role_catalogue_versions (
  version   text PRIMARY KEY,
  sha256    text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  loaded_at timestamptz NOT NULL DEFAULT now(),
  loaded_by text NOT NULL
);
CREATE TABLE roles (
  role                       text PRIMARY KEY CHECK (role ~ '^[a-z][a-z0-9-]{1,62}$'),
  kinds                      text[] NOT NULL,            -- devorch KIND_AGENT, as data
  llm                        boolean NOT NULL,
  network_class              text NOT NULL CHECK (network_class IN ('none', 'model-only', 'deps')),
  writes_allowed             boolean NOT NULL,
  max_concurrent_per_project int NOT NULL CHECK (max_concurrent_per_project >= 0),
  profile                    jsonb NOT NULL,
  catalogue_version          text NOT NULL REFERENCES role_catalogue_versions,
  retired                    boolean NOT NULL DEFAULT false
);

CREATE TABLE projects (
  project_id      text PRIMARY KEY CHECK (project_id ~ '^[a-z][a-z0-9-]{1,22}[a-z0-9]$'),   -- R6 D24
  display_name    text NOT NULL,
  github_repo     text CHECK (github_repo ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
  linear_team     text,
  config_version  text NOT NULL,                -- project config `config_version` (recorded on every event)
  registry_ref    text NOT NULL,                -- <path in project registry>@<commit>
  status          text NOT NULL CHECK (status IN ('draft', 'onboarding', 'active', 'paused', 'archived')),  -- R6 D4
  assurance_mode  text NOT NULL DEFAULT 'standard' CHECK (assurance_mode IN ('standard', 'reduced')),
  artifact_bucket text NOT NULL,
  cost_usd_per_day numeric(12, 4) CHECK (cost_usd_per_day >= 0),
  tokens_per_day   bigint CHECK (tokens_per_day >= 0),
  limits          jsonb NOT NULL DEFAULT '{}',  -- e.g. heartbeat_timeout_seconds
  linear_write_fact text CHECK (linear_write_fact ~ '^[A-Za-z0-9._:-]{1,64}$'),  -- config: fact enabling Linear writes; NULL = never
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (artifact_bucket = 'devplat-' || project_id)                                        -- R6 D11
);

-- Required operator-fact keys for G1 and dispatch of FULL-lifecycle work, from project config
-- review_gates.hard_preconditions (default [DOD-02, DOD-13] lives in the config schema, not here). R6 D1.
CREATE TABLE project_hard_preconditions (
  project_id text NOT NULL REFERENCES projects,
  fact_key   text NOT NULL CHECK (fact_key ~ '^[A-Za-z0-9._:-]{1,64}$'),
  PRIMARY KEY (project_id, fact_key)
);
-- Roles enabled by the project config, with the task kinds the project allows them (∩ catalogue kinds).
CREATE TABLE project_roles (
  project_id text NOT NULL REFERENCES projects,
  role       text NOT NULL REFERENCES roles,
  kinds      text[] NOT NULL,
  PRIMARY KEY (project_id, role)
);

-- Execution target = {cluster_ref, namespace_prefix}: Option C is a row change.
CREATE TABLE execution_targets (
  target_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id       text NOT NULL REFERENCES projects,
  name             text NOT NULL CHECK (name ~ '^[a-z][a-z0-9-]{0,30}$'),
  cluster_ref      text NOT NULL,
  namespace_prefix text NOT NULL CHECK (namespace_prefix ~ '^proj-[a-z0-9-]{1,40}$'),
  runtime_class    text NOT NULL DEFAULT 'gvisor',
  network_class    text NOT NULL DEFAULT 'none' CHECK (network_class IN ('none', 'model-only', 'deps')),  -- R6 D5
  assurance        text NOT NULL DEFAULT 'standard' CHECK (assurance IN ('standard', 'reduced')),
  enabled          boolean NOT NULL DEFAULT true,
  UNIQUE (project_id, name)
);

CREATE TABLE oidc_issuers (
  issuer             text PRIMARY KEY,
  audience           text NOT NULL,
  subject_deny_regex text NOT NULL DEFAULT '^(system:|devplat-|dp-)',  -- workload identities are never operators
  max_auth_age_s     int NOT NULL DEFAULT 900 CHECK (max_auth_age_s BETWEEN 60 AND 86400),
  enabled            boolean NOT NULL DEFAULT true
);
-- Allowed operator subjects (chart operatorIdentity.allowedSubjects, minItems 1). project_id NULL = all projects. R6 D2.
-- Platform invariant (R6 D1, re-check RS-5): fact keys every project's hard_preconditions must include. Set only
-- by the migration Job (set_mandatory_hard_preconditions); the controller cannot narrow a project's list below it.
CREATE TABLE mandatory_hard_preconditions (fact_key text PRIMARY KEY CHECK (fact_key ~ '^[A-Za-z0-9._:-]{1,64}$'));

CREATE TABLE operator_identities (
  issuer     text NOT NULL REFERENCES oidc_issuers,
  subject    text NOT NULL,
  project_id text REFERENCES projects,
  UNIQUE NULLS NOT DISTINCT (issuer, subject, project_id)
);

-- Row visibility: a role sees a project's rows if it is a member of a role granted that project ('*' = all).
CREATE TABLE project_grants (
  project_id text NOT NULL,
  role_oid   regrole NOT NULL,
  PRIMARY KEY (project_id, role_oid)
);
CREATE FUNCTION can_see(p_project_id text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM devplat.project_grants g
                  WHERE g.project_id IN (p_project_id, '*') AND pg_has_role(g.role_oid::oid, 'MEMBER') IS TRUE)
$$;

-- =====================================================================================================
-- 3. Tasks, contracts, contract-derived rows, events. Identity = (project_id, task_id) everywhere (R6 D3).
-- =====================================================================================================
CREATE TABLE tasks (
  project_id       text NOT NULL REFERENCES projects,
  task_id          text NOT NULL CHECK (task_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$'),
  kind             text NOT NULL REFERENCES task_kinds,
  lifecycle        text NOT NULL REFERENCES lifecycles,
  parent_task_id   text,
  covers_tasks     text[] NOT NULL DEFAULT '{}',
  external_ref     text,
  state            text NOT NULL DEFAULT 'NEW' REFERENCES states,
  contract_version int,
  core_sha256      text,
  attempt          int,
  gates            text[] NOT NULL DEFAULT '{}',
  counts           jsonb NOT NULL DEFAULT '{"attempt":0,"review":0,"security":0,"integration":0,"env":0}',
  head_commit      text,                        -- tested head (G2)
  impl_head        text,                        -- head of the last checked implementation_completed
  pr_head          text,                        -- G6 head
  frozen_files     jsonb NOT NULL DEFAULT '{}',
  need_bump        boolean NOT NULL DEFAULT false,
  revisions_since_reset int NOT NULL DEFAULT 0,  -- contract_revised count, max 3 until an operator reset (R6 D18)
  revision_reset_fact_id bigint,
  last_seq         int NOT NULL DEFAULT 0,
  last_hash        text NOT NULL DEFAULT 'GENESIS',
  lease_holder     text,
  lease_token      bigint NOT NULL DEFAULT 0,
  lease_expires_at timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, task_id),
  FOREIGN KEY (project_id, parent_task_id) REFERENCES tasks (project_id, task_id)
);
CREATE INDEX tasks_project_state ON tasks (project_id, state);

CREATE TABLE task_contracts (
  project_id       text NOT NULL,
  task_id          text NOT NULL,
  contract_version int NOT NULL CHECK (contract_version >= 1),
  core_sha256      text NOT NULL CHECK (core_sha256 ~ '^[0-9a-f]{64}$'),
  body             jsonb NOT NULL,
  max_attempts     int NOT NULL CHECK (max_attempts BETWEEN 1 AND 5),
  origin           text NOT NULL CHECK (origin IN ('controller', 'planner')),
  requires_approval boolean NOT NULL,          -- planner origin or a revision (R6 D18)
  registered_at    timestamptz NOT NULL DEFAULT now(),
  registered_by    text NOT NULL,
  PRIMARY KEY (project_id, task_id, contract_version),
  UNIQUE (project_id, task_id, core_sha256),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks
);

-- Contract-derived rows (filled by register_contract, immutable). devorch contract_dep_blockers / issue facts (R6 D7).
CREATE TABLE task_dependencies (
  project_id       text NOT NULL,
  task_id          text NOT NULL,
  contract_version int NOT NULL,
  depends_on       text NOT NULL,
  required_state   text NOT NULL CHECK (required_state IN ('COMPLETED', 'INTERFACE_FROZEN', 'AWAITING_HUMAN')),
  path             text,
  sha256           text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (project_id, task_id, contract_version, depends_on),
  FOREIGN KEY (project_id, task_id, contract_version) REFERENCES task_contracts,
  FOREIGN KEY (project_id, depends_on) REFERENCES tasks (project_id, task_id),
  CHECK (required_state <> 'INTERFACE_FROZEN' OR (path IS NOT NULL AND sha256 IS NOT NULL))
);
CREATE TABLE task_interface_contracts (
  project_id       text NOT NULL,
  task_id          text NOT NULL,
  contract_version int NOT NULL,
  path             text NOT NULL,
  sha256           text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  frozen_by        text NOT NULL,
  PRIMARY KEY (project_id, task_id, contract_version, path),
  FOREIGN KEY (project_id, task_id, contract_version) REFERENCES task_contracts
);
CREATE TABLE task_required_facts (
  project_id       text NOT NULL,
  task_id          text NOT NULL,
  contract_version int NOT NULL,
  fact_key         text NOT NULL CHECK (fact_key ~ '^[A-Za-z0-9._:-]{1,64}$'),   -- e.g. G-S1, P0-3
  PRIMARY KEY (project_id, task_id, contract_version, fact_key),
  FOREIGN KEY (project_id, task_id, contract_version) REFERENCES task_contracts
);

-- Append-only, hash-chained per task. Written ONLY by record_event().
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
  controller_id        text NOT NULL,
  on_behalf_of         text,                    -- '<issuer>#<subject>' when an operator_fact is cited
  contract_version     int NOT NULL,
  contract_core_sha256 text NOT NULL,
  attempt              int NOT NULL,
  head_commit          text,
  evidence             jsonb NOT NULL,
  payload              jsonb NOT NULL DEFAULT '{}',
  idempotency_key      text,
  lease_token          bigint NOT NULL,
  config_version       text NOT NULL,           -- project config version in force (R6 D8)
  assurance_mode       text NOT NULL CHECK (assurance_mode IN ('standard', 'reduced')),
  prev_hash            text NOT NULL,
  hash                 text NOT NULL CHECK (hash ~ '^[0-9a-f]{64}$'),
  PRIMARY KEY (project_id, task_id, seq),
  UNIQUE (project_id, task_id, idempotency_key),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks
);
CREATE INDEX task_events_project_at ON task_events (project_id, at);
CREATE INDEX task_events_evidence ON task_events USING gin (evidence jsonb_path_ops);

-- Canonical form for hashing: jsonb text of a fixed object (deterministic key order). Not devorch's Python
-- canonical JSON and not RFC 8785; v1 hashes are kept in payload.v1_hash on import.
CREATE FUNCTION event_canonical(e task_events) RETURNS text
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT jsonb_build_object(
    'schema', 'devplat.task_event.v2', 'project_id', e.project_id, 'task_id', e.task_id, 'seq', e.seq,
    'at', to_char(e.at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'event', e.event, 'from_state', e.from_state, 'to_state', e.to_state, 'gate', e.gate,
    'actor', e.actor, 'controller_id', e.controller_id, 'on_behalf_of', e.on_behalf_of,
    'contract_version', e.contract_version, 'contract_core_sha256', e.contract_core_sha256,
    'attempt', e.attempt, 'head_commit', e.head_commit, 'evidence', e.evidence, 'payload', e.payload,
    'idempotency_key', e.idempotency_key, 'lease_token', e.lease_token, 'config_version', e.config_version,
    'assurance_mode', e.assurance_mode, 'prev_hash', e.prev_hash)::text
$$;
CREATE FUNCTION event_hash(e task_events) RETURNS text
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT encode(sha256(convert_to(devplat.event_canonical(e), 'UTF8')), 'hex')
$$;

-- =====================================================================================================
-- 4. Admission, Job runs, uploads, test runs, budgets, leases
-- =====================================================================================================
CREATE TABLE admission_decisions (
  decision_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id    text NOT NULL,
  task_id       text NOT NULL,
  attempt       int NOT NULL,
  role          text NOT NULL,
  decision      text NOT NULL CHECK (decision IN ('admit', 'hold', 'reject')),
  reason        text NOT NULL CHECK (reason IN ('admitted', 'global_limit', 'project_limit', 'role_limit', 'budget',
                  'project_status', 'quota', 'dependency', 'operator_hold', 'image_unavailable', 'target_unavailable')),
  detail        jsonb NOT NULL DEFAULT '{}',
  controller_id text NOT NULL,
  lease_token   bigint NOT NULL,
  decided_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK ((decision = 'admit') = (reason = 'admitted')),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks
);

CREATE TABLE job_runs (
  job_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id        text NOT NULL,
  task_id           text NOT NULL,
  attempt           int NOT NULL CHECK (attempt BETWEEN 1 AND 50),
  role              text NOT NULL,              -- catalogue role, or 'verifier'
  dispatch_no       int NOT NULL DEFAULT 1 CHECK (dispatch_no >= 1),   -- env re-dispatch ordinal within an attempt
  admission_id      bigint NOT NULL UNIQUE REFERENCES admission_decisions,
  idempotency_key   text NOT NULL UNIQUE CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{16,128}$'),
  target_id         bigint REFERENCES execution_targets,
  k8s_namespace     text NOT NULL CHECK (k8s_namespace ~ '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'),
  k8s_job_name      text NOT NULL CHECK (k8s_job_name ~ '^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$'),
  k8s_job_uid       uuid UNIQUE,
  phase             text NOT NULL DEFAULT 'planned'
                    CHECK (phase IN ('planned', 'created', 'running', 'succeeded', 'failed', 'lost', 'cancelled')),
  failure_class     text CHECK (failure_class IN ('task', 'environmental', 'platform', 'budget', 'cancelled')),
  detail            jsonb NOT NULL DEFAULT '{}',
  lease_token       bigint NOT NULL,
  gateway_token_sha256 text UNIQUE CHECK (gateway_token_sha256 ~ '^[0-9a-f]{64}$'),   -- per-Job model-gateway token
  upload_token_sha256  text UNIQUE CHECK (upload_token_sha256 ~ '^[0-9a-f]{64}$'),    -- per-Job artifact-gateway token
  tokens_expire_at  timestamptz,                -- Job deadline + 15 min (R6 D11)
  created_at        timestamptz NOT NULL DEFAULT now(),
  started_at        timestamptz,
  finished_at       timestamptz,
  last_heartbeat_at timestamptz,
  heartbeat_count   int NOT NULL DEFAULT 0,
  UNIQUE (k8s_namespace, k8s_job_name),
  UNIQUE (project_id, task_id, attempt, role, dispatch_no),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks
);
CREATE INDEX job_runs_active ON job_runs (phase) WHERE phase IN ('planned', 'created', 'running', 'lost');

-- Objects uploaded by a run through devplat-artifact-gateway (R6 D10/D11): one-time per name, capped.
CREATE TABLE run_uploads (
  job_id        bigint NOT NULL REFERENCES job_runs,
  name          text NOT NULL REFERENCES run_object_caps,
  declared_size bigint NOT NULL CHECK (declared_size >= 0),
  sha256        text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes    bigint,
  status        text NOT NULL DEFAULT 'authorized' CHECK (status IN ('authorized', 'stored')),
  authorized_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  stored_at     timestamptz,
  PRIMARY KEY (job_id, name)
);

-- Verifier results (the controller's own G2 re-run, R6 D8).
CREATE TABLE test_runs (
  test_run_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id      text NOT NULL,
  task_id         text NOT NULL,
  attempt         int NOT NULL,
  head_commit     text NOT NULL CHECK (head_commit ~ '^[0-9a-f]{40}$'),
  test_id         text NOT NULL,
  job_id          bigint NOT NULL REFERENCES job_runs,
  outcome         text NOT NULL CHECK (outcome IN ('passed', 'failed', 'error', 'skipped')),
  exit_code       int NOT NULL,
  artifact_sha256 text CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$'),
  recorded_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks
);

-- Atomic per-project, per-day budgets (R6 D8). Reservations are never refunded across attempts or env retries (D17).
CREATE TABLE budget_days (
  project_id      text NOT NULL REFERENCES projects,
  day             date NOT NULL,
  cost_limit_usd  numeric(12, 4) NOT NULL,
  tokens_limit    bigint,
  reserved_usd    numeric(12, 4) NOT NULL DEFAULT 0,
  settled_usd     numeric(12, 4) NOT NULL DEFAULT 0,
  reserved_tokens bigint NOT NULL DEFAULT 0,
  settled_tokens  bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (project_id, day)
);
CREATE TABLE budget_reservations (
  reservation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id     text NOT NULL,
  task_id        text NOT NULL,
  job_id         bigint NOT NULL REFERENCES job_runs,
  day            date NOT NULL,
  request_id     text NOT NULL,
  est_usd        numeric(12, 4) NOT NULL CHECK (est_usd >= 0),
  est_tokens     bigint NOT NULL CHECK (est_tokens >= 0),
  actual_usd     numeric(12, 4),
  actual_tokens  bigint,
  status         text NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'settled', 'released')),
  created_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  settled_at     timestamptz,
  UNIQUE (job_id, request_id),
  FOREIGN KEY (project_id, day) REFERENCES budget_days
);

-- Named non-task leases (controller-leader mirror, outbox dispatcher, reconcilers). The authoritative leader
-- election is the Kubernetes Lease; 'controller-leader' here is taken by the winner to fence-transfer task leases.
CREATE TABLE leases (
  resource    text PRIMARY KEY,
  holder      text NOT NULL,
  token       bigint NOT NULL,
  acquired_at timestamptz NOT NULL,
  expires_at  timestamptz NOT NULL
);

-- =====================================================================================================
-- 5. Artifacts, operator facts, outbox, reconciliation, checkpoints
-- =====================================================================================================
CREATE TABLE artifacts (
  artifact_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id      text NOT NULL REFERENCES projects,
  sha256          text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  bucket          text NOT NULL,
  object_key      text NOT NULL,
  alias_key       text CHECK (alias_key ~ '^manifests/[A-Za-z0-9._-]+/[0-9]+/[0-9]+\.json$'),
  size_bytes      bigint NOT NULL CHECK (size_bytes >= 0),
  media_type      text NOT NULL,
  kind            text NOT NULL REFERENCES artifact_kinds,
  task_id         text,
  job_id          bigint REFERENCES job_runs,
  gate            text CHECK (gate ~ '^G[1-7]$'),
  retention_class text NOT NULL CHECK (retention_class IN ('ephemeral', 'standard', 'evidence')),
  retain_until    timestamptz NOT NULL,
  legal_hold      boolean NOT NULL DEFAULT false,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (project_id, sha256),
  CONSTRAINT artifacts_object_key_check CHECK (object_key = 'sha256/' || sha256),   -- content addressed (doc 20 §2)
  CONSTRAINT artifacts_bucket_check CHECK (bucket = 'devplat-' || project_id),
  CONSTRAINT artifacts_alias_check CHECK (alias_key IS NULL OR kind = 'evidence_manifest'),
  FOREIGN KEY (project_id, task_id) REFERENCES tasks
);

-- Authenticated human statements. Append-only; a revocation is a newer fact with the same key.
-- Written ONLY by record_operator_fact() (devplat_api) for an allowed operator identity (R6 D2).
CREATE TABLE operator_facts (
  fact_id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  project_id      text REFERENCES projects,     -- NULL = platform-wide; never satisfies a project precondition (D1)
  fact_key        text NOT NULL CHECK (fact_key ~ '^[A-Za-z0-9._:-]{1,64}$'),
  status          text NOT NULL REFERENCES fact_statuses,
  value           jsonb NOT NULL,
  task_id         text,
  statement       text,
  evidence_sha256 text CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
  subject         text NOT NULL,
  issuer          text NOT NULL REFERENCES oidc_issuers,
  email           text,
  auth_time       timestamptz NOT NULL,
  token_jti       text NOT NULL UNIQUE,
  recorded_at     timestamptz NOT NULL DEFAULT now(),
  recorded_via    text NOT NULL,
  FOREIGN KEY (project_id, task_id) REFERENCES tasks,
  CHECK (task_id IS NULL OR project_id IS NOT NULL)
);
CREATE INDEX operator_facts_key ON operator_facts (project_id, fact_key, fact_id DESC);

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
  external_ref     text,
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
  signature_ref   text NOT NULL,
  exported_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (checkpoint_id, artifact_sha256)
);

-- =====================================================================================================
-- 6. Immutability triggers
-- =====================================================================================================
CREATE FUNCTION forbid_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  RAISE EXCEPTION USING ERRCODE = 'DP003',
    MESSAGE = format('refused: %s is append-only (%s forbidden)', TG_TABLE_NAME, TG_OP);
END $$;

DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['task_events', 'task_contracts', 'task_dependencies', 'task_interface_contracts',
                           'task_required_facts', 'operator_facts', 'chain_checkpoints', 'checkpoint_exports',
                           'admission_decisions', 'test_runs'] LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON devplat.%I FOR EACH ROW EXECUTE FUNCTION devplat.forbid_mutation()', r || '_append_only', r);
    EXECUTE format('CREATE TRIGGER %I BEFORE TRUNCATE ON devplat.%I FOR EACH STATEMENT EXECUTE FUNCTION devplat.forbid_mutation()', r || '_no_truncate', r);
  END LOOP;
END $$;
CREATE TRIGGER tasks_no_delete BEFORE DELETE ON tasks FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER tasks_no_truncate BEFORE TRUNCATE ON tasks FOR EACH STATEMENT EXECUTE FUNCTION forbid_mutation();

-- State columns of tasks change only inside record_event() (defence in depth against owner-level bugs).
CREATE FUNCTION guard_task_state() RETURNS trigger
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  IF coalesce(current_setting('devplat.writer', true), '') <> 'record_event' AND
     (NEW.task_id, NEW.project_id, NEW.kind, NEW.lifecycle, NEW.parent_task_id, NEW.covers_tasks, NEW.state,
      NEW.contract_version, NEW.core_sha256, NEW.attempt, NEW.gates, NEW.counts, NEW.head_commit, NEW.impl_head,
      NEW.pr_head, NEW.frozen_files, NEW.need_bump, NEW.revisions_since_reset, NEW.revision_reset_fact_id,
      NEW.last_seq, NEW.last_hash)
     IS DISTINCT FROM
     (OLD.task_id, OLD.project_id, OLD.kind, OLD.lifecycle, OLD.parent_task_id, OLD.covers_tasks, OLD.state,
      OLD.contract_version, OLD.core_sha256, OLD.attempt, OLD.gates, OLD.counts, OLD.head_commit, OLD.impl_head,
      OLD.pr_head, OLD.frozen_files, OLD.need_bump, OLD.revisions_since_reset, OLD.revision_reset_fact_id,
      OLD.last_seq, OLD.last_hash) THEN
    RAISE EXCEPTION USING ERRCODE = 'DP003', MESSAGE = 'refused: task state changes only through record_event()';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END $$;
CREATE TRIGGER tasks_guard_state BEFORE UPDATE ON tasks FOR EACH ROW EXECUTE FUNCTION guard_task_state();

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
-- 7. Internal helpers (not granted)
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
    PERFORM devplat._refuse(format('stale or missing task lease for %s/%s (presented %s/%s, current %s/%s until %s)',
      t.project_id, t.task_id, p_holder, p_token, t.lease_holder, t.lease_token, t.lease_expires_at), 'DP002');
  END IF;
END $$;

-- Latest PROJECT-SCOPED fact for (project, key) decides; a platform-wide fact never satisfies (R6 D1).
CREATE FUNCTION _fact_satisfied(p_project_id text, p_key text) RETURNS boolean
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT coalesce((SELECT fs.satisfies FROM devplat.operator_facts f JOIN devplat.fact_statuses fs ON fs.status = f.status
                    WHERE f.project_id = p_project_id AND f.fact_key = p_key AND f.task_id IS NULL
                    ORDER BY f.fact_id DESC LIMIT 1), false)
$$;

CREATE FUNCTION _missing_hard_preconditions(p_project_id text) RETURNS text[]
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT coalesce(array_agg(h.fact_key ORDER BY h.fact_key), '{}') FROM devplat.project_hard_preconditions h
   WHERE h.project_id = p_project_id AND NOT devplat._fact_satisfied(p_project_id, h.fact_key)
$$;

-- R6 D4: may work of this kind be dispatched (or pushed) in this project now?
CREATE FUNCTION _check_dispatchable(p_project_id text, p_kind text, p_what text) RETURNS void
LANGUAGE plpgsql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE v_status text; k task_kinds%ROWTYPE; v_missing text[];
BEGIN
  SELECT status INTO v_status FROM projects WHERE project_id = p_project_id;
  SELECT * INTO k FROM task_kinds WHERE kind = p_kind;
  IF v_status = 'active' THEN
    IF k.lifecycle = 'FULL' OR p_what = 'push' THEN
      v_missing := _missing_hard_preconditions(p_project_id);
      IF cardinality(v_missing) > 0 THEN
        PERFORM _refuse(format('%s refused: hard preconditions %s are not satisfied project facts of %s', p_what, v_missing, p_project_id));
      END IF;
    END IF;
  ELSIF v_status = 'onboarding' AND p_what <> 'push' AND k.lifecycle = 'SHORT' AND k.read_only THEN
    NULL;   -- planning, *_review, operator_action, mac_validation
  ELSE
    PERFORM _refuse(format('%s of kind %s refused: project %s is %s', p_what, p_kind, p_project_id, v_status));
  END IF;
END $$;

-- git-like globs (devorch glob_re): '**/' = zero or more directories, '**' anything, '*' and '?' never match '/'.
CREATE FUNCTION glob_regex(p text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE i int := 1; n int := length(p); o text := ''; ch text;
BEGIN
  WHILE i <= n LOOP
    IF substr(p, i, 3) = '**/' THEN o := o || '(?:.*/)?'; i := i + 3;
    ELSIF substr(p, i, 2) = '**' THEN o := o || '.*'; i := i + 2;
    ELSE
      ch := substr(p, i, 1);
      IF ch = '*' THEN o := o || '[^/]*';
      ELSIF ch = '?' THEN o := o || '[^/]';
      ELSIF ch ~ '^[A-Za-z0-9_/]$' THEN o := o || ch;
      ELSE o := o || '\' || ch;
      END IF;
      i := i + 1;
    END IF;
  END LOOP;
  RETURN '^' || o || '$';
END $$;
CREATE FUNCTION _matches(p_path text, p_patterns text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM unnest(coalesce(p_patterns, '{}')) g WHERE p_path ~ devplat.glob_regex(g))
$$;
-- devorch overlap(): conservative literal-prefix test
CREATE FUNCTION _overlap(a text[], b text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT EXISTS (SELECT 1 FROM unnest(a) x, unnest(b) y,
                  LATERAL (SELECT substring(x FROM '^[^*?\[]*') AS px, substring(y FROM '^[^*?\[]*') AS py) l
                  WHERE starts_with(l.px, l.py) OR starts_with(l.py, l.px))
$$;
CREATE FUNCTION _jtext(j jsonb) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$ SELECT coalesce(ARRAY(SELECT jsonb_array_elements_text(coalesce(j, '[]'))), '{}') $$;

-- devorch active_primary_paths(): writing primary tasks that currently own paths.
CREATE FUNCTION _ownership_conflict(p_project_id text, p_task_id text, p_allowed text[]) RETURNS text
LANGUAGE sql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
  SELECT min(t.task_id) FROM devplat.tasks t
    JOIN devplat.task_kinds k ON k.kind = t.kind
    JOIN devplat.task_contracts c ON c.project_id = t.project_id AND c.task_id = t.task_id AND c.contract_version = t.contract_version
   WHERE t.project_id = p_project_id AND t.task_id <> p_task_id AND NOT k.read_only AND t.parent_task_id IS NULL
     AND t.state IN ('RUNNING', 'AWAITING_REVIEW', 'AWAITING_INTEGRATION', 'AWAITING_HUMAN')
     AND cardinality(p_allowed) > 0 AND devplat._overlap(p_allowed, devplat._jtext(c.body->'allowed_paths'))
$$;

CREATE FUNCTION _enqueue_outbox(p_project_id text, p_target text, p_operation text, p_dedup_key text,
                                p_payload jsonb, p_task_id text, p_seq int)
RETURNS TABLE (r_outbox_id bigint, r_created boolean)
LANGUAGE plpgsql SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE v_id bigint; v_old outbox%ROWTYPE; op outbox_operations%ROWTYPE;
BEGIN
  SELECT * INTO op FROM outbox_operations o WHERE o.target = p_target AND o.operation = p_operation;
  IF NOT FOUND THEN
    PERFORM _refuse(format('side effect %s.%s is not an allowed outbox operation', p_target, p_operation));
  END IF;
  IF op.is_push THEN PERFORM _check_dispatchable(p_project_id, 'implementation', 'push'); END IF;
  IF p_target = 'linear' AND NOT coalesce((SELECT _fact_satisfied(p_project_id, pj.linear_write_fact) FROM projects pj
                                             WHERE pj.project_id = p_project_id AND pj.linear_write_fact IS NOT NULL), false) THEN
    PERFORM _refuse('Linear writes are not enabled for this project (configured write fact missing or not satisfied)');
  END IF;
  INSERT INTO outbox (project_id, target, operation, dedup_key, payload, source_task_id, source_seq)
  VALUES (p_project_id, p_target, p_operation, p_dedup_key, coalesce(p_payload, '{}'), p_task_id, p_seq)
  ON CONFLICT (dedup_key) DO NOTHING RETURNING outbox_id INTO v_id;
  IF v_id IS NOT NULL THEN RETURN QUERY SELECT v_id, true; RETURN; END IF;
  SELECT * INTO v_old FROM outbox o WHERE o.dedup_key = p_dedup_key;
  IF v_old.project_id <> p_project_id OR v_old.target <> p_target OR v_old.operation <> p_operation THEN
    PERFORM _refuse('dedup key reused for a different side effect');
  END IF;
  RETURN QUERY SELECT v_old.outbox_id, false;
END $$;

-- devorch result_errors() checks that can be decided from the controller-validated summary (R6 D7, A-03).
-- r = payload.result (fields of devorch.task_result.v1 / devplat.task_result.v2).
CREATE FUNCTION _result_errors(t tasks, c task_contracts, k task_kinds, r jsonb, p_event text, p_attempt int, p_head text)
RETURNS text LANGUAGE plpgsql STABLE SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE v_req text[]; v_rep jsonb; v_bad text[]; v_id text; v_accept boolean;
BEGIN
  IF jsonb_typeof(r) IS DISTINCT FROM 'object' THEN RETURN 'needs payload.result (the controller-validated result)'; END IF;
  IF r->>'task_id' IS DISTINCT FROM t.task_id OR (r->>'contract_version')::int IS DISTINCT FROM c.contract_version
     OR (r->>'attempt')::int IS DISTINCT FROM p_attempt THEN
    RETURN 'result task_id/contract_version/attempt do not match the contract';
  END IF;
  IF c.body ? 'assigned_agent' AND r->>'agent' IS DISTINCT FROM c.body->>'assigned_agent' THEN
    RETURN 'result agent is not the assigned agent';
  END IF;
  IF r->>'status' IS DISTINCT FROM 'completed' THEN RETURN format('result status is %s, not completed', r->>'status'); END IF;
  IF p_event = 'implementation_completed' AND r->>'head_commit' IS DISTINCT FROM p_head THEN
    RETURN 'head_commit must equal the result''s head_commit';
  END IF;
  v_accept := coalesce(r->>'recommendation', '') IN ('accept', 'accept_with_conditions');
  IF k.is_review THEN
    IF r->>'reviewed_head_commit' IS DISTINCT FROM c.body->'review_target'->>'head_commit' THEN
      RETURN 'reviewed_head_commit must equal review_target.head_commit';
    END IF;
    IF NOT r ? 'recommendation' THEN RETURN 'review result needs a recommendation'; END IF;
    IF v_accept AND jsonb_path_exists(r, '$.findings[*] ? (@.blocking == true)') THEN
      RETURN 'recommendation accept with blocking findings';
    END IF;
  END IF;
  v_req := ARRAY(SELECT x->>'id' FROM jsonb_array_elements(coalesce(c.body->'required_tests', '[]')) x);
  v_rep := coalesce((SELECT jsonb_object_agg(x->>'id', x) FROM jsonb_array_elements(coalesce(r->'tests', '[]')) x), '{}');
  IF k.is_review THEN
    v_bad := ARRAY(SELECT i FROM unnest(v_req) i WHERE NOT v_rep ? i);
    IF cardinality(v_bad) > 0 THEN RETURN format('review must report an outcome for every required test: %s', v_bad); END IF;
    IF v_accept THEN
      v_bad := ARRAY(SELECT i FROM unnest(v_req) i WHERE v_rep->i->>'outcome' <> 'passed' OR (v_rep->i->>'exit_code')::int <> 0);
      IF cardinality(v_bad) > 0 THEN RETURN format('accept with failing required tests: %s', v_bad); END IF;
    END IF;
  ELSIF t.kind NOT IN ('mac_validation', 'operator_action', 'planning') THEN
    v_bad := ARRAY(SELECT i FROM unnest(v_req) i WHERE NOT v_rep ? i OR v_rep->i->>'outcome' IS DISTINCT FROM 'passed'
                                                    OR (v_rep->i->>'exit_code')::int IS DISTINCT FROM 0);
    IF cardinality(v_bad) > 0 THEN RETURN format('required tests not passed: %s', v_bad); END IF;
  END IF;
  IF t.kind = 'integration' AND (r->>'recommendation' IS NULL OR jsonb_typeof(r->'integrated_heads') IS DISTINCT FROM 'array') THEN
    RETURN 'integration result needs recommendation and integrated_heads';
  END IF;
  RETURN NULL;
END $$;

-- =====================================================================================================
-- 8. Migrator API (deploy time): role catalogue and operator identities
-- =====================================================================================================
-- p_profiles = the `profiles` array of execution-profiles.yaml as JSON.
CREATE FUNCTION load_role_catalogue(p_version text, p_sha256 text, p_profiles jsonb)
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE p jsonb; n int := 0; v_reviews int;
BEGIN
  IF EXISTS (SELECT 1 FROM role_catalogue_versions WHERE version = p_version) THEN
    IF (SELECT sha256 FROM role_catalogue_versions WHERE version = p_version) = p_sha256 THEN RETURN 0; END IF;
    PERFORM _refuse('catalogue version already loaded with different content');
  END IF;
  INSERT INTO role_catalogue_versions (version, sha256, loaded_by) VALUES (p_version, p_sha256, session_user);
  UPDATE roles SET retired = true WHERE role NOT IN (SELECT x->>'role' FROM jsonb_array_elements(p_profiles) x);
  FOR p IN SELECT x FROM jsonb_array_elements(p_profiles) x LOOP
    SELECT count(*) INTO v_reviews FROM jsonb_array_elements_text(p->'kinds') kk JOIN task_kinds tk ON tk.kind = kk WHERE tk.is_review;
    IF v_reviews > 1 THEN PERFORM _refuse(format('role %s provides more than one review kind', p->>'role')); END IF;
    INSERT INTO roles (role, kinds, llm, network_class, writes_allowed, max_concurrent_per_project, profile, catalogue_version)
    VALUES (p->>'role', _jtext(p->'kinds'), (p->>'llm')::boolean, p->>'network_class', (p->>'writes_allowed')::boolean,
            (p->>'max_concurrent_per_project')::int, p, p_version)
    ON CONFLICT (role) DO UPDATE SET kinds = EXCLUDED.kinds, llm = EXCLUDED.llm, network_class = EXCLUDED.network_class,
      writes_allowed = EXCLUDED.writes_allowed, max_concurrent_per_project = EXCLUDED.max_concurrent_per_project,
      profile = EXCLUDED.profile, catalogue_version = EXCLUDED.catalogue_version, retired = false;
    n := n + 1;
  END LOOP;
  RETURN n;
END $$;

-- Replaces the allowed operator subjects with the chart's list (minItems 1, R6 D2).
CREATE FUNCTION set_operator_identities(p_issuer text, p_audience text, p_identities jsonb)
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE n int;
BEGIN
  IF jsonb_typeof(p_identities) IS DISTINCT FROM 'array' OR jsonb_array_length(p_identities) < 1 THEN
    PERFORM _refuse('at least one allowed operator subject is required');
  END IF;
  INSERT INTO oidc_issuers (issuer, audience) VALUES (p_issuer, p_audience)
  ON CONFLICT (issuer) DO UPDATE SET audience = EXCLUDED.audience, enabled = true;
  DELETE FROM operator_identities WHERE issuer = p_issuer;
  INSERT INTO operator_identities (issuer, subject, project_id)
  SELECT p_issuer, x->>'subject', x->>'project_id' FROM jsonb_array_elements(p_identities) x;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

CREATE FUNCTION set_mandatory_hard_preconditions(p_keys text[]) RETURNS int
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  IF coalesce(cardinality(p_keys), 0) < 1 THEN PERFORM _refuse('at least one mandatory hard precondition is required'); END IF;
  DELETE FROM mandatory_hard_preconditions;
  INSERT INTO mandatory_hard_preconditions SELECT DISTINCT x FROM unnest(p_keys) x;
  RETURN (SELECT count(*) FROM mandatory_hard_preconditions);
END $$;

-- =====================================================================================================
-- 9. Controller API (SECURITY DEFINER; EXECUTE granted to the controller role only)
-- =====================================================================================================
-- From the project registry. p_roles: {"<role>": ["<kind>", ...]} for ENABLED roles only.
CREATE FUNCTION upsert_project(p_project_id text, p_display_name text, p_github_repo text, p_linear_team text,
                               p_config_version text, p_registry_ref text, p_status text, p_assurance_mode text,
                               p_hard_preconditions text[], p_roles jsonb, p_cost_usd_per_day numeric,
                               p_tokens_per_day bigint, p_limits jsonb DEFAULT '{}', p_linear_write_fact text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE v_role text; v_missing text[];
BEGIN
  IF coalesce(cardinality(p_hard_preconditions), 0) < 1 THEN
    PERFORM _refuse('review_gates.hard_preconditions must list at least one fact key');
  END IF;
  -- R6 re-check RS-5: the controller supplies the list, so the platform's mandatory keys are enforced here
  IF NOT EXISTS (SELECT 1 FROM mandatory_hard_preconditions) THEN
    PERFORM _refuse('mandatory hard preconditions are not set (migration Job: set_mandatory_hard_preconditions)');
  END IF;
  v_missing := ARRAY(SELECT m.fact_key FROM mandatory_hard_preconditions m WHERE m.fact_key <> ALL (p_hard_preconditions)
                     ORDER BY m.fact_key);
  IF cardinality(v_missing) > 0 THEN
    PERFORM _refuse(format('review_gates.hard_preconditions must include the platform''s mandatory keys %s', v_missing));
  END IF;
  IF p_linear_write_fact = ANY (p_hard_preconditions) OR p_linear_write_fact = 'REDUCED-ASSURANCE'
     OR p_linear_write_fact IN (SELECT fact_key FROM mandatory_hard_preconditions) THEN
    PERFORM _refuse(format('linear_write_fact %s is a hard precondition or reserved key; Linear writes need their own fact', p_linear_write_fact));
  END IF;
  INSERT INTO projects (project_id, display_name, github_repo, linear_team, config_version, registry_ref, status,
                        artifact_bucket, cost_usd_per_day, tokens_per_day, limits, linear_write_fact)
  VALUES (p_project_id, p_display_name, p_github_repo, p_linear_team, p_config_version, p_registry_ref, 'draft',
          'devplat-' || p_project_id, p_cost_usd_per_day, p_tokens_per_day, coalesce(p_limits, '{}'), p_linear_write_fact)
  ON CONFLICT (project_id) DO UPDATE SET display_name = EXCLUDED.display_name, github_repo = EXCLUDED.github_repo,
    linear_team = EXCLUDED.linear_team, config_version = EXCLUDED.config_version, registry_ref = EXCLUDED.registry_ref,
    cost_usd_per_day = EXCLUDED.cost_usd_per_day, tokens_per_day = EXCLUDED.tokens_per_day, limits = EXCLUDED.limits,
    linear_write_fact = EXCLUDED.linear_write_fact, updated_at = now();
  DELETE FROM project_hard_preconditions WHERE project_id = p_project_id;
  INSERT INTO project_hard_preconditions SELECT p_project_id, x FROM unnest(p_hard_preconditions) x;
  DELETE FROM project_roles WHERE project_id = p_project_id;
  FOR v_role IN SELECT jsonb_object_keys(coalesce(p_roles, '{}')) LOOP
    IF NOT EXISTS (SELECT 1 FROM roles WHERE role = v_role AND NOT retired) THEN
      PERFORM _refuse(format('role %s is not in the platform role catalogue', v_role));
    END IF;
    INSERT INTO project_roles VALUES (p_project_id, v_role,
      ARRAY(SELECT x FROM jsonb_array_elements_text(p_roles->v_role) x
             WHERE x = ANY ((SELECT r.kinds FROM roles r WHERE r.role = v_role)::text[])));
  END LOOP;
  -- status and assurance (R6 D4, D16)
  IF p_status = 'active' THEN
    v_missing := _missing_hard_preconditions(p_project_id);
    IF cardinality(v_missing) > 0 THEN PERFORM _refuse(format('project cannot be active: hard preconditions %s not satisfied', v_missing)); END IF;
    IF p_cost_usd_per_day IS NULL THEN PERFORM _refuse('project cannot be active without budgets.cost_usd_per_day'); END IF;
  END IF;
  IF p_assurance_mode = 'reduced' AND NOT _fact_satisfied(p_project_id, 'REDUCED-ASSURANCE') THEN
    PERFORM _refuse('reduced assurance needs the project fact REDUCED-ASSURANCE');
  END IF;
  UPDATE projects SET status = p_status, assurance_mode = p_assurance_mode WHERE project_id = p_project_id;
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

-- Task lease: fencing token, or NULL if another holder's lease is unexpired. Same holder renews (same token);
-- takeover after expiry increments the token.
CREATE FUNCTION acquire_task_lease(p_project_id text, p_task_id text, p_holder text, p_ttl_seconds int)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE; v_token bigint;
BEGIN
  IF p_ttl_seconds NOT BETWEEN 1 AND 3600 THEN PERFORM _refuse('lease ttl must be 1..3600 s'); END IF;
  SELECT * INTO t FROM tasks WHERE project_id = p_project_id AND task_id = p_task_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s/%s', p_project_id, p_task_id)); END IF;
  IF t.lease_holder = p_holder AND t.lease_expires_at > clock_timestamp() THEN
    UPDATE tasks SET lease_expires_at = clock_timestamp() + make_interval(secs => p_ttl_seconds)
     WHERE project_id = p_project_id AND task_id = p_task_id;
    RETURN t.lease_token;
  END IF;
  IF t.lease_holder IS NOT NULL AND t.lease_expires_at > clock_timestamp() THEN RETURN NULL; END IF;
  UPDATE tasks SET lease_holder = p_holder, lease_token = t.lease_token + 1,
                   lease_expires_at = clock_timestamp() + make_interval(secs => p_ttl_seconds)
   WHERE project_id = p_project_id AND task_id = p_task_id RETURNING lease_token INTO v_token;
  RETURN v_token;
END $$;

CREATE FUNCTION release_task_lease(p_project_id text, p_task_id text, p_holder text, p_token bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  UPDATE tasks SET lease_holder = NULL, lease_expires_at = NULL
   WHERE project_id = p_project_id AND task_id = p_task_id AND lease_holder = p_holder AND lease_token = p_token;
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

-- R6 D22: a newly elected leader (holding the 'controller-leader' DB lease) takes every task lease held by
-- another holder at once (token + 1) instead of waiting for TTL expiry. Returns the number transferred.
CREATE FUNCTION fence_transfer_task_leases(p_holder text, p_leader_token bigint, p_ttl_seconds int)
RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE n int;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM leases WHERE resource = 'controller-leader' AND holder = p_holder
                   AND token = p_leader_token AND expires_at > clock_timestamp()) THEN
    PERFORM _refuse('fence transfer needs the current controller-leader lease', 'DP002');
  END IF;
  UPDATE tasks SET lease_holder = p_holder, lease_token = lease_token + 1,
                   lease_expires_at = clock_timestamp() + make_interval(secs => p_ttl_seconds)
   WHERE lease_holder IS NOT NULL AND lease_holder <> p_holder;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- Create a task (NEW) with the caller's first lease. devorch subtask id convention: reviews <parent>-rN,
-- security reviews <parent>-sN, integration <first covers_tasks entry>-iN, plan proposals <parent>-pN (task-bound)
-- or PL-<nnnn> (project-level, no parent; doc 16 §10). Projects in onboarding or active (R6 D4).
CREATE FUNCTION create_task(p_project_id text, p_task_id text, p_kind text, p_parent_task_id text,
                            p_covers_tasks text[], p_external_ref text, p_holder text, p_ttl_seconds int)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE k task_kinds%ROWTYPE; p tasks%ROWTYPE; v_old tasks%ROWTYPE; v_cov text; v_status text;
BEGIN
  SELECT * INTO k FROM task_kinds WHERE kind = p_kind;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown kind %s', p_kind)); END IF;
  SELECT status INTO v_status FROM projects WHERE project_id = p_project_id;
  IF v_status IS NULL OR v_status NOT IN ('onboarding', 'active') THEN
    PERFORM _refuse(format('project %s is %s: tasks are created only in onboarding or active', p_project_id, coalesce(v_status, 'unknown')));
  END IF;
  IF k.subtask_suffix IN ('r', 's') THEN
    SELECT * INTO p FROM tasks WHERE project_id = p_project_id AND task_id = p_parent_task_id;
    IF NOT FOUND OR p.lifecycle <> 'FULL' THEN
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
      IF NOT EXISTS (SELECT 1 FROM tasks WHERE project_id = p_project_id AND task_id = v_cov) THEN
        PERFORM _refuse(format('covered task %s not found in project', v_cov));
      END IF;
    END LOOP;
    IF p_task_id !~ ('^' || regexp_replace(p_covers_tasks[1], '([.\-])', '\\\1', 'g') || '-i[0-9]+$') THEN
      PERFORM _refuse(format('integration id must be %s-iN', p_covers_tasks[1]));
    END IF;
  ELSIF k.subtask_suffix = 'p' THEN
    IF coalesce(cardinality(p_covers_tasks), 0) > 0 THEN PERFORM _refuse('a plan proposal has no covers_tasks'); END IF;
    IF p_parent_task_id IS NULL THEN
      IF p_task_id !~ '^PL-[0-9]{4,}$' THEN PERFORM _refuse('a project-level plan proposal id must be PL-<nnnn>'); END IF;
    ELSE
      IF NOT EXISTS (SELECT 1 FROM tasks WHERE project_id = p_project_id AND task_id = p_parent_task_id) THEN
        PERFORM _refuse('a task-bound plan proposal needs a parent in the same project');
      END IF;
      IF p_task_id !~ ('^' || regexp_replace(p_parent_task_id, '([.\-])', '\\\1', 'g') || '-p[0-9]+$') THEN
        PERFORM _refuse(format('plan proposal id must be %s-pN', p_parent_task_id));
      END IF;
    END IF;
  ELSIF p_parent_task_id IS NOT NULL OR coalesce(cardinality(p_covers_tasks), 0) > 0 THEN
    PERFORM _refuse('only subtasks have a parent or covers_tasks');
  END IF;
  INSERT INTO tasks (project_id, task_id, kind, lifecycle, parent_task_id, covers_tasks, external_ref,
                     lease_holder, lease_token, lease_expires_at)
  VALUES (p_project_id, p_task_id, p_kind, k.lifecycle, p_parent_task_id, coalesce(p_covers_tasks, '{}'), p_external_ref,
          p_holder, 1, clock_timestamp() + make_interval(secs => p_ttl_seconds))
  ON CONFLICT (project_id, task_id) DO NOTHING;
  IF FOUND THEN RETURN 1; END IF;
  SELECT * INTO v_old FROM tasks WHERE project_id = p_project_id AND task_id = p_task_id;
  IF v_old.kind = p_kind AND v_old.parent_task_id IS NOT DISTINCT FROM p_parent_task_id
     AND v_old.lease_holder = p_holder AND v_old.lease_expires_at > clock_timestamp() THEN
    RETURN v_old.lease_token;
  END IF;
  PERFORM _refuse(format('task %s/%s already exists', p_project_id, p_task_id));
END $$;

-- devorch contract_errors() (R6 D7): role vs kind map, read-only scopes, allowed ⊄ restricted, review target,
-- subtask fields, path ownership; contract-derived dependencies, interface contracts and required facts.
CREATE FUNCTION register_contract(p_project_id text, p_task_id text, p_contract_version int, p_core_sha256 text,
                                  p_body jsonb, p_max_attempts int, p_origin text, p_holder text, p_token bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE; k task_kinds%ROWTYPE; v_old task_contracts%ROWTYPE; v_allowed text[]; v_restricted text[];
        v_p text; v_role text; v_conflict text; d jsonb; v_first int;
BEGIN
  SELECT * INTO t FROM tasks WHERE project_id = p_project_id AND task_id = p_task_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s/%s', p_project_id, p_task_id)); END IF;
  PERFORM _check_lease(t, p_holder, p_token);
  SELECT * INTO v_old FROM task_contracts WHERE project_id = p_project_id AND task_id = p_task_id AND contract_version = p_contract_version;
  IF FOUND THEN
    IF v_old.core_sha256 = p_core_sha256 THEN RETURN false; END IF;
    PERFORM _refuse('contract version already registered with a different core');
  END IF;
  IF EXISTS (SELECT 1 FROM task_contracts WHERE project_id = p_project_id AND task_id = p_task_id AND contract_version > p_contract_version) THEN
    PERFORM _refuse('contract versions must increase');
  END IF;
  SELECT * INTO k FROM task_kinds WHERE kind = t.kind;
  IF p_body->>'kind' IS DISTINCT FROM t.kind THEN PERFORM _refuse('contract kind differs from task kind'); END IF;
  IF p_body ? 'task_id' AND p_body->>'task_id' <> p_task_id THEN PERFORM _refuse('contract task_id differs'); END IF;
  -- assigned role vs the kind map (catalogue ∩ project-enabled roles)
  v_role := p_body->>'assigned_agent';
  IF NOT k.operator_evidence THEN
    IF NOT EXISTS (SELECT 1 FROM roles r JOIN project_roles pr ON pr.role = r.role AND pr.project_id = p_project_id
                    WHERE r.role = v_role AND NOT r.retired AND t.kind = ANY (r.kinds) AND t.kind = ANY (pr.kinds)) THEN
      PERFORM _refuse(format('kind %s must be assigned to an enabled role of the catalogue that provides it (got %s)', t.kind, v_role));
    END IF;
  ELSIF EXISTS (SELECT 1 FROM roles r WHERE r.role = v_role AND r.llm) THEN
    PERFORM _refuse(format('kind %s is completed by the operator, not by an LLM role', t.kind));
  END IF;
  v_allowed := _jtext(p_body->'allowed_paths');
  v_restricted := _jtext(p_body->'restricted_paths');
  IF k.read_only AND cardinality(v_allowed) > 0 THEN PERFORM _refuse('read-only kinds must have allowed_paths []'); END IF;
  FOREACH v_p IN ARRAY v_allowed LOOP
    IF _matches(replace(replace(v_p, '**', 'x'), '*', 'x'), v_restricted) THEN
      PERFORM _refuse(format('allowed path %s falls inside restricted_paths', v_p));
    END IF;
  END LOOP;
  IF k.is_review AND coalesce(p_body->'review_target'->>'head_commit', '') !~ '^[0-9a-f]{40}$' THEN
    PERFORM _refuse('review tasks need review_target.head_commit');
  END IF;
  IF k.is_review AND p_body->>'parent_task_id' IS DISTINCT FROM t.parent_task_id THEN
    PERFORM _refuse('review subtasks need parent_task_id equal to the task''s parent');
  END IF;
  IF t.kind = 'integration' AND _jtext(p_body->'covers_tasks') IS DISTINCT FROM t.covers_tasks THEN
    PERFORM _refuse('integration covers_tasks differ from the task');
  END IF;
  FOR v_p IN SELECT x FROM jsonb_array_elements_text(coalesce(p_body->'required_reviewers', '[]')) x LOOP
    IF NOT EXISTS (SELECT 1 FROM roles r JOIN project_roles pr ON pr.role = r.role AND pr.project_id = p_project_id
                     JOIN task_kinds tk ON tk.kind = ANY (r.kinds) AND tk.is_review WHERE r.role = v_p AND NOT r.retired) THEN
      PERFORM _refuse(format('required reviewer %s is not an enabled reviewing role', v_p));
    END IF;
  END LOOP;
  v_conflict := _ownership_conflict(p_project_id, p_task_id, v_allowed);
  IF v_conflict IS NOT NULL THEN PERFORM _refuse(format('path ownership conflict with active task %s', v_conflict)); END IF;
  SELECT min(contract_version) INTO v_first FROM task_contracts WHERE project_id = p_project_id AND task_id = p_task_id;
  INSERT INTO task_contracts (project_id, task_id, contract_version, core_sha256, body, max_attempts, origin,
                              requires_approval, registered_by)
  VALUES (p_project_id, p_task_id, p_contract_version, p_core_sha256, p_body, p_max_attempts, p_origin,
          p_origin = 'planner' OR v_first IS NOT NULL, p_holder);
  FOR d IN SELECT x FROM jsonb_array_elements(coalesce(p_body->'dependencies', '[]')) x LOOP
    -- R6 re-check RA-3: cross-project dependencies are designed only; refuse them rather than bind to a same-id task
    IF d ? 'project_id' AND d->>'project_id' <> p_project_id THEN
      PERFORM _refuse(format('cross-project dependency on %s/%s is not implemented', d->>'project_id', d->>'task_id'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM tasks WHERE project_id = p_project_id AND task_id = d->>'task_id') THEN
      PERFORM _refuse(format('dependency %s is not a task of project %s', d->>'task_id', p_project_id));
    END IF;
    INSERT INTO task_dependencies VALUES (p_project_id, p_task_id, p_contract_version, d->>'task_id',
      coalesce(d->>'required_state', 'COMPLETED'), d->>'path', d->>'sha256');
  END LOOP;
  FOR d IN SELECT x FROM jsonb_array_elements(coalesce(p_body->'interface_contracts', '[]')) x LOOP
    INSERT INTO task_interface_contracts VALUES (p_project_id, p_task_id, p_contract_version, d->>'path', d->>'sha256', d->>'frozen_by');
  END LOOP;
  INSERT INTO task_required_facts SELECT p_project_id, p_task_id, p_contract_version, x
    FROM jsonb_array_elements_text(coalesce(p_body->'required_facts', '[]')) x;
  RETURN true;
END $$;

-- Admission decision (holds with reason are recorded too). An 'admit' is consumed by exactly one dispatch_job().
CREATE FUNCTION record_admission(p_project_id text, p_task_id text, p_attempt int, p_role text, p_decision text,
                                 p_reason text, p_detail jsonb, p_holder text, p_token bigint)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE; v_id bigint;
BEGIN
  SELECT * INTO t FROM tasks WHERE project_id = p_project_id AND task_id = p_task_id;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s/%s', p_project_id, p_task_id)); END IF;
  PERFORM _check_lease(t, p_holder, p_token);
  IF p_decision = 'admit' THEN PERFORM _check_dispatchable(p_project_id, t.kind, 'dispatch'); END IF;
  INSERT INTO admission_decisions (project_id, task_id, attempt, role, decision, reason, detail, controller_id, lease_token)
  VALUES (p_project_id, p_task_id, p_attempt, p_role, p_decision, p_reason, coalesce(p_detail, '{}'), p_holder, p_token)
  RETURNING decision_id INTO v_id;
  RETURN v_id;
END $$;

-- -----------------------------------------------------------------------------------------------------
-- record_event: the ONLY way to append to task_events / change task state. Port of devorch check_transition()
-- + apply() + verify_subtask() + result_errors(); refusals raise SQLSTATE DP001 (rule) / DP002 (lease).
-- -----------------------------------------------------------------------------------------------------
CREATE FUNCTION record_event(
  p_project_id text, p_task_id text, p_event text, p_contract_version int, p_attempt int,
  p_lease_holder text, p_lease_token bigint,
  p_evidence jsonb DEFAULT '[]', p_head_commit text DEFAULT NULL, p_payload jsonb DEFAULT '{}',
  p_idempotency_key text DEFAULT NULL, p_outbox jsonb DEFAULT '[]')
RETURNS TABLE (r_seq int, r_from_state text, r_to_state text, r_gate text, r_hash text, r_replayed boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $fn$
DECLARE
  t tasks%ROWTYPE; k task_kinds%ROWTYPE; c task_contracts%ROWTYPE; st tasks%ROWTYPE; sk task_kinds%ROWTYPE;
  pj projects%ROWTYPE; v_old task_events%ROWTYPE; e task_events%ROWTYPE; v_fact operator_facts%ROWTYPE;
  v_to text; v_gate text; v_have text[]; v_kinds text[]; v_counter text; v_max int; v_need text[];
  v_subs text[]; v_sub text; v_res jsonb; v_item jsonb; v_on_behalf text; v_rk text; v_ob jsonb; v_err text;
  v_gates text[]; v_counts jsonb; v_impl text; v_head text; v_pr text; v_frozen jsonb; v_bump boolean;
  v_revs int; v_reset bigint; v_reset_new bigint; v_missing text[]; v_conflict text; v_job job_runs%ROWTYPE;
  v_payload jsonb := coalesce(p_payload, '{}');
BEGIN
  SELECT * INTO t FROM tasks WHERE project_id = p_project_id AND task_id = p_task_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s/%s', p_project_id, p_task_id)); END IF;

  IF p_idempotency_key IS NOT NULL THEN
    SELECT * INTO v_old FROM task_events te
     WHERE te.project_id = p_project_id AND te.task_id = p_task_id AND te.idempotency_key = p_idempotency_key;
    IF FOUND THEN
      IF v_old.event <> p_event OR v_old.attempt <> p_attempt OR v_old.contract_version <> p_contract_version THEN
        PERFORM _refuse(format('idempotency key %s already used for a different record (seq %s)', p_idempotency_key, v_old.seq));
      END IF;
      RETURN QUERY SELECT v_old.seq, v_old.from_state, v_old.to_state, v_old.gate, v_old.hash, true;
      RETURN;
    END IF;
  END IF;

  PERFORM _check_lease(t, p_lease_holder, p_lease_token);
  SELECT * INTO pj FROM projects WHERE project_id = p_project_id;
  SELECT * INTO k FROM task_kinds WHERE kind = t.kind;
  SELECT * INTO c FROM task_contracts tc
   WHERE tc.project_id = p_project_id AND tc.task_id = p_task_id AND tc.contract_version = p_contract_version;
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
           SELECT 1 FROM artifacts a WHERE a.project_id = p_project_id AND a.sha256 = v_item->>'sha256') THEN
        PERFORM _refuse(format('file evidence %s is not a registered artifact of project %s', v_item->>'ref', p_project_id));
      END IF;
    END IF;
    IF v_item->>'kind' = 'operator_fact' THEN
      IF v_item->>'ref' !~ '^[0-9]{1,18}$' THEN PERFORM _refuse('operator_fact ref must be a fact_id'); END IF;
      SELECT * INTO v_fact FROM operator_facts f WHERE f.fact_id = (v_item->>'ref')::bigint;
      IF NOT FOUND OR v_fact.project_id IS DISTINCT FROM p_project_id THEN
        PERFORM _refuse(format('operator fact %s not found for project %s', v_item->>'ref', p_project_id));
      END IF;
      v_on_behalf := v_fact.issuer || '#' || v_fact.subject;
    END IF;
  END LOOP;
  v_kinds := ARRAY(SELECT DISTINCT x->>'kind' FROM jsonb_array_elements(p_evidence) x);

  IF p_head_commit IS NOT NULL AND p_head_commit !~ '^[0-9a-f]{40}$' THEN PERFORM _refuse('head_commit must be a 40-hex sha'); END IF;
  IF p_attempt IS NULL OR p_attempt NOT BETWEEN 1 AND 50 THEN PERFORM _refuse('attempt must be 1..50'); END IF;

  -- contract-core continuity
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

  -- revision limit (R6 D18): max 3 contract_revised until an operator 'revision-reset' fact for this task
  v_revs := t.revisions_since_reset; v_reset := t.revision_reset_fact_id;
  IF p_event = 'contract_revised' THEN
    IF v_revs >= 3 THEN
      SELECT max(f.fact_id) INTO v_reset_new FROM operator_facts f
       WHERE f.project_id = p_project_id AND f.task_id = p_task_id AND f.fact_key = 'revision-reset'
         AND f.status = 'approved' AND f.fact_id > coalesce(t.revision_reset_fact_id, 0);
      IF v_reset_new IS NULL THEN
        PERFORM _refuse('revision limit 3 reached: an operator revision-reset is required');
      END IF;
      v_revs := 0; v_reset := v_reset_new;
    END IF;
    v_revs := v_revs + 1;
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

  -- project status / hard preconditions for dispatch (R6 D4); path ownership when the task becomes an owner (D7)
  IF p_event IN ('assigned', 'dispatched') THEN
    PERFORM _check_dispatchable(p_project_id, t.kind, 'dispatch');
  END IF;
  IF p_event = 'assigned' THEN
    v_conflict := _ownership_conflict(p_project_id, p_task_id, _jtext(c.body->'allowed_paths'));
    IF v_conflict IS NOT NULL THEN PERFORM _refuse(format('path ownership conflict with active task %s', v_conflict)); END IF;
  END IF;

  -- environmental classification only from platform signals (R6 D17)
  IF p_event = 'env_retry' THEN
    IF NOT EXISTS (SELECT 1 FROM env_signals s WHERE s.signal = v_payload->>'signal') THEN
      PERFORM _refuse(format('env_retry needs a platform signal (got %s); agent-reported failures are charged attempts', coalesce(v_payload->>'signal', 'none')));
    END IF;
    IF coalesce(v_payload->>'job_id', '') !~ '^[0-9]{1,18}$' THEN PERFORM _refuse('env_retry needs payload.job_id'); END IF;
    SELECT * INTO v_job FROM job_runs j WHERE j.job_id = (v_payload->>'job_id')::bigint;
    IF NOT FOUND OR v_job.project_id <> p_project_id OR v_job.task_id <> p_task_id OR v_job.failure_class IS DISTINCT FROM 'environmental'
       OR v_job.detail->>'signal' IS DISTINCT FROM v_payload->>'signal' THEN
      PERFORM _refuse('env_retry must cite a Job of this task classified environmental with the same signal');
    END IF;
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

  -- entering READY: operator approval of planner contracts and revisions (R6 D18)
  IF v_to = 'READY' AND c.requires_approval AND NOT EXISTS (
       SELECT 1 FROM operator_facts f WHERE f.project_id = p_project_id AND f.task_id = p_task_id
          AND f.fact_key = 'contract-approval' AND f.status = 'approved'
          AND (f.value->>'contract_version')::int = c.contract_version AND f.value->>'core_sha256' = c.core_sha256) THEN
    PERFORM _refuse(format('contract %s v%s needs an operator contract-approval before READY', p_task_id, c.contract_version));
  END IF;

  -- G1 (devorch issue_blockers + contract_dep_blockers, R6 D1/D7)
  IF p_event = 'unblocked' THEN
    IF NOT 'design_ref' = ANY (v_kinds) THEN PERFORM _refuse('G1 needs design_ref evidence (operator-approved design commit)'); END IF;
    IF t.lifecycle = 'FULL' THEN
      v_missing := _missing_hard_preconditions(p_project_id);
      IF cardinality(v_missing) > 0 THEN
        PERFORM _refuse(format('not READY, refusing G1: fact %s (project hard preconditions)', array_to_string(v_missing, ', fact ')));
      END IF;
    END IF;
    v_missing := ARRAY(SELECT rf.fact_key FROM task_required_facts rf
                        WHERE rf.project_id = p_project_id AND rf.task_id = p_task_id AND rf.contract_version = c.contract_version
                          AND NOT _fact_satisfied(p_project_id, rf.fact_key) ORDER BY rf.fact_key);
    IF cardinality(v_missing) > 0 THEN
      PERFORM _refuse(format('not READY, refusing G1: fact %s', array_to_string(v_missing, ', fact ')));
    END IF;
    SELECT string_agg(format('interface %s not frozen at the contracted sha256 by %s', ic.path, ic.frozen_by), '; ') INTO v_err
      FROM task_interface_contracts ic LEFT JOIN tasks ft ON ft.project_id = ic.project_id AND ft.task_id = ic.frozen_by
     WHERE ic.project_id = p_project_id AND ic.task_id = p_task_id AND ic.contract_version = c.contract_version
       AND (ft.task_id IS NULL OR ft.frozen_files->>ic.path IS DISTINCT FROM ic.sha256);
    IF v_err IS NOT NULL THEN PERFORM _refuse('not READY, refusing G1: ' || v_err); END IF;
    SELECT string_agg(format('dependency %s not %s', d.depends_on, d.required_state), '; ') INTO v_err
      FROM task_dependencies d JOIN tasks dt ON dt.project_id = d.project_id AND dt.task_id = d.depends_on
     WHERE d.project_id = p_project_id AND d.task_id = p_task_id AND d.contract_version = c.contract_version
       AND NOT CASE d.required_state
             WHEN 'COMPLETED' THEN dt.state = 'COMPLETED'
             WHEN 'AWAITING_HUMAN' THEN dt.state IN ('AWAITING_HUMAN', 'COMPLETED')
             WHEN 'INTERFACE_FROZEN' THEN dt.frozen_files->>d.path IS NOT DISTINCT FROM d.sha256 END;
    IF v_err IS NOT NULL THEN PERFORM _refuse('not READY, refusing G1: ' || v_err); END IF;
  END IF;

  -- checked results (devorch result_errors, R6 D7)
  IF p_event = 'implementation_completed' AND t.lifecycle = 'FULL' THEN
    IF p_head_commit IS NULL THEN PERFORM _refuse('implementation_completed must record head_commit (the result''s head)'); END IF;
    IF NOT 'result_file' = ANY (v_kinds) THEN PERFORM _refuse('implementation_completed needs a result_file'); END IF;
    v_err := _result_errors(t, c, k, v_payload->'result', p_event, p_attempt, p_head_commit);
    IF v_err IS NOT NULL THEN PERFORM _refuse('implementation_completed refused, result does not check: ' || v_err); END IF;
  END IF;
  IF p_event = 'result_accepted' THEN
    IF k.operator_evidence THEN
      IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(p_evidence) x JOIN operator_facts f
                        ON f.fact_id = CASE WHEN x->>'kind' = 'operator_fact' THEN (x->>'ref')::bigint END
                     WHERE f.project_id = p_project_id AND f.task_id = p_task_id
                       AND f.status IN (SELECT status FROM fact_statuses WHERE satisfies)) THEN
        PERFORM _refuse('operator/Mac task completion needs an authenticated operator fact for this task');
      END IF;
    ELSE
      IF NOT 'result_file' = ANY (v_kinds) THEN PERFORM _refuse('result_accepted needs a validated result_file'); END IF;
      v_err := _result_errors(t, c, k, v_payload->'result', p_event, p_attempt, p_head_commit);
      IF v_err IS NOT NULL THEN PERFORM _refuse('result_accepted refused, result does not check: ' || v_err); END IF;
    END IF;
  END IF;

  -- G2: the verifier's own re-run of every required test at this head (R6 D8)
  IF p_event = 'tests_passed' THEN
    IF p_head_commit IS NULL THEN PERFORM _refuse('tests_passed must record head_commit (the tested tip)'); END IF;
    IF NOT 'test_run' = ANY (v_kinds) THEN PERFORM _refuse('tests_passed needs test_run evidence from the verifier re-run'); END IF;
    IF t.impl_head IS DISTINCT FROM p_head_commit THEN
      PERFORM _refuse('tests_passed head is not the head of a checked implementation_completed in this attempt');
    END IF;
    v_missing := ARRAY(SELECT x->>'id' FROM jsonb_array_elements(coalesce(c.body->'required_tests', '[]')) x
                        WHERE NOT EXISTS (SELECT 1 FROM test_runs tr JOIN job_runs j ON j.job_id = tr.job_id
                                           WHERE tr.project_id = p_project_id AND tr.task_id = p_task_id
                                             AND tr.attempt = p_attempt AND tr.head_commit = p_head_commit
                                             AND tr.test_id = x->>'id' AND tr.outcome = 'passed' AND tr.exit_code = 0
                                             AND j.role = 'verifier'));
    IF cardinality(v_missing) > 0 THEN
      PERFORM _refuse(format('G2 needs a passed verifier test run at this head for %s', v_missing));
    END IF;
  END IF;

  -- G3/G4/G5: bound subtasks (devorch verify_subtask)
  IF p_event IN ('code_review_passed', 'security_review_passed', 'integration_verified') THEN
    v_subs := ARRAY(SELECT x->>'ref' FROM jsonb_array_elements(p_evidence) x WHERE x->>'kind' = 'subtask');
    IF cardinality(v_subs) = 0 THEN
      PERFORM _refuse(format('%s needs subtask evidence (a COMPLETED review/integration task)', p_event));
    END IF;
    FOREACH v_sub IN ARRAY v_subs LOOP
      SELECT * INTO st FROM tasks WHERE project_id = p_project_id AND task_id = v_sub;
      IF NOT FOUND THEN PERFORM _refuse(format('subtask %s not found in project', v_sub)); END IF;
      IF NOT EXISTS (SELECT 1 FROM gate_providers gp WHERE gp.event = p_event AND gp.kind = st.kind) THEN
        PERFORM _refuse(format('subtask %s kind %s cannot provide %s', v_sub, st.kind, p_event));
      END IF;
      IF st.kind <> 'integration' AND st.parent_task_id IS DISTINCT FROM t.task_id THEN
        PERFORM _refuse(format('subtask %s does not belong to %s', v_sub, t.task_id));
      END IF;
      IF st.state <> 'COMPLETED' THEN PERFORM _refuse(format('subtask %s is %s, not COMPLETED', v_sub, st.state)); END IF;
      SELECT te.payload->'result' INTO v_res FROM task_events te
       WHERE te.project_id = p_project_id AND te.task_id = v_sub AND te.event = 'result_accepted' ORDER BY te.seq DESC LIMIT 1;
      IF v_res IS NULL THEN PERFORM _refuse(format('%s has no accepted result', v_sub)); END IF;
      SELECT * INTO sk FROM task_kinds WHERE kind = st.kind;
      IF sk.is_review THEN
        IF coalesce(v_res->>'recommendation', '') NOT IN ('accept', 'accept_with_conditions') THEN
          PERFORM _refuse(format('review %s did not accept', v_sub));
        END IF;
        IF jsonb_path_exists(v_res, '$.findings[*] ? (@.blocking == true)') THEN
          PERFORM _refuse(format('review %s has blocking findings', v_sub));
        END IF;
        IF v_res->>'reviewed_head_commit' IS DISTINCT FROM t.head_commit OR
           (SELECT tc.body->'review_target'->>'head_commit' FROM task_contracts tc
             WHERE tc.project_id = p_project_id AND tc.task_id = v_sub AND tc.contract_version = st.contract_version) IS DISTINCT FROM t.head_commit THEN
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
    FOR v_rk IN SELECT tk.kind FROM jsonb_array_elements_text(coalesce(c.body->'required_reviewers', '[]')) rr(reviewer)
                  JOIN roles r ON r.role = rr.reviewer JOIN task_kinds tk ON tk.kind = ANY (r.kinds) AND tk.is_review
                 WHERE tk.kind <> 'security_review' LOOP
      IF NOT EXISTS (SELECT 1 FROM tasks s WHERE s.project_id = p_project_id AND s.task_id = ANY (v_subs) AND s.kind = v_rk) THEN
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
  IF p_event = 'interface_frozen' AND (jsonb_typeof(v_payload->'frozen_files') IS DISTINCT FROM 'object'
                                       OR v_payload->'frozen_files' = '{}'::jsonb) THEN
    PERFORM _refuse('interface_frozen needs payload.frozen_files {path: sha256}');
  END IF;

  -- review-gate target and REQUIRED_BEFORE
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

  e.project_id := p_project_id; e.task_id := p_task_id; e.seq := t.last_seq + 1; e.at := clock_timestamp();
  e.event := p_event; e.from_state := t.state; e.to_state := v_to; e.gate := v_gate;
  e.actor := 'devplat-controller'; e.controller_id := p_lease_holder; e.on_behalf_of := v_on_behalf;
  e.contract_version := p_contract_version; e.contract_core_sha256 := c.core_sha256; e.attempt := p_attempt;
  e.head_commit := p_head_commit; e.evidence := p_evidence; e.payload := v_payload;
  e.idempotency_key := p_idempotency_key; e.lease_token := p_lease_token;
  e.config_version := pj.config_version; e.assurance_mode := pj.assurance_mode; e.prev_hash := t.last_hash;
  e.hash := event_hash(e);
  INSERT INTO task_events (project_id, task_id, seq, at, event, from_state, to_state, gate, actor, controller_id,
                           on_behalf_of, contract_version, contract_core_sha256, attempt, head_commit, evidence,
                           payload, idempotency_key, lease_token, config_version, assurance_mode, prev_hash, hash)
  VALUES (e.project_id, e.task_id, e.seq, e.at, e.event, e.from_state, e.to_state, e.gate, e.actor, e.controller_id,
          e.on_behalf_of, e.contract_version, e.contract_core_sha256, e.attempt, e.head_commit, e.evidence,
          e.payload, e.idempotency_key, e.lease_token, e.config_version, e.assurance_mode, e.prev_hash, e.hash);

  PERFORM set_config('devplat.writer', 'record_event', true);
  UPDATE tasks SET state = v_to, contract_version = p_contract_version, core_sha256 = c.core_sha256, attempt = p_attempt,
                   gates = v_gates, counts = v_counts, head_commit = v_head, impl_head = v_impl, pr_head = v_pr,
                   frozen_files = v_frozen, need_bump = v_bump, revisions_since_reset = v_revs,
                   revision_reset_fact_id = v_reset, last_seq = e.seq, last_hash = e.hash
   WHERE project_id = p_project_id AND task_id = p_task_id;
  PERFORM set_config('devplat.writer', '', true);

  FOR v_ob IN SELECT x FROM jsonb_array_elements(coalesce(p_outbox, '[]')) x LOOP
    PERFORM _enqueue_outbox(p_project_id, v_ob->>'target', v_ob->>'operation', v_ob->>'dedup_key',
                            coalesce(v_ob->'payload', '{}'), p_task_id, e.seq);
  END LOOP;

  RETURN QUERY SELECT e.seq, e.from_state, e.to_state, e.gate, e.hash, false;
END $fn$;

-- Job dispatch: needs an unconsumed 'admit' decision; concurrent or repeated calls with one key yield one row.
CREATE FUNCTION dispatch_job(p_project_id text, p_task_id text, p_attempt int, p_role text, p_dispatch_no int,
                             p_admission_id bigint, p_idempotency_key text, p_target_id bigint, p_k8s_namespace text,
                             p_k8s_job_name text, p_holder text, p_token bigint)
RETURNS TABLE (r_job_id bigint, r_created boolean, r_k8s_job_name text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE t tasks%ROWTYPE; v_id bigint; j job_runs%ROWTYPE; a admission_decisions%ROWTYPE;
BEGIN
  SELECT * INTO t FROM tasks WHERE project_id = p_project_id AND task_id = p_task_id FOR SHARE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown task %s/%s', p_project_id, p_task_id)); END IF;
  PERFORM _check_lease(t, p_holder, p_token);
  -- an existing row for this key is returned before any other check (at-least-once controller)
  SELECT * INTO j FROM job_runs jr WHERE jr.idempotency_key = p_idempotency_key;
  IF NOT FOUND THEN
    IF t.state <> 'RUNNING' THEN PERFORM _refuse(format('task %s is %s; Jobs are dispatched only in RUNNING', p_task_id, t.state)); END IF;
    IF t.attempt IS NOT NULL AND p_attempt <> t.attempt AND NOT (t.need_bump AND p_attempt = t.attempt + 1) THEN
      PERFORM _refuse(format('attempt %s is not dispatchable (current %s)', p_attempt, t.attempt));
    END IF;
    PERFORM _check_dispatchable(p_project_id, t.kind, 'dispatch');   -- every role, the verifier included (re-check RA-8)
    SELECT * INTO a FROM admission_decisions WHERE decision_id = p_admission_id;
    IF NOT FOUND OR a.decision <> 'admit' OR a.project_id <> p_project_id OR a.task_id <> p_task_id
       OR a.attempt <> p_attempt OR a.role <> p_role OR a.decided_at < clock_timestamp() - interval '10 minutes' THEN
      PERFORM _refuse('dispatch needs a fresh admit decision for this task, attempt and role');
    END IF;
    IF p_target_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM execution_targets et
         WHERE et.target_id = p_target_id AND et.project_id = p_project_id AND et.enabled
           AND p_k8s_namespace LIKE et.namespace_prefix || '-%') THEN
      PERFORM _refuse('namespace is not in an enabled execution target of the task''s project');
    END IF;
    INSERT INTO job_runs (project_id, task_id, attempt, role, dispatch_no, admission_id, idempotency_key, target_id,
                          k8s_namespace, k8s_job_name, lease_token)
    VALUES (p_project_id, p_task_id, p_attempt, p_role, p_dispatch_no, p_admission_id, p_idempotency_key, p_target_id,
            p_k8s_namespace, p_k8s_job_name, p_token)
    ON CONFLICT (idempotency_key) DO NOTHING RETURNING job_id INTO v_id;
    IF v_id IS NOT NULL THEN
      RETURN QUERY SELECT v_id, true, p_k8s_job_name; RETURN;
    END IF;
    SELECT * INTO j FROM job_runs jr WHERE jr.idempotency_key = p_idempotency_key;
  END IF;
  IF j.project_id <> p_project_id OR j.task_id <> p_task_id OR j.attempt <> p_attempt OR j.role <> p_role
     OR j.k8s_job_name <> p_k8s_job_name THEN
    PERFORM _refuse('idempotency key collision with a different job');
  END IF;
  RETURN QUERY SELECT j.job_id, false, j.k8s_job_name;
END $$;

-- Per-Job tokens (hashes only) for the model gateway and the artifact gateway; TTL = Job deadline + 15 min.
CREATE FUNCTION set_job_tokens(p_job_id bigint, p_gateway_token_sha256 text, p_upload_token_sha256 text,
                               p_job_deadline timestamptz, p_holder text, p_token bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE j job_runs%ROWTYPE; t tasks%ROWTYPE;
BEGIN
  SELECT * INTO j FROM job_runs WHERE job_id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown job %s', p_job_id)); END IF;
  SELECT * INTO t FROM tasks WHERE project_id = j.project_id AND task_id = j.task_id;
  PERFORM _check_lease(t, p_holder, p_token);
  IF j.gateway_token_sha256 IS NOT NULL THEN PERFORM _refuse('job tokens are set once'); END IF;
  UPDATE job_runs SET gateway_token_sha256 = p_gateway_token_sha256, upload_token_sha256 = p_upload_token_sha256,
                      tokens_expire_at = p_job_deadline + interval '15 minutes'
   WHERE job_id = p_job_id;
END $$;

CREATE FUNCTION update_job_phase(p_job_id bigint, p_phase text, p_k8s_uid uuid, p_failure_class text, p_detail jsonb,
                                 p_holder text, p_token bigint)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE j job_runs%ROWTYPE; t tasks%ROWTYPE;
BEGIN
  SELECT * INTO j FROM job_runs WHERE job_id = p_job_id FOR UPDATE;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown job %s', p_job_id)); END IF;
  SELECT * INTO t FROM tasks WHERE project_id = j.project_id AND task_id = j.task_id;
  PERFORM _check_lease(t, p_holder, p_token);
  IF p_k8s_uid IS NOT NULL AND j.k8s_job_uid IS NOT NULL AND j.k8s_job_uid <> p_k8s_uid THEN
    PERFORM _refuse(format('duplicate execution: Job %s/%s has uid %s, observed %s', j.k8s_namespace, j.k8s_job_name, j.k8s_job_uid, p_k8s_uid));
  END IF;
  -- R6 D17: 'environmental' only with a platform signal
  IF p_failure_class = 'environmental' AND NOT EXISTS (SELECT 1 FROM env_signals s WHERE s.signal = p_detail->>'signal') THEN
    PERFORM _refuse(format('environmental classification needs a platform signal (got %s)', coalesce(p_detail->>'signal', 'none')));
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

CREATE FUNCTION job_heartbeat(p_job_id bigint, p_k8s_uid uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
BEGIN
  UPDATE job_runs SET last_heartbeat_at = clock_timestamp(), heartbeat_count = heartbeat_count + 1
   WHERE job_id = p_job_id AND phase IN ('created', 'running') AND k8s_job_uid IS NOT DISTINCT FROM p_k8s_uid;
  RETURN FOUND;
END $$;

-- Verifier result for G2 (the controller parses the verifier Job's report).
CREATE FUNCTION record_test_run(p_job_id bigint, p_head_commit text, p_test_id text, p_outcome text, p_exit_code int,
                                p_artifact_sha256 text, p_holder text, p_token bigint)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE j job_runs%ROWTYPE; t tasks%ROWTYPE; v_id bigint;
BEGIN
  SELECT * INTO j FROM job_runs WHERE job_id = p_job_id;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown job %s', p_job_id)); END IF;
  SELECT * INTO t FROM tasks WHERE project_id = j.project_id AND task_id = j.task_id;
  PERFORM _check_lease(t, p_holder, p_token);
  IF j.role <> 'verifier' THEN PERFORM _refuse('test runs are recorded only from verifier Jobs'); END IF;
  INSERT INTO test_runs (project_id, task_id, attempt, head_commit, test_id, job_id, outcome, exit_code, artifact_sha256)
  VALUES (j.project_id, j.task_id, j.attempt, p_head_commit, p_test_id, p_job_id, p_outcome, p_exit_code, p_artifact_sha256)
  RETURNING test_run_id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION register_artifact(p_project_id text, p_sha256 text, p_size_bytes bigint, p_media_type text, p_kind text,
                                  p_task_id text, p_job_id bigint, p_gate text, p_retention_class text,
                                  p_alias_key text DEFAULT NULL)
RETURNS TABLE (r_artifact_id bigint, r_created boolean)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE ak artifact_kinds%ROWTYPE; v_id bigint; a artifacts%ROWTYPE; v_until timestamptz;
BEGIN
  SELECT * INTO ak FROM artifact_kinds WHERE kind = p_kind;
  IF NOT FOUND THEN PERFORM _refuse(format('unknown artifact kind %s', p_kind)); END IF;
  IF p_size_bytes > ak.max_bytes THEN PERFORM _refuse(format('%s artifact over %s bytes', p_kind, ak.max_bytes)); END IF;
  v_until := now() + make_interval(days => CASE p_retention_class WHEN 'ephemeral' THEN 7 ELSE ak.default_retention_days END);
  INSERT INTO artifacts (project_id, sha256, bucket, object_key, alias_key, size_bytes, media_type, kind, task_id, job_id, gate,
                         retention_class, retain_until)
  VALUES (p_project_id, p_sha256, 'devplat-' || p_project_id, 'sha256/' || p_sha256, p_alias_key, p_size_bytes, p_media_type,
          p_kind, p_task_id, p_job_id, p_gate, p_retention_class, v_until)
  ON CONFLICT (project_id, sha256) DO NOTHING RETURNING artifact_id INTO v_id;
  IF v_id IS NOT NULL THEN RETURN QUERY SELECT v_id, true; RETURN; END IF;
  SELECT * INTO a FROM artifacts x WHERE x.project_id = p_project_id AND x.sha256 = p_sha256 FOR UPDATE;
  IF a.size_bytes <> p_size_bytes THEN PERFORM _refuse('same sha256 registered with a different size'); END IF;
  IF v_until > a.retain_until THEN
    UPDATE artifacts SET retain_until = v_until,
           retention_class = CASE WHEN p_retention_class = 'evidence' THEN 'evidence' ELSE retention_class END
     WHERE artifact_id = a.artifact_id;
  END IF;
  RETURN QUERY SELECT a.artifact_id, false;
END $$;

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
-- 10. Model gateway API (budgets only, R6 D8): atomic reserve / settle / release per project-day and task
-- =====================================================================================================
-- p_gateway_token_sha256 binds the request to its Job, task and project (R6 D12). Task cap: contract
-- budget.max_cost_usd over ALL reservations of the task (every attempt and env re-dispatch, R6 D17).
CREATE FUNCTION reserve_budget(p_gateway_token_sha256 text, p_request_id text, p_est_usd numeric, p_est_tokens bigint)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE j job_runs%ROWTYPE; p projects%ROWTYPE; b budget_days%ROWTYPE; v_day date := (now() AT TIME ZONE 'UTC')::date;
        v_id bigint; v_task_cap numeric; v_task_used numeric;
BEGIN
  SELECT * INTO j FROM job_runs WHERE gateway_token_sha256 = p_gateway_token_sha256;
  IF NOT FOUND OR j.phase NOT IN ('created', 'running') OR j.tokens_expire_at <= clock_timestamp() THEN
    PERFORM _refuse('unknown, finished or expired gateway token');
  END IF;
  SELECT reservation_id INTO v_id FROM budget_reservations WHERE job_id = j.job_id AND request_id = p_request_id;
  IF v_id IS NOT NULL THEN RETURN v_id; END IF;
  SELECT * INTO p FROM projects WHERE project_id = j.project_id;
  IF p.cost_usd_per_day IS NULL THEN PERFORM _refuse(format('project %s has no daily cost budget', p.project_id)); END IF;
  INSERT INTO budget_days (project_id, day, cost_limit_usd, tokens_limit) VALUES (p.project_id, v_day, p.cost_usd_per_day, p.tokens_per_day)
  ON CONFLICT DO NOTHING;
  SELECT * INTO b FROM budget_days WHERE project_id = p.project_id AND day = v_day FOR UPDATE;   -- serialises the project-day
  IF b.reserved_usd + b.settled_usd + p_est_usd > b.cost_limit_usd THEN
    PERFORM _refuse(format('daily cost budget of %s exhausted (%s used or reserved)', p.project_id, b.reserved_usd + b.settled_usd));
  END IF;
  IF b.tokens_limit IS NOT NULL AND b.reserved_tokens + b.settled_tokens + p_est_tokens > b.tokens_limit THEN
    PERFORM _refuse(format('daily token budget of %s exhausted', p.project_id));
  END IF;
  SELECT (c.body->'budget'->>'max_cost_usd')::numeric INTO v_task_cap FROM tasks t
    JOIN task_contracts c ON c.project_id = t.project_id AND c.task_id = t.task_id AND c.contract_version = t.contract_version
   WHERE t.project_id = j.project_id AND t.task_id = j.task_id;
  IF v_task_cap IS NOT NULL THEN
    SELECT coalesce(sum(CASE WHEN status = 'settled' THEN actual_usd WHEN status = 'reserved' THEN est_usd ELSE 0 END), 0)
      INTO v_task_used FROM budget_reservations WHERE project_id = j.project_id AND task_id = j.task_id;
    IF v_task_used + p_est_usd > v_task_cap THEN
      PERFORM _refuse(format('task cost budget %s exhausted (%s used or reserved, all attempts and retries)', v_task_cap, v_task_used));
    END IF;
  END IF;
  UPDATE budget_days SET reserved_usd = reserved_usd + p_est_usd, reserved_tokens = reserved_tokens + p_est_tokens
   WHERE project_id = p.project_id AND day = v_day;
  INSERT INTO budget_reservations (project_id, task_id, job_id, day, request_id, est_usd, est_tokens)
  VALUES (j.project_id, j.task_id, j.job_id, v_day, p_request_id, p_est_usd, p_est_tokens) RETURNING reservation_id INTO v_id;
  RETURN v_id;
END $$;

CREATE FUNCTION settle_budget(p_reservation_id bigint, p_actual_usd numeric, p_actual_tokens bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE r budget_reservations%ROWTYPE;
BEGIN
  SELECT * INTO r FROM budget_reservations WHERE reservation_id = p_reservation_id FOR UPDATE;
  IF NOT FOUND OR r.status <> 'reserved' THEN RETURN false; END IF;
  UPDATE budget_days SET reserved_usd = reserved_usd - r.est_usd, reserved_tokens = reserved_tokens - r.est_tokens,
                         settled_usd = settled_usd + p_actual_usd, settled_tokens = settled_tokens + p_actual_tokens
   WHERE project_id = r.project_id AND day = r.day;
  UPDATE budget_reservations SET status = 'settled', actual_usd = p_actual_usd, actual_tokens = p_actual_tokens,
                                 settled_at = clock_timestamp() WHERE reservation_id = p_reservation_id;
  RETURN true;
END $$;

-- Only for a request that never reached the upstream API (rejected locally). Never used for retries.
CREATE FUNCTION release_budget(p_reservation_id bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE r budget_reservations%ROWTYPE;
BEGIN
  SELECT * INTO r FROM budget_reservations WHERE reservation_id = p_reservation_id FOR UPDATE;
  IF NOT FOUND OR r.status <> 'reserved' THEN RETURN false; END IF;
  UPDATE budget_days SET reserved_usd = reserved_usd - r.est_usd, reserved_tokens = reserved_tokens - r.est_tokens
   WHERE project_id = r.project_id AND day = r.day;
  UPDATE budget_reservations SET status = 'released', settled_at = clock_timestamp() WHERE reservation_id = p_reservation_id;
  RETURN true;
END $$;

-- =====================================================================================================
-- 11. Artifact gateway API (R6 D10/D11): per-Job one-time upload authorisation with caps
-- =====================================================================================================
-- Returns bucket and key runs/<job-uid>/<name>. One authorisation per (job, name); per-object cap and 512 MiB per run.
CREATE FUNCTION authorize_upload(p_upload_token_sha256 text, p_job_uid uuid, p_name text, p_declared_size bigint)
RETURNS TABLE (r_bucket text, r_key text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE j job_runs%ROWTYPE; v_cap bigint; v_total bigint;
BEGIN
  SELECT * INTO j FROM job_runs WHERE upload_token_sha256 = p_upload_token_sha256 FOR UPDATE;
  IF NOT FOUND OR j.k8s_job_uid IS DISTINCT FROM p_job_uid OR j.phase NOT IN ('created', 'running')
     OR j.tokens_expire_at <= clock_timestamp() THEN
    PERFORM _refuse('unknown, foreign, finished or expired upload token');
  END IF;
  SELECT max_bytes INTO v_cap FROM run_object_caps WHERE name = p_name;
  IF v_cap IS NULL THEN PERFORM _refuse(format('object name %s is not part of the run layout', p_name)); END IF;
  IF p_declared_size < 0 OR p_declared_size > v_cap THEN PERFORM _refuse(format('%s over its cap of %s bytes', p_name, v_cap)); END IF;
  SELECT coalesce(sum(coalesce(size_bytes, declared_size)), 0) INTO v_total FROM run_uploads WHERE job_id = j.job_id;
  IF v_total + p_declared_size > 536870912 THEN PERFORM _refuse('run upload total over 512 MiB'); END IF;
  INSERT INTO run_uploads (job_id, name, declared_size) VALUES (j.job_id, p_name, p_declared_size)
  ON CONFLICT DO NOTHING;
  IF NOT FOUND THEN PERFORM _refuse(format('%s was already uploaded for this run (one-time)', p_name)); END IF;
  RETURN QUERY SELECT 'devplat-' || j.project_id, 'runs/' || p_job_uid::text || '/' || p_name;
END $$;

CREATE FUNCTION complete_upload(p_upload_token_sha256 text, p_job_uid uuid, p_name text, p_sha256 text, p_size_bytes bigint)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE j job_runs%ROWTYPE;
BEGIN
  SELECT * INTO j FROM job_runs WHERE upload_token_sha256 = p_upload_token_sha256 AND k8s_job_uid = p_job_uid;
  IF NOT FOUND THEN PERFORM _refuse('unknown upload token'); END IF;
  UPDATE run_uploads SET sha256 = p_sha256, size_bytes = p_size_bytes, status = 'stored', stored_at = clock_timestamp()
   WHERE job_id = j.job_id AND name = p_name AND status = 'authorized' AND p_size_bytes <= declared_size;
  RETURN FOUND;
END $$;

-- =====================================================================================================
-- 12. Verification (read-only)
-- =====================================================================================================
CREATE FUNCTION verify_chain(p_project_id text DEFAULT NULL, p_task_id text DEFAULT NULL)
RETURNS TABLE (v_project_id text, v_task_id text, v_seq int, v_problem text)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE tk tasks%ROWTYPE; e task_events%ROWTYPE; v_prev text; v_n int; v_state text; v_tr transitions%ROWTYPE;
BEGIN
  FOR tk IN SELECT * FROM tasks WHERE (p_project_id IS NULL OR project_id = p_project_id)
                                  AND (p_task_id IS NULL OR task_id = p_task_id) ORDER BY project_id, task_id LOOP
    v_prev := 'GENESIS'; v_n := 0; v_state := 'NEW';
    FOR e IN SELECT * FROM task_events te WHERE te.project_id = tk.project_id AND te.task_id = tk.task_id ORDER BY te.seq LOOP
      v_n := v_n + 1;
      IF e.seq <> v_n THEN RETURN QUERY SELECT tk.project_id, tk.task_id, e.seq, 'seq gap (expected ' || v_n || ')'; v_n := e.seq; END IF;
      IF e.prev_hash <> v_prev THEN RETURN QUERY SELECT tk.project_id, tk.task_id, e.seq, 'prev_hash does not link to the previous record'; END IF;
      IF event_hash(e) <> e.hash THEN RETURN QUERY SELECT tk.project_id, tk.task_id, e.seq, 'hash mismatch (row altered)'; END IF;
      IF e.from_state <> v_state THEN RETURN QUERY SELECT tk.project_id, tk.task_id, e.seq, 'from_state does not follow the previous to_state'; END IF;
      SELECT * INTO v_tr FROM transitions tr WHERE tr.lifecycle = tk.lifecycle AND tr.from_state = e.from_state AND tr.event = e.event;
      IF NOT FOUND OR (e.to_state <> v_tr.to_state AND NOT (e.event IN ('code_review_passed', 'security_review_passed')
                                                            AND e.to_state = 'AWAITING_INTEGRATION')) THEN
        RETURN QUERY SELECT tk.project_id, tk.task_id, e.seq, 'not a legal transition';
      END IF;
      v_prev := e.hash; v_state := e.to_state;
    END LOOP;
    IF tk.last_seq <> v_n OR tk.last_hash <> v_prev THEN
      RETURN QUERY SELECT tk.project_id, tk.task_id, NULL::int, 'tasks row does not match the chain tail (rows removed or added?)';
    END IF;
    IF tk.state <> v_state THEN RETURN QUERY SELECT tk.project_id, tk.task_id, NULL::int, 'tasks.state differs from the chain'; END IF;
  END LOOP;
END $$;

CREATE FUNCTION chain_digest()
RETURNS TABLE (r_digest text, r_task_count int, r_event_count bigint, r_max_event_id bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
  WITH tails AS (SELECT DISTINCT ON (project_id, task_id) project_id, task_id, seq, hash FROM devplat.task_events
                  ORDER BY project_id, task_id, seq DESC)
  SELECT encode(sha256(convert_to(coalesce(string_agg(project_id || '/' || task_id || ':' || seq || ':' || hash, E'\n'
                                                      ORDER BY project_id, task_id), ''), 'UTF8')), 'hex'),
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
-- 13. devplat-api: authenticated operator facts (allowed identities only, R6 D2)
-- =====================================================================================================
CREATE FUNCTION record_operator_fact(p_project_id text, p_fact_key text, p_status text, p_value jsonb, p_task_id text,
                                     p_statement text, p_subject text, p_issuer text, p_email text, p_auth_time timestamptz,
                                     p_token_jti text, p_evidence_sha256 text DEFAULT NULL)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = devplat, pg_catalog, pg_temp AS $$
DECLARE i oidc_issuers%ROWTYPE; v_id bigint;
BEGIN
  SELECT * INTO i FROM oidc_issuers WHERE issuer = p_issuer AND enabled;
  IF NOT FOUND THEN PERFORM _refuse(format('issuer %s is not an enabled operator identity provider', p_issuer)); END IF;
  IF coalesce(p_subject, '') = '' OR p_subject ~ i.subject_deny_regex THEN
    PERFORM _refuse(format('subject %s is not a human operator identity', p_subject));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM operator_identities oi WHERE oi.issuer = p_issuer AND oi.subject = p_subject
                   AND (oi.project_id IS NULL OR oi.project_id IS NOT DISTINCT FROM p_project_id)) THEN
    PERFORM _refuse(format('subject %s is not an allowed operator for project %s', p_subject, coalesce(p_project_id, '(platform)')));
  END IF;
  IF p_auth_time IS NULL OR p_auth_time > now() + interval '60 seconds'
     OR p_auth_time < now() - make_interval(secs => i.max_auth_age_s) THEN
    PERFORM _refuse('operator authentication is not fresh (re-authenticate)');
  END IF;
  IF p_task_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tasks WHERE project_id = p_project_id AND task_id = p_task_id) THEN
    PERFORM _refuse('task not found in project');
  END IF;
  INSERT INTO operator_facts (project_id, fact_key, status, value, task_id, statement, evidence_sha256, subject, issuer, email,
                              auth_time, token_jti, recorded_via)
  VALUES (p_project_id, p_fact_key, p_status, coalesce(p_value, '{}'), p_task_id, p_statement, p_evidence_sha256, p_subject,
          p_issuer, p_email, p_auth_time, p_token_jti, session_user)
  RETURNING fact_id INTO v_id;
  RETURN v_id;
END $$;

-- =====================================================================================================
-- 14. Views
-- =====================================================================================================
CREATE VIEW stale_jobs WITH (security_invoker = true) AS
  SELECT j.job_id, j.project_id, j.task_id, j.attempt, j.role, j.k8s_namespace, j.k8s_job_name, j.phase,
         coalesce(j.last_heartbeat_at, j.started_at, j.created_at) AS last_seen
    FROM job_runs j JOIN projects p ON p.project_id = j.project_id
   WHERE j.phase IN ('created', 'running')
     AND coalesce(j.last_heartbeat_at, j.started_at, j.created_at)
         < now() - make_interval(secs => coalesce((p.limits->>'heartbeat_timeout_seconds')::int, 300));

-- =====================================================================================================
-- 15. Row-level security and grants
-- =====================================================================================================
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['projects', 'project_hard_preconditions', 'project_roles', 'execution_targets', 'tasks',
                           'task_contracts', 'task_dependencies', 'task_interface_contracts', 'task_required_facts',
                           'task_events', 'admission_decisions', 'job_runs', 'test_runs', 'budget_days',
                           'budget_reservations', 'artifacts', 'outbox'] LOOP
    EXECUTE format('ALTER TABLE devplat.%I ENABLE ROW LEVEL SECURITY', r);
    EXECUTE format('CREATE POLICY %I ON devplat.%I FOR SELECT USING (devplat.can_see(project_id))', r || '_visible', r);
  END LOOP;
  FOREACH r IN ARRAY ARRAY['operator_facts', 'reconciliation_runs', 'operator_identities'] LOOP
    EXECUTE format('ALTER TABLE devplat.%I ENABLE ROW LEVEL SECURITY', r);
    EXECUTE format('CREATE POLICY %I ON devplat.%I FOR SELECT USING (project_id IS NULL OR devplat.can_see(project_id))', r || '_visible', r);
  END LOOP;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA devplat FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA devplat FROM PUBLIC;
GRANT USAGE ON SCHEMA devplat TO :"role_controller", :"role_api", :"role_readonly", :"role_model_gateway",
                                 :"role_artifact_gateway", :"role_migrator";

GRANT SELECT ON lifecycles, states, task_kinds, transitions, gate_prerequisites, loop_counters, event_counters,
  gate_providers, evidence_kinds, fact_statuses, env_signals, job_phase_transitions, outbox_operations, artifact_kinds,
  run_object_caps, role_catalogue_versions, roles, projects, project_hard_preconditions, project_roles, execution_targets,
  project_grants, tasks, task_contracts, task_dependencies, task_interface_contracts, task_required_facts, task_events,
  admission_decisions, job_runs, run_uploads, test_runs, budget_days, budget_reservations, artifacts, operator_facts,
  outbox, reconciliation_runs, chain_checkpoints, checkpoint_exports, stale_jobs
  TO :"role_controller", :"role_api", :"role_readonly";
GRANT SELECT ON leases, oidc_issuers, operator_identities TO :"role_controller";
GRANT SELECT ON oidc_issuers, operator_identities TO :"role_api";
GRANT EXECUTE ON FUNCTION can_see(text), verify_chain(text, text), chain_digest(), event_canonical(task_events), event_hash(task_events)
  TO :"role_controller", :"role_api", :"role_readonly";

-- migrator (deploy time): role catalogue and operator identities
GRANT EXECUTE ON FUNCTION load_role_catalogue(text, text, jsonb), set_operator_identities(text, text, jsonb),
  set_mandatory_hard_preconditions(text[]) TO :"role_migrator";

-- controller: functions only
GRANT EXECUTE ON FUNCTION
  upsert_project(text, text, text, text, text, text, text, text, text[], jsonb, numeric, bigint, jsonb, text),
  upsert_execution_target(text, text, text, text, text, text, text, boolean),
  acquire_task_lease(text, text, text, int), release_task_lease(text, text, text, bigint), acquire_lease(text, text, int),
  fence_transfer_task_leases(text, bigint, int),
  create_task(text, text, text, text, text[], text, text, int),
  register_contract(text, text, int, text, jsonb, int, text, text, bigint),
  record_admission(text, text, int, text, text, text, jsonb, text, bigint),
  record_event(text, text, text, int, int, text, bigint, jsonb, text, jsonb, text, jsonb),
  dispatch_job(text, text, int, text, int, bigint, text, bigint, text, text, text, bigint),
  set_job_tokens(bigint, text, text, timestamptz, text, bigint),
  update_job_phase(bigint, text, uuid, text, jsonb, text, bigint),
  job_heartbeat(bigint, uuid),
  record_test_run(bigint, text, text, text, int, text, text, bigint),
  register_artifact(text, text, bigint, text, text, text, bigint, text, text, text),
  expire_artifacts(int),
  enqueue_outbox(text, text, text, text, jsonb), claim_outbox(text, int, int), complete_outbox(bigint, text, text),
  fail_outbox(bigint, text, text, boolean, int),
  start_reconciliation(text, text, text), finish_reconciliation(bigint, text, jsonb, jsonb),
  create_checkpoint(text), record_checkpoint_export(bigint, text, text)
  TO :"role_controller";

GRANT EXECUTE ON FUNCTION record_operator_fact(text, text, text, jsonb, text, text, text, text, text, timestamptz, text, text) TO :"role_api";
GRANT EXECUTE ON FUNCTION reserve_budget(text, text, numeric, bigint), settle_budget(bigint, numeric, bigint),
  release_budget(bigint) TO :"role_model_gateway";
GRANT EXECUTE ON FUNCTION authorize_upload(text, uuid, text, bigint), complete_upload(text, uuid, text, text, bigint)
  TO :"role_artifact_gateway";

INSERT INTO project_grants VALUES ('*', :'role_controller'::regrole), ('*', :'role_api'::regrole);

COMMIT;
RESET ROLE;
