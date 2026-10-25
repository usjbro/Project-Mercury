# Phase 3 Review — Agent D (DevOps / Platform): Runtime Reliability and Recovery

| | |
|---|---|
| Reviewer | Agent D, DevOps / Platform Architect |
| Phase | 3, cross-agent review |
| Date | 2026-10-12 |
| Focus | Runtime reliability and recovery across all designs. Covers C's per-state recovery, process adoption, leases and timers; B's retry, backoff and credential handling; E's separate-macOS-user requirement (SEC-201) and how to run it under launchd; whether A's NFRs are achievable on a laptop that sleeps; and F's sleep, reboot, power-loss and network tests. It also reviews my own `operations/macos-service.md` and `operations/recovery.md`. |
| Finding prefix | `RD-nn` |

---

## 1 Scope and method

**Read in full:**
- `reviews/00-brief.md` and `03-design-baseline.md`;
- all six Phase 2 reports (`10`–`15`);
- my own `operations/macos-service.md` and `operations/recovery.md`.

**Read by section** (the parts that bear on reliability):

| Document | Sections read |
|---|---|
| `architecture/state-machine.md` | §1 (states, classes); §3.3–3.7 (transitions, globals); §5 (holds); §6 (BLOCKED, FAILED, CANCELLED, resume); §7 (retries, awake time, timers); §8 (guards, cancel); §9 (counters); §10 (recovery per state) |
| `architecture/components.md` | §4.1–4.2 (types, Supervisor, shutdown); §4.7 (ProcessSupervisor); §5 (control socket); §6 DDL (`daemon_instances`, `leases`, `host_events`); §7 (derived queue, claim, limits, backoff); §8 (runwrap, identity, cancel, adoption); §9 (worktrees, archive, disk); §10.6, §10.7, §10.10 (startup, outbox, sleep detection); §11–§12 (locking, retry tables) |
| `architecture/overview.md` | §5.3–5.4 (trust domains, layout); §6 (process model); §10 (NFRs); §16 (assumptions) |
| ADRs | ADR-010 in full. ADR-002 and ADR-011 through the overview's references only |
| `integrations/github.md` | §2.1 (permissions); §3 (token custody); §4.3 (push); §15 (retry matrix); §16 (credential boundary); §17 (compatibility) |
| `integrations/codex.md` | §5–§8 (CODEX_HOME, env, auth, events and stall); §11–§13 (failure map, kill, self-test) |
| `integrations/claude.md` | §7–§9 (auth, env, managed settings, self-test, supervision) |
| `integrations/linear.md` | §2 (identity, token lifecycle); §11 (failure behaviour) |
| `security/threat-model.md` | §5.1 (SEC-2xx, SEC-6xx, SEC-9xx); §6.1–6.2 (permission matrices); §8.1–8.2 (layout, wrapper); §8.5 (anchoring); §9 (risk register entries R-03, R-21); §11 (D-SEC-1…6) |
| `testing/verification-plan.md` | §2 (tiers, FakeClock, FaultProxy); §3 (levels L7–L9, L12, L15, L16); §6 (crash harness); §7 (gates); TC-P0, TC-AFS, TC-NET, TC-REC, TC-OPS, TC-PERF |
| `planning/traceability.md` | CON-009, FR-043, FR-280…283, NFR-001…005, NFR-020…024, NFR-050…052, NFR-070…073 |

**Method:**
- For every recovery-relevant mechanism (clocks, run supervision, shutdown, worktree reset, durability, retries, credentials, alerting, file ownership), I compared what each document says and recorded the contradictions.
- I then checked each mechanism against the physical behaviour of a sleeping, rebooting, logged-out laptop with FileVault.
- Each NFR and test was then checked for whether it can be measured and executed.

I applied the same standard to my own two documents. Six findings are against them (RD-04, RD-05, RD-07, RD-12, RD-13, RD-24, marked *self*), and RD-30 collects the rest.

---

## 2 Summary verdict

**Not yet implementation-ready on reliability and recovery. The fixes are bounded.** The individual mechanisms are mostly sound:
- C's derived queue with leases, fencing tokens and `runwrap` adoption;
- B's find-then-create outbox handlers;
- the sleep-aware awake-time budgets;
- the expand/contract migrations.

Three systemic problems remain.

1. **SEC-201 (separate agent uid) is a MUST, but every runtime design assumes one uid.** The affected designs are A's T0 domain and ADR-010, C's `kill(-pgid)` and `ps` identity checks, B's real `HOME`, D's `lsof` orphan sweep, Keychain ACL and real `HOME`, and E's per-run `CODEX_HOME`.
   - Process control, file ownership, secret delivery and toolchains all break as written once agents run under another uid.
   - §4.5 below gives a concrete design that works with launchd: the operator-uid LaunchAgent, plus root-owned `agent-exec` and `agent-ctl` wrappers run through a restricted `sudoers` entry as `_mercuryagent`, plus a group with inherited ACLs on a space-free work root outside the operator's home.
2. **The same recovery facts are defined differently in two to five places.** Each pair of contradictions would make two implementers build different recovery behaviour. The affected facts are:
   - how sleep is detected;
   - where a worktree is reset to, and with which `clean` flags;
   - whether runs survive SIGTERM;
   - exit codes at startup;
   - retry counting for network errors;
   - `CODEX_HOME` scope;
   - paths;
   - timing parameters.
3. **Durability and integrity stop at the SQLite boundary.**
   - git objects and refs, and `runwrap`'s `exit.json`, are not flushed under the same guarantee as the database.
   - Restoring a backup, or moving to a new Mac, collides with the audit hash chain, its anchors and the HMAC key. That would cancel every in-flight task.

**Counts by severity:** 31 findings in total.

| Severity | Count |
|---|---|
| Critical | 1 |
| High | 5 |
| Medium | 22 |
| Low | 3 |

---

## 3 Findings

