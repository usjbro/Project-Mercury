# Phase 4 Revision — Agent C (Staff/Principal Engineer): disposition

Scope: `architecture/components.md`, `architecture/state-machine.md`, `protocols/messages.md`, `protocols/schemas/*.json`. Implements `reviews/30-reconciliation.md` RD-1…RD-20 and Addenda A–C. Schemas re-validated with `jsonschema` 4.26 (metaschema for all 26 files, strict-subset lint for the 8 output contracts incl. explicit `type` beside every `enum`, `$ref` resolution, Phase 2 fixtures updated) and all Mermaid blocks parsed with `mermaid` (8/8 ok).

## 1. Summary of changes per document

**state-machine.md (rewritten)**
- Single-source table at the top; operational values cited by MS-PARAM names (`run.<kind>.*`, `wake.*`, `disk.*`, `hold_age.*`); workflow policy (attempts, backoff, budgets, reminder timers) kept here (Addendum B §4).
- Brief-name → design mapping incl. `Discovered` as `linear_issues.mercury_status` (RD-14); mode-dependent Linear projection (RD-9).
- Gate checks: new §2.3 diagram; `github.check.upsert` on T20 (CR `queued`, PL `success`/`action_required`), T22 (`in_progress`), T24/T24p (`success`), T25 (`failure`), T26 / every BLOCKED-with-PR / G5 / cancel (`action_required`); never `neutral`/`skipped` (Addendum C). T25 posts `COMMENT` only (RC-01).
- Policy gate: T24p → `BLOCKED(policy_ack_required)`, T42 `policy ack` (presence ★), T43 `policy reject`; policy guard §8.7 with carry-forward on identical protected-blob digest (RC-03, RD-14).
- Spec drift: **AG@apply** — the authorization guard incl. `spec_sha256` runs at result-application time; results `deferred`/`discarded`; re-authorization outcomes `reauthorize_same_scope` / `amend_scope` / `revoke` / `needs_human` (RD-13, RA-05, RC-04, RE-14).
- New transitions T41 (behind base → coordinator merge commit, RC-12), T25c (conflicting reviews / plan change → Claude consolidation, RD-8), T24p, T42, T43; T18 now covers Codex `blocked` (source `codex_deviation`, per B) and `partial` (RC-13); T19 split per RF-26.
- Holds: canonical catalogue with scope, clearing path (`auto`/`operator`/`presence`/`authorization`), outbox effects (H1), ageing (H4), alias map (RD-3, RC-21); `security_halt`, `integrity_alert`, `integrity_check_failed` (safe mode), `authorization_expired`, `host_instability`, `operator_hold`.
- Block reasons canonical; `★` marks presence-tier actions (RD-12). `network`, `implementer_blocked`, `external_state_lost`, `push_rejected` removed.
- Invariants renamed `INV-01…INV-20`; new INV-21 (gate check conclusions), INV-22 (presence tier), INV-23 (apply-time guard), INV-24 (agent uid), INV-25 (durability order), INV-26 (security holds), INV-27 (no dispatch under halt/safe mode/dark wake). INV-20 extended with the RD-14/RD-16 timer rule.
- §7.1 failure classes aligned with GH §15.1 (`lost_by_host` separate cap); merge verification §8.5 maps GH §8 M1–M8 to holds (M2/M5/M8 global halt, M3/M6/M7 repo alert, M4 policy notice).
- Recovery §10: identity triple, finalize-after-reboot, `lost_by_host`, durability check, restore epoch, orphan remote objects (RC-07).

