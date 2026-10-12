# Phase 4 Revision — Agent D (DevOps / Platform): Disposition

| | |
|---|---|
| Agent | D, DevOps / Platform Architect |
| Phase | 4, revision to `reviews/30-reconciliation.md` (RD-1…RD-20) |
| Date | 2026-10-12 |
| Files revised | `operations/macos-service.md`, `operations/recovery.md` |

---

## 1 Summary of changes per document

### 1.1 `operations/macos-service.md`

- **Header.** Lists what the document is the single source for (parameters, agent-uid design, layout, exit contract, credential inventory, sleep/watchdog, durability, Phase 0 Mac register) and what it only references (DDL, states, holds, failure classes, retry matrix, CLI verbs, SEC text, requirement IDs). `REL-nn` IDs are retired; F holds the aliases. Every root-level step is marked **[ROOT — operator consent]**.
- **§2 Operational parameter table (new, normative, RD-10/RD-21).** Stable dotted parameter names (`svc.*`, `recovery.*`, `supervisor.*`, `run.*`, `clock.*`, `wake.*`, `net.*`, `github.*`, `linear.*`, `limits.*`, `resources.*`, `disk.*`, `watchdog.*`, `backup.*`, `hold_age.*`, …) for F to register. It merges the values from A, C, D and F (my review §4.10) and adds the RD-3, RD-11, RD-16 and RD-18 values. Workflow policy (attempts, revision budgets, reminder timers) stays with C / OD-08 (see §3).
- **§3 Runtime architecture and agent isolation (RD-1).** This section now holds the full agent-uid design from my review §4.5:
  - the process tree;
  - the `spec.json` spawn contract and the identity triple;
  - `_mercuryagent` and group `mercury` creation commands;
  - root-owned wrappers;
  - the exact sudoers drop-in, with `Cmnd_Alias` digests, `env_reset`, `!setenv`, `closefrom_override`, `!use_pty` and `umask`;
  - the `agent-exec` command-line grammar and its 12-step validation (per-kind binary, prefix, option tokens, forbidden flags, cwd roots, env allowlist, fd-3 framing);
  - the fd-3 secret hand-off and its residual risk;
  - the `agent-ctl` subcommand grammar (`signal`, `probe`, `list`, `stats`, `reap`, `purge`, `fix-acl`, `version`);
  - adoption, the supervisor lease and launchd interactions;
  - toolchain provisioning (`mercury toolchain sync`, `agent.gitconfig`, agent-home credential scan);
  - install, `doctor` checks and uninstall;
  - the interim same-uid mode and the SEC-T-20 gate.
- **§4–§6.** LaunchAgent rationale kept; the broker LaunchDaemon is recorded as the v2 alternative and U2 as OD-36. New **§5.2 exit-code and startup contract** (RD-11): `flock` held → exit 0; corruption → safe mode; schema too new → `fatal.json` + exit 0; chain mismatch → safe mode + SECURITY; awaiting restore confirmation; codes 75 and 78 are never used. `instance_lease` is removed.
- **§7.1 Single filesystem layout table (RD-2/ADR-016).**
  - Covers `MERCURY_HOME`, logs, `WORK_ROOT=/Users/Shared/MercuryWork`, the agent home, root-owned paths and the sudoers file.
  - Each path has its owner:group, mode, ACL, agent access, purpose and Time Machine status.
  - Per-task `CODEX_HOME`, `snapshots/<tree_sha>` and the per-run I/O directories now live in `WORK_ROOT`.
  - Withdrawn roots are listed explicitly.
  - §7.3 defines the group ACL, its fail-closed behaviour and Seatbelt as the second layer.
- **§8 Sleep (RD-16).**
  - C §10.10 is referenced as normative.
  - The wake procedure gains an undici pool reset and the dark-wake dispatch rule.
  - Connectivity uses authenticated ETag probes, and network errors never count toward attempts. `BLOCKED(network)` is removed.
  - New §8.6 adds the signed power helper: will-sleep heartbeat and full or dark wake.
- **§9 Credentials (RD-6/RD-18).**
  - One inventory table with the single prefix `com.usjbro.mercury.*`. It lists the `mercury-bot` and `mercury-ops` keys, the Linear client secret (plus a fallback refresh token), the model keys, an optional Claude OAuth token with an expiry alert, `k_auth` and the healthcheck URL.
  - Items are read once, at start and on `mercury reload-credentials`, through a signed `mercury-keychain` helper that is the only trusted application for those items (RE-29).
  - The per-kind environment allowlist is defined.
  - Git push uses askpass over an fd from the mirror. The socket credential helper is removed (RD-20).
  - New §9.5 covers the human-presence helper (RD-12): install, nonce flow and hardened runtime.