| ID | Sev | Type | Location(s) | Finding | Recommended resolution | Owner |
|---|---|---|---|---|---|---|
| RD-01 | **Critical** | infeasible / contradiction | threat-model §5.1 SEC-201, §6.1 note 1, §8.1–8.2; overview §5.3 (T0 = one uid), ADR-010 Alternatives ("future option"); components §5.2, §8.2–8.5; codex.md §6 (`HOME` = operator home); macos-service §3, §7, §9.2, §9.4; recovery §4 step 10 | SEC-201 makes agents running under a separate uid a MUST, and E's proof (§5.2.2) relies on it: R-03 is Critical until it holds. No runtime design implements it, and several mechanisms stop working under a second uid: (a) `kill(-pgid)` from the operator uid to agent-uid processes returns EPERM; (b) `ps` probably hides another uid's argv, so the `--mercury-run` marker check fails (ASM); `lsof -d cwd` of another uid needs root; (c) files created by the agent are not writable or deletable by the coordinator, so `git commit`, `reset`, `clean` and worktree removal fail; (d) agent model keys cannot come from a Keychain, because a role account never unlocks one, so E's `apiKeyHelper` reading a "dedicated item" fails; (e) toolchains in the operator's home become unreachable; (f) `sudo`'s `env_reset` and `closefrom` drop env and fd-based secrets unless configured. | Adopt the design in **§4.5**: an operator-uid LaunchAgent, plus root-owned `agent-exec` and `agent-ctl` run through a restricted sudoers drop-in as `_mercuryagent:mercury`, a work root at `/Users/Shared/MercuryWork` with inherited group ACLs, secrets passed on fd 3, and a supervisor lease. A records it as an ADR (A-SEC-2). C changes `ProcessSupervisor` so that `signalGroup`, `probe` and `listMarked` go through `agent-ctl`. E verifies it with SEC-T-20 canaries. Gate: no workspace-write Codex run against a non-sandbox repo until this passes on the real Mac. | D (design), A (ADR), C (port), E (verify) |
| RD-02 | High | security | codex.md §10 (L2 tests run by the coordinator); components §8.2 (`sandbox-exec` as coordinator uid); threat-model SEC-703 (only deps install as agent uid) | The authoritative L2 `verify` run executes untrusted repository code (tests, build scripts) as the coordinator, which is the operator uid. Only a Seatbelt profile then stands between that code and `~/.config/gh`, `~/.ssh` and the Keychain files. `deps_install` is covered by SEC-703 but `verify` is not. This reopens R-03 on exactly the path where untrusted code runs most. | Every process that runs repository-derived code (`codex_*`, `verify`, `deps_install`, plus Claude when it has tools) runs as the agent uid through `agent-exec`, with `sandbox-exec` as a second layer. Add this to SEC-201's text and to C §8.2. | E, C, B |
| RD-03 | High | contradiction / unverifiable-assumption | overview §5.2 ("wall clock vs. monotonic"), §6 step 6, ASM-A-04; traceability FR-282, ASM-F-04; verification-plan §2.2 FakeClock (`sleepGap` advances wall, **not** monotonic), TC-P0-007; vs macos-service §8.2 [N1] and components §10.10 | On macOS, libuv's `hrtime` is `mach_continuous_time`, which **advances during sleep**. A's design, F's FR-282 and F's FakeClock all model the opposite. A detector built to FR-282 will not see sleep on the real Mac. Stall and deadline clocks then fire right after wake and kill healthy runs, which violates NFR-021 and CON-009. The fake-clock tests would pass and give false confidence. | Make C's algorithm in §10.10 normative: credited time = `min(Δmono, Δwall, 3×tick)`, gaps are not credited, and `kern.waketime` confirms a sleep (D §8.2). Rewrite FR-282 to state the behaviour ("sleep gaps are not credited to run budgets") rather than the mechanism. FakeClock gets both modes (`mono_pauses: true/false`) and every sleep test runs in both. Correct ASM-A-04 and ASM-F-04. Phase 0 E2 / TC-P0-007 decide which mode the real Mac has. | F, A, C |
| RD-04 | High | contradiction (*self*) | codex.md §12 (`reset --hard <last_pushed_sha> && clean -ffdx`); state-machine §10 IMPLEMENTING, T17 (`last_commit_sha`, archive patch first); recovery §4 step 9 (`checkpoint_sha`, `clean -fdx`, "checkpoint commit after each successful run step"); macos-service §14 | There are three reset targets and three sets of clean flags. (a) Resetting to `last_pushed_sha` throws away a coordinator commit that passed the diff gate and secret scan but was not yet pushed (task in `TESTING`). T14's guard ("HEAD equals `last_commit_sha`") then fails and the task drops to `BLOCKED`. (b) `clean -fdx` deletes ignored dependency trees produced by `deps_install`, but a retry inside `IMPLEMENTING` (T16) does not re-queue `deps_install`, so the retry fails. (c) My "checkpoint commit after each run step" is defined in no other document and conflicts with the coordinator-owned commit pipeline, which commits only after the gates. | Define one `WorktreeResetPolicy` in C §9: (1) archive uncommitted changes as a patch artifact (R8); (2) `reset --hard tasks.last_commit_sha` (or `base_sha`); (3) `clean -ffd`, adding `-x` only when `deps_install` is re-queued in the same step. Delete "checkpoint commit" from recovery.md and macos-service §14. | C (owner), B, D |
| RD-05 | High | missing-requirement (*self*) | recovery §1 R2, REL-03/REL-05; NFR-050, TC-REC-002; components §8.1–8.2 (`exit.json` temp+rename, no fsync stated); ADR-006 coordinator commit | SQLite commits use `fullfsync`, but nothing requires git objects and refs (in the mirror) or `runwrap`'s `exit.json` to be flushed. After a power loss the database can point to a `last_commit_sha` or pushed SHA whose object or ref never reached disk, or adopt a torn `exit.json`. "0 lost commits" then cannot be proven. TC-REC-002 covers only SQLite. | (1) Mirror config `core.fsync=committed,reference` with `core.fsyncMethod=fsync`. Whether git uses `F_FULLFSYNC` on macOS is a Phase 0 question (new ASM-D-29). (2) Order the operations: git commit, then fsync, then the database transaction that records the SHA. (3) `runwrap`/`agent-exec` write `proc.json` and `exit.json` with write, `fsync`, rename and a directory `fsync`. (4) Recovery verifies `git cat-file -e <last_commit_sha>` and the branch ref. If either is missing, classify `lost_by_host` (no attempt consumed), reset to the last durable commit and re-run the step. (5) Extend TC-REC-002 and TC-REC-001 to check git and SQLite consistency. | D, C |
| RD-06 | High | infeasible / missing-requirement | threat-model SEC-602 (failed chain halts dispatch), SEC-603 (HMAC key in Keychain), SEC-604 (anchors); state-machine §6.1 `guard_integrity_failure` (resume = cancel or abandon only); recovery RB-08, RB-11; components §6 (no `anchors` table, C report §7) | Restoring a backup legitimately rewinds the audit chain behind the last off-host anchor. SEC-602 then halts dispatch with a SECURITY alert. If the mismatch is routed to `guard_integrity_failure`, every non-terminal task can only be cancelled or abandoned. On a new Mac (RB-11) the HMAC key `k_auth` is gone, so every MAC fails the same way. The documented recovery runbooks would therefore destroy all in-flight work, and the anchors table does not exist in the DDL. | (1) Add an operator-initiated `audit.restore_epoch` event: `mercury restore` records `{backup_seq, backup_hash, last_anchor_seq, last_anchor_hash, reason}`, anchors continue under epoch+1, and `audit verify` accepts the fork only through that event. (2) After a restore or key loss, unverifiable authority maps to `BLOCKED(reauthorization_required)` (recovery R4), never to `guard_integrity_failure`. (3) Escrow `k_auth` (operator-held recovery copy) or accept re-authorization on a new Mac. (4) C adds `anchors` and `audit_epochs` to the DDL. | E, C, D |
| RD-07 | Medium | infeasible (*self*) | macos-service §11.4, §11.6 (watchdog, `pending_work`); REL-09 | The heartbeat body is a snapshot. If the lid closes during a run, `pending_work = true` stays frozen (`caffeinate -i` does not prevent lid-close sleep), and the watchdog alerts 45 minutes later, every night. That is exactly the noise the design meant to avoid. REL-09 ("≤ 75 min") is also unverifiable, because GitHub can delay or skip scheduled workflows. | Add a small, signed sleep-notification helper (IOKit `kIOMessageSystemWillSleep`, which allows up to about 30 s while the network is usually still up). On sleep it writes a final heartbeat with `mode: sleeping` and takes a pre-sleep checkpoint. The watchdog then uses a 45-minute threshold when awake and a 12-hour one when the last heartbeat said `sleeping`. Restate REL-09 as "p90 ≤ 75 min, best effort". Add an E2E test. | D |
| RD-08 | Medium | contradiction | github.md §2.1 (Issues: **none**; Checks: write; Statuses: read); threat-model §6.2 (issues: write; checks: read; statuses: write); macos-service §11.4/§11.6 (ops issue and heartbeat issue need `issues:write` on `project-mercury`); SEC-901 (security alerts as GitHub issues) | The operations alert channel and the SECURITY notification channel both need `issues:write`, which B's permission table explicitly omits. B and E also disagree on whether the review gate uses `checks` or `statuses`. | The App declares `issues:write`. Per-purpose installation tokens narrow it: the `ops` token gets `repositories:["project-mercury"], permissions:{issues:write}`. B and E settle checks versus statuses in one table. | B, E |
| RD-09 | Medium | contradiction | recovery §2 (`network`: cap 3 per step, then `BLOCKED(network)`) and §3 (journal stays pending while offline); state-machine §5/§7.1 (`network_down` hold, not an attempt); components §7.6 (outbox `dead` after 10 attempts, any class); github.md §15 (retry 3 times, then defer; network not counted; 30 s stability) | Four retry policies for the same condition. `BLOCKED(network)` contradicts C's meaning of BLOCKED ("a human must act"), and brief §G says flaky Wi-Fi should not escalate. If network errors count toward outbox `max_attempts`, a flapping link (one host reachable, one not) produces `dead` items and `BLOCKED(run_exhausted)`. | B §15 becomes the single retry matrix and C implements it. Network-class failures never consume run or outbox attempts while the `network_down` hold is set, or when the host probe fails within 60 s of the error. Delete `BLOCKED(network)` from recovery.md §2. Only non-network errors count toward `dead`. | B (matrix), C, D |
| RD-10 | Medium | contradiction | components §4.2 step 3 (keep adoptable runs on SIGTERM); macos-service §12 (interrupt by default); ADR-010 decision 2 (SIGINT, then SIGTERM groups); NFR-024 ("signal child process groups") | Three different SIGTERM policies. The real gap is that runs kept alive while `mercuryd` is absent (logout, `bootout`, crash loop, safe mode; and, with RD-01, agent-uid processes that may survive logout) are **unsupervised**: no stall check and no deadline. | Keep adoptable runs (C's position), but have `runwrap`/`agent-exec` enforce (a) the hard awake-time deadline it is given and (b) a **supervisor lease**: if `run/coordinator.alive` (touched every 10 s) is stale for more than 10 minutes of credited time, it sends SIGINT, then SIGTERM, then SIGKILL to the group and writes `exit.json{reason: supervisor_lost}`. Reword NFR-024 to say "stop dispatch; interrupt non-adoptable runs; checkpoint; exit within ExitTimeOut". Delete D §12's "default interrupt" and ADR-010 decision 2. | C, D, A, F |
| RD-11 | Medium | contradiction | components §10.6 (`flock` held → `exit(75)`; `quick_check` fail → "refuse to start"); macos-service §5 exit-code contract (0 = intentional stop, otherwise restart), §3.4 (`instance_lease`); recovery §4 steps 4–5 (corruption → safe mode; duplicate → exit 0) | Under `KeepAlive{SuccessfulExit:false}`, an exit of 75 makes launchd restart every 30 s. Refusing to start on corruption produces a crash loop instead of the intended "safe mode with heartbeat and alerts". Two single-instance mechanisms exist (C's `flock` plus `leases`, D's `instance_lease`). | C's `flock` is the primary guard (the kernel releases it on crash) and D's `instance_lease` is dropped. Use D's exit contract everywhere: lock held → log, then exit 0; corruption → stay alive in safe mode; schema too new → `fatal.json`, then exit 0. One table in TDD §18. | C, D |
| RD-12 | Medium | contradiction (*self*) | recovery §4 step 9 ("if rebooted → mark interrupted" for every run); state-machine §10, components §8.6 (`exit.json` + valid `final.json` → finalize); components §8.6 (dead, no `exit.json` → `crash`, consumes an attempt) | (a) After a reboot my procedure throws away runs that had already finished: their `exit.json` and `final.json` are on disk. (b) C counts "dead with no `exit.json`" as `crash`, which consumes attempts. Reboots and power loss are environmental (NFR-021, recovery R5). Three reboots during one implementation would exhaust the budget and escalate. | Follow C for (a): finalize from `exit.json` + `final.json` even after a reboot. For (b), add class `lost_by_host`, which applies when `bootsessionuuid` changed or `exit.json{reason: supervisor_lost}` is present. It consumes no attempt and keeps a separate cap (5 per step), which raises an ops alert, not BLOCKED. | D, C |
| RD-13 | Medium | contradiction (*self*) | macos-service §7.1 (`runs/<run_id>/codex_home`, per run); threat-model SEC-203 (per run); codex.md §5 and components §9.1 (per task, needed for resume) | `codex exec resume <thread>` needs the `sessions/` directory of the earlier run. With a per-run home, the planned recovery paths "resume after `stalled`" (codex.md §11/§12, components §8.6) cannot work. | Per **task**: generated `config.toml` (read-only to the agent) and agent-writable `sessions/`, archived at cleanup. E amends SEC-203 from "per-run" to "per-task, coordinator-generated". Fix D §7.1. | E, D |
| RD-14 | Medium | contradiction | claude.md §7.2, codex.md §5/§13 (`~/Library/Application Support/Mercury/…`); components §9.1 and overview §5.4 (`~/MercuryWork`); macos-service §7.1 (`~/Library/Mercury`); threat-model §8.1 (`/Users/Shared/mercury`, `/opt/mercury/toolchain`) | There are five layouts. Under SEC-201 the agent must traverse the work root, so any work root inside the operator's home forces the home to stay 0755 (ASM-E-04). | See §4, item 4. | D (owner of layout) |
| RD-15 | Medium | ambiguous-contract | codex.md §8 (stall: 10 min planning, 15 min implementation, "allows long test commands"); state-machine §7.1; macos-service §10.1 | Codex emits no JSONL while a single command runs (`item.started`, then nothing until `item.completed`). A 20-minute test suite, which `verify` itself allows, is therefore killed as `stalled` and resumed into the same hang. | Liveness = stdout growth **or** CPU-time progress of the process group (`agent-ctl stats`: summed `cputime` across the group). `stalled` requires both to be flat for `stall_ms`. Make the stall threshold for a command-in-progress at least `repo.test_timeout`. | B, C |
| RD-16 | Medium | ambiguous-contract | state-machine §7.3 (MERGED: 24 h after merge → `BLOCKED(external_state_conflict)`; authorization `expires_at`; reminders 24 h/72 h); components §4.2 (tick phase order: `timers` before `inbox`/`outbox`/`polls`); I20 limited to external waits | Scenario: the operator merges from the iPhone on Friday evening, and the Mac sleeps until Monday. On Monday's first tick the merge is observed (T31), and the 24 h timer computed from `merged_at` fires before verification ever runs. The result is a spurious BLOCKED plus a high-priority security-class notification. After a long absence every authorization also expires together, which produces N separate `decision_needed` notifications. | Extend I20 to every state timer: a timer may fire only after at least one attempt of the awaited action has been made after the most recent wake or start. Measure from the first observation, not from the remote timestamp. On wake, coalesce all due reminders and expiries into one summary notification (recovery §4 step 16). | C |
| RD-17 | Medium | infeasible | components §4.3 (synchronous `node:sqlite`), §7.2 step 4 (lease renewal every tick), §8.4 (flush every 15 s), §10.10 (sleep gap if a gap exceeds 6 × tick = 12 s); macos-service §3.4 (lease every 10 s), §14 (`VACUUM INTO`, daily `integrity_check`) | Each `fullfsync` commit blocks the only event loop (`F_FULLFSYNC` flushes the whole drive cache: milliseconds to tens of milliseconds, and more under I/O load). `VACUUM INTO` and `integrity_check` on the main connection block it for seconds. This can (a) trigger C's 12-second "sleep gap" falsely, freezing stall clocks and setting `host_sleep_grace`, and (b) cost battery and SSD wear, since leases and heartbeats cause tens of thousands of full flushes a day while runs are active. | (1) Backups and integrity checks run in a `worker_thread` or child process with its own read connection. (2) Persist leases at ≥ 60 s intervals (the `flock` is the real guard). Keep per-tick progress in memory, flushed every 60 s or on a phase change, or in a separate `runtime.db` with `synchronous=NORMAL`, never authority. (3) Sleep gap = gap > 30 s and not explained by a measured blocking operation. (4) Add a TC-PERF item: commit p99 and loop lag under a Codex plus test load. | C, D |
| RD-18 | Medium | unverifiable-assumption | macos-service §8.4 (wake procedure resumes dispatch); components §10.10 | Power Nap / DarkWake can briefly run user processes with the lid closed. The wake path would pass the connectivity gate, start a Codex run and take an idle-sleep assertion while the machine sits in a bag. Neither document distinguishes dark wake from full wake. | Never dispatch new runs during a dark wake. Require a full-wake signal (from the RD-07 helper, via IOPM capabilities) or at least 5 minutes of continuous credited awake time before dispatch. Phase 0 experiment E9: with Power Nap enabled, check `pmset -g log` and the mercuryd log. | D |
| RD-19 | Medium | contradiction | github.md §3 (key read "on demand", Keychain `dev.mercury.*`); macos-service §9.1–9.3 (read once at start, `com.usjbro.mercury.*`; inventory lists "Linear API key", no OAuth client secret); recovery RB-06 (no Linear client-secret or Claude setup-token rotation); threat-model SEC-202 (`apiKeyHelper` reads a dedicated item for the agent uid) | (a) Reading on demand fails after wake if "lock keychain when sleeping" is set. (b) Two naming schemes. (c) My inventory and RB-06 are stale against B's Linear client-credentials design. (d) Agent-side Keychain reads are infeasible (RD-01d). | Read every item once at start and on `mercury reload-credentials`, and hold it in memory as a `Secret`. Use one prefix (`com.usjbro.mercury.*`, or whatever A decides) in a single inventory table in macos-service §9.1. Add the Linear client secret, and the Claude `setup-token` expiry alert if OQ-B-01 picks it. Agent model keys are passed per run on fd 3 (§4.5). | D, B, E |
| RD-20 | Low | contradiction | macos-service §9.3 (git credential helper over the control socket with a nonce); github.md §3 (`GIT_ASKPASS` or `GIT_CONFIG_COUNT` header); components §9.2 (askpass reading an inherited fd) | Three push-credential mechanisms. Mine also adds a git principal to the control socket that C's principal table does not have. | Use `GIT_ASKPASS` to a helper that reads the token from an inherited fd (C/B). Delete D's socket variant. | D |
| RD-21 | Medium | contradiction | ADR-010 (ExitTimeOut 60, Throttle 10, downtime notice > 8 h); overview NFR-REL-01 (≤ 60 s including reconcile), NFR-REL-02 (≤ 2 min); macos-service REL-01 (≤ 45 s, Throttle 30, Exit 45), REL-02 (≤ 3 min), REL-13 (≤ 60 s); recovery §4 step 18 (notice > 6 h); state-machine §10 (notice > 60 min); traceability NFR-002 (restart ≤ 30 s / healthy ≤ 60 s), NFR-021 (≤ 120 s); wake grace C 120 s vs D 5 min; disk thresholds C 10/3 GB vs D 15/5/2 GiB | The same operational parameters have two to four values each, so implementation and tests will diverge. | Adopt the single parameter table in **§4.10** as the source. F holds the IDs; TDD §18 and §20 reference it. | F (IDs), D (values) |
| RD-22 | Medium | ambiguous-contract | overview §10 NFR-LAT-03/05, NFR-AVL-01; traceability NFR-003, NFR-004, NFR-005 | "Applies while awake" has no measurement rule. The normal case, a merge from the iPhone while the Mac sleeps, would count as a breach of NFR-LAT-05 or be silently excluded, depending on the implementer. NFR-005 ("no state change missed … across sleep") cannot be met literally: transient states during sleep (a label added then removed, a review requested then dismissed) are never observable by polling. | Define the measurement: latency = `t_done − max(t_event, first_awake_online_instant_after(t_event))`, and availability excludes sleep, logout and offline intervals taken from `host_events`. Reword NFR-005 to: "every durable event (review, merge, comment, check conclusion) and the final state of each tracked entity are observed; transient intermediate states are out of scope". | F, A |
| RD-23 | Medium | missing-requirement | verification-plan §8 TC-REC, TC-NET, TC-AFS, TC-OPS | Scenarios that matter most on a laptop are missing. See the list in §4.11. | Add the TC items listed in §4.11, mostly T4 (real Mac) with operator involvement marked. | F (IDs), D (procedures) |
| RD-24 | Medium | infeasible (*self*) | verification-plan TC-REC-002 / ASM-F-09 (FUSE fault filesystem on Linux, plus "T4 abrupt power-off manually once"); recovery T-REC-02 ("macOS VM hard reset in CI") | (a) A Linux fault filesystem does not exercise `F_FULLFSYNC` or APFS. (b) A battery-powered laptop cannot be power-cut, and a forced power-off of the operator's machine is risky. (c) GitHub-hosted macOS runners do not offer nested virtualization, so my "VM hard reset in CI" cannot run there. | Run power-loss tests in a **macOS guest VM on an Apple Silicon host** (Virtualization.framework through tart or UTM). Force-stop it 50 times under write load, then check `integrity_check` plus the ledger plus git consistency. Note the caveat: the host's disk-cache mode affects fidelity, so set the VM disk to uncached or synchronous. Keep the Linux fault filesystem for SQLite logic only. Never power-cut the operator's Mac. | F, D |
| RD-25 | Medium | infeasible | claude.md §2, §7.2 (`CLAUDE_CONFIG_DIR` under the operator's App Support; SDK pipes); components ASM-C-06; macos-service ASM-D-15 | Under SEC-201 the Claude binary must run as the agent uid. The Agent SDK must spawn it through `sudo agent-exec`, using `spawnClaudeCodeProcess`, with pipes. Its config directory must also be writable by the agent, and the operator's App Support is not. | (a) Custom spawn: `sudo -n -C 4 -u _mercuryagent agent-exec --kind claude …`. sudo passes stdin and stdout pipes through, the key goes on fd 3, and the config directory is `WORK_ROOT/runs/<run>/claude-config`. Phase 0 SDK test. (b) Alternative: B's ALT-B-1 (Messages API with coordinator-implemented, realpath-confined Read, Grep and Glob) removes the Claude process and its uid problem entirely. Operator and B to choose. | B, D |
| RD-26 | Medium | infeasible | codex.md §6 (ASM-B-15, operator `HOME`); macos-service §9.4 (ASM-D-23); threat-model §8.2 (`/opt/mercury/toolchain`) | Target-repo toolchains usually live in the operator's home (nvm, rustup, pyenv, Homebrew prefix permissions). Under SEC-201 they are unreachable, so Codex runs and L2 tests fail, and it is unclear who installs and pins toolchains for the agent. | A per-repo toolchain manifest in `mercury.toml`. `mercury toolchain sync` installs pinned toolchains into `/Users/Shared/MercuryWork/toolchains/<name>/<ver>`: coordinator-owned, group read and execute, never agent-writable. The agent's `HOME` (`/Users/_mercuryagent`) holds only caches, and `doctor` scans it for credential files. Phase 0: run the `network_monitor` test suite as `_mercuryagent`. | D, B |
| RD-27 | Low | ambiguous-contract | verification-plan L9 exit ("0 duplicate … Codex runs per step"); macos-service REL-04/05 | Is the re-execution of a step after a lost run (reboot, crash) a "duplicate Codex run"? | Duplicate = two concurrently active runs, or two runs with the same `(task, step, attempt)` (A's NFR-REL-03). A re-run after loss is a new attempt and is counted by REL-05. | F |
| RD-28 | Medium | contradiction | ADR-010 Alternatives ("separate macOS user … future option"); overview §8.6, RA-9 | A treats a separate user as a future option, while E makes it a MUST. Known disagreement 5, not a new finding. | See §4, item 5. ADR-010 must be revised. | A |
| RD-29 | Low | other (*self*) | recovery §3 (own `side_effects` DDL); macos-service §3.2 (`ALTER TABLE runs …`), §3.4 (`instance_lease`) | My documents carry illustrative DDL that differs from C's `outbox`, `runs`, `leases` and `daemon_instances`. | Remove the DDL from D's documents and reference C's canonical tables. Keep only semantics such as reconcile-by-natural-key, which already match C §10.7 handlers. | D |
| RD-30 | Medium | other (*self*) | macos-service §1, §7, §9.2 (`-T /usr/bin/security`), §9.4 (real `HOME`), §16 (Phase 0) | My documents implement none of SEC-201. My REL table has no isolation requirement. Phase 0 §16 lacks the ASM-E-04 and SEC-T-20 canary steps and the user, group, sudoers and ACL setup, all of which need root and explicit operator consent. | Revise macos-service §1/§3/§7/§9/§16 to the §4.5 design. Add P0-26…P0-32 (§4.5 "Verification") and REL-16 ("0 agent-readable operator or coordinator credentials, SEC-T-20"). | D |
| RD-31 | Medium | ambiguous-contract | threat-model SEC-902, SEC-905 (mismatch → SECURITY incident + pause); state-machine §8.5 check5 (merged before Claude review = failure) | Under G-DETECT, a deliberate early merge by the operator fails check5 and triggers a **global** auto-pause. The pause scope and the conditions for resuming are undefined, so one benign event stops all repositories. | Pause scope by check: check1 or check3 failure (wrong merge actor, or merge commit not on base) → global pause; check2, check4 or check5 failure → repo-scoped hold plus `BLOCKED(merge_verification_failed)`. Resume = operator `ack-merge` (T40). | E, C |

**Low-severity items folded into the findings above:**
- After wake, reset the undici keep-alive pool so dead sockets are not reused (RD-17 / §8.4).
- B caches tokens until 10 minutes before expiry, D until 5 minutes: adopt B's value.
- `ps` visibility of another uid's argv is unverified (RD-01, ASM-D-30).

---

## 4 Positions on the known disagreements, plus the concrete designs

### 4.1 (1) BLOCKED with auto-resume (A) vs holds separate from states (C)

**Recommendation: C's holds.**

From a reliability point of view:
- Holds need no resume target and survive restarts, because the state never changed. They also generate no human notifications. That directly addresses the Slack failure patterns (noise, 14-hour unnoticed stalls caused by alert fatigue).
- BLOCKED should keep C's meaning: a person must act.

Add one safeguard A's model had implicitly: **hold ageing**. A task-scope hold active for more than N days of awake time sends one low-priority summary notification (defaults: `dependency_unresolved` 7 days, `deprioritized` 14 days, `spec_changed` 24 hours if re-authorization keeps failing). That way a task cannot sit invisible for ever.

### 4.2 (2) `jobs` table (A) vs a queue derived from task state (C)

**Recommendation: C's derived queue.**
- A separate `jobs` table is a second source of truth, and after a crash it can disagree with `tasks.state`.
- C's claim transaction (version check, `runs` row with lease and fencing token, partial unique indexes) gives the same crash semantics with one source.
- The non-run work A wanted in `jobs` (polls, publish, verify-merge) is covered by the outbox, timers and the MergeVerifier.

### 4.3 (3) HMAC on authority records: optional (A, C) vs required (E); the anchoring table is missing

**Recommendation: HMAC is SHOULD once SEC-201 is in place, and MUST only during the same-uid interim fallback.**
- With SEC-201, the agent uid cannot open the database at all. That is OS-enforced, and it is the threat SEC-603 targets. Against a same-uid attacker, E itself says HMAC does not help.
- The operational cost is real: key loss (RD-06) or a locked Keychain at start would disable every authorization.
- If HMAC is kept, a failed MAC verification after a restore or a key change must map to `reauthorization_required`, not to `guard_integrity_failure`.

**The anchors and `audit_epochs` tables are required in either case** (RD-06). Anchoring is the stronger tamper-evidence control, and it needs the restore-epoch event.

### 4.4 (4) Filesystem layout

**Recommendation** (this supersedes my own `~/Library/Mercury`):

| Purpose | Path | Owner, mode | Why |
|---|---|---|---|
| Coordinator state: DB, artifacts, backups, control socket, config | `~/Library/Application Support/Mercury/` | operator, 0700 | Apple-conventional; outside TCC; agents must never reach it. The space does not matter because no build tool runs here. |
| Logs | `~/Library/Logs/Mercury/` | operator, 0700 | Convention |
| Work root: mirrors, worktrees, review snapshots, per-task `CODEX_HOME`, run I/O directories, toolchains | `/Users/Shared/MercuryWork/` | operator:`mercury`, 0750 plus ACLs (§4.5) | Space-free, so build scripts work. Outside the operator's home, so the home can be 0700 and the agent uid still traverses the work root. Not TCC-protected (ASM-D-31). |
| Pinned Node and agent CLIs | `/Users/Shared/MercuryWork/toolchains/` (agent-readable) | operator:`mercury`, 0750 | Agents must execute them (Codex CLI, test toolchains) |

**If the operator declines SEC-201,** use the same layout but with the work root at `~/MercuryWork` (C/A). B's App Support paths for checkouts and `CODEX_HOME` are rejected because of the space and agent access.

### 4.5 (5) Separate macOS agent user (E SEC-201) vs same-user process groups (C, D): a workable launchd design

**Recommendation: implement SEC-201 for v1 as follows. Run the coordinator as the operator uid.** E's note 1 allows this. The login Keychain is decisive: a dedicated coordinator uid that never logs in has no unlocked Keychain, and would need the System keychain (root) or secrets in files.

#### Identities

- **`_mercuryagent`**: hidden role account (uid in 200–400, `sysadminctl -addUser _mercuryagent -roleAccount`, shell `/usr/bin/false`, no password, never logs in). Home `/Users/_mercuryagent`, mode 0700, holding only caches.
- **Group `mercury`**: members are the operator and `_mercuryagent` (`dseditgroup`).
- **Operator's home**: `chmod 0700 ~`. At minimum `~/.ssh`, `~/.config` and `~/Library` must be 0700 (ASM-E-04). `mercury doctor` verifies this.

#### How agent processes are launched (no new launchd job)

**Wrappers.** Two root-owned compiled binaries (Swift or Go, hash-pinned) in `/usr/local/libexec/mercury/` (root:wheel 0755):
- `agent-exec`: starts a run. It replaces C's `runwrap` for agent-uid runs.
- `agent-ctl`: control operations.

**sudoers.** Drop-in `/etc/sudoers.d/mercury` (0440, validated with `visudo -cf`):

```text
Cmnd_Alias MERCURY_AGENT = /usr/local/libexec/mercury/agent-exec, /usr/local/libexec/mercury/agent-ctl
Defaults!MERCURY_AGENT env_reset, !use_pty, !log_output, closefrom_override, umask_override, umask=0007
<operator> ALL=(_mercuryagent:mercury) NOPASSWD: MERCURY_AGENT
```

The grant is lateral, to the agent uid only, never to root.

**Spawning.** `mercuryd` (the LaunchAgent, operator uid) spawns `sudo -n -C 4 -u _mercuryagent -g mercury /usr/local/libexec/mercury/agent-exec --run-dir <WORK_ROOT>/runs/<run_id>` with `detached: true`.
- **fd 1 and fd 2** are `stdout.jsonl` and `stderr.log`. `mercuryd` opens them as operator-owned 0640 files, and they are passed by inheritance. Permission is checked when the file is opened, so the agent writes through the fd without owning the file. The agent cannot rewrite the files afterwards.
- **fd 3** carries the run's model key, once, length-prefixed. It never appears in env, argv or a file, and `sudo -C 4` with `closefrom_override` lets it through.
- **Claude runs** keep fd 0 and fd 1 as the SDK's pipes, which sudo passes through. That makes the RD-25(a) path workable.

**What `agent-exec` does, in order:**
1. Validates the run directory's realpath (under `WORK_ROOT/runs`).
2. Reads `spec.json` (operator-owned 0640) and validates argv against a fixed grammar per kind (`codex_plan`, `codex_implement`, `codex_revise`, `verify`, `deps_install`, `claude`).
3. Checks that `cwd` is under `WORK_ROOT`.
4. Builds the environment from the allowlist plus the key read from fd 3, then closes fd 3.
5. Calls `setsid()` and sets rlimits.
6. Writes `ctl/proc.json` (fsync and rename).
7. Forks the agent and `waitpid`s it.
8. Enforces the awake-time hard deadline and the **supervisor lease** (RD-10).
9. Writes `ctl/exit.json` (fsync and rename).

**`agent-ctl` subcommands** (all running as the agent uid, so `kill` and `proc_pidinfo` work, with JSON output):

| Subcommand | Purpose |
|---|---|
| `signal <run_id> <INT\|TERM\|KILL>` | Reads `proc.json`, verifies `pid` + `lstart` + marker, then `kill(-pgid)` |
| `ps` | Lists all `_mercuryagent` processes with pid, pgid, lstart, cwd and marker. Replaces `lsof` and `ps` argv scraping for orphan sweeps. |
| `stats <run_id>` | Group RSS and CPU time, used for RD-15 and the RSS caps |
| `purge <path>` | `rm -rf` limited by realpath to `WORK_ROOT/{worktrees,runs,codex-home}` |
| `fix-acl <path>` | Re-applies the group ACL |

C's `ProcessSupervisor` port maps `signalGroup`, `probe`, `listMarked` and the stats sampler onto `agent-ctl`. Adoption is unchanged: it is based on files, `proc.json` and `exit.json`.

**Why sudo rather than a broker LaunchDaemon:**
- With sudo there is no long-lived agent-uid daemon for a compromised agent to tamper with.
- Claude's SDK pipes work without a relay.
- Installation is one sudoers drop-in plus two binaries.

**Broker alternative.** A broker would be a LaunchDaemon with `UserName=_mercuryagent` and a Unix socket. It gives true `waitpid` and runs that survive logout, but needs IPC, stdio relaying for Claude and its own recovery. Kept as a v2 option.

#### File ownership and ACLs (`WORK_ROOT=/Users/Shared/MercuryWork`)

The group ACL used below is:

```text
group:mercury allow list,search,add_file,add_subdirectory,delete_child,read,write,append,execute,delete,readattr,writeattr,readextattr,writeextattr,readsecurity,file_inherit,directory_inherit
```

| Path | Owner:group, mode | ACL | Agent access | Coordinator access |
|---|---|---|---|---|
| `mirrors/<owner>__<repo>.git` (`core.sharedRepository=0640`) | op:mercury, 0750 | — | read (objects, refs) | read and write (fetch, commit objects, refs) |
| `mirrors/…/worktrees/<name>/` (linked-worktree admin: HEAD, index) | op:mercury, 0750 | — | read | read and write |
| `worktrees/<repo>/<task>/` | op:mercury, 2770 | group ACL, inherited | read and write (Codex) | read and write via the ACL (commit reads, reset, clean) |
| `codex-home/<task>/` (`config.toml` 0640 op; `sessions/` agent) | op:mercury, 2770 | inherited | read config; write sessions | read (archive) |
| `runs/<run>/` (`spec.json`, `stdout.jsonl`, `stderr.log` op 0640) | op:mercury, 0750 | — | read the spec; writes stdout only via the fd | read and write |
| `runs/<run>/{ctl,tmp,out,claude-config}/` | op:mercury, 2770 | inherited | read and write | read and write |
| `snapshots/<task>/<sha12>/` (SEC-205) | op:mercury, 0550, files 0440 | — | read | write before the run |
| `toolchains/` | op:mercury, 0750 | — | read and execute | install |

**Seatbelt as a second layer.** Codex's writable roots are the worktree plus `runs/<run>/{tmp,out}` only. Codex commands therefore cannot forge `ctl/exit.json`, even though they run as the same uid as `agent-exec`.

**Failure mode.** An agent can strip ACLs (`chmod -N`) or `chmod 600` its own files. The coordinator's commit read then fails closed: the run is classified `policy_violation`, `agent-ctl purge` cleans up, and the task goes to `BLOCKED(security_policy_violation)`. Nothing unreadable can be pushed.

#### Keychain and secrets

- Every MERCURY item stays in the **operator's login Keychain** and is read once by `mercuryd` (RD-19).
- The agent uid has no Keychain. It cannot open the operator's `~/Library/Keychains` (0700). This also neutralises my own `-T /usr/bin/security` concern (ASM-D-21) for agents, since only operator-uid processes remain able to call it.
- Model keys reach agents only on fd 3 per run. Known residual risk: Codex child commands running as the same uid might read Codex's environment (ASM-B-16). Mitigations are a capped, dedicated project key and `shell_environment_policy`.

#### launchd behaviour

| Event | What happens |
|---|---|
| `mercuryd` crash, `kickstart -k` or upgrade | sudo and `agent-exec` are in their own session and survive. Runs are adopted through `proc.json`. |
| Logout | Agent-uid processes may survive (ASM-D-32). The supervisor lease ends them after 10 minutes of credited time without the coordinator. |
| Shutdown | Everything is killed. Recovery classifies `lost_by_host` (RD-12). |
| Unchanged | `caffeinate`, BTM, ExitTimeOut |

#### Installation

This is an explicit, operator-run, root-level step in Phase 0 or M1. It is a host modification that this design phase must not perform. `mercury-install --system` performs:
1. create the group and the user;
2. install the wrappers;
3. install the sudoers drop-in (validated with `visudo -cf` first);
4. create `WORK_ROOT`, its modes and ACLs;
5. `chmod 700 ~`.

`mercury-install --system --uninstall` reverses all of it.

`mercury doctor` checks at every start:
- `sudo -n -l -U <op>` lists exactly the two commands;
- the wrapper hashes match the pins;
- the ACLs are present;
- the agent home has no credential files.

Any failure sets the `config_fatal` hold for agent dispatch.

#### Verification (new Phase 0 items for macos-service §16, feeding SEC-T-20)

| ID | Check |
|---|---|
| P0-26 | `sudo -n -u _mercuryagent /usr/bin/true` from a probe LaunchAgent (no TTY) |
| P0-27 | Canary secrets in `~/.ssh`, `~/.config/gh`, `~/.codex/auth.json`, a test Keychain item and `MERCURY_HOME` are unreadable as `_mercuryagent`, using `cat`, `security` and Claude Read |
| P0-28 | `kill` of an agent-uid group from the operator uid fails, and `agent-ctl signal` succeeds |
| P0-29 | `ps` argv visibility across uids (ASM-D-30) |
| P0-30 | A Codex run in a worktree of the 0640 mirror works without write access to `.git` (ASM-E-13) |
| P0-31 | An agent-uid process survives logout (ASM-D-32); the lease ends it |
| P0-32 | The `network_monitor` test suite passes as `_mercuryagent` with `toolchains/` (RD-26) |

#### Interim fallback

E's same-uid fallback (Seatbelt and Claude deny rules) is allowed only on the sandbox repository, recorded as R-03 Critical. Running real repositories with workspace-write requires P0-26…P0-31 to pass.

### 4.6 (6) Merge governance: G-1/G-2 (A) vs G-ORG/G-SPLIT/G-DETECT (E) vs detect-after (B)

**Recommendation: G-ORG (identical to A's G-2) as the target.**

Reliability facts the operator should weigh:
- **G-SPLIT** adds a second push credential (a deploy key: an SSH key in the Keychain, plus agent forwarding or a key file). That is another rotation and recovery path, and deploy keys skip `workflows` gating (ASM-E-07).
- **Under any mode, B's required `MERCURY / claude-review` check means "MERCURY down ⇒ the operator cannot merge"**. The runbook needs an RB-13 "MERCURY down, I need to merge" with the audited ruleset bypass (B R-B-05). I will add it.
- **G-DETECT** must use the scoped pause in RD-31, or a single early merge stops all work.

### 4.7 (7) `revision_request` as a separate Claude decision (B) vs verbatim forwarding (C)

**Recommendation: C (verbatim for sources that are already Claude reviews; a Claude run for CI, tests, human comments and conflicts).**
- Each extra Claude run is one more non-adoptable process, lost on every daemon restart (REL-04), and one more failure point.
- Verbatim forwarding still uses Claude's own words, so authority is unchanged.

### 4.8 (8) Linear status ownership (B: MERCURY → In Progress, the integration → In Review / Done) vs A's open decision

**Recommendation: B's default.**
- The Linear GitHub integration moves `Done` even while the Mac sleeps. MERCURY-owned `Done` would lag until the next wake, often hours after a merge from the iPhone, and would make NFR-LAT-05 depend on the Mac's power state.
- MERCURY verifies and comments. A verification failure is a comment plus BLOCKED, not a status rollback.
- If the operator picks F's OD-06(b) (MERCURY owns `Done`), NFR-LAT-05 must be measured with RD-22's rule.

### 4.9 (9) Requirement ID schemes

**Recommendation: F's scheme is canonical.** D's REL-nn become aliases, then are retired:

| REL | Maps to |
|---|---|
| REL-01 | NFR-002 |
| REL-02 | new NFR-025 (reconcile after start) |
| REL-03 | NFR-050 |
| REL-04, REL-05 | new NFR-026 (lost agent work bounds) |
| REL-06 | NFR-001 |
| REL-07, REL-08 | NFR-003 |
| REL-09 | new OPS-013 (downtime alert, best effort) |
| REL-10 | FR-281 |
| REL-11, REL-12 | NFR-022 |
| REL-13 | NFR-021 |
| REL-14 | NFR-024 |
| REL-15 | new NFR-027 (crash-loop safe mode) |
| REL-16 (§4.5) | SEC range (E) |

A's NFR-REL-xx and F's ADR-P keys map to A's ADR numbers in Phase 4 (F's mapping table).

### 4.10 Single parameter table (resolves RD-21)

| Parameter | Value | Rationale |
|---|---|---|
| `ThrottleInterval` / `ExitTimeOut` / internal shutdown budget | 30 s / 45 s / 20 s | Halves crash-loop churn. The budget is never longer than the logout-shortened case (ASM-D-04). |
| Restart → `ready` after a crash (NFR-002) | ≤ 45 s, of which start ≤ 15 s | Throttle 30 s plus start time. A process that ran longer than 30 s restarts immediately. |
| Reconcile complete after `ready` or after wake + network (NFR-025, NFR-021) | ≤ 120 s (≤ 50 tasks); first poll ≤ 60 s | ETag reconciles are cheap; one number for start and wake |
| Wake grace (`host_sleep_grace`) | 120 s (C) | My 5 minutes is unnecessarily long once RD-15 adds CPU-based liveness |
| Network stability before resuming | 30 s (B) | Avoids flapping |
| Downtime notice on resume | > 60 min of downtime with active tasks (C); one notice | 6 h and 8 h hide the 14-hour-stall class of problem |
| Watchdog | heartbeat every 5 min; checks every 30 min; threshold 45 min (awake) or 12 h (`sleeping`) | RD-07 |
| Disk (dispatch hold / interrupt `verify` and `deps_install` / interrupt Codex) | 15 GiB and 10 % / 5 GiB / 2 GiB | Merges C and D; ballast is kept |
| Lease persistence | ≥ 60 s; `flock` is primary | RD-17 |
| Stall | no output **and** no group CPU progress for: plan 10 min, implement 15 min, verify 10 min | RD-15 |

### 4.11 Missing tests (resolves RD-23); proposed IDs for F

| Test | Scenario | Environment | Pass criterion |
|---|---|---|---|
| TC-REC-010 | Lid-close sleep ≥ 2 h during `codex_implement` (stream dies, token expired) | T4 ⓗ | Classified `network_down` or `transient_api`; resumed thread; 0 attempts consumed; token re-minted |
| TC-REC-011 | Idle sleep is blocked while a run is active (`caffeinate -i`) and allowed when idle | T4 | Assertion present or absent as expected |
| TC-REC-012 | DarkWake / Power Nap with tasks queued | T4 | 0 dispatches during dark wake (RD-18) |
| TC-REC-013 | Logout with an active Codex run; log back in | T4 ⓗ | Run adopted or lease-terminated; 0 orphans |
| TC-REC-014 | Login Keychain locked at start; "lock on sleep" set | T4 | `credentials` alert; partial degrade; recovery after unlock |
| TC-REC-015 | Disk full during a run (FM-10) | T2 + T4 | Ballast released; `degraded:disk`; 0 DB corruption |
| TC-REC-016 | Wall-clock jump ±10 min (FM-15) | T1 FakeClock + T4 | No false sleep; deadlines correct |
| TC-REC-017 | BTM "Allow in the Background" off | T4 ⓗ | `doctor` reports it; watchdog alerts with pending work |
| TC-REC-018 | Upgrade with `--keep-runs` during a real Codex run | T4 | Adopted; result finalized; 0 re-runs |
| TC-REC-019 | Restore a 24-hour-old backup with anchors ahead | T2 | Restore epoch recorded; 0 cancelled tasks; authority shrinks only (RD-06) |
| TC-REC-020 | Power-loss VM cycles (RD-24) | Apple Silicon VM | 50/50: `integrity_check` ok; git `last_commit_sha` present or classified `lost_by_host` |
| TC-REC-021 | Merged while asleep for > 24 h | T2 virtual clock | Verified, not BLOCKED (RD-16) |
| TC-NET-006 | Flapping link (GitHub reachable, Linear not, and the reverse) | T2 FaultProxy | 0 `dead` outbox items from network-class errors (RD-09) |
| TC-NET-007 | Captive portal or TLS interception | T2 | Treated as offline; TLS never disabled |
| TC-OPS-011 | Watchdog end-to-end with the daemon stopped vs sleeping | Sandbox repo | Alert vs no alert (RD-07) |
| TC-SEC (E range) | SEC-T-20 canaries under `_mercuryagent`; `agent-ctl` argv-grammar fuzzing | T4 | 0 reads; 0 grammar escapes |

Also: run every sleep-related test with FakeClock in both monotonic modes (RD-03).

### 4.12 (10) Re-attach vs re-run for Claude runs after a crash

**There is no real disagreement. Agreed position:**
- Codex, `verify` and `deps_install` runs are adoptable (files plus `exit.json`).
- Claude SDK runs are re-run without consuming an attempt.
- A Claude run whose adapter had already persisted a validated `final.json` is finalized idempotently (C §8.6).

The remaining conflicts are SIGTERM handling (RD-10) and the reboot classification (RD-12), both resolved above. Under §4.5 a Claude run spawned through sudo could survive a crash, but its SDK pipes would not, so re-running stays correct.

### 4.13 (11) Removing DISCOVERED as a task state (C) vs the brief

**Recommendation: C.** The brief explicitly allows justified renames. For recovery, issue-level discovery means fewer non-terminal rows to reconcile at start (REL-02 scales with tasks), and no authority-free tasks. The TDD must state the mapping explicitly: "DISCOVERED = `linear_issues.mercury_status`".

### 4.14 (12) MERGE_UNVERIFIED and integrity-alert handling

**Recommendation: keep C's `BLOCKED(merge_verification_failed)`, which F's FR-182 needs as a non-COMPLETED landing state.** Add three things:
1. "data not yet available" vs definitive failure, plus RD-16 so long sleeps do not create false failures;
2. the scoped pause in RD-31;
3. an `integrity_alert` flag on the `merge_verifications` row that B asked for (no new state).

The B/F request for a distinct state is satisfied by the reason code plus the flag.

---

## 5 Items needing an operator decision

| # | Decision | Options | D recommendation |
|---|---|---|---|
| OD-D-01 | Implement SEC-201 as in §4.5. This needs root once: a role account, a group, two root-owned wrappers, a sudoers drop-in, `chmod 700 ~`, and a work root in `/Users/Shared`. | (a) As designed; (b) broker LaunchDaemon instead of sudo; (c) same-uid interim only (R-03 stays Critical, sandbox repo only) | (a) before any real-repository implementation run |
| OD-D-02 | How Claude runs under the agent uid | (a) SDK through the sudo custom spawn (needs a Phase 0 SDK test); (b) B's ALT-B-1 Messages API with coordinator-implemented read tools | (a) if the test passes, else (b). (b) is simpler under SEC-201. |
| OD-D-03 | Toolchain provisioning for the agent uid | (a) MERCURY-managed pinned toolchains in `WORK_ROOT/toolchains`; (b) system-wide installs by the operator | (a) |
| OD-D-04 | Install a small signed native helper for sleep and wake notifications | (a) yes (enables RD-07 and RD-18); (b) no (accept nightly false watchdog alerts, or a 12-hour threshold always) | (a) |
| OD-D-05 | Machine type and power policy (repeats D Phase 2 Q2) | laptop / desktop; `prevent_system_sleep_on_ac` | Laptop: default off. Desktop: on. |
| OD-D-06 | External dead-man's-switch backstop (Healthchecks-style, 12-hour grace) | yes / no | Optional; yes if GitHub Mobile alone feels insufficient |
| OD-D-07 | Escrow of the HMAC key `k_auth`, if E's SEC-603 stays MUST | operator-held recovery copy / accept re-authorization after a Mac change | Re-authorization (no escrow) together with §4.3's SHOULD |
| OD-D-08 | May agent runs continue while the operator is logged out, up to the supervisor lease? | lease 10 min (default) / 0 (kill at coordinator loss) / longer | 10 min |

---

## 6 Confidence

| Area | Confidence | Why |
|---|---|---|
| Contradiction findings (RD-03, -04, -09…-16, -19…-21) | **High** | Direct text comparison across documents. Each conflicting value is cited. |
| Sleep-clock behaviour (RD-03) | Medium–High | Verified in libuv source. Real-Mac behaviour is still Phase 0 E2. C's algorithm works under either outcome. |
| Git and runwrap durability gap (RD-05) | Medium–High | The gap is certain. Whether git uses `F_FULLFSYNC` on macOS with `core.fsync` is unverified (ASM-D-29). |
| Restore vs audit chain (RD-06) | High | Follows mechanically from SEC-602/603/604 together with RB-08, RB-11 and the state-machine resume table |
| Separate-user design (§4.5) | **Medium** | Each building block is standard: sudoers `Cmnd_Alias`/`closefrom_override`/`umask`, macOS ACL inheritance, role accounts, fd inheritance across sudo, uid rules for `kill`. Unverified: `ps` argv visibility across uids, survival at logout, Codex with a read-only mirror, the SDK custom spawn through sudo, ACL stripping behaviour, and `/Users/Shared` and TCC (ASM-D-30…32, ASM-E-04/13). All are P0-26…P0-32. |
| Watchdog and dark-wake findings (RD-07, RD-18) | Medium | Power Nap behaviour varies by hardware and macOS version, so these need the Phase 0 experiment |
| Test executability (RD-24) | Medium–High | No nested virtualization on hosted macOS runners is well established. VM force-stop fidelity depends on the disk-cache setting. |
| Severity calibration | Medium | RD-01 is Critical only because SEC-201 is a MUST that E's proof depends on. If the operator downgrades SEC-201, it becomes High. |
