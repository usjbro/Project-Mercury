# MERCURY Agent Communication Protocol: Messages and Schemas

Owner: Agent C (Staff Engineer), with input from Agent B (`integrations/claude.md` §6.1) and Agent E (`security/threat-model.md` §7.3, C-SEC-1, C-SEC-5). Status: Phase 2 design proposal.

Schemas live in [`schemas/`](schemas/). They were generated from one source and checked by a script during design: every file validates against its metaschema; the output contracts pass a strict-subset lint (§5); sample fixtures validate, and a message with an unknown top-level field is rejected. The implementation must re-run these checks in CI (`components.md` §14.3, CT-01/CT-02).

---

## 1. Principles

1. **Agents never produce messages.** Claude and Codex produce only an **output contract** document (a verdict, plan or result), which is validated in four stages (CL §6: V1 SDK/CLI result, V2 schema, V3 binding echo, V4 semantic rules). The coordinator then wraps the validated content in a **message** (the envelope plus a payload that includes IDs, hashes and bindings the coordinator computed). Agents cannot forge IDs, hashes, timestamps or authority. This is what makes "text is never authority" (SEC-302) enforceable.
2. **Two schema families.**
   - *Message schemas* (`<type>.schema.json`, JSON Schema **draft 2020-12**): persisted in `messages`, used for audit, traceability and contract tests. Closed with `unevaluatedProperties: false`.
   - *Output contracts* (`output.<name>.schema.json`, **draft-07 keyword subset**): handed to the agent as `outputFormat` (Claude Agent SDK), `--json-schema` (Claude CLI fallback) or `--output-schema` (Codex). Draft-07 because the Claude SDK validates draft-07 (`02-discovery-agent-runtimes.md` §2.2) and Agents B and E specify draft-07 (CL §6 V2, SEC-303). They use only keywords that mean the same in draft-07 and 2020-12, so a 2020-12 message schema can `$ref` them (verified).
3. **Messages are written in the same transaction as the transition that produces them** (`components.md` §10.2, L4). `dedup_key` is `UNIQUE` in `messages`, so a retried transition cannot emit a duplicate.
4. **Free text is display-only.** Fields named `summary`, `rationale*`, `detail*`, `notes`, `display` and `escalation_reason` are shown to humans or quoted to the next agent as untrusted data. No guard reads them (C-SEC-5). Guards read only enums, IDs, hashes, numbers and booleans.
5. **All messages and outputs are bounded**: every string has `maxLength`, every array has `maxItems` (SEC-303).

---

## 2. Envelope

File: [`schemas/envelope.schema.json`](schemas/envelope.schema.json). Every field is required; "not applicable" is `null`.

| Field | Type | Meaning |
|---|---|---|
| `schema` | `mercury.<type>.v<major>` | Message type and major version, e.g. `mercury.plan.review.v1` |
| `schema_version` | semver | Full version of the message schema used (`1.0.0`) |
| `message_id` | `msg_<ULID>` | Unique message ID |
| `correlation_id` | `tsk_…` or `run_…` | The task ID. For task-less triage messages, the triage run ID |
| `causation_id` | `msg_…` or `null` | The message that caused this one (e.g. `plan.approval` is caused by `plan.review`) |
| `dedup_key` | string, `<type>:<natural key>` | Idempotency key (§4) |
| `occurred_at` | RFC 3339 UTC | When the fact happened (run end, observed merge time) |
| `recorded_at` | RFC 3339 UTC | Transaction time in `mercuryd` |
| `issue` | `JAM-204` or `null` | Linear identifier (prefix never hard-coded) |
| `repo` | `owner/name` or `null` | Target repository |
| `task_id` | `tsk_…` or `null` | Task |
| `run_id` | `run_…` or `null` | Execution that produced the content |
| `producer` | `{kind, name, version}` | Authority that originated the content: `claude`, `codex`, `coordinator`, `operator`, `github`, `linear` |
| `actor` | SEC-601 vocabulary | `coordinator`, `operator`, `claude:<role>`, `codex:<role>`, `github:<login>`, `linear:<user>` (C-SEC-5) |
| `recorded_by` | `{instance_id, app_version}` | Which `mercuryd` instance wrote it (always the coordinator) |
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

