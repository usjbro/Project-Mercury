# Phase 5 Validation — Agent D: Operational Recoverability

| | |
|---|---|
| Agent | D, DevOps / Platform Architect |
| Phase | 5, independent validation (instructions: `phase5-common`) |
| Date | 2026-10-13 |
| Inputs | TDD.md (complete); `operations/macos-service.md` (MS), `operations/recovery.md` (REC); `architecture/components.md` (CMP) §5, §8–§13; `architecture/state-machine.md` (SM) §5–§7, §9–§10; `integrations/claude.md`, `codex.md`, `github.md` §15; `security/threat-model.md` (parameter references); `planning/traceability.md`, `testing/verification-plan.md` (numeric values); reviews 30, 41–45 |
| Method | Inspection and trace by hand; scripted extraction of numeric values and parameter names (`grep -o` over every non-review document, then a comparison of the names used with the names defined in MS §2) |
| Verdict | **Approve with conditions** (see §8) |

Severity counts: **Critical 0 · High 1 · Medium 9 · Low 11**. The High finding and 6 of the Medium findings are fixed in D's files. The items that remain open belong to other owners and are listed in §8.

---

## 1. Phase 4 open items closed in D's files

| Item (source) | Change | Where |
|---|---|---|
| B's agent-configuration parameters (41-revision-B §4; 45-revision-F) | All registered with their values: `claude.<type>.*`, `claude.daily_budget_usd`, `claude.triage.min_interval`, `claude.max_path_denials`, `claude.limit_retry_factor`, `codex.*`, `gate.*`, `github.review.max_inline_comments`, `github.security_findings.private_full`, `linear.*`, `outbox.pending_escalation`, `budget.*_mutations_per_hour` | MS §2.8 |
| E's parameter requests (44-revision-E, open-items table: presence validity, SEC-312 thresholds, rlimits for SEC-704, raw-log retention, run-dir retention, mutation budgets) | Added `presence.validity_s`, `policy.*` thresholds, `run.rlimit_*`, `runs.raw_retention_d` and `runs.retention_d` | MS §2.6, §2.7, §2.9 |
| fd 0 is the prompt file for Codex kinds (41-revision-B §4, codex.md §3) | Spawn table changed. `agent-exec` now validates fd 0: a regular file at `runs/<run_id>/in/prompt.txt` for Codex kinds, `/dev/null` for `verify`/`deps`, a pipe for `claude`. The Codex grammar requires the final `-` | MS §3.4, §3.5 step 7, kind table |
| `claude` grammar | `--add-dir` may be `cwd` or `runs/<run_id>/in`. `cwd` may be `runs/<run_id>/in` when the spec names no snapshot | MS §3.5 table, step 5 |
| C's workflow-policy defaults | Registered **by reference** in a new MS §2.11 (owners SM §7.1/§7.3/§9 and CMP §13), as offered in 43-revision-D §3.1. No values are duplicated | MS §2.11 |
| Inline numeric values in D's documents | Moved to MS §2.10 (`orphan.sweep_interval_min`, `git.stale_index_lock_min`, `clock.skew_alert_s`, upgrade and shutdown timings, among others). REC now cites them by name | MS §2.10; REC FM-11/12/15, §4 step 13 |

---

## 2. Failure-mode walk (REC §5) through REC §4 and SM §10

Columns: D = detection, A = automatic action, Att = attempt accounting, SE = side-effect reconciliation (no duplicates), Git = worktree and git durability, Op = operator action and notification. ✓ = traced and consistent. A finding ID marks a gap.