- **§10–§13.**
  - Admission now includes holds and the dark-wake rule.
  - Monitoring goes through `agent-ctl`.
  - New §10.6 gives host capacity input for the cost model (RF-32).
  - The ops alert kinds now use `mercury-ops` channels.
  - The watchdog uses separate awake and sleeping thresholds, a minimal heartbeat body and locked issues (RE-11).
  - Shutdown keeps adoptable runs and interrupts only Claude and `git_step` runs (RD-10/RD-11).
  - Migrations align with C's `schema_migrations` and `vocab` (RC-29).
  - New §13.6 covers wrapper upgrades.
- **§14 Durability and restore.**
  - Backups and integrity checks run in a worker thread (RD-17).
  - New §14.2 covers durability: `core.fsync=committed,reference`, the order commit → fsync → DB transaction, `F_FULLFSYNC` + rename + directory fsync for `proc.json` and `exit.json`, and the recovery check.
  - "Checkpoint commits" are removed.
  - New §14.4 covers the restore epoch and the new-Mac procedure (RD-4).
- **§15 CI.** New `test-wrappers` job. Power-loss and agent-uid tests run on a macOS guest VM rig (RD-24).
- **§16 Phase 0.** The register now uses three-digit `P0-nnn` IDs, with the old IDs as aliases.
  - P0-001…025 are read-only, now including home modes, `/Users/Shared` and the sudo version.
  - P0-026…032 are the agent-uid and SEC-T-20 checks (root, with consent).
  - P0-033…048 are experiments, including the SDK spawn through sudo, git `F_FULLFSYNC`, ACL/TCC, presence, dark wake, the VM rig and managed settings.
  - A new ASM-E → P0 mapping covers RE-20.
- **§17 Assumptions.** ASM-D-29…36 added; ASM-D-15/22/23 withdrawn.

### 1.2 `operations/recovery.md`

- **Principles.** R2 now refers to C's outbox and the git ordering. R5 states that host losses never consume attempts and adds the `lost_by_host` cap. New R7: security conditions never auto-clear.
- **§2.** Replaced by a host-event → C-failure-class mapping. It defines `lost_by_host` and removes the environment cap and `BLOCKED(network)`.
- **§3.** The illustrative `side_effects` DDL is removed. What remains is the reconcile-before-retry semantics D relies on, referencing C §10.7 and B §14/§15.
- **§4 Startup order.** Rewritten in 20 steps that match the §5.2 contract:
  - `flock`, with the supervisor alive file touched first;
  - audit-chain and restore-epoch handling;
  - the git durability check;
  - an `agent-ctl` run-recovery table (adopt, finalize, `lost_by_host`, kill Claude);
  - the orphan sweep via `agent-ctl list`;
  - the RD-14 timer rule;
  - the dark-wake gate.

  The Mermaid flowchart is redrawn and validated with the mermaid 11 parser.
- **§5 Catalogue.** FM-01…21 are updated. FM-22…30 are new: supervisor lost, agent-uid infrastructure, chain mismatch, restore or new host, dark wake, MERCURY down with a merge needed, security halt, permission tampering, Keychain locked at start.
- **§6 Tests.** Procedures for TC-REC-001…023, TC-NET-006/007 and TC-OPS-011/012, all as ID proposals for F. Restore criteria now follow RF-19/RC-07. New §6.1 describes the macOS guest VM power-loss approach (RD-24).
- **§7 Runbooks.**
  - RB-01 now covers both Apps, the system install with operator consent, the P0 gate and locked issues.
  - RB-06 covers rotation for both Apps, the Linear secret, the OAuth token and `k_auth`.
  - RB-08 covers restore with an epoch and presence confirmation.
  - RB-11 covers a new Mac.
  - New runbooks: RB-13 (MERCURY down, merge needed; RD-5), RB-14 (clearing `security_halt`), RB-15 (`policy ack`), RB-16 (toolchains), RB-17 (agent-uid repair), RB-18 (orphan remote objects).
  - CLI verbs are aligned to components §5.5 (`pause`/`unpause`, `resume <task> --action`, `cancel`, `grant`, `ack-merge`).
- **§8.** The troubleshooting flowchart is updated: holds, safe-mode causes, awaiting restore confirmation, `dark_wake` deferral.

---

