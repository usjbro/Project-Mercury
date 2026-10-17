# 27 — Mercury TDD Compatibility Review and Amendment Proposal

Status: **Proposed** (Architecture Amendment 001, 2026-10-17). Review of the Mercury TDD v1.0-rc1, its owner documents and ADR-001…020 against the devplat platform (docs 15–26, ADR-022…030). **Awaiting operator approval**; no TDD file is changed by this document (CLAUDE.md: design documents change only through an operator-approved amendment).
Reuses / supersedes: **extends** `12-amendments.md` §4 ("Proposed TDD change summary"), which proposed one cross-reference in TDD §27. That cross-reference stays and is widened (W-1). Nothing in the TDD, its owner documents or ADR-001…020 is superseded.

## 1. Result in one paragraph

**Mercury's production architecture is unchanged.** Kubernetes is a property of the platform that *builds* Mercury, not of Mercury. Every production decision — the local `mercuryd` LaunchAgent on the operator's Mac (ADR-010, CON-002), SQLite (ADR-002), `_mercuryagent` + Seatbelt + root-owned wrappers (ADR-013), Claude and Codex invocation (ADR-004/005, CON-016), Keychain credentials, recovery and adoption (ADR-020), deployment and upgrade (TDD §24) — is class **(3) no change**. What changes is **where and how Mercury's own development and tests run** (class **(1)**): Linux-portable test tiers T0, T2 and the Linux part of T1 may run as devplat Kubernetes test Jobs; T1-macOS stays on GitHub-hosted macOS runners; T3 may run in a dedicated devplat sandbox namespace if the operator allows sandbox credentials there; T4, T4v and T5 stay on Apple hardware as the **external macOS lane**. Five TDD/owner-document passages need **wording** amendments (§5). Four production changes are listed **as options only** (§4); none is proposed, and each would need its own ADR.

Classes: **(1)** development-platform change only · **(2)** proposed Mercury production change · **(3)** no change.
Count over 34 items: 16 have a class-(1) development-platform aspect (11 of them are "3 for production, 1 for development, tests or co-hosting"; 5 are development-only); 18 are class (3) only; **0 are class (2)**; 4 production options are listed but not proposed.

## 2. What was reviewed

TDD §1–§32; `architecture/overview.md` (AP-11), `components.md` §1–§2, `state-machine.md`; `operations/macos-service.md` §1, §3, §9, §10, §13, §15; `operations/recovery.md`; `security/threat-model.md` (SEC-201, SEC-310, §8.10 gates); `testing/verification-plan.md` §2–§3; `planning/traceability.md` CON-001…018; `planning/roadmap.md`, `issue-breakdown.md`; `integrations/github.md` §9, `claude.md`, `codex.md`; ADR-001…020; development package docs 00–16, 28–29.

## 3. Impact register

### 3.1 Summary

