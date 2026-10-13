# Phase 5 Validation F: Requirements Traceability and Acceptance Criteria

| | |
|---|---|
| Validator | Agent F (Technical Program Manager) |
| Date | 2026-10-13 |
| Scope | Cross-document ID and pointer lint (deferred from Phase 4, TC-OPS-010 dry run); requirement → design → test → milestone coverage; brief quality gates; brief completeness (operating model 1–15, hard constraints, areas A–J, 32 sections, Mermaid types); roadmap dependencies and security gates; operator-decision register consistency; accuracy of TDD §5, §22, §27–§30 |
| Method | Inspection plus read-only scripts run with `python3 -I`: `lint_ids.py`, `lint_links.py`, `trace_cov.py`, `brief_cov.py`, `mermaid_check.py` (in the session scratchpad; not committed) |
| Ground rules | Validation, not redesign. I fixed Low/Medium defects in place only in F-owned files (`planning/*`, `testing/verification-plan.md`). I report defects in other owners' files and in TDD.md for the orchestrator. |

Findings use `VF-nn`. Severity follows the Phase 5 scale: Critical / High / Medium / Low.

---

## 1. Cross-document ID and pointer lint

### 1.1 ID resolution and uniqueness (`lint_ids.py`)

**Method.** The script reads every `.md` and `.json` file under `docs/mercury/`. It extracts every citation of the families FR, NFR, CON, OPS, SEC, SEC-T, INV, PROP, TC-*, ADR, OD, RISK, P0, ASM-*, SAC, RB and FM. Range and list shorthand (`…`, `/nnn`, `, -nnn`) are expanded to their explicit endpoints. Definitions are taken only from each family's canonical location in the registry (traceability §1.1):

- traceability §3: CON, FR, NFR, OPS
- traceability §9: OD
- threat-model §5.1: SEC
- threat-model §9: RISK-01…34
- threat-model §10.1–§10.3: SAC, SEC-T, ASM-E
- state-machine §4: INV
- verification plan §5: PROP
- verification plan §8: TC and F's P0
- macos-service §16: P0-0xx and ASM-D
- github.md §19: P0-2xx and ASM-B
- recovery.md: RB headings and FM rows
- `architecture/decisions/`: ADR files
- roadmap §8: RISK-41…

**Result.**

| Measure | Value |
|---|---|
| Distinct IDs cited | 1,150 |
| Canonical definitions | ADR 20 · ASM 122 · CON 18 · FM 30 · FR 107 · INV 27 · NFR 48 (incl. retired NFR-007) · OD 37 · OPS 19 · P0 85 · PROP 24 · RB 18 · RISK 50 · SAC 20 · SEC 90 · SEC-T 57 · TC 282 (284 after the fix below) |
| Defined twice in canonical locations | **0**. The first run reported 10 ASM-E duplicates. These were D's ASM-E→P0 mapping table (macos-service §16.4), which only cites the IDs; after refining the script the count is 0 |
| Cited outside `reviews/` but not resolved | 64 raw. Triage below |
| Cited only in `reviews/` and not resolved | 27, all historical (e.g. ASM-C-03…18, FR-039, SEC-089). Informational only |
| Restated ID rows outside canonical locations | TDD §30 OD summary (17 rows, allowed as a summary, checked in §6); traceability RTM, alias and SEC registration tables (by design); threat-model §5.2.3 (2 analysis rows). None restate a definition differently (spot-checked) |

Triage of the 64 raw unresolved citations:

