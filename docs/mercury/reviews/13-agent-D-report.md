# Agent D Report — DevOps / Platform Architect (Phase 2)

Detailed design: [`operations/macos-service.md`](../operations/macos-service.md), [`operations/recovery.md`](../operations/recovery.md). Builds on `02-discovery-platform.md` §4–§6, which Agent D co-authored.

## 1 Findings

1. **Correction to discovery §4.4 (high impact).** The discovery said Node's monotonic clock pauses during sleep, so a wall-versus-monotonic gap would reveal sleep. That is wrong. libuv's macOS `uv__hrtime` returns `mach_continuous_time()`, which **keeps counting during sleep** (libuv `darwin.c`, a change that shipped around libuv 1.38.1). Sleep detection therefore uses an **event-loop tick gap**, confirmed by `sysctl kern.waketime`. The wall-versus-monotonic difference becomes a **clock-jump** detector instead (macos-service §8.2).
2. **Codex runs can survive a daemon crash.** If `codex exec` is spawned detached, with stdout/stderr redirected to files rather than pipes, a mercuryd crash or upgrade restart does not kill it. The daemon re-attaches by pid + start time + pgid and tails the file. Claude runs through the Agent SDK use pipes and cannot be re-attached; they are short, idempotent decision runs and are simply re-run.
3. **The plain `KeepAlive=true` choice is a trap.** Deliberate fatal halts (corrupt DB, schema too new) would restart every `ThrottleInterval`. `{SuccessfulExit:false}` plus an exit-code contract (0 = intentional stop) plus an app-level crash-loop → safe-mode guard avoids that.
4. **Spaces in paths.** `~/Library/Application Support` contains a space, which commonly breaks target-repo build and test scripts. Worktrees and mirrors go to a space-free `~/Library/Mercury/`.
5. **Time Machine and live SQLite do not mix.** Exclude `db/` and back up `VACUUM INTO` snapshots instead.
6. **A dead man's switch needs no inbound access.** A GitHub Actions scheduled workflow can read a heartbeat issue that the App updates, and alert through GitHub Mobile. Public-repo scheduled workflows are disabled after 60 days without repository activity, so `mercury doctor` must watch for that.
7. **Keychain exposure to agent children is the main open security question.** With `-T /usr/bin/security`, any same-user process can read MERCURY's items. Whether Codex's Seatbelt profile blocks that is unverified (ASM-D-21).

## 2 Recommended design (summary)

- **Supervision:** per-user LaunchAgent `com.usjbro.mercury`.
  - Pinned Node from an absolute path.
  - `KeepAlive{SuccessfulExit:false}`, `ThrottleInterval 30`, `ExitTimeOut 45` (internal budget 20 s).
  - `ProcessType Standard`, `Umask 63`, `NumberOfFiles 8192`.
  - Minimal env with no secrets.
  - Full plist and launchctl commands: macos-service §5.
- **Process model:** launchd → mercuryd → agent runs in their own sessions and process groups. pid/pgid/start-time are persisted before the run counts as `running`. Orphans are swept by pgid and by cwd under the work root (§3).
- **Sleep:** `caffeinate -i -w <mercuryd pid>` only while runs are active. Never fight lid close. Agent budgets are counted in **awake time**. Post-wake connectivity gate → token re-mint → reconcile → re-poll within 60 s (§8).
- **Credentials:** login Keychain items `com.usjbro.mercury.<name>`, created with an interactive `-w`, read once via `/usr/bin/security` on a pipe. GitHub App JWT is minted in-process. git uses a credential helper over the control socket. There is a per-child env allowlist (§9).
- **Resources:** `max_codex_runs=1` (raise to 2 after Phase 0 E6), `max_claude_runs=2`, one Codex run per repo. Disk, CPU and memory-pressure admission checks; a 64 MiB ballast file; in-process log rotation (§10).
- **Observability:** JSON log schema with baseline correlation IDs. `heartbeat.json`, `mercury status`/`doctor`. Ops alerts go to one GitHub "operations alerts" issue (@mention). Watchdog workflow alerts when the heartbeat is stale **and work is pending** (§11).
- **Upgrades:** versioned releases + atomic `current` symlink. Drain → `VACUUM INTO` backup → migrate. Expand/contract migrations with `schema_meta.min_reader_version`, so code rollback needs no data restore. Auto-rollback if not ready in 5 min (§13).
- **Backups:** verified `VACUUM INTO` daily (catch-up, not a fixed time) and before upgrades. 7 daily / 4 weekly / 5 pre-upgrade. `quick_check` at every start, `integrity_check` daily (§14).
- **CI:** GitHub-hosted only (including a `macos-15` job), SHA-pinned actions, no secrets, build provenance on release. No self-hosted runner. Target repos must have ≥ 1 required check and G3 protections before MERCURY dispatches to them (§15).
- **Recovery:** side-effect journal with reconcile-by-natural-key (zero duplicates), an 18-step startup procedure, a 21-entry failure catalogue, and runbooks RB-01…RB-12 including the "MERCURY is silent" tree (recovery.md).
- **Reliability targets REL-01…REL-15** (macos-service §2): e.g. restart ≤ 45 s, reconcile ≤ 3 min, 0 lost commits, 0 duplicate side effects, dead-run detection ≤ 60 s, operator learns of downtime ≤ 75 min.