| Schema id | File | Producer (authority) | Emitted by transition (`state-machine.md`) | Main consumers |
|---|---|---|---|---|
| `mercury.task.authorization.v1` | [task.authorization](schemas/task.authorization.schema.json) | claude | T02, T37, G1a (Claude revoke), G4, limits amendments | Dispatch guard, audit trace, Linear comment |
| `mercury.task.assignment.v1` | [task.assignment](schemas/task.assignment.schema.json) | coordinator | Every run claim (T05, T12, T14, T28, Claude runs) | Audit ("what exactly was Codex given") |
| `mercury.plan.v1` | [plan](schemas/plan.schema.json) | codex | T06 | Plan review input; approval binding |
| `mercury.plan.review.v1` | [plan.review](schemas/plan.review.schema.json) | claude | T09, T10, T11 | Approval, revision loop, Linear summary |
| `mercury.plan.approval.v1` | [plan.approval](schemas/plan.approval.schema.json) | claude | T09 | Implementation dispatch guard (SM §8.2) |
| `mercury.plan.revision_request.v1` | [plan.revision_request](schemas/plan.revision_request.schema.json) | claude (verbatim review changes or `revision_request` run) | T10, T17, T30, G4 | Codex re-plan prompt |
| `mercury.implementation.progress.v1` | [implementation.progress](schemas/implementation.progress.schema.json) | coordinator (from agent events) | Sampled, ≤ 1 / 60 s / run, phase changes | `mercury status`, stall analysis. Never a guard input |
| `mercury.test.results.v1` | [test.results](schemas/test.results.schema.json) | coordinator (`local_verify`, `ci`); codex (`codex_self_report`, forced `authoritative:false`) | T20, T21, T22, T23 | PR body, Claude PR review, revision loop |
| `mercury.pr.created.v1` | [pr.created](schemas/pr.created.schema.json) | coordinator | First confirmation of PR upsert per head SHA | Audit, Linear link |
| `mercury.code.review.v1` | [code.review](schemas/code.review.schema.json) | claude | T24, T25, T26 | Review binding guard (SM §8.3), GitHub review post |
| `mercury.security.findings.v1` | [security.findings](schemas/security.findings.schema.json) | claude | T24, T25, T26 | Same; security notifications |
| `mercury.revision.request.v1` | [revision.request](schemas/revision.request.schema.json) | claude | T18, T21, T23, T25, T32 (after the instruction exists) | Codex revision prompt |
| `mercury.task.completed.v1` | [task.completed](schemas/task.completed.schema.json) | coordinator | T34, T40 | Linear completion comment, metrics |
| `mercury.task.failed.v1` | [task.failed](schemas/task.failed.schema.json) | coordinator / claude | T03, T04, T08, T11, T13, T19, T26, T29, T35, T39, G1, G2, G5, G6 (`outcome` = `failed`, `cancelled` or `blocked`) | Notifications, operator |
| `mercury.triage.result.v1` | [triage.result](schemas/triage.result.schema.json) | claude | After each validated triage run (no transition; T01 follows for the top *k*) | Triage audit |

Name note: the assignment's "PR creation" and "security findings" map to `pr.created` and `security.findings`; "completion and failure events" map to `task.completed` and `task.failed`. `task.failed` with `outcome: blocked` is the escalation event (BLOCKED is non-terminal).

---

## 4. Dedup keys

`dedup_key = "<type>:<natural key>"`. The natural key identifies the *fact*, so the same fact always produces the same key, whichever code path or restart emits it.

| Message | Natural key |
|---|---|
| `task.authorization` | `<authorization_id>:v<version>` |
| `task.assignment` | `<run_id>` |
| `plan` | `<task_id>:v<plan_version>` |
| `plan.review` | `<run_id>` |
| `plan.approval` | `<plan_id>` (one approval per plan version, I5) |
| `plan.revision_request`, `revision.request` | `<revision_request_id>` |
| `implementation.progress` | `<run_id>:<sequence>` |
| `test.results` | `<source>:<commit_sha>:<run_id or check digest>` |
| `pr.created` | `<repo>#<number>:<head_sha>` |
| `code.review`, `security.findings` | `<run_id>` |
| `task.completed` | `<task_id>` |
| `task.failed` | `<task_id>:<to_state>:<reason_code>:<block_epoch>` |
| `triage.result` | `<run_id>` |

---

## 5. Agent output contracts

These are the documents the agents return. They are strict: every object has `additionalProperties: false`; every property is listed in `required` (optional values are expressed as `null` through type arrays, which satisfies OpenAI structured-output strict mode used by Codex, ASM-C-07); no `$ref`, `oneOf`, `allOf`, `if` or `const` inside the contract (so the same file works for the Claude SDK, the Claude CLI and Codex without bundling); bounded strings and arrays. Before passing a contract to an agent, the adapter removes `$schema` and `$id` (ASM-C-08) and records `schema_sha256` of the exact bytes sent (CL §11).