| FM | D | A | Att | SE | Git | Op | Result |
|---|---|---|---|---|---|---|---|
| 01 crash mid-transition | launchd exit | restart; REC §4; `in_flight` → reconcile (CMP §10.7) | n/a | ✓ reconcile-before-retry | ✓ INV-25 | FM-17 if looping | ✓ |
| 02 crash mid-run | probe | adopt Codex/verify/deps; Claude re-run, same `input_digest` | ✓ none | ✓ | ✓ | — | ✓ (VD-02 for the `starting` edge) |
| 03 sleep mid-run | gap + `kern.waketime` + power helper | not credited; `host_sleep_grace`; token re-mint; reconcile; dark-wake rule | ✓ | ✓ | ✓ | — | ✓ |
| 04 logout / graceful reboot | SIGTERM; boot uuid | Claude interrupted (`cancelled_by_coordinator`); adoptable runs lease-bounded | ✓ | ✓ | ✓ | log in | ✓ |
| 05 power loss / panic | boot uuid changed, no `exit.json` | `lost_by_host`; durability check; reset policy | ✓ cap → `host_instability` (fixed VD-13) | ✓ | ✓ `cat-file -e` → replay | log in | ✓ |
| 06 network loss in push/PR | network-class error | `network_down`; reconcile by natural key (`ls-remote`, `findPullByHead state=all`) | ✓ `net.error_probe_window_s` | ✓ | ✓ push recorded only after success | — | ✓ |
| 07 outage / rate limit | retry matrix | circuit / `rate_limited` holds | ✓ | ✓ | — | via the other channel | ✓ |
| 08 credential expired / locked | 401 after re-mint; −25308; model-key `auth_failed` | integration / agent / keychain holds | ✓ | ✓ | — | RB-06 → `reload-credentials` | ✓ (`agent_auth_failed` added, VD-14) |
| 09 DB corruption | `quick_check` / `SQLITE_CORRUPT` | safe mode, no writes, quarantine copy | n/a | outbox frozen (in DB) | ✓ | RB-08 | fixed VD-15 (path after step 5 now explicit) |
| 10 disk full | `ENOSPC` / guard | ballast; `low_disk`; interrupts | VD-19 | ✓ | ✓ reset on retry | free space | partial (VD-19) |
| 11 orphans | `agent-ctl list` | reap | — | — | — | if unkillable | ✓ |
| 12 stuck worktree / locks | `index.lock`; missing worktree | stale-lock removal; recreate from mirror | — | — | ✓ (reset epoch, VD-18) | RB-12 | ✓ after fix |
| 13 half-created PR | outbox `in_flight` | adopt the App-authored PR by head | — | ✓ | — | — | ✓ |
| 14 duplicate poll events | unique dedup key | dropped at insert | — | ✓ | — | — | ✓ |
| 15 clock jump | `clock.wall_jump_s` | not sleep; `due_at` re-evaluated | ✓ | — | — | check time | ✓ |
| 16 agent CLI breaks contract | pin/hash; schema failures | `config_fatal`, circuit | ✓ none | — | — | RB-09 | ✓ |
| 17 crash loop | `starts.log` | safe mode | — | — | — | VD-04 | VD-04 (clearing path fixed on D side) |
| 18 hang | no stdout **and** no CPU progress | kill ladder; `stalled` | ✓ consumes (SM §7.1) | — | reset on retry | — | ✓ |
| 19 run dies | probe / `exit.json` | classified | ✓ | — | — | — | VD-07 (`deadline` mapping in CMP) |
| 20 daemon down long | watchdog | none | — | — | — | §8 tree | ✓ |
| 21 foreign change | reconcile | `BLOCKED(foreign_* / pr_closed_*)`; SM G5–G7 | — | never overwrite | ✓ | resume ★ | ✓ |
| 22 supervisor lost | `exit.json{supervisor_lost}` | `lost_by_host` | ✓ | — | ✓ | — | ✓ |
| 23 agent-uid infra broken | doctor; exit 125 | `config_fatal` (agents) | ✓ none | — | — | RB-17 [ROOT] | ✓ |
| 24 chain mismatch | step 7 | safe mode + SECURITY | — | — | — | RB-14 | ✓ |
| 25 restore / new host | `restore.json` | awaiting ★ confirm; epoch; reauth; orphans | — | ✓ orphans never adopted | ✓ replay | RB-08/11/18 | **VD-01** (fixed on D side) |
| 26 dark wake | power helper / time rule | no dispatch | — | polls only | — | — | ✓ (behaviour UNVERIFIABLE IN DESIGN — P0-046) |
| 27 MERCURY down, merge needed | checks pending | none | — | — | — | RB-13 | VD-05 († verbs) |
| 28 security halt | verifier, drift, canary | halt; runs stopped | — | check `action_required` | quarantine | RB-14 ★ | ✓ (verbs fixed, VD-14) |
| 29 permission tamper | commit read fails | `policy_violation` | ✓ | nothing pushed | ✓ | RB-12 ★ | ✓ |
| 30 Keychain locked at start | −25308 | hold; retry | — | — | — | unlock | ✓ |