| Class | IDs | Verdict |
|---|---|---|
| Registry band endpoints and wildcards | CON-099, FR-999, NFR-109, OPS-099, RISK-35/40/99, P0-050/079, NFR-04x/08x, TC-GOV-11n/11x, TC-PI-13n/13x | Not citations. Pass |
| Retired or withdrawn rows listed as such | SEC-001…099 (traceability §4.2); TC-SEC-002/005/007, TC-GOV-003/007, TC-PI-005 (VP §8.18); ASM-B-03/15/17/18/20 (github.md §19 "Withdrawn"); ASM-D-15/22/23 (macos-service §16 "Withdrawn") | Pass. One exception: ASM-B-18 is listed as withdrawn but is still cited as a live assumption in traceability §10.2 (row "ASM-A-05, ASM-B-18 → P0-038"). **Fixed in place** (VF-07) |
| Phase-2 two-digit P0 aliases | P0-01, P0-25 (alias statement, valid); **P0-26…P0-32** in overview.md:626/630, ADR-013:31, ADR-020:56, threat-model §10.3 (958–996) | Meaning is unambiguous (1:1 with P0-026…032). However, D declares aliases only for `P0-01…P0-25`, and the registry rule says new text uses canonical IDs. **VF-05 (Low, A/E)** |
| Truly undefined | **P0-049**: cited in 8 places (gates SEC-206, G-S2 "if chosen") but it has no procedure row ("to be specified by E"). **P0-052**: endpoint in OPS-001's RTM row. **ASM-C-01, ASM-C-02**: cited by components.md:50 and traceability §10.2, but defined only in the process record `reviews/12-agent-C-report.md`. **TC-REC-022/023**: defined in recovery.md §6 but not in the verification plan catalogue | P0-049 → **VF-06 (Low, E/D; resolved during Phase 5: E added the procedure as `security/threat-model.md` §10.4 (VE-17), and F updated the gate registration, see §8)**. P0-052 → **fixed in place** (VF-07). ASM-C → **VF-08 (Low, C)**. TC-REC-022/023 → **fixed in place** (VF-04) |
| Namespace collisions | **RB-06a/b, RB-19…RB-26** are Review-B findings (`reviews/21`, RB-01…27). They share the RB prefix with D's runbooks RB-01…18, so RB-01…18 citations are ambiguous: linear.md §7.3 heading "(RD-18, RB-13)" means Review-B finding 13, not runbook RB-13. Likewise **RD-nn** (Review-D findings, RD-01…31) collides with reconciliation decisions **RD-1…RD-20**. Examples: traceability §1.5 "RD-16, RD-22"; reconciliation RD-15 cites "RD-13, RD-15" as findings | **VF-03 (Medium)** |

**TC-REC semantic collision (VF-04, Medium, D).** `operations/recovery.md` §6 labels seven scenarios with TC-REC IDs that mean something else in the verification plan, the sole TC owner:

| recovery.md §6 label | What recovery.md means | What the verification plan defines under that ID | Canonical ID per traceability §8.3 alias map |
|---|---|---|---|
| TC-REC-002 | power loss on the VM | fault-filesystem logic test | TC-REC-020 (VM) |
| TC-REC-003 | adoption | sleep | TC-REC-030 |
| TC-REC-004 | 2 h sleep | reboot | TC-REC-031 |
| TC-REC-006 | restore | launchd restart | TC-REC-019 |
| TC-REC-007 | invalid Codex output | SIGTERM | TC-AFS-008 |
| TC-REC-008 | SIGTERM | corrupt DB | TC-REC-007 |
| TC-REC-009 | supervisor lease | downtime summary | TC-REC-033 |

recovery.md says its IDs are "proposals for F", so the verification plan governs. Fixed in F's files: I added TC-REC-022/023 to the verification plan §8.10 and added a mapping note after §8.10. **D should relabel recovery.md §6** to the canonical IDs.

### 1.2 Relative Markdown links and file§ pointers (`lint_links.py`)

**Method.** The script checks:

- every non-URL Markdown link (text in brackets, target in parentheses) outside code fences: the file must exist, and the anchor must match a GitHub-style heading slug;
- every plain-text pointer of the form `<doc>[.md] §N[.N…]` (including continuation lists) and the abbreviations SM/GH/MSG/CL/CX/LN/VP/TM/TR/RM: the cited section number must exist as a heading in the target file.

All non-review documents were scanned.

**Result.** 472 links and 1,175 file§ pointers checked.

| Class | Count | Detail | Verdict |
|---|---|---|---|
| Missing link target | 5 at first run; **0 at re-run** | TDD §19, §32 → `security/security-review.md`, `reviews/50-…`, `51-…`, `52-…` | All four Phase 5 outputs now exist. **VF-09 (Low, orchestrator, resolved)**: re-run the lint once more at sign-off, because TDD.md was edited during Phase 5 (re-run on the current TDD: 1,511 pointers, 0 genuine misses) |
| Missing anchor | 1 | `reviews/12-agent-C-report.md:31` → `components.md#9-worktree-management` (heading is now "9. Worktrees, snapshots and git hardening") | Process record; informational |
| Missing section | 0 genuine | Two script hits were false positives (traceability:228 "TDD §5, 0 references"; components:965 "§4.1/§4.15 of this document") | Pass |
| TDD.md pointers into supporting docs | all resolve | e.g. components §4.2–§4.16, §5, §5.7, §6.4, §6.5, §10.2–§10.10; state-machine §2.2, §3.7, §4, §7.3, §8, §10; macos-service §2, §2.3, §2.5, §3, §7.1, §9.1, §10, §11, §13–§14; github.md §8, §13; threat-model §3, §5, §5.2.2, §8.10, §9, §10.1; overview §2, §4, §5.3, §7, §9, §11, §14; messages §5 | Pass |