| Contract id | File | Run kind / decision type | Passed via | Binding echo fields (V3) |
|---|---|---|---|---|
| `mercury.output.triage_proposal.v1` | [output.triage_proposal](schemas/output.triage_proposal.schema.json) | `claude_triage` / `triage` | SDK `outputFormat` | `request_id`, `input_digest`; per entry `issue_id`, `spec_sha256` |
| `mercury.output.task_authorization_decision.v1` | [output.task_authorization_decision](schemas/output.task_authorization_decision.schema.json) | `claude_authorize` / `authorization` | SDK `outputFormat` | `request_id`, `task_id`, `input_digest`, `issue_id`, `repo`, `spec_sha256` |
| `mercury.output.codex_plan.v1` | [output.codex_plan](schemas/output.codex_plan.schema.json) | `codex_plan` | `codex exec --output-schema` | `request_id`, `task_id`, `auth_id`, `base_sha` |
| `mercury.output.plan_review.v1` | [output.plan_review](schemas/output.plan_review.schema.json) | `claude_plan_review` / `plan_review` | SDK `outputFormat` | `request_id`, `task_id`, `input_digest`, `issue_id`, `repo`, `spec_sha256`, `auth_id`, `pln_id`, `plan_sha256` |
| `mercury.output.codex_implementation.v1` | [output.codex_implementation](schemas/output.codex_implementation.schema.json) | `codex_implement`, `codex_revise` | `codex exec --output-schema` | `request_id`, `task_id`, `pln_id`, `plan_sha256` |
| `mercury.output.code_review.v1` | [output.code_review](schemas/output.code_review.schema.json) | `claude_code_review` / `pr_code_review` | SDK `outputFormat` | all of C-SEC-1: `request_id`, `task_id`, `input_digest`, `issue_id`, `repo`, `spec_sha256`, `auth_id`, `pln_id`, `plan_sha256`, `head_sha`, `base_sha`, `diff_sha256` |
| `mercury.output.security_review.v1` | [output.security_review](schemas/output.security_review.schema.json) | `claude_security_review` / `pr_security_review` | SDK `outputFormat` | `request_id`, `task_id`, `input_digest`, `issue_id`, `repo`, `auth_id`, `head_sha`, `base_sha`, `diff_sha256` |
| `mercury.output.revision_request.v1` | [output.revision_request](schemas/output.revision_request.schema.json) | `claude_revision_request` / `revision_request` | SDK `outputFormat` | `request_id`, `task_id`, `input_digest`, `auth_id`, `pln_id`, `plan_sha256` (+ `head_sha` when the source is post-PR) |