## 3 Alternatives considered

| Topic | Alternative | Why not chosen |
|---|---|---|
| Supervisor | LaunchDaemon | No login Keychain. Running before login is useless with FileVault on. Root blast radius. |
| Restart | `KeepAlive=true` | Crash loops on deliberate halts |
| Sleep | `caffeinate -s` or `pmset` changes | Fights the user and needs root. Correctness must not depend on being awake. Kept as an opt-in `-s` on AC. |
| Sleep detection | wall vs `hrtime` gap (discovery) | Invalid on macOS: hrtime counts during sleep [N1] |
| Child supervision | Non-detached children (launchd kills them with the daemon) | Cannot kill one agent tree by pgid. Loses re-attach. Grandchildren can `setsid` anyway. |
| Log rotation | `newsyslog` | Needs root config in `/etc/newsyslog.d` |
| Liveness alert | Healthchecks.io | Third party, and unconditional alerts on overnight sleep. Kept as an optional backstop. |
| Liveness alert | Self-hosted runner, inbound probe, iOS Shortcuts | Violate constraints or are fragile |
| Migrations | Forward-only with restore-on-rollback | Data loss on rollback. Expand/contract avoids it. |
| CI | Self-hosted Mac runner for macOS tests | Public repo [S21]. GitHub-hosted macOS runners suffice. |
| Paths | Everything under Application Support (as briefed) | Space in path (ASM-D-12). State stays there; work trees moved. |

**Baseline disagreement:** none on vocabulary. I propose one addition: **run-level** statuses (`starting`, `running`, `interrupted`, `adopted`) that are separate from task states, so interruptions never become task FAILED (recovery R5). Agent C should confirm.

## 4 Tradeoffs

- **LaunchAgent + FileVault:** MERCURY is down after an unplanned reboot until the operator logs in. The trade is security over availability, made visible by the watchdog.
- **`max_codex_runs=1`:** lower throughput, but the bottleneck is human merge latency (≈ 14.5 h), and parallel Codex safety is unverified.
- **Re-attaching detached Codex runs:** more supervision code (polling liveness instead of `waitpid`, no exit code), in exchange for zero lost Codex work on crash or upgrade.
- **Heartbeat issue edits:** about 288 writes a day and `issues:write` on the MERCURY repo, in exchange for conditional alerting without a new vendor.
- **`synchronous=FULL` + `fullfsync`:** higher write latency, but write volume is low.

## 5 Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Agent children can read Keychain secrets via `security` (ASM-D-21) | **High** | Phase 0 E5. Claude reviewer has no Bash. If E5 fails → signed helper ACL or a different secret delivery (Agent E). |
| Watchdog workflow silently disabled (60-day rule) or delayed | Medium | `doctor` checks workflow state. Optional Healthchecks backstop. |
| BTM "Allow in the Background" toggled off → MERCURY never starts | Medium | Doctor check; watchdog alert |
| Pinned agent CLI drifts (manual upgrade, Homebrew) | Medium | Version self-test at start + circuit (FM-16) |
| Graceful shutdown cut short at system shutdown (ASM-D-04) | Low | DB durable per commit; runs re-run from checkpoint |
| Re-attach misjudges success without an exit code (ASM-D-16) | Low–Med | Adopt only with schema-valid output + `turn.completed`; else re-run |
| Disk exhaustion by test suites in worktrees | Medium | Admission guard, worktree size cap, ballast |

## 6 Assumptions

