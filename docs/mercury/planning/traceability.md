# MERCURY — Requirements, ID Registry and Traceability

| | |
|---|---|
| **Owner** | Agent F (Technical Program Manager) |
| **Status** | Phase 4 revision. Implements the binding reconciliation decisions RD-1…RD-20 (`reviews/30-reconciliation.md`). Every requirement is a **baseline candidate** (§1.4) until TDD §32 sign-off. |
| **Authority** | **Single source of truth for requirement IDs and for the project-wide ID registry** (RD-10). Other documents cite IDs from this file and do not redefine them. Statement text of `SEC-*` requirements stays in `security/threat-model.md` (E); this file registers and traces them. |
| **Companions** | `testing/verification-plan.md` defines every `TC-*` and `PROP-*` cited here. `planning/roadmap.md` defines phases, gates and dates. `planning/issue-breakdown.md` maps `MERC-*` issues to requirement IDs. |
| **Disposition** | Phase 3 findings addressed by this revision are listed in `reviews/45-revision-F.md`. |

---

## 1. Conventions

### 1.1 Registry rules (unified ID scheme, RD-10)

1. **One registry.** Every identifier family used in `docs/mercury/` is listed below with its owner and its single defining location. A document that needs an ID it does not own cites it; it never defines a parallel one.
2. **IDs are permanent.** A retired ID keeps its row with status `Retired` and a pointer to its replacement. IDs are never reused. Gaps inside a range are intentional.
3. **Aliases.** IDs used by contributors before Phase 4 remain valid as **aliases for one release** (until M9c exit) through the alias tables in §8. New text must use the canonical ID. The ID lint (TC-OPS-010) reports any alias used outside a quotation of history.
4. **Single source of values.** Requirement rows state *what* must hold and *how it is measured*. Operational parameter **values** (timeouts, thresholds, intervals) live only in the parameter table of `operations/macos-service.md` (D); this file registers each parameter **by name** (§7) and requirements reference the name.
5. **Statement owner vs registration owner.** E owns `SEC-*` statement text; F owns its registration, priority mapping and traceability. C owns `INV-*` text; F owns the `PROP-*` tests that check them.

| Family | Form | Owner | Defined in | Notes |
|---|---|---|---|---|
| Constraints | `CON-001…099` | F | this file §3 | Non-negotiable boundaries |
| Functional | `FR-001…999` (bands §1.2) | F | this file §3 | `FR-9xx` = Won't |
| Non-functional | `NFR-001…109` (bands §1.2) | F | this file §3 | Absorbs A's `NFR-LAT/REL/…` and D's `REL-nn` (aliases §8.1) |
| Operational | `OPS-001…099` | F | this file §3 | Environment, rollout, operator procedures |
| Security | `SEC-1xx…9xx` | E (text), F (registration) | `security/threat-model.md` §5.1; registered in §4 | F's `SEC-001…099` reservation **retired** (§4.2) |
| Design invariants | `INV-01…` | C | `architecture/state-machine.md` §4 | C's `I1…I20` renamed in order (I1 → INV-01) |
| Test properties | `PROP-01…` | F | `testing/verification-plan.md` §5 | Each cites the INV/CON it checks |
| Test cases | `TC-<LEVEL>-nnn` | F (IDs, levels, gates); C, D, E contribute content | `testing/verification-plan.md` §4, §8 | Only test-ID scheme. Contributor IDs are aliases (§8.3) |
| Security acceptance criteria | `SAC-01…20` | E | `security/threat-model.md` §10.1 | Each SAC names its gate G-S1…G-S5 (verification plan §7) |
| Security test procedures | `SEC-T-nn` | E | `security/threat-model.md` §10.2 | Registered as TC aliases (§8.3) |
| Phase 0 checks | `P0-nnn` | D (Mac procedures), B/E (integration and governance procedures), F (closure tracking) | Procedures: `operations/macos-service.md` Phase 0 checklist; register: verification plan §8 `TC-P0` | `TC-P0-nnn` ≡ `P0-nnn`. `P0-001…049` Mac items (D, `operations/macos-service.md` §16); `P0-050…079` agent-CLI, GitHub and Linear items (F allocates, §10.2). Phase 2 `P0-nn` and `E1…E9` are D's aliases |
| Assumptions | `ASM-<agent>-nn` | each agent | the agent's own document | Each gating ASM is linked to a `P0-nnn` check (§10.2) |
| ADRs | `ADR-001…020` | A | `architecture/decisions/` | `ADR-Pnn` retired (§5.2) |
| Operator decisions | `OD-01…36` | F (register), operator (decision) | this file §9 | One list; contributor IDs (OD-A/OQ-B/OD-C/OD-D/OD-E, E Qn) are aliases |
| Risks | `RISK-01…99` | E (`RISK-01…34`, security, `security/threat-model.md` §9); F (`RISK-41…`, delivery and schedule, `planning/roadmap.md` §8) | as listed | Aliases: E `R-01…26`; F `PR-01…12`. `RISK-35…40` reserved for D/C additions |
| Milestones | `P0a…P0d`, `M1…M8`, `M9a…M9c` | F | `planning/roadmap.md` | A's migration stages are `MIG-0…MIG-4` (§8.5) |
| Security gates | `G-S1…G-S5` | E (controls and SAC per gate, `security/threat-model.md` §8.10, §10.1); F (placement in the roadmap) | `planning/roadmap.md` §4 | Gate IDs, not requirements. `G-ORG`/`G-SPLIT`/`G-DETECT` are governance **modes** (ADR-014), not gates |
| Implementation issues | `MERC-nnn` | F | `planning/issue-breakdown.md` | Proposals; not created in Linear by this design |
| Failure modes / runbooks | `FM-nn`, `RB-nn` | D | `operations/recovery.md` | Unchanged |
| Operational parameters | by **name** (`svc.*`, `run.*`, …) | D (values), F (registration) | `operations/macos-service.md` §2 | §7. Workflow policy (attempt counts, revision budgets, authorization expiry, state reminder timers) stays in `architecture/state-machine.md` §7, §9 and OD-08 (Addendum B.4) |

### 1.2 Numeric bands (F-owned prefixes)