`request_id` equals the `run_id` of the decision run (Agent E's `request_id`; one request per run). The coordinator compares every binding field with the value it supplied in the prompt envelope; any mismatch rejects the output and records `security.verdict_binding_mismatch` (TH-04).

### 5.1 Semantic rules enforced in code (V4)

| Contract | Rule |
|---|---|
| All Claude verdicts | `injection_suspected = true` forces `needs_human` (authorization) or `BLOCKED(injection_suspected)` (reviews) regardless of `decision` (TM §7.3) |
| All with findings | Every `path` exists at the bound SHA and `line` is within the file; dropped references counted; > 30 % dropped ⇒ reject as `hallucinated_references` (CL §6) |
| `task_authorization_decision` | `authorize` ⇒ `scope` and `limits` non-null; each `allowed_path_globs` entry is covered by the offered globs; no protected path matches an allowed glob; `max_files_changed`/`max_loc_changed` ≤ offered maxima; limits ≤ config caps; `dependency_changes_allowed` is `false` or `"escalate"` (never `true`, by schema); non-`authorize` ⇒ `scope = null` |
| `plan_review` | `criteria` contains each of the 9 criteria exactly once; `approve` ⇒ no criterion `fail` and no finding with severity `blocking`, `critical` or `high`; `revise` ⇒ ≥ 1 finding with non-null `required_change`; `ac_coverage` lists every AC id parsed from the spec snapshot; `approve` ⇒ all `covered = true` |
| `code_review` | 8 criteria exactly once; `files_reviewed` ⊇ changed files of the diff (SEC-303), otherwise `incomplete_review` (re-run once, then escalate); same approve/revise rules as plan review; `ac_coverage` complete |
| `security_review` | Any `critical` ⇒ escalate (T26); any `high` ⇒ at least `revise`; `approve` ⇒ no `critical`/`high`; `files_reviewed` complete |
| `codex_plan` | `status = ready` or `needs_clarification` (both go to Claude review); AC coverage lists every AC id; `steps` non-empty; `dependencies` non-empty only if authorization allows `escalate` (then flagged for Claude) |
| `codex_implementation` | Advisory only. `files_changed` is compared with the coordinator's own diff; mismatch is recorded, not trusted |
| `revision_request` | `revise`/`replan` ⇒ ≥ 1 instruction; `escalate` ⇒ `escalation_reason` non-null |

### 5.2 How payloads embed output contracts

Message payloads for `plan`, `plan.review`, `code.review`, `security.findings` and `triage.result` carry the validated agent document unchanged in `payload.body` (`$ref` to the contract file), next to the coordinator-computed fields (IDs, `artifact` reference with sha256, reviewer `agent_info`, findings with assigned `fnd_` IDs, validation result). The artifact hash that approvals bind to is `sha256(JCS(body))`, which equals the hash of the stored artifact file because the artifact store writes the JCS form.

---

## 6. Versioning and compatibility

| Rule | Detail |
|---|---|
| V-1 | `schema` carries the **major** version (`.v1`); `schema_version` carries the full semver of the file used. Each schema file has a fixed `$id` per major version (`https://schemas.mercury.local/v1/<file>`) |
| V-2 | **Minor** version: adding an optional-in-meaning field. Because schemas are closed, a minor version is a new file revision that accepts both shapes for messages (new fields nullable), and readers validate a stored message with the schema version recorded in it. The registry keeps every released revision under `schemas/<major>/<semver>/` in the implementation repository |
| V-3 | **Major** version: removing or renaming a field, changing a type, or changing meaning (e.g. what a hash covers). A new major gets a new `schema` id; old messages remain valid under their own schema forever (append-only history) |
| V-4 | **Output contracts** change only together with the adapter and prompt template; the contract version and `schema_sha256` are recorded per run. A contract change is a minor or major version of the contract id and requires re-running the prompt-injection suite (SEC-311) and the adapter contract tests (CT-03) |
| V-5 | **Hash definitions are part of the contract**: `payload_sha256` = SHA-256 of RFC 8785 JCS bytes of `payload`; plan/review artifact hash = SHA-256 of JCS of `body`; `authorizations.payload_sha256` = SHA-256 of JCS of the `task.authorization` payload. Changing any of these is a major version |
| V-6 | Readers accept only majors they know. An unknown major in the DB (downgrade) makes `mercuryd` refuse to start (migration check) |
| V-7 | CI test CT-02: every fixture of minor *n* validates under minor *n + 1* |

---

## 7. Mapping to names used by other agents

| Used elsewhere | This document | Note |
|---|---|---|
| `mercury.triage_proposal.v1` (CL §3) | `mercury.output.triage_proposal.v1` | `output.` prefix separates agent contracts from coordinator messages |
| `mercury.task_authorization_decision.v1` (CL §3), `mercury.authorization_verdict.v1` (TM §7.3) | `mercury.output.task_authorization_decision.v1` | Includes TM §7.3 fields: `issue_id`, `repo`, `spec_sha256`, `allowed_path_globs`, `max_files_changed`, `max_loc_changed`, `dependency_changes_allowed ∈ {false,"escalate"}`, `injection_suspected` |
| `mercury.plan_review.v1`, `mercury.code_review.v1`, `mercury.security_review.v1`, `mercury.revision_request.v1` (CL §3) | `mercury.output.plan_review.v1`, `…code_review.v1`, `…security_review.v1`, `…revision_request.v1` | B's `ClaudeVerdictCommon`: `decision`, `summary`, `findings[]` with `id/category/severity/title/detail/required_change` and location, `injection_suspected` are present. Location is flattened (`path`, `line`, `end_line`) in contracts and nested (`location`) in messages |
| `codex-plan.v1.schema.json`, `codex-impl-result.v1.schema.json` (CX §3) | `output.codex_plan.schema.json`, `output.codex_implementation.schema.json` | — |
| `mercury.test_results.v1`, `mercury.implementation_progress.v1` (CX §8, §10) | `mercury.test.results.v1`, `mercury.implementation.progress.v1` | Dot-separated per the assignment's message list |
| `mercury.authorization_decision.v1` (overview §7.2) | `mercury.output.task_authorization_decision.v1` | — |
| `mercury.failure_decision.v1` (overview §8.2, FAILURE_TRIAGE) | not defined in v1 | Failure triage is optional (`claude_failure_triage` run kind reserved); define the contract if Phase 4 keeps it |
| `audit_events` (SEC-601) | `audit_log` table (`components.md` §6.3) | Same semantics |