**components.md (rewritten)**
- `ProcessSupervisor`/`AgentLauncher` port with `AgentExecSupervisor` (`sudo … agent-exec --run-dir`, `agent-ctl signal|probe|list|stats|reap|purge|fix-acl`) and `SameUidLauncher` (sandbox only); `runwrap` removed (RD-1). Run directory per MS §7.1; supervisor lease file `WORK_ROOT/ctl/coordinator.alive` (Addendum B §3); liveness = stdout growth or CPU progress (RD-15).
- `HoldService` with outbox effects; `PolicyService`; `SnapshotService` (RD-7); `PresenceVerifier` aligned with MS §9.5 (daemon-spawned `mercury-presence`, nonce); `AnchorService` (carriers exclude public check-run summaries, Addendum B §2).
- Control API: principals `readonly`, `claude_session`, `operator`, `operator_presence`; method and CLI tables mark ★ methods incl. `policy.ack`, `security.unhalt`, `audit.restore_confirm`, `orphan.adopt` (RD-12, RF-31); audit-question query map §5.7 (RF-35).
- DDL: `vocab` table (RC-29), `schema_meta`, `boot_session_uuid`, `repos.governance_mode/sandbox/ci_runs_on_draft`, `spec_sha256` (B's `spec_hash`), `authorizations.mode/trigger/amendment_kind spec_confirm/models_used`, `runs.result_disposition/exec_uid/schema_sha256/…`, `snapshots`, `gate_checks`, `policy_escalations`, `policy_acks`, `observation_seqs` (GH §13.2), `merge_verifications` M2–M8 columns, `orphan_remote_objects`, `audit_epochs`, `anchors`; `host_events` age-based retention; triggers for INV-22/24/26, gate success, scope_version chain.
- Outbox catalogue uses GH §13 keys (with `<cause>`), `github.check.upsert`, reconcile-before-retry, network-class accounting (RD-18); Linear ids deterministic v4-shaped (RB-13); `findPullsByHead` `state=all` + author id (RB-23, RC-36).
- §8 process execution, §9 worktrees with normative **WorktreeResetPolicy** (§9.4), snapshots, git hardening (plumbing against the mirror, push from mirror, durability order).
- §10 pseudocode updated: dispatcher (INV-27), TE with deferred results, reauthorize recording, PR review with policy guard, startup per MS §5.2 exit contract (flock → exit 0, safe mode, `fatal.json`, restore confirmation, chain verify), outbox, merge verification, inbox (pending-push reconcile RC-28, operator-id filters RE-21), **normative credited-time algorithm** §10.10 (RD-16, dark wake), policy ack.
- Notification channel matrix §4.15 (RF-21, RD-19); crash-point registry §8.7 (RC-31); tests updated.

**messages.md (rewritten)** — catalogue with new `policy.escalation` message, revision provenance (§3.1), message dedup keys separated from GH §13, binding echoes (security review + `spec_sha256`/`pln_id`/`plan_sha256`; Codex impl + `auth_id`; authorization + `mode`, `prior_auth_payload_sha256`), V4 rules for reauthorize and Codex status mapping, wire-copy generator with B's profiles `claude-sdk`/`anthropic-messages`/`codex-strict` (§5.3), mapping table.

**schemas** — `code.review` event `["COMMENT"]`; `snapshot_tree_sha` on review messages; `producer`, `source_review_ids`, `source_sha256s` + extended sources on revision messages; reauthorize decision vocabulary; `task.authorization` `mode`/`trigger`/`models_used`/`spec_confirm`; binding additions; `task.failed` new actions + `presence_required_actions`; `task.completed` verification `result`/`scope_action`/`control_kind`; `task.assignment` `exec_uid`/`snapshot_tree_sha`/`codex_home`; new `policy.escalation.schema.json`; explicit `type` added to every untyped `enum` in output contracts.

## 2. Finding dispositions

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RC-01 | 22 | fixed (COMMENT only) | SM T25, INV-09; CMP §4.11, D6, CT-04; `code.review` schema |
| RC-02 | 22 | fixed (`github.check.upsert` from transitions and holds; T22 excludes MERCURY contexts) | SM §2.3, §3, §5 H1; CMP §4.14, `gate_checks` |
| RC-03 | 22 | fixed per RD-14 (BLOCKED + presence ack, not "allow T24") | SM T24p/T42/T43, §8.7; CMP `policy_escalations`, `policy_acks`, §10.11 |
| RC-04 | 22 | fixed (AG@apply, deferred results, reauthorize outcomes) | SM §3, §8.1, §8.1.1; CMP `runs.result_disposition` |
| RC-05 | 22 | fixed (per-task `CODEX_HOME`) | CMP §4.6, §8.2; `tasks.codex_home_path` |
| RC-06 | 22 | fixed (single checkpoint `last_commit_sha`, WorktreeResetPolicy, thread-resume rule) | CMP §9.4, §8.6; `tasks.last_pushed_sha` removed |
| RC-07 | 22 | fixed (orphan remote objects, never auto-adopted) | SM §10; CMP `orphan_remote_objects`, §5.4 |
| RC-08 | 22 | fixed (GH §15.1 accounting; no-progress detector) | SM §7.1 |
| RC-09 | 22 | fixed (agent-exec/agent-ctl adapter, ACL model per MS §7.3) | CMP §4.7, §8 |
| RC-10 | 22 | fixed (canonical tables, status aliases, reconcile-before-retry, network-class rule) | CMP §4.14, §6.3 `outbox`, §10.7; MSG §7 |
| RC-11 | 22 | fixed (mode-dependent projection) | SM §1.2; CMP §10.8 |
| RC-12 | 22 | fixed (T41) | SM T41; CMP §7.1, §4.9 `mergeBase` |
| RC-13 | 22 | fixed (`blocked` → `codex_deviation` per B; `partial` → `incomplete`) | SM T16/T18; MSG §5.2 |
| RC-14 | 22 | fixed in part: `anchors`, `audit_epochs`, startup verification; `record_mac` kept nullable per RD-4 (HMAC SHOULD) | CMP §4.16, §6.3 |
| RC-15 | 22 | fixed (`audit_epochs`, restore confirmation) | CMP §4.16, §6.3, §10.6 |
| RC-16 | 22 | fixed (GH §8 M1–M8 by numeric id; columns) | SM §8.5; CMP `merge_verifications`, `github_reviews.user_id` |
| RC-17 | 22 | fixed (waiver = new row; repo `integrity_alert`) | SM T40; CMP DDL |
| RC-18 | 22 | fixed on my side (INV-02 wording) — F owns VP I5 | SM INV-02 |
| RC-19 | 22 | deferred (F, VP wording); SM binds `scope_version` | — |
| RC-20 | 22 | fixed (INV-nn) | SM §4 |
| RC-21 | 22 | fixed (canonical holds/reasons + alias map) | SM §5.1, §5.3, §6.1 |
| RC-22 | 22 | fixed (run statuses, audit columns, `run_meta_json`) | CMP `runs` |
| RC-23 | 22 | fixed (holds `deprioritized`, `operator_hold`) | SM §5.1; CMP §10.9 |
| RC-24 | 22 | fixed (snapshots) | CMP §9.5, `snapshots` |
| RC-25 | 22 | fixed (instruction-file guard) | SM §8.8 |
| RC-26 | 22 | fixed (finding identity, repeat counts double) | SM §9 R5; CMP `findings.identity_sha256` |
| RC-27 | 22 | fixed (normative algorithm) | CMP §10.10 |
| RC-28 | 22 | fixed | CMP §10.9; SM G5 |
| RC-29 | 22 | fixed (`vocab`, `schema_meta`, `user_version`) | CMP §6.3–§6.4 |
| RC-30 | 22 | fixed by RD-2 (paths by reference to MS §7.1) | CMP §9.1 |
| RC-31 | 22 | fixed (crash-point registry, duplicate definition) | CMP §8.7 |
| RC-32 | 22 | fixed (names follow schemas; binding fields added) | schemas; CMP §10.3 |
| RC-33 | 22 | fixed (age-based retention trigger) | CMP §6.4 |
| RC-34 | 22 | fixed (attempt increments per claim) | CMP `runs.attempt` |
| RC-35 | 22 | fixed (`authorization_expired` hold + auto re-auth; BLOCKED only on decline/needs_human) | SM §5.1, §7.3 |
| RC-36 | 22 | fixed (author id + branch) | CMP §4.11, §10.7 |
| RC-37 | 22 | fixed (values via MS-PARAM / SM policy) | SM §7 |
| RC-38 | 22 | n/a for C (B; `resume --adopt` routes through TESTING/review) | SM G5 |
| RC-39 | 22 | fixed | CMP `daemon_instances.boot_session_uuid` |
| RC-40 | 22 | deferred (F); replay = re-apply `task_transitions` | — |
| RC-41 | 22 | fixed | SM §8.6; CMP §10.7 |
| RA-01 | 20 | fixed (hold + B's `spec_hash` + PR protection) | SM §5.1 |
| RA-02 | 20 | fixed (port) | CMP §4.7 |
| RA-04 | 20 | fixed | see RC-01 |
| RA-05 | 20 | fixed (reauthorize mode and outcomes) | SM §8.1.1; schema |
| RA-09 | 20 | fixed (presence tier) | CMP §5.2/§5.4; INV-22 |
| RA-10 | 20 | fixed (projection by mode) | SM §1.2 |
| RA-11 | 20 | fixed (`claude_failure_triage` removed) | CMP §4.1, `runs.kind`; MSG §7 |
| RA-13 | 20 | fixed | CMP §9.5 |
| RA-17 | 20 | fixed (C routing, GH §8 predicate) | SM §8.5, G6/T33 |
| RA-18 | 20 | fixed (`integrity_alert`, presence clear) | SM §5.1 |
| RA-19 | 20 | resolved by RD-4 (SHOULD, nullable) | CMP §6.3 |
| RA-20 | 20 | fixed (`anchors`, `audit.anchor.commit`, overdue alert) | CMP §4.14, §4.16 |
| RA-21 | 20 | fixed (T01 eligibility + WIP) | SM T01 |
| RA-30 | 20 | fixed (hold ageing per RD-3 instead of 72 h) | SM §5 H4 |
| RB-01 | 21 | fixed (wire copies, profiles, typed enums) | MSG §5.3; schemas |
| RB-03, RB-04 | 21 | fixed | see RC-01/RC-02 |
| RB-08 | 21 | fixed (C part) | CMP §4.7 |
| RB-09 | 21 | fixed (`repos.ci_runs_on_draft` onboarding) | CMP §6.3, §13 |
| RB-10 | 21 | fixed (authenticated ETag probe, passive liveness) | CMP §10.10 |
| RB-11 | 21 | fixed (observation sequence, level snapshots, relation ids) | CMP §4.13, `observation_seqs` |
| RB-12 | 21 | fixed (GH §13 is the single catalogue) | CMP §4.13–§4.14; MSG §4 |
| RB-13 | 21 | fixed | CMP §10.7 |
| RB-14 | 21 | fixed | SM §1.2, T34 |
| RB-17 | 21 | fixed (rules API) | SM T22; CMP §4.11 |
| RB-19 | 21 | fixed (no fallback model, models recorded) | CMP §4.6, DDL; schemas |
| RB-21 | 21 | fixed (C part: long-lived read token) | CMP §4.11 |
| RB-22 | 21 | fixed (`producer`, source ids/hashes) | schemas; MSG §3.1 |
| RB-23 | 21 | fixed | CMP §4.11, §10.7 |
| RB-24 | 21 | fixed (C part: lint + "intentionally absent") | CMP D6, §4.11 |
| RD-01 | 23 | fixed (C part) | CMP §4.7, §8 |
| RD-02 | 23 | fixed (verify/deps_install as agent uid) | SM §7.1; CMP §8.2 |
| RD-03 | 23 | fixed (C part: normative algorithm, both FakeClock modes) | CMP §10.10, §14.1 |
| RD-04 | 23 | fixed | CMP §9.4 |
| RD-05 | 23 | fixed (durability order, INV-25) | CMP §9.6, L13; SM §10 |
| RD-06 | 23 | fixed (restore epoch, `reauthorization_required`) | SM §6.1, §8.1; CMP §4.16 |
| RD-09 | 23 | fixed (C part) | CMP §4.14, §7.6 |
| RD-10 | 23 | fixed (supervisor lease, SIGTERM policy) | CMP §4.2, §8.4 |
| RD-11 | 23 | fixed (MS §5.2 exit contract) | CMP §10.6, L1 |
| RD-12 | 23 | fixed (`lost_by_host`, finalize after reboot) | SM §7.1, §10; CMP §8.6 |
| RD-15 | 23 | fixed (CPU-progress liveness) | SM §7.1; CMP §8.4 |
| RD-16 | 23 | fixed (INV-20 extension, coalesced wake summary) | SM §4, §7.3 |
| RD-17 | 23 | fixed (worker thread, lease ≥ 60 s, measured blocking) | CMP §4.3, L14, §10.10 |
| RD-31 | 23 | fixed (scope by check, per GH §8) | SM §8.5 |
| RE-09 | 24 | fixed (C part) | CMP §4.16 |
| RE-12 | 24 | fixed (C part: `NeutralisedText` sink type) | CMP §4.16 |
| RE-13 | 24 | fixed (C part: quarantine chmod 000) | CMP §9.7 |
| RE-14 | 24 | fixed | SM AG@apply |
| RE-15 | 24 | fixed | see RC-01 |
| RE-16 | 24 | fixed via GH §8 M1–M8 (M8 added by B); M9 base-commit audit is GH §9.6 | SM §8.5 |
| RE-17 | 24 | fixed (C part: mutation budgets in OutboxWorker) | CMP §4.14, §10.7 |
| RE-19 | 24 | fixed (paths from one constant module) | CMP §9.1 |
| RE-21 | 24 | fixed | SM T32; CMP §4.13 |
| RE-23 | 24 | fixed (C part: pipeline checks, instruction-file check before resume) | CMP §4.10; SM §8.8 |
| RE-25 | 24 | fixed (`security_halt`) | SM §5.1 |
| RE-27 | 24 | fixed | see RC-33 |
| RE-28 | 24 | fixed (`--reset` = new fast-forward commit) | SM G5 |
| RF-01 | 25 | fixed (C part) | CMP §4.7, §8 |
| RF-03 | 25 | fixed (C part: INV-nn) | SM §4 |
| RF-05 | 25 | fixed (`snapshot_tree_sha` recorded) | CMP `pr_reviews`; schemas |
| RF-07 | 25 | fixed (C part) | SM §8.7 |
| RF-08 | 25 | fixed (C part: projection by mode) | SM §1.2 |
| RF-10 | 25 | fixed (C part: tables; credential is `mercury-ops`, RD-6) | CMP §6.3 |
| RF-12 | 25 | fixed (C part) | CMP §8 |
| RF-14 | 25 | fixed (SM §9 single source) | SM §9 |
| RF-15 | 25 | fixed (C part) | CMP §4.17, §10.10 |
| RF-17 | 25 | fixed (C part: no raw persistence after finalization; retention per E) | CMP §4.16, §6.5 |
| RF-21 | 25 | fixed | CMP §4.15 |
| RF-22 | 25 | fixed (C part: `mercury_status` values, `status --issues`) | SM §1; CMP §6.3, §5.4 |
| RF-26 | 25 | fixed | SM T15/T19, §8.7 |
| RF-27 | 25 | fixed per RD-14/GH §8 scoping (repo `integrity_alert`, not `operator_pause`) | SM §8.5 |
| RF-31 | 25 | fixed (CMP §5.5 single source; `resume` vs `unpause`) | CMP §5.5 |
| RF-35 | 25 | fixed | CMP §5.7 |

## 3. Objections to reconciliation decisions

None blocking. Two notes for the orchestrator:

1. **RD-4 HMAC SHOULD.** Implemented (nullable `record_mac`). I still recommend populating it whenever the key is available from M1, because adding NOT NULL later is a table rebuild; no change requested.
2. **M4 (`merged_unreviewed_head`).** Implemented as GH §8 specifies (`BLOCKED` with a policy notice, no hold). Under G-DETECT this produces a `BLOCKED` task for every deliberate early merge; if that proves noisy in the pilot, `COMPLETED` + notice is a one-row change in SM §8.5.

## 4. Remaining open items

- **B:** confirm the generator profile rules match CL §6.1/CX §3.6 exactly; Phase 0 probe on the mixed-type `dependency_changes_allowed` enum (MSG §5.3 fallback); ASM-B-56 (check-run conclusion updates).
- **D:** register C's workflow-policy defaults referenced by name if F wants them in the parameter registry (`limits.max_awaiting_human`, no-progress detector 5 min / 5 interruptions); `agent-exec` `deps_install` lockfile-ack input.
- **E:** SEC-113 wording (`action_required`, Addendum C); SEC-902 list of `security_halt` triggers referenced by SM §5.1; SEC-505/606 retention values for raw/redacted run logs.
- **F:** register INV-21…INV-27; map SMT/DBT/CT/RT aliases to `TC-` IDs; RC-19, RC-40 wording in the verification plan.
