# MERCURY Agent Communication Protocol: Messages and Schemas

Owner: Agent C (Staff Engineer), with input from Agent B (`integrations/claude.md` §6, `integrations/codex.md` §3.6) and Agent E (`security/threat-model.md` §7.3, C-SEC-1, C-SEC-5). Status: **Phase 4 revision** (RD-8, RD-13, RD-15, RD-18; Addenda B and C).

Schemas live in [`schemas/`](schemas/) and are the single source of truth for message payloads and agent output contracts. During design they were checked by script: every file validates against its metaschema; every output contract passes the strict-subset lint (§5.3); sample fixtures validate; a message with an unknown top-level field is rejected. CI re-runs these checks (`components.md` §14.3, CT-01/CT-02).

Not restated here: states and transitions (`architecture/state-machine.md`, **SM**), tables (`architecture/components.md` §6, **CMP**), dedup keys of **inbound facts and outbound operations** (`integrations/github.md` §13, **GH-DEDUP**; a separate namespace from the message dedup keys of §4).

---

## 1. Principles

1. **Agents never produce messages.** Claude and Codex produce only an **output contract** document (a verdict, plan or result), validated in four stages (CL §6: V1 SDK/CLI result, V2 schema against the **canonical** contract, V3 binding echo, V4 semantic rules). The coordinator wraps the validated content in a **message** with IDs, hashes and bindings it computed itself. Agents cannot forge IDs, hashes, timestamps or authority (SEC-302).
2. **Two schema families.**
   - *Message schemas* (`<type>.schema.json`, JSON Schema **draft 2020-12**): persisted in `messages`, used for audit and contract tests. Closed with `unevaluatedProperties: false`.
   - *Output contracts* (`output.<name>.schema.json`, **draft-07 keyword subset**): the canonical contract the coordinator validates with Ajv. Providers receive a generated **wire copy** per provider profile (§5.3), never the canonical file.
3. **Messages are written in the same transaction as the transition that produces them** (CMP §10.2, L4). `dedup_key` is `UNIQUE` in `messages`.
4. **Free text is display-only.** Fields named `summary`, `rationale*`, `detail*`, `notes`, `display`, `*_display` and `escalation_reason` are shown to humans or quoted to the next agent as untrusted data; no guard reads them (C-SEC-5). Agent text sent to public sinks passes the `NeutralisedText` renderer (CMP §4.16).
5. **All messages and canonical outputs are bounded**: every string has `maxLength`, every array `maxItems` (SEC-303). Bounds removed from a wire copy are still enforced at V2.

---

## 2. Envelope

File: [`schemas/envelope.schema.json`](schemas/envelope.schema.json). Every field is required; "not applicable" is `null`.

| Field | Type | Meaning |
|---|---|---|
| `schema` | `mercury.<type>.v<major>` | Message type and major version |
| `schema_version` | semver | Full version of the schema file used |
| `message_id` | `msg_<ULID>` | Unique message ID |
| `correlation_id` | `tsk_…` or `run_…` | The task ID; for task-less triage messages, the triage run ID |
| `causation_id` | `msg_…` or `null` | The message that caused this one |
| `dedup_key` | `<type>:<natural key>` | Idempotency key (§4) |
| `occurred_at` / `recorded_at` | RFC 3339 UTC | Fact time / transaction time |
| `issue`, `repo`, `task_id`, `run_id` | ids or `null` | Correlation |
| `producer` | `{kind, name, version}` | Authority that originated the content: `claude`, `codex`, `coordinator`, `operator`, `github`, `linear` |
| `actor` | SEC-601 vocabulary | `coordinator`, `operator`, `claude:<role>`, `codex:<role>`, `github:<login>`, `linear:<user>` |
| `recorded_by` | `{instance_id, app_version}` | The `mercuryd` instance that wrote it |
| `payload_sha256` | hex | `sha256(JCS(payload))` |
| `payload` | object | Type-specific, closed |

