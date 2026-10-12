# Phase 4 Revision — Agent E (Application Security Architect): Dispositions

| Field | Value |
|---|---|
| Owner | Agent E |
| Date | 2026-10-12 |
| Documents changed | `security/threat-model.md` (full revision). No other file was edited. |
| Binding input | `reviews/30-reconciliation.md` RD-1…RD-20 |

---

## 1. Summary of changes per document

### `security/threat-model.md`

- **Header and conventions.** Phase 4 status; single-source rules (SEC text here, IDs registered by F, parameter values only in D's table, layout only in `macos-service.md` §7.1, DDL only in `components.md`, schemas only in `protocols/`). Numbers that were configuration values (deadlines, rlimits, mutation budgets, retention, Unicode thresholds, disk floors) are replaced by parameter names; only security **bounds** remain as requirements (drift detection ≤ 60 min awake, merge verification ≤ 5 min awake).
- **§0 Summary** rewritten for the reconciled design: two required MERCURY check runs, COMMENT-only reviews, G-ORG before unattended operation, three zones with H and C sharing the operator uid, agent-class processes as `_mercuryagent`, the corrected secret-scan statement (RE-24), N1 interactive agents, and the new consequence of RD-1 that coordinator compromise reaches human credentials.
- **§1 Assets.** Split App assets into `mercury-bot` and `mercury-ops`; added the root-owned TCB (A-17), the control socket (A-18) and private findings (A-20).
- **§2 Actors and principals.** Added `verify`, `deps_install`, the wrappers, and operator-uid non-human processes (AC-09). New principal table: `operator-presence`, `operator`, `claude_session`. Adversary model updated (compromised coordinator now only partially contained).
- **§3 Trust boundaries.** New three-zone Mermaid diagram (Zone H and Zone C inside one operator-uid box, Zone A as `_mercuryagent`, root-owned TCB, egress to registries). New boundaries B13 (control socket), B14 (sudo/`agent-exec`), B15 (run files), B16 (registry egress). Data-flow narrative updated to snapshots, policy gate, mirror push, draft PRs, check runs, disclosure policy.
- **§4 Threats.** Updated TH-03, TH-09, TH-23, TH-29, TH-30, TH-40, TH-50, TH-61, TH-70. New TH-13 (CI logs), TH-31 (`verify`), TH-32 (push redirection, N2), TH-33 (control socket, N3), TH-34 (run-file forgery), TH-35 (wrapper abuse), TH-36 (cross-run interference), TH-37 (unsupervised runs), TH-38 (hostile worktree files opened by a human), TH-39 (model key via env), TH-51 (public ops issue), TH-52 (mentions/magic words), TH-53 (update-branch/auto-merge), TH-54 (N1), TH-55 (disclosure), TH-65 (foreign PR), TH-75 (fake restore), TH-84/85 (TCB and toolchain tampering).
- **§5.1 Requirements.** Changed (▲): SEC-100, 101, 102, 105, 106, 108, 109, 110, 111, 201, 202, 203, 204, 205, 206, 207, 208, 209, 210, 211, 303, 304, 305, 307, 308, 309, 310, 311, 313, 314, 315, 401, 402, 403, 405, 406, 501, 502, 503, 505, 601, 602, **603 → SHOULD**, **604 MUST with anchoring carriers**, 605, 606, 701, 702, 703, 704, 705, 801, 803, 805, 901, 902, 903, 904, 905. New (★): SEC-113 required check runs, SEC-114 draft-until-pass, SEC-115 presence tier, SEC-212 wrapper contract, SEC-213 cross-run isolation, SEC-214 supervised lifetime, SEC-215 L2/deps profiles, SEC-316 revision provenance, SEC-407 push from mirror, SEC-507 publication policy, SEC-607 restore epochs, SEC-708 toolchains, SEC-906 `security_halt` scoping, SEC-907 ops-channel hardening, SEC-908 fail-closed startup.
- **§5.2 Proof.** Layer stack rebuilt (L1 = agent uid, L1b = presence tier, L3b = policy check). Path-by-path proof re-run against the reconciled design, including the three new paths from my review: N1 (interactive agents, open by policy), N2 (push redirection, blocked), N3 (control-socket principal, blocked). Single-control-failure table corrected: SEC-201 failure plus any publish path breaks H; added rows for check forgery, Seatbelt, wrapper bypass, presence bypass and coordinator compromise.
- **§6 Permission matrix.** Three tables: OS principals (operator, operator-uid processes, `mercuryd`, wrappers, each `_mercuryagent` run kind), control-socket principals (`operator-presence` / `operator` / `claude_session`), SaaS identities (`mercury-bot`, `mercury-ops`, deploy key, Linear app, model keys, operator).
- **§7 Prompt injection.** Context table adds revision-request runs and security review on every PR; no Codex narrative; pre-check pseudo-code now block vs escalate with presence-bound acknowledgement; corpus extended PI-16…PI-20.
- **§8 Details.** §8.1 now lists security properties only and references §7.1 for the layout; §8.2 agent launch through `agent-exec`; §8.3 git plumbing against the mirror, push from the mirror; §8.4 redaction plus neutraliser; §8.5 anchoring carriers and epochs; new §8.7 L2/deps profile design, §8.8 presence-tier mechanics, §8.9 `security_halt` scoping table, §8.10 security phase gates G-S1…G-S5.
- **§9 Risk register.** RISK-01…34 with R-xx aliases, severity before and residual after reconciliation; new RISK-27 (coordinator compromise reaches Zone H), RISK-28 (N1), RISK-29 (Keychain ACL), RISK-30 (presence bypass), RISK-31 (cross-run), RISK-32 (wrappers), RISK-33 (disclosure), RISK-34 (ops issue).
- **§10.** SAC-01…SAC-20 with gates; SEC-T list with binary pass criteria (SEC-T-03…SEC-T-94); ASM-E-01…24 each with a P0 link.
- **§11.** Reduced to open items per owner after the reconciliation.

---

## 2. Finding dispositions

### 2.1 My own review (RE-*)

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RE-01 | 24 | **Fixed, per RD-1** (D's agent-uid model, not my U2). E part: SEC-201 rewritten; SEC-T-20 extended; gate G-S2. Remaining parts owned by A (ADR-013), D (implementation), B (env tables). Objection recorded in §3 | TM §0, SEC-201/202/212, §5.2, §8.10, SEC-T-20 |
| RE-02 | 24 | Fixed (E part: profile design and tests). Implementation: D; B for codex.md §10 | SEC-206, SEC-215, SEC-702/703, §8.7, SEC-T-25/71 |
| RE-03 | 24 | Fixed (E part). C/B/D implement plumbing and mirror push | SEC-401/402/407, §8.3, TH-32, SEC-T-40/41/44 |
| RE-04 | 24 | Fixed per RD-12 (method tier list delivered) | SEC-115, §2 principals, §6.2, §8.8, SEC-T-45 |
| RE-05 | 24 | Fixed per RD-5: `MERCURY / policy`, block vs escalate lists, `"escalate"` semantics | SEC-113, SEC-305, SEC-310, §7.5, SEC-T-38 |
| RE-06 | 24 | Fixed per RD-7 | SEC-205, SEC-T-24 |
| RE-07 | 24 | Fixed per RD-11 (E part) | SEC-214, SEC-906, SEC-T-29 |
| RE-08 | 24 | Fixed (policy; OD-E-02); residual RISK-28 | SEC-106, TH-54, §5.2.2 N1 |
| RE-09 | 24 | Fixed per RD-4: SEC-603 SHOULD, SEC-604 MUST with three carriers, epochs, startup verification | SEC-602–607, §8.5 |
| RE-10 | 24 | Fixed per RD-6 (two Apps) | SEC-101, SEC-110, §6.3 |
| RE-11 | 24 | Fixed | SEC-907, TH-51, RISK-34 |
| RE-12 | 24 | Fixed | SEC-304, PI-17, SEC-T-53 |
| RE-13 | 24 | Fixed (layout per RD-2; block-class IDE/env paths; quarantine policy) | SEC-310, TH-38, SEC-106 |
| RE-14 | 24 | Fixed per RD-13 | SEC-307 |
| RE-15 | 24 | Fixed: SEC-102 COMMENT only | SEC-102, SEC-T-11/18 |
| RE-16 | 24 | Fixed (E part: M8, M9 required); B owns the recipe text | SEC-904, SEC-905 |
| RE-17 | 24 | Fixed (E part): drift cadence and coverage, settings, mutation budgets | SEC-105, 108, 112, 705, 906 |
| RE-18 | 24 | Fixed (E part): `allowedTools`, self-test gate, managed settings MUST (OD-19), hash pins, ASM-E-17 | SEC-204, SEC-210 |
| RE-19 | 24 | Fixed per RD-2 (single layout owned by D) | SEC-405, §8.1 |
| RE-20 | 24 | Fixed (E part): SEC-T list with pass criteria, SAC gates, ASM-E with P0 links. F imports | §10 |
| RE-21 | 24 | Fixed | SEC-313, SEC-314, PI-14 |
| RE-22 | 24 | Fixed (E part) | SEC-801, SEC-803, ASM-E-05/11 |
| RE-23 | 24 | Fixed (E part) | SEC-209, 309, 403, 404, 406, 903 |
| RE-24 | 24 | **Fixed (self-correction)** | §0 item 6, SEC-502, §5.2.3, SEC-T-20, ASM-E-16/17 |
| RE-25 | 24 | Fixed per RD-3b/RD-14 | SEC-906, §8.9 |
| RE-26 | 24 | Fixed per RD-10 (SEC-1xx…9xx canonical) | Header |
| RE-27 | 24 | Deferred to C (DDL owner); no TM change required | — |
| RE-28 | 24 | Fixed (E part: fast-forward reset requirement); C/B implement | SEC-407 |
| RE-29 | 24 | Fixed (E part). Under RD-1 agents have no Keychain; residual for operator-uid processes recorded | SEC-503, SEC-215 (`mach-lookup` deny), RISK-29, ASM-E-08 |

### 2.2 Findings from other reviews addressed to E

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RA-02 | 20 | Fixed (E review part): wrapper contract specified as a security requirement | SEC-212, SEC-T-28 |
| RA-03 | 20 | Fixed: layout referenced, not restated | SEC-405, §8.1 |
| RA-04 | 20 | Fixed: COMMENT only | SEC-102 |
| RA-06 | 20 | Fixed: check runs for both gates | SEC-113, §6.3 |
| RA-07 | 20 | Fixed per RD-6 (two Apps; no auditor App; admin-read settings are POL) | SEC-101, SEC-108 |
| RA-08 | 20 | Fixed: per-task `CODEX_HOME` | SEC-203 |
| RA-09 | 20 | Fixed per RD-12 | SEC-115, §8.8 |
| RA-12 | 20 | Fixed: no MCP in v1 | SEC-204 |
| RA-13 | 20 | Fixed per RD-7 | SEC-205 |
| RA-14 | 20 | Fixed: security review on every PR | SEC-314 |
| RA-18 | 20 | Fixed: `integrity_alert` repo hold mandatory for approval/content mismatches | §8.9 |
| RA-19 | 20 | Rejected as stated (HMAC required), per RD-4: SEC-603 is SHOULD | SEC-603 |
| RA-20 | 20 | Fixed: anchor carriers, overdue → ops alert, no halt | SEC-604, §8.5 |
| RB-03 | 21 | Fixed | SEC-102, SEC-T-18 |
| RB-04 | 21 | Fixed (E part: names and semantics) | SEC-113 |
| RB-05 | 21 | Fixed (E part): `statuses:write` conditional on the pinning test | SEC-101, §6.3 |
| RB-06 | 21 | Fixed | SEC-109, SEC-T-12 |
| RB-08 | 21 | Fixed (E part): env and key delivery requirements | SEC-202 |
| RB-16 | 21 | Fixed: rulesets mandated; drift via `metadata:read` | SEC-100, SEC-108 |
| RB-20 | 21 | Fixed: conversation resolution off | SEC-100 |
| RB-24 | 21 | Fixed | SEC-102 |
| RB-25 | 21 | Fixed: TH-61 targets MCP/UI paths | TH-61 |
| RC-03 | 22 | Fixed (E part): escalation semantics and acknowledgement binding; C owns table and transitions | SEC-310, SEC-113 |
| RC-04 | 22 | Fixed per RD-13 | SEC-307 |
| RC-05 | 22 | Fixed | SEC-203 |
| RC-09 | 22 | Fixed per RD-1 (E part) | SEC-201, SEC-212, SEC-213 |
| RC-15 | 22 | Fixed | SEC-607 |
| RC-26 | 22 | Fixed: single source in SM §9; rule retained there | SEC-315 |
| RD-01 | 23 | Fixed (E verifies via SEC-T-20 and gate G-S2) | SEC-201, §8.10 |
| RD-02 | 23 | Fixed | SEC-201, SEC-215, TH-31 |
| RD-06 | 23 | Fixed | SEC-603, SEC-607 |
| RD-08 | 23 | Fixed per RD-6 | SEC-101, §6.3 |
| RD-13 | 23 | Fixed | SEC-203 |
| RD-14 | 23 | Fixed (reference only) | SEC-405 |
| RD-19 | 23 | Fixed: key on fd 3; read once; single prefix | SEC-202, SEC-503 |
| RD-26 | 23 | Fixed (E part) | SEC-708 |
| RD-31 | 23 | Fixed | SEC-906, §8.9 |
| RF-01 | 25 | Fixed per RD-1 (E part) | SEC-201 |
| RF-04 | 25 | Fixed (E part): security bounds kept as requirements; values to D's table | SEC-108, SEC-905 |
| RF-06 | 25 | Fixed | SEC-203 |
| RF-07 | 25 | Fixed | SEC-113 |
| RF-10 | 25 | Fixed per RD-4/RD-6 (`mercury-ops`, not a PAT) | SEC-604 |
| RF-11 | 25 | Fixed: no `administration` at all; admin-read checks POL | SEC-101, SEC-108 |
| RF-13 | 25 | Fixed | SEC-314 |
| RF-14 | 25 | Fixed (reference to SM §9) | SEC-315 |
| RF-16 | 25 | Fixed per RD-13 | SEC-307 |
| RF-17 | 25 | Fixed: raw logs only until finalization, then redacted copy; raw deletion per retention parameter | SEC-505 |
| RF-21 | 25 | Fixed (E part): channel requirements; C owns the matrix | SEC-901 |
| RF-26 | 25 | Fixed: block vs escalate split | SEC-310, §7.5 |
| RF-27 | 25 | Fixed per RD-14 scoping | SEC-906 |
| RF-28 | 25 | Fixed: trailers reference GH §4.2 | SEC-111 |

---

## 3. Objections to reconciliation decisions

**RD-1 (agent uid instead of U2): accepted, with a qualified objection.** I agree that D's model is stronger than my U2 for the in-scope adversary: it keeps MERCURY's own credentials (and so the required `MERCURY / claude-review` check) away from agents, and its setup cost is similar. The threat model now implements it. Three points remain:

1. **Coordinator compromise is no longer contained.** In Phase 2 the proof claimed H "holds even if the coordinator is fully compromised, provided human credentials stay out of reach". Under RD-1, `mercuryd` runs as the operator uid and can read `~/.config/gh` and the `gh` Keychain item. A code-execution bug in the coordinator, which parses untrusted JSON, git objects and diffs, would now give human impersonation. I recorded this as RISK-27 (High before, Medium residual). **Request:** re-evaluate OD-36 (U2 for the coordinator, combined with D's agent uid) **before unattended operation (G-S5)**, rather than leaving it at "not in v1" with no trigger.
2. **Zone H ↔ C is policy only.** Operator-uid processes, including the operator's interactive agents, can read `MERCURY_HOME` and possibly MERCURY's Keychain items (ASM-E-08). The presence tier stops them from *clearing* escalations. It does not stop them from reading the App key and forging check runs. **Condition:** if Phase 0 shows MERCURY's Keychain items must trust `/usr/bin/security`, the signed Keychain helper moves into v1 (RISK-29).
3. **Sudoers grant usable by any operator-uid process.** This is acceptable because the grant is lateral, to a less-privileged uid. It must stay exactly two binaries with no root target, which `doctor` checks (SEC-210).

No other decision is contested. RD-4 (HMAC SHOULD) and RD-12 match my Phase 3 positions.

---

## 4. Remaining open items

| Item | Owner | Note |
|---|---|---|
| Register SEC-113…115, 212–215, 316, 407, 507, 607, 708, 906–908 and all changed levels (SEC-603 SHOULD) in the RTM; SEC-T as TC-SEC aliases; SAC-01…20 as gates G-S1…G-S5; RISK-01…34; ASM-E-01…24 | F | The old SEC-001…099 reservation is retired (RD-10) |
| Assign `P0-nnn` ids to the ASM-E items marked "new" in TM §10.3; reconcile D's `P0-26…P0-32` with F's three-digit scheme | F, D | Two P0 numbering forms exist today |
| Add parameters named in the TM to the parameter table: drift interval (bound ≤ 60 min), supervisor lease, presence validity window, anchor overdue threshold, mutation budgets, raw-log retention, Unicode/line-length thresholds, sandbox-violation thresholds, run-dir retention | D | Proposed defaults: lease 10 min credited; presence validity 120 s; anchor overdue 24 h awake; mutation budgets 60/h/repo per service; raw-log retention 14 d; line length 1,000 chars |
| Implement SEC-215 profiles from TM §8.7 and choose the SEC-206 egress mechanism (pf vs loopback proxy) | D | Phase 0 (ASM-E-06) |
| Presence helper feasibility in a LaunchAgent GUI session (ASM-E-19) | D | If it fails, the TTY-plus-nonce fallback is POL and RISK-30 rises |
| Merge-verification M8/M9 text and endpoint allowlist list | B | TM states the requirement only |
| `policy_escalations`, `security_halt` hold kinds, principal recording, `anchors`/`audit_epochs` DDL | C | |
| RE-27 (`host_events` deletion versus the append-only trigger) | C | No TM change needed |
| OD-36 re-evaluation trigger before unattended operation | Orchestrator, Operator | See §3 |