### 2.1 Crash-point registry (CMP §8.7)

| Crash point | Recovery path | Duplicates? | Result |
|---|---|---|---|
| `after_claim_commit_before_spawn` | `starting`, no `proc.json` → `lost_by_coordinator_crash` → re-dispatch | none | ✓ |
| `after_spawn_before_pid_recorded` | REC: probe with the identity in `proc.json`. **CMP §10.6** marks `starting ∧ pid null` lost **without probing**. The orphan sweep then kills the live run, and if it cannot be killed, re-dispatch can start a second mutating run (INV-02) | possible | **VD-02** |
| `after_run_exit_before_finalize` | finalize from `exit.json` + `final.json` (AG@apply) | none | ✓ (VD-03 ordering) |
| `after_artifact_write_before_tx` | content-addressed rewrite; the unreferenced file is harmless | none | ✓ |
| `after_git_commit_before_fsync` / `after_fsync_before_db_record` | idempotent `git:commit:<run_id>`: a branch tip that already carries `Mercury-Run: <run_id>` is skipped (codex.md §8); otherwise re-commit; INV-25 | none | ✓ |
| `after_result_tx_before_transition` | deferred path re-applied | none | ✓ |
| `after_hold_set_before_outbox` | H1: hold and outbox items in one tx; drained after restart | none | ✓ |
| `after_outbox_send_before_done` (incl. `github.check.*`) | `in_flight` → `reconcile(natural_key)` | none | ✓ (fakes: TC-REC-001; real APIs UNVERIFIABLE IN DESIGN — P0-236 check-run update semantics) |
| `after_push_before_pr` | `ls-remote` = intended → done; PR upsert finds by head | none | ✓ |
| `after_policy_ack_tx` | committed with its outbox; no new presence prompt | none | ✓ |
| `mid_migration` | `BEGIN IMMEDIATE` rollback; backup taken first. **CMP §10.6** evaluates the crash-loop guard *after* `migrate()`, so a migration that kills the process repeats forever | — | **VD-04** |
| `during_archive` / `during_reset` | idempotent resume (REC step 13); the archive comes before the reset, so evidence is kept | none | ✓ |
| `during_snapshot_build` | snapshot dir keyed by tree SHA. Build-to-temp + rename and manifest verification on reuse are **not specified**, so a partial tree can be reused for a Claude review | — | **VD-06** |

---

## 3. "No recovery path grants authority"

| Path | Check | Result |
|---|---|---|
| Adopt / finalize after crash or reboot | AG@apply (INV-23) before use | ✓, but VD-03 (stale `spec_sha256` at startup) |
| Claude output persisted before crash | DecisionRecorder idempotent on `run_id`, bindings validated | ✓ (VD-03 applies too) |
| Outbox reconcile | adopts only App-authored PRs with the matching marker; foreign PR → `dead` + notification | ✓ |
| `resume --adopt` after a foreign push | ★; routes through TESTING and review (RC-38) | ✓ |
| Orphan remote objects | never auto-adopted; ★ `orphan adopt` → new task in `AWAITING_AUTHORIZATION` | ✓ |
| **Restore of an older backup** | Only *unverifiable* rows led to `reauthorization_required`. A verifiable authorization revoked **after** the backup, a CLI cancel, consumed revision counters or `budget_grants` and expiries are silently resurrected, so dispatch could resume under authority that was withdrawn. This contradicts REC R4 and RD-4 | **VD-01 High**, fixed in MS §14.4 step 3, REC §4 step 17, TC-REC-019 |
| `k_auth` loss / new Mac | every non-terminal task → `reauthorization_required` | ✓ |
| Ruleset emergency (RB-13) | the human edits the ruleset with their own credentials; ★ window; drift otherwise → `security_halt` | ✓ |
| Security holds | cleared only by ★ (INV-26); adopted runs not kept under a halt or in safe mode | ✓ |