Example (abbreviated payload):

```json
{
  "schema": "mercury.plan.approval.v1",
  "schema_version": "1.0.0",
  "message_id": "msg_01JA7Q2M5V3K8N1R4T6W9Y0B2C",
  "correlation_id": "tsk_01JA7P9X2C4E6G8J0L2N4Q6S8U",
  "causation_id": "msg_01JA7Q2M5T0F2H4K6M8P0R2T4V",
  "dedup_key": "plan.approval:pln_01JA7Q0A1B2C3D4E5F6G7H8J9K",
  "occurred_at": "2026-10-12T14:03:05.120Z",
  "recorded_at": "2026-10-12T14:03:05.123Z",
  "issue": "JAM-204",
  "repo": "usjbro/network_monitor",
  "task_id": "tsk_01JA7P9X2C4E6G8J0L2N4Q6S8U",
  "run_id": "run_01JA7Q1Z9Y8X7W6V5T4S3R2Q1P",
  "producer": { "kind": "claude", "name": "claude-agent-sdk", "version": "0.3.296" },
  "actor": "claude:plan_reviewer",
  "recorded_by": { "instance_id": "ins_01JA7N0000000000000000000A", "app_version": "0.1.0" },
  "payload_sha256": "3f1c…(64 hex)",
  "payload": {
    "approval_id": "apr_01JA7Q2M5W…",
    "plan": { "plan_id": "pln_01JA7Q0A1B…", "version": 2, "sha256": "9b2e…" },
    "review_id": "rev_01JA7Q1ZB…",
    "authorization": { "authorization_id": "auth_01JA7PA…", "version": 1, "scope_version": 1, "payload_sha256": "77ad…" },
    "approval_conditions": ["Add a regression test for the empty-capture case (AC-3)"],
    "approved_by": { "agent": "claude", "run_id": "run_01JA7Q1Z9Y…", "model": "claude-opus-5-5", "agent_version": "2.1.296", "session_id": "6f0c…" }
  }
}
```

Shared definitions (IDs, hashes, `artifact_ref`, `authorization_ref`, `plan_ref`, `pr_ref`, `agent_info`, `finding`, `location`, `severity`, `task_state`) are in [`schemas/common.schema.json`](schemas/common.schema.json).

---

## 3. Message catalogue

Transition IDs refer to SM §3.