| Prefix | Range | Area | Brief anchor |
|---|---|---|---|
| `CON-` | 001–099 | Constraints and invariants (non-negotiable) | Hard constraints, authority invariants |
| `FR-` | 001–019 | Intake, eligibility, dependencies | A, steps 1–2 |
| `FR-` | 020–039 | Claude triage and authorization | A, steps 1–3 |
| `FR-` | 040–059 | Scheduling, dispatch, holds, execution control | A, step 4, F |
| `FR-` | 060–079 | Agent communication and contracts | B |
| `FR-` | 080–099 | Workflow state machine and timers | C |
| `FR-` | 100–119 | Codex planning and Claude plan review | D, steps 5–7 |
| `FR-` | 120–139 | Implementation and tests | E/F, steps 8–9 |
| `FR-` | 140–159 | Git operations and PRs | E, step 9 |
| `FR-` | 160–179 | Claude PR review, required checks, revision loops | E, steps 10–11 |
| `FR-` | 180–199 | Merge verification and post-merge | E, steps 13–14 |
| `FR-` | 200–219 | Linear projection | E/G |
| `FR-` | 220–239 | Human notifications | G, step 12 |
| `FR-` | 240–259 | Operator control | A/F |
| `FR-` | 260–279 | Audit queries and audit integrity | I |
| `FR-` | 280–299 | Recovery | F, step 15 |
| `FR-` | 300–319 | Slack migration and cutover | Mission |
| `FR-` | 900–999 | Explicitly out of scope (Won't) | Non-goals |
| `NFR-` | 001–019 / 020–039 / 040–049 / 050–059 / 060–069 / 070–079 / 080–089 / 090–099 / 100–109 | Reliability / Recoverability / Latency while awake / Durability / Auditability and notifications / Operability / Resource usage and cost / Portability and version pinning / Maintainability and testability | F, I, J |
| `OPS-` | 001–099 | Operational, environment, identity and rollout | F, Mission |

### 1.3 Field definitions

| Field | Meaning |
|---|---|
| **Requirement** | One testable "shall/must" statement ("should" for S, "could" for C). It states behaviour, not mechanism (RD-16). |
| **Rationale / source** | Brief section, discovery fact, reconciliation decision (RD-n) or review finding (Rx-nn). |
| **Pri (MoSCoW)** | **M**: required to exit the supervised pilot (M9b) and cut over (M9c). **S**: required within 30 days after cutover. **C**: optional. **W**: will not be built in this release. SEC `MUST` = M and **release-blocking**; SEC `SHOULD` = S (F-SEC-1). |
| **Acceptance criterion** | Measurable pass/fail. Where the threshold is an operational parameter it is cited by name (§7); the value lives in `operations/macos-service.md`. |
| **Verification** | **Test** (automated), **Inspection**, **Demo** (operator-observed), **Analysis** (data or log analysis). |
| **Owning design** | TDD section plus the supporting document and section holding the detailed design. |

### 1.4 Requirement status lifecycle

`Draft` → `Baseline candidate` (Phase 4, this revision) → `Baselined` (TDD §32 sign-off) → `Designed` (owning section passed Phase 5 review) → `Implemented` (merged) → `Verified` (all mapped TCs pass at their level, evidence linked). Side exits: `Deferred`, `Retired`. A change to a `Baselined` requirement needs a change note (§14) naming the cause: an operator decision, a Phase 0 result, or a review finding.

### 1.5 NFR measurement rule (normative; RD-16, RD-22)

1. **Latency** for an external event `e` is `t_done − max(t_event, t_first_awake_online(e))`, where `t_first_awake_online(e)` is the first instant after `t_event` at which the Mac is awake (full wake, not dark wake), the operator session is logged in and the connectivity probe succeeds, as recorded in `host_events`.
2. **Availability** excludes intervals recorded in `host_events` as sleep, dark wake, logout or offline. Those intervals are reported separately (they are not breaches).
3. **Awake-time budgets** (run deadlines, stall thresholds, hold ageing) count only credited awake time per C's algorithm (`architecture/components.md` §10.10). Sleep gaps are never credited.
4. A metric is computed by the pilot report (`mercury audit --report pilot`) from the audit DB, never by hand. TC-PERF-007 verifies the computation against a scripted `host_events` fixture.

### 1.6 Document abbreviations and owners

All paths are relative to `docs/mercury/`.

| Path | Owner |
|---|---|
| `architecture/overview.md`, `architecture/decisions/ADR-*.md` | A |
| `integrations/{claude,codex,linear,github}.md` | B |
| `architecture/components.md`, `architecture/state-machine.md`, `protocols/messages.md`, `protocols/schemas/` | C |
| `operations/macos-service.md`, `operations/recovery.md` | D |
| `security/threat-model.md` | E |
| `planning/*`, `testing/verification-plan.md` | F |

Section pointers below use the Phase 4 section titles. They are re-checked by the pointer lint (TC-OPS-010) after all Phase 4 revisions land.

---

## 2. Source coverage map

Each brief item and discovery pain point maps to at least one requirement. Phase 5 validation uses this table as its completeness check.

### 2.1 Operating model (brief steps 1–15)

| Step | Summary | Requirements |
|---|---|---|
| 1 | Claude is the primary orchestrator (decision authority; the coordinator holds the loop, RD-20) | CON-003, FR-020 |
| 2 | Claude evaluates and prioritizes eligible issues | FR-001…008, FR-020, FR-042 |
| 3 | Claude explicitly authorizes each task | FR-021…024, CON-005 |
| 4 | A continuously running coordinator executes and tracks | FR-040, FR-041, FR-049…055, NFR-002, NFR-004, NFR-042 |
| 5 | Codex produces a plan | FR-100 |
| 6 | Claude reviews the plan | FR-066, FR-101, FR-105 |
| 7 | Claude auto-approves or requests revisions | FR-103, FR-104, FR-106 |
| 8 | Codex implements in isolated worktrees | FR-120, FR-121, FR-123, FR-124, FR-126, CON-016, CON-018 |
| 9 | Tests run, PR prepared | FR-122, FR-140…144 |
| 10 | Claude reviews the PR independently | FR-160, FR-161, FR-162, FR-166 |
| 11 | Failed review leads to a revision loop | FR-163, FR-144, FR-165 |
| 12 | Human notified through GitHub and Linear | FR-164, FR-220, NFR-043, CON-011 |
| 13 | Only the human approves and merges | CON-007, CON-014, FR-166, FR-167, FR-180, FR-902, SEC-100, SEC-109 |
| 14 | Coordinator verifies the merge and updates Linear | FR-181…183, FR-200, NFR-044 |
| 15 | Unfinished tasks recover after restart | FR-053, FR-054, FR-280…283, NFR-020, NFR-024 |

### 2.2 Hard constraints and authority invariants

| Constraint | Requirements |
|---|---|
| Never start work from a Linear status change alone (Inv. 3) | CON-004, FR-002, FR-203, INV-17 |
| Claude authorization required, as a versioned record (Inv. 1) | CON-005, FR-021, FR-022, INV-03, INV-18 |
| Codex cannot run unapproved implementation (Inv. 2) | CON-006, FR-102, FR-121, INV-04, INV-05 |
| Human approval enforced technically; no impersonation (Inv. 4) | CON-007, CON-008, CON-014, FR-162, FR-166, FR-167, FR-180, FR-242, OPS-003, SEC-100…109, SEC-201 |
| No assumption of work during sleep | CON-009, FR-052, FR-082, FR-085, FR-282, NFR-021, NFR-008 |
| A plan revision invalidates earlier approval | CON-006, FR-102, INV-05 |
| Bounded revision cycles with escalation | CON-012, FR-104, FR-144, FR-163, SEC-315 |
| No secrets in docs | CON-010, SEC-501 |
| Design only | CON-001 |
| No public inbound access | CON-002, FR-901 |

### 2.3 Content areas A–J

| Area | Requirements |
|---|---|
| A Orchestration | FR-001…008, FR-020…024, FR-040…055, CON-003…005 |
| B Communication | FR-060…066, FR-125 |
| C State machine | FR-080…085, FR-050, CON-012 |
| D Plan approval | FR-100…106 |
| E GitHub PR workflow | FR-120…126, FR-140…145, FR-160…168, FR-180…185, OPS-003, OPS-016, OPS-017, CON-007, CON-014 |
| F Local execution | FR-044, FR-051…055, FR-184, FR-280…283, NFR-002, NFR-020…027, NFR-050…053, NFR-070, NFR-092, OPS-012…015, CON-018 |
| G Notifications | FR-164, FR-220…224, CON-011, NFR-063 |
| H Security | `SEC-1xx…9xx` (§4), CON-007, CON-008, CON-010, CON-018, FR-124, FR-203, FR-242, FR-243 |
| I Observability and audit | FR-260…264, NFR-060…062 |
| J Testing | NFR-100, NFR-101, OPS-004, `testing/verification-plan.md` |

### 2.4 Quality gates (brief)

| Gate | Evidence requirement(s) or check |
|---|---|
| Deterministic lifecycle | FR-080, FR-084 |
| Every transition has authorization rules | FR-080, FR-081 (initiator field), INV-19, TC-SM-001/002/019 |
| Persistence and recovery specified | FR-063, FR-280, NFR-020, NFR-050, NFR-053 |
| Communication versioned and traceable | FR-060, FR-061, FR-065 |
| Claude authorization before development | CON-005, FR-022 |
| Codex cannot run unapproved work | CON-006, FR-121 |
| Human approval via GitHub permissions | CON-007, FR-166, FR-167, OPS-003, TC-GOV-* |
| Measurable verification | Every row in §3 has a pass/fail acceptance criterion; §1.5 measurement rule |
| Roadmap reflects dependencies | `planning/roadmap.md` (Mermaid graph, gates), `planning/issue-breakdown.md` (blocked-by) |
| Assumptions and open decisions documented | §9 (OD register), §10 (assumption closure), `planning/roadmap.md` §8 (RISK register) |

### 2.5 Discovery pain points and facts

| Pain point / fact (source) | Requirements |
|---|---|
| Identity confusion: agents post as the human (integrations S1; fact 3) | CON-008, FR-140, FR-201, OPS-002, SEC-103, SEC-801 |
| Lost or unseen replies (Slack pattern 2) | FR-063, NFR-005 |
| Stalls without detection, 14 h (pattern 3) | FR-044, FR-125, NFR-003, NFR-006, FR-222, OPS-013 |
| Manual human relays (pattern 4) | FR-020, FR-241, TC-PIL-002 ("0 relays") |
| Delivery failures needing manual retry (pattern 5) | FR-223 |
| Duplicate or junk posts; token leaked by the test suite (pattern 6) | FR-221, NFR-001, OPS-004, CON-010 |
| Environment split: cloud vs Mac worktrees (pattern 7) | CON-016 |
| Evidence vs claims (pattern 8) | FR-064, FR-122, FR-181 |
| Linear `Todo` used as the queue (fact 5) | CON-004, FR-002 |
| Linear coding sessions as a second start path (fact 5) | FR-005, FR-904, SEC-803, SEC-804 |
| Linear GitHub integration auto-moves status (integrations C3) | FR-183, FR-200, OD-06 |
| Personal-account repo; merge restriction is org-only (fact 4) | CON-014, OPS-017, OD-01 |
| Codex likely cannot commit in a sandboxed worktree (fact 7) | FR-140, P0-037 |
| Claude runs repo hooks and `.mcp.json` headless (fact 6) | FR-066, SEC-204, SEC-205, TC-SEC-103 |
| No whole-run timeout in either CLI (fact 8) | FR-044, FR-055, NFR-083 |
| launchd: LaunchAgent only while logged in; detached children escape cleanup (fact 10) | FR-051, FR-055, FR-281, NFR-024, OPS-012 |
| TCC-protected folders (platform M6) | NFR-092 |
| SQLite durability on macOS (fact 11) | NFR-050, NFR-053 |
| Version churn in agent CLIs (runtimes §6) | NFR-090, NFR-093 |
| Agents could read the operator's credentials (E R-03; RD-1) | CON-018, FR-051, OPS-014, SEC-201 |

---

## 3. Requirements

### Constraints (CON) — non-negotiable boundaries

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **CON-001** | MERCURY's design phase must not modify any host, repository setting, Linear workspace, GitHub resource or Slack workspace; implementation starts only after operator sign-off of the TDD. | Brief: Mission | M | Phase 4/5 review finds 0 write actions in agent evidence logs; TDD §32 sign-off recorded before M1 starts. | Inspection | TDD §32, §27 · `reviews/` |
| **CON-002** | The coordinator must run locally on the operator's Mac and must not require any public inbound network path; all integrations are outbound. | Brief; discovery fact 9 | M | No MERCURY listener on a non-loopback interface; control is a Unix socket; all GitHub/Linear traffic is outbound HTTPS. | Inspection + Test | TDD §7, §18 · `architecture/overview.md`; `operations/macos-service.md` |
| **CON-003** | Role boundary: Claude makes development decisions, MERCURY coordinates execution, Codex implements, the operator holds final merge authority. Operator CLI actions may stop, hold, cancel, grant budget or acknowledge escalations; they never authorize work or approve plans or PRs. An interactive agent running as the operator may *request* a decision but never clear an escalation (RD-12, RD-20). | Brief: core boundary; RA-09 | M | Every authority record (`authorizations`, `plan_approvals`, `plan_reviews`, `pr_reviews`) references a successful Claude decision run (INV-18); the control API exposes no authorize/approve method (TC-INT-024); safety-relaxing methods require the presence tier (TC-SEC-145). | Inspection + Test | TDD §9 · `architecture/overview.md` §8; `architecture/components.md` §5 |
| **CON-004** | A Linear status change alone must never start development work; it may only make an issue eligible for Claude evaluation. | Invariant 3; fact 5 | M | 0 Codex runs start without an authorization record across E2E and sandbox; moving 50 sandbox issues to Todo produces 0 Codex spawns before authorization; PROP-03 holds. | Test | TDD §11, §12 · `architecture/state-machine.md` §4; `integrations/linear.md` |
| **CON-005** | No Codex run may execute without a valid, unrevoked Claude authorization bound to the exact task, Linear issue, repository and current `spec_hash`. | Invariant 1; RD-13 | M | Spawn gate refuses 100 % of the negative matrix (missing, revoked, expired, superseded, mismatched task/issue/repo/spec); PROP-01: 0 counterexamples. | Test | TDD §9, §11, §13 · `architecture/state-machine.md` §8.1 |
| **CON-006** | No Codex implementation run may execute without a Claude approval bound to the exact plan artifact hash; any plan revision invalidates earlier approval unless the revised artifact is explicitly re-approved. | Invariant 2 | M | PROP-02: 0 counterexamples; spawn gate refuses 100 % of hash-mismatch mutants. | Test | TDD §11, §14 · `architecture/state-machine.md` §8.2 |
| **CON-007** | The human approval boundary must be enforced by GitHub rulesets, required MERCURY check runs pinned to the MERCURY App, CODEOWNERS and token permissions, not by prompt instructions; no MERCURY identity may satisfy required human approval or impersonate it. | Invariant 4; RD-5 | M | TC-GOV-110…118 and TC-PI-138 pass on the sandbox; SAC-01, SAC-02, SAC-16 and SAC-17 pass. | Test + Inspection | TDD §15, §19 · `integrations/github.md` §9; `architecture/decisions/ADR-014` |
| **CON-008** | Agents and the coordinator must never act under the operator's personal GitHub, Linear or Slack identity or credentials. | Fact 3; RD-6 | M | Every PR, commit, review, check run and Linear write is attributed to `mercury-bot`, `mercury-ops` or the Linear app actor; credential inventory contains no human token (SEC-T-13). | Test + Inspection | TDD §9, §15, §19 · `integrations/github.md` §2; `integrations/linear.md` §2 |
| **CON-009** | The design must not assume work continues while macOS sleeps, dark-wakes, is logged out or is rebooting; every timer must tolerate indefinite pauses. | Hard constraints; fact 10; RD-16 | M | No task reaches `FAILED` or `BLOCKED` solely because of a sleep gap in TC-SM-009/TC-REC-031 (both FakeClock modes) and TC-REC-003/021 (real Mac / virtual clock). | Test | TDD §18, §20 · `architecture/components.md` §10.10; `operations/macos-service.md` §8 |
| **CON-010** | Secrets must never appear in docs, repositories, plists, process argv, logs, artifacts, PR bodies or Linear comments. | Fact 12 (leaked bot token) | M | Secret canary test finds 0 occurrences (TC-SEC-004, SAC-06); repository secret scan returns 0 findings (TC-OPS-009). | Test + Inspection | TDD §19, §21 · `security/threat-model.md` §8.4 |
| **CON-011** | Human-facing notifications must use existing GitHub and Linear channels (iPhone + Mac) and, for local-only conditions, macOS notifications; MERCURY must not require a new dashboard, app or chat channel. | Brief; RD-19 | M | Every notification kind in the channel matrix is delivered through GitHub, Linear, the `mercury-ops` issue or a local notification; no MERCURY UI exists beyond the CLI. | Inspection + Test | TDD §7, §21 · `architecture/components.md` §4.15; `ADR-019` |
| **CON-012** | Revision cycles (plan, PR review, CI/test fix, human change requests) must be bounded per task, and exceeding a bound must escalate to the operator. | Hard constraints | M | TC-SM-008: the (N+1)th request for each loop type → `BLOCKED` with exactly one escalation; PROP-07 holds. | Test | TDD §11, §14 · `architecture/state-machine.md` §9 |
| **CON-013** | MERCURY must coordinate target repositories distinct from its own and must not hard-code Linear team keys, issue prefixes, repository names or human logins. | Fact 2 | M | Source grep for `JAM`, `network_monitor`, `usjbro` outside config/fixtures returns 0; E2E passes with a different team key and repo. | Inspection + Test | TDD §8, §12 · `architecture/components.md` §13 |
| **CON-014** | Each MERCURY-managed repository has a recorded merge-governance mode — G-ORG, G-SPLIT or G-DETECT (ADR-014). G-DETECT is allowed only for the sandbox and the supervised pilot and only with written operator risk acceptance; **G-ORG is required before any unattended or overnight operation on a target repository**. In every mode a non-operator merge is detected and alerted. | Fact 4; RD-5; RF-27 | M | Governance report lists the mode per repo with the acceptance reference (TC-OPS-005); a simulated non-operator merge raises a SECURITY incident within one poll cycle and ≤ 5 min awake (SAC-10, TC-GOV-004); the dispatcher refuses unattended dispatch to a non-G-ORG target (TC-E2E-021). | Inspection + Test | TDD §15, §19 · `ADR-014`; `integrations/github.md` §8, §10 |
| **CON-015** | All Mac-, GitHub- and Linear-dependent behaviour marked as an assumption must be verified by a Phase 0 check (or explicitly accepted by the operator) before the milestone that depends on it starts. | Fact 1 | M | Phase 0 report shows every gating `ASM-*` (§10.2) as Verified, Refuted-with-design-change or Accepted; 0 Open at each milestone entry. | Inspection | TDD §18, §30 · §10 below |
| **CON-016** | Codex must execute only in coordinator-managed local worktrees on the Mac; cloud worktrees, Codex Cloud or Linear coding sessions are not part of the controlled path. | Pattern 7 | M | Every Codex run record has `cwd` under `WORK_ROOT` task worktrees; FR-005 covers Linear-native sessions. | Test + Inspection | TDD §13 · `integrations/codex.md`; `operations/macos-service.md` §7.1 |
| **CON-017** | Each requirement and each contract is defined in exactly one place; other documents reference IDs (§1.1). | Brief: documentation layout | M | ID lint finds 0 requirement definitions outside this file / TDD §5, 0 references to undefined IDs, 0 restated parameter values outside the parameter table (TC-OPS-010). | Inspection | TDD §5, §29 · this file |
| **CON-018** | No Codex workspace-write run, L2 `verify` run or `deps_install` run may execute against a non-sandbox repository until the agent-uid isolation (SEC-201) has passed the credential-canary test (SEC-T-20) on the operator's real Mac. Same-uid execution under Seatbelt is permitted only with fakes and the sandbox repository. | RD-1 gates; RF-01 | M | Dispatcher refuses such runs while gate `G-S2` is not recorded (TC-UNIT-072); SAC-05 evidence exists before the first non-sandbox run. | Test + Inspection | TDD §18, §19 · `ADR-013`; `planning/roadmap.md` §4 |

### FR — Intake, eligibility and dependencies (content area A; operating model 2)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-001** | The coordinator shall poll each configured Linear team incrementally with a durable `updatedAt` cursor and overlap window and record each observed change exactly once, using the dedup key catalogue (value-keyed facts carry an observation sequence so A→B→A transitions are not lost). | Fact 9; RD-18 | M | 100 scripted sandbox updates (including during a poll and A→B→A flips): 0 missed, 0 double-processed. | Test | TDD §12 · `integrations/linear.md`; `integrations/github.md` §14 |
| **FR-002** | An observed issue is eligible for Claude evaluation only when all configured eligibility rules hold (team in scope, workflow state in the configured set, operator-added opt-in label per OD-10, no `Not Speced` label, repository mapping resolves, not already a MERCURY task). | Step 2; OD-10 | M | Rule-table tests cover every rule true/false (≥ 2 cases each); issues failing any rule never get a task row. | Test | TDD §12 · `integrations/linear.md` |
| **FR-003** | Each task resolves to exactly one Linear issue and one target repository through explicit configuration; zero or multiple mappings make the issue ineligible and are flagged once. | Baseline | M | 0/1/2+ mappings → ineligible/eligible/ineligible; one flag per issue per change. | Test | TDD §8, §12 · `architecture/components.md` §13 |
| **FR-004** | The coordinator shall not dispatch a task whose Linear issue has unresolved `blockedBy` relations, applying the dependency guard of FR-008, and shall re-evaluate when blockers change. | Area A | M | E2E: open blocker → undispatched for ≥ 3 poll cycles; dispatched within 2 poll intervals after the blocker resolves. | Test | TDD §8, §11 · `architecture/state-machine.md` §8.4 |
| **FR-005** | The coordinator shall detect Linear-native delegation or coding sessions on managed or eligible issues, refuse to dispatch them, and flag the issue once (SEC-803). | Fact 5 | M | Fixture with a foreign `delegate` → `BLOCKED(foreign_agent_delegation)` and exactly one flag. | Test | TDD §12 · `integrations/linear.md` |
| **FR-006** | The coordinator should pass all Linear relations, labels, priority and the description to Claude triage and mark prose-only dependency references as unverified context. | JAM-117 | C | Triage input fixture contains relations and a `prose_refs` list. | Test | TDD §12, §14 · `integrations/linear.md` |
| **FR-007** | The coordinator shall record each observed issue's issue-level status `mercury_status ∈ {discovered, ineligible(reason), shortlisted, task}`, visible in `mercury status --issues`. The brief's `Discovered` state is this issue-level status, not a task state. | RF-22; RD-14 | M | Every observed issue in the sandbox corpus has exactly one current `mercury_status`; CLI lists them; brief-state mapping table present in TDD §11. | Test + Inspection | TDD §11, §12 · `architecture/state-machine.md` §1 |
| **FR-008** | Dependency guard: a blocker that is itself MERCURY-managed is resolved only when its task is `COMPLETED` in MERCURY; Linear `Done` is never treated as merge proof. Non-managed blockers resolve on the configured Linear completed/canceled states. | RD-9 | M | E2E: blocker issue moved to Done in Linear while its MERCURY task is not `COMPLETED` → dependent stays undispatched (TC-E2E-017). | Test | TDD §11 · `architecture/state-machine.md` §8.4 |

### FR — Claude triage and authorization (content area A; operating model 1–3)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-020** | The coordinator shall invoke Claude to evaluate and prioritize eligible issues and accept only output valid against the triage/authorization schemas in `protocols/schemas/` (the schemas are the single source of the decision enum; RA-29). | Steps 1–3 | M | Contract tests: valid outputs accepted; invalid or missing `structured_output` → run failure, no state change beyond retry accounting. | Test | TDD §9, §14 · `integrations/claude.md`; `protocols/schemas/` |
| **FR-021** | For each `authorize` decision the coordinator shall write an immutable, versioned authorization record (task, issue, repo, `spec_hash`, scope, limits, expiry) derived only from schema-valid Claude output; re-authorization creates a new version that supersedes the old one, never mutates it. | Hard constraint; RD-13 | M | DB rejects UPDATE on authorization rows (trigger, TC-INT-020); each record carries the SHA-256 of its canonical JSON; re-authorization yields version n+1. | Test + Inspection | TDD §9, §16 · `architecture/components.md` §6, §10.3 |
| **FR-022** | Before spawning any Codex run, and again before applying any run result, the coordinator shall verify in one transaction that a current authorization exists, is unrevoked, unexpired, not superseded, and matches task, issue, repository and current `spec_hash`. | Invariant 1; RD-13 | M | Gate unit tests at 100 % branch coverage; 0 unauthorized spawns or applied results in TC-SM-004 and TC-REC-001/038. | Test | TDD §11, §13 · `architecture/state-machine.md` §8.1 |
| **FR-023** | Claude (decision run) or the operator (CLI) shall be able to revoke an authorization; running Codex processes for the task are stopped and no further work side effects (push, PR creation, review request) occur. | Area A | M | E2E: revocation during implementation stops the run within the kill-ladder bound (`supervisor.kill_ladder_s`) and produces 0 pushes/PRs afterwards. | Test | TDD §9, §11 · `architecture/state-machine.md` §8.6 |
| **FR-024** | Spec drift: the compared value is `spec_hash` (normalized title, description, acceptance criteria and eligibility-relevant labels). A change after authorization sets the `spec_changed` hold; results of runs that finish after the change are not acted upon until Claude re-authorizes against the new hash (Claude may confirm "no material change"); PR-stage tasks keep the PR open and require re-authorization before further Codex work. One non-mention Linear comment records the drift; escalation to `BLOCKED` happens only through hold ageing (FR-050). | RD-13; RF-16; RE-14 | M | TC-E2E-008/020: edit after authorization → hold set, 0 Codex dispatches and 0 applied results until a new authorization version exists; PR stays open; TC-SM-015 passes. | Test | TDD §11, §12 · `architecture/state-machine.md` §5, §8.1 |

### FR — Scheduling, dispatch, holds and execution control (content area A)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-040** | Work is dispatched from a queue **derived** from `tasks.state`, holds and leases (no separate jobs table) by a claim transaction that re-checks version, holds and guards, such that at most one active **mutating** run exists per task and at most one active run per (task, kind); read-only Claude review runs may overlap (INV-02). | ADR-015; RC-18; RA-16 | M | PROP-05: 0 counterexamples; TC-CONC-004: 0 violations across 1,000 simulated lease expiries. | Test | TDD §8, §16 · `architecture/components.md` §7 |
| **FR-041** | Configurable concurrency limits: global, per agent type (Claude, Codex) and per repository (defaults per OD-07). | Area A | M | TC-CONC-001: never exceeded over 1,000 simulated steps with 20 queued tasks. | Test | TDD §8, §23 · `architecture/components.md` §7.3 |
| **FR-042** | The dispatcher orders authorized work by Claude priority, then authorization time, and does not starve tasks beyond the configured ageing bound. | Steps 2, 4 | S | Scheduler tests: order respected; no task waits beyond the bound in simulation. | Test | TDD §8 · `architecture/components.md` §7.4 |
| **FR-043** | Each side-effecting step carries a deterministic idempotency key from the single dedup key catalogue so re-execution after a crash or retry has at most one external effect. | Area A/B; RD-18 | M | See NFR-001; TC-CON-015 checks keys against the catalogue. | Test | TDD §10, §20 · `integrations/github.md` §14; `architecture/components.md` §4.14 |
| **FR-044** | The coordinator detects agent failure by awake-time deadline, stall and exit classification. Liveness = stdout growth **or** process-group CPU-time progress; a run is stalled only when both are flat for the kind's stall threshold, which is never shorter than the repository test timeout while a command runs. Termination is SIGINT → SIGTERM → SIGKILL of the whole group via `agent-ctl`. | Fact 8; RD-15 | M | Hung fake agent with 3 descendants: all terminated within deadline + grace; 0 survivors; a 20-minute quiet test command with CPU progress is **not** classified stalled (TC-AFS-009). | Test | TDD §13, §18 · `architecture/components.md` §8.4; parameter table (`run.<kind>.*`) |
| **FR-045** | Each step has a bounded retry policy per the single retry matrix; non-transient failures route to `FAILED` or `BLOCKED` with escalation. | Area C; RD-18 | M | Retry-calculator tests match the matrix; injected permanent error → exactly one escalation. | Test | TDD §11, §20 · `integrations/github.md` §15 |
| **FR-046** | The operator (CLI) and Claude (decision) can cancel a task from any non-terminal state; cancellation stops running processes, records the reason, reaches `CANCELLED` and schedules cleanup per FR-184. After the cancel timestamp there are 0 **work** side effects (runs, pushes, PR creation, review requests); the cancel-protocol notices are each sent exactly once. | Area A; RC-19 | M | TC-SM-010: cancel succeeds from every non-terminal state; 0 processes survive; 0 work effects; each cancel notice once. | Test | TDD §11 · `architecture/state-machine.md` §8.6 |
| **FR-047** | The operator can pause and resume a task or the whole coordinator; pause is a hold (no state change) and resume continues from the last durable point without repeating completed side effects. Verbs are those of `architecture/components.md` §5.5 (single source). | Area A; RF-31 | M | TC-SM-011: pause/resume from every pausable state; 0 repeated effects; state unchanged by pause. | Test | TDD §11, §20 · `architecture/components.md` §5.5 |
| **FR-048** | Only one coordinator instance may run per `MERCURY_HOME` (`flock`, the single instance guard); the CLI acts only through the control socket. | Fact 11; RD-11 | M | Second instance with the lock held logs and exits 0 within 5 s; no CLI path writes SQLite (inspection). | Test + Inspection | TDD §8, §18 · `architecture/components.md` §5.1 |
| **FR-049** | The CLI exposes task status (state, holds, step, age, attempts, next deadline, waiting-on). | Area A | M | `mercury status` returns all non-terminal tasks in ≤ 2 s with the listed fields. | Demo + Test | TDD §8, §21 · `architecture/components.md` §5.5 |
| **FR-050** | Holds (`operator_pause`, `sleep`, `network_down`, `rate_limited`, `spec_changed`, `dependency_unresolved`, `deprioritized`, `integrity_alert` (repo), `security_halt` (global)) block new work only and never change task state. Each hold kind has a defined setter, clearer and notification policy. A hold active longer than its ageing threshold (awake time) escalates **once** to `BLOCKED(needs_human_decision)` or a digest notification. Security conditions are never auto-clearing; a hold whose clearing re-enables Codex work clears only through the authorization guard. Holds can emit outbox effects. | ADR-015; RD-3 | M | PROP-20, PROP-21: 0 counterexamples; TC-SM-012/013/014 pass. | Test | TDD §11 · `architecture/state-machine.md` §5; parameter table (`hold_age.*`) |
| **FR-051** | Every process that executes model-directed or repository-derived code (Codex plan/implement/revise, L2 `verify`, `deps_install`, Claude decision runs) is spawned as the agent uid through the root-owned `agent-exec` wrapper and is signalled, probed, listed, measured and swept only through `agent-ctl`, both with a fixed argument grammar. Secrets reach agents only on fd 3. The coordinator never signals agent processes directly. | RD-1; RF-01; RF-12 | M | TC-INT-025 (fake broker) and P0-026…028 (real Mac) pass; argv-grammar fuzzing yields 0 escapes (TC-SEC-128); `ps` audit shows agent kinds running as the agent uid. | Test | TDD §13, §18 · `ADR-013`; `operations/macos-service.md` agent-uid design; `architecture/components.md` §4.7 |
| **FR-052** | No new run is dispatched during a dark wake: dispatch requires a full-wake signal or a continuous credited awake period of at least `wake.dark_wake_min_awake_s`. | RD-16; RD-18 (D) | M | TC-REC-012 (real Mac, Power Nap) and TC-SM-023: 0 dispatches during dark wake. | Test | TDD §18 · `operations/macos-service.md` §8 |
| **FR-053** | Run outcome class `lost_by_host` applies when the boot session changed or `exit.json` reports `supervisor_lost`; it consumes no attempt, has a separate cap per step (`run.lost_by_host_cap`) and on exhaustion raises an ops alert, not `BLOCKED`. | RD-11; RD-12 (D) | M | TC-REC-032: three reboots during one implementation step consume 0 attempts; cap exhaustion → 1 ops alert, state unchanged; PROP-24 holds. | Test | TDD §20 · `architecture/components.md` §8.6 |
| **FR-054** | After a coordinator restart, detached Codex, `verify` and `deps_install` runs are adopted when the identity triple (`run_id` marker, start time, boot session) matches; piped Claude runs are killed and re-run with the same `input_digest` without consuming an attempt. The authorization guard (FR-022) is re-evaluated before an adopted output is acted on. Adopted runs are never kept through safe mode or a security halt. | RD-11 | M | TC-REC-030: adopted run finalized, 0 re-runs; TC-REC-038: authorization revoked while down → adopted output discarded; TC-AFS-010: Claude re-run consumes 0 attempts. | Test | TDD §20 · `architecture/components.md` §8.6; `ADR-020` |
| **FR-055** | `agent-exec` enforces the hard awake-time deadline it is given and a supervisor lease: if `WORK_ROOT/ctl/coordinator.alive` (operator-owned 0640, group-readable; Addendum B.3) is stale for more than `supervisor.lease_stale_min` of credited time it terminates the group (SIGINT → SIGTERM → SIGKILL) and writes `exit.json{reason: supervisor_lost}`. | RD-11; RD-10 (D) | M | TC-REC-033: daemon stopped with a live run → run terminated after the lease, `exit.json` reason recorded; 0 orphans. | Test | TDD §18, §20 · `ADR-020`; parameter table |

### FR — Agent communication and contracts (content area B)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-060** | Every message between coordinator components and agent adapters uses the versioned envelope defined in `protocols/messages.md`. | Area B | M | Envelope validator rejects one mutant per required field. | Test | TDD §10, §17 · `protocols/messages.md` |
| **FR-061** | Message schemas exist for every brief §B message type and are validated on produce and consume. | Area B | M | Every schema has ≥ 1 golden example and ≥ 3 invalid mutants; 100 % pass. | Test | TDD §10, §17 · `protocols/schemas/` |
| **FR-062** | Agent outputs are requested with a CI-generated **wire copy** of each output schema restricted to the provider's strict-mode subset, and validated by the coordinator against the canonical schema; a missing or invalid output is a run failure, never a success; a provider schema-rejection error is classified `config_fatal`. | Runtimes §2.1; RD-15 | M | TC-CON-014: every wire copy is generated and accepted by both providers' validators; TC-AFS-005/011 pass. | Test | TDD §13, §14, §17 · `protocols/messages.md`; `integrations/claude.md`; `integrations/codex.md` |
| **FR-063** | Messages and external-effect intents are persisted before they are acted on (transactional inbox/outbox); consumers are idempotent by key. | Fact 12 | M | 100 duplicate deliveries → 100 effects; kill between persist and act loses 0 messages. | Test | TDD §10, §16 · `architecture/components.md` §4.13–§4.14 |
| **FR-064** | Artifacts are immutable files under `MERCURY_HOME` (outside any worktree), referenced by ID and SHA-256 and verified on read. | Baseline | M | Tamper → hash mismatch → integrity alert; no artifact path inside `WORK_ROOT`. | Test | TDD §10, §16 · `protocols/messages.md` |
| **FR-065** | Consumers should accept the current and previous minor version of each schema. | Area B | S | Contract suite validates N and N−1 examples. | Test | TDD §17 · `protocols/messages.md` |
| **FR-066** | Every repository tree Claude reads is a coordinator-built git-object snapshot (base SHA for authorization and plan review; head SHA for PR review); Claude never runs in a Codex worktree; the snapshot's tree SHA is recorded in the decision binding (answers audit question 7). | RD-7; RF-05 | M | TC-SEC-124 (snapshot builder) passes; 100 % of Claude decision records carry `snapshot_tree_sha`; 0 Claude runs with `cwd` in a worktree. | Test | TDD §14 · `ADR-017`; `architecture/components.md` §9 |

### FR — Workflow state machine and timers (content area C)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-080** | The coordinator implements the 17-state lifecycle and transition table of `architecture/state-machine.md` and rejects (and audits) any transition not in the table. | Area C; RD-14 | M | TC-SM-001 accepts 100 % of table transitions with guards true; TC-SM-002 rejects 100 % of other pairs. | Test | TDD §11 · `architecture/state-machine.md` §3 |
| **FR-081** | Each transition records initiator, event, guard results, evidence and timestamps in the same transaction as the state change; the initiator must be allowed for that row (INV-19). | Area C | M | TC-SM-003 (fields on 100 % of transitions); TC-SM-019 (initiator fuzzing: 0 accepted mismatches). | Test + Inspection | TDD §11, §16 · `architecture/state-machine.md` §11 |
| **FR-082** | Each non-terminal state defines a timeout and action. Deadlines that measure agent work use credited awake time; deadlines that wait on external parties fire only under the timer rule (FR-085). | Fact 10; RD-16 | M | TC-SM-009 in both FakeClock modes: an 8 h sleep gap during `IMPLEMENTING` fires nothing; awake overrun fires. | Test | TDD §11, §18 · `architecture/state-machine.md` §7 |
| **FR-083** | Terminal states are absorbing; `MERGED` → `COMPLETED` only after merge verification and the Linear update succeed. | Area C | M | TC-SM-006: 0 transitions out of terminal states; PROP-06 holds. | Test | TDD §11 · `architecture/state-machine.md` §3.5 |
| **FR-084** | State evolution is deterministic: re-applying a task's `task_transitions` rows with their recorded evidence and guard reports to a fresh store yields identical `tasks` rows and counters. (Raw-event replay under a fake clock is a separate property.) | Quality gate; RC-40 | M | TC-SM-005 / PROP-10: equality in 10,000 generated logs. | Test | TDD §11, §16 · `architecture/state-machine.md` §11 |
| **FR-085** | Timer rule: a state timer may fire only after at least one attempt of the awaited action has been made after the latest wake or start; durations are measured from first observation, not the remote timestamp; on wake, all due reminders and expiries are coalesced into one summary notification. | RD-14; RD-16 (D) | M | TC-REC-021: merge observed after > 24 h asleep is verified, not blocked; TC-REC-039: N authorizations expiring during sleep → 1 summary; TC-SM-021 passes. | Test | TDD §11, §20 · `architecture/state-machine.md` §7.3 |

### FR — Codex planning and Claude plan review (content area D; operating model 5–7)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-100** | For an authorized task the coordinator runs Codex in planning mode (read-only sandbox, task worktree, per-task coordinator-generated `CODEX_HOME` with a read-only `config.toml` and agent-writable `sessions/`) and stores the plan as an immutable, hashed, schema-valid plan version. | Step 5; RD-15 | M | E2E: plan artifact stored with hash; argv contains the read-only sandbox and output-schema flags; `config.toml` hash verified before every run (TC-INT-026). | Test | TDD §13 · `integrations/codex.md` §3, §5 |
| **FR-101** | Claude reviews each plan version against the nine criteria of the plan-review schema; the verdict is machine-readable with per-criterion results, findings and approval conditions. | Step 6 | M | Schema enforces all 9 criteria exactly once; contract test rejects omissions. | Test | TDD §14 · `integrations/claude.md`; `protocols/schemas/` |
| **FR-102** | A plan approval binds to the exact plan hash and the current authorization `scope_version`; any new plan version supersedes prior approvals; a limits-only amendment keeps the approval valid. | Invariant 2; RC-19 | M | See CON-006 (PROP-02); TC-SM-026 (scope vs limits amendment). | Test | TDD §11, §14 · `architecture/state-machine.md` §8.2 |
| **FR-103** | On a plan `revise` verdict bound to the current plan hash, the coordinator renders Claude's `required_change` items **verbatim** through the fixed, hashed revision template and resumes the Codex planning thread; the new plan version links to the review that caused it. | Step 7; RD-8 | M | E2E: 2 revision cycles → plan v1→v3, each linked; template hash recorded; no coordinator-authored text in the request (TC-E2E-002). | Test | TDD §13, §14 · `protocols/messages.md` §5.1; `integrations/codex.md` §3.2 |
| **FR-104** | Plan review cycles are limited (OD-08 default); exceeding the limit blocks the task with one escalation. | Bounded cycles | M | TC-E2E-003: limit + 1 → `BLOCKED` + exactly 1 notification. | Test | TDD §11 · `architecture/state-machine.md` §9 |
| **FR-105** | Issues labelled `Security` (configurable) require an explicit security pass in plan review and PR review; a non-pass cannot be auto-approved. | Discovery | M | E2E: approval without a security pass is rejected by the guard. | Test | TDD §14, §19 · `integrations/claude.md` |
| **FR-106** | Claude may auto-approve a plan only when all mandatory criteria pass (policy per OD-11); conditional approvals record conditions that PR review must check. | Step 7 | M | Guard rejects approve with any failing mandatory criterion; conditions appear in PR-review input. | Test | TDD §14 · `integrations/claude.md` |

### FR — Implementation and testing (operating model 8–9)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-120** | One isolated git worktree per task, created from the base branch at a recorded base SHA under `WORK_ROOT` (layout per `operations/macos-service.md` §7.1). The branch name contains the Linear identifier only in Linear mode `integration_owns_done`; in `mercury_owns_all` it does not (OD-06). | Step 8; RD-2; RD-9 | M | Worktree path under `WORK_ROOT`; branch name matches the mode's pattern in `integrations/github.md` §4.1; base SHA recorded. | Test | TDD §13, §15 · `integrations/github.md` §4.1 |
| **FR-121** | A Codex implementation run (workspace-write sandbox, no network, allowlisted environment, agent uid) starts only after FR-022 and the plan-approval gate pass, with the approved plan as input. | Step 8 | M | Spawn audit shows both gate results for 100 % of implementation runs; argv contains approved flags only. | Test + Inspection | TDD §13 · `integrations/codex.md` §4 |
| **FR-122** | The coordinator runs the repository's configured tests (`verify`) as the agent uid under a fail-closed Seatbelt profile with no network, and stores a test-results artifact. If no sandbox mechanism is available, `verify` is recorded `not_run` and CI is the gate; tests never run unsandboxed. | Step 9; RD-17; RE-02 | M | Test-results artifact for 100 % of PRs; TC-SEC-125: unsandboxed execution 0 times; network attempts from `verify` denied. | Test | TDD §13, §22 · `integrations/codex.md` §10 |
| **FR-123** | Dependency installation is a coordinator step (`deps_install`) run as the agent uid with `--ignore-scripts`, a registry allowlist and lockfile lint, using only base-branch lockfiles or lockfile changes acknowledged through `MERCURY / policy` (OD-09). | Runtimes R2; RD-17 | M | TC-SEC-125/171: lifecycle scripts not executed; non-allowlisted `resolved` hosts rejected before install; unacknowledged lockfile change → install refused. | Test + Inspection | TDD §13 · `integrations/codex.md` §10 |
| **FR-124** | Before committing, the coordinator compares the diff with the approved plan scope and the protected-path policy (owned by SEC-310). Secret hits, forbidden symlinks and forbidden events **block** (`BLOCKED(security_policy_violation)`). A protected-path change within the authorization's `escalate` allowance proceeds to push with `MERCURY / policy` not successful until the operator acknowledges it (FR-167); outside the allowance it blocks. | Discovery; RF-26 | M | TC-UNIT-043 and TC-AFS-007: out-of-scope and forbidden fixtures block; allowed protected-path fixture → push + policy check pending; TC-PI-138 passes. | Test | TDD §13, §19 · `integrations/codex.md` §9; `architecture/state-machine.md` T19 |
| **FR-125** | Codex progress (JSONL) is converted into progress messages so stall detection and the audit trail reflect real activity. | Stalls | M | ≥ 1 progress event per completed Codex item; FR-044 liveness uses it. | Test | TDD §13, §21 · `integrations/codex.md` |
| **FR-126** | Worktree reset follows one policy: archive uncommitted changes as a patch artifact → `reset --hard tasks.last_commit_sha` (or `base_sha`) → `clean -ffd`, adding `-x` only when `deps_install` is re-queued in the same step. No checkpoint commits. | RD-11; RD-04 (D) | M | TC-REC-037: after each reset the tree equals the recorded commit; archived patch restores the discarded changes; ignored dependency trees survive retries that do not re-queue `deps_install`. | Test | TDD §13, §20 · `architecture/components.md` §9 |

### FR — Git operations and pull requests (operating model 9)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-140** | The coordinator (never Codex or Claude) commits, pushes and opens the PR as `mercury-bot`. Commits are created with plumbing against the mirror, never with configuration from an agent-writable worktree; the worktree `.git` pointer is verified before every git invocation; pushes happen from the mirror with `GIT_ASKPASS` reading the token from an inherited fd. | RD-17; RE-03 | M | TC-INT-027 and TC-SEC-140/141: planted hooks, fsmonitor, `insteadOf` and pointer tampering never execute or redirect; sandbox PRs and commits authored by the bot. | Test | TDD §13, §15 · `architecture/components.md` §9; `integrations/github.md` §3–§4 |
| **FR-141** | Commits carry the trailer set of `integrations/github.md` §4.2 (single source; `Mercury-Plan` carries the full SHA-256). | RF-28 | S | Trailer parser finds the full set on 100 % of MERCURY commits. | Test | TDD §15 · `integrations/github.md` §4.2 |
| **FR-142** | The PR opens as **draft** from the template (`integrations/github.md` §5.1) with the Linear link phrasing of the active Linear mode, authorization and plan references and the test summary. It is marked ready and the operator review is requested only when `MERCURY / claude-review` succeeds. Agent text in the body passes the public-sink renderer (mentions, closing keywords and Linear magic words neutralised). | RD-18; RD-9; RE-12 | M | Golden render test; sandbox PR is draft until the check succeeds; 0 review requests before success (TC-E2E-019); TC-SEC-153 passes. | Test | TDD §15 · `integrations/github.md` §5–§6 |
| **FR-143** | PR creation is idempotent: lookup by head (`state=all`) before create; at most one PR per task. | Area A; RD-18 | M | Crash/timeout between create and response: retry yields the same PR (0 duplicates in 1,000 crash runs). | Test | TDD §15, §20 · `integrations/github.md` §5 |
| **FR-144** | The coordinator derives the required CI contexts from `GET /rules/branches/{base}` at each evaluation, waits only on non-MERCURY required checks, and routes CI failures through a Claude `revision_request` decision run (CI logs are untrusted) to a bounded fix loop (OD-08 default) or escalation. | RD-5; RD-8; RD-18; RF-14 | M | E2E: failing check → Claude revision request → fix → green; limit + 1 → `BLOCKED` + 1 notification; changed ruleset contexts picked up on the next evaluation (TC-INT-029). | Test | TDD §15 · `integrations/github.md` §7 |
| **FR-145** | Target-repository CI must run on draft PRs; onboarding verifies this before the first dispatch to the repository. | RD-18 | M | OPS-016 onboarding check fails for a repo whose workflows skip drafts (TC-OPS-016). | Test + Inspection | TDD §15 · `integrations/github.md` §9 |

### FR — Claude PR review, required checks and revision loops (operating model 10–11)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-160** | Claude independently reviews each PR head SHA (snapshot per FR-066) for functionality, maintainability, security, spec compliance, plan conformance and approval conditions, returning a schema-valid verdict bound to the head SHA. | Step 10 | M | Contract tests pass; verdict bound to head SHA in the store. | Test | TDD §14 · `integrations/claude.md` §3 |
| **FR-161** | A Claude security review runs on **every** PR as a separate run (OD-23); findings at or above the configured severity block the claude-review check. | Area E; RF-13 | M | E2E: blocking security finding → check not successful regardless of the functional verdict. | Test | TDD §14, §19 · `integrations/claude.md` §3; SEC-314 |
| **FR-162** | Review results are persisted as artifacts and posted by `mercury-bot` as `COMMENT` reviews only; MERCURY never submits `APPROVE` or `REQUEST_CHANGES`, never dismisses reviews. | RD-5; RA-04; RB-03; RC-01 | M | Sandbox: 100 % of MERCURY reviews are `COMMENT`; static check finds no other event literal on the review path (TC-CON-012); TC-GOV-118 passes. | Test + Inspection | TDD §15 · `integrations/github.md` §6 |
| **FR-163** | Revision requests: a validated Claude review bound to the current head yields its `required_change` items verbatim through the fixed template; every other source (CI failures, local test failures, merge conflicts, operator `CHANGES_REQUESTED` reviews, diff-gate violations, conflicting or `needs_plan_change` reviews) goes through a Claude `revision_request` decision run. Loops are bounded (OD-08) with escalation. | Step 11; RD-8 | M | TC-E2E-004/018: each source routes as specified; provenance (`producer.kind`) recorded; limit + 1 → `BLOCKED` + 1 notification. | Test | TDD §11, §14 · `protocols/messages.md` §5.1 |
| **FR-164** | On a passing review the task enters `AWAITING_HUMAN_APPROVAL` and the operator is notified through the GitHub review request per the channel matrix. | Step 12 | M | Sandbox: review request within NFR-043. | Test | TDD §11, §15 · `integrations/github.md` §6 |
| **FR-165** | Any new commit on the PR head after a Claude pass invalidates the pass (check reset) and triggers re-review. | Last-push rule | M | E2E: human push → re-review on the new SHA; check not successful meanwhile. | Test | TDD §11 · `architecture/state-machine.md` §8.3 |
| **FR-166** | `MERCURY / claude-review` is a required check run created by `mercury-bot` and pinned to it by integration id in the ruleset; it is `success` only when the code and security reviews pass for the exact head SHA, otherwise neutral/failure; hold changes update it through the outbox. | RD-5; RB-04/05 | M | TC-GOV-117: same-named check from another identity does not satisfy the ruleset; TC-E2E-019: success only for the reviewed head. | Test | TDD §15 · `integrations/github.md` §6, §9; `ADR-014` |
| **FR-167** | `MERCURY / policy` is a required check run (deterministic pre-checks) that stays neutral/failure while protected-path, dependency or build-script changes await operator acknowledgement; the task is `BLOCKED(policy_ack_required)` until `mercury policy ack` (presence tier) concludes the check `success` for that head SHA. | RD-5; RD-14; RF-07 | M | TC-PI-138: merge impossible until acknowledgement; acknowledgement without presence rejected (TC-SEC-145); TC-SM-016 passes. | Test | TDD §15, §19 · `integrations/github.md` §6; `architecture/state-machine.md` §6 |
| **FR-168** | Security findings on public PRs: details for medium and below; critical/high and pre-existing findings are withheld (generic line plus local report ID) per OD-21. | RD-18 | M | TC-SEC-154: seeded high finding never appears in PR text; report ID resolves locally. | Test | TDD §14, §19 · `integrations/github.md` §6 |

### FR — Merge verification and post-merge (operating model 13–14)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-180** | The coordinator never approves, merges, enables auto-merge, calls `update-branch`, dismisses reviews or edits rulesets; no such code path exists (endpoint allowlist, SEC-102). | Step 13 | M | Static analysis and network log over all suites: 0 such calls (TC-GOV-005, TC-GOV-111). | Inspection + Test | TDD §15 · `integrations/github.md` §1 |
| **FR-181** | After a merge is observed, the coordinator verifies it with the merge-verification recipe of `integrations/github.md` §8 (checks by numeric ID, single source), distinguishing "data not yet available" from definitive failure. | Step 14; RE-16 | M | Predicate tests for each failing check (TC-UNIT-052); sandbox operator merge verifies OK. | Test | TDD §15 · `integrations/github.md` §8 |
| **FR-182** | A definitive merge-verification failure keeps the task out of `COMPLETED` as `BLOCKED(merge_verification_failed)` with a SECURITY notification within one poll cycle and ≤ 5 min awake. Wrong merge actor or merge commit not on base → global `security_halt`; approval, content or review-ordering mismatch → repo `integrity_alert` hold. An operator merge before the Claude review (`merged_unreviewed_head`) is a policy notice, not a security incident. Exit via `ack-merge` (presence tier) or re-verify. | RD-14; RF-27; RD-31 (D) | M | TC-GOV-004 and TC-SM-017/018: correct scope per failing check; alert latency per NFR-008; no new state introduced. | Test | TDD §15, §19 · `architecture/state-machine.md` §8.5 |
| **FR-183** | Post-merge Linear updates follow the configured Linear mode (OD-06): `integration_owns_done` — the Linear integration moves In Review/Done, MERCURY writes `In Progress`, comments and a verification comment after merge verification; `mercury_owns_all` — MERCURY sets `Done` only after merge verification. Updates are idempotent and never fight the integration. | RD-9; RF-08 | M | TC-E2E-015/016 and TC-SBX-004/009: per mode, exactly one verification comment; final state Done; 0 status flaps over 10 min. | Test | TDD §12 · `integrations/linear.md` §6 |
| **FR-184** | Worktree and local branch are removed after verified merge or cancellation only if no uncommitted changes remain or an archive artifact exists (INV-14), with realpath-checked removal (SEC-406). | Area F | S | Cleanup refuses when unsaved changes exist; artifacts remain (TC-INT-006, TC-SEC-143). | Test | TDD §13 · `architecture/components.md` §9.5 |
| **FR-185** | A PR closed without merge transitions to a defined state (`CANCELLED` if closed by the operator; Claude decision otherwise) with one notification. | Completeness | S | E2E: closed PR → `CANCELLED(pr_closed)`. | Test | TDD §11 · `architecture/state-machine.md` |

### FR — Linear projection

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-200** | The coordinator projects internal state onto Linear per the active Linear mode's projection table; the internal store is authoritative and Linear `Done` is never merge proof. | RD-9 | M | Projection tests per mode cover all 17 states. | Test | TDD §12 · `integrations/linear.md` §6 |
| **FR-201** | Linear writes are attributed to the OAuth `actor=app` application (OD-05). | Fact 3 | M | Sandbox comments show the app actor. | Test | TDD §12 · `integrations/linear.md` §2 |
| **FR-202** | Linear writes are idempotent (deterministic v4-shaped UUID comment ids) with at most one comment per decision event. | RD-18 | M | Interrupted write retried → 1 comment (TC-NET-003, TC-UNIT-070). | Test | TDD §12 · `integrations/linear.md` |
| **FR-203** | No Linear or GitHub text is interpreted as an authorization, approval or operator command. | SEC-302 | M | TC-GOV-006 and TC-PI-131 pass. | Test | TDD §12, §19 · `integrations/linear.md` §10 |

### FR — Human notifications (content area G)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-220** | The coordinator notifies the operator for repeated plan-review failure, decisions needing human judgement, security escalation, unrecoverable failures, PR ready for approval, CI failures needing intervention and merge completion, using exactly the channels of the notification channel matrix (kind → channel → dedup key → reminder cadence; `architecture/components.md` §4.15, ADR-019). | Area G; RD-19; RF-21 | M | Sandbox: each kind delivered once through its matrix channel (TC-SBX-006). | Test | TDD §21 · `architecture/components.md` §4.15 |
| **FR-221** | Notifications are deduplicated by (task, kind, subject version) and never sent for unchanged status. | Report-on-change rule | M | TC-DUP-005: 0 repeats over 100 unchanged polls. | Test | TDD §21 · `architecture/components.md` §4.15 |
| **FR-222** | After downtime or sleep longer than `recovery.downtime_notice_min` with active tasks, the coordinator sends one summary notification on resume (coalescing all due reminders, FR-085). | Unnoticed stalls | S | TC-REC-009: one summary per episode. | Test | TDD §20, §21 · `operations/recovery.md` |
| **FR-223** | Undelivered notifications are persisted and retried until delivered or expired; delivery failure is logged. Network-class failures consume no attempt (FR-283). | DNS incident | M | Network down during notify → delivered once after recovery. | Test | TDD §21 · `architecture/components.md` §4.14 |
| **FR-224** | Operations and SECURITY alerts go to the `mercury-ops` issue in `project-mercury`; the issue conversation is locked to collaborators and alert text is template-only (no task content). | RD-19; RE-11 | M | TC-SEC-190: template-only body; non-collaborator comment impossible; heartbeat carries no task content. | Test + Inspection | TDD §21 · `operations/macos-service.md` §11 |

### FR — Operator control

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-240** | A local CLI provides the verbs of `architecture/components.md` §5.5 (single source), restricted to the operator account through the 0600 socket token; every mutating command is audited. | Areas A, F, I; RF-31 | M | CLI integration tests per verb; audit event per mutating command (TC-INT-010). | Test | TDD §8, §18 · `architecture/components.md` §5 |
| **FR-241** | The operator resolves escalations only through the local CLI in v1 (OD-12); GitHub and Linear text is never a control input. The operator can see escalations on the iPhone but not resolve them (accepted tradeoff). | RD-19 | M | Escalation resolution recorded with the operator principal; comments cannot resolve escalations (TC-GOV-006). | Test | TDD §9, §19 · `ADR-019` |
| **FR-242** | Operator-presence tier: `ack-merge`, security resume/unhalt, `adopt`, budget/revision `grant`, `policy ack`, post-incident `unpause`, restore-epoch confirmation (Addendum B.5) and the ruleset-emergency runbook require a local user-presence confirmation (Touch ID or password via the signed LocalAuthentication helper) in addition to the socket token. Other operator commands need only the token. | RD-12; RA-09 | M | TC-SEC-145: each presence command rejected with token only; accepted with presence; a process running as the operator can request but not clear. | Test | TDD §9, §19 · `ADR-019`; `architecture/components.md` §5.2 |
| **FR-243** | Global `security_halt` is set automatically on the triggers listed in SEC-902/SEC-905 and E's halt list (unauthorized merge, merge without approval, content mismatch, unexpected base commit, governance drift, secret-scan hit, git-config tamper, chain failure, sandbox violation) and is cleared only through the presence tier; `mercury pause --all` and the halt flag file act as a kill switch. | RE-25; RD-3 | M | TC-SEC-191: each trigger sets the halt; 0 dispatches while set; token-only unpause rejected. | Test | TDD §19, §20 · `architecture/state-machine.md` §5 |

### FR — Audit queries and integrity (content area I)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-260** | `mercury trace <task|issue|pr>` answers the ten brief §I questions using the question → table/column → artifact mapping of `architecture/components.md` §5.4. | Area I; RF-35 | M | TC-E2E-010: 10/10 correct, including a crashed and restarted task. | Test | TDD §21 · `architecture/components.md` §5.4 |
| **FR-261** | Every state transition, agent run (argv without secrets, versions, exit, cost/tokens, model actually used), external write and operator action produces an audit event linked by correlation and causation IDs. | Area I; RD-18 | M | See NFR-060. | Test | TDD §21 · `architecture/components.md` §4.16 |
| **FR-262** | At startup and daily the coordinator verifies the audit hash chain; a failure enters safe mode (no dispatch) and sends one SECURITY notification. | RD-4 | M | TC-SEC-161: single-row mutation → safe mode + 1 notification (SAC-08). | Test | TDD §21 · `ADR-018` |
| **FR-263** | The chain head `(seq, hash)` is anchored off-host in App-posted artifacts: the Linear completion comment per task and a daily anchor in a private anchor repository via `mercury-ops`; the `MERCURY / claude-review` check-run summary carries it **only on private repositories** (Addendum B.2, OD-24). An overdue anchor (`audit.anchor_overdue_h`) raises an ops alert, never a halt. Anchoring is required before unattended operation (M7 exit). | RD-4; RF-10 | M | TC-SEC-163: anchors present at each carrier and absent from public check summaries; a local rewrite behind an anchor is detected by `audit verify`. | Test | TDD §21 · `ADR-018`; `architecture/components.md` §6 (`anchors`) |
| **FR-264** | Restore and new-Mac flows record an operator-initiated `audit.restore_epoch` event; `audit verify` accepts a chain fork only through that event; authority that cannot be verified after restore maps to `BLOCKED(reauthorization_required)`, never to `guard_integrity_failure`. | RD-4; RD-06 (D); RF-19 | M | TC-REC-019 and TC-SEC-164: restore of a 24 h-old backup with anchors ahead → epoch recorded, 0 cancelled tasks, authority only shrinks; TC-SM-022 passes. | Test | TDD §20, §21 · `operations/recovery.md`; `ADR-018` |

### FR — Recovery (content area F; operating model 15)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-280** | On start the coordinator follows the startup/exit contract (lock held → exit 0; DB corruption → stay alive in safe mode; schema too new → `fatal.json`, exit 0) and then recovers every non-terminal task: reconcile runs (FR-054), reconcile external state, resume or re-queue from the last durable point. | Step 15; RD-11 | M | TC-REC-001/004/035: 100 % of non-terminal tasks recovered; 0 duplicates; each contract case behaves as specified. | Test | TDD §20 · `operations/recovery.md`; `architecture/components.md` §10.6 |
| **FR-281** | Orphaned agent processes are reaped through `agent-ctl sweep`, keyed by `run_id`, with pgid and start time verified (PID-reuse safe). | Fact 10; RF-12 | M | TC-REC-005: orphans killed; unrelated process with reused PID untouched; 0 orphans after recovery. | Test | TDD §18, §20 · `architecture/components.md` §8.3 |
| **FR-282** | Sleep gaps are not credited to run budgets or state timers. On wake the coordinator probes connectivity, re-evaluates deadlines under the timer rule (FR-085) and resumes polling. (Detection mechanism: `architecture/components.md` §10.10.) | Platform §4.4; RD-16; RF-15 | M | TC-SM-009 and TC-REC-031 in both FakeClock modes: 0 credited sleep; TC-REC-003 (real Mac): first poll ≤ `recovery.first_poll_max_s` after the network is reachable. | Test | TDD §18, §20 · `architecture/components.md` §10.10; `operations/macos-service.md` §8 |
| **FR-283** | During connectivity loss the coordinator holds external effects (`network_down` hold), queues intents durably and resumes without state corruption. Network-class failures never consume run or outbox attempts while the hold is set or the authenticated probe fails within 60 s of the error; there is no `BLOCKED(network)`. | Area F; RD-18 | M | TC-NET-001…003 and TC-NET-006/008: 0 `dead` outbox items and 0 attempts consumed from network-class errors. | Test | TDD §20 · `integrations/github.md` §15 |

### FR — Migration from the Slack workflow

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-300** | During MIG-1…MIG-2, MERCURY-managed issues are marked by the opt-in label (OD-10) and excluded from the legacy scripts so that no issue is driven by both systems; MERCURY refuses issues with a legacy claim. | Fact 2; ADR-012 | M | Pilot log: 0 issues with both legacy gate files and MERCURY tasks. | Inspection + Demo | TDD §24, §27 · `planning/roadmap.md` §3 |
| **FR-301** | At cutover (MIG-3) Slack-based coordination for MERCURY-managed work is disabled and its bot token revoked (SEC-806). | Fact 12 | M | 30-day watch: 0 Slack posts for MERCURY tasks; revocation recorded. | Inspection | TDD §24, §27 · `planning/roadmap.md` §3 |

### FR — Explicitly out of scope for this release (Won't)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-900** | No web dashboard or mobile app. | Brief | W | No HTTP UI exists. | Inspection | TDD §3 · `architecture/overview.md` |
| **FR-901** | No inbound webhooks or public endpoint. | Brief | W | See CON-002. | Inspection | TDD §3, §7 · `architecture/overview.md` |
| **FR-902** | MERCURY will not merge, approve or enqueue PRs for merge, even when all checks pass. | Step 13 | W | See FR-180. | Inspection | TDD §3, §15 · `integrations/github.md` |
| **FR-903** | No multi-Mac operation or high availability. | Locally hosted | W | Single-instance lock (FR-048). | Inspection | TDD §3 · `architecture/overview.md` |
| **FR-904** | No Linear-native agent delegation, coding sessions or Codex Cloud as an execution path. | Fact 5 | W | See FR-005. | Inspection | TDD §3, §12 · `integrations/linear.md` |
| **FR-905** | No operator response channel through GitHub or Linear text in v1 (OD-12). | RD-19 | W | See FR-241. | Inspection | TDD §3 · `ADR-019` |

### NFR — Reliability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-001** | External side effects are exactly-once in effect under crashes and retries. **Duplicate execution** = two concurrently active runs violating INV-02, or a second run for the same (task, kind, binding) after a validated result was recorded. Re-execution after a lost run is allowed and counted by NFR-026. | Area A; RC-31; RD-27 (D) | M | 0 ledger violations across 1,000 randomized crash-injection runs per nightly, every crash point hit ≥ 10 times (TC-REC-001). | Test | TDD §20 · `architecture/components.md` §8.7 (crash-point registry) |
| **NFR-002** | After a coordinator crash launchd restarts it and it is `ready` within `svc.restart_to_ready_max_s` and dispatching within 60 s of the crash. | Platform M1; RF-04 | M | 10 `kill -9` trials on the Mac: 10/10 within the bounds (TC-REC-006). | Test | TDD §18 · `operations/macos-service.md` §5; parameter table |
| **NFR-003** | Task-level stall: any task not waiting on a human with no progress beyond its state timeout is flagged within timeout + 2 poll intervals of awake time. | 14 h stall | M | 100 % of injected stalls detected within bound; pilot max undetected stall within bound (TC-PIL-004). | Test + Analysis | TDD §20, §21 · `architecture/state-machine.md` §7 |
| **NFR-004** | Coordinator availability (per §1.5) ≥ 99 % during the supervised pilot and ≥ 99.5 % over the 30 days after cutover. | Monitoring gap; RF-04 | S | Heartbeat analysis per §1.5 (TC-PIL-002, TC-PERF-007). | Analysis | TDD §20 · `operations/macos-service.md` §11 |
| **NFR-005** | Every durable event (review, merge, comment, check conclusion) and the final state of each tracked entity relevant to an active task is observed, including across network interruptions and sleep; transient intermediate states that polling cannot observe are out of scope. | Missed replies; RD-22 | M | Sandbox replay of 500 events with 20 injected interruptions and sleep gaps: 0 durable events or final states missed. | Test | TDD §12, §15, §20 · `integrations/github.md` §7 |
| **NFR-006** | A dead agent run is detected within 60 s; a stalled run within its stall threshold + 60 s (liveness per FR-044). | REL-07/08; RF-20 | M | TC-AFS-002/009 and TC-REC-005 measurements within bounds. | Test | TDD §20 · parameter table (`run.<kind>.*`) |
| **NFR-007** | Retired → OPS-013 (downtime awareness is an operational watchdog target). | RD-10 | — | — | — | — |
| **NFR-008** | Latency and availability metrics are computed only per the measurement rule §1.5 from `host_events`. | RD-16; RD-22 | M | TC-PERF-007: computed values equal the fixture oracle. | Test | TDD §23 · this file §1.5 |

### NFR — Recoverability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-020** | After `kill -9`, power loss or reboot, 100 % of non-terminal tasks resume or reach a defined state, and the database passes `quick_check`. | Step 15 | M | TC-REC-001/002/004/020: 0 lost tasks; 0 integrity errors. | Test | TDD §20 · `operations/recovery.md` |
| **NFR-021** | No task fails solely because of a sleep gap of any duration; the first poll after wake happens within `recovery.first_poll_max_s` of the network becoming reachable. | Fact 10 | M | TC-REC-003, TC-NET-004. | Test | TDD §18, §20 · parameter table |
| **NFR-022** | Online backup at least daily (RPO ≤ 24 h awake time plus before every upgrade/migration); restore drill ≤ 15 min of operator time. | Platform P2 | M | TC-INT-011, TC-OPS-006. | Test + Demo | TDD §20, §24 · `operations/recovery.md` |
| **NFR-023** | Schema migrations follow the expand/contract model with a backup first; a failed migration leaves the prior DB usable. | Platform P2 | M | Injected migration failure → original DB intact (TC-INT-012). | Test | TDD §16, §24 · `operations/macos-service.md` §13.3 |
| **NFR-024** | On SIGTERM the coordinator stops dispatch, interrupts non-adoptable runs, keeps adoptable runs, checkpoints and exits within `svc.exit_timeout_s` (internal budget `svc.shutdown_budget_s`). | Platform M1–M2; RD-11; RD-10 (D) | M | 10/10 trials within bounds; adoptable runs survive and are adopted on restart (TC-REC-007). | Test | TDD §18, §20 · `operations/macos-service.md` §12 |
| **NFR-025** | Full reconciliation of all non-terminal tasks completes within `recovery.reconcile_max_s` after `ready` or after wake + network (for ≤ 50 open tasks). | REL-02; RF-20 | M | `recovery.completed` duration within bound in TC-REC-004 and TC-REC-003. | Test | TDD §20 · parameter table |
| **NFR-026** | Lost agent work (cost metric): 0 Codex/`verify`/`deps_install` runs lost on a coordinator crash (adoption); at most one re-run per lost step after reboot or power loss, classified `lost_by_host`. | REL-04/05; RD-11 | S | TC-REC-030/032 counts. | Test | TDD §20 · `ADR-020` |
| **NFR-027** | Crash-loop containment: more than `svc.crash_loop_starts` within `svc.crash_loop_window_min` → safe mode (no dispatch, heartbeat `degraded`). | REL-15 | M | TC-REC-036. | Test | TDD §18 · parameter table |

### NFR — Latency while awake (measured per §1.5)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-040** | A relevant Linear change is observed within p95 ≤ 2 min, max ≤ 5 min. | NFR-LAT-03 | S | TC-PERF-002 over ≥ 100 sandbox changes. | Test | TDD §12, §23 · `integrations/linear.md` |
| **NFR-041** | GitHub review, check and merge events for active PRs are observed within p95 ≤ 120 s. | Platform E1 | S | TC-PERF-002 over ≥ 100 sandbox events. | Test | TDD §15, §23 · `integrations/github.md` §7 |
| **NFR-042** | Authorization recorded → Codex planning started: p95 ≤ 30 s, max ≤ 120 s (slot free). | NFR-LAT-01 | S | TC-PERF-003. | Test | TDD §8, §23 · `architecture/components.md` §7 |
| **NFR-043** | `MERCURY / claude-review` success → operator review requested: p95 ≤ 2 min, max ≤ 5 min. | NFR-LAT-04 | S | Sandbox measurement (TC-SBX-006). | Test | TDD §15, §21 · `integrations/github.md` §6 |
| **NFR-044** | Human merge → merge verified and Linear updated: p95 ≤ 5 min. | NFR-LAT-05; SAC-10 | S | Sandbox measurement (TC-SBX-004). | Test | TDD §15, §12 · `integrations/github.md` §8 |
| **NFR-045** | Plan approval recorded → implementation started: p95 ≤ 30 s, max ≤ 120 s. | NFR-LAT-02 | S | TC-PERF-003. | Test | TDD §8, §23 · `architecture/components.md` §7 |

### NFR — Durability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-050** | Committed state transitions survive power loss: SQLite WAL, `synchronous=FULL`, `fullfsync=ON`, verified by the startup self-check. | Fact 11 | M | Self-check refuses other values; TC-REC-002/020: 0 lost commits. | Inspection + Test | TDD §16, §20 · `operations/recovery.md` |
| **NFR-051** | Artifacts and run records (`exit.json`, `proc.json`) are written atomically (write, fsync, rename, directory fsync) and hash-verified on read. | Baseline; RD-11 | M | Crash mid-write leaves no partial file visible (TC-UNIT-031, TC-REC-034). | Test | TDD §16 · `ADR-020` |
| **NFR-052** | `quick_check` at startup and `integrity_check` daily, run in a worker thread with its own read connection; failure → safe mode and an alert. | Platform P2; RD-11 | M | Corrupted DB fixture → safe mode + notification (TC-REC-008); event-loop lag during the check within TC-PERF-006 bound. | Test | TDD §16, §20 · `operations/macos-service.md` §14 |
| **NFR-053** | Git durability ordering: mirror `core.fsync=committed,reference`; git commit → fsync → DB transaction recording the SHA; recovery verifies `git cat-file -e` and refs, else classifies `lost_by_host` and replays from the last durable commit. | RD-11; RD-05 (D) | M | TC-REC-034 and TC-REC-020 (VM power loss): DB never references a missing object or ref. | Test | TDD §16, §20 · `ADR-020`; `architecture/components.md` §9.2 |

### NFR — Auditability and notifications

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-060** | 100 % of state transitions, agent runs and external writes have audit events with correlation IDs; a task's history is reconstructable from the audit log alone; the chain verifies. | Area I | M | Audit-completeness checker over the E2E corpus: 0 gaps (TC-SM-003, TC-E2E-010). | Test | TDD §21 · `architecture/components.md` §4.16 |
| **NFR-061** | Retention (OD-15): audit events and decision artifacts ≥ 1 year; redacted transcripts 90 days; operational logs 90 days; debug logs 30 days (SEC-606); raw unredacted agent output is not persisted beyond run completion; deletion is audited. | RF-17 | S | Housekeeping test deletes only beyond retention; no raw output file exists after run completion (TC-OPS-008). | Inspection + Test | TDD §21 · `architecture/components.md` §6.5 |
| **NFR-062** | Logs are structured JSON (schema in `operations/macos-service.md` §11.1) and pass through the redactor (sinks accept only redacted types). | Area I | M | Log schema validation 100 %; canary test passes. | Test | TDD §21 · `architecture/components.md` §4.16 |
| **NFR-063** | Human-facing notifications per happy-path task ≤ 2 (review request; merge done). | NFR-NOT-02; RF-20 | S | E2E count (TC-E2E-001) and pilot analysis. | Test + Analysis | TDD §21 · `architecture/components.md` §4.15 |

### NFR — Operability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-070** | Install, upgrade and uninstall are each one documented command, render the plist, install the agent-uid wrappers and helpers idempotently, and are reversible. | §24; RD-1 | M | TC-OPS-001/012 on a clean account. | Demo | TDD §18, §24 · `operations/macos-service.md` §5, §13 |
| **NFR-071** | `mercury doctor`/`status` report poller lag, last poll per source, holds, DB status, agent CLI versions, governance status, agent-home credential scan and BTM state within 2 s. | Supervision | M | TC-OPS-002/013. | Test | TDD §21 · `architecture/components.md` §5.5 |
| **NFR-072** | Configuration is schema-validated at startup; invalid configuration prevents start with an actionable error. | Operability | M | TC-OPS-003: 10 invalid configs → 10 refusals with field paths. | Test | TDD §8, §24 · `architecture/components.md` §13 |
| **NFR-073** | A runbook exists for every escalation, block reason and alert class. | Area G | S | Runbook walkthrough per class (TC-OPS-004). | Demo + Inspection | TDD §20, §21 · `operations/recovery.md` |

### NFR — Resource usage and cost

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-080** | Idle coordinator ≤ 250 MB RSS and ≤ 2 % of one core averaged over 1 h (stretch: 200 MB / 1 %). | RF-04 | S | 24 h soak (TC-PERF-001). | Test | TDD §23 · `operations/macos-service.md` §10 |
| **NFR-081** | Non-304 GitHub reads ≤ 20 % of each identity's hourly primary limit at 10 active PRs; Linear ≤ 20 % of its limit; writes are capped by SEC-705. | RF-04 | M | TC-SBX-008, TC-NET-005. | Test | TDD §23 · `integrations/github.md` §15 |
| **NFR-082** | Dispatch holds and run interruption at the disk thresholds of the parameter table (`disk.*`). | Resource safety | S | TC-PERF-005, TC-REC-015. | Test | TDD §23 · parameter table |
| **NFR-083** | Per-run agent limits (Claude turns/budget; Codex tokens; awake-time deadline) and per-task budget totals are enforced and recorded. | Runtimes §1.9 | M | Exceeding a limit ends the run with a classified reason; cost/tokens per run recorded (TC-AFS-001). | Test | TDD §13, §14, §23 · `integrations/claude.md` §3.1 |
| **NFR-084** | A daily agent spend cap (OD-08) holds new dispatch when reached and notifies once. | RF-32 | S | E2E with fake costs: cap reached → `rate_limited`-class hold + 1 notification (TC-E2E-022). | Test | TDD §23 · `planning/roadmap.md` §7 (cost model) |
| **NFR-085** | Event-loop lag p99 ≤ 250 ms and SQLite commit p99 ≤ 50 ms under one Codex run plus a test run; no false sleep-gap detection from measured blocking operations. | RD-17 (D) | S | TC-PERF-004/006. | Test | TDD §23 · `architecture/components.md` §10.10 |

### NFR — Portability and version pinning

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-090** | Node.js, dependencies, Claude Code/Agent SDK and Codex CLI are pinned to exact versions and hashes (SEC-701); the startup self-test refuses mismatches. | Runtimes §6 | M | Self-test fails with a mismatched fake binary (TC-INT-013, TC-SEC-127). | Test | TDD §24 · `operations/macos-service.md` §13.5 |
| **NFR-091** | SQLite access sits behind a repository interface; the suite runs against both drivers. | Platform P3 | S | CI matrix passes for both. | Test | TDD §16 · `architecture/components.md` §4.3 |
| **NFR-092** | All MERCURY paths (`MERCURY_HOME`, `WORK_ROOT`, logs) are outside TCC-protected folders and need no Full Disk Access. | Platform M6; RD-2 | M | Install self-check rejects protected paths (P0-021, TC-OPS-001). | Test + Inspection | TDD §18 · `operations/macos-service.md` §7.1 |
| **NFR-093** | Agent CLI contract tests run against each pinned version before an upgrade is accepted. | Runtimes V6 | M | Upgrade blocked when the contract suite fails (TC-OPS-007). | Demo | TDD §24 · `integrations/codex.md` |
| **NFR-094** | Supported macOS versions are those verified in Phase 0; sandbox, agent-uid and launchd self-tests re-run after each macOS update. | Runtimes V8 | S | Self-test report per OS build. | Demo | TDD §18, §24 · `operations/macos-service.md` |
| **NFR-095** | The pinned-toolchain self-test at startup completes within 15 s. | NFR-MNT-01 | S | Startup log measurement (TC-INT-013). | Test | TDD §24 · `operations/macos-service.md` |

### NFR — Maintainability and testability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-100** | Claude, Codex, GitHub, Linear, clock, host events, process broker and spawner sit behind ports with fakes; state machine, guards and scheduler reach 100 % branch coverage, the rest ≥ 85 % lines. | Area J | S | CI coverage report. | Inspection | TDD §22 · `testing/verification-plan.md` §2.2 |
| **NFR-101** | Deterministic simulation (virtual clock in both monotonic modes, seeded randomness) for state-machine, recovery and concurrency tests; every sleep-related test runs in both modes. | Area J; RD-16 | M | Same seed → identical trace 100/100; CI shows both modes for each sleep test. | Test | TDD §22 · `testing/verification-plan.md` §2.2 |

### OPS — Operational requirements

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **OPS-001** | The Phase 0 register (`P0-nnn`) is executed and recorded before each milestone it gates. | Fact 1 | M | Phase 0 report with every check Pass/Fail/Accepted and evidence; §10.2 closure 0 Open at milestone entry. | Inspection | TDD §18, §27 · `operations/macos-service.md` Phase 0 checklist |
| **OPS-002** | Identities exist before any write integration: GitHub Apps `mercury-bot` (target repos: `contents:write`, `pull_requests:write`, `checks:write`, `statuses:read`, `metadata:read`, plus `statuses:write` only if P0-062 requires it; Addendum B.1) and `mercury-ops` (`issues:write` on `project-mercury`, `contents:write` on the private anchor repo, `metadata:read` on targets); Linear OAuth app `actor=app`; dedicated Anthropic and OpenAI keys with spend limits. Installation tokens are narrowed per purpose. | RD-6; RF-11 | M | Identity inventory equals this list (SAC-02, TC-GOV-112); no human credential anywhere. | Inspection + Test | TDD §15, §19 · `integrations/github.md` §2; `ADR-008` |
| **OPS-003** | Repository governance uses **rulesets** (not classic protection) per ADR-014 and is checked by the drift monitor at start, at every wake and at least every 60 min (SEC-108); drift raises a SECURITY alert and a global `security_halt`. | RB-16; RE-17; RF-11 | M | TC-GOV-115/115: relaxed rule detected ≤ 60 min, dispatch halted (SAC-09). | Test | TDD §15, §19 · `integrations/github.md` §9 |
| **OPS-004** | A dedicated sandbox GitHub repository and Linear team exist; no automated test may write to production repos or teams. | JAM-160 | M | Test allow-list contains only sandbox targets; CI guard fails on any other (TC-OPS-009). | Inspection + Test | TDD §22 · `testing/verification-plan.md` §2.3 |
| **OPS-005** | Upgrades (coordinator, Node, agent CLIs, wrappers, helpers) follow the documented procedure with backup, contract tests and rollback. | Version churn | M | Upgrade + rollback demo (TC-OPS-007). | Demo | TDD §24 · `operations/macos-service.md` §13 |
| **OPS-006** | Backup and restore procedures are documented and drilled at least quarterly. | Platform P2 | S | Drill log (TC-OPS-006). | Demo | TDD §20, §24 · `operations/recovery.md` |
| **OPS-007** | Secrets live in Keychain items with the single prefix `com.usjbro.mercury.*`, are read once at start and on `mercury reload-credentials`, and are held in memory; rotation per SEC-504. | RD-18 | M | TC-SEC-020; inventory matches `operations/macos-service.md` §9.1. | Inspection + Test | TDD §19 · `operations/macos-service.md` §9 |
| **OPS-008** | The pilot on `network_monitor` proceeds MIG-1 shadow → MIG-2 supervised → MIG-3 cutover → MIG-4 watch with the exit criteria in `planning/roadmap.md` §3 (OD-16). | ADR-012; RA-25; RF-18 | M | Exit criteria met and recorded (TC-PIL-001…004). | Demo + Analysis | TDD §27 · `planning/roadmap.md` |
| **OPS-009** | Slack decommission for MERCURY-managed work: disable `slack-notify.sh` paths, revoke the bot token, record the date. | Fact 12 | M | See FR-301. | Inspection | TDD §24 · `planning/roadmap.md` |
| **OPS-010** | Incident runbooks cover unauthorized merge, credential compromise, governance drift, chain failure and the ruleset-emergency procedure. | Area G | M | Tabletop walkthrough recorded (TC-OPS-004). | Demo | TDD §19, §20 · `operations/recovery.md` |
| **OPS-011** | Logs, artifacts, snapshots and worktrees are rotated/cleaned per retention without manual action. | NFR-061 | S | Housekeeping test (TC-OPS-008). | Test | TDD §21, §23 · `operations/macos-service.md` §10.5 |
| **OPS-012** | The operator is told (doctor + one notification) if the LaunchAgent is disabled in Login Items or not loaded. | Platform M7 | S | TC-REC-017. | Demo | TDD §18 · `operations/macos-service.md` §6 |
| **OPS-013** | Downtime awareness: `mercury-ops` heartbeat and an external GitHub Actions watchdog alert the operator when MERCURY is down with pending work, best effort p90 ≤ 75 min; a final `mode: sleeping` heartbeat from the sleep-notification helper switches the watchdog to the sleeping threshold (values in the parameter table). | REL-09; RD-16; RF-20 | M | TC-OPS-011: stopped daemon → alert; sleeping Mac → no alert. | Test | TDD §21 · `operations/macos-service.md` §11.6 |
| **OPS-014** | One-time root setup (operator-performed, Phase 0b) creates the agent uid `_mercuryagent`, group `mercury`, the root-owned `agent-exec`/`agent-ctl` wrappers, the restricted sudoers drop-in and `WORK_ROOT` ACLs; `doctor` verifies them on every start. | RD-1; RD-30 (D) | M | P0-026…032 pass; `doctor` detects each deliberate misconfiguration (TC-OPS-012). | Test + Inspection | TDD §18 · `operations/macos-service.md` agent-uid design; `ADR-013` |
| **OPS-015** | Per-repo toolchains are provisioned by `mercury toolchain sync` into `WORK_ROOT/toolchains` (coordinator-owned, agent read/execute only); the agent `HOME` holds caches only and is scanned for credential files. | RD-1; RD-26 (D) | M | P0-032 and TC-INT-028: target test suite passes as the agent uid; doctor flags a planted credential file (TC-OPS-013). | Test | TDD §18 · `operations/macos-service.md` §7 |
| **OPS-016** | Target-repository onboarding verifies: ruleset per ADR-014 (PR, 1 approval, Code Owner review, last-push approval, dismiss stale, no bypass, block force-push/deletion), CODEOWNERS = operator only, `allow_auto_merge=false`, both MERCURY checks required and pinned to the App, CI on draft PRs, toolchain manifest. | RD-5; RD-18 | M | `mercury repo check` passes on sandbox and `network_monitor` (TC-OPS-016, SEC-T-10). | Test | TDD §15 · `integrations/github.md` §9 |
| **OPS-017** | Each repository's governance mode and, for G-DETECT, the operator's written risk acceptance are recorded in config and audit before dispatch; unattended dispatch to a target requires G-ORG. | RD-5; CON-014 | M | Dispatcher refuses an unrecorded mode and unattended dispatch to a non-G-ORG target (TC-E2E-021). | Test + Inspection | TDD §15 · `ADR-014` |
| **OPS-018** | Signed helpers (LocalAuthentication presence helper; sleep/wake notification helper) are installed, code-signature-verified at start, and their absence degrades safely (presence commands refused; watchdog uses the awake threshold only). | RD-12; RD-16 | M | TC-OPS-012 and TC-SEC-145: missing/unsigned helper → presence commands refused, alert raised. | Test | TDD §18 · `operations/macos-service.md` §3.5 |
| **OPS-019** | The operator completes the OD-35 policy checklist (2FA; no plaintext classic PAT; Linear coding sessions and agent triage automations off; Actions settings per SEC-105; leaked Slack token rotated; interactive agents restricted from `gh pr review --approve`/`gh pr merge`; Linear write connectors acting as the human removed) with evidence before G-S1. | SEC-106/804/806; RD-12 | M | Evidence recorded per item (P0-074). | Inspection | TDD §19 · `security/threat-model.md` §6 |

---

## 4. Security requirements registry (E's IDs)

### 4.1 Registered SEC requirements

E owns each statement, level, tag and verification method in `security/threat-model.md` §5.1. This table registers each ID for traceability only: MUST → priority **M (release-blocking)**, SHOULD → **S** (F-SEC-1). The topic column is a navigation label, not the requirement. Test and milestone mappings are in the RTM (§6.2).

| SEC | Pri | Topic label | SEC | Pri | Topic label |
|---|---|---|---|---|---|
| SEC-100 | M | Ruleset on protected branches | SEC-315 | M | Bounded loops |
| SEC-101 | M | App permission sets | SEC-316 | M | Revision provenance |
| SEC-102 | M | Endpoint allowlist; COMMENT only | SEC-401 | M | Hardened git invocation |
| SEC-103 | M | Human credentials absent | SEC-402 | M | Git config and pointer verification |
| SEC-104 | M | CODEOWNERS operator only | SEC-403 | M | Committed-tree checks |
| SEC-105 | M | Repository and Actions settings | SEC-404 | M | No-follow coordinator reads |
| SEC-106 | M | Operator account and agent policy | SEC-405 | M | Layout properties |
| SEC-107 | M | Act only on own PRs | SEC-406 | M | Safe removal |
| SEC-108 | M | Governance drift monitor | SEC-407 | M | Push from mirror |
| SEC-109 | M | Merge-actor enforcement | SEC-501 | M | Redaction at every sink |
| SEC-110 | S | Separate author/review identities | SEC-502 | M | Pre-push secret scan |
| SEC-111 | M | Bot commit identity and trailers | SEC-503 | M | Keychain custody |
| SEC-112 | S | Tag ruleset | SEC-504 | M | Rotation |
| SEC-113 | M | Required MERCURY check runs | SEC-505 | M | Masked run records; raw output lifetime |
| SEC-114 | M | Draft until Claude passes | SEC-506 | S | GitHub secret scanning |
| SEC-115 | M | Operator-presence tier | SEC-507 | M | Publication (disclosure) policy |
| SEC-201 | M | Agent process isolation (agent uid) | SEC-601 | M | Security event audit |
| SEC-202 | M | Agent environment allowlist | SEC-602 | M | Hash chain |
| SEC-203 | M | Per-task generated `CODEX_HOME` | SEC-603 | S | HMAC on authority rows |
| SEC-204 | M | Claude run profiles | SEC-604 | M | Off-host anchoring |
| SEC-205 | M | Review snapshots | SEC-605 | M | `audit verify` |
| SEC-206 | S | Agent egress control | SEC-606 | S | Log retention |
| SEC-207 | M | Per-run scratch | SEC-607 | M | Restore epochs |
| SEC-208 | M | Forbidden Codex flags | SEC-701 | M | Pinned agent binaries |
| SEC-209 | M | Instruction-file integrity | SEC-702 | M | Dependency-change escalation |
| SEC-210 | M | Pinned binaries and TCB | SEC-703 | M | Controlled dependency install |
| SEC-211 | S | Codex network off | SEC-704 | M | Resource limits |
| SEC-212 | M | Wrapper contract | SEC-705 | M | External write budgets |
| SEC-213 | M | Cross-run isolation | SEC-706 | M | MERCURY's own dependencies |
| SEC-214 | M | Supervised lifetime | SEC-707 | S | Target workflow hygiene |
| SEC-215 | M | `verify`/`deps_install` profiles | SEC-708 | M | Toolchain provisioning |
| SEC-301 | M | Provenance tagging | SEC-801 | M | Linear `actor=app` |
| SEC-302 | M | Text is never authority | SEC-802 | M | No MCP/connectors in runs |
| SEC-303 | M | Strict schemas | SEC-803 | M | Delegation, coding session, foreign PR block |
| SEC-304 | M | Free text display-only; neutraliser | SEC-804 | M | Coding sessions off (policy) |
| SEC-305 | M | Decision constraints in code | SEC-805 | M | Linear endpoint allowlist |
| SEC-306 | M | Plan approval binding | SEC-806 | M | Legacy decommission |
| SEC-307 | M | Spec drift | SEC-901 | M | SECURITY notifications |
| SEC-308 | M | PR review binding | SEC-902 | M | Kill switch |
| SEC-309 | M | Deterministic pre-checks | SEC-903 | M | Sandbox-violation signals |
| SEC-310 | M | Block vs escalate; policy acknowledgement | SEC-904 | M | Re-check before review request |
| SEC-311 | M | Prompt-injection suite | SEC-905 | M | Merge verification |
| SEC-312 | M | Bidi / invisible characters | SEC-906 | M | `security_halt` scoping |
| SEC-313 | M | Revision-input allowlist | SEC-907 | M | Ops-channel hardening |
| SEC-314 | M | Role separation; security review every PR | SEC-908 | M | Fail-closed startup |

SEC-603 is SHOULD (RD-4, E revision). New in E's Phase 4 revision: SEC-113…115, SEC-212…215, SEC-316, SEC-407, SEC-507, SEC-607, SEC-708, SEC-906…908.

### 4.2 Retired F reservation `SEC-001…099`

| Retired anchor | Scope | Maps to E IDs |
|---|---|---|
| SEC-001 | Identity and authN | SEC-103, SEC-106, SEC-111, SEC-801 |
| SEC-010 | AuthZ and least privilege | SEC-101, SEC-107, SEC-110, SEC-805 |
| SEC-020 | Credentials and redaction | SEC-501…506 |
| SEC-030 | Execution isolation | SEC-201…211, SEC-401…406 |
| SEC-040 | Untrusted content / prompt injection | SEC-301…315, SEC-802 |
| SEC-050 | Human approval and merge governance | SEC-100, SEC-102, SEC-104, SEC-105, SEC-108, SEC-109, SEC-112, SEC-904, SEC-905 |
| SEC-060 | Audit integrity | SEC-601…606 |
| SEC-070 | Supply chain | SEC-701…707 |
| SEC-080 | Security review and escalation | SEC-309, SEC-310, SEC-314, SEC-803, SEC-806, SEC-901…903 |

`SEC-0nn` IDs are never reused. Documents that cite them (Phase 2 F report App. C, earlier RTM) are superseded by this table.

---

## 5. ADR registry

### 5.1 Final ADRs (A owns numbering and text)

| ADR | Decision | Main requirements |
|---|---|---|
| ADR-001 | Coordinator runtime: Node.js LTS + TypeScript | NFR-080, NFR-090, NFR-091 |
| ADR-002 | SQLite WAL store, single writer | FR-043, FR-048, FR-063, FR-081, NFR-001, NFR-020, NFR-022, NFR-023, NFR-050, NFR-052, NFR-091 |
| ADR-003 | Coordinator-mediated agent communication (SQLite + JSON artifacts) | FR-060, FR-061, FR-063, FR-064 |
| ADR-004 | Claude invocation (Agent SDK, isolated profile, agent-uid custom spawn; ALT-B-1 fallback) | FR-020, FR-062, FR-101, FR-160, NFR-090 |
| ADR-005 | Codex invocation (supervised `codex exec`, per-task `CODEX_HOME`, fresh implementation thread; dependency installation outside Codex) | CON-016, FR-062, FR-100, FR-103, FR-121, FR-123 |
| ADR-006 | Coordinator owns git and PR | FR-124, FR-140 |
| ADR-007 | Polling over webhooks | CON-002, FR-001, FR-901, NFR-005, NFR-040, NFR-041, NFR-081 |
| ADR-008 | Identity inventory (`mercury-bot`, `mercury-ops`, Linear app, model keys) | CON-008, FR-140, FR-162, FR-201, OPS-002 |
| ADR-009 | System-of-record split; Linear modes | FR-005, FR-183, FR-200, FR-904 |
| ADR-010 | LaunchAgent in the operator's GUI session | CON-002, CON-009, FR-903, NFR-002, NFR-024, NFR-070, OPS-012 |
| ADR-011 | Immutable, hash-bound authorization and approval records | CON-003…006, FR-021…024, FR-102, FR-203 |
| ADR-012 | Migration from the Slack workflow (`MIG-0…4`) | FR-300, FR-301, OPS-008, OPS-009 |
| ADR-013 | Agent process isolation via `_mercuryagent`, `agent-exec`/`agent-ctl` | CON-018, FR-051, FR-055, FR-281, OPS-014, OPS-015 |
| ADR-014 | Merge governance modes and required MERCURY checks | CON-007, CON-014, FR-162, FR-166, FR-167, FR-180…182, OPS-003, OPS-016, OPS-017 |
| ADR-015 | Holds vs `BLOCKED`; derived queue | FR-040, FR-047, FR-050, FR-243 |
| ADR-016 | Filesystem layout (`MERCURY_HOME`, `WORK_ROOT`, logs) | FR-064, FR-120, FR-184, NFR-092 |
| ADR-017 | Claude reads git-object snapshots | FR-066, FR-160 |
| ADR-018 | Audit integrity (chain MUST, anchoring MUST, HMAC SHOULD, restore epoch) | FR-262, FR-263, FR-264, NFR-060 |
| ADR-019 | Operator-presence tier; notification and operator-response channels | CON-003, CON-011, FR-220, FR-224, FR-241, FR-242, OPS-018 |
| ADR-020 | Crash adoption, lost runs and durability | FR-053…055, FR-280, NFR-024, NFR-026, NFR-051, NFR-053 |

### 5.2 Retired provisional keys

| Retired key | Final ADR |
|---|---|
| ADR-P01 runtime | ADR-001 |
| ADR-P02 store/queue | ADR-002 (store); ADR-015 (derived queue) |
| ADR-P03 polling | ADR-007 |
| ADR-P04 identities | ADR-008 |
| ADR-P05 merge governance | ADR-014 (ADR-008 keeps the identity inventory) |
| ADR-P06 coordinator owns git | ADR-006 |
| ADR-P07 Claude invocation | ADR-004 |
| ADR-P08 Codex invocation | ADR-005 |
| ADR-P09 LaunchAgent / sleep-tolerant timers | ADR-010; ADR-020 (adoption) |
| ADR-P10 Linear status ownership | ADR-009 (with OD-06) |
| ADR-P11 authorization records | ADR-011 |
| ADR-P12 notifications | ADR-019 |
| ADR-P13 communication | ADR-003 |
| ADR-P14 dependency install | ADR-005 (with SEC-703) |
| ADR-P15 filesystem layout | ADR-016 |

---

## 6. Requirements Traceability Matrix

Columns: requirement → ADR(s) → test case(s) → milestone where first verified → status. Design pointers are in the requirement rows (§3) to avoid restating them. Status values: **BC** = baseline candidate (§1.4). Milestone keys are defined in `planning/roadmap.md`.

### 6.1 CON / FR / NFR / OPS

| Req | Pri | ADR(s) | Test case(s) | Milestone | Status |
|---|---|---|---|---|---|
| CON-001 | M | — | TC-OPS-010 | P0d | BC |
| CON-002 | M | ADR-007, ADR-010 | TC-OPS-001, TC-SEC-008 | M1 | BC |
| CON-003 | M | ADR-011, ADR-019 | TC-SM-004, TC-INT-024, TC-SEC-145 | M1 | BC |
| CON-004 | M | ADR-011 | TC-SM-004, TC-E2E-006, TC-SBX-001 | M2 | BC |
| CON-005 | M | ADR-011 | TC-UNIT-011, TC-SM-004 | M3 | BC |
| CON-006 | M | ADR-011 | TC-UNIT-012, TC-SM-007 | M4 | BC |
| CON-007 | M | ADR-008, ADR-014 | TC-GOV-117, TC-GOV-118, TC-PI-138, TC-GOV-110, TC-GOV-116 | P0c / M6 | BC |
| CON-008 | M | ADR-008 | TC-SBX-002, TC-SBX-005, TC-SEC-113, P0-060 | P0c | BC |
| CON-009 | M | ADR-010, ADR-020 | TC-SM-009, TC-REC-003, TC-REC-021, TC-REC-031 | M1 / M8 | BC |
| CON-010 | M | — | TC-SEC-004, TC-OPS-009 | M1 | BC |
| CON-011 | M | ADR-019 | TC-SBX-006 | M7 | BC |
| CON-012 | M | — | TC-SM-008, TC-E2E-003 | M4 | BC |
| CON-013 | M | — | TC-UNIT-061, TC-E2E-001 | M1 | BC |
| CON-014 | M | ADR-014 | TC-GOV-004, TC-OPS-005, TC-E2E-021 | M7 / M9c | BC |
| CON-015 | M | — | P0-001, TC-OPS-010 | P0a | BC |
| CON-016 | M | ADR-005 | TC-INT-005, TC-E2E-014 | M4 | BC |
| CON-017 | M | — | TC-OPS-010 | P0d | BC |
| CON-018 | M | ADR-013 | TC-UNIT-072, TC-SEC-120 | M4 (G-S2) | BC |
| FR-001 | M | ADR-007 | TC-INT-001, TC-SBX-001, TC-DUP-001, TC-DUP-006, TC-CON-007 | M2 | BC |
| FR-002 | M | — | TC-UNIT-001, TC-E2E-006 | M2 | BC |
| FR-003 | M | — | TC-UNIT-002 | M2 | BC |
| FR-004 | M | — | TC-UNIT-003, TC-E2E-011 | M2 | BC |
| FR-005 | M | ADR-009 | TC-E2E-014, TC-SEC-181 | M2 | BC |
| FR-006 | C | — | TC-UNIT-004 | M3 | BC |
| FR-007 | M | ADR-015 | TC-UNIT-005, TC-INT-030 | M2 | BC |
| FR-008 | M | ADR-009 | TC-E2E-017 | M2 | BC |
| FR-020 | M | ADR-004 | TC-CON-003, TC-E2E-001 | M3 | BC |
| FR-021 | M | ADR-011 | TC-UNIT-010, TC-INT-020 | M1 / M3 | BC |
| FR-022 | M | ADR-011 | TC-UNIT-011, TC-SM-004, TC-REC-038 | M3 | BC |
| FR-023 | M | ADR-011 | TC-E2E-007 | M5 | BC |
| FR-024 | M | ADR-011 | TC-UNIT-013, TC-SM-015, TC-E2E-008, TC-E2E-020 | M3 / M6 | BC |
| FR-040 | M | ADR-015 | TC-INT-003, TC-CONC-004, TC-SM-004 | M1 | BC |
| FR-041 | M | — | TC-UNIT-022, TC-CONC-001, TC-CONC-002, P0-038 | M1 | BC |
| FR-042 | S | — | TC-UNIT-022 | M1 | BC |
| FR-043 | M | ADR-002 | TC-DUP-003, TC-REC-001, TC-CON-015 | M1 | BC |
| FR-044 | M | ADR-013 | TC-UNIT-021, TC-INT-005, TC-AFS-002, TC-AFS-004, TC-AFS-009 | M1 / M4 | BC |
| FR-045 | M | — | TC-UNIT-020, TC-AFS-001, TC-AFS-003, TC-AFS-006 | M1 | BC |
| FR-046 | M | — | TC-SM-010 | M1 | BC |
| FR-047 | M | ADR-015 | TC-SM-011 | M1 | BC |
| FR-048 | M | ADR-002 | TC-INT-004, TC-CONC-003 | M1 | BC |
| FR-049 | M | — | TC-INT-010 | M1 | BC |
| FR-050 | M | ADR-015 | TC-SM-012, TC-SM-013, TC-SM-014 | M1 | BC |
| FR-051 | M | ADR-013 | TC-INT-025, TC-SEC-128, P0-026, P0-028 | P0b / M1 | BC |
| FR-052 | M | ADR-020 | TC-SM-023, TC-REC-012 | M1 / M8 | BC |
| FR-053 | M | ADR-020 | TC-REC-032 | M1 | BC |
| FR-054 | M | ADR-020 | TC-REC-030, TC-REC-038, TC-AFS-010 | M1 / M4 | BC |
| FR-055 | M | ADR-020 | TC-REC-033 | M1 | BC |
| FR-060 | M | ADR-003 | TC-UNIT-030, TC-CON-001 | M1 | BC |
| FR-061 | M | ADR-003 | TC-CON-001 | M1 | BC |
| FR-062 | M | ADR-004, ADR-005 | TC-CON-003, TC-CON-005, TC-CON-014, TC-AFS-005, TC-AFS-011, P0-050 | M3 | BC |
| FR-063 | M | ADR-002, ADR-003 | TC-INT-003, TC-DUP-003 | M1 | BC |
| FR-064 | M | ADR-003, ADR-016 | TC-UNIT-031 | M1 | BC |
| FR-065 | S | — | TC-CON-002 | M8 | BC |
| FR-066 | M | ADR-017 | TC-SEC-124, TC-E2E-001 | M3 | BC |
| FR-080 | M | — | TC-SM-001, TC-SM-002 | M1 | BC |
| FR-081 | M | ADR-002 | TC-SM-003, TC-SM-019 | M1 | BC |
| FR-082 | M | ADR-010 | TC-UNIT-062, TC-SM-009 | M1 | BC |
| FR-083 | M | — | TC-SM-006 | M1 | BC |
| FR-084 | M | — | TC-SM-005 | M1 | BC |
| FR-085 | M | ADR-020 | TC-SM-021, TC-REC-021, TC-REC-039 | M1 / M7 | BC |
| FR-100 | M | ADR-005 | TC-CON-005, TC-INT-026, TC-E2E-001 | M4 | BC |
| FR-101 | M | ADR-004 | TC-CON-003, TC-E2E-002 | M4 | BC |
| FR-102 | M | ADR-011 | TC-SM-007, TC-SM-026, TC-UNIT-012 | M4 | BC |
| FR-103 | M | ADR-005 | TC-E2E-002 | M4 | BC |
| FR-104 | M | — | TC-SM-008, TC-E2E-003 | M4 | BC |
| FR-105 | M | — | TC-E2E-012 | M4 | BC |
| FR-106 | M | — | TC-UNIT-012, TC-E2E-004 | M4 | BC |
| FR-120 | M | ADR-016 | TC-UNIT-040, TC-INT-006 | M4 | BC |
| FR-121 | M | ADR-005 | TC-UNIT-011, TC-UNIT-012, TC-E2E-001 | M5 | BC |
| FR-122 | M | ADR-013 | TC-INT-008, TC-SEC-125 | M5 | BC |
| FR-123 | M | ADR-005 | TC-INT-009, TC-SEC-125, TC-SEC-171 | M5 | BC |
| FR-124 | M | ADR-006 | TC-UNIT-043, TC-AFS-007, TC-PI-138 | M5 | BC |
| FR-125 | M | — | TC-CON-004, TC-AFS-004 | M4 | BC |
| FR-126 | M | ADR-020 | TC-REC-037 | M4 | BC |
| FR-140 | M | ADR-006, ADR-008 | TC-INT-007, TC-INT-027, TC-SBX-002, TC-SEC-140, TC-SEC-141 | M5 | BC |
| FR-141 | S | — | TC-UNIT-041 | M5 | BC |
| FR-142 | M | ADR-009, ADR-014 | TC-UNIT-042, TC-SBX-002, TC-E2E-019, TC-SEC-153 | M5 / M6 | BC |
| FR-143 | M | — | TC-DUP-004, TC-NET-002, TC-REC-001 | M5 | BC |
| FR-144 | M | ADR-014 | TC-E2E-005, TC-INT-002, TC-INT-029 | M6 | BC |
| FR-145 | M | ADR-014 | TC-OPS-016, P0-071 | P0c / M9a | BC |
| FR-160 | M | ADR-004, ADR-017 | TC-CON-003, TC-E2E-004 | M6 | BC |
| FR-161 | M | — | TC-E2E-012 | M6 | BC |
| FR-162 | M | ADR-014 | TC-SBX-003, TC-CON-012, TC-GOV-118 | M6 | BC |
| FR-163 | M | — | TC-E2E-004, TC-E2E-018, TC-SM-008, TC-SM-020 | M6 | BC |
| FR-164 | M | ADR-019 | TC-SBX-006 | M6 | BC |
| FR-165 | M | — | TC-E2E-013, TC-SM-025 | M6 | BC |
| FR-166 | M | ADR-014 | TC-GOV-117, TC-E2E-019, P0-062 | M6 | BC |
| FR-167 | M | ADR-014, ADR-019 | TC-PI-138, TC-SM-016, TC-SEC-145 | M5 | BC |
| FR-168 | M | — | TC-SEC-154 | M6 | BC |
| FR-180 | M | ADR-014 | TC-GOV-005, TC-GOV-111, TC-GOV-112 | M5 | BC |
| FR-181 | M | ADR-014 | TC-UNIT-052, TC-SBX-004, TC-CON-006 | M7 | BC |
| FR-182 | M | ADR-014 | TC-GOV-004, TC-SM-017, TC-SM-018 | M7 | BC |
| FR-183 | M | ADR-009 | TC-E2E-015, TC-E2E-016, TC-SBX-004, TC-SBX-009 | M7 | BC |
| FR-184 | S | ADR-016 | TC-INT-006, TC-SEC-143 | M7 | BC |
| FR-185 | S | — | TC-E2E-009 | M7 | BC |
| FR-200 | M | ADR-009 | TC-UNIT-050 | M7 | BC |
| FR-201 | M | ADR-008 | TC-SBX-005, P0-061 | P0c / M7 | BC |
| FR-202 | M | — | TC-NET-003, TC-DUP-001, TC-UNIT-070 | M7 | BC |
| FR-203 | M | ADR-011 | TC-GOV-006, TC-PI-131 | M3 | BC |
| FR-220 | M | ADR-019 | TC-SBX-006 | M7 | BC |
| FR-221 | M | — | TC-UNIT-051, TC-DUP-005 | M7 | BC |
| FR-222 | S | — | TC-REC-009 | M7 | BC |
| FR-223 | M | — | TC-NET-003 | M7 | BC |
| FR-224 | M | ADR-019 | TC-SEC-190 | M7 | BC |
| FR-240 | M | — | TC-INT-010 | M1 | BC |
| FR-241 | M | ADR-019 | TC-INT-010, TC-GOV-006 | M7 | BC |
| FR-242 | M | ADR-019 | TC-SEC-145 | M5 | BC |
| FR-243 | M | ADR-015 | TC-SEC-191 | M1 / M5 | BC |
| FR-260 | M | — | TC-E2E-010 | M7 | BC |
| FR-261 | M | — | TC-SM-003, TC-E2E-010 | M1 | BC |
| FR-262 | M | ADR-018 | TC-SEC-161 | M1 / M7 | BC |
| FR-263 | M | ADR-018 | TC-SEC-163 | M7 | BC |
| FR-264 | M | ADR-018 | TC-REC-019, TC-SM-022 | M7 | BC |
| FR-280 | M | ADR-020 | TC-REC-001, TC-REC-004, TC-REC-035 | M1 | BC |
| FR-281 | M | ADR-013 | TC-REC-005 | M1 | BC |
| FR-282 | M | ADR-010, ADR-020 | TC-UNIT-062, TC-SM-009, TC-REC-031, TC-REC-003, TC-NET-004 | M1 / M8 | BC |
| FR-283 | M | — | TC-NET-001, TC-NET-002, TC-NET-003, TC-NET-006, TC-NET-008 | M2 | BC |
| FR-300 | M | ADR-012 | TC-PIL-002, P0-073 | M9a | BC |
| FR-301 | M | ADR-012 | TC-PIL-003 | M9c | BC |
| FR-900 | W | ADR-019 | TC-SEC-008 | M8 | BC |
| FR-901 | W | ADR-007 | TC-SEC-008 | M8 | BC |
| FR-902 | W | ADR-014 | TC-GOV-005 | M5 | BC |
| FR-903 | W | ADR-010 | TC-INT-004 | M1 | BC |
| FR-904 | W | ADR-009 | TC-E2E-014 | M2 | BC |
| FR-905 | W | ADR-019 | TC-GOV-006 | M7 | BC |
| NFR-001 | M | ADR-002 | TC-REC-001 | M1 (200 runs) / M8 (1,000) | BC |
| NFR-002 | M | ADR-010 | TC-REC-006 | M8 | BC |
| NFR-003 | M | — | TC-AFS-002, TC-PIL-004 | M8 | BC |
| NFR-004 | S | — | TC-PIL-002, TC-PERF-007 | M9b | BC |
| NFR-005 | M | ADR-007 | TC-SBX-001, TC-NET-001, TC-DUP-002 | M8 | BC |
| NFR-006 | M | ADR-013 | TC-AFS-002, TC-AFS-009, TC-REC-005 | M4 | BC |
| NFR-007 | — | — | (retired → OPS-013) | — | Retired |
| NFR-008 | M | — | TC-PERF-007 | M8 | BC |
| NFR-020 | M | ADR-002 | TC-REC-002, TC-REC-004, TC-REC-008, TC-REC-020 | M8 | BC |
| NFR-021 | M | ADR-010 | TC-REC-003, TC-NET-004 | M8 | BC |
| NFR-022 | M | ADR-002 | TC-INT-011, TC-OPS-006 | M8 | BC |
| NFR-023 | M | ADR-002 | TC-INT-012 | M1 | BC |
| NFR-024 | M | ADR-020 | TC-REC-007 | M8 | BC |
| NFR-025 | M | — | TC-REC-003, TC-REC-004 | M8 | BC |
| NFR-026 | S | ADR-020 | TC-REC-030, TC-REC-032 | M8 | BC |
| NFR-027 | M | — | TC-REC-036 | M1 | BC |
| NFR-040 | S | ADR-007 | TC-PERF-002 | M2 | BC |
| NFR-041 | S | ADR-007 | TC-PERF-002 | M6 | BC |
| NFR-042 | S | — | TC-PERF-003 | M4 | BC |
| NFR-043 | S | ADR-019 | TC-SBX-006 | M7 | BC |
| NFR-044 | S | — | TC-SBX-004 | M7 | BC |
| NFR-045 | S | — | TC-PERF-003 | M5 | BC |
| NFR-050 | M | ADR-002 | TC-INT-013, TC-REC-002, TC-PERF-004 | M1 | BC |
| NFR-051 | M | ADR-020 | TC-UNIT-031, TC-REC-034 | M1 | BC |
| NFR-052 | M | ADR-002 | TC-REC-008, TC-PERF-006 | M1 | BC |
| NFR-053 | M | ADR-020 | TC-REC-034, TC-REC-020 | M5 / M8 | BC |
| NFR-060 | M | ADR-018 | TC-SM-003, TC-E2E-010 | M7 | BC |
| NFR-061 | S | — | TC-OPS-008 | M8 | BC |
| NFR-062 | M | — | TC-SEC-004, TC-SEC-150, TC-INT-010 | M1 | BC |
| NFR-063 | S | ADR-019 | TC-E2E-001 | M7 | BC |
| NFR-070 | M | ADR-010, ADR-013 | TC-OPS-001, TC-OPS-012 | M8 | BC |
| NFR-071 | M | — | TC-OPS-002, TC-OPS-013 | M2 | BC |
| NFR-072 | M | — | TC-UNIT-061, TC-OPS-003 | M1 | BC |
| NFR-073 | S | — | TC-OPS-004 | M8 | BC |
| NFR-080 | S | ADR-001 | TC-PERF-001 | M8 | BC |
| NFR-081 | M | ADR-007 | TC-SBX-008, TC-NET-005 | M8 | BC |
| NFR-082 | S | — | TC-PERF-005, TC-REC-015 | M8 | BC |
| NFR-083 | M | — | TC-AFS-001, TC-UNIT-021 | M3 | BC |
| NFR-084 | S | — | TC-E2E-022 | M9a | BC |
| NFR-085 | S | — | TC-PERF-004, TC-PERF-006 | M8 | BC |
| NFR-090 | M | ADR-001, ADR-004, ADR-005 | TC-INT-013, TC-CON-008, TC-SEC-127 | M1 | BC |
| NFR-091 | S | ADR-001, ADR-002 | TC-INT-003 | M1 | BC |
| NFR-092 | M | ADR-016 | P0-021, TC-OPS-001 | P0a / M1 | BC |
| NFR-093 | M | — | TC-CON-004, TC-CON-008, TC-OPS-007 | M8 | BC |
| NFR-094 | S | — | P0-001, TC-OPS-007 | M8 | BC |
| NFR-095 | S | — | TC-INT-013 | M1 | BC |
| NFR-100 | S | — | TC-UNIT-011, TC-UNIT-012 | M1 | BC |
| NFR-101 | M | — | TC-SM-005, TC-SM-009 | M1 | BC |
| OPS-001 | M | — | P0-001…052 | P0a / P0b | BC |
| OPS-002 | M | ADR-008 | P0-060, P0-061, TC-GOV-008, TC-GOV-112 | P0c | BC |
| OPS-003 | M | ADR-014 | TC-GOV-115, TC-OPS-005 | M2 / M5 | BC |
| OPS-004 | M | — | TC-OPS-009, TC-SBX-001 | P0c | BC |
| OPS-005 | M | — | TC-OPS-007 | M8 | BC |
| OPS-006 | S | — | TC-OPS-006 | M8 | BC |
| OPS-007 | M | — | P0-035, TC-SEC-020 | M1 | BC |
| OPS-008 | M | ADR-012 | TC-PIL-001, TC-PIL-002 | M9a / M9b | BC |
| OPS-009 | M | ADR-012 | TC-PIL-003 | M9c | BC |
| OPS-010 | M | — | TC-OPS-004 | M8 | BC |
| OPS-011 | S | — | TC-OPS-008, TC-PERF-005 | M8 | BC |
| OPS-012 | S | ADR-010 | TC-REC-017, TC-OPS-002 | M8 | BC |
| OPS-013 | M | ADR-019 | TC-OPS-011 | M7 | BC |
| OPS-014 | M | ADR-013 | P0-026, P0-027, TC-OPS-012 | P0b / M8 | BC |
| OPS-015 | M | ADR-013 | P0-032, TC-INT-028, TC-OPS-013 | M5 | BC |
| OPS-016 | M | ADR-014 | TC-OPS-016, TC-GOV-110 | P0c / M9a | BC |
| OPS-017 | M | ADR-014 | TC-E2E-021, TC-OPS-005 | M5 / M9c | BC |
| OPS-018 | M | ADR-019 | TC-OPS-012, TC-SEC-145 | M5 / M7 | BC |
| OPS-019 | M | — | P0-074 | P0c | BC |

### 6.2 SEC (E's statements; F's traceability)

TC aliases of E's `SEC-T-nn` follow §8.3 (TC-SEC-1nn, TC-GOV-11n, TC-PI-13n). "Gate" is E's gate (G-S1…G-S5, `security/threat-model.md` §8.10) that requires the SEC, with the SAC that measures it.

| SEC | Pri | ADR(s) | Test case(s) | Milestone | Gate |
|---|---|---|---|---|---|
| SEC-100 | M | ADR-014 | TC-GOV-110, TC-GOV-116, TC-OPS-016 | P0c (sandbox) / M9a (targets) | G-S3 |
| SEC-101 | M | ADR-008 | TC-GOV-112, TC-GOV-008, P0-060 | P0c | G-S3 (SAC-02) |
| SEC-102 | M | ADR-014 | TC-GOV-111, TC-CON-012 | M5 | G-S3 |
| SEC-103 | M | ADR-013 | TC-SEC-113, TC-SEC-120 | P0b | G-S2 |
| SEC-104 | M | ADR-014 | TC-GOV-110 | P0c | G-S3 |
| SEC-105 | M | ADR-014 | TC-SEC-114 | P0c | G-S3 |
| SEC-106 | M | — | P0-074 | P0c | G-S1 |
| SEC-107 | M | — | TC-UNIT-053 | M5 | G-S3 |
| SEC-108 | M | ADR-014 | TC-GOV-115 | M2 (read) / M5 (halt) | G-S4 (SAC-09) |
| SEC-109 | M | ADR-014 | TC-GOV-116, TC-GOV-004, TC-E2E-021 | M7 / M9c | G-S4 (mode), G-S5 (G-ORG) |
| SEC-110 | S | ADR-008 | TC-GOV-112 | M8 | — |
| SEC-111 | M | — | TC-UNIT-041 | M5 | G-S3 |
| SEC-112 | S | — | TC-GOV-110 | M8 | — |
| SEC-113 | M | ADR-014 | TC-GOV-117, TC-PI-138, TC-E2E-019 | M5 (policy) / M6 (claude-review) | G-S3 (SAC-16, SAC-17) |
| SEC-114 | M | ADR-014 | TC-E2E-019 | M6 | G-S3 |
| SEC-115 | M | ADR-019 | TC-SEC-145, P0-045 | M5 | G-S4 (SAC-15) |
| SEC-201 | M | ADR-013 | TC-SEC-120, P0-026…032 | P0b / M4 | G-S2 (SAC-05) |
| SEC-202 | M | ADR-013 | TC-SEC-121 | M3 | G-S2 (SAC-13) |
| SEC-203 | M | ADR-005 | TC-INT-026, TC-SEC-122 | M4 | G-S1 |
| SEC-204 | M | ADR-004 | TC-SEC-103, TC-SEC-123, TC-SEC-006 | M3 | G-S1 (SAC-03) |
| SEC-205 | M | ADR-017 | TC-SEC-124 | M3 | G-S3 |
| SEC-206 | S | ADR-013 | TC-SEC-125, P0-049 | M8 | — |
| SEC-207 | M | ADR-013 | TC-INT-025 | M3 | G-S2 |
| SEC-208 | M | ADR-005 | TC-SEC-122, P0-048 | M4 | G-S1 |
| SEC-209 | M | ADR-005 | TC-SEC-126 | M4 | G-S1 |
| SEC-210 | M | ADR-004, ADR-005 | TC-SEC-127 | M3 | G-S2 |
| SEC-211 | S | ADR-005 | TC-SEC-003 | M5 | — |
| SEC-212 | M | ADR-013 | TC-SEC-128 | M1 | G-S2 (SAC-14) |
| SEC-213 | M | ADR-013 | TC-SEC-194 | M4 | G-S2 |
| SEC-214 | M | ADR-020 | TC-SEC-129, TC-REC-033 | M1 | G-S2 (SAC-19) |
| SEC-215 | M | ADR-013 | TC-SEC-125, TC-SEC-171 | M5 | G-S2 (SAC-18) |
| SEC-301 | M | ADR-003 | TC-PI-130, TC-UNIT-073 | M3 | G-S4 (SAC-04) |
| SEC-302 | M | ADR-011 | TC-GOV-006, TC-PI-131 | M3 | G-S3 |
| SEC-303 | M | ADR-003 | TC-CON-001, TC-CON-014, TC-PI-132 | M3 | G-S1 |
| SEC-304 | M | — | TC-SEC-153 | M5 | G-S3 |
| SEC-305 | M | ADR-011 | TC-UNIT-011, TC-PI-133 | M3 | G-S3 (SAC-11) |
| SEC-306 | M | ADR-011 | TC-SM-007, TC-PI-134 | M4 | G-S3 (SAC-11) |
| SEC-307 | M | ADR-011 | TC-SM-015, TC-E2E-008, TC-PI-135 | M3 | G-S3 (SAC-11) |
| SEC-308 | M | ADR-014 | TC-SM-025, TC-PI-136 | M6 | G-S3 (SAC-11) |
| SEC-309 | M | ADR-014 | TC-UNIT-043, TC-PI-137 | M5 | G-S3 |
| SEC-310 | M | ADR-014 | TC-PI-138 | M5 | G-S3 (SAC-16) |
| SEC-311 | M | — | TC-PI-130 | M8 | G-S4 (SAC-04) |
| SEC-312 | M | — | TC-PI-139 | M5 | G-S3 |
| SEC-313 | M | — | TC-PI-131, TC-E2E-018 | M6 | G-S3 |
| SEC-314 | M | ADR-004 | TC-E2E-012 | M6 | G-S4 |
| SEC-315 | M | — | TC-SM-008 | M4 | G-S3 |
| SEC-316 | M | ADR-003 | TC-E2E-018, TC-PI-131 | M6 | G-S3 |
| SEC-401 | M | ADR-006 | TC-SEC-140 | M5 | G-S3 (SAC-07) |
| SEC-402 | M | ADR-006 | TC-SEC-141 | M5 | G-S3 (SAC-07) |
| SEC-403 | M | ADR-006 | TC-SEC-142 | M5 | G-S3 |
| SEC-404 | M | ADR-006 | TC-SEC-142 | M5 | G-S3 |
| SEC-405 | M | ADR-016 | TC-SEC-120, TC-OPS-001 | M1 | G-S2 |
| SEC-406 | M | ADR-016 | TC-SEC-143 | M7 | G-S5 |
| SEC-407 | M | ADR-006 | TC-SEC-144, TC-INT-027 | M5 | G-S3 (SAC-07) |
| SEC-501 | M | — | TC-SEC-150, TC-SEC-004 | M1 | G-S3 (SAC-06) |
| SEC-502 | M | ADR-006 | TC-SEC-151 | M5 | G-S3 (SAC-06) |
| SEC-503 | M | — | TC-SEC-020, TC-SEC-152, P0-035, P0-036 | M1 | G-S2 |
| SEC-504 | M | — | TC-OPS-004 | M8 | G-S5 |
| SEC-505 | M | — | TC-SEC-152, TC-OPS-008 | M3 | G-S3 |
| SEC-506 | S | — | TC-SEC-114 | P0c | — |
| SEC-507 | M | — | TC-SEC-154 | M6 | G-S4 (SAC-20) |
| SEC-601 | M | ADR-018 | TC-SM-003, TC-SEC-160 | M1 | G-S5 |
| SEC-602 | M | ADR-018 | TC-SEC-161 | M1 | G-S5 (SAC-08) |
| SEC-603 | S | ADR-018 | TC-SEC-162 | M7 | — |
| SEC-604 | M | ADR-018 | TC-SEC-163 | M7 | G-S5 |
| SEC-605 | M | ADR-018 | TC-SEC-161 | M7 | G-S5 (SAC-08) |
| SEC-606 | S | — | TC-OPS-008 | M8 | — |
| SEC-607 | M | ADR-018 | TC-SEC-164, TC-REC-019 | M7 | G-S5 (SAC-08) |
| SEC-701 | M | — | TC-SEC-127, TC-CON-008 | M1 | G-S2 |
| SEC-702 | M | ADR-014 | TC-SEC-170, TC-PI-138 | M5 | G-S3 |
| SEC-703 | M | ADR-005 | TC-SEC-171 | M5 | G-S2 (SAC-18) |
| SEC-704 | M | ADR-013 | TC-SEC-172, TC-AFS-004 | M1 | G-S2 |
| SEC-705 | M | — | TC-SEC-173 | M5 | G-S3 |
| SEC-706 | M | — | TC-OPS-009 | P0d | G-S1 |
| SEC-707 | S | — | TC-SEC-114 | M9a | — |
| SEC-708 | M | ADR-013 | TC-INT-028, P0-032 | M5 | G-S2 |
| SEC-801 | M | ADR-008 | TC-SEC-180, TC-SBX-005, P0-061 | P0c | G-S3 |
| SEC-802 | M | ADR-004 | TC-SEC-123, P0-042 | M3 | G-S1 |
| SEC-803 | M | — | TC-SEC-181, TC-E2E-014 | M2 | G-S4 |
| SEC-804 | M | — | P0-074 | P0c | G-S1 |
| SEC-805 | M | — | TC-UNIT-071, TC-SEC-180 | M7 | G-S4 |
| SEC-806 | M | ADR-012 | TC-PIL-003 | M9c | — |
| SEC-901 | M | ADR-019 | TC-SEC-190 | M7 | G-S4 |
| SEC-902 | M | ADR-015 | TC-SEC-191 | M1 / M5 | G-S3 |
| SEC-903 | M | — | TC-SEC-192 | M5 | G-S3 |
| SEC-904 | M | ADR-014 | TC-UNIT-054, TC-E2E-019 | M6 | G-S4 |
| SEC-905 | M | ADR-014 | TC-SEC-193, TC-GOV-004 | M7 | G-S4 (SAC-10) |
| SEC-906 | M | ADR-015 | TC-SEC-191, TC-SM-017 | M5 / M7 | G-S5 |
| SEC-907 | M | ADR-019 | TC-SEC-190 | M7 | G-S4 |
| SEC-908 | M | ADR-020 | TC-SEC-161, TC-REC-035 | M1 | G-S5 |

### 6.3 Coverage summary

Counted from §3 and §4.1 (`Retired` rows excluded; NFR-007 is retired).

| Type | Count | M | S | C | W |
|---|---|---|---|---|---|
| CON | 18 | 18 | 0 | 0 | 0 |
| FR | 107 | 94 | 6 | 1 | 6 |
| NFR | 47 | 28 | 19 | 0 | 0 |
| OPS | 19 | 16 | 3 | 0 | 0 |
| SEC (E) | 90 | 82 | 8 | 0 | 0 |
| **Total** | **281** | **238** | **36** | **1** | **6** |

Checks run while generating this file (repeatable by the ID lint, TC-OPS-010):
- Every `TC-*` and `P0-*` cited in the RTM is defined in `testing/verification-plan.md` §8.
- Every defined, non-retired `TC-*` covers at least one requirement in this file.
- No requirement ID is duplicated; every ADR cited exists in §5.1.

---

## 7. Operational parameter registry (names only; values in `operations/macos-service.md` §2)

D's table is the **single source of values** (RD-10, Addendum B.4). This registry fixes which names requirements and tests cite. Names follow D's `mercury.toml` keys. A requirement may cite only a registered name; changing a value is a D change, plus a change note in §14 if a requirement's pass/fail outcome changes. Workflow policy is **not** an operational parameter: attempt counts and backoff (`architecture/state-machine.md` §7.1), revision budgets and authorization expiry (OD-08, state-machine §9), state reminder timers (state-machine §7.3), notification cadence (`architecture/components.md` §4.15), retry matrix (`integrations/github.md` §15).

| Parameter group (D §2) | Names cited | Cited by |
|---|---|---|
| Service (§2.1) | `svc.throttle_interval_s`, `svc.exit_timeout_s`, `svc.shutdown_budget_s`, `svc.start_to_ready_max_s`, `svc.restart_to_ready_max_s`, `svc.crash_loop_starts`, `svc.crash_loop_window_min` | NFR-002, NFR-024, NFR-027 |
| Recovery (§2.1) | `recovery.reconcile_max_s`, `recovery.first_poll_max_s`, `recovery.downtime_notice_min` | NFR-021, NFR-025, FR-222, FR-282 |
| Persistence (§2.1) | `db.lease_persist_s`, `db.progress_flush_s` | FR-040, NFR-085 |
| Run supervision (§2.1–§2.2) | `run.liveness_poll_s`, `run.lost_by_host_cap`, `supervisor.alive_touch_s`, `supervisor.lease_stale_min`, `supervisor.kill_ladder_s`, `run.hard_deadline_margin_pct`, `wrapper.tick_s` | FR-023, FR-044, FR-053, FR-055, NFR-006 |
| Deadlines and stalls (§2.3) | `run.<kind>.deadline`, `run.<kind>.stall` for `claude_triage`, `claude_authorize`, `claude_plan_review`, `claude_revision_request`, `claude_code_review`, `claude_security_review`, `codex_plan`, `codex_implement`, `codex_revise`, `verify`, `deps_install`, `git_step`; `repo.test_timeout_min` | FR-044, FR-055, NFR-006, NFR-083 |
| Clocks and wake (§2.4) | `clock.tick_active_ms`, `clock.tick_idle_ms`, `clock.sleep_gap_s`, `clock.wall_jump_s`, `wake.grace_s`, `wake.dark_wake_min_awake_s`, `power.will_sleep_budget_s`, `power.prevent_system_sleep_on_ac` | FR-052, FR-082, FR-282, NFR-085 |
| Connectivity (§2.4) | `net.stability_s`, `net.probe_interval_offline_s`, `net.error_probe_window_s` | FR-283 |
| Integration cadence (§2.5) | `github.poll_*`, `github.reconcile_open_prs_min`, `linear.poll_s`, `linear.poll_overlap_s`, `circuit.*`, `gov.drift_check_interval_min`, `audit.anchor_overdue_h` | NFR-040, NFR-041, NFR-081, OPS-003, FR-263 |
| Concurrency and resources (§2.6) | `limits.max_codex_runs`, `limits.max_claude_runs`, `limits.max_runs`, `limits.max_runs_per_repo`, `limits.max_active_tasks`, `resources.*`, `run.stdout_cap_mib`, `deferral.notify_after_h` | FR-041, NFR-082 |
| Disk (§2.6) | `disk.dispatch_hold_gib`, `disk.dispatch_hold_pct`, `disk.interrupt_local_gib`, `disk.interrupt_codex_gib`, `disk.ballast_mib` | NFR-082 |
| Observability and backups (§2.7) | `heartbeat.local_s`, `heartbeat.remote_min`, `watchdog.schedule`, `watchdog.stale_awake_min`, `watchdog.stale_sleeping_h`, `watchdog.renotify_h`, `credentials.*`, `backup.due_after_h`, `backup.retention`, `logs.*`, `runs.retention_d` | OPS-013, NFR-022, NFR-061, OPS-011 |
| Hold ageing (§2.7) | `hold_age.spec_changed_h`, `hold_age.dependency_unresolved_d`, `hold_age.deprioritized_d` | FR-050 |

Security **bounds** (drift detection ≤ 60 min awake, merge-verification alert ≤ 5 min awake) are requirements (SEC-108, SEC-905, CON-014), not parameters; D's cadences must satisfy them.

---

## 8. Alias tables (valid until M9c exit)

### 8.1 Requirement aliases

| Alias (owner, document) | Canonical ID |
|---|---|
| NFR-LAT-01 (A, overview §10) | NFR-042 |
| NFR-LAT-02 | NFR-045 |
| NFR-LAT-03 | NFR-040 |
| NFR-LAT-04 | NFR-043 |
| NFR-LAT-05 | NFR-044 |
| NFR-REL-01 | NFR-002 |
| NFR-REL-02 | NFR-025 (full reconcile); NFR-021 (first poll) |
| NFR-REL-03 | NFR-001 (duplicate execution definition) + FR-040 |
| NFR-REL-04 | NFR-001 |
| NFR-REL-05 | NFR-050 |
| NFR-REL-06 | NFR-003, NFR-006 |
| NFR-REL-07 | CON-009 |
| NFR-AUD-01 | CON-005, NFR-060 |
| NFR-AUD-02 | NFR-060, FR-262 |
| NFR-AUD-03 | FR-260 |
| NFR-AUD-04 | NFR-061 |
| NFR-SEC-01 | CON-010 |
| NFR-SEC-02 | SEC-202 |
| NFR-SEC-03 | CON-014, SEC-905 |
| NFR-NOT-01 | FR-221 |
| NFR-NOT-02 | NFR-063 |
| NFR-RES-01 | NFR-080 |
| NFR-RES-02, NFR-RES-03 | NFR-081 |
| NFR-AVL-01 | NFR-004 |
| NFR-MNT-01 | NFR-095 |
| NFR-COST-01 | NFR-083, NFR-084 |
| REL-01 (D, macos-service §2) | NFR-002 |
| REL-02 | NFR-025 |
| REL-03 | NFR-050 |
| REL-04, REL-05 | NFR-026 |
| REL-06 | NFR-001 |
| REL-07, REL-08 | NFR-006 |
| REL-09 | OPS-013 |
| REL-10 | FR-281 |
| REL-11, REL-12 | NFR-022 |
| REL-13 | NFR-021 |
| REL-14 | NFR-024 |
| REL-15 | NFR-027 |
| REL-16 (D, agent-uid credentials) | SEC-201 (E) |
| SEC-001…080 anchors (F) | §4.2 |

### 8.2 Invariants and test properties

| C label (retired) | Canonical | Checked by |
|---|---|---|
| I1 | INV-01 | PROP-11 |
| I2 | INV-02 | PROP-05 |
| I3 | INV-03 | PROP-01 |
| I4 | INV-04 | PROP-02 |
| I5 | INV-05 | PROP-02 |
| I6 | INV-06 | PROP-12 |
| I7 | INV-07 | PROP-08 |
| I8 | INV-08 | PROP-06 |
| I9 | INV-09 | PROP-04, TC-CON-012 |
| I10 | INV-10 | PROP-18, TC-SEC-121 |
| I11 | INV-11 | PROP-13 |
| I12 | INV-12 | PROP-14 |
| I13 | INV-13 | PROP-15, TC-INT-020 |
| I14 | INV-14 | PROP-16 |
| I15 | INV-15 | PROP-07 |
| I16 | INV-16 | TC-INT-004 |
| I17 | INV-17 | PROP-03 |
| I18 | INV-18 | PROP-17 |
| I19 | INV-19 | PROP-08, TC-SM-019 |
| I20 | INV-20 (extended by the timer rule, FR-085) | PROP-09, TC-SM-021 |
| VP I1…I10 (F, retired) | PROP-01…PROP-10 (same order) | verification plan §5 |

C is asked to add INV-21 "replay determinism" (FR-084) and INV-22 "holds never change state" (FR-050); PROP-10 and PROP-20 check them in the meantime.

### 8.3 Test-ID aliases

| Contributor IDs | Canonical TC | Rule |
|---|---|---|
| E `SEC-T-nn` (except below) | `TC-SEC-1nn` | Same two digits (SEC-T-20 → TC-SEC-120) |
| E `SEC-T-10…18` | `TC-GOV-110…118` | Governance level |
| E `SEC-T-30…39` | `TC-PI-130…139` | Prompt-injection level |
| E `PI-01…15` | Variants inside TC-PI-130…139 | Corpus items |
| C `SMT-01` | TC-SM-001, TC-SM-002 | |
| C `SMT-02` | TC-SM-019 | |
| C `SMT-03`, `SMT-04` | TC-SM-004 (PROP suite) | |
| C `SMT-05` | TC-SM-007 | |
| C `SMT-06` | TC-SM-025 | |
| C `SMT-07` | TC-SM-008 | |
| C `SMT-08` | TC-SM-026 | |
| C `SMT-09` | TC-SM-027 | |
| C `SMT-10` | TC-SM-012 | |
| C `DBT-01…04` | TC-INT-020…023 | |
| C `CT-01…05` | TC-CON-009…013 | |
| C `RT-01` | TC-REC-001 | |
| C `RT-02` | TC-DUP-006 | |
| C `RT-03` | TC-REC-031 | |
| C `RT-04` | TC-NET-008 | |
| C `RT-05` | TC-INT-005 | |
| C `RT-06` | TC-REC-005 | |
| C `RT-07` | TC-SEC-150 | |
| C `RT-08` | TC-CONC-001 | |
| C `RT-09` | TC-INT-024 | |
| C `RT-10` | TC-INT-006 | |
| D `T-REC-01` | TC-REC-001 | |
| D `T-REC-02` | TC-REC-020 | |
| D `T-REC-03` | TC-REC-030 | |
| D `T-REC-04` | TC-REC-031 | |
| D `T-REC-05` | TC-REC-005 | |
| D `T-REC-06` | TC-REC-019 | |
| D `T-REC-07` | TC-AFS-008 | |
| D `T-REC-08` | TC-REC-007 | |
| F `TC-P0-001…015` (Phase 2) | `P0-nnn` register | verification plan §8 `TC-P0` retired table |
| F `TC-SEC-001`, `-002`, `-005`, `-007` (Phase 2 seeds) | TC-SEC-103, TC-SEC-121, TC-SEC-120, TC-SEC-122 | Superseded by E's tests |

### 8.4 Operator-decision aliases

See the "Aliases" column of §9.

### 8.5 Milestone and stage aliases

| Alias | Canonical |
|---|---|
| F Phase 2 `P0` | `P0a`…`P0d` |
| F Phase 2 `M9` | `M9a` (shadow), `M9b` (supervised), `M9c` (cutover and watch) |
| A ADR-012 `M0` | `MIG-0` (inventory, in P0a) |
| A ADR-012 `M1` shadow | `MIG-1` = M9a |
| A ADR-012 `M2` pilot | `MIG-2` = M9b |
| A ADR-012 `M3` cutover | `MIG-3` = M9c start |
| A ADR-012 `M4` decommission/watch | `MIG-4` = M9c end |
| A governance `G-1` / `G-2` | `G-DETECT` / `G-ORG` |
| B "detect-after" | `G-DETECT` |

---

## 9. Operator decision register (OD-01…OD-36)

One list. Defaults are the design's adopted defaults (binding where a reconciliation decision fixed them); only the operator decides. "Needed by" uses the milestones of `planning/roadmap.md`. The design works under every listed option unless the row says otherwise.

| OD | Decision | Aliases | Options | Recommended / adopted default | Needed by | Affects |
|---|---|---|---|---|---|---|
| OD-01 | Merge-actor governance mode per repository (**required before unattended operation**, with OD-36) | OD-A-01, OQ-B-09, E Q1, SEC-109 | G-ORG; G-SPLIT; G-DETECT | Sandbox and supervised pilot: G-DETECT **with written risk acceptance**. **G-ORG required before any unattended or overnight operation on targets** (RD-5). G-SPLIT only if P0-064, P0-065 and P0-068 pass. F additionally recommends moving targets to an org before M9b. | P0c (sandbox acceptance); M9b (pilot acceptance); M9c (G-ORG) | CON-014, OPS-017, SEC-109 |
| OD-02 | GitHub identity type | F OD-02 | GitHub Apps; machine user | Two GitHub Apps, `mercury-bot` (incl. `statuses:read`, Addendum B.1) and `mercury-ops` (RD-6); no machine user | P0c | OPS-002, ADR-008 |
| OD-03 | Claude authentication and billing | OQ-B-01, OD-A-04 | Dedicated API key; `setup-token` | Dedicated Anthropic workspace API key with spend limit | P0a (needed for P0-042) | NFR-083, SEC-504 |
| OD-04 | Codex authentication and billing | OQ-B-03, OD-A-04 | Dedicated project key; ChatGPT login | Dedicated OpenAI project key with spend limit | P0a | NFR-083 |
| OD-05 | Linear identity | F OD-05, SEC-801 | OAuth `actor=app`; team-scoped key (sandbox only) | OAuth app `actor=app` (client credentials) | P0c | FR-201 |
| OD-06 | Linear `Done` owner (Linear mode per team) | OD-A-03, OQ-B-06, RA-10 | `integration_owns_done`; `mercury_owns_all` | `integration_owns_done` for the pilot (RD-9); `mercury_owns_all` is the security-preferred alternative | M4 (branch naming, FR-120); M7 (projection) | FR-120, FR-142, FR-183, FR-200 |
| OD-07 | Concurrency | F OD-07, D Q3 | — | Codex 1, Claude 2, 1 per repo; Codex 2 after P0-038 passes | M1 | FR-041 |
| OD-08 | Revision budgets, authorization expiry, spend caps | OD-A-05, OD-C-02, SEC-315 | — | Plan 3, PR review 3, CI/test fix 3, human change requests 5; authorization expiry 7 days; per-decision caps per `integrations/claude.md` §3.1; daily spend cap set from shadow data | M4 (budgets); M9a (daily cap) | CON-012, FR-104, FR-144, FR-163, NFR-084 |
| OD-09 | Codex network; dependency lifecycle scripts | F OD-09, OQ-B-04, E Q4 | — | Codex never has network; `deps_install` with `--ignore-scripts`, registry allowlist, no per-repo override in v1 | M5 | FR-121, FR-123 |
| OD-10 | Eligibility signal | OD-A-02 | — | `Todo`/`Backlog` + operator-added `mercury` label | M2 | FR-002, FR-300 |
| OD-11 | Plan auto-approval scope | F OD-11 | All; operator gate for some | Operator gate for `Security`-labelled or protected-path plans during the pilot | M4 | FR-106 |
| OD-12 | Escalation response channel | F OD-12, RA-27 | CLI only; verified-author GitHub channel | Local CLI only in v1 (iPhone can see, not resolve); revisit after M9c | M7 | FR-241, FR-905 |
| OD-13 | Sandbox names; second human test account | F OD-13 | — | `mercury-sandbox` + Linear `MSB`; a test-human account only for TC-GOV automation | P0c | OPS-004 |
| OD-14 | Machine type and power policy | F OD-14, D Q2, OD-D-05 | — | Laptop: `caffeinate -i` only while runs are active, no system-sleep prevention; desktop: opt-in `-s` on AC | M8 | CON-009, NFR-004 |
| OD-15 | Retention and raw logs | F OD-15, SEC-606, C §4.16 | — | Audit and artifacts ≥ 1 year; redacted transcripts 90 d; ops logs 90 d; debug 30 d; no raw unredacted agent output beyond run completion | M7 | NFR-061 |
| OD-16 | Pilot scope and Slack shutdown | F OD-16, ADR-012, RA-25 | — | Shadow 10 working days; supervised ≥ 10 tasks, the first 5 at concurrency 1; cutover watch 30 days; Slack coordination off at cutover start | M9a | OPS-008, FR-301 |
| OD-17 | Meaning of "Claude is the primary orchestrator" | A Q1, RA-1 | — | Accept RD-20: Claude holds decision authority; `mercuryd` holds the loop | P0c | CON-003 |
| OD-18 | Agent process isolation | OQ-B-05, SEC-201, OD-C-07, E Q3, OD-D-01, OD-D-02, OD-D-03, OD-D-08 | — | Adopt RD-1: `_mercuryagent` via `agent-exec`/`agent-ctl` (sudoers); Claude via SDK custom spawn, falling back to ALT-B-1 if P0-042 fails; MERCURY-managed toolchains; supervisor lease while logged out per parameter table | P0b | CON-018, FR-051, OPS-014, OPS-015 |
| OD-19 | Root-owned managed settings (Claude) and `requirements.toml` (Codex) | OQ-B-02, D-SEC-4 | — | Yes, narrowly scoped (also affects the operator's interactive Claude) | M3 | SEC-204, SEC-208 |
| OD-20 | Operations identity, audit anchoring and HMAC key escrow | E Q2, SEC-108, SEC-603/604, OD-D-07 | — | `mercury-ops` App with `issues:write` on `project-mercury`, `contents:write` on a private anchor repo, `metadata:read` on targets (RD-6); HMAC SHOULD; no `k_auth` escrow (re-authorize after a Mac change) | P0c | OPS-002, FR-263, FR-264 |
| OD-21 | Security findings on public PRs | OQ-B-07 | — | Withhold critical/high and pre-existing details; generic line + local report ID | M6 | FR-168 |
| OD-22 | Require review-thread resolution | OQ-B-08, SEC-100, RB-20 | On; off | **Off** (bot `COMMENT` threads would otherwise block merges; E SEC-100 revised) | P0c | SEC-100 |
| OD-23 | Security review on every PR, separate run | E Q5, A Q6 | — | Every PR, separate run | M6 | FR-161 |
| OD-24 | Chain head in public artifacts | E Q6 | Embed; do not embed | **No public chain-head embed**: carriers are the Linear completion comment and the private anchor repo; the check-run summary only on private repos (Addendum B.2) | M7 | FR-263 |
| OD-25 | Automatic triage | OD-C-01 | — | On, debounced, shortlist-only; on in shadow mode | M3 | FR-020 |
| OD-26 | Do operator review comments without `CHANGES_REQUESTED` start a revision? | OD-C-03, SEC-313 | — | No; only operator `CHANGES_REQUESTED` reviews; a `mercury:revise` label later (counts only when the label actor is the operator) | M6 | FR-163 |
| OD-27 | `BLOCKED` TTL before `FAILED` | OD-C-04 | — | 30 days; reminders at 24 h, 72 h, then weekly | M1 | FR-050 |
| OD-28 | Operator merges before the Claude review | OD-C-05 | — | `merged_unreviewed_head` policy notice, closed by `ack-merge` (RD-14) | M7 | FR-182 |
| OD-29 | Claude failure-triage decision kind in v1 | OD-C-06, A R4 | — | Defer; failures escalate to the operator (RD-8 `revision_request` runs are separate) | M3 | FR-045 |
| OD-30 | External liveness backstop and sleep helper | D Q1, OD-D-04, OD-D-06 | — | GitHub Actions watchdog via `mercury-ops` + signed sleep-notification helper; third-party heartbeat service off | M7 | OPS-013, OPS-018 |
| OD-31 | Keychain `-T /usr/bin/security` ACL | D Q4, RISK-29 | — | Not acceptable as the end state: if P0-036 shows MERCURY items must trust `/usr/bin/security`, the signed `mercury-keychain` helper is built in M1 (Addendum A) | M1 | SEC-503, OPS-007 |
| OD-32 | Delete remote branches of cancelled tasks | D Q6 | — | No (v1) | M7 | FR-184 |
| OD-33 | Re-authorize on every spec edit | A Q7 | — | Always on `spec_hash` change; Claude may confirm "no material change" (RD-13) | M3 | FR-024 |
| OD-34 | Model per decision type | B tradeoffs | — | Opus for all types in the pilot; no `fallbackModel` for authority decisions; revisit triage after shadow cost data | M3 | FR-020, FR-261 |
| OD-35 | Policy actions checklist (not choices) | SEC-105/106/804/806, E §7, OD-E-02 | — | Complete OPS-019 with evidence | P0c | OPS-019 |
| OD-36 | Dedicated macOS account for the coordinator (U2), in addition to the agent uid | E RE-01 (U2), E 44 §3, RD-1, Addendum A | (a) stay in the operator uid and accept RISK-27 in writing; (b) move `mercuryd` to a dedicated account (Zone C separated from Zone H) | **Required decision before unattended operation (G-S5)**, alongside OD-01 (Addendum A). v1 build assumes (a); F recommends deciding at M8 exit with the pilot data, so (b) can be scheduled as MERC-807b without delaying M9c | M8 exit (decision); G-S5 / M9c (in force) | RISK-27, ADR-010, ADR-013 |

Deduplication: the 60 raw items across A (5 + 2 questions), B (9), C (7), D (6 + 8 OD-D), E (6 + operator list) and F (16) reduce to 36. OD-35 is a checklist.

---

## 10. Assumptions and Phase 0 closure

### 10.1 Agent F assumptions

| ID | Assumption | Impact if false | Verified by |
|---|---|---|---|
| ASM-F-01 | Latency defaults fit the rate budgets | NFR-040/041/081 retuned | TC-SBX-008 |
| ASM-F-02 | A sandbox Linear team can be created on the current plan | Separate workspace needed | P0-061 |
| ASM-F-03 | GitHub Apps install on personal-account repositories with the RD-6 permission sets | Org move earlier (OD-01) | P0-060 |
| ASM-F-04 | **Refuted** (RD-16): monotonic time continues during sleep on macOS | Requirements now state behaviour (FR-282) | P0-034 |
| ASM-F-05 | Fullfsync commit latency is acceptable on the Mac SSD | Batch writes; worker thread | TC-PERF-004 |
| ASM-F-06 | Governance tests needing a human approval run with the operator in the loop | TC-GOV stay semi-manual | OD-13 |
| ASM-F-07 | GitHub-hosted macOS runners are available for T1/T2 | Linux CI plus local runs before exits | CI spike (P0d) |
| ASM-F-08 | Fake executables are accepted by the version self-test in test mode | Inject paths via config | M1 |
| ASM-F-09 | A Linux fault filesystem suffices for SQLite logic tests (not durability) | Logic only; durability via the macOS VM (TC-REC-020) | M1 |
| ASM-F-10 | Agent-assisted throughput reaches ~1.5 focused engineer-days per workday | Calendar plan stretches (roadmap §6) | Re-estimate at P0 exit |
| ASM-F-11 | An Apple Silicon host can run a macOS guest VM (tart/UTM) for power-loss tests | Power-loss tested by inspection only | P0-047 |

### 10.2 Gating assumption closure register and Phase 0 ID allocation

`P0-001…049` are D's Mac checks (procedures and gates in `operations/macos-service.md` §16). F allocates `P0-050…079` for agent-CLI, GitHub and Linear checks (procedures by B for integrations and E for governance; listed in verification plan §8 `TC-P0`). The table tracks closure of every assumption that gates a milestone (CON-015). Owners keep a "Verified by" column pointing here.

| Assumption(s) | Phase 0 check | Gates (milestone / gate) | Status |
|---|---|---|---|
| ASM-E-04, ASM-E-15, ASM-E-16 (agent uid cannot read operator or MERCURY secrets) | P0-007, P0-027, P0-037 | G-S2 | Open |
| ASM-E-20, ASM-D-36 (sudo fd 3 hand-off without TTY) | P0-026 | M1 | Open |
| ASM-E-21 (cross-uid signalling only via `agent-ctl`) | P0-028 | M1 | Open |
| ASM-E-22, ASM-D-30 (`ps` argv across uids) | P0-029 | M1 | Open |
| ASM-E-13 (Codex with read-only mirror) | P0-030 | M1 | Open |
| ASM-E-23, ASM-D-32 (lease ends runs after logout) | P0-031 | M1 | Open |
| ASM-E-24, RD-26 (target tests as `_mercuryagent` with toolchains) | P0-032 | M1 (D) / G-S2 | Open |
| ASM-D-03/04 (LaunchAgent, `ExitTimeOut`) | P0-033 | M1 | Open |
| ASM-D-13/14, ASM-A-04, ASM-C-02 (clock across sleep) | P0-034 | M1 | ASM-A-04, ASM-F-04 **Refuted** (RD-16); rest Open |
| ASM-D-09, ASM-A-02 (Keychain from LaunchAgent) | P0-035 | M1 | Open |
| ASM-E-08, RE-29 (Keychain ACL trusts helper, not `/usr/bin/security`) — decides whether `mercury-keychain` is v1 | P0-036 | M1 | Open |
| ASM-D-21, ASM-E-15, ASM-B-19 (Seatbelt denies Keychain, mirror writes, cross-run files) | P0-037 | M1 | Open |
| ASM-A-05, ASM-B-18 (parallel per-task `CODEX_HOME`) | P0-038 | Codex concurrency 2 | Open |
| ASM-D-11 (`caffeinate -i`) | P0-039 | M1 | Open |
| ASM-D-06 (local notifications) | P0-040 | M1 | Open |
| ASM-D-33, RD-25 (Claude SDK custom spawn via `sudo agent-exec`) | P0-042 | M3 (else ALT-B-1) | Open |
| ASM-E-11, ASM-E-12 (no connectors; egress only to the API) | P0-042 (with egress log) | M3 | Open |
| ASM-D-29 (git `core.fsync` uses full fsync) | P0-043 | M2 | Open |
| ASM-D-31 (`WORK_ROOT` ACL inheritance) | P0-044 | M1 | Open |
| ASM-D-34, ASM-E-19 (presence helper from a LaunchAgent) | P0-045 | M5 / G-S4 | Open |
| ASM-D-35, RD-18 (dark-wake detection via power helper) | P0-046 | M5 (D) / M1 logic | Open |
| ASM-F-11, RD-24 (macOS guest VM power-loss rig) | P0-047 | M8 | Open |
| ASM-E-10 (managed settings, `requirements.toml`) | P0-048 | M3 | Open |
| ASM-E-06 (agent-uid egress control) | P0-049 (E specifies) | SEC-206 (SHOULD); G-S2 if chosen for `deps_install` | Open |
| ASM-B (Codex output-schema failure behaviour) | P0-050 | M4 | Open |
| ASM-E-17 (`disableAllHooks` vs SDK hooks) | P0-051 | G-S1 | Open |
| RD-15 (wire-copy schemas accepted by both providers) | P0-052 | M3 | Open |
| ASM-E-18 (Seatbelt denies `process-info` of the Codex parent) | P0-053 | G-S2 | Open |
| ASM-F-03, RD-6, Addendum B.1 (both Apps; exact permission sets incl. `statuses:read`) — SEC-T-12 part 1 | P0-060 | P0c / G-S3 | Open |
| ASM-B-30, ASM-F-02 (Linear client-credentials app, sandbox team) | P0-061 | P0c | Open |
| RB-05 (pinning requires `statuses:write`?) + SEC-T-17 forged same-name check | P0-062 | M6 / G-S3 | Open |
| RB-03 (bot `COMMENT` review never blocks; SEC-T-18) | P0-063 | M6 | Open |
| ASM-E-01, RB-06a (deploy-key push of an approved head to `main` rejected) | P0-064 | G-SPLIT only | Open |
| ASM-E-02, RB-06b, ASM-B-53 (App cannot merge or enable auto-merge) | P0-065 | M5 / G-S3 | Open |
| RB-16, ASM-B-51 (rulesets and `bypass_actors` readable with `metadata:read`) | P0-066 | M2 | Open |
| ASM-E-03 (read-only credential reads Actions settings) | P0-067 | Optional (else POL check) | Open |
| ASM-E-07 (branch workflows and deploy keys) | P0-068 | G-SPLIT only | Open |
| ASM-E-05 (Linear app actor cannot merge or diff-review) | P0-069 | P0c (else Linear writes paused) | Open |
| ASM-A-07 (withdrawn), RA-10 (branch-name closing behaviour for `mercury_owns_all`) | P0-070 | M4 if OD-06 = `mercury_owns_all` | Open |
| RD-18 (target CI runs on draft PRs) | P0-071 | M9a | Open |
| SEC-T-16 cases (a)–(g) on the sandbox | P0-072 | G-S3 (rerun at M5 exit) | Open |
| MIG-0 legacy inventory of `network_monitor` | P0-073 | M9a | Open |
| OD-35 policy checklist evidence (OPS-019) | P0-074 | G-S1 | Open |
| ASM-E-09 (`fs.rm` symlinks) | unit test on macOS CI (TC-SEC-143) | M7 | Open |
| ASM-E-14 (`uappnd`) | not gating | — | Optional |

---

## 11. Milestone keys (summary; `planning/roadmap.md` is authoritative)

| Key | Milestone | Security gate at exit |
|---|---|---|
| P0a | Mac and agent-CLI verification (read-only and experiments); legacy inventory (MIG-0) | — |
| P0b | Agent-uid provisioning and verification | Agent uid probe evidence |
| P0c | Identities, sandbox governance, operator decisions and policy actions | Prerequisites of G-S1 (governance, OPS-019) |
| P0d | MERCURY repository bootstrap (CI, protections, ID lint) | — |
| M1 | Core: DDL + invariants + audit chain, state engine + holds, derived queue, broker adapter, lifecycle, CLI, fakes, PROP suite | G-S1 (before the first real agent run on the Mac) |
| M2 | Read-only pollers, eligibility, drift monitor (read) | — |
| M3 | Claude adapter under agent uid, snapshot builder, authorization records | — |
| M4 | Codex planning, per-task `CODEX_HOME`, instruction integrity, plan review loop | G-S2 evidence (SEC-T-20/21/28 with real agents; required before any non-sandbox write run) |
| M5 | Implementation, `verify`/`deps_install`, git hardening, pre-push gates, `MERCURY / policy`, presence tier, PR | G-S3 |
| M6 | Claude code + security review, `MERCURY / claude-review`, revision loops | — |
| M7 | Merge verification, Linear modes, notifications, audit trace, anchoring, watchdog | G-S5 controls built (E: "M7") |
| M8 | Hardening on the real Mac; SAC-01…20 evidence | — |
| M9a | Shadow (MIG-1) | — |
| M9b | Supervised pilot (MIG-2) | G-S4 at entry |
| M9c | Cutover and watch (MIG-3, MIG-4) | G-S5 at entry (G-ORG, OD-36 decided, SAC-01…20 green) |

---

## 12. Definition of Ready (MERCURY implementation issue)

An issue in `planning/issue-breakdown.md` (or in MERCURY's own backlog once the operator creates it) is **Ready** only when every item holds. Each issue carries the DoR fields marked "field".

| # | Criterion | Check / field |
|---|---|---|
| R1 | Linked to ≥ 1 requirement ID from this file with status `Baselined` or later | Field "Requirements" |
| R2 | The linked requirements' `TC-*` exist in the verification plan; the issue lists the TCs it makes pass | Field "Verifies" (inside "Acceptance") |
| R3 | Acceptance criteria copied or refined from the requirement, measurable pass/fail | Reviewer check |
| R4 | Contracts touched (schemas, ports, DB tables, CLI verbs) exist in their owning documents with a version | Links |
| R5 | Every `blocked-by` issue is Done, or the dependency is marked parallel-safe with a fake | Field "Blocked by" |
| R6 | Every gating `P0-nnn` / `ASM-*` is Verified or Accepted (§10.2) | Field "Gates" |
| R7 | No open `OD-*` blocks it, or it implements a configurable default with the OD recorded as pending | Field "OD" |
| R8 | Security impact stated; issues touching a `SEC-*` carry the `Security` label and a threat-model reference | Field "Security" |
| R9 | Recovery semantics stated for any new persistent step or external effect (idempotency key, crash-point name) | Field "Recovery" |
| R10 | P50 ≤ 3 engineer-days, otherwise split | Field "Estimate" |
| R11 | Test environment tier (T0–T5, T4v) available | Field "Env" |
| R12 | Description follows the issue convention (Context / Scope / Security / Tests / Acceptance / Size), not `Not Speced` | Template |
| R13 | Operational parameters cited by name (§7), never by value | Reviewer check |

## 13. Definition of Done

| # | Criterion |
|---|---|
| D1 | Merged to MERCURY's protected default branch through a PR approved and merged by the operator (CODEOWNERS), with all required checks green. |
| D2 | All listed TCs implemented and passing at their level; sandbox and real-Mac TCs have stored evidence (run ID, date, versions). |
| D3 | Coverage gates (NFR-100) met; no new lint or type errors. |
| D4 | New persistent steps registered in the crash-point registry and exercised by TC-REC-001; new external effects use a catalogue idempotency key. |
| D5 | Audit events and structured logs exist; redaction canary (TC-SEC-004) passes; secret scan clean. |
| D6 | Claude code review and security review completed (COMMENT reviews; MERCURY checks green once MERCURY reviews itself); blocking findings resolved; `Security` issues have E's checklist completed. |
| D7 | The owning design document and runbook are updated in the same PR (or a linked PR merged before the milestone exit). |
| D8 | RTM rows updated (`Implemented`, or `Verified` with evidence). |
| D9 | New configuration keys documented, defaulted and covered by the config validator (TC-UNIT-061); new parameters added to D's table and §7 first. |
| D10 | Worktree and branch cleaned up; the Linear issue reaches Done through the configured Linear mode. |

---

## 14. Change notes (Phase 4)

| Change | Cause |
|---|---|
| Unified ID registry (§1.1), alias tables (§8), parameter registry (§7) | RD-10; RF-02, RF-03, RF-04, RF-20, RF-36, RA-26, RC-20, RD-21, RE-26 |
| `SEC-001…099` retired; E's 90 SEC IDs registered and traced | RD-10; RF-02; F-SEC-1 |
| ADR-P keys retired; ADR-001…020 | RD-10; RF-25, RF-36 |
| New CON-018 (agent-uid gate), FR-051…055, OPS-014/015 | RD-1, RD-11; RF-01, RF-12 |
| FR-024 (spec drift) rewritten | RD-13; RF-16 |
| FR-040 (derived queue; mutating-run rule), FR-050 (holds) | RD-3; RC-18, RA-16 |
| FR-103/FR-163 revision routing; FR-162 COMMENT only; FR-166/167 required checks | RD-5, RD-8; RA-04, RB-03, RC-01, RE-15, RF-07 |
| FR-122/123/124/140 (verify, deps, pre-push split, git hardening) | RD-17; RF-09, RF-26 |
| FR-182 (merge-verification scope), CON-014 alert ≤ 5 min | RD-14; RF-27 |
| FR-183/200/120 Linear modes | RD-9; RF-08, RA-10 |
| FR-242/243 presence tier and security halt | RD-12; RA-09; RE-25 |
| FR-262…264 audit verification, anchoring, restore epoch | RD-4; RF-10, RF-19 |
| FR-282 rewritten (behaviour, not mechanism); ASM-F-04 refuted; NFR measurement rule §1.5; NFR-005 reworded | RD-16; RF-15, RA-23, RD-03, RD-22 |
| NFR-001 duplicate-execution definition; NFR target reconciliation | RC-31, RD-27; RF-04 |
| New FR-007 (issue-level discovery) | RF-22; RD-14 |
| NFR-061 single retention table | RF-17; OD-15 |
| OD register OD-01…36 | RF-23 (decisions part); RD decisions; OD-36 new |
