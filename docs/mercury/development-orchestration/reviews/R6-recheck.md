# R6 — Independent re-check of the fix round

Status: **Closed offline** (2026-10-23). The re-check reviewed `ea13dd5`; the fixes are in `c249c51`; the confirmation pass on `c249c51` (§6) accepted with conditions, and both conditions are fixed in the commit after it. Runtime verification remains (R-2).

## 1. Reviewers and verdicts

| Review | Brief | Ran at `ea13dd5` | Verdict |
|---|---|---|---|
| Architecture and consistency | `.claude/agents/mdev-lead-architect.md`, read-only, fresh context (did not write the fixes) | validate_projects 2/2 + self-test 49/49; schema 7; roles 9; jobspec 13; DB 49 | **changes_required**: 1 new High (RA-1), 6 Medium, 9 Low. A-01…A-04, A-06, A-07 closed offline; A-05 partly closed, as stated |
| Security | `.claude/agents/mdev-security-engineer.md`, read-only, fresh context | `validate_all.sh --strict` exit 0; admission 128 CEL / 115 cases / 0 mismatches; 8 own admission exploits (all allowed); 2 DB exploits (both reproduced) | **changes_required**: S-1 not closed even offline (RS-1, High); 5 Medium, 3 Low. S-2 closed for exec/build, partly for test namespaces; S-3 operator-only, as stated |

## 2. Findings and fixes