| Schema id | File | Producer (authority) | Emitted by | Main consumers |
|---|---|---|---|---|
| `mercury.task.authorization.v1` | [task.authorization](schemas/task.authorization.schema.json) | claude | T02; re-authorization outcomes (SM §8.1.1: same-scope, amend scope / G4, revoke / G1a); T37 | Dispatch and apply-time guard, audit trace, Linear comment. Payload carries `mode` (`initial`/`reauthorize`), `trigger`, `amendment_kind` (`limits`/`spec_confirm`/`scope`), `models_used` |
| `mercury.task.assignment.v1` | [task.assignment](schemas/task.assignment.schema.json) | coordinator | Every run claim (T05, T12, T14, T28, Claude runs) | Audit ("what exactly was the agent given"); carries `exec_uid`, `snapshot_tree_sha`, per-task `codex_home` |
| `mercury.plan.v1` | [plan](schemas/plan.schema.json) | codex | T06 | Plan review input; approval binding |
| `mercury.plan.review.v1` | [plan.review](schemas/plan.review.schema.json) | claude | T09, T10, T11 | Approval, revision loop; carries `snapshot_tree_sha` |
| `mercury.plan.approval.v1` | [plan.approval](schemas/plan.approval.schema.json) | claude | T09 | Implementation guard (SM §8.2) |
| `mercury.plan.revision_request.v1` | [plan.revision_request](schemas/plan.revision_request.schema.json) | claude (verbatim render or `revision_request` run; `producer` field, RD-8) | T10, T17, T30, G4 | Codex re-plan prompt |
| `mercury.implementation.progress.v1` | [implementation.progress](schemas/implementation.progress.schema.json) | coordinator (from agent events) | Sampled, phase changes | `mercury status`. Never a guard input |
| `mercury.test.results.v1` | [test.results](schemas/test.results.schema.json) | coordinator (`local_verify`, `ci`); codex (`codex_self_report`, `authoritative: false`) | T20, T21, T22, T23 | PR body, Claude PR review, revision loop |
| `mercury.pr.created.v1` | [pr.created](schemas/pr.created.schema.json) | coordinator | First confirmation of a PR upsert per head | Audit, Linear link |
| `mercury.policy.escalation.v1` *(new)* | [policy.escalation](schemas/policy.escalation.schema.json) | coordinator (opened, carried forward, superseded); operator (acknowledged via presence tier, rejected) | T20, T42, T43, new head | PL check, policy guard (SM §8.7), audit question 8 |
| `mercury.code.review.v1` | [code.review](schemas/code.review.schema.json) | claude | T24, T24p, T25, T25c, T26 | Review binding guard (SM §8.3); `github_review.event` is **`COMMENT` only** (RD-5); carries `snapshot_tree_sha` |
| `mercury.security.findings.v1` | [security.findings](schemas/security.findings.schema.json) | claude | T24, T24p, T25, T25c, T26 | Same; security notifications |
| `mercury.revision.request.v1` | [revision.request](schemas/revision.request.schema.json) | claude (verbatim render or `revision_request` run) | T18, T21, T23, T25, T25c, T32, T43 (after the instruction exists) | Codex revision prompt |
| `mercury.task.completed.v1` | [task.completed](schemas/task.completed.schema.json) | coordinator | T34, T40 | Linear completion comment, metrics; `verification.result` `passed`/`waived`, `scope_action`, `control_kind` |
| `mercury.task.failed.v1` | [task.failed](schemas/task.failed.schema.json) | coordinator / claude | T03, T04, T08, T11, T13, T19, T24p, T26, T29, T35, T39, G1, G2, G5, G6 (`outcome` = `failed`, `cancelled` or `blocked`) | Notifications; `presence_required_actions` lists ★ actions (RD-12) |
| `mercury.triage.result.v1` | [triage.result](schemas/triage.result.schema.json) | claude | After each validated triage run | Triage audit |

`task.failed` with `outcome: blocked` is the escalation event (`BLOCKED` is non-terminal).

### 3.1 Revision-request provenance (RD-8)

Both revision messages carry `producer = {kind, template_sha256, instruction_run_id}`, `source_review_ids[]` and `source_sha256s[]`:

| `producer.kind` | When | Rules |
|---|---|---|
| `verbatim_render` | Source is a validated Claude plan or PR review bound to the current plan hash / head SHA (`claude_plan_review`, `claude_code_review`, `claude_security_review`) | The `required_change` items are rendered verbatim through a fixed template whose hash is `template_sha256`; the coordinator chooses no words; `source_review_ids`/`source_sha256s` name the bound reviews; `instruction_run_id = null` |
| `claude_revision_request` | Every other source: `local_tests`, `ci`, `merge_conflict`, `human_review`, `diff_gate`, `codex_deviation` (incl. Codex `blocked`), `codex_incomplete`, `conflicting_reviews`, `review_needs_plan_change`, `policy_rejected`, `authorization_amended` | A Claude `revision_request` run produced the instructions (`instruction_run_id`); CI logs and human text reach Codex only through it (RD-8, T4) |

---

## 4. Message dedup keys

`dedup_key = "<type>:<natural key>"`. The natural key identifies the *fact*, so the same fact always produces the same key. These keys apply to the `messages` table only; inbox facts and outbox operations use GH-DEDUP.