## 2 Finding dispositions

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RD-01 | 23 (D) | Fixed (D design). A, C and E items belong to their owners. | MS §3.3–§3.11, §7.1, §16.2 |
| RD-02 | 23 | Fixed (D side): `verify` and `deps_install` run as the agent uid through `agent-exec` with Seatbelt. SEC text and C §8.2 belong to E and C. | MS §3.5, §9.4 |
| RD-03 | 23 | Fixed (D side): C §10.10 referenced as normative; FakeClock runs in both modes in CI. FR-282 and the ASMs belong to F and A. | MS §8.2, §15.1; REC §6 |
| RD-04 | 23 (self) | Fixed: checkpoint commits removed; C §9 reset policy referenced | MS §14.2; REC §4 step 13, FM-05/12 |
| RD-05 | 23 (self) | Fixed: `core.fsync`, ordering, `F_FULLFSYNC` + rename + directory fsync, recovery verification; TC-REC-001/002 extended | MS §14.2; REC §4 step 10, §6 |
| RD-06 | 23 | Fixed (D side): restore epoch, `reauthorization_required`, new-Mac flow, escrow OD-D-07. Tables belong to C. | MS §14.4; REC RB-08, RB-11, FM-25 |
| RD-07 | 23 (self) | Fixed: power helper, `sleeping` heartbeat, awake and sleeping thresholds; the watchdog target becomes best effort (F words the NFR) | MS §8.6, §11.6, §2.7 |
| RD-08 | 23 | Fixed via RD-6: `mercury-ops` has `issues:write` on `project-mercury`. B and E own the permission tables. | MS §9.1, §11.6 |
| RD-09 | 23 | Fixed (D side): `BLOCKED(network)` and the environment cap removed; network errors not counted | MS §8.5; REC §2, §3 |
| RD-10 | 23 | Fixed (D side): adoptable runs kept on SIGTERM; supervisor lease in `agent-exec` | MS §3.5 step 11, §3.8, §12 |
| RD-11 | 23 | Fixed: `flock` only; exit contract; `instance_lease` dropped | MS §5.2; REC §4 |
| RD-12 | 23 (self) | Fixed: finalize from `exit.json` after reboot; `lost_by_host` with a cap | REC §2, §4 step 11 |
| RD-13 | 23 (self) | Fixed: per-task `CODEX_HOME` | MS §7.1 |
| RD-14 | 23 | Fixed: single layout | MS §7.1 |
| RD-15 | 23 | Fixed (D side): CPU-progress liveness via `agent-ctl stats`; stall ≥ test timeout | MS §2.3, §3.7; REC FM-18 |
| RD-16 | 23 | D side only: timer rule and coalescing referenced in MS §8.3 and REC §4 step 18. C owns the rule. | — |
| RD-17 | 23 | Fixed (D side): worker-thread backups and integrity checks; lease and progress persistence at 60 s; sleep gap 30 s; loop-lag and commit-p99 metrics | MS §2.1, §2.4, §11.2, §14.1 |
| RD-18 | 23 | Fixed: dark-wake rule; P0-046 | MS §8.4, §16.3 |
| RD-19 | 23 | Fixed: read-once semantics; single prefix; Linear client secret; OAuth expiry alert; fd 3 | MS §9.1–§9.3 |
| RD-20 | 23 | Fixed: socket credential helper removed; askpass over an fd | MS §9.3 |
| RD-21 | 23 | Fixed: single parameter table | MS §2 |
| RD-22 | 23 | D side only: `recovery.reconcile_max_s` measured from the first awake-and-online instant. NFR wording belongs to F and A. | MS §2.1 |
| RD-23 | 23 | Fixed (procedures); IDs belong to F | REC §6 |
| RD-24 | 23 (self) | Fixed: VM rig; never power-cut the operator's Mac | MS §15.3; REC §6.1; P0-047 |
| RD-25 | 23 | Fixed (D side): `agent-exec` kind `claude` with pipes, fd 3 and `claude-config`; P0-042; ALT-B-1 fallback | MS §3.5, §3.11, §16.3 |
| RD-26 | 23 | Fixed: toolchain provisioning; P0-032 | MS §3.9 |
| RD-27 | 23 | D side only: re-run after loss is `lost_by_host`, not a duplicate. Definition belongs to F. | REC §2 |
| RD-28 | 23 | Deferred (A, ADR-010/ADR-013) | — |
| RD-29 | 23 (self) | Fixed: all DDL removed from D's documents | REC §3; MS §3.2 |
| RD-30 | 23 (self) | Fixed. The REL-16 isolation target is now the SEC-T-20 gate (E range). | MS §3.11, §16.2 |
| RD-31 | 23 | D side only: RB-13 and RB-14 use the scoped halts. Scope is defined by E and C per RD-14. | REC RB-13/14 |
| RA-02 | 20 | Fixed (D design) | MS §3 |
| RA-03 | 20 | Fixed. The group is named `mercury`, as in RD-1, not `mercury-agents`. | MS §7.1 |
| RA-07 | 20 | Fixed (D side): `mercury-ops` key and uses. The App-Auditor idea is superseded by RD-6 (rulesets readable with `metadata:read`). | MS §9.1 |
| RA-08 | 20 | Fixed: per-task `CODEX_HOME`, regenerated before each run | MS §7.1 |
| RA-20 | 20 | Fixed (D side): `audit.anchor_overdue_h` → ops alert, never a halt | MS §2.5, §11.4, §14.3 |
| RA-22 | 20 | Fixed (D side). ADR-010 references MS §2. | MS §2.1 |
| RA-31 | 20 | Fixed: C's statuses and classes; `interrupted` and `adopted` withdrawn | MS §3.8; REC §2 |
| RA-32 | 20 | Fixed: C's table names (`outbox`, `runs`) | REC §3 |
| RB-07 | 21 | Fixed; E6 (now P0-038) runs two tasks | MS §7.1, §16.3 |
| RB-08 | 21 | Fixed (D side): fd-3 env delivery; EPERM handled by `agent-ctl probe`; group ACL; agent `HOME`; SDK spawn | MS §3.5–§3.9 |
| RB-10 | 21 | Fixed: authenticated ETag probes only | MS §8.5 |
| RB-12 | 21 | Fixed (D side): overlap 300 s / 600 s after restart or wake; keys referenced | MS §2.5; REC FM-14 |
| RC-05 | 22 | Fixed | MS §7.1 |
| RC-06 | 22 | Fixed (D side); C defines the policy | MS §14.2 |
| RC-07 | 22 | Fixed: orphan remote objects; `reauthorization_required`; T-REC-06 criterion | MS §14.4; REC RB-08, RB-18, TC-REC-006 |
| RC-08 | 22 | Fixed: environment cap and `BLOCKED(network)` removed | REC §2 |
| RC-09 | 22 | Fixed (D design): umask 0007 plus a setgid ACL directory; `agent.gitconfig` `safe.directory`; root outside the home. The run-dir overwrite risk is mitigated (§7.3), not eliminated. | MS §3, §7.3 |
| RC-10 | 22 | Fixed (D side) | REC §3 |
| RC-15 | 22 | Fixed (D side) | MS §14.4 |
| RC-21 | 22 | Fixed: safe mode is mapped to the `config_fatal` / `integrity_check_failed` holds; D's holds use C's names | MS §5.2; REC §8 |
| RC-29 | 22 | Fixed (D side): `schema_migrations`, `user_version` and `min_reader_version`; CHECK changes are contract-class | MS §13.3 |
| RC-30 | 22 | Fixed | MS §7.1 |
| RE-09 | 24 | Fixed (D side): startup chain verification before dispatch | REC §4 step 7 |
| RE-10 | 24 | Fixed via RD-6 | MS §9.1 |
| RE-11 | 24 | Fixed: issues locked; template alerts; minimal heartbeat body; trust rule in the runbook | MS §11.6; REC RB-01, RB-03 |
| RE-13 | 24 | Fixed (D side): quarantine mode 0000; inspect only via `mercury show --diff`. The protected-path list belongs to B and C. | MS §7.1; REC RB-12 |
| RE-17 | 24 | Fixed (D side): `gov.drift_check_interval_min` 60 plus every wake. The mechanism belongs to B. | MS §2.5 |
| RE-18 | 24 | Fixed (D side): binaries hash-pinned in `agent.conf` and checked at every spawn; managed settings installed as root (OD-19) | MS §3.4, §13.5, P0-048 |
| RE-19 | 24 | Fixed: one constant work root (U2 path rejected per RD-1) | MS §7.1, §7.2 |
| RE-20 | 24 | Fixed (D side): ASM-E → P0 mapping; SEC-T-20 gate | MS §16.2, §16.4 |
| RE-25 | 24 | D side only: clearing runbook; adopted runs stopped under a halt. The hold belongs to C. | REC RB-14; MS §3.8 |
| RE-29 | 24 | Fixed: the signed `mercury-keychain` helper is the only trusted application (v1); `/usr/bin/security` is a recorded fallback | MS §9.2, P0-036 |
| RF-01 | 25 | Fixed (D design). The group is named `mercury` per RD-1. | MS §3 |
| RF-04 | 25 | Fixed (D values) | MS §2 |
| RF-06 | 25 | Fixed | MS §7.1 |
| RF-12 | 25 | Fixed | MS §3.7 |
| RF-19 | 25 | Fixed | REC TC-REC-006, RB-08 |
| RF-21 | 25 | D side only: ops alerts reference the C §4.15 matrix | MS §11.4 |
| RF-23 | 25 | Fixed (Mac items): `P0-nnn` register with gates. Closure tracking belongs to F. | MS §16 |
| RF-29 | 25 | Fixed: `worktrees/<owner>__<repo>/<issue-lower>-<ulid8>/` (C's form) | MS §7.1 |
| RF-31 | 25 | Fixed (D side): runbooks use C §5.5 verbs; maintenance verbs listed for C (§4) | REC §7 |
| RF-32 | 25 | Fixed (D input) | MS §10.6 |
| RD-5 runbook item | 30 | Fixed: RB-13 | REC RB-13 |
| RD-12 helper install | 30 | Fixed | MS §9.5, §3.4; P0-045 |

---

## 3 Objections to reconciliation decisions

No reconciliation decision is overturned. Three points need the orchestrator's confirmation:

1. **Scope of the "single parameter table" (RD-10).**
   - Implemented: §2 holds every operational value (timing, thresholds, caps, cadences, run deadlines and stalls).
   - Workflow policy is deliberately not in §2 and stays with its owners: per-kind attempt counts and backoff (SM §7.1), revision budgets and authorization expiry (OD-08), state-level reminder timers (SM §7.3).
   - Reason: moving workflow policy into an ops document would split the state machine across owners.
   - If the orchestrator wants literally all numbers in one table, I will add them as references to the same names.
   - C must replace the deadline and stall values in SM §7.1 with references to `run.<kind>.*`.
2. **Location of the supervisor alive file (RD-11).**
   - RD-11 names `run/coordinator.alive`. `run/` is inside `MERCURY_HOME` (0700 operator), so the agent uid running `agent-exec` cannot read it.
   - Implemented instead as `WORK_ROOT/ctl/coordinator.alive` (operator-owned 0640, group-readable). The semantics are unchanged.
3. **Restore-epoch confirmation is a presence-tier method.**
   - RD-12's list does not name it.
   - Accepting a chain fork is a security-relaxing act, equivalent to "security resume/unhalt", so I gated it on presence.
   - Please confirm, or remove the gate.

---

## 4 Remaining open items

| Item | Owner |
|---|---|
| Add maintenance verbs to the CLI surface: `stop`, `reload-credentials`, `backup [list]`, `restore [--confirm] [--reason]`, `clear-fatal`, `upgrade`, `rollback`, `runtime upgrade`, `agents upgrade\|pin`, `toolchain sync`, `repo check`, `policy ack`, `orphan list\|adopt\|close`, `ruleset-emergency begin\|end`, `unpause --security`, `doctor --repair\|--presence\|--plant-canaries`; mark the presence-tier ones | C (components §5.4/§5.5) |
| Components updates implied here: `runwrap` → `agent-exec`; run dir moves to `WORK_ROOT/runs/`; `flock` held → exit 0 (not 75); `quick_check` failure → safe mode; progress flush 60 s (not 15 s); orphan sweep via `agent-ctl list`; `mode = awaiting_restore_confirmation`; `runs` columns for `boot_session_uuid` | C |
| `codex.md` / `claude.md` flag lists compiled into `agent-exec` token tables; codex.md §6 `HOME` = agent home; the Keychain prefix changes from `dev.mercury.*` to `com.usjbro.mercury.*`; github.md §16 key names (`github-bot-key`, `github-ops-key`) | B |
| SEC-T-20 location list (adds the `MERCURY_HOME` DB); Seatbelt profiles `verify.sb`/`deps.sb`; `agent-exec` argv fuzzing in the SEC-T range; ASM-E-06 egress check (P0-049) | E |
| Register the §2 parameter names, the `P0-nnn` IDs (incl. gates), the TC IDs in recovery §6, and new ODs: OD-D-01…08 (agent uid as designed, Claude path, toolchains, power helper, machine type, external backstop, `k_auth` escrow, lease duration) | F |
| ADR-013 must reference MS §3; ADR-010 drops concrete values; ADR-016 references MS §7.1; ADR-019 references MS §9.5 for the helper | A |
| Operator decisions: OD-D-07 (`k_auth` escrow; default no escrow, re-authorize on a new Mac), OD-D-05 (machine type), OD-D-06 (external dead-man's switch), OD-36 (U2) | Operator |
| Phase 0 execution of every **[ROOT — operator consent]** step (P0-026…032, P0-043, P0-048). Not performed in the design phase | Operator with D |