| ID | Area | Existing design (owner) | Class | Change |
|---|---|---|---|---|
| I-01 | Coordinator runtime | ADR-001; components §1 | 3 | None. devplat builds a Node 24 toolchain image; needs the exact pin ADR-001 already requires |
| I-02 | Durable store | ADR-002; TDD §16 | 3 (prod) / 1 (tests) | Mercury keeps SQLite. devplat's **own** task state is PostgreSQL (ADR-026). Mercury SQLite tests in Linux Jobs prove logic only |
| I-03 | Agent communication | ADR-003 | 3 | None; devplat mirrors hub-and-spoke |
| I-04 | Claude execution | ADR-004; integrations/claude.md | 3 (prod) / 1 (dev) | Production unchanged. Development agents are Claude Code in Jobs behind a model gateway |
| I-05 | Codex execution | ADR-005; CON-016 | 3 | None. devplat never runs real Codex; Kubernetes tests use FakeCodex |
| I-06 | Git and PR ownership | ADR-006 | 3 (prod) / 1 (dev) | Production unchanged; devplat gitbroker applies the same principle to `dev/*` |
| I-07 | Polling | ADR-007; CON-002 | 3 | None |
| I-08 | Identities | ADR-008; CON-008 | 3 (prod) / 1 (dev) | Production unchanged. Development bot App (DOD-13) separate from `mercury-bot` (S1–S2) |
| I-09 | Sandbox credentials for T3 | verification-plan §2.3; ADR-008 | 1 | Optional: T3 in a devplat sandbox namespace with sandbox-only App keys as Kubernetes Secrets (operator decision) |
| I-10 | System of record | ADR-009 | 3 | None |
| I-11 | macOS service (launchd) | ADR-010; macos-service §4–§6 | 3 | None. Kubernetes is not imposed on Mercury |
| I-12 | Local process supervision | ADR-010 item 3–4; ADR-020; macos-service §3.8 | 3 | None |
| I-13 | Authority records | ADR-011, ADR-018 | 3 | None |
| I-14 | Migration from Slack | ADR-012 | 3 | None |
| I-15 | Agent sandboxing | ADR-013 (`_mercuryagent`, Seatbelt, sudoers wrappers); SEC-201; CON-018 | 3 (prod) / 1 (tests) | Production unchanged. SEC-T-20 and every uid/Seatbelt test stay on the real Mac (T4). Pod isolation is a development control only |
| I-16 | Merge governance, required checks | ADR-014; github.md §9; roadmap P0d | 3 | None. P0d "govern MERCURY's own repository like a target" and RA-D2's time-boxed exception unchanged |
| I-17 | Task condition model | ADR-015 | 3 | None |
| I-18 | Filesystem layout | ADR-016; macos-service §7 | 3 | None. Linux test Jobs need the paths module's test seam (already required by D5 / ADR-016 item 3) |
| I-19 | Claude review snapshots | ADR-017 | 3 | None |
| I-20 | Notifications, presence | ADR-019; CON-011 | 3 (prod) / 1 (dev) | Production unchanged. devplat's dashboard serves development only; no Mercury notification goes through devplat |
| I-21 | Recovery, adoption | ADR-020; recovery.md; TDD §20 | 3 (prod) / 1 (tests) | Production unchanged. Crash-injection suites (L9 T1/T2) may run in Jobs; real-Mac and power-loss recovery stay T4/T4v |
| I-22 | Credential management | macos-service §9 (Keychain); CON-010 | 3 (prod) / 1 (dev) | Production unchanged. Development keys live only in gitbroker / model-gateway Secrets |
| I-23 | Deployment and upgrade | TDD §24; macos-service §13–§14 | 3 | None. devplat never deploys Mercury (project config: production target `automated: false`) |
| I-24 | Mercury CI/CD | TDD §24; macos-service §1, §15.1 ("GitHub-hosted runners only. No self-hosted runner") | 1 | devplat test Jobs are **not** GitHub Actions runners. No self-hosted runner is introduced (would contradict §15.1 on a public repository) |
| I-25 | Testing infrastructure | verification-plan §2.1, §2.5, §3; TDD §22 | 1 | T0/T2 and Linux T1 may also run as devplat Jobs; wording amendment W-3 |
| I-26 | Resource management | TDD §23; macos-service §10; OD-07 | 3 (prod) / 1 (dev) | Production concurrency and admission unchanged. Development capacity moves from one host to quotas (docs 17, 25) |
| I-27 | Roadmap and issues | TDD §27–§28; roadmap; issue-breakdown | 1 | Execution vehicle of MERC tasks changes; no MERC scope or acceptance changes (§6) |
| I-28 | Local-first principle | CON-002; AP-11 ("no container runtime") | 3 (prod) / 1 (co-hosting) | Production unchanged. Recommendation: do not co-host devplat workstation mode with a running production `mercuryd` on the same Mac |
| I-29 | Codex locality | CON-016 | 3 | None: no Codex run on devplat |
| I-30 | Self-hosting | `11-…`; `15-…` §8 rule 4 | 1 | Self-hosting never makes devplat depend on Mercury |
| I-31 | Non-goals | TDD §3 ("no cloud-hosted coordinator in v1"; "no new dashboard") | 3 | None: devplat is not a Mercury coordinator and its dashboard is not a Mercury channel |
| I-32 | Threat model | threat-model §3–§9; RISK-27, RISK-28 | 3 (prod) / 1 (dev) | Production unchanged. devplat's own threat model is doc 18 |
| I-33 | Requirements and traceability | traceability CON/FR/NFR/OPS | 3 | No requirement text changes; W-3 adds an environment note only |
| I-34 | Design approval gate | CON-001; TDD §32.3 | 3 | None: devplat runs no Mercury implementation before DOD-01, exactly as v1 |