| Message | Natural key |
|---|---|
| `task.authorization` | `<authorization_id>:v<version>` |
| `task.assignment` | `<run_id>` |
| `plan` | `<task_id>:v<plan_version>` |
| `plan.review` | `<run_id>` |
| `plan.approval` | `<plan_id>` (one approval per plan version, INV-05) |
| `plan.revision_request`, `revision.request` | `<revision_request_id>` |
| `implementation.progress` | `<run_id>:<sequence>` |
| `test.results` | `<source>:<commit_sha>:<run_id or check digest>` |
| `pr.created` | `<repo>#<number>:<head_sha>` |
| `policy.escalation` | `<escalation_id>:<event>` |
| `code.review`, `security.findings` | `<run_id>` |
| `task.completed` | `<task_id>` |
| `task.failed` | `<task_id>:<to_state>:<reason_code>:<block_epoch>` |
| `triage.result` | `<run_id>` |

---

## 5. Agent output contracts

### 5.1 Contracts

Every canonical contract is closed (`additionalProperties: false`), lists every property in `required` (optional values are `null` through type arrays), gives every `enum` an explicit `type`, uses no `$ref`, `oneOf`, `anyOf`, `allOf`, `if` or `const`, and bounds every string and array.

| Contract id | File | Run kind / decision type | Binding echo fields (V3) |
|---|---|---|---|
| `mercury.output.triage_proposal.v1` | [output.triage_proposal](schemas/output.triage_proposal.schema.json) | `claude_triage` / `triage` | `request_id`, `input_digest`; per entry `issue_id`, `spec_sha256` |
| `mercury.output.task_authorization_decision.v1` | [output.task_authorization_decision](schemas/output.task_authorization_decision.schema.json) | `claude_authorize` / `authorization` (modes `initial`, `reauthorize`) | `request_id`, `task_id`, `input_digest`, `issue_id`, `repo`, `spec_sha256`, `mode`, `prior_auth_payload_sha256` |
| `mercury.output.codex_plan.v1` | [output.codex_plan](schemas/output.codex_plan.schema.json) | `codex_plan` | `request_id`, `task_id`, `auth_id`, `base_sha` |
| `mercury.output.plan_review.v1` | [output.plan_review](schemas/output.plan_review.schema.json) | `claude_plan_review` / `plan_review` | `request_id`, `task_id`, `input_digest`, `issue_id`, `repo`, `spec_sha256`, `auth_id`, `pln_id`, `plan_sha256` |
| `mercury.output.codex_implementation.v1` | [output.codex_implementation](schemas/output.codex_implementation.schema.json) | `codex_implement`, `codex_revise` | `request_id`, `task_id`, `auth_id`, `pln_id`, `plan_sha256` |
| `mercury.output.code_review.v1` | [output.code_review](schemas/output.code_review.schema.json) | `claude_code_review` / `pr_code_review` | C-SEC-1: `request_id`, `task_id`, `input_digest`, `issue_id`, `repo`, `spec_sha256`, `auth_id`, `pln_id`, `plan_sha256`, `head_sha`, `base_sha`, `diff_sha256` |
| `mercury.output.security_review.v1` | [output.security_review](schemas/output.security_review.schema.json) | `claude_security_review` / `pr_security_review` | Same set as code review (now including `spec_sha256`, `pln_id`, `plan_sha256`, RC-32) |
| `mercury.output.revision_request.v1` | [output.revision_request](schemas/output.revision_request.schema.json) | `claude_revision_request` / `revision_request` | `request_id`, `task_id`, `input_digest`, `auth_id`, `pln_id`, `plan_sha256` (+ `head_sha` when post-PR) |

`spec_sha256` is B's `spec_hash` (`integrations/linear.md` §5). `request_id` equals the decision run's `run_id`. Any binding mismatch rejects the output and records `security.verdict_binding_mismatch` (class `binding_mismatch`, GH §15.1).

### 5.2 Semantic rules enforced in code (V4)