| ID | Sev | Finding | Fix | Check |
|---|---|---|---|---|
| RA-1 | **High** | `jobspec.py` Job name and idempotency key omit the role. The implementer's and the verifier's Jobs of one attempt and dispatch collided: `dispatch_job()` refused the second ("idempotency key collision"), so G2 could never pass. The DB tests hid it (random keys in the helper) | Role in both formulas: `dp-<project>-<task>-a<attempt>-<role>-d<dispatch>` (role without the `mdev-` prefix) and `sha256(project\|task\|core\|attempt\|role\|dispatch)`; fixture, doc 16 example, docs 15/21/24, ADR-024, chart comment and VAP message updated. The DB test helper now uses the `jobspec.py` formulas | job: `test_roles_of_one_attempt_get_distinct_names_and_keys`; db: `test_assigned_role_and_verifier_jobs_of_one_attempt` (fails with "idempotency key collision" under the old formulas, mutation-checked) |
| RS-1 | **High** | D12 policy did not cover image/document content blocks with `source.type: url` (the provider fetches an agent-chosen URL: exfiltration and instruction intake) and rejected server tools by a denylist | Allowlists fixed by the chart schema: `allowedToolTypes: [custom]` (a tool passes only without `type` or with `custom`), `allowedContentSourceTypes: [base64, text]`, `rejectFileReferences: true`. Doc 18 K-13 and PI-9, ADR-025 item 7, doc 16 V-16-3, doc 22 probe N13, chart comment updated | chart: "model-gateway URL content source (RS-1)", "… server tool type allowed (RS-1)", "… file references allowed (RS-1)". Runtime: gateway parser not built (V-16-3) |
| RS-2 | Medium | Namespacer could create `default-deny-all` selecting nothing or Ingress-only, and `allow-deps` for every pod: open egress for agent-written test code | VAP `devplat-namespacer-scope`: `default-deny-all` must be `podSelector {}`, `[Ingress, Egress]`, no rules; `allow-deps` must select exactly `network-class: deps`. Doc 18 §9.3 states the residual: existence of the policies is not enforced by admission; the controller must observe all five, and a cluster baseline deny is recommended for DP4 | adm: `RS2-default-deny-selects-nothing`, `-ingress-only`, `-with-allow-rule`, `-matchExpressions`, `RS2-allow-deps-all-pods` (all deny); existing `ok-` cases still allow |
| RS-3 | Medium | Extra test-namespace labels allowed (`devplat.io/ingress-gateway`, old PSA versions) | Exact label set on create: managed-by, ns-role, project, `kubernetes.io/metadata.name`, PSA enforce/audit/warn `restricted` at `v1.33` or `latest` | adm: `RS3-ingress-gateway-label`, `RS3-old-psa-version`, `RS3-psa-warn-baseline`, `RS3-psa-audit-missing` (deny), `ok-RS3-metadata-name-label` |
| RS-4 | Medium | Artifact gateway had no DB login, Secret, env or network path, so `authorize_upload()` could not be called | CNPG managed role `devplat_artifact_gateway` (Secret `devplat-db-artifact-gateway`), `dbEnv` in the template, base pinning map entry, NetworkPolicy egress to PostgreSQL and ingress on `postgres`; docs 18, 24, NOTES, values | chart: new `db-paths` check over every DB-authorized component (fails when the gateway's DB env is removed, mutation-checked); secret pinning; base strict |
| RS-5 | Medium | The controller chose the hard-precondition list (exploit: activate with `['note']`); the DB accepted `linear_write_fact = 'DOD-02'` | `mandatory_hard_preconditions`, set only by the migration Job (`set_mandatory_hard_preconditions`, env `DEVPLAT_MANDATORY_HARD_PRECONDITIONS=DOD-02,DOD-13`); `upsert_project()` refuses a list without them and a write fact that is a hard precondition or `REDUCED-ASSURANCE`; K-10 updated | db: `test_controller_cannot_drop_mandatory_hard_preconditions` (2 mutations caught) |
| RA-2 | Medium | Doc 16 §2 diagram still showed the gateway minting the upload token | Redrawn per doc 21 §1 item 4: admission → `dispatch_job` → `set_job_tokens` → suspended Job → ConfigMap/Secret → `:9444` register → unsuspend → `dispatched`; gateways authorize in PostgreSQL | — |
| RA-3 | Medium | Contract v2 `dependencies[].project_id` was stored under the wrong project | `register_contract()` refuses a dependency on another project ("not implemented") and an unknown dependency task; docs 15, 16, 17 and both schema descriptions say cross-project dependencies are designed only | db: `test_cross_project_dependency_refused` |
| RA-4 | Medium | DOD-13 row still said the App has "no merge or approval" | Row corrected (S-14) | — |
| RA-5 | Medium | Docs 26 and 15 still described the old A-05 position | Aligned with doc 16 §9.1; direction stated as subject to the operator's review | — |
| RA-6 | Medium | HANDOFF stale | Rewritten to the current head (`HANDOFF.md`) | — |
| RA-7 | Low–Med | Environment `task_kinds` lacked `plan_proposal` | Enum value added (minor 2), field vocabulary documented, Mercury `k8s-exec` lists it | config validator |
| RA-8 | Low | Verifier exemption in `dispatch_job()` could never take effect | Removed (fail-safe); doc 17 rule 5 says every role passes checks 1–2 | DB suite |
| RA-9 | Low | `tools` split broke `Agent(a, b)`; planner allow list held role names | Parenthesis-aware split | roles: `test_planner_settings_parse_agent_parentheses` (mutation-checked) |
| RA-10 | Low | ConfigMap name hashes data only | Accepted and documented (doc 16 §9.1) | — |
| RA-11 | Low | `--agent planner` vs frontmatter name | V-16-1 states the runner passes the frontmatter `name` | runtime (V-16-1) |
| RA-12…RA-15 | Low | "until DOD-05" wording; doc 25 v1 keys; doc 22 `builds.images`; doc 29 count | Corrected (docs 15, 18, 22, 25, 28, 29, api chart comment, `mercury.yaml` DevOps ref) | — |
| RA-16 | Low | Project section lacked branch prefix and commit trailers; rules 6 and 8 could conflict | "Branches and commits" row; rule 6 defers to rule 8 for documents | roles: `test_branch_and_trailer_rows` |
| RS-6 | Low | Config text inserted into prompts unescaped | Collapsed to one inert line, backticks replaced | roles: `test_config_text_cannot_inject_markdown` (mutation-checked) |
| RS-7 | Low | H8 not checked | `validate_projects.py` requires `.github/**` in `restricted_paths` for non-draft projects (`docs/**` stays DOD-23) | cfg: ".github/** not restricted" (self-test 50/50) |
| RS-8 | Low | `openai` provider allowed with any host | Chart schema: provider `anthropic` at `api.anthropic.com` only | chart: "model-gateway second provider (RS-8)" |
| RS-9 | Low | `dispatch_job()` with a NULL target does not tie the namespace to the project | **Not fixed** (mitigated by the `job-shape` VAP project label check); residual R-6 | — |

## 3. Disposition corrections

`R6-dispositions.md` is updated accordingly: A-23 reopened and closed by RA-1; S-1 closed in config only after RS-1; S-2 and S-6 cite RS-2/RS-3/RS-4; A-01/S-5 cite RS-5; A-02 notes cross-project dependencies; S-9 states the residual (the migrator login is the CNPG `initdb.owner` and a member of `devplat_owner`, so it can still rewrite `task_events`; detected only by the hash chain and DOD-18 signing); S-12 notes that publish/adduser being disabled is fixed in the template, not tested.

## 4. Evidence after the fixes

`platform/tools/validate_all.sh --strict` (2026-10-23): **ALL CHECKS PASSED (nothing skipped), exit 0** — devorch 30; jobspec 14; contract v2 rules 7; project configs 2/2 + self-test 50/50; base 140 valid; role ConfigMap tests 12; DB on real PostgreSQL 16 52; admission 131 CEL expressions compiled, 125 cases / 143 decisions, 0 mismatches; charts 56 passed, 0 failed, 0 skipped. All offline.

## 5. Remaining before operator review

Residuals in `R6-dispositions.md` §4 (R-1 neutral role bodies, R-2 runtime, R-3, R-5 operator decisions, R-6 RS-9, R-7 cluster baseline deny).

## 6. Confirmation pass (same reviewers, read-only, at `c249c51`)

| Review | Verdict | Re-ran |
|---|---|---|
| Architecture | **accept_with_conditions**: RA-1…RA-16 fixed; RA-1 verified end to end (112 generated names for every role plus `verifier` at maximum id lengths: unique, valid, ≤ 54 characters) | validate_projects 2/2, self-test 50/50, schema 7, roles 12, jobspec 14, DB 52 |
| Security | **accept_with_conditions**: RS-1…RS-8 fixed; RS-9 residual agreed; bypass attempts against the RS-1 spec (url image inside `tool_result`, nested document sources, `container_upload`, server-like custom tool names) all covered | `validate_all.sh --strict` exit 0; admission 0 mismatches; own 8 admission exploits (5 now denied, 3 not exploitable: blocked by other controls); 2 DB exploits refused |

| ID | Sev | Condition | Fix | Check |
|---|---|---|---|---|
| RC-1 | Medium | Evidence-manifest alias `manifests/<task>/<attempt>/<dispatch>.json` had no role (same class as RA-1) and gate manifests shared it | `manifests/<task>/<attempt>/<role>-d<dispatch>.json` and `…/gate-G<n>.json`; DB alias regex, unique `(project_id, alias_key)` index and an explicit refusal; docs 16, 19, 20, ADR-026 | db: `test_artifact_immutability_bucket_and_caps` (role-less form refused, alias reuse refused, re-registration idempotent) |
| C-1 | Medium | Content-block types and top-level request fields still screened by a denylist | Chart schema `allowedContentBlockTypes` and `allowedRequestFields` (const); doc 18 K-13, ADR-025, doc 22 N13 | chart: "model-gateway extra content block type (C-1)", "… extra request field (C-1)" |
| RC-2 | Low | Doc 20 example manifest used the old Job name | Updated, with `role` | — |
| RC-4 | Low | Mercury uses a minor-2 value but declared `schema_minor: 1` | `schema_minor: 2` | validator |
| RC-3 | Low | Admission fixtures use old Job names (valid for the loose name regex) | Not changed (cosmetic) | — |