---

## 4. End-to-end host flows

| Flow | Trace | Result |
|---|---|---|
| Sleep / wake | MS §8.3–§8.4, CMP §10.10, SM §5.1 `host_sleep_grace`: not credited, grace, pool reset, connectivity gate, reconcile, INV-20 coalescing, dark-wake rule | ✓ |
| Dark wake | no dispatch until a full wake or `wake.dark_wake_min_awake_s`; polls allowed | ✓ in design; macOS signal UNVERIFIABLE IN DESIGN — P0-046 |
| Reboot (FileVault) | nothing runs until login; boot uuid → `lost_by_host`; `exit.json` finalize | ✓ |
| Power loss | SQLite FULL + fullfsync; git `core.fsync` (P0-043); `exit.json` fsync + rename; replay | ✓; F_FULLFSYNC UNVERIFIABLE IN DESIGN — P0-043; VM fidelity — P0-047 |
| Logout | SIGTERM; adoptable runs bounded by the lease | ✓; survival UNVERIFIABLE IN DESIGN — P0-031 |
| Network loss | `network_down`, attempts not consumed, `BLOCKED(network)` withdrawn | ✓ |
| Credential expiry | GitHub 401 → `integration_auth_failed`; Linear token refresh; OAuth 14-day alert; model key → `agent_auth_failed` | ✓ |
| Disk full | ballast; `low_disk`; interrupts; cleanup of safe items only | ✓ except VD-19 |
| DB corruption | safe mode, quarantine, agent processes reaped without the DB, RB-08 | ✓ after VD-15 |
| Restore | lock, `restore.json`, ★ confirm, epoch anchored, reauth, orphans | ✓ after VD-01 |
| New Mac | system install [ROOT], new App keys, Time Machine restore, `--reason new_host`, re-clone mirrors, replay | ✓ after VD-16 (rotate every secret if the old Mac is not wiped) |

---

## 5. Parameter consistency

Method: `grep -o` of `<number> <unit>` patterns over TDD.md and every architecture, ADR, integration, protocol, security, testing and planning document (133 hits), plus a comparison of backticked dotted names used elsewhere against the names defined in MS §2.

| Finding | Location | Value elsewhere | MS §2 | Disposition |
|---|---|---|---|---|
| Ops-log retention conflict | MS §2.7 (before this phase) | TDD §16/§21, NFR-061, OD-15: 90 d | 30 d | **VD-09**, fixed: `logs.retention_d` 90, `logs.debug_retention_d` 30 |
| Raw run stream retention conflict | MS `runs.retention_d` kept raw `stdout.jsonl` 30 d | TDD §16 / NFR-061: not beyond completion; SEC-505: "within raw-log retention" (E proposed 14 d) | — | **VD-09**, fixed: `runs.raw_retention_d = 0`. E to align SEC-505 or the operator to choose |
| Probe window "60 s" restated | CMP §4.14 (l. 661), SM §7.1 (l. 444), traceability (l. 403) | 60 s | `net.error_probe_window_s` 60 | consistent; cite the name (VD-12) |
| Lease persistence "≥ 60 s" | TDD §23, CMP l. 361/977 | 60 | `db.lease_persist_s` 60 | consistent, restated |
| Watchdog "45 min / 12 h" | TDD §21 | same | `watchdog.*` | consistent, restated |
| Metrics "every 5 min" | TDD §21, MS §11.2 | 5 | none before | fixed: `metrics.interval_min` |
| Outbox lease 5 min; snapshot retention 1 day | CMP §10.7, §9.5 | — | none before | registered (`outbox.lease_min`, `snapshots.retention_h`); C to cite the names (VD-12) |
| Triage interval: two keys | CMP §13 `[triage] min_interval_minutes` vs claude.md `claude.triage.min_interval` | 30 | registered once | VD-12 (C) |
| Keychain-locked ops issue "> 24 h" | CMP §4.15 l. 680 | 24 h | `credentials.locked_alert_min` 15 (local alert) | not contradictory (different channel); Low note in VD-12 |
| `host_instability` at the cap omitted | github.md §15 l. 776; traceability FR-053 | "ops alert, not BLOCKED" | SM §5.1 hold | VD-13 (B, F); D's documents fixed |
| SM §7.1 attempts/backoff, §7.3 timers, §9 budgets | SM | policy | by reference (§2.11) | ✓ (Addendum B §4) |
| Concurrency (TDD §23, OD-07), cadences (github.md budget table uses 120 s), drift ≤ 60 min (threat model), RPO 24 h | various | equal | equal | ✓ |