| Contract | Rule |
|---|---|
| All Claude verdicts | `injection_suspected = true` forces `needs_human` (authorization) or `BLOCKED(injection_suspected)` (reviews) |
| All with findings | Every `path` exists at the bound SHA (in the snapshot) and `line` is within the file; > 30 % dropped ⇒ reject as `hallucinated_references` |
| `task_authorization_decision` | `mode = initial` ⇒ `decision ∈ {authorize, decline, defer, needs_spec, needs_human}`; `mode = reauthorize` ⇒ `decision ∈ {reauthorize_same_scope, amend_scope, revoke, needs_human}` (SM §8.1.1); `authorize`/`reauthorize_same_scope`/`amend_scope` ⇒ `scope` and `limits` non-null, globs covered by the offered template, no protected path allowed, limits ≤ config caps, `dependency_changes_allowed ∈ {false, "escalate"}`; `reauthorize_same_scope` ⇒ `scope` equal to the current scope; `amend_scope` ⇒ `scope` differs; other decisions ⇒ `scope = null` |
| `plan_review` | 9 criteria exactly once; `approve` ⇒ no criterion `fail` and no `blocking`/`critical`/`high` finding; `revise` ⇒ ≥ 1 finding with `required_change`; AC coverage complete |
| `code_review` | 8 criteria exactly once; `files_reviewed` ⊇ changed files (else `incomplete_review`: re-run once, then escalate); same approve/revise rules |
| `security_review` | Any `critical` ⇒ escalate (T26); any `high` ⇒ at least `revise`; `approve` ⇒ no `critical`/`high`; `files_reviewed` complete |
| `codex_plan` | `steps` non-empty; AC coverage lists every AC id; `dependencies` non-empty only if the authorization allows `escalate` |
| `codex_implementation` | Advisory. `files_changed` compared with the coordinator's own diff. `status` mapping (SM T15–T18): `completed` → commit pipeline; `needs_plan_change` → T17; `blocked` → T18 source `codex_deviation`; `partial` → class `incomplete` (one resume), then T18 source `codex_incomplete` |
| `revision_request` | `revise`/`replan` ⇒ ≥ 1 instruction; `escalate` ⇒ `escalation_reason` non-null |
| Authority decisions | The result's actual model ids equal the requested model (no `fallbackModel`, RD-18); otherwise `output_invalid` |

### 5.3 Wire copies and the generator (RD-15)

The canonical files are **never sent to a provider**. `scripts/gen-wire-schemas.ts` (C owns; runs in CI and at build) emits one wire copy per contract and provider profile into `schemas/wire/<profile>/`, plus a manifest of their SHA-256s. The coordinator copies the wire file into `runs/<run_id>/in/` and records the canonical `schema_id` and the wire `schema_sha256` on the run (CMP §6.3 `runs.schema_id`, `schema_sha256`).

| Profile | Used by | Transformation (normative text in CL §6.1 and CX §3.6) |
|---|---|---|
| `claude-sdk` | Agent SDK `outputFormat` | Remove `$schema`, `$id`; keep draft-07 keywords |
| `anthropic-messages` | ALT-B-1 (Messages API) | Also remove `minLength`, `maxLength`, `minimum`, `maximum`, `minItems` > 1; restate removed bounds in `description`; fail the build if per-request optional/union limits are exceeded |
| `codex-strict` | Codex `--output-schema` | Remove `$schema`, `$id`, `minLength`, `maxLength`, `minimum`, `maximum` and any `minItems`/`maxItems` the Phase 0 probe rejects; restate bounds in `description`; explicit `type` beside every `enum` (already true of the canonical files) |

Rules: (1) full validation (V2) always uses the canonical file with Ajv; (2) a provider rejection of a wire schema at request time is `config_fatal` for that decision type, never retried; (3) the canonical files themselves stay inside the strict subset of §5.1, so the generator only strips keywords; (4) CT-01 lints every wire copy against its profile and checks the manifest; Phase 0 probes send each wire copy to the pinned CLI (ASM-B-61, CL §8).

