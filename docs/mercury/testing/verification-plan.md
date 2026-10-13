# MERCURY — Verification Plan

| | |
|---|---|
| **Owner** | Agent F (test IDs, levels, environments, gates). Content contributors: C (state machine, contracts, crash-point registry), D (macOS procedures, Phase 0 Mac checks, recovery procedures), E (security tests `SEC-T-*`, acceptance criteria `SAC-*`, gates `G-S1…G-S5`), B (agent and API fixtures, integration Phase 0 checks). |
| **Status** | Phase 4 revision (implements RD-1…RD-20 and Addenda A–B of `reviews/30-reconciliation.md`). |
| **Requirement source** | `planning/traceability.md` (single source of requirement IDs and of the ID registry). Every `TC-*` here maps to ≥ 1 requirement there; every requirement there has ≥ 1 `TC-*` or `P0-*`. |
| **Single sources referenced, not restated** | SEC test procedures and binary pass criteria: `security/threat-model.md` §10.2. SAC thresholds and gates: §10.1 and §8.10 there. Mac procedures: `operations/macos-service.md` §16 and `operations/recovery.md` §6. Parameter values: `operations/macos-service.md` §2 (cited by name). |
| **Rule** | A requirement is `Verified` only when all mapped TCs pass at their stated level with stored evidence. Passing against fakes never verifies a requirement whose TC is defined at the sandbox (T3), real-Mac (T4) or VM (T4v) level. |

The brief warns against confusing design completeness with validated implementation. This plan therefore separates what is proven against **fakes** (logic, state machine, idempotency), against the **real sandbox** (GitHub and Linear behaviour, governance), on the **operator's real Mac** (launchd, sleep, Keychain, agent uid, Seatbelt) and in a **macOS guest VM** (power loss).

---

## 1. Principles