Every other numeric hit is a requirement bound (traceability, threat model), a test criterion, a GitHub or Linear platform fact, or workflow policy. None differs from MS §2.

---

## 6. Runbook executability (CLI surface CMP §5.5)

| Runbook verb | In CMP §5.5? | Disposition |
|---|---|---|
| `status`, `doctor [--recheck]`, `request …`, `pause/unpause`, `cancel`, `cancel-run`, `show`, `trace`, `resume --action`, `grant`, `ack-merge`, `policy ack --head`, `security unhalt`, `unpause --safe-mode`, `restore`, `restore --confirm`, `clear-fatal`, `toolchain sync`, `stop`, `reload-credentials`, `db backup`, `orphan …`, `audit verify` | yes | ✓ |
| `unpause --security`, `resume --discard-worktree-changes`, `policy ack` without `--head`, `mercury backup` (REC) | wrong form | fixed in REC (VD-14) |
| `upgrade`, `rollback`, `runtime upgrade`, `agents upgrade\|pin`, `db backup --list`, `restore --reason restore`, `ruleset-emergency begin\|end`, `repo check`, `show --diff [--policy]`, `doctor --repair\|--presence\|--plant-canaries\|--agents\|--quick\|--full` | **no** | **VD-05** (C). Marked † in REC §7. RB-07, RB-08, RB-09, RB-13 and RB-15 cannot be executed as written. CMP §5.2 lists "ruleset-emergency acknowledgement" as ★ but no method exists |
| Root steps | RB-01 s2, RB-07 wrappers, RB-09 pin, RB-10 s7, RB-11, RB-17 s2/s4, MS §6 `authrestart`, §13.5, §13.6: flagged ✓. **P0-043** (`sudo fs_usage`) was not flagged; fixed (VD-17) | ✓ |

---

## 7. Phase 0 coverage of ASM-D and agent-uid assumptions

Every ASM-D-01…36 (15/22/23 withdrawn) maps to a P0 check, a CI job or an operator item (MS §17). Corrections made (VD-17):
- ASM-D-01 and ASM-D-02 pointed at checks that do not confirm them (P0-010 reads the man page). P0-033 now tests `~` expansion and a group-writable plist.
- ASM-D-20 and ASM-D-25 said "Spike". They now map to the `test-macos` CI job.
- P0-049 (ASM-E-06 egress) was referenced but not defined. A procedure is added; E owns the pass criterion.

Agent-uid assumptions are each covered:

| Assumption | P0 checks |
|---|---|
| sudo `-C 4` / `closefrom_override` | P0-014, P0-026 |
| canaries | P0-027 |
| cross-uid signals | P0-028 |
| mirror read as agent | P0-030 |
| logout survival | P0-031 |
| toolchains | P0-032 |
| sandbox denies | P0-037 |
| SDK through sudo | P0-042 |
| ACL / TCC | P0-044 |
| managed settings | P0-048 |
| egress | P0-049 |

All of these are UNVERIFIABLE IN DESIGN until Phase 0 runs.

---

## 8. Findings

### Open (other owners)