**Content cross-check (by inspection).** Merge verification is defined once in `integrations/github.md` §8 as **M1–M8**; TDD §15 and §10.2 agree. Other documents disagree:

- `security/threat-model.md` §3.3 item 11, §5.2.1 (L7) and SEC-T-93 say **M1–M9** (**VF-02, Low, E**);
- F's own documents also said M1–M9 (verification plan TC-UNIT-052 and TC-SEC-193; issue-breakdown MERC-70x description). **Fixed in place.**

## 2. Requirement → design → test → milestone coverage (`trace_cov.py`)

**Method.** The script parses:

- the requirement rows of traceability §3: statement, priority, acceptance criterion, verification method, owning design;
- E's SEC catalogue (threat-model §5.1);
- the RTM (traceability §6.1–§6.2);
- the verification-plan catalogue (§8), including P0 rows from macos-service §16 and github.md §19.

For each requirement it checks four things:

1. Is a TDD section named, plus a supporting document?
2. Is the acceptance criterion non-empty, and is it measurable? A heuristic flags criteria with no threshold, count or binary outcome; I reviewed each flagged one by hand.
3. Does the RTM row exist with ≥ 1 test, and does every cited TC or P0 resolve?
4. Is a valid milestone key given?

For each TC it checks that the Covers column cites ≥ 1 registered requirement, that a pass criterion is present, and that the RTM lists the TC (bidirectional trace).

**Result (after fixes).**

| Check | Population | Result |
|---|---|---|
| Requirement has a TDD design section and a supporting-document pointer | 192 CON/FR/NFR/OPS (W rows excluded from test and milestone checks) | **Pass.** First run: NFR-006/021/025/027/082 cited only "parameter table" and FR-260 pointed to components §5.4 (Methods) instead of §5.7 (audit query map). **Fixed in place** |
| Acceptance criterion present and measurable | 192 | **Pass.** 13 flagged by the heuristic; 9 are binary accept/reject criteria (acceptable). NFR-091, NFR-094, NFR-100 and FR-042 lacked a threshold; **fixed in place** with explicit thresholds. FR-042's starvation bound is only implicit in C's scoring formula (components §7.4): **VF-10 (Low, C)** |
| RTM row with ≥ 1 resolvable test | 192 + 90 SEC = 281 live rows | **Pass.** 0 undefined TC IDs. OPS-001's range `P0-001…048, P0-060…074, P0-201…241` has intentional gaps (registry rule 2) |
| Milestone assigned | 281 | **Pass**, every row has a valid key (P0a…P0d, M1…M8, M9a…M9c) |
| Priority consistent (§3 vs RTM; SEC level vs MoSCoW rule F-SEC-1) | 281 | **Finding, fixed in place.** SEC-110 and SEC-211 are MUST in threat-model §5.1 but were registered as S; SEC-206 is "MUST / SHOULD" but was registered as S. All three are now M in traceability §4.1/§6.2, and the §6.3 totals are updated (SEC M 85 / S 5; total M 241 / S 33). (VF-07) |
| TC cites ≥ 1 registered requirement and has a pass criterion | 290 TC/P0 rows in verification plan §8 | **Pass.** The only rows without Covers are the 5 retired-ID rows (§8.18). TC-SEC-1xx/TC-GOV-11x/TC-PI-13x alias rows carry their binary criterion in threat-model §10.2 by design |
| TC listed in the RTM (reverse trace) | 284 live TCs | **Finding, fixed in place.** 19 TCs cited a requirement but were missing from the RTM: TC-SM-027, TC-CON-009/010/011/013, TC-INT-021/022/023, TC-AFS-008, TC-NET-007/009, TC-REC-010/011/013/014/016/018/022/023. Appended to 21 RTM rows; now 0 |
| Verification-only-by-fakes rule | verification plan §1, TDD §22 last line | Pass by inspection: Mac-level requirements (CON-009, CON-018, SEC-201, NFR-053) map to T4/T4v TCs, not only to T0–T2 |

**Unverifiable in design.** Every pass/fail threshold is defined, but none has been measured. Mac-level criteria depend on Phase 0: SEC-T-20 (P0-027), launchd/sleep behaviour (P0-033…046) and the power-loss rig (P0-047). These are **UNVERIFIABLE IN DESIGN — Phase 0 P0-0xx/P0-2xx** as registered in traceability §10.2.

