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

## 3. Brief quality gates (reviews/00-brief.md "Quality gates")

"Pass (design)" means the design specifies the control completely and consistently. It does **not** mean the control is implemented or measured; in the brief's words, design completeness is not validated implementation.

| # | Gate | Status | Evidence | Method |
|---|---|---|---|---|
| Q1 | Every subagent delivered, or limitation recorded | **Pass** | Phase 2 reports `reviews/10…15`; Phase 3 reviews `20…25`; Phase 4 revisions `40…45`; Phase 5 `50`, `51`, `52`, `security/security-review.md` all exist; limitations listed in TDD §31 (six items) | Inspection + link lint |
| Q2 | All major interfaces contracted | **Pass** (one Low) | Envelope + 16 message schemas + 8 strict `output.*` contracts + `common` (26 files; `output.*` have `additionalProperties:false`); control API and CLI (components §5.1–§5.5); `agent-exec`/`agent-ctl` grammar (macos-service §3.5, §3.7); GitHub endpoints and allowlist (github.md §10.4); Linear operations (linear.md); ports (components §4). TDD §10's envelope example omits 4 schema-required fields (VF-12) | Script over `protocols/schemas/` + inspection |
| Q3 | Deterministic lifecycle | **Pass (design)** | Single transition table (state-machine §3, 54 rows T01…, G1…); FR-080/FR-084; PROP-10 replay determinism; TC-SM-001/002 | Script + inspection |
| Q4 | Every transition has authorization rules | **Pass** | 54/54 rows have Initiator, Required evidence and Persistent side effects. Guards are "—" only on T38, G1a, G1b; these are authority-*removing* cancel/revoke transitions gated by principal (operator socket or Claude revoke run). INV-19; TDD §11.3; PROP-08 | Script over state-machine §3 |
| Q5 | Persistence and recovery specified | **Pass (design)** | DDL and triggers (components §6, §6.4); durability ordering (macos-service §14.2); ordered startup recovery (recovery §4; components §10.6); per-state recovery (state-machine §10); FM-01…30, RB-01…18 | Inspection |
| Q6 | Communication versioned and traceable | **Pass** | `envelope.schema.json` requires `schema`, `schema_version`, `message_id`, `correlation_id`, `causation_id`, `dedup_key`, `occurred_at`, `recorded_at`, `issue`, `repo`, `task_id`, `run_id`, `producer`, `actor`, `recorded_by`, `payload_sha256`, `payload`; N/N-1 rule (messages.md); FR-060/061/065 | Script |
| Q7 | Claude authorization required before development | **Pass (design)** | CON-005, FR-022 (dispatch and result application), INV-03 trigger on `runs` insert, PROP-01, PROP-03, TC-SM-004. UNVERIFIABLE until M3 tests run | Trace |
| Q8 | Codex cannot run unapproved work through the coordinator | **Pass (design)** | CON-006, INV-04/05, PROP-02, TC-UNIT-012, TC-SM-007; fresh implementation thread with hash-checked plan (codex.md) | Trace |
| Q9 | Human approval enforced via GitHub permissions and protections | **Pass with condition** | Ruleset (github.md §9.1: CODEOWNERS, last-push approval, no bypass, App-pinned checks); endpoint allowlist SEC-102; ADR-014 modes; threat-model §5.2.2 path proof. **Condition:** on a personal-account repo only G-DETECT is possible (merge actor detected, not prevented); G-ORG (OD-01) is required before unattended use (G-S5). UNVERIFIABLE IN DESIGN — Phase 0 P0-072 (SEC-T-16 on the sandbox), P0-233/235/237 | Trace + inspection |
| Q10 | Security independently reviewed | **Pass** | `reviews/24-review-E-security.md` (Phase 3); `security/security-review.md` (Phase 5, E); cross-review by C/D/F in `50`/`51`/`52` | Inspection |
| Q11 | Failure scenarios documented | **Pass** | recovery §2 host classes, §5 FM catalogue, §7 runbooks, §8 "silent" tree; state-machine §7.1 failure classes; github.md §15 retry matrix | Inspection |
| Q12 | Measurable verification criteria | **Pass** (after fixes) | §2 of this report: 192/192 requirements and 284/284 live TCs have pass/fail criteria; 4 criteria were tightened in place | Script |
| Q13 | Roadmap reflects dependencies | **Pass** (after fixes) | §5 of this report: 80 issues, 0 dependency cycles, 1 phase-placement inversion fixed (MERC-005); security gates placed before first use | Script + inspection |
| Q14 | Incremental implementability | **Pass (design)** | M1 fakes-first core with every invariant trigger; one external capability per milestone; DoR/DoD (traceability §12–§13); C's feasibility validation `reviews/50` | Inspection |
| Q15 | Assumptions and open decisions documented | **Pass with findings** | ASM closure register (traceability §10.2); OD-01…37 (§9); RISK-01…34 + RISK-41…56; TDD §30. ADR/OD default contradictions in §6 (VF-14 Medium, VF-15 Low) | Script + inspection |
| Q16 | "Do not confuse theoretical design completeness with validated implementation" | **Pass** | TDD header "Not approved for implementation"; requirement lifecycle (traceability §1.4: Baseline candidate, nothing Verified); every Mac-level item routed to Phase 0 | Inspection |