| ID | Sev | Owner | Finding | Proposed fix |
|---|---|---|---|---|
| VD-01 | **High** | C, F (D fixed) | A restore that loses history can resurrect revoked authorizations, CLI cancels, budgets and expiries. Before this fix, only unverifiable rows led to reauthorization | SM §10 "DB restored" and CMP §10.6 step 6: when `backup_audit_head` seq < last anchor seq, or the reason is `new_host`, **every** non-terminal task → `BLOCKED(reauthorization_required)` (MS §14.4 step 3). F: TC-REC-019 / TC-SEC-164 criteria as in REC §6 |
| VD-02 | Medium | C | CMP §10.6 treats `starting ∧ pid null` as lost without probing, even when `proc.json` exists. This risks INV-02 | Branch on `proc.json` presence and probe with its identity (REC §4 run table, new row) |
| VD-03 | Medium | C (D fixed) | Startup finalizes and applies results (step 11 / CMP step 2) before the Linear reconcile refreshes `spec_sha256`, so AG@apply checks a stale spec | Record results with `result_disposition = deferred` until the first post-start Linear observation of the issue, then apply |
| VD-04 | Medium | C | CMP §10.6: the crash-loop guard runs after `migrate()`. Crash-loop safe mode reuses `integrity_check_failed` (SECURITY semantics). The order also differs from REC §4: credentials before the chain check, runs before the durability check, no `coordinator.alive` touch at the start | Move the guard before `store.open()`. Tag the hold `cause = crash_loop` with an ops (not SECURITY) notice, cleared by ★ `unpause --safe-mode`. Align the order with REC §4 (normative per MS §5.2) |
| VD-05 | Medium | C | Maintenance verbs are missing from CMP §5.5/§5.4 (§6 above). This was D's Phase 4 open item | Add the verbs with their principals (★: `ruleset-emergency`, `restore --confirm`, `doctor --plant-canaries`) |
| VD-06 | Medium | C | Snapshot build is not atomic. After `during_snapshot_build` a partial tree can be reused by tree SHA for a Claude review | Build in `snapshots/.tmp-<tree>-<ulid>`, then `rename`; on reuse, verify `manifest_sha256` against `ls-tree` |
| VD-07 | Low | C | CMP §10.6 maps `exit.json.reason = deadline` to `crash` (or `lost_by_host`), and `exec_failed` is unhandled | `deadline` → `timed_out`; `exec_failed` → `config_fatal` (REC §2) |
| VD-08 | Low | C | SM §5.1 says `integrity_check_failed` is set by "schema newer than code"; MS §5.2 writes `fatal.json` and exits 0 | Remove it from the SM "Set by" column |
| VD-12 | Low | C, F | Restated 60 s probe window; duplicate triage key; new names `outbox.lease_min` and `snapshots.retention_h` | Cite the MS-PARAM names; use one key, `claude.triage.min_interval` |
| VD-13 | Low | B, F | github.md §15 l. 776 and FR-053 omit the `host_instability` hold at the cap | Add "+ task `host_instability` hold" |
| VD-18 | Low | C | Recreating a missing worktree (CMP §9.3) does not state that `reset_epoch` is bumped | State it (REC FM-12 now does) |
| VD-19 | Low | C | `ENOSPC` / `SQLITE_FULL` in `git_step` or a run is not classified, so it could consume attempts | Environment class under `low_disk` (no attempt) |
| VD-09b | Medium | E / operator | SEC-505 ("raw deleted within raw-log retention", 14 d proposed) vs NFR-061 / TDD §16 ("not beyond completion") | Keep `runs.raw_retention_d = 0` (OD-15) or record an operator change |
| VD-20 | Medium (aggregate of Low items) | Orchestrator | TDD inaccuracies; see §9 | Edit TDD as listed |

### Fixed in place (D's files)