### 3.2 Detail for every item that is not a plain "no change"

Fields: **E** existing design · **P** proposed change · **R** reason · **C** compatibility · **M** migration · **S** security implications · **B** benefits · **N** new risks.

**I-02 SQLite (ADR-002) — class 3 for production, 1 for tests.**
- E: one SQLite DB in WAL, `synchronous=FULL`, `fullfsync=ON`, single writer; T4v proves durability (ADR-002; verification-plan §2.1 T4v).
- P: unchanged. devplat's *development* state (task events, gates) lives in PostgreSQL (ADR-026); that is devplat's store, not Mercury's. Mercury's SQLite unit and trigger tests may run in Linux test Jobs.
- R: Linux containers execute SQLite logic identically; they cannot prove `F_FULLFSYNC` (macOS-only) or APFS durability.
- C: full. The verification plan already says "the Linux fault-injecting filesystem stays for SQLite logic only (ASM-F-09); durability evidence comes from T4v".
- M: none.
- S: none for production. A Linux result must never be recorded as evidence for an NFR verified at T4/T4v (verification-plan rule "passing against fakes never verifies…").
- B: faster parallel test feedback. N: a Linux-only pass hides a macOS-only defect → mitigated by T1-mac on GitHub-hosted runners and L4's "100 % pass on macOS runner" exit, which stays.

**I-04 Claude execution (ADR-004) — class 3 / 1.**
- E: Claude decision runs via the Agent SDK spawned as `_mercuryagent` through `agent-exec`, key on fd 3, `settingSources: []`.
- P: production unchanged. Development specialists run as Claude Code headless in Jobs; the model key stays in `devplat-model-gateway`.
- R/C: separation rule S3 already keeps production from reading `.claude/agents/mdev-*`. Contract recording of the pinned SDK (TC-CON-003/004/005/014) needs G-S1 and real binaries under the agent uid → stays on the macOS lane.
- M: none. S: devplat's gateway key is a development key, never Mercury's Anthropic key (OD-03). B: development agents never see a key. N: gateway compromise (doc 18).

**I-06 Git and PR (ADR-006) / I-08 identities (ADR-008) — class 3 / 1.**
- E: only `mercuryd` commits and pushes, as `mercury-bot`; operator credentials never used (CON-008).
- P: production unchanged. devplat-gitbroker is the only development component holding a GitHub key (the dev bot App, DOD-13), pushes only `dev/*`, opens drafts only.
- C: `dev/*` never collides with production `mercury/*` (`06-…` §2). M: none. S: S1–S2 forbid reusing `mercury-bot`. B: closes R5 S-01 for development. N: none for production.

**I-09 T3 sandbox credentials — class 1, operator decision.**
- E: T3 runs on "Operator's Mac or a dev machine with sandbox credentials" (verification-plan §2.1); sandbox Apps have installation ids separate from production (§2.3).
- P: optionally run T3 suites in a dedicated `proj-mercury-t-<runid>` sandbox test class whose namespace alone mounts the sandbox App keys and the `MSB` Linear app credential as Kubernetes Secrets, with egress only to GitHub and Linear.
- R: parallel, repeatable sandbox runs without the operator's Mac. C: a cluster node is a "dev machine" in the plan's wording; the allow-list guard (TC-OPS-009) still applies.
- M: the operator creates the sandbox credentials (P0c, OD-13) and decides whether they may leave the Mac.
- S: **new credential location.** Sandbox keys can write only to the sandbox repo and team, but a compromised test namespace could abuse them there. Production keys never go to devplat.
- B: T3 independent of the Mac. N: secret sprawl → names only in config, holder `test-namespace`, short-lived installation tokens.