## 4. Brief completeness (operating model, constraints, A–J, sections, diagrams)

| Brief item | Present in | Result |
|---|---|---|
| Operating model 1–15 | traceability §2.1 maps each step to ≥ 1 requirement; TDD §1, §7.3, §9–§15, §20. Step 9 deviation ("Codex prepares a PR": the coordinator creates the PR) is documented with rationale in TDD §25 and ADR-006 | Pass |
| Hard constraints (7) + no inbound + design-only | traceability §2.2 → CON-001…018; TDD §3, §6, §11.3, §15, §19 | Pass |
| A Orchestration (authority, dispatch, concurrency, dependencies, status, failure detection, cancel/resume, duplicate prevention, multi-process, versioned authorization) | TDD §8, §9, §11, §23; components §7; state-machine §8; FR-001…055 | Pass |
| B Communication: mechanism evaluation (JSON, queues, SQLite, CLI, MCP, files, IPC, HTTP) | TDD §10 summary; overview §7.1; ADR-003 | Pass |
| B Schemas (14 listed in the brief) | task.authorization, task.assignment, plan (implementation plan), plan.review, plan.approval, plan.revision_request, implementation.progress, test.results, pr.created, code.review, security.findings, revision.request, task.completed, task.failed: **14/14 files present**, plus policy.escalation, triage.result, 8 output contracts | Pass |
| B Required fields (correlation, schema version, timestamps, issue, repo, execution, dedup) | envelope required list (Q6) | Pass |
| C 18 brief states | 17 task states plus issue-level `discovered`; mapping table TDD §11.1; each name present in state-machine.md (counts 8–81 occurrences); full transition table + Mermaid (TDD §11.2; state-machine 3 diagrams) | Pass |
| D Plan-approval criteria (9) + machine-readable results + conditions + max cycles + escalation | TDD §14 (9 criteria = `output.plan_review` enum); V4 semantic checks (messages §5.2); OD-08 budgets; `BLOCKED` + `repeated_review_failure` | Pass |
| E PR workflow + governance | TDD §13, §15; github.md §6, §8, §9, §10 | Pass |
| F Local execution (launchd, login, supervision, shutdown, crash, DB integrity, checkpoints, connectivity, orphans, worktree cleanup, restart) | TDD §18, §20; macos-service; recovery | Pass |
| G Notifications (7 brief events) | TDD §21 matrix and components §4.15: plan-review failure → `repeated_review_failure`; human judgement → `decision_needed`; security → `security_escalation`/`security_halt`; unrecoverable → `unrecoverable_failure`; PR ready → `pr_ready_for_approval`; CI → `ci_intervention_needed`; merge → `merge_completed`. Dedup keys per kind. One channel mismatch, TDD vs components (VF-18) | Pass |
| H Security (16 topics, SW vs POL) | TDD §19 table; threat-model §5 tagged [SW]/[GH]/[OS]/[POL] | Pass |
| I Ten audit questions | components §5.7 rows 1–10 map 1:1 to the brief's questions; TC-E2E-010 oracle; FR-260 (pointer corrected to §5.7) | Pass |
| J Test types (14) | Verification plan L1–L14 cover all 14. TDD §22 summary omits generic integration (L4) and duplicate events (L10) (VF-13) | Pass (TDD summary Low) |
| 32 TDD sections | `## 1.`…`## 32.` titles match the brief (26 is spelled out "Architecture Decision Records") | Pass |
| Mermaid types: architecture, task workflows, message sequences, data relationships, state transitions, failure recovery | TDD §7.1/§7.2 (flowchart), §7.3 (flowchart), §10.1/§10.2 (sequenceDiagram), §16 (erDiagram), §11.2 (stateDiagram-v2), §20 (flowchart) | Present. **§10.2 does not parse (VF-01)** |

**Mermaid lint (`mm/check.mjs`, `mmd/check.mjs`; mermaid 10.9.1 and 11.4.1 with jsdom, `mermaid.parse`).** 29 blocks in non-review docs.

- **10.9.1:** 28/29 parse. The one failure is TDD.md block 5 (§10.2). In a `sequenceDiagram`, `;` acts as a statement separator, so `MD->>GH: push … from mirror; draft PR; check runs pending` (line 344) and line 348 split into invalid statements.
- **11.4.1:** the same failure. Three flowcharts (issue-breakdown, roadmap, threat-model) raise "Element is not defined", which is a jsdom environment limitation; all three parse under 10.9.1.
- **Fix, verified on a patched copy under both versions:** replace `;` with `,` in TDD lines 344 and 348.
- **Limitation:** parse only, no rendering. Layout and readability are unchecked.