1. **Deterministic first.** The core is tested against a virtual clock in **both monotonic modes**, seeded randomness and scripted fakes (NFR-101). The same seed gives the same trace.
2. **Invariants as properties.** Authority invariants (C's `INV-*`) are checked as properties (`PROP-*`) over generated event sequences (§5).
3. **Crash anywhere.** Every persistence and external-effect boundary is a named crash point (C's registry, `architecture/components.md` §8.7); the recovery suite kills the process at each point (§6).
4. **No production writes from tests.** Automated suites target only the sandbox repo and team, through an allow-list guard (OPS-004, TC-OPS-009).
5. **Real agents sparingly and only behind gates.** Real Claude and Codex run only in contract recording, prompt-injection, security-boundary and sandbox smoke suites, each with a budget cap, and only after the security gate for that use has passed (§7.2).
6. **Measurable gates.** Every level has numeric entry and exit criteria (§3). "Looks fine" is never an exit criterion.
7. **Security tests are first-class.** They run in every CI build where the tier allows, and the gates G-S1…G-S5 block milestones, not only M8.
8. **Sleep is a mode, not an edge case.** Every sleep-related test runs with FakeClock `mono_pauses: true` **and** `false` (RD-16).

---

## 2. Test environment strategy

### 2.1 Environment tiers

| Tier | Name | What is real | What is fake | Runs where | Used by levels |
|---|---|---|---|---|---|
| T0 | In-process | Coordinator code | Everything external, clock, host events, process broker | CI (Linux and macOS runners) | L1, L2 |
| T1 | Local integration | SQLite (both drivers), git (mirror, worktrees, plumbing), filesystem, child processes | Agent binaries (fake `claude`/`codex`), `agent-exec`/`agent-ctl` (FakeBroker, same argv grammar), GitHub, Linear | CI (macOS runner preferred) | L3, L4, L9 crash injection, L11 |
| T2 | E2E simulation | Whole daemon + CLI + control socket | All external systems; virtual clock; FaultProxy; FakeHost | CI | L5, L7, L8, L10 |
| T3 | Sandbox | Sandbox repo with real rulesets and both MERCURY Apps; Linear sandbox team with the Linear app; Linear GitHub integration | Agents (fakes by default; real agents in tagged runs after their gate) | Operator's Mac or a dev machine with sandbox credentials | L6, L13, parts of L12, L15 |
| T4 | Real Mac | launchd, Keychain, Seatbelt profiles, `_mercuryagent`, sudoers wrappers, presence and power helpers, sleep, dark wake, logout, reboot | External systems are the sandbox (T3) | Operator's Mac only; ⓗ marks operator steps | L0, L9 (Mac), L12, L15 |
| T4v | macOS guest VM | macOS, APFS, `F_FULLFSYNC` path, git `core.fsync`, SQLite | Network targets faked | Apple Silicon host with `tart`/UTM, uncached/synchronous disk (P0-047; `operations/macos-service.md` §15.3) | TC-REC-020 power-loss cycles |
| T5 | Pilot | Everything on `network_monitor` | — | Operator's Mac | L17 |

Notes:
- GitHub-hosted macOS runners provide no nested virtualization, so T4v runs on an operator-controlled Apple Silicon host, never in hosted CI (RD-24). The operator's own Mac is **never** power-cut.
- The Linux fault-injecting filesystem stays for SQLite **logic** only (ASM-F-09); durability evidence comes from T4v.
- T4 security tests that need root setup run only after the operator performs the one-time install (OPS-014); procedures are marked **[ROOT — operator consent]** in D's register.

### 2.2 Fakes

All fakes implement the production ports (NFR-100). Port names follow `architecture/components.md` §4.

| Fake | Port | Behaviour | Fault injection |
|---|---|---|---|
| **FakeClaude** | `ClaudeDecisionPort` (SDK custom-spawn path and ALT-B-1 path) | Scripted results per decision type (triage, authorize, plan review, revision request, code review, security review) in the pinned SDK result shapes; records `input_digest` and model used | `error_max_turns`, budget, structured-output retries, `success` without output, hang, exit 143, slow stream, auth failure, schema rejection (`config_fatal`) |
| **FakeCodex** | Fake `codex` executable (pinned argv contract) | Reads a scenario script; emits JSONL; writes scripted changes; writes `-o` output; rejects argv lacking required flags or containing forbidden ones; long quiet commands with CPU activity | `turn.failed`, hang with and without CPU progress, ignored-SIGTERM grandchildren, protected-path and forbidden-path edits, invalid output, attempted `git commit`, `.git` pointer rewrite |
| **FakeBroker** | `ProcessSupervisor` / `AgentLauncher` (`agent-exec`, `agent-ctl` grammar) | Validates specs with the real grammar tables; simulates uid separation (operator `kill` → EPERM), fd-3 hand-off, `exit.json`/`proc.json` writes, supervisor lease, `stats` CPU time | Lease expiry, boot-session change, torn `exit.json`, PID reuse, grammar fuzzing |
| **FakeGitHub** | `GitHubPort` (REST subset incl. check runs with `app.id`, rules for branches, reviews, merges) | In-memory repo with ETag 304s; simplified ruleset model including required-check pinning to an integration id. **Not** an oracle for real GitHub rules: governance truth only from T3 | 5xx, unknown-outcome writes, secondary rate limits, list lag, replayed reviews, forged same-name checks |
| **FakeLinear** | `LinearPort` | In-memory workspace, `updatedAt` ordering, client-supplied ids, integration-mode simulation (`integration_owns_done` moves) | Same-timestamp bursts, late updates, rate limits, dropped responses after apply, A→B→A flips |
| **FakeClock** | `Clock` (wall + monotonic) | Virtual time with **two sleep modes**: `mono_pauses: true` (monotonic stops during sleep) and `mono_pauses: false` (monotonic continues, the real macOS behaviour, RD-16). `sleepGap(d)` advances wall time and, per mode, monotonic time | Wall jumps (`clock.wall_jump_s`), NTP steps, blocking operations that look like gaps |
| **FakeHost** | `HostEvents` (power helper, `kern.waketime`, boot session, logout) | Emits will-sleep, full wake, dark wake, logout/login, reboot (new boot session) | Missing helper, dark wake without full wake, rapid flapping |
| **FakePresence** | Presence helper port | Returns presence success, user cancel, timeout or helper missing/unsigned | Each outcome |
| **FaultProxy** | HTTP(S) proxy | Latency, drop, reset, DNS failure, partitions, captive portal, TLS interception | All network tests |

Scenario scripts (YAML) are owned by C; the runner records the seed and both clock modes in the evidence.

### 2.3 Sandbox environment (T3)

Created by the operator in P0c (OD-13); MERCURY never creates it.

| Item | Specification |
|---|---|
| GitHub sandbox repo | `mercury-sandbox` (placeholder) under the same owner type as the targets. If OD-01 moves targets to an organization, keep a personal **and** an org sandbox so G-DETECT and G-ORG are both tested. Small TypeScript project with CI that runs on draft PRs, a flaky-test toggle, a lockfile, and a protected-path fixture. |
| Governance | Ruleset per ADR-014 / `integrations/github.md` §9 (rulesets, not classic protection): PR, 1 approval, Code Owner review, last-push approval, dismiss stale, no bypass, block force-push/deletion, `allow_auto_merge=false`, both MERCURY checks required and pinned to `mercury-bot`. `mercury repo check` must report sandbox and targets equivalent before governance TCs count (TC-OPS-016). |
| Identities | `mercury-bot` and `mercury-ops` sandbox installations (separate installation ids from production); Linear app `actor=app` on team `MSB`. |
| Human actor | Operator-in-the-loop steps ⓗ from a scripted checklist. A second human test account only if OD-13 allows. |
| Reset | Reset script with sandbox credentials only. |
| Allow-list guard | Harness refuses any repo or team not in `test-targets.allow` (TC-OPS-009). |

### 2.4 Real-agent usage and budgets

| Suite | Real agents | Gate required first | Budget cap |
|---|---|---|---|
| Contract recording (TC-CON-003/004/005/014) | Claude, Codex (pinned) | G-S1 | ≤ USD 5 per session |
| Security boundary (TC-SEC-1xx at T4) | Real binaries as `_mercuryagent`, scratch repos | G-S1 (canaries are part of G-S2) | minimal |
| Prompt-injection corpus (TC-PI-130…139) | Both | G-S1; target repos never | ≤ USD 20 per full run |
| Sandbox smoke (`live-agents` tag) | Both | G-S3 (pushes) | ≤ USD 10 per run |
| Any run touching a non-sandbox repository | Both | **G-S2** (CON-018) | per OD-08 |

### 2.5 Environment readiness (entry for each tier)

| Tier | Ready when |
|---|---|
| T0/T1/T2 | MERCURY repo CI live (P0d); fakes for the ports touched exist |
| T3 | P0c exit: both Apps and the Linear app installed on the sandbox; governance equivalent (TC-OPS-016); allow-list guard green |
| T4 | P0a and P0b results recorded; agent uid installed (OPS-014) for agent-uid tests |
| T4v | P0-047 passed; rig per `operations/macos-service.md` §15.3 |
| T5 | M8 exit; G-S4 for M9b; G-S5 for M9c |

---

## 3. Test levels with entry and exit criteria

Ranges per level are in §4. "Exit" is the pass/fail criterion for the level at a milestone exit; individual TCs carry their own criteria in §8.

| # | Level | Env | Entry criteria | Exit criteria (all measurable) | Main requirements |
|---|---|---|---|---|---|
| L0 | Phase 0 register (`P0-nnn`) | T4 / T3 | Operator available; root steps consented; ODs needed by the check decided | Every check recorded Pass, Fail-with-design-change or Accepted; 0 Open checks gating the next milestone (traceability §10.2) | CON-015, OPS-001 |
| L1 | Unit | T0 | Port interfaces defined | 100 % pass; 100 % branch coverage on guards, state machine, scheduler, policy gate, merge-verification predicate; ≥ 85 % lines overall | FR-002…008, FR-021…024, FR-124, FR-181 |
| L2 | State machine and property | T0 | Transition table baselined (C) | 100 % table transitions accepted; 100 % illegal pairs rejected and audited; **0 counterexamples in 10,000 sequences per property per CI run** (100,000 nightly), each sleep property in both clock modes | FR-050, FR-080…085, CON-004…006, CON-012 |
| L3 | Contract | T0/T1 | Schemas and wire copies generated; pinned versions chosen | 100 % golden examples valid; 100 % mutants rejected; wire copies accepted by both providers' validators; recorded fixtures match pinned versions | FR-060…066, NFR-090, NFR-093 |
| L4 | Integration | T1 | L1 green for touched components | 100 % pass on macOS runner, both SQLite drivers; 0 surviving child processes after the suite; DB triggers: one positive and one negative case per trigger | FR-040, FR-043, FR-051, FR-063, FR-140, NFR-022, NFR-023, NFR-050 |
| L5 | E2E with fakes | T2 | L2–L4 green for touched components | 100 % scenarios reach the expected final state, artifacts, notifications (count per NFR-063) and audit answers; 0 runtime invariant violations | Operating model 1–15; FR-260 |
| L6 | Sandbox integration | T3 | T3 ready (§2.5) | 100 % pass; 0 writes outside the allow-list; GitHub/Linear read use ≤ 20 % of limits | FR-001, FR-140…145, FR-162, FR-166, FR-181…183, FR-201, FR-220 |
| L7 | Agent failure simulation | T2 | FakeClaude/FakeCodex/FakeBroker fault modes | 100 % failures classified as specified; 0 orphans; 0 state advance on invalid output; 0 false stalls on quiet commands with CPU progress | FR-044, FR-045, FR-053, FR-054, FR-062, NFR-006, NFR-083 |
| L8 | Network interruption | T2 (+T4 TC-NET-004) | FaultProxy | 0 duplicate effects; 0 false transitions; 0 attempts consumed and 0 `dead` outbox items from network-class errors; first poll ≤ `recovery.first_poll_max_s` after network restored | FR-283, FR-143, FR-202, FR-223, NFR-005, NFR-021 |
| L9 | Crash, sleep, restart recovery | T1/T2 (crash), T4 (Mac), T4v (power loss) | Crash-point registry complete for the milestone | **0 ledger violations in 1,000 randomized crash runs** (200 at M1), each crash point ≥ 10 hits; 100 % non-terminal tasks recovered; 0 sleep-induced failures in both clock modes; restart within `svc.restart_to_ready_max_s` 10/10; T4v: 50/50 power-loss cycles with `integrity_check` ok and no DB reference to a missing git object | NFR-001, NFR-002, NFR-020…027, NFR-053, FR-280…282 |
| L10 | Duplicate events | T2 | — | Each duplicate input → exactly one effect; 0 repeated notifications in 100 unchanged polls; A→B→A value flips each observed | FR-001, FR-043, FR-063, FR-143, FR-221 |
| L11 | Concurrency | T1/T2 | — | Limits never exceeded; ≤ 1 active mutating run per task and ≤ 1 per (task, kind); 0 `SQLITE_BUSY` surfaced | FR-040, FR-041, FR-048 |
| L12 | Security boundary | T1/T4/T3 | Threat model baselined; gate of the TC's scope (§7.2) | Each TC's binary criterion per `security/threat-model.md` §10.2; the SAC of the gate met (§7.2) | `SEC-*`, CON-002, CON-010, CON-018 |
| L13 | Unauthorized merge and approval | T3 ⓗ | Sandbox governance equivalent | SAC-01, SAC-02, SAC-17 thresholds; G-DETECT case raises an incident ≤ 5 min awake (SAC-10); 0 merge/approve/dismiss/update-branch/auto-merge calls by MERCURY | CON-007, CON-014, FR-162, FR-166, FR-180…182 |
| L14 | Prompt-injection resistance | T2 (guards) + T3 (real agents) | Corpus PI-01…PI-20 reviewed by E | SAC-04: code-enforced outcomes 100 %; LLM-judgement ≥ 95 % flagged or declined; ≥ 60 variants by M9b; re-run on every agent upgrade | SEC-301…316, FR-203 |
| L15 | Performance and resource | T3/T4 | Feature-complete for the measured path | NFR-040…045, NFR-080…085 thresholds; metrics computed per the measurement rule (traceability §1.5, TC-PERF-007) | NFR-04x, NFR-08x, NFR-008 |
| L16 | Operational / demo / inspection | T4 / CI | Runbooks drafted | Each demo meets its criterion with an evidence note; ID, pointer and parameter lint 0 violations | NFR-070…073, OPS-* |
| L17 | Pilot acceptance | T5 | M8 exit; G-S4 (M9b); G-S5 (M9c) | TC-PIL criteria (§7.3) | OPS-008, FR-300, FR-301, NFR-004 |

---

## 4. Test case ID scheme

`TC-<LEVEL>-<nnn>`; IDs permanent; removed tests keep a `Retired` row (§8.18). Ranges:

| Level key | Range | Contributor | Notes |
|---|---|---|---|
| `TC-P0` | 001–049 D; 050–079 F-allocated (E, operator); 201–241 B | — | `TC-P0-nnn` ≡ `P0-nnn` |
| `TC-UNIT` | 001–199 | all | |
| `TC-SM` | 001–099 | C, F | |
| `TC-CON` | 001–099 | C, B | CT-01…05 = TC-CON-009…013 |
| `TC-INT` | 001–099 | C, D | DBT-01…04 = TC-INT-020…023 |
| `TC-E2E`, `TC-SBX`, `TC-AFS`, `TC-NET`, `TC-DUP`, `TC-CONC`, `TC-PERF`, `TC-OPS`, `TC-PIL` | 001–099 | F, C, D | |
| `TC-REC` | 001–099 | D, C | D's §4.11 tests are TC-REC-010…021; T-REC-01…08 aliases in traceability §8.3 |
| `TC-SEC` | 001–099 F-owned; **100–199 = E's `SEC-T-nn`** (TC-SEC-1nn ≡ SEC-T-nn) | E, F | |
| `TC-GOV` | 001–099 F-owned; **110–118 ≡ SEC-T-10…18** | E, F | |
| `TC-PI` | 001–099 retired seeds; **130–139 ≡ SEC-T-30…39** | E | Corpus PI-01…PI-20 are variants inside TC-PI-130 |

A new TC cites ≥ 1 requirement ID from `planning/traceability.md`. If none fits, the contributor asks F for a requirement rather than defining one here. Contributor IDs (SMT, DBT, CT, RT, T-REC, SEC-T) are aliases per traceability §8.3.

---

## 5. State-machine property suite (L2)

The model-based test drives the real state-machine module with generated sequences of agent results, poll observations (including duplicates, reorderings and A→B→A flips), operator and presence commands, holds, timeouts, crashes, reboots, sleep gaps, dark wakes and restores. After every step it checks the properties below. C's transition table is the oracle; C's invariants (`INV-01…27`, `architecture/state-machine.md` §4) are the safety properties.

| PROP | Property (checked after every step) | INV / requirement |
|---|---|---|
| PROP-01 | A Codex run starts, or its result is applied, only with a current, unrevoked, unexpired, non-superseded authorization matching task, issue, repo and current `spec_hash` | INV-03; CON-005, FR-022, FR-024 |
| PROP-02 | An implementation run starts only with an approval whose `plan_sha256` equals the current plan hash and whose `scope_version` equals the current authorization's `scope_version` (limits-only amendments keep it valid) | INV-04, INV-05; CON-006, FR-102 |
| PROP-03 | No sequence of Linear observations alone reaches `AUTHORIZED` or any later state, or creates an authorization | INV-17; CON-004 |
| PROP-04 | MERCURY never emits merge, approve, request-changes, dismiss, update-branch or auto-merge | INV-09; FR-162, FR-180 |
| PROP-05 | ≤ 1 active mutating run per task and ≤ 1 active run per (task, kind); no run without a valid claim | INV-02; FR-040 |
| PROP-06 | Terminal states absorbing; `COMPLETED` implies verified-merge evidence | INV-08; FR-083 |
| PROP-07 | Each revision counter ≤ its limit + Σ operator grants; reaching the limit implies `BLOCKED` with exactly one escalation | INV-15; CON-012 |
| PROP-08 | Every state change has exactly one transition row with an allowed initiator, evidence and audit event | INV-07, INV-19; FR-081, NFR-060 |
| PROP-09 | A sleep gap alone never causes `FAILED` or `BLOCKED`, in both clock modes; state timers obey the timer rule | INV-20; CON-009, FR-085 |
| PROP-10 | Re-applying `task_transitions` (evidence and guard reports) to a fresh store yields identical `tasks` rows and counters (raw-event replay is a separate fake-clock property) | FR-084 |
| PROP-11 | ≤ 1 non-terminal task per Linear issue | INV-01 |
| PROP-12 | `AWAITING_HUMAN_APPROVAL` only with code and security reviews approving the exact current head SHA | INV-06; FR-165 |
| PROP-13 | Every external effect is an outbox row written in the same transaction as its cause | INV-11; FR-063 |
| PROP-14 | Every external observation is processed at most once | INV-12; FR-001 |
| PROP-15 | Append-only tables are never updated or deleted | INV-13 |
| PROP-16 | A worktree is removed only for a terminal task with no unarchived changes | INV-14; FR-184 |
| PROP-17 | Authority rows are inserted only by the Decision Recorder from a successful Claude run | INV-18; CON-003 |
| PROP-18 | No agent spawn spec carries GitHub/Linear credentials or the control token; agents never hold a DB handle; every agent-class spawn goes through `agent-exec` as the agent uid | INV-10, INV-24; SEC-202 |
| PROP-20 | Setting or clearing a hold never changes `tasks.state` | FR-050 |
| PROP-21 | Security conditions never clear without a presence-tier command; safety-relaxing methods never execute without a presence assertion | INV-22, INV-26; FR-050, FR-242, FR-243 |
| PROP-22 | A result finishing after a spec change is not applied before a new authorization version exists | INV-23; FR-024 |
| PROP-23 | No dispatch during dark wake (before `wake.dark_wake_min_awake_s` without a full-wake signal), sleep grace, safe mode or a security halt in scope | INV-27; FR-052, FR-243 |
| PROP-24 | `lost_by_host` outcomes never consume attempts; cap exhaustion raises an ops alert without a state change | FR-053 |
| PROP-25 | `MERCURY / claude-review` reaches `success` on head H only via review acceptance or a same-scope hold release with INV-06 true for H; `MERCURY / policy` reaches `success` only with no unacknowledged escalation for H | INV-21; FR-166, FR-167 |

Generator: ≥ 10,000 sequences per property per CI run (100,000 nightly), length 1–200 events, seed printed on failure, shrinking on, each sequence executed in both clock modes when it contains a sleep gap. Failing seeds become permanent regression fixtures. TC-SM-004 is the suite (C's SMT-03); TC-SM-007, -009, -012, -014, -015, -021, -023 isolate individual properties for diagnosis.

---

## 6. Crash, power-loss and recovery harness (L9)

- **Crash-point registry** is C's (`architecture/components.md` §8.7): one point per transaction boundary and one before and after each outbox call, git commit, fsync and DB record of a SHA. DoD D4 requires every new persistent step to register a point.
- **Harness.** Per run: seed, scenario, crash point and hit count; start the daemon at T2 with fakes, `SIGKILL` at the point, restart, run to quiescence; check PROP-01…24 and the external-effect ledger kept by the fakes.
- **Ledger checks.** PRs per task ≤ 1; pushes produce one head per commit set; review requests per head ≤ 1; check-run conclusions per head monotonic; Linear comments per decision event ≤ 1; notifications per (task, kind, subject version) ≤ 1.
- **Duplicate execution** follows NFR-001: two concurrently active runs violating INV-02, or a second run for the same (task, kind, binding) after a validated result was recorded. Re-execution after a lost run is not a violation; it is counted (NFR-026) and must be classified `lost_by_host` when the boot session changed or `exit.json` says `supervisor_lost` (TC-REC-032).
- **Pass criterion (NFR-001).** 1,000 randomized runs per nightly (200 at M1 exit), every point ≥ 10 hits, 0 ledger violations, 0 lost tasks, 0 `quick_check` failures.
- **Power loss.** Logic: Linux fault filesystem (drops un-fsynced writes) for SQLite paths (TC-REC-002). Durability evidence: **T4v**, 50 force-stops under write load including git commits in the mirror (TC-REC-020): `integrity_check` ok; every DB-recorded `last_commit_sha` present (`git cat-file -e`) or the step classified `lost_by_host` and replayed from the last durable commit (NFR-053).
- **Real Mac** procedures (D, `operations/recovery.md` §6): sleep during `IMPLEMENTING` and waiting states, lid-close ≥ 2 h, dark wake with Power Nap, logout with an active run, reboot with in-flight tasks, `kill -9` ×10, `launchctl bootout`, locked Keychain, BTM toggle off, upgrade with `--keep-runs`. Evidence: audit log excerpt, `launchctl print`, `pmset -g log`, power-helper log.

---

## 7. Gates and pilot acceptance

### 7.1 Milestone test gates

Phases and dependencies are defined in `planning/roadmap.md`. "Must pass" lists TCs at their stated level.

| Milestone | Must pass | Measurable gate |
|---|---|---|
| P0a | P0-001…025, P0-033…035, P0-037, P0-039…041, P0-201…214, P0-073 | 0 Open checks gating M1 |
| P0b | P0-026…032, P0-036, P0-044 (**[ROOT]**) | Agent uid installed; P0-027 canaries 0 reads with probe processes |
| P0c | P0-060, P0-220…225, P0-230…241, P0-072, P0-074, TC-OPS-016 (sandbox), TC-GOV-110, TC-SEC-114 | Identities equal the inventory (SAC-02 rehearsal); SEC-T-16 cases (a)–(e) rejected on the sandbox |
| P0d | TC-OPS-009, TC-OPS-010 | CI, secret scan and ID lint green |
| M1 | TC-UNIT core, TC-SM-001…014, -019, -021, -023, -027, -028 (logic), TC-CON-001, -009…013, TC-INT-003…005, -010, -012, -013, -020…025, -030, TC-CONC-001/004, TC-REC-001 (200 runs), TC-REC-030…036, TC-SEC-128 (FakeBroker grammar), TC-SEC-150, TC-SEC-161, TC-SEC-191 | 0 counterexamples; 0 ledger violations; **G-S1** recorded before any real agent run on the Mac |
| M2 | TC-INT-001/002, TC-CON-006/007, TC-SBX-001, TC-NET-001…003/006/008, TC-DUP-001/002/006, TC-PERF-002 (Linear), TC-GOV-115 (read only), TC-E2E-011/014/017 | 0 missed of 100 updates; 0 writes in sandbox audit |
| M3 | TC-CON-003/014, TC-UNIT-010/011/013, TC-E2E-006/008, TC-SM-015, TC-SEC-103, -121, -123, -124, -127, -152, TC-PI-130…133 (guards with fakes), TC-AFS-001/005/006/011 | 0 Codex spawns without authorization; snapshot tests 100 % |
| M4 | TC-CON-004/005, TC-E2E-002/003, TC-SM-007/008/026, TC-AFS-003/004/009/010, TC-INT-026, TC-SEC-122, -126, -194, TC-REC-037, TC-PERF-003 | 0 implementation spawns with stale approval; **G-S2 evidence**: TC-SEC-120, -121, -128, -129, -125 (verify/deps profiles) with real agents as `_mercuryagent` |
| M5 | TC-INT-006…009, -027, -028, TC-E2E-001 (to PR open), TC-E2E-007/021, TC-SBX-002, TC-DUP-004, TC-UNIT-043/053, TC-AFS-007, TC-SEC-140…145, -151, -153, -170…173, -192, TC-PI-134…139, TC-GOV-111, -112, -116 (all cases), TC-SM-016, TC-REC-034 | **G-S3** before the first sandbox push |
| M6 | TC-E2E-004/005/012/013/018/019/020, TC-SBX-003, TC-GOV-117, -118, TC-SM-020/025, TC-SEC-154, TC-UNIT-054, TC-PERF-002 (GitHub) | Bot reviews 100 % `COMMENT`; check success only on the reviewed head |
| M7 | TC-SBX-004/005/006/009, TC-GOV-004/006, TC-E2E-009/010/015/016, TC-UNIT-050…052/070/071, TC-DUP-005, TC-SM-017/018/022, TC-SEC-143, -160…164, -180, -181, -190, -193, TC-REC-019/021/039, TC-OPS-011, live-agent sandbox smoke | Audit 10/10; ≤ 1 notification per event; anchors at every carrier; G-S5 controls built |
| M8 | TC-REC-001 (1,000), TC-REC-002…021, TC-REC-020 (T4v 50/50), TC-NET-*, TC-PI-130 (≥ 60 variants, real agents), all TC-SEC-1xx at T4, TC-PERF-*, TC-OPS-001…013, TC-CON-002/008 | All L7–L16 exit criteria; SAC-01…20 evidence collected |
| M9a | TC-PIL-001, TC-OPS-016 (`network_monitor`), P0-240, TC-E2E-022 | §7.3 |
| M9b | TC-PIL-002, TC-PIL-004 | §7.3; G-S4 at entry |
| M9c | TC-PIL-003 | §7.3; G-S5 at entry |

### 7.2 Security gates (E's G-S1…G-S5 and their SAC evidence)

E owns each gate's controls (`security/threat-model.md` §8.10) and each SAC threshold (§10.1). F places the gates and lists the evidence TCs. A gate is recorded in the audit log and in `planning/roadmap.md` §4 only when every SAC row is green with evidence.

| Gate | Placed before | SAC evidence (TCs) |
|---|---|---|
| **G-S1** | Any real agent run on the Mac (M1 exit; M1–M4 runs on the sandbox only) | SAC-03 (TC-SEC-103); SEC-204/208/203 self-tests (TC-SEC-122, TC-SEC-123, TC-INT-026); P0-201; P0-074 (policy checklist) |
| **G-S2** | First workspace-write Codex, `verify` or `deps_install` on a non-sandbox repository (CON-018); evidence collected at M4 | P0-049 (agent-uid egress, required whenever `deps_install` is enabled for a non-sandbox repo; VE-17); SAC-05 (TC-SEC-120, P0-027), SAC-13 (TC-SEC-121), SAC-14 (TC-SEC-128), SAC-18 (TC-SEC-125, TC-SEC-171), SAC-19 (TC-SEC-129) |
| **G-S3** | First sandbox push (M5 exit) | SAC-01 (TC-GOV-116), SAC-02 (TC-GOV-112), SAC-06 (TC-SEC-150/151), SAC-07 (TC-SEC-140…144), SAC-11 (TC-PI-134…136), SAC-16 (TC-PI-138), SAC-17 (TC-GOV-117); TC-SEC-124; TC-GOV-111 |
| **G-S4** | Supervised pilot on a target repository (M9b entry) | G-DETECT written acceptance or G-ORG (OPS-017); SAC-04 (TC-PI-130), SAC-09 (TC-GOV-115), SAC-10 (TC-SEC-193), SAC-12 (traceability §10.2 ASM-E rows closed), SAC-15 (TC-SEC-145), SAC-20 (TC-SEC-154) |
| **G-S5** | Unattended or overnight operation (M9c entry; controls built in M7) | G-ORG on every target (OD-01); OD-36 decided (Addendum A); SAC-08 (TC-SEC-161, -163, -164); SEC-604 anchoring live (TC-SEC-163); SEC-906 (TC-SEC-191); **SAC-01…SAC-20 all green** |

### 7.3 Pilot acceptance (T5, `network_monitor`; OD-16 defaults)

| Stage | Duration | Pass criteria |
|---|---|---|
| Shadow, MIG-1 (TC-PIL-001) | ≥ 10 working days | Triage dry-run only: 0 writes to GitHub or Linear by MERCURY; for every issue the operator labelled `mercury`, MERCURY's eligibility and authorize/decline proposal recorded next to the operator's actual handling; ≥ 90 % agreement on eligibility, and every disagreement explained in the report; spend per decision recorded (input for the OD-08 daily cap) |
| Supervised, MIG-2 (TC-PIL-002) | ≥ 10 tasks end-to-end; first 5 at concurrency 1; dispatch only in operator-declared supervision windows unless G-S5 passed | 0 human relays; 0 duplicate side effects; 0 governance violations; audit 10/10 for every task; availability ≥ 99 % per traceability §1.5; median operator touch-points ≤ 2 per task plus escalations; ≤ 2 notifications on happy-path tasks |
| Cutover and watch, MIG-3/4 (TC-PIL-003/004) | 30 days | 0 Slack coordination posts for MERCURY tasks; Slack token revoked (recorded); max undetected stall ≤ state timeout + 2 poll intervals; availability ≥ 99.5 % |

---

## 8. Test case catalogue

"Covers" uses requirement IDs from `planning/traceability.md`. ⓗ = operator step. Procedures for `P0-*` and T4 recovery tests are D's; for `TC-SEC-1xx`, `TC-GOV-11x` and `TC-PI-13x` they are E's (threat model §10.2), with the binary criterion there.

### 8.1 TC-P0 (Phase 0 register)

`P0-001…049`: D's Mac register (`operations/macos-service.md` §16) — read-only P0-001…025, agent uid P0-026…032 **[ROOT]**, experiments P0-033…048, egress P0-049 (procedure in `security/threat-model.md` §10.4; gates G-S2 whenever `deps_install` is enabled for a non-sandbox repository, VE-17). `P0-201…241`: B's agent-CLI, GitHub and Linear checks (`integrations/github.md` Phase 0 table, one ASM-B per row with its gate). Each row in those tables carries its procedure, pass criterion and gate; closure is tracked in traceability §10.2. F-allocated checks (governance and programme):

| P0 | Check | Env | Pass criterion | Covers |
|---|---|---|---|---|
| P0-060 | ⓗ `mercury-bot` and `mercury-ops` created and installed (`mercury-ops` only on `project-mercury` and the anchor repo); minted token `permissions` equal the inventory incl. `statuses:read` (SEC-T-12 part 1) | T3 | Exact sets; no `administration`, `workflows`, `actions` (unless OD-37) | OPS-002, SEC-101 |
| P0-067 | Read-only credential reads Actions settings (ASM-E-03) | T3 | Recorded; if not, SEC-105 checks stay POL | SEC-105 |
| P0-068 | Same-repo branch workflows and deploy keys vs `workflows` (ASM-E-07) | T3 | Recorded (G-SPLIT only) | SEC-109 |
| P0-072 | ⓗ SEC-T-16 cases (a)–(g) on the sandbox | T3 | SAC-01 | SEC-100, SEC-109 |
| P0-073 | MIG-0 inventory of `network_monitor` scripts, protections, Linear automations, coding-session settings (read-only) | read-only | Inventory recorded | FR-300 |
| P0-074 | ⓗ OD-35 / OPS-019 policy checklist evidence | Operator | Every item evidenced | OPS-019, SEC-106, SEC-804 |

Phase 0 checks cited by requirements in this plan that live in B's table: P0-201 (`disableAllHooks` vs SDK hooks), P0-207 (process-env visibility), P0-209 (Codex output-schema mismatch), P0-211/P0-214 (wire schemas accepted), P0-213 (Claude spawn via `agent-exec`), P0-220 (Linear app), P0-224 (closing link types), P0-225 (Linear app cannot merge), P0-231 (`metadata:read` drift reads), P0-233 (auto-merge forbidden), P0-235 (pinning permission), P0-236 (check-run update), P0-237 (COMMENT never blocks), P0-238 (deploy-key push), P0-240 (draft-PR CI).

### 8.2 TC-UNIT

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-UNIT-001 | Eligibility rule evaluator, each rule true/false | All cases pass | FR-002 |
| TC-UNIT-002 | Repo mapping resolver 0/1/many | All cases | FR-003 |
| TC-UNIT-003 | Blocked-by resolver across relation states | All cases | FR-004 |
| TC-UNIT-004 | Triage input builder incl. prose references | Golden match | FR-006 |
| TC-UNIT-005 | Issue-level `mercury_status` transitions | Every observed issue has exactly one current status | FR-007 |
| TC-UNIT-010 | Authorization record builder: canonical JSON, hash, versioning, supersession | Hashes stable; new version on re-authorization | FR-021 |
| TC-UNIT-011 | Authorization guard (missing/revoked/expired/superseded/mismatch incl. `spec_hash`) at dispatch and at result application | 100 % branch coverage; all negatives refused | CON-005, FR-022, FR-121, NFR-100 |
| TC-UNIT-012 | Plan-approval binding and mandatory-criteria guard | 100 % branch coverage | CON-006, FR-102, FR-106, FR-121, NFR-100 |
| TC-UNIT-013 | `spec_hash` normalization | Material edits detected; cosmetic ignored | FR-024 |
| TC-UNIT-020 | Retry calculator vs the single retry matrix | Matches matrix rows | FR-045 |
| TC-UNIT-021 | Run outcome classifier incl. `lost_by_host`, `supervisor_lost`, `config_fatal` | Every fixture as specified | FR-044, FR-053, NFR-083 |
| TC-UNIT-022 | Scheduler order, limits, ageing bound | All properties hold | FR-041, FR-042 |
| TC-UNIT-030 | Envelope builder/validator | One mutant per field rejected | FR-060 |
| TC-UNIT-031 | Artifact and run-record atomic write; hash verify | Tamper detected 100 %; no partial file | FR-064, NFR-051 |
| TC-UNIT-040 | Branch/worktree naming per Linear mode | Pattern conformance; 0 collisions in 10k names | FR-120 |
| TC-UNIT-041 | Commit trailer formatter/parser (GH §4.2 set) | Round-trip equality | FR-141, SEC-111 |
| TC-UNIT-042 | PR body template renderer per Linear mode | Golden match | FR-142 |
| TC-UNIT-043 | Diff gate: scope, block-class vs escalate-class paths, allowance | Block fixtures block; escalate fixtures proceed with policy pending | FR-124, SEC-309 |
| TC-UNIT-050 | Linear projection tables (both modes) | All 17 states mapped per mode | FR-200 |
| TC-UNIT-051 | Notification dedup key and suppression | Duplicates suppressed | FR-221 |
| TC-UNIT-052 | Merge-verification predicate (checks M1…M8 by ID, `integrations/github.md` §8; not-yet-available vs definitive) | Each failing check detected with the right scope | FR-181, FR-182 |
| TC-UNIT-053 | PR ownership check (`user.login`, head repo, recorded branch) | Foreign PRs ignored | SEC-107 |
| TC-UNIT-054 | Pre-review re-check (head = reviewed SHA, checks, policy) | Review request suppressed on any mismatch | SEC-904 |
| TC-UNIT-061 | Config validator (incl. no hard-coded team/repo; parameter clamps) | Invalid configs rejected with field path | CON-013, NFR-072 |
| TC-UNIT-062 | Credited-time algorithm (`min(Δmono, Δwall, 3×tick)`; gap > `clock.sleep_gap_s` unexplained = sleep; wall jumps) in both clock modes | 0 credited sleep; 0 false gaps from measured blocking | FR-082, FR-282 |
| TC-UNIT-070 | Deterministic v4-shaped UUIDs for Linear comments | Same input → same UUID; valid v4 shape | FR-202 |
| TC-UNIT-071 | Linear endpoint allowlist | Every non-allowlisted mutation throws | SEC-805 |
| TC-UNIT-072 | Dispatcher refuses non-sandbox workspace-write/`verify`/`deps_install` while G-S2 is not recorded | 100 % refused | CON-018 |
| TC-UNIT-073 | Provenance tag renderer for untrusted prompt content | Every untrusted item tagged; tag injection escaped | SEC-301 |

### 8.3 TC-SM

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-SM-001 | Table conformance: all allowed transitions (SMT-01) | 100 % accepted with guards true | FR-080 |
| TC-SM-002 | Non-listed (state, event) pairs rejected and audited | 100 % rejected | FR-080 |
| TC-SM-003 | Evidence and audit fields written atomically | 100 % complete | FR-081, FR-261, NFR-060, SEC-601 |
| TC-SM-004 | PROP suite (§5) incl. SMT-03/04 | 0 counterexamples | CON-003, CON-004, CON-005, FR-022, FR-040 |
| TC-SM-005 | Replay determinism (PROP-10) | Equality in 10,000 logs | FR-084, NFR-101 |
| TC-SM-006 | Terminal states absorbing; `COMPLETED` needs verification | 0 escapes | FR-083 |
| TC-SM-007 | Plan revision invalidates approval (SMT-05) | 0 counterexamples | CON-006, FR-102, SEC-306 |
| TC-SM-008 | Budgets N/M/K/H → `BLOCKED` + one escalation; grants add exactly `extra` (SMT-07) | Exact | CON-012, FR-104, FR-163, SEC-315 |
| TC-SM-009 | Timeouts with sleep gaps, both clock modes | 0 sleep-induced failures; awake overrun fires | CON-009, FR-082, FR-282, NFR-101 |
| TC-SM-010 | Cancel from every non-terminal state | 0 work effects after cancel; each cancel notice once | FR-046 |
| TC-SM-011 | Pause/resume (hold) from every pausable state | State unchanged; 0 repeated effects | FR-047 |
| TC-SM-012 | Holds never change state; release resumes (SMT-10, PROP-20) | 0 violations | FR-050 |
| TC-SM-013 | Hold ageing escalates once per hold episode (`hold_age.*`) | Exactly one escalation | FR-050 |
| TC-SM-014 | Security holds never auto-clear (PROP-21) | 0 auto-clears | FR-050 |
| TC-SM-015 | Spec drift (SMT-11): hold set; post-change results not applied; re-authorization creates a new version (PROP-22) | 0 applied results before re-authorization | FR-024, SEC-307 |
| TC-SM-016 | Policy escalation (SMT-12): `BLOCKED(policy_ack_required)` cleared only by presence `policy ack` for that head | Ack for head X never clears head Y | FR-167 |
| TC-SM-017 | Merge-verification failure scope (SMT-13): actor / not-on-base → global halt; other checks → repo `integrity_alert` | Scope exact per check | FR-182, SEC-906 |
| TC-SM-018 | `merged_unreviewed_head` → policy notice, not security; `ack-merge` closes | No SECURITY notice; one policy notice | FR-182 |
| TC-SM-019 | Initiator restriction fuzzing (SMT-02) | 0 accepted mismatches | FR-081 |
| TC-SM-020 | Revision-request routing per source (RD-8) | Verbatim only for validated Claude reviews; all others via a `revision_request` run | FR-163 |
| TC-SM-021 | Timer rule: no fire before an attempt after wake; measured from first observation; wake coalescing | 0 premature fires; 1 summary | FR-085 |
| TC-SM-022 | Restore with unverifiable authority → `BLOCKED(reauthorization_required)`, never `guard_integrity_failure` | 100 % | FR-264 |
| TC-SM-023 | Dark-wake dispatch suppression (PROP-23) | 0 dispatches | FR-052 |
| TC-SM-025 | Review bound to head SHA; foreign push (SMT-06) | Stale verdict never enables approval state | FR-165, SEC-308 |
| TC-SM-026 | Scope amendment re-plans; limits-only amendment does not (SMT-08) | As specified | FR-102 |
| TC-SM-027 | Recovery per state × run situation (SMT-09) | Each cell reaches the specified state | FR-280 |
| TC-SM-028 | Gate checks (SMT-14, PROP-25): CR success only via T24/T24p or same-scope release; PL success only after acknowledgement; T22 never waits on MERCURY's own contexts | 0 violations | FR-144, FR-166, FR-167 |

### 8.4 TC-CON

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-CON-001 | Message schemas golden/mutants | 100 % | FR-060, FR-061, SEC-303 |
| TC-CON-002 | Schema N−1 compatibility | 100 % | FR-065 |
| TC-CON-003 | Claude structured outputs per decision type incl. error subtypes | 100 % | FR-020, FR-062, FR-101, FR-160 |
| TC-CON-004 | Codex JSONL contract, pinned version | 100 % | FR-125, NFR-093 |
| TC-CON-005 | Codex plan output contract | 100 % | FR-062, FR-100 |
| TC-CON-006 | GitHub REST shapes (pulls, reviews, check runs with `app.id`, rules for branches, merges) | 100 % | FR-181 |
| TC-CON-007 | Linear GraphQL shapes | 100 % | FR-001 |
| TC-CON-008 | Agent CLI flag and hash self-test vs pins | All required flags present; hashes match | NFR-090, NFR-093, SEC-701 |
| TC-CON-009 | Fixtures validate (CT-01) | 100 % | FR-061 |
| TC-CON-010 | Minor-version compatibility (CT-02) | 100 % | FR-065 |
| TC-CON-011 | Adapter contract vs recorded streams (CT-03) | 100 % | FR-062 |
| TC-CON-012 | GitHub adapter has no merge/approve/request-changes/dismiss/update-branch/auto-merge path (CT-04, static + runtime) | 0 paths | FR-162, FR-180, SEC-102 |
| TC-CON-013 | JCS canonical JSON vectors (CT-05) | Hashes stable across Node versions | FR-021 |
| TC-CON-014 | Wire-copy generation: every canonical output schema has a strict-subset copy; canonical Ajv validation catches dropped constraints | 100 % | FR-062, SEC-303 |
| TC-CON-015 | Idempotency keys conform to the dedup key catalogue | 100 % | FR-043 |

### 8.5 TC-INT

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-INT-001 | Linear poller vs FakeLinear (overlap, dedupe, 100 updates, A→B→A) | 0 missed, 0 double | FR-001 |
| TC-INT-002 | GitHub poller (ETag, checks, rate limits) | Correct; 304s not reprocessed | FR-144 |
| TC-INT-003 | Inbox/outbox, both drivers | 0 lost/duplicated | FR-040, FR-063, NFR-091 |
| TC-INT-004 | Single instance (`flock`): second instance logs and exits 0 within 5 s | As specified | FR-048, FR-903 |
| TC-INT-005 | Supervisor via FakeBroker: kill ladder, group termination (RT-05) | 0 surviving descendants; PID reuse safe | CON-016, FR-044 |
| TC-INT-006 | Worktree manager create/cleanup (RT-10) | Refuses unsafe cleanup | FR-120, FR-184 |
| TC-INT-007 | Commit/push to a local bare remote; idempotent | Single head; trailers present | FR-140 |
| TC-INT-008 | `verify` step records test-results artifact | Fields complete | FR-122 |
| TC-INT-009 | `deps_install` from lockfile outside Codex | Codex network off; install logged | FR-123 |
| TC-INT-010 | CLI against running daemon, all §5.5 verbs | Correct; mutating verbs audited | FR-049, FR-240, FR-241, NFR-062 |
| TC-INT-011 | Online backup and restore in a worker thread | Restored DB passes `integrity_check` | NFR-022 |
| TC-INT-012 | Expand/contract migration with injected failure | Original DB intact | NFR-023 |
| TC-INT-013 | Startup self-test: pragmas, pins, config, helpers, ≤ 15 s | Refuses on each violation; time bound met | NFR-050, NFR-090, NFR-095 |
| TC-INT-020 | Every DB trigger: one negative, one positive (DBT-01) | 100 % | FR-021, INV-13 |
| TC-INT-021 | Partial unique indexes (DBT-02) | Violations fail | FR-040 |
| TC-INT-022 | Migration from every released schema (DBT-03) | Clean checks | NFR-023 |
| TC-INT-023 | Audit chain tamper at any field (DBT-04) | Detected at the row | SEC-602 |
| TC-INT-024 | Control API principals; no authorize/approve method; token required (RT-09) | 100 % | CON-003 |
| TC-INT-025 | `agent-exec` spec generation and FakeBroker: run dir, scratch, fd 3, `exit.json` | Grammar-valid specs only; scratch removed | FR-051, SEC-207 |
| TC-INT-026 | Per-task `CODEX_HOME`: generated read-only `config.toml` re-hashed before every run; `sessions/` archived at cleanup | Tamper → regenerated, audited | FR-100, SEC-203 |
| TC-INT-027 | Plumbing commit against the mirror; push from the mirror with fd `GIT_ASKPASS` | Token never in env/argv; hooks never run | FR-140, SEC-407 |
| TC-INT-028 | `mercury toolchain sync` installs pinned toolchains; agent can execute, not write | As specified | OPS-015, SEC-708 |
| TC-INT-029 | Required contexts derived from `GET /rules/branches/{base}` each evaluation | Ruleset change picked up next evaluation | FR-144 |
| TC-INT-030 | `mercury status --issues` lists issue-level statuses | All observed issues listed | FR-007 |

### 8.6 TC-E2E

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-E2E-001 | Happy path discovered → `COMPLETED` | Completed; artifacts and audit present; ≤ 2 notifications | CON-013, FR-020, FR-066, FR-100, FR-121, NFR-063 |
| TC-E2E-002 | Plan revision loop (2 cycles) then approval; verbatim template | Plan v3 approved; links and template hash recorded | FR-101, FR-103 |
| TC-E2E-003 | Plan limit exceeded | `BLOCKED` + 1 notification | CON-012, FR-104 |
| TC-E2E-004 | PR review → revision → pass; conditions checked | Pass on new SHA | FR-106, FR-160, FR-163 |
| TC-E2E-005 | CI failure → Claude `revision_request` → fix → green; limit → escalate | As specified | FR-144 |
| TC-E2E-006 | Claude defer/decline/needs_human | 0 Codex spawns | CON-004, FR-002 |
| TC-E2E-007 | Authorization revoked mid-implementation | Run stopped within kill ladder; 0 pushes/PRs after | FR-023 |
| TC-E2E-008 | Spec changed after authorization (pre-PR) | Hold; re-authorization before next run | FR-024, SEC-307 |
| TC-E2E-009 | PR closed unmerged | `CANCELLED(pr_closed)` | FR-185 |
| TC-E2E-010 | `mercury trace` answers 10 questions incl. a crashed task | 10/10 | FR-260, FR-261, NFR-060 |
| TC-E2E-011 | Blocked-by gating | Dispatch only after blocker resolves | FR-004 |
| TC-E2E-012 | Security label and blocking security finding; security review every PR | Guard enforces | FR-105, FR-161, SEC-314 |
| TC-E2E-013 | Human push after Claude pass | Re-review on new SHA | FR-165 |
| TC-E2E-014 | Linear-native delegation / coding session / foreign PR | `BLOCKED`; 0 runs | CON-016, FR-005, FR-904, SEC-803 |
| TC-E2E-015 | Linear mode `integration_owns_done` | MERCURY writes only In Progress + comments + verification comment | FR-183 |
| TC-E2E-016 | Linear mode `mercury_owns_all` | Done only after verification; branch without issue ID | FR-183 |
| TC-E2E-017 | Managed blocker Done in Linear but not `COMPLETED` in MERCURY | Dependent stays undispatched | FR-008 |
| TC-E2E-018 | Revision sources: Claude review, CI, test failure, conflict, operator `CHANGES_REQUESTED`, third-party comment | Routing and provenance per FR-163; third-party text excluded | FR-163, SEC-313, SEC-316 |
| TC-E2E-019 | Draft PR; `MERCURY / claude-review` success only for reviewed head; ready + review request after success | 0 review requests before success | FR-142, FR-166, SEC-114, SEC-904 |
| TC-E2E-020 | Spec change at PR stage | PR stays open; no Codex work before re-authorization | FR-024 |
| TC-E2E-021 | Governance mode enforcement: unrecorded mode → refuse; unattended dispatch to non-G-ORG target → refuse | 100 % refused | CON-014, OPS-017, SEC-109 |
| TC-E2E-022 | Daily spend cap reached | Dispatch hold + 1 notification | NFR-084 |

### 8.7 TC-SBX

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-SBX-001 | Linear sandbox: 100 scripted updates; Todo moves never start work | 0 missed; 0 unauthorized runs | CON-004, FR-001, NFR-005, OPS-004 |
| TC-SBX-002 | PR by `mercury-bot`, draft, naming per mode, Linear link | Author bot; link per mode | CON-008, FR-140, FR-142 |
| TC-SBX-003 | Claude reviews posted as `COMMENT` | 100 % `COMMENT` | FR-162 |
| TC-SBX-004 | ⓗ Operator approves and merges; verification; Linear per mode | Verified; 1 verification comment; p95 ≤ 5 min | FR-181, FR-183, NFR-044 |
| TC-SBX-005 | Linear writes attributed to app actor | 100 % | CON-008, FR-201, SEC-801 |
| TC-SBX-006 | Notification channel matrix: each kind once on its channel | 100 %; NFR-043 latency | CON-011, FR-164, FR-220, NFR-043 |
| TC-SBX-008 | Rate budget, 1 h, 10 active PRs | ≤ 20 % reads | NFR-081 |
| TC-SBX-009 | Interaction with Linear GitHub integration | 0 flaps over 10 min | FR-183 |

### 8.8 TC-AFS

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-AFS-001 | Claude max turns/budget/structured-output retries | Classified; retry/escalate per policy | FR-045, NFR-083 |
| TC-AFS-002 | Hang with no output and no CPU | Detected within stall + 60 s | FR-044, NFR-003, NFR-006 |
| TC-AFS-003 | Codex `turn.failed` | Classified correctly | FR-045 |
| TC-AFS-004 | Runaway descendants | Group killed via `agent-ctl`; 0 orphans | FR-044, FR-125, SEC-704 |
| TC-AFS-005 | Invalid or missing output | Never advances state | FR-062 |
| TC-AFS-006 | Auth failure | `BLOCKED` + 1 notification; ≤ 3 attempts | FR-045 |
| TC-AFS-007 | Out-of-scope and block-class edits | Commit refused; revision requested | FR-124 |
| TC-AFS-008 | Contract break (T-REC-07): 1 retry, then circuit open | No task `FAILED` for environment reasons | FR-045 |
| TC-AFS-009 | 20-minute quiet test command with CPU progress | **Not** stalled; stall only when output and CPU both flat | FR-044, NFR-006 |
| TC-AFS-010 | Claude run killed by coordinator crash is re-run with the same `input_digest` | 0 attempts consumed; same input | FR-054 |
| TC-AFS-011 | Provider schema rejection | Classified `config_fatal`; 1 notification | FR-062 |

### 8.9 TC-NET

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-NET-001 | Drop during polling | No false transitions; resumes | FR-283, NFR-005 |
| TC-NET-002 | Drop during push / PR create (unknown outcome) | Exactly 1 PR | FR-143, FR-283 |
| TC-NET-003 | Drop during Linear write / notification | Exactly 1 comment; delivered after recovery | FR-202, FR-223, FR-283 |
| TC-NET-004 | ⓗ DNS failure after wake (T4) | First poll ≤ `recovery.first_poll_max_s` after network | FR-282, NFR-021 |
| TC-NET-005 | Secondary rate limit with retry-after | Honoured | NFR-081 |
| TC-NET-006 | Flapping link (GitHub up/Linear down and reverse) | 0 `dead` items from network-class errors | FR-283 |
| TC-NET-007 | Captive portal / TLS interception | Treated as offline; TLS never disabled | FR-283 |
| TC-NET-008 | Network loss during outbox delivery and runs (RT-04) | 0 attempts consumed | FR-283 |
| TC-NET-009 | Connectivity probe is authenticated and ETag-conditional | No unauthenticated GitHub requests | FR-283 |

### 8.10 TC-REC

| TC ID | Test | Env | Pass criterion | Covers |
|---|---|---|---|---|
| TC-REC-001 | Randomized crash injection (RT-01, T-REC-01) | T1/T2 | §6 criterion | FR-022, FR-043, FR-143, FR-280, NFR-001, NFR-051 |
| TC-REC-002 | Power loss, SQLite logic (fault FS) | T1 | 0 lost committed transitions | NFR-020, NFR-050 |
| TC-REC-003 | ⓗ Sleep during Codex run and waiting states | T4 | 0 sleep-induced failures; reconcile within `recovery.reconcile_max_s` | CON-009, FR-282, NFR-021, NFR-025 |
| TC-REC-004 | ⓗ Reboot with in-flight tasks | T4 | 100 % recovered; reconcile bound met | FR-280, NFR-020, NFR-025 |
| TC-REC-005 | Orphan sweep via `agent-ctl` with PID reuse (RT-06, T-REC-05) | T1/T4 | Orphans killed; reused PID untouched; dead run detected ≤ 60 s | FR-281, NFR-006 |
| TC-REC-006 | launchd restart after crash ×10 | T4 | `ready` within `svc.restart_to_ready_max_s` 10/10 | NFR-002 |
| TC-REC-007 | SIGTERM (T-REC-08) | T4 | Exit within `svc.shutdown_budget_s`; adoptable runs kept | NFR-024 |
| TC-REC-008 | Corrupted DB at start | T1 | Safe mode; alert | NFR-020, NFR-052 |
| TC-REC-009 | Long downtime summary | T2 | Exactly 1 summary | FR-222 |
| TC-REC-010 | ⓗ Lid-close ≥ 2 h during implementation | T4 | `network_down`/transient; thread resumed; 0 attempts; token re-minted | FR-282 |
| TC-REC-011 | Idle-sleep assertion only while runs are active | T4 | As expected | CON-009 |
| TC-REC-012 | Dark wake / Power Nap with tasks queued | T4 | 0 dispatches during dark wake | FR-052 |
| TC-REC-013 | ⓗ Logout with active Codex run, log back in | T4 | Adopted or lease-terminated; 0 orphans | FR-055 |
| TC-REC-014 | Keychain locked at start | T4 | `credentials` alert; recovery after unlock | OPS-007 |
| TC-REC-015 | Disk full during a run | T2 + T4 | Ballast released; 0 DB corruption | NFR-082 |
| TC-REC-016 | Wall-clock jump ±10 min | T0 + T4 | No false sleep; deadlines correct | FR-282 |
| TC-REC-017 | ⓗ BTM "Allow in the Background" off | T4 | `doctor` reports; watchdog alerts with pending work | OPS-012 |
| TC-REC-018 | Upgrade with `--keep-runs` during a real Codex run | T4 | Adopted; 0 re-runs | OPS-005 |
| TC-REC-019 | Restore a 24 h-old backup with anchors ahead (T-REC-06); epoch confirmed with presence; fixture includes an authorization revoked, a task cancelled by CLI and a budget grant consumed **after** the backup | T2 | Epoch recorded; **every** non-terminal task is `BLOCKED(reauthorization_required)` (history-losing restore: backup audit head seq < last anchor seq, or reason `new_host`; VD-01); 0 tasks cancelled by the restore; 0 dispatches before a new authorization version; no revoked authorization, CLI cancel, consumed budget or expiry is resurrected (authority only shrinks) | FR-264, SEC-607 |
| TC-REC-020 | Power-loss cycles (T-REC-02) | **T4v** | 50/50 per §6 | NFR-020, NFR-050, NFR-053 |
| TC-REC-021 | Merged while asleep > 24 h | T2 | Verified, not blocked | CON-009, FR-085 |
| TC-REC-022 | `agent-exec` rejects a tampered `spec.json` mode, a symlinked `--run-dir`, an unknown flag, and a key on fd 3 for `verify` (D, recovery §6) | T4v | 100 % rejected with exit 125; nothing executed; `config_fatal` hold | FR-051, SEC-212 |
| TC-REC-023 | Agent strips ACLs in its worktree (D, recovery §6) | T4v | `policy_violation`; `BLOCKED(security_policy_violation)`; nothing committed | SEC-405, SEC-903 |
| TC-REC-030 | Adoption of a detached Codex run after coordinator crash (T-REC-03) | T1/T4 | Result adopted; 0 re-runs | FR-054, NFR-026 |
| TC-REC-031 | Sleep simulation in both clock modes (RT-03, T-REC-04) | T0/T2 | Budget unchanged; one coalesced notice | CON-009, FR-282 |
| TC-REC-032 | Reboots during a step → `lost_by_host`; cap exhaustion | T2 | 0 attempts; 1 ops alert at cap; state unchanged | FR-053, NFR-026 |
| TC-REC-033 | Supervisor lease: daemon stopped with live run | T1 (FakeBroker) + T4 | Run ended after `supervisor.lease_stale_min` + ladder; `exit.json` `supervisor_lost` | FR-055, SEC-214 |
| TC-REC-034 | Git/DB durability ordering; `cat-file` verification after crash | T1 | DB never references a missing object | NFR-051, NFR-053 |
| TC-REC-035 | Startup/exit contract: lock held, DB corrupt, schema too new | T1 | Exit 0 / safe mode / `fatal.json` + exit 0 | FR-280, SEC-908 |
| TC-REC-036 | Crash loop → safe mode | T1 | Safe mode after `svc.crash_loop_starts` | NFR-027 |
| TC-REC-037 | Worktree reset policy | T1 | Tree = recorded commit; patch archived; `-x` only with deps re-queue | FR-126 |
| TC-REC-038 | Authorization revoked while daemon down; adopted output | T2 | Output not applied | FR-022, FR-054 |
| TC-REC-039 | N authorizations expire during sleep | T2 | 1 summary notification | FR-085 |

**Recovery §6 numbering (Phase 5, VF-04).** `operations/recovery.md` §6 proposes IDs; the canonical IDs are the rows above. Where D's §6 label differs, read: §6 TC-REC-002 → TC-REC-020 (T4v) and TC-REC-002 (logic); §6 -003 → TC-REC-030; §6 -004 → TC-REC-031; §6 -006 → TC-REC-019; §6 -007 → TC-AFS-008; §6 -008 → TC-REC-007; §6 -009 → TC-REC-033. §6 TC-REC-001, -005 and -010…-023 match.

### 8.11 TC-DUP and TC-CONC

| TC ID | Test | Pass criterion | Covers |
|---|---|---|---|
| TC-DUP-001 | Duplicate Linear events | Once | FR-001, FR-202 |
| TC-DUP-002 | Duplicate/replayed GitHub reviews and checks | Once | NFR-005 |
| TC-DUP-003 | Duplicate queue delivery | Idempotent | FR-043, FR-063 |
| TC-DUP-004 | PR create retried after unknown outcome | 0 duplicates | FR-143 |
| TC-DUP-005 | 100 unchanged polls | 0 repeat notifications | FR-221 |
| TC-DUP-006 | Duplicate and reordered observations; A→B→A (RT-02) | One transition per fact | FR-001 |
| TC-CONC-001 | Limits under load (RT-08) | Never exceeded; fairness bound | FR-041 |
| TC-CONC-002 | Two tasks, one repo | Per-repo limit; isolation | FR-041 |
| TC-CONC-003 | CLI and daemon concurrent access | 0 `SQLITE_BUSY` surfaced | FR-048 |
| TC-CONC-004 | Lease expiry and re-claim | PROP-05 holds | FR-040 |

### 8.12 TC-SEC

F-owned seeds and additions:

| TC ID | Test | Env | Pass criterion | Covers |
|---|---|---|---|---|
| TC-SEC-003 | Codex implementation sandbox denies network | T4 | Outbound attempt fails | SEC-211 |
| TC-SEC-004 | Secret canary absent from logs, artifacts, PR bodies, check output, Linear comments | T2 + T3 | 0 occurrences | CON-010, NFR-062, SEC-501 |
| TC-SEC-006 | Claude reviewer tools limited to Read/Grep/Glob with confinement hook; denials audited | T1 | Denials recorded | SEC-204 |
| TC-SEC-008 | No listener on non-loopback interfaces | T4 | 0 | CON-002, FR-900, FR-901 |
| TC-SEC-020 | Credentials read once at start and on `reload-credentials`; single prefix | T4 | No reads at other times; inventory matches | OPS-007, SEC-503 |

E's tests registered by alias (procedure and binary criterion in `security/threat-model.md` §10.2; gate per §7.2):

| TC ID | SEC-T | Env | Covers |
|---|---|---|---|
| TC-SEC-103 | SEC-T-03 hook/MCP planting | T1/T4 | SEC-204 |
| TC-SEC-113 | SEC-T-13 operator canaries in coordinator env | T4 | SEC-103 |
| TC-SEC-114 | SEC-T-14 repository settings | T3 | SEC-105, SEC-506, SEC-707 |
| TC-SEC-120 | SEC-T-20 credential canaries per run kind | T4 | SEC-201, SEC-405, CON-018 |
| TC-SEC-121 | SEC-T-21 env allowlist per run kind | T4 | SEC-202, INV-10 |
| TC-SEC-122 | SEC-T-22 argv builder, forbidden flags, `config.toml` regeneration | T0 + T4 | SEC-203, SEC-208 |
| TC-SEC-123 | SEC-T-23 operator `~/.claude` MCP and hooks not loaded | T4 | SEC-204, SEC-802 |
| TC-SEC-124 | SEC-T-24 snapshot builder | T0 | FR-066, SEC-205 |
| TC-SEC-125 | SEC-T-25 egress of `verify`, `deps_install`, Codex | T4 | FR-122, SEC-206, SEC-215 |
| TC-SEC-126 | SEC-T-26 instruction files before fresh and resumed runs | T1 | SEC-209 |
| TC-SEC-127 | SEC-T-27 tampered pinned binary | T4 | NFR-090, SEC-210, SEC-701 |
| TC-SEC-128 | SEC-T-28 wrapper grammar fuzzing; `sudo -l` | T1 (FakeBroker grammar) + T4 | FR-051, SEC-212 |
| TC-SEC-129 | SEC-T-29 supervised lifetime, safe mode, halt | T4 | SEC-214 |
| TC-SEC-140 | SEC-T-40 planted git config/hooks | T1 | FR-140, SEC-401 |
| TC-SEC-141 | SEC-T-41 pointer and mirror tamper | T1 | FR-140, SEC-402 |
| TC-SEC-142 | SEC-T-42 tree checks | T0 | SEC-403, SEC-404 |
| TC-SEC-143 | SEC-T-43 removal with escaping symlinks | T4 | FR-184, SEC-406 |
| TC-SEC-144 | SEC-T-44 push path and token delivery | T1 | SEC-407 |
| TC-SEC-145 | SEC-T-45 presence tier per principal | T4 | CON-003, FR-167, FR-242, SEC-115, OPS-018 |
| TC-SEC-150 | SEC-T-50 redaction at every sink (incl. RT-07) | T0 | NFR-062, SEC-501 |
| TC-SEC-151 | SEC-T-51 pre-push scan; canary → halt | T1 | SEC-502 |
| TC-SEC-152 | SEC-T-52 no secrets in `ps`, plist, env | T4 | SEC-503, SEC-505 |
| TC-SEC-153 | SEC-T-53 neutraliser at public sinks | T0 | FR-142, SEC-304 |
| TC-SEC-154 | SEC-T-54 disclosure policy | T1 | FR-168, SEC-507 |
| TC-SEC-160 | SEC-T-60 append-only audit | T0 | SEC-601 |
| TC-SEC-161 | SEC-T-61 chain mutation → safe mode | T1 | FR-262, SEC-602, SEC-605, SEC-908 |
| TC-SEC-162 | SEC-T-62 HMAC and restore mapping (if implemented) | T1 | SEC-603 |
| TC-SEC-163 | SEC-T-63 anchor divergence; carriers (Linear comment, private anchor repo; check summary only on private repos) | T1 + T3 | FR-263, SEC-604 |
| TC-SEC-164 | SEC-T-64 restore epoch with and without presence. Added F criterion (Phase 5, VD-01): after an accepted history-losing restore epoch, every non-terminal task is `BLOCKED(reauthorization_required)` and 0 dispatches occur before re-authorization; without presence the epoch is refused | T1 | FR-264, SEC-607 |
| TC-SEC-170 | SEC-T-70 lockfile lint | T0 | SEC-702 |
| TC-SEC-171 | SEC-T-71 `deps_install` scripts, ack, hosts | T4 | FR-123, SEC-703, SEC-215 |
| TC-SEC-172 | SEC-T-72 resource limits | T4 | SEC-704 |
| TC-SEC-173 | SEC-T-73 mutation budget | T1 | SEC-705 |
| TC-SEC-180 | SEC-T-80 Linear token capabilities | T3 | SEC-801, SEC-805 |
| TC-SEC-181 | SEC-T-81 delegation, coding session, foreign PR | T3 | FR-005, SEC-803 |
| TC-SEC-190 | SEC-T-90 notification routing; locked ops issue | T3 | FR-224, SEC-901, SEC-907 |
| TC-SEC-191 | SEC-T-91 kill switch and every halt trigger | T2 | FR-243, SEC-902, SEC-906 |
| TC-SEC-192 | SEC-T-92 sandbox violations | T4 | SEC-903 |
| TC-SEC-193 | SEC-T-93 merge-verification mismatches M1–M8 (`integrations/github.md` §8; incl. unexpected base commit, M5) | T3 | FR-182, SEC-905 |
| TC-SEC-194 | SEC-T-94 cross-run isolation | T4 | SEC-213 |

### 8.13 TC-GOV

| TC ID | Test | Env | Pass criterion | Covers |
|---|---|---|---|---|
| TC-GOV-004 | ⓗ Non-operator merge after approval (G-DETECT → incident ≤ 5 min awake; G-ORG → rejected) | T3 | As specified (SAC-10) | CON-014, FR-182, SEC-109 |
| TC-GOV-005 | No merge/approve code path; network log of all suites | static + logs | 0 calls | FR-180, FR-902 |
| TC-GOV-006 | Comment claiming approval/authorization/command | T2 + T3 | 0 state changes | FR-203, FR-241, SEC-302 |
| TC-GOV-008 | Identity permission sets equal the inventory | T3 | Exact | OPS-002, SEC-101 |
| TC-GOV-110 | SEC-T-10 golden ruleset/settings compare | T3 | E | SEC-100, SEC-104, SEC-112, OPS-016 |
| TC-GOV-111 | SEC-T-11 forbidden endpoints throw; static scan | T0 | E | FR-180, SEC-102 |
| TC-GOV-112 | SEC-T-12 token scopes; workflow push; deploy key; auto-merge | T3 | E (SAC-02) | OPS-002, SEC-101 |
| TC-GOV-115 | SEC-T-15 drift detection ≤ 60 min awake, halt | T3 | E (SAC-09) | OPS-003, SEC-108 |
| TC-GOV-116 | SEC-T-16 unauthorized merge cases (a)–(g) | T3 ⓗ | E (SAC-01) | CON-007, SEC-100, SEC-109 |
| TC-GOV-117 | SEC-T-17 forged same-name check/status | T3 | E (SAC-17) | FR-166, SEC-113 |
| TC-GOV-118 | SEC-T-18 bot `COMMENT` review never blocks | T3 ⓗ | E | FR-162 |

### 8.14 TC-PI

| TC ID | SEC-T | Covers |
|---|---|---|
| TC-PI-130 | SEC-T-30 corpus PI-01…PI-20 (SAC-04) | SEC-301, SEC-311 |
| TC-PI-131 | SEC-T-31 text never authority (incl. non-operator comments, labels, CI logs) | FR-203, SEC-302, SEC-313, SEC-316 |
| TC-PI-132 | SEC-T-32 schema fuzz | SEC-303 |
| TC-PI-133 | SEC-T-33 scope widening | SEC-305 |
| TC-PI-134 | SEC-T-34 plan change / replayed approval | SEC-306 |
| TC-PI-135 | SEC-T-35 spec change during each phase | SEC-307 |
| TC-PI-136 | SEC-T-36 head moves | SEC-308 |
| TC-PI-137 | SEC-T-37 pre-check classes | SEC-309 |
| TC-PI-138 | SEC-T-38 policy gate block vs escalate; ack bound to head (SAC-16) | FR-124, FR-167, SEC-310, SEC-702 |
| TC-PI-139 | SEC-T-39 Unicode fixtures | SEC-312 |

### 8.15 TC-PERF

| TC ID | Test | Env | Pass criterion | Covers |
|---|---|---|---|---|
| TC-PERF-001 | 24 h idle soak | T4 | ≤ 250 MB RSS; ≤ 2 % CPU | NFR-080 |
| TC-PERF-002 | Detection latency Linear/GitHub (per §1.5 rule) | T3 | NFR-040, NFR-041 bounds | NFR-040, NFR-041 |
| TC-PERF-003 | Authorization → planning and approval → implementation start | T2/T3 | p95 ≤ 30 s, max ≤ 120 s | NFR-042, NFR-045 |
| TC-PERF-004 | SQLite commit latency with fullfsync under load | T4 | p99 ≤ 50 ms | NFR-050, NFR-085 |
| TC-PERF-005 | Disk thresholds and worktree caps | T1 | Hold/interrupt at `disk.*`; 1 notification | NFR-082, OPS-011 |
| TC-PERF-006 | Event-loop lag during Codex + test run, backup and `integrity_check` | T4 | p99 lag ≤ 250 ms; 0 false sleep gaps | NFR-052, NFR-085 |
| TC-PERF-007 | Metric computation per measurement rule against a scripted `host_events` fixture | T0 | Equals oracle | NFR-004, NFR-008 |

### 8.16 TC-OPS

| TC ID | Test | Env | Pass criterion | Covers |
|---|---|---|---|---|
| TC-OPS-001 | Install/upgrade/uninstall on a clean account (operator level) | T4 | Each succeeds; paths outside TCC | CON-002, NFR-070, NFR-092, SEC-405 |
| TC-OPS-002 | `doctor`/`status` content and latency | T1 | ≤ 2 s; fields present | NFR-071, OPS-012 |
| TC-OPS-003 | Invalid configuration refuse-start | T1 | 10/10 | NFR-072 |
| TC-OPS-004 | Runbook walkthrough per alert, block reason and incident (incl. rotation, ruleset emergency) | Demo | Every class has a working runbook | NFR-073, OPS-010, SEC-504 |
| TC-OPS-005 | Governance report: mode and acceptance per repo | T3 | Reported per repo | CON-014, OPS-003, OPS-017 |
| TC-OPS-006 | Restore drill | T4 | ≤ 15 min operator time | NFR-022, OPS-006 |
| TC-OPS-007 | Agent CLI / Node upgrade gated by contract tests, rollback | T4 | Bad version blocked; rollback works | NFR-093, NFR-094, OPS-005 |
| TC-OPS-008 | Retention: rotation and raw-output lifetime | T1 | Only expired items removed; no raw output after finalization; deletion audited | NFR-061, OPS-011, SEC-505 |
| TC-OPS-009 | Secret scan of docs and repos; test-target allow-list guard | CI | 0 findings; non-sandbox target fails CI | CON-010, OPS-004, SEC-706 |
| TC-OPS-010 | ID, pointer and parameter lint (registry, aliases, no restated parameter values, no undefined IDs) | CI | 0 violations | CON-001, CON-015, CON-017 |
| TC-OPS-011 | Watchdog: daemon stopped vs Mac sleeping (final `sleeping` heartbeat) | T3 + T4 | Alert vs no alert | OPS-013 |
| TC-OPS-012 | **[ROOT]** System install of agent uid, wrappers, sudoers, helpers: idempotent; `doctor` detects each deliberate misconfiguration; unsigned helper refused | T4 | 100 % detected | NFR-070, OPS-014, OPS-018 |
| TC-OPS-013 | `doctor` scans the agent `HOME` for credential files; toolchain write attempt | T4 | Planted file flagged | NFR-071, OPS-015 |
| TC-OPS-016 | `mercury repo check` (onboarding: ruleset, CODEOWNERS, `allow_auto_merge=false`, pinned checks, CI on drafts, toolchain manifest) | T3 / target read-only | Pass on sandbox and `network_monitor` | FR-145, OPS-016, SEC-100 |

### 8.17 TC-PIL

| TC ID | Test | Env | Pass criterion | Covers |
|---|---|---|---|---|
| TC-PIL-001 | Shadow (MIG-1) | T5 read-only | §7.3 | OPS-008 |
| TC-PIL-002 | Supervised pilot (MIG-2) | T5 | §7.3 | FR-300, NFR-004, OPS-008 |
| TC-PIL-003 | Cutover and Slack decommission (MIG-3/4) | T5 | §7.3 | FR-301, OPS-009, SEC-806 |
| TC-PIL-004 | Stall metric during pilot | T5 | Max undetected stall ≤ timeout + 2 polls | NFR-003 |

### 8.18 Retired test IDs

| Retired | Replacement | Reason |
|---|---|---|
| TC-P0-001…015 (Phase 2) | 001 → P0-001/002/006; 002 → P0-025/033; 003 → P0-035; 004 → P0-042; 005 → P0-016; 006 → P0-037; 007 → P0-034; 008 → P0-012/013; 009 → P0-060; 010 → P0-220; 011 → P0-021; 012 → P0-017 + TC-SEC-123; 013 → P0-209; 014 → P0-038; 015 → P0-073 | Unified P0 register (RD-10; old numbers collided with D's) |
| TC-SEC-001, -002, -005, -007 | TC-SEC-103, -121, -120, -122 | Superseded by E's SEC-T tests |
| TC-PI-001…005 | TC-PI-130…136 | Corpus owned by E |
| TC-GOV-001…003, -007 | TC-GOV-116 (cases a–c), TC-PI-138 | Merged into SEC-T-16 and the policy gate |
| TC-SBX-007 | TC-GOV-115 | Drift test is SEC-T-15 |

---

## 9. Evidence and reporting

| Evidence | Where | Retention |
|---|---|---|
| CI reports (JUnit, coverage, both clock modes, seeds) | MERCURY repo CI artifacts | ≥ 90 days; milestone-exit runs kept permanently and linked from the RTM |
| Failing property and crash seeds | Regression fixture directory | Permanent |
| Sandbox, real-Mac and T4v runs | `docs/mercury/testing/evidence/<milestone>/<TC>-<date>.md`: versions (macOS, Node, Claude, Codex, coordinator SHA, wrapper and helper hashes), steps, observations, result | Permanent (redaction canary checked) |
| Phase 0 results | `reviews/phase0-mac-facts.md` (D) and `docs/mercury/testing/evidence/P0/phase0-report.md` (F closure view) | Permanent |
| Gate records (G-S1…G-S5) | Audit event `gate.recorded` + evidence file listing every SAC and its TCs | Permanent |
| Pilot metrics | `mercury audit --report pilot` (measurement rule, traceability §1.5) | Permanent |

---

## 10. Contributions still required

| Item | Contributor | Expected |
|---|---|---|
| Transition-table oracle mapping and crash-point registry list | C | TC-SM rows per transition; `components.md` §8.7 |
| Scenario schema, golden fixtures, mutants, wire copies | C, B | Per schema in `protocols/schemas/` |
| Recorded agent and API fixtures per pinned version | B | Recording procedure (TC-CON-003…008) |
| Procedures for P0-060…074 | E (governance P0-067, P0-068, P0-072), operator (P0-060, P0-073, P0-074) | Steps and evidence capture |
| Real-Mac and T4v procedures | D | `operations/recovery.md` §6 for TC-REC-003…021, -030…039 |
| PI corpus ≥ 60 variants by M9b | E | Inside TC-PI-130 |