**I-15 Agent sandboxing (ADR-013) — class 3 / 1.**
- E: every model-directed or repository-derived process runs as `_mercuryagent` through root-owned `agent-exec`/`agent-ctl` with a sudoers drop-in; Seatbelt as second layer; CON-018 / SEC-T-20 gate on the real Mac.
- P: unchanged. Kubernetes pod isolation (gVisor, no SA token, default-deny egress) protects the **development** platform from the code agents write; it is not a substitute for, and never counts as evidence of, SEC-201.
- R: Seatbelt, macOS uids, sudoers and the login Keychain do not exist in Linux pods. C: FakeBroker (same argv grammar) runs in Linux T1; the real wrappers' grammar tests stay `test-wrappers` on `macos-15`.
- M: none. S: no weakening; CON-018 unchanged. B: devplat's agents developing `packaging/agent/**` cannot reach the operator's Mac at all. N: **Unverified assumption** that `agent-exec`'s grammar tests are portable to Linux; if not, they stay macOS-only.

**I-18 Filesystem layout (ADR-016) — class 3.** Tests running in Linux must not hard-code `/Users/Shared/MercuryWork`; ADR-016 item 3 and rule D5 already require a single paths module, so a test root is injectable. No change.

**I-20 Notifications (ADR-019, CON-011) — class 3 / 1.** devplat has an operator dashboard and API (doc 15). CON-011 and ADR-019 bind MERCURY ("no new dashboard"); devplat's dashboard is a development tool. Rule: no production Mercury event is ever routed through devplat.

**I-21 Recovery (ADR-020) — class 3 / 1.**
- E: adoption by identity triple, supervisor lease, `lost_by_host`, 20-step startup recovery; L9 crash injection T1/T2, real-Mac T4, power loss T4v.
- P: unchanged. Crash-injection suites (MERC-801) may run in parallel Jobs (seeded, reproducible). MERC-802 (VM rig) and MERC-803 (real-Mac recovery) stay on the macOS lanes.
- B: 1,000-run crash suites in parallel. N: none for production.

**I-22 Credentials (Keychain) — class 3 / 1.** Keychain items `com.usjbro.mercury.*`, read once (macos-service §9). Unchanged. Development keys: Kubernetes Secrets mounted only by gitbroker / model-gateway (doc 18). The temporary-keychain round-trip test stays `test-macos`.

**I-24 Mercury CI/CD — class 1.**
- E: TDD §24 "GitHub Actions on `project-mercury` … no self-hosted runner on public repos"; macos-service §1 and §15.1 "GitHub-hosted runners only. No self-hosted runner".
- P: devplat's G2 re-run and integration tests are **devplat Jobs**, reported as development evidence, not as GitHub check runs from a self-hosted runner. Required CI on `main` stays GitHub-hosted (MERC-030). devplat must not register Actions Runner Controller (ARC) runners for this repository.
- R: a self-hosted runner on a public repository lets fork PRs execute on the cluster (the reason for §15.1). C: full. M: none. S: keeps the public-repo rule. B: no new CI trust path. N: two test executions (devplat + GitHub CI) can disagree → G6 already requires CI green at the tested head.

**I-25 Testing infrastructure — class 1 (wording W-3).**
- E: verification-plan §2.1 "Runs where": T0 "CI (Linux and macOS runners)", T1 "CI (macOS runner preferred)", T2 "CI", T3 "Operator's Mac or a dev machine", T4 "Operator's Mac only", T4v Apple Silicon host.
- P: T0, T2 and the Linux part of T1 may additionally run as devplat test Jobs in ephemeral namespaces with no credentials and no egress; T3 per I-09; T4/T4v/T5 unchanged and scheduled as `mac_validation` / `operator_action` tasks with operator evidence (project config `macos-lane`, `macos-vm-lane`).
- C: exit criteria unchanged; in particular L4 "100 % pass on macOS runner" still needs the macOS runner. M: W-3 wording. S: none. B: parallelism, independence from the operator's Mac for T0–T2. N: none beyond I-02.