Known edge: `dependency_changes_allowed` is typed `["boolean", "string"]` with enum `[false, "escalate"]` (E's TM §7.3 shape). If the `codex-strict` or `anthropic-messages` probe rejects a mixed-type enum, the generator emits `{"type": "string", "enum": ["none", "escalate"]}` in the wire copy and the adapter maps `"none"` back to `false` before V2.

### 5.4 How payloads embed output contracts

Message payloads for `plan`, `plan.review`, `code.review`, `security.findings` and `triage.result` carry the validated agent document unchanged in `payload.body` (`$ref` to the canonical contract), next to coordinator-computed fields (IDs, artifact reference with sha256, reviewer `agent_info`, findings with `fnd_` IDs, validation result, `snapshot_tree_sha`). The artifact hash that approvals bind to is `sha256(JCS(body))`, which equals the stored artifact's hash.

---

## 6. Versioning and compatibility

| Rule | Detail |
|---|---|
| V-1 | `schema` carries the major version; `schema_version` the full semver of the file used; each file has a fixed `$id` per major version |
| V-2 | **Minor**: additive change. Readers validate a stored message with the schema version recorded in it; the registry keeps every released revision under `schemas/<major>/<semver>/` in the implementation repository. The Phase 4 changes are part of the unreleased `1.0.0` (no implementation exists yet) |
| V-3 | **Major**: removing or renaming a field, changing a type or a meaning (e.g. what a hash covers) |
| V-4 | Output contracts change only with the adapter, the prompt template and the regenerated wire copies; the contract version and wire `schema_sha256` are recorded per run; a change re-runs the prompt-injection suite (SEC-311) and CT-03 |
| V-5 | Hash definitions are part of the contract (`payload_sha256`, artifact hash = JCS of `body`, `authorizations.payload_sha256`); changing one is a major version |
| V-6 | Readers accept only majors they know; an unknown major in the DB makes `mercuryd` write `fatal.json` and exit 0 (MS §5.2) |
| V-7 | CT-02: every fixture of minor *n* validates under minor *n + 1* |

---

## 7. Mapping to names used by other agents

| Used elsewhere | This document / canonical | Note |
|---|---|---|
| `mercury.triage_proposal.v1`, `mercury.task_authorization_decision.v1`, `mercury.plan_review.v1`, `mercury.code_review.v1`, `mercury.security_review.v1`, `mercury.revision_request.v1` (CL §3) | `mercury.output.<name>.v1` | `output.` prefix separates agent contracts from messages |
| `mercury.authorization_verdict.v1` (TM §7.3), `mercury.authorization_decision.v1` (overview) | `mercury.output.task_authorization_decision.v1` | Includes TM §7.3 fields |
| `codex-plan.v1.schema.json`, `codex-impl-result.v1.schema.json` | `output.codex_plan.schema.json`, `output.codex_implementation.schema.json` | Wire copies: `schema.<contract>.wire.json` in the run's `in/` dir (CX §3.6) |
| `mercury.test_results.v1`, `mercury.implementation_progress.v1` | `mercury.test.results.v1`, `mercury.implementation.progress.v1` | Dot-separated |
| `mercury.failure_decision.v1` (FAILURE_TRIAGE) | **withdrawn** | No failure-triage decision in v1 (RA-11); exhausted failures go to `BLOCKED(run_exhausted)` |
| `inbound_events`, `outbound_ops`, `side_effects`, `agent_runs`, `instance_lease` | `events_inbox`, `outbox`, `outbox`, `runs`, `flock` + `leases` | CMP §6.3 is canonical |
| `audit_events` (SEC-601) | `audit_log` (+ `audit_epochs`, `anchors`) | ADR-018 |
| Phase 2 invariants `I1…I20` | `INV-01…INV-20` (+ `INV-21…27`) | SM §4 |