| ID | Sev | Fix |
|---|---|---|
| VD-01 (D side) | High | MS §14.4 step 3; REC §4 step 17; TC-REC-019 |
| VD-03 (D side) | Medium | REC §4 step 11 deferral |
| VD-09 | Medium | MS §2.7 retention values; §10.5 raw deletion |
| VD-10 | Medium | Phase 4 open items (§1), incl. the missing SEC-704 `nproc`/`fsize` values |
| VD-11 | Low | Inline values → MS §2.10 |
| VD-14 | Low | REC verbs: `security unhalt`, `--action discard-worktree-changes`, `policy ack --head`, `db backup`; FM-17 clearing (`unpause --safe-mode` ★, not `clear-fatal`); FM-08 `agent_auth_failed`; `host_instability` in R5, §2, MS §2.1 |
| VD-15 | Low | DB-corruption path through REC §4 made explicit (reap without the DB, direct alert) |
| VD-16 | Low | New Mac: rotate every secret if the old Mac is not wiped; `restore` holds the instance lock |
| VD-17 | Low | P0-043 [ROOT]; P0-049 row; ASM-D-01/02/20/25 mappings |

## 9. TDD accuracy (§18, §20, §23, §24) — for the orchestrator

| § | Statement | Correct per owner |
|---|---|---|
| 18 | "`mercury-power` holds an idle-sleep assertion only while runs are active" | `caffeinate -i -w <pid>` holds the assertion; `mercury-power` reports will-sleep and full/dark wake (MS §8.1, §8.6) |
| 18 | "All root steps require explicit operator consent in Phase 0" | Root steps also occur later: wrapper upgrades, `--update-pins`, `--repair`, uninstall, new Mac, `fdesetup authrestart` (MS §6, §13.5–§13.6) |
| 20 | Flowchart: schema check before `quick_check`; no crash-loop or config-fatal branches; the "await restore confirmation" node has no exit; dark wake loops to "Timers" | REC §4.1: crash loop → `fatal.json` → config → `quick_check` → schema → chain; confirmation continues to the secrets step; dark wake → poll only, no dispatch |
| 20 | "`lost_by_host` … consumes no attempt" | Add "capped per step (`run.lost_by_host_cap`) → `host_instability` hold + ops alert" |
| 20 | "backups restored only through a recorded restore epoch" | Add: when history is lost, every non-terminal task needs re-authorization (VD-01) |
| 21 | "90-day retention (macos-service §11)" | MS §2.7 `logs.*` (now 90 / debug 30) |
| 23 | "daily spend cap (OD-08)" | `claude.daily_budget_usd` (B default, MS §2.8); OD-08 covers revision budgets and expiry |
| 24 | "drain (… let adoptable runs finish or interrupt), backup, migrate, switch symlink, kickstart, verify doctor" | MS §13.2: drain Claude runs only (adoptable runs are kept unless `requires-drain`) → backup → switch → `kickstart -k` → **the new version migrates** → verify ready within `upgrade.ready_max_min`, else auto-rollback |
| 24 | "nightly online backup" | Due after `backup.due_after_h` (24 h) of **awake** time, checked hourly and at wake (MS §14.1) |
| 24 | (missing) | Wrapper and helper upgrades need **[ROOT — operator consent]** (`--upgrade-wrappers`, MS §13.6) |

## 10. Unverifiable in design (Phase 0)

| Behaviour | Phase 0 check |
|---|---|
| Dark wake | P0-046 |
| Logout survival | P0-031 |
| git `F_FULLFSYNC` | P0-043 |
| sudo fd / digest support | P0-014, P0-026 |
| SDK through sudo | P0-042 |
| Credential canaries | P0-027 |
| ACL / TCC | P0-044 |
| Presence helper | P0-045 |
| VM power-loss fidelity | P0-047 |
| Agent-uid egress | P0-049 |
| Check-run update semantics | P0-236 |
| Keychain helper ACL | P0-036 |

Every recovery guarantee that depends on these is conditional on the check passing.

**Verdict: Approve with conditions.** Conditions:
1. C applies VD-01, VD-02, VD-04 and VD-05 before M1 exit, and VD-03 and VD-06 before M3.
2. The orchestrator corrects TDD per §9.
3. E or the operator resolves the raw-retention wording (VD-09b).
