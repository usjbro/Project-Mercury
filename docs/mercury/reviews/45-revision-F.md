# Phase 4 Revision — Agent F (Technical Program Manager): Dispositions

| Field | Value |
|---|---|
| Owner | Agent F |
| Date | 2026-10-12 |
| Documents changed | `planning/traceability.md` (full revision), `testing/verification-plan.md` (full revision) |
| Documents created | `planning/roadmap.md`, `planning/issue-breakdown.md` |
| Binding input | `reviews/30-reconciliation.md` RD-1…RD-20, Addenda A, B, C; revisions of A (40), B (41), C (42), D (43), E (44) |

---

## 1. Summary of changes per document

### `planning/traceability.md`
- **ID registry (RD-10).** §1.1 lists every ID family with owner and defining location: CON/FR/NFR/OPS (F); SEC-1xx…9xx (E text, F registration); INV-01…27 (C); PROP-nn and TC-<LEVEL>-nnn (F); SAC-01…20 and G-S1…G-S5 (E); P0-nnn (D 001…049, B 201…241, F 050…079); ASM linked to P0; ADR-001…020 (A); OD-01…37; RISK-01…34 (E) and RISK-41… (F); MERC-nnn; parameters by name.
- **SEC reservation retired.** SEC-001…099 retired with a mapping to E's IDs (§4.2). All 90 SEC IDs of E's Phase 4 revision are registered with priority (MUST → M release-blocking; SEC-603 = S), ADR, TCs, milestone and E's gate (§4.1, §6.2).
- **Alias tables (§8).** A's NFR-LAT/REL/AUD/SEC/NOT/RES/AVL/MNT/COST; D's REL-01…16; C's I1…I20 → INV-01…20 plus C's new INV-21…27; VP I1…I10 → PROP-01…10; C's SMT-01…14, DBT-01…04, CT-01…06, RT-01…12; D's T-REC-01…08; E's SEC-T-nn (→ TC-SEC-1nn, TC-GOV-110…118, TC-PI-130…139); old TC-P0-001…015; milestone and MIG stages; G-1/G-2.
- **Parameter registry (§7).** D's §2 names registered by group with the requirements that cite them; no values. Workflow policy stays with C/OD-08 (Addendum B.4). B's agent-configuration names registered pending D's table entry.
- **Requirements updated for the reconciliation.** New: CON-018 (agent-uid gate), FR-007, FR-008, FR-050…055, FR-066, FR-085, FR-126, FR-145, FR-166…168, FR-224, FR-242, FR-243, FR-262…264, FR-905, NFR-006, NFR-008, NFR-025…027, NFR-045, NFR-053, NFR-063, NFR-084, NFR-085, NFR-095, OPS-013…019. Rewritten: CON-003, CON-005, CON-007, CON-009, CON-014, FR-020, FR-022, FR-024, FR-040, FR-044, FR-046, FR-047, FR-062, FR-100, FR-102, FR-103, FR-120, FR-122…124, FR-140…144, FR-161…164, FR-181…183, FR-200, FR-220, FR-240, FR-241, FR-280…283, NFR-001, NFR-002, NFR-004, NFR-005, NFR-024, NFR-061, OPS-002, OPS-003, OPS-007. NFR-007 retired (→ OPS-013).
- **NFR measurement rule (§1.5)** normative (RD-16/RD-22); every latency NFR is measured from the first awake-and-online instant.
- **Addenda.** `statuses:read` for `mercury-bot`; `mercury-ops` not on targets; drift via a `metadata:read` bot token; anchor carriers exclude public check summaries; alive file `WORK_ROOT/ctl/coordinator.alive`; restore-epoch confirmation is presence-tier; `MERCURY / policy` uses `action_required`; OD-36 promoted to a required decision before unattended operation; OD-37 added; Keychain helper becomes v1 if P0-036 requires it.
- **RTM (§6)** rebuilt against ADR-001…020; status "baseline candidate"; coverage: 18 CON, 107 FR, 47 NFR, 19 OPS, 90 SEC.
- **OD register (§9)** OD-01…OD-37 with aliases, options, defaults (binding where an RD fixed them) and needed-by milestone.
- **Assumption closure (§10.2)** gating ASM-A/B/C/D/E/F rows linked to P0 checks, incl. every ASM-E-01…24 marked "new" by E.
- **DoR/DoD (§12–§13)** updated (DoR fields used by the issue breakdown; R13 parameters by name; D6 COMMENT reviews and MERCURY checks).

