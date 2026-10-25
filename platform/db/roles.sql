-- devplat database roles — bootstrap, run ONCE per cluster by the cluster administrator
-- (in-cluster: the equivalent CloudNativePG `managed.roles` entries; cloud: the provider admin).
-- Status: Proposed (Architecture Amendment 001, R6 D9). Design: docs/mercury/development-orchestration/19-postgresql-state.md §2.
--
--   devplat_migrator        LOGIN  — created by CNPG `bootstrap.initdb.owner` (owns the database). The ONLY identity
--                                    that runs migrations (Helm pre-install/pre-upgrade Job, Secret devplat-db-migrator).
--   devplat_owner           NOLOGIN — owns every devplat object; assumed only via SET ROLE by devplat_migrator.
--   devplat_controller      NOLOGIN group — the controller login is a member; EXECUTE on controller functions only.
--   devplat_api             NOLOGIN group — devplat-api login; records authenticated operator facts, reads.
--   devplat_readonly        NOLOGIN group — dashboards/exporters; reads under row-level security.
--   devplat_model_gateway   NOLOGIN group — model-gateway login; budget reservation functions only.
--   devplat_artifact_gateway NOLOGIN group — artifact-gateway login; upload authorisation functions only.
-- The controller never runs migrations and is never a member of devplat_owner.
--
-- psql -v role_migrator=... [-v role_owner=... ...] -f roles.sql   (names overridable for isolated test runs)

\set ON_ERROR_STOP on
\if :{?role_migrator}
\else
\set role_migrator devplat_migrator
\endif
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
\if :{?role_model_gateway}
\else
\set role_model_gateway devplat_model_gateway
\endif
\if :{?role_artifact_gateway}
\else
\set role_artifact_gateway devplat_artifact_gateway
\endif

SELECT format('DO $x$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %L) THEN '
              'RAISE EXCEPTION ''migrator login %s must exist (CNPG initdb.owner)''; END IF; END $x$', :'role_migrator', :'role_migrator') \gexec
SELECT format('DO $x$ BEGIN IF (SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = %L) THEN '
              'RAISE EXCEPTION ''migrator %s must not be SUPERUSER or CREATEROLE''; END IF; END $x$', :'role_migrator', :'role_migrator') \gexec

SELECT format('CREATE ROLE %I NOLOGIN', r)
  FROM unnest(ARRAY[:'role_owner', :'role_controller', :'role_api', :'role_readonly', :'role_model_gateway',
                    :'role_artifact_gateway']) AS r
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) \gexec
-- the owner can never log in, even if an earlier version created it with LOGIN (R6 S-9)
SELECT format('ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOBYPASSRLS', :'role_owner') \gexec
SELECT format('GRANT %I TO %I', :'role_owner', :'role_migrator') \gexec