**I-26 Resources — class 3 / 1.** OD-07 concurrency (Codex 1, Claude 2, 1/repo) and the admission check are production parameters, unchanged. The development constraint "MacBook Air M2 16 GB" (`09-…`) applies only to workstation mode (doc 15 §7).

**I-27 Roadmap and issues — class 1.** See §6.

**I-28 Co-hosting — class 1 recommendation.** CON-002 forbids a MERCURY listener off loopback; devplat-api has an authenticated ingress. If devplat runs in workstation mode (kind/k3d) on the same Mac on which production `mercuryd` later runs (M9b+), a second privileged system shares the host with MERCURY's Zone C, widening RISK-27. Recommendation: from M9b on, devplat does not run on the production Mac; before that, workstation mode is acceptable (no production MERCURY exists).

**I-30 Self-hosting — class 1.** `11-…` Stages A–E stay; `15-…` §8 rule 4 adds that Mercury building itself never makes devplat depend on Mercury.

**I-32 Threat model — class 3 / 1.** No SEC requirement changes. RISK-28 (operator's interactive agents can approve as the human) is about the operator's own sessions; devplat agents hold no human credential, so the development side of RISK-28 shrinks once DOD-13 is in place.

## 4. Production changes listed as options only (not proposed)

Each would need its own ADR, Security review and operator approval. None is recommended now.

| Option | Would change | Conflicts with | Possible benefit | Why not now |
|---|---|---|---|---|
| P-1 Run `mercuryd` in a Linux container / Kubernetes | ADR-010, ADR-013, ADR-016, macos-service, TDD §18, §24 | CON-002 (local on the Mac, no inbound), CON-009 sleep model, Keychain, presence helper (ADR-019), AP-11 ("no container runtime") | Multi-host, no sudoers root steps | Contradicts the problem statement (coordination on the operator's Mac); no requirement asks for it |
| P-2 PostgreSQL as Mercury's store | ADR-002, components §6 DDL and triggers | AP-11, single-writer `flock` model, backup/restore epochs | Concurrent readers, managed backups | SQLite meets every NFR on paper; adds a service to a one-user host |
| P-3 Pod-based agent isolation instead of `_mercuryagent` | ADR-013, SEC-201, CON-018, macos-service §3 | Requires P-1 | Removes root steps on the Mac | Depends on P-1 |
| P-4 macOS lane inside the cluster (macOS VMs) | verification-plan T4/T4v | Apple licensing and virtualization limits; GitHub-hosted runners lack nested virtualization (RD-24) | Automate T4 partly | Not available on Kubernetes; T4v already has a dedicated rig |

## 5. TDD and owner-document passages that need wording amendments

The TDD contains **no explicit statement that Mercury's development runs on the operator's Mac**. The passages below imply a single-host development model or would be misread once devplat exists. All are editorial (class 1) and need the operator's approval.

| # | Location | Current wording (abridged) | Proposed wording |
|---|---|---|---|
| W-1 | TDD §27 (Implementation Roadmap) | — (no reference to how implementation is executed) | Add: "Implementation is executed by the development platform described in `docs/mercury/development-orchestration/` (ADR-021, and for the Kubernetes-native platform ADR-022…030, all proposed). It holds no production authority, does not change this design, and is retired or kept independently of MERCURY per its self-hosting plan." (widens `12-…` §4) |
| W-2 | TDD §22 table, row "Integration (generic) — macOS runner" | "macOS runner, both SQLite drivers" | Unchanged; add a sentence under the table: "Linux-portable levels may also run as development-platform test Jobs; such runs are development evidence and never replace the required CI, sandbox (T3) or real-Mac (T4) evidence." |
| W-3 | verification-plan §2.1 "Runs where" (T0, T1, T2, T3) and §2.5 | T0 "CI (Linux and macOS runners)"; T1 "CI (macOS runner preferred)"; T2 "CI"; T3 "Operator's Mac or a dev machine with sandbox credentials" | T0/T2: "CI; optionally devplat test Jobs (Linux)". T1: "CI (macOS runner preferred; the L4 exit requires it); the Linux part optionally in devplat test Jobs". T3: "Operator's Mac, a dev machine, or a devplat sandbox test namespace, with sandbox credentials only (operator decision, `27-…` I-09)" |
| W-4 | macos-service §15.1 | "GitHub-hosted runners only (public repo …)" | Add: "The development platform's test Jobs are not GitHub Actions runners; no self-hosted runner is registered for this repository." |
| W-5 | roadmap §5 / ASM-F-10 ("one operator-engineer with agent assistance", "≈ 1.5 focused engineer-days per workday") | as is | Add a pointer: "Agent execution capacity and its effect on the schedule: `development-orchestration/05-…`, `28-roadmap-k8s.md`." No estimate changes |

Not amended: TDD §1 ("on the operator's Mac"), §3 non-goals, §18, §24 deployment — they describe production and remain correct.

## 6. Planning and issue impacts

| Item | Impact | Change |
|---|---|---|
| P0a–P0c (MERC-001…005, 010…012, 020…024) | Mac and identity work by the operator | **None.** Scheduled on devplat as `mac_validation` / `operator_action` tasks with operator evidence (same as v1) |
| P0d MERC-030 (CI with macOS runner, lint, secret scan, ruleset, CODEOWNERS) | Governance of Mercury's own repository | **Scope and acceptance unchanged.** GitHub-hosted CI only (I-24). RA-D2's time-boxed exception unchanged. On devplat, `.github/**` is restricted for agents until the operator answers Q-M3 (`26-…` §2.3) |
| MERC-031 (RA-D1, development orchestration verification) | Verified v1 local mode | Kept for local mode; its devplat counterpart is the DP4 acceptance (`28-…`, `29-…`) |
| M1–M7 implementation issues (MERC-101…) | Built by specialists | **No scope change.** Execution vehicle changes from local subagents to Jobs once devplat reaches DP4, unless DOD-16 allows v1 local mode earlier |
| MERC-112 (fakes), MERC-113 (PROP suite, crash harness v1), MERC-801 (crash injection at scale) | Linux-portable | May use devplat test Jobs for parallel seeds; acceptance unchanged |
| MERC-802 (power-loss VM rig), MERC-803 (real-Mac recovery), MERC-805 (security suite on the Mac) | Apple hardware | **None**; external lanes |
| M8–M9 (MERC-806…906) | Pilot and cutover on the Mac | **None**. I-28 co-hosting recommendation applies from M9b |
| Operator decisions OD-01…37 | Production | **None** added or changed |
| Development decisions | — | DOD-11…16 (`12-…`), Q-M1…Q-M11 (`26-…`) |

## 7. Capability status

| Capability | Status |
|---|---|
| This compatibility review | Documented only (inspection; no test can prove a negative impact) |
| W-1…W-5 wording amendments | Awaiting operator approval |
| Classification "production unchanged" | Documented only; holds as long as no option P-1…P-4 is adopted |
| T0/T2 in devplat Jobs | Documented only (no Mercury code or image exists) |
| T3 in a devplat sandbox namespace | Awaiting operator approval (I-09) |
| macOS lane as `mac_validation` tasks | Documented only (v1 has it as a tested short lifecycle in `devorch.py`) |

## 8. Open questions and inconsistencies found

1. I-09: may sandbox App keys and the `MSB` Linear credential leave the Mac (into a devplat Secret)?
2. I-15: are the `agent-exec`/`agent-ctl` grammar tests portable to Linux, or macOS-only? (Unverified assumption.)
3. I-28: confirm that devplat will not run on the production Mac from M9b.
4. The TDD and owner docs name the repository `usjbro/project-mercury`; the remote is `usjbro/Project-Mercury` (case only).
5. TDD §24 says "no self-hosted runner on public repos" while macos-service §15.1 says "GitHub-hosted runners only … self-hosted runners only for private repos": consistent, but if the repository becomes private (G-ORG move) the rule should be re-decided explicitly rather than lapse.