### `testing/verification-plan.md`
- Environment strategy with tier T4v (macOS guest VM for power loss; never the operator's Mac; not on hosted runners), real-agent budgets tied to gates, tier readiness criteria.
- Fakes: FakeClock with both monotonic modes (every sleep test runs in both), FakeBroker (wrapper grammar, uid separation, lease), FakeHost (dark wake, boot session), FakePresence; FakeGitHub models check-run pinning.
- Levels L0–L17 with explicit entry and measurable exit criteria.
- PROP-01…25 mapped to INV-01…27 (RC-18/RC-19/RC-40 wording fixed: mutating-run rule, `scope_version`, limit + grants, defined replay).
- Crash/power-loss harness: duplicate-execution definition, `lost_by_host`, git/DB ordering, T4v 50-cycle criterion.
- Milestone gates for P0a…M9c; security gates G-S1…G-S5 with SAC-01…20 evidence TCs; pilot acceptance per OD-16 (shadow 10 working days; supervised ≥ 10 tasks; 30-day watch).
- Catalogue: new TCs from D §4.11 (TC-REC-010…021), RE/RB findings (SEC-T canaries, check-run pinning, presence tier, policy gate, snapshot builder, dark wake, `lost_by_host`, restore epoch, both clock modes, power loss in the VM), C's SMT/DBT/CT/RT, E's SEC-T as TC aliases; retired-ID table.

### `planning/roadmap.md` (new)
Phases P0a–P0d, M1–M8, M9a–c with scope, entry/exit criteria and effort; Mermaid dependency graph with G-S1…G-S5; security-gate placement (SEC-T-20 before non-sandbox write runs; G-ORG and OD-36 before unattended); effort 156 P50 / ≈ 214 planning P90 (+12/22 contingency); phase and issue critical path; calendar ≈ 7 months P50, 9–10 months P90; throughput and cost model (RF-32); delivery risk register RISK-41…56; OD needed-by table.

### `planning/issue-breakdown.md` (new)
13 epics, 80 issues `MERC-001…906` (3 conditional), each with description, blocked-by, requirements, acceptance with TCs, P50/P90 and uncertainty, DoR fields and subtasks; epic Mermaid graph; computed dependency critical path. No Linear issues were created.

---

## 2. Finding dispositions

### 2.1 My review (RF-*)

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RF-01 | 25 | Fixed (F part): CON-018, FR-051, FR-055, OPS-014/015; P0b phase; G-S2 placement; issues MERC-010…012, -107, -406. Design owned by D/A/C (done in their revisions) | TR §3; RM §2, §4; IB E0b/E1 |
| RF-02 | 25 | Fixed: SEC-001…099 retired; 90 E IDs registered | TR §4, §6.2 |
| RF-03 | 25 | Fixed: INV/PROP split; contributor test aliases | TR §8.2–§8.3; VP §4, §5 |
| RF-04 | 25 | Fixed: one NFR per topic; values by parameter name; A/D aliases | TR §3 NFR, §7, §8.1 |
| RF-05 | 25 | Fixed (F part): FR-066; TC-SEC-124; snapshot in M3 | TR FR-066; VP; RM M3 |
| RF-06 | 25 | Fixed (F part): FR-100, TC-INT-026 (per-task `CODEX_HOME`) | TR FR-100 |
| RF-07 | 25 | Fixed (F part): FR-166/167, TC-GOV-117, TC-PI-138, TC-SM-016/028 | TR; VP |
| RF-08 | 25 | Fixed per RD-9: OD-06 default `integration_owns_done`; FR-120/183/200 mode-dependent; TC-E2E-015/016 | TR; VP |
| RF-09 | 25 | Fixed: pre-push controls in M5 with G-S3 before the first sandbox push | RM §2, §4; IB E5 |
| RF-10 | 25 | Fixed (F part) per RD-4/RD-6 and Addendum B.2: FR-263, MERC-705, G-S5 | TR; RM |
| RF-11 | 25 | Fixed per RD-6/Addendum C.1: OPS-002/003 (no `administration`; drift via bot `metadata:read`; ≤ 60 min) | TR OPS-002/003 |
| RF-12 | 25 | Fixed (F part): FR-051, FR-281 via `agent-ctl`; TC-INT-025, TC-REC-005 | TR; VP |
| RF-13 | 25 | Fixed: FR-161 every PR, OD-23 | TR |
| RF-14 | 25 | Fixed: CI/test fix budget 3 (OD-08); budgets referenced to state-machine §9 | TR FR-144, OD-08 |
| RF-15 | 25 | Fixed: FR-282 states behaviour; ASM-F-04 refuted | TR FR-282, §10 |
| RF-16 | 25 | Fixed per RD-13: FR-024 | TR |
| RF-17 | 25 | Fixed (F part): NFR-061 single retention table (OD-15) | TR |
| RF-18 | 25 | Fixed: MIG-0…4 mapped to P0a/M9a/b/c; criteria in roadmap and VP §7.3 | RM §2; TR §8.5 |
| RF-19 | 25 | Fixed (F part): FR-264, TC-SM-022, TC-REC-019 | TR; VP |
| RF-20 | 25 | Fixed: NFR-006, NFR-025…027, NFR-045, NFR-063, NFR-084, NFR-095, OPS-013; watchdog in M7; doctor in M8 | TR; RM |
| RF-21 | 25 | Fixed (F part): FR-220 cites C's channel matrix; TC-SBX-006, TC-SEC-190 | TR; VP |
| RF-22 | 25 | Fixed: FR-007 | TR |
| RF-23 | 25 | Fixed: single P0 register with owners; ASM closure table; OD consolidation | TR §9, §10.2; VP §8.1 |
| RF-24 | 25 | Fixed: re-baselined 156 P50 / ≈ 214 planning P90 (+ contingency); re-estimate at P0 exit | RM §5; IB §2 |
| RF-25 | 25 | Fixed by A (ADR-013…020); TR §5.1 registers them | TR §5 |
| RF-26 | 25 | Fixed (F part): FR-124 block vs escalate split | TR |
| RF-27 | 25 | Fixed per RD-14: FR-182 scope, ≤ 5 min awake, CON-014 | TR |
| RF-28 | 25 | Fixed: FR-141 references GH §4.2 | TR |
| RF-29 | 25 | Deferred to D (layout owner, ADR-016); FR-120 references `macos-service.md` §7.1 | TR FR-120 |
| RF-30 | 25 | Fixed: L14 uses SAC-04 (≥ 60 variants, 100 % / ≥ 95 %) | VP §3 |
| RF-31 | 25 | Fixed: FR-047/FR-240 reference `components.md` §5.5 as single source | TR |
| RF-32 | 25 | Fixed: throughput and cost model with B's and D's inputs; NFR-084 | RM §7 |
| RF-33 | 25 | Fixed: E owns RISK-01…34 (security); F's delivery register RISK-41…56; ranges in the registry | RM §8; TR §1.1 |
| RF-34 | 25 | Fixed: SEC-T-16 on the sandbox in P0c; target onboarding (OPS-016, P0-240) before M9a; G-S4/G-S5 | RM §2; VP §7 |
| RF-35 | 25 | Fixed (F part): FR-260 cites C's question mapping; TC-E2E-010 oracle | TR |
| RF-36 | 25 | Fixed: ADR-P keys retired with mapping | TR §5.2 |
| RF-37 | 25 | Fixed by A (ADR-005) | — |

### 2.2 Findings from other reviews naming F

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RA-04 | 20 | Fixed: FR-162 COMMENT only; MERC-602 | TR; IB |
| RA-09 | 20 | Fixed: CON-003 tightened; FR-242; TC-SEC-145 | TR; VP |
| RA-10 | 20 | Fixed per RD-9 (OD-06 default `integration_owns_done`) | TR |
| RA-16 | 20 | Fixed: FR-040 / NFR-001 mutating-run rule | TR |
| RA-22 | 20 | Fixed: values only by parameter name | TR §7 |
| RA-23 | 20 | Fixed: ASM-F-04 refuted; FR-282 | TR |
| RA-25 | 20 | Fixed: stage criteria in roadmap and VP §7.3; agreement metric defined on eligibility | RM §2; VP §7.3 |
| RA-26 | 20 | Fixed (registry) | TR §1.1 |
| RA-27 | 20 | Fixed (F part): FR-241, FR-905, OD-12 | TR |
| RA-29 | 20 | Fixed: FR-020 cites the schemas for the enum | TR |
| RB-03 | 21 | Fixed: FR-162, TC-GOV-118, P0-237 | TR; VP |
| RC-01 | 22 | Fixed: M6 "COMMENT only" (MERC-602) | IB |
| RC-18 | 22 | Fixed: PROP-05, FR-040 | VP §5 |
| RC-19 | 22 | Fixed: PROP-02 (`scope_version`), PROP-07 (limit + grants), FR-046/TC-SM-010 (work side effects) | VP; TR |
| RC-20 | 22 | Fixed per RD-10 (INV-nn, not SMI-nn) | TR §8.2 |
| RC-31 | 22 | Fixed: NFR-001 duplicate definition; harness §6 | TR; VP §6 |
| RC-40 | 22 | Fixed: FR-084 / PROP-10 replay definition | TR; VP |
| RD-03 | 23 | Fixed (F part): FR-282; FakeClock two modes; NFR-101 | TR; VP §2.2 |
| RD-10 | 23 | Fixed (F part): NFR-024 wording | TR |
| RD-21 | 23 | Fixed: parameter registry by name | TR §7 |
| RD-22 | 23 | Fixed: measurement rule; NFR-005 reworded | TR §1.5 |
| RD-23 | 23 | Fixed: TC-REC-010…021, TC-NET-006/007, TC-OPS-011 | VP §8 |
| RD-24 | 23 | Fixed: T4v tier; TC-REC-020; MERC-802 | VP §2.1, §6 |
| RD-27 | 23 | Fixed: NFR-001 / NFR-026 | TR |
| RE-15 | 24 | Fixed: M6 COMMENT only | IB |
| RE-20 | 24 | Fixed: SEC-T imported as TC aliases; SAC-01…20 as gate evidence; G-S2 before non-sandbox write runs; SEC-T-16 at P0c and G-S3; ASM-E linked to P0 | VP §7.2, §8; TR §10.2 |
| RE-22 | 24 | Fixed (F part): ASM-E-05/11 → P0-225, P0-042 | TR §10.2 |
| RE-26 | 24 | Fixed | TR §4.2 |

### 2.3 Open items addressed to F in other Phase 4 revisions

| Item | Source | Disposition |
|---|---|---|
| Register SEC-113…115, 212–215, 316, 407, 507, 607, 708, 906–908; SEC-603 SHOULD; SEC-T aliases; SAC-01…20 as G-S1…G-S5; RISK-01…34; ASM-E-01…24 with P0 IDs | 44 (E) | Fixed (TR §4, §6.2, §8.3, §10.2; VP §7.2) |
| Register D's parameter names, P0-nnn incl. gates, recovery TC IDs, OD-D-01…08 | 43 (D) | Fixed (TR §7, §8.3, §9 aliases, §10.2) |
| Register P0-201…241, OD-37, cost-model input | 41 (B), Addendum C | Fixed (TR §1.1, §9, §10.2; VP §8.1; RM §7) |
| Register INV-21…27; map SMT/DBT/CT/RT; RC-19/RC-40 wording | 42 (C) | Fixed (TR §8.2–§8.3; VP §5) |
| OD-36 required before unattended operation | Addendum A | Fixed (TR OD-36; RM §4, G-S5; MERC-905, MERC-807b) |

---

## 3. Objections to reconciliation decisions

No decision is contested. Three points for the orchestrator:

1. **G-S5 placement.** E's gate table says "Unattended or overnight operation (M7)". I place the controls in M7 but the gate at **M9c entry**, because no unattended operation happens before cutover. If the orchestrator wants unattended sandbox runs earlier, G-S5 must move and G-ORG would be needed for the sandbox too.
2. **RD-5 and the supervised pilot.** I implement "G-DETECT with written acceptance is enough for M9b". My recommendation (recorded in OD-01, not a deviation) remains to move targets to an organization before M9b, because supervised runs on a real repository can still finish while the operator is away.
3. **Estimate growth.** The reconciled scope moves the base estimate from ≈ 132 to 156 P50 engineer-days (planning P90 ≈ 214) plus 12/22 days of conditional contingency. This is a consequence of RD-1, RD-4, RD-5, RD-11, RD-12 and RD-16, not an objection to them.

---

## 4. Remaining open items

| Item | Owner |
|---|---|
| Pointer lint (TC-OPS-010) across all Phase 4 documents once every revision has landed; section pointers in TR rows use Phase 4 titles | F (Phase 5) |
| D's §16 gate column uses "M0" for Phase 0; read as P0a/P0b in the roadmap | D (wording) |
| Add B's agent-configuration defaults (`claude.*`, `codex.max_tokens_per_run`, `budget.*`) to the parameter table; TR §7 already registers the names | D |
| SEC-113 text: `neutral` → `action_required` (Addendum C.2); TR FR-167 already uses `action_required` | E (Phase 5) |
| P0-049 (agent-uid egress) procedure | E with D |
| Procedures for F-allocated P0-060, P0-067, P0-068, P0-072…074 | E, operator |
| Owners update their ASM "Verified by" columns to the P0 IDs in TR §10.2 | A, B, C, D, E |
| Operator decisions OD-01…37, in particular OD-18 (P0b), OD-36 (by M8 exit) and OD-37 | Operator |