ASM-D-01…ASM-D-28 in macos-service §17, each mapped to a Phase 0 command (P0-01…P0-25) or experiment (E1–E8). The ones that change the design if false: ASM-D-21 (Keychain from sandbox), ASM-D-14 and ASM-D-13 (clocks and sysctls), ASM-D-15 (Claude SDK process group), ASM-D-12 (spaces).

## 7 Dependencies

- **Agent C:**
  - canonical `runs`, `side_effects` (journal), `inbox` (dedup), `instance_lease`, `schema_meta` tables;
  - run-level vs task-level status;
  - the cancel and conflict transitions;
  - the control-socket CLI surface (`mercury status|pause|cancel`).
- **Agent B:**
  - whether Claude runs via Agent SDK or CLI (affects re-attach and pgid, ASM-D-15);
  - the push credential mechanism (ASM-D-22);
  - PR markers and idempotency details;
  - an optional `mercury-pr-policy` required check in target repos;
  - App permissions must add `issues:write` on `project-mercury` (heartbeat and ops issues).
- **Agent E:** Keychain ACL decision; redaction patterns; whether ops alerts may mention task content; security escalation for FM-21.
- **Agent F:** adopt REL-01…REL-15 into requirement IDs; Phase 0 milestone = macos-service §16; recovery tests T-REC-01…08 into the verification plan.
- **Notification design (brief §G):** ops alerts share the GitHub-mention channel; dedup rules must be consistent.

## 8 Unresolved questions

1. Operator: Healthchecks-style external ping as a backstop, yes or no? Is GitHub-Mobile-only alerting acceptable?
2. Operator: laptop or desktop? Should `prevent_system_sleep_on_ac` default to true for a desktop?
3. Operator: is the default `max_codex_runs=1` acceptable?
4. Agent E: is `-T /usr/bin/security` acceptable for v1 if E5 passes?
5. Agent B: can the Agent SDK spawn the Claude CLI in its own process group, and can its run be made re-attachable (would remove the "≤ 1 Claude run lost" exception)?
6. Should cancelled tasks' remote branches be deleted (needs a decision on remote cleanup; v1 = no)?

## 9 Supporting evidence

- `02-discovery-platform.md` §4 (launchd keys, launchctl, sleep, Keychain/TCC), §5 (SQLite WAL/FULL/fullfsync, `node:sqlite`, detached spawn), §6 (M1–M7, P1–P4, E2) — S16–S29.
- `02-discovery-agent-runtimes.md` §1 findings 7–9, §3.3, §3.5–3.6, §6 V1–V9, §7 unknowns (no whole-run timeout, Claude SIGTERM = 143, Codex 0/1 exit codes, CODEX_HOME concurrency).
- `01-discovery-integrations.md`: stall pain points (14 h), PR-to-merge ≈ 14.5 h, notification failures.
- New: libuv `darwin.c` `uv__hrtime` → `mach_continuous_time` (https://github.com/libuv/libuv/blob/v1.x/src/unix/darwin.c) [V]; libuv macOS clock change PR (#2894, 1.38.1) [V~]; GitHub Docs, scheduled workflows disabled after 60 days of inactivity in public repos (https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows) [V~]; Healthchecks.io FAQ (https://healthchecks.io/faq) [V~].

## 10 Confidence level

| Recommendation | Confidence | Why |
|---|---|---|
| LaunchAgent over LaunchDaemon | High | Keychain constraint is documented; FileVault removes the daemon's benefit |
| Plist keys and values | Medium–High | OSS man page is older than current macOS; Phase 0 P0-10/E1 |
| Sleep detection via tick gap | Medium–High | Source-verified clock behaviour; the sysctl confirmation is ASM |
| Codex re-attach after crash | Medium | Sound POSIX mechanics; adoption semantics need contract tests |
| Side-effect journal + reconcile = 0 duplicates | High | Standard outbox pattern; natural keys exist for every GitHub/Linear effect listed |
| Keychain via `/usr/bin/security` | Medium–Low | Works mechanically; exposure to agent children unverified (ASM-D-21) |
| GitHub Actions watchdog | Medium | Works without inbound; schedule delays and the 60-day rule are real caveats |
| Expand/contract migrations + symlink upgrades | High | Well-established practice; small single-node scope |
| Resource defaults (thresholds, concurrency) | Low–Medium | Mac hardware and target test suites unknown until Phase 0 |
