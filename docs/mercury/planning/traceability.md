# MERCURY — Requirements and Traceability

| | |
|---|---|
| **Owner** | Agent F (Technical Program Manager) |
| **Status** | Phase 2 draft. Baselined in Phase 4, when TDD §5 and §29 will reference this file. |
| **Authority** | **Single source of truth for requirement IDs** (brief: "Requirement IDs are owned by Agent F"). Other documents cite IDs from this file and do not redefine them. |
| **Inputs** | `reviews/00-brief.md`, `reviews/03-design-baseline.md`, `reviews/01-discovery-*.md`, `reviews/02-discovery-*.md` |
| **Companion** | `testing/verification-plan.md` defines every `TC-*` ID cited below. |

> Other Phase 2 documents (architecture, integrations, state machine, operations, threat model) are being written in parallel. Cells that depend on them say **TBD**, and every "Owning design" pointer is the *expected* section. Phase 4 reconciliation replaces TBDs and adjusts section pointers.

---

## 1. Conventions

### 1.1 ID scheme and reserved ranges

IDs are permanent. A retired requirement keeps its ID with status `Retired`, and IDs are never reused. Gaps inside a range are intentional, leaving room to insert related requirements next to each other.

| Prefix | Range | Area | Brief anchor |
|---|---|---|---|
| `CON-` | 001–099 | Constraints and invariants (non-negotiable) | Hard constraints, authority invariants |
| `FR-` | 001–019 | Intake, eligibility, dependencies | A, steps 1–2 |
| `FR-` | 020–039 | Claude triage and authorization | A, steps 1–3 |
| `FR-` | 040–059 | Scheduling, dispatch, execution control | A, step 4 |
| `FR-` | 060–079 | Agent communication and contracts | B |
| `FR-` | 080–099 | Workflow state machine | C |
| `FR-` | 100–119 | Codex planning and Claude plan review | D, steps 5–7 |
| `FR-` | 120–139 | Implementation and tests | E/F, steps 8–9 |
| `FR-` | 140–159 | Git operations and PRs | E, step 9 |
| `FR-` | 160–179 | Claude PR review and revision loops | E, steps 10–11 |
| `FR-` | 180–199 | Merge verification and post-merge | E, steps 13–14 |
| `FR-` | 200–219 | Linear projection | E/G |
| `FR-` | 220–239 | Human notifications | G, step 12 |
| `FR-` | 240–259 | Operator control | A/F |
| `FR-` | 260–279 | Audit queries | I |
| `FR-` | 280–299 | Recovery | F, step 15 |
| `FR-` | 300–319 | Slack migration and cutover | Mission |
| `FR-` | 900–999 | Explicitly out of scope (Won't) | Non-goals |
| `NFR-` | 001–019 / 020–039 / 040–049 / 050–059 / 060–069 / 070–079 / 080–089 / 090–099 / 100–109 | Reliability / Recoverability / Latency while awake / Durability / Auditability / Operability / Resource usage / Portability and version pinning / Maintainability and testability | F, I, J |
| `SEC-` | 001–099 | Security. **Reserved for Agent E.** Sub-ranges are in §4. | H |
| `OPS-` | 001–099 | Operational, environment and rollout | F, Mission |
| `TC-` | see `testing/verification-plan.md` §4 | Test cases | J |
| `ADR-Pnn` | provisional | ADR topic keys, mapped to Agent A's final ADR numbers in Phase 4 | §26 |
| `OD-nn` | — | Operator decisions (see §8) | §30 |
| `ASM-F-nn` | — | Agent F assumptions (see §9) | §30 |

### 1.2 Field definitions

| Field | Meaning |
|---|---|
| **Requirement** | One testable "shall/must" statement (or "should" for S, "could" for C). |
| **Rationale / source** | The brief section or discovery fact that creates the need. |
| **Pri (MoSCoW)** | **M**: required to exit the supervised pilot (M9) and cut over from Slack. **S**: required within 30 days after cutover. **C**: optional. **W**: will not be built in this release (recorded to prevent scope creep). |
| **Acceptance criterion** | A measurable pass/fail condition. Numeric defaults are tunable in configuration, but a change to a default needs an RTM note. |
| **Verification** | **Test** (automated), **Inspection** (review of code, config or docs), **Demo** (operator-observed run), **Analysis** (data or log analysis). |
| **Owning design** | The TDD section, plus the supporting document that holds the detailed design. |

### 1.3 Requirement status lifecycle

`Draft` → `Baselined` (Phase 4 sign-off) → `Designed` (owning section exists and passed review) → `Implemented` (merged) → `Verified` (all mapped TCs pass, with an evidence link). Side exits are `Deferred` and `Retired`. A change to a `Baselined` requirement needs an RTM change note naming the cause: an operator decision, a Phase 0 result, or a review finding.

### 1.4 Document abbreviations

All paths are relative to `docs/mercury/`.

| Path | Owner (Phase 2) |
|---|---|
| `architecture/overview.md`, `architecture/decisions/ADR-*.md` | A |
| `integrations/{claude,codex,linear,github}.md` | B |
| `architecture/components.md`, `architecture/state-machine.md`, `protocols/messages.md`, `protocols/schemas/` | C |
| `operations/macos-service.md`, `operations/recovery.md` | D |
| `security/threat-model.md` | E |
| `planning/*`, `testing/verification-plan.md` | F |

---

## 2. Source coverage map

Each brief item and discovery pain point maps to at least one requirement. Phase 5 validation uses this table as its completeness check.

### 2.1 Operating model (brief steps 1–15)

| Step | Summary | Requirements |
|---|---|---|
| 1 | Claude is the primary orchestrator | CON-003, FR-020 |
| 2 | Claude evaluates and prioritizes eligible issues | FR-001, FR-002, FR-003, FR-004, FR-020, FR-042 |
| 3 | Claude explicitly authorizes each task | FR-021, FR-022, FR-023, FR-024, CON-005 |
| 4 | A continuously running coordinator executes and tracks | FR-040, FR-041, FR-049, NFR-002, NFR-004, NFR-042 |
| 5 | Codex produces a plan | FR-100 |
| 6 | Claude reviews the plan | FR-101, FR-105 |
| 7 | Claude auto-approves or requests revisions | FR-103, FR-104, FR-106 |
| 8 | Codex implements in isolated worktrees | FR-120, FR-121, FR-123, FR-124, CON-016 |
| 9 | Tests run, PR prepared | FR-122, FR-140, FR-141, FR-142, FR-143 |
| 10 | Claude reviews the PR independently | FR-160, FR-161, FR-162 |
| 11 | Failed review leads to a revision loop | FR-163, FR-144, FR-165 |
| 12 | Human notified through GitHub and Linear | FR-164, FR-220, NFR-043, CON-011 |
| 13 | Only the human approves and merges | CON-007, CON-014, FR-180, FR-902, SEC-050 |
| 14 | Coordinator verifies the merge and updates Linear | FR-181, FR-182, FR-183, FR-184, NFR-044 |
| 15 | Unfinished tasks recover after restart | FR-280, FR-281, FR-282, FR-283, NFR-020, NFR-024 |

### 2.2 Hard constraints and authority invariants

| Constraint | Requirements |
|---|---|
| Never start work from a Linear status change alone (Inv. 3) | CON-004, FR-002, FR-203 |
| Claude authorization required, as a versioned record (Inv. 1) | CON-005, FR-021, FR-022 |
| Codex cannot run unapproved implementation (Inv. 2) | CON-006, FR-102, FR-121 |
| Human approval enforced technically; no impersonation (Inv. 4) | CON-007, CON-008, FR-162, FR-180, OPS-003, SEC-050 |
| No assumption of work during sleep | CON-009, FR-082, FR-282, NFR-021 |
| A plan revision invalidates earlier approval | CON-006, FR-102, TC-SM-007 |
| Bounded revision cycles with escalation | CON-012, FR-104, FR-144, FR-163 |
| No secrets in docs | CON-010, SEC-020 |
| Design only | CON-001 |
| No public inbound access | CON-002, FR-901 |

### 2.3 Content areas A–J

| Area | Requirements |
|---|---|
| A Orchestration | FR-001…006, FR-020…024, FR-040…049, CON-003…005 |
| B Communication | FR-060…065, FR-125 |
| C State machine | FR-080…084, CON-012 |
| D Plan approval | FR-100…106 |
| E GitHub PR workflow | FR-120, FR-140…144, FR-160…165, FR-180…185, OPS-003, CON-007, CON-014 |
| F Local execution | FR-044, FR-184, FR-280…283, NFR-002, NFR-020…024, NFR-050…052, NFR-070, NFR-092, OPS-012 |
| G Notifications | FR-164, FR-220…223, CON-011 |
| H Security | SEC-001…089 (Agent E), CON-007, CON-008, CON-010, FR-124, FR-203 |
| I Observability and audit | FR-260, FR-261, NFR-060…062 |
| J Testing | NFR-100, NFR-101, OPS-004, `testing/verification-plan.md` |

### 2.4 Quality gates (brief)

| Gate | Evidence requirement(s) or check |
|---|---|
| Deterministic lifecycle | FR-080, FR-084 |
| Every transition has authorization rules | FR-080, FR-081 (initiator field), TC-SM-001/002 |
| Persistence and recovery specified | FR-063, FR-280, NFR-020, NFR-050 |
| Communication versioned and traceable | FR-060, FR-061, FR-065 |
| Claude authorization before development | CON-005, FR-022 |
| Codex cannot run unapproved work | CON-006, FR-121 |
| Human approval via GitHub permissions | CON-007, OPS-003, TC-GOV-* |
| Measurable verification | Every row in §3 has a pass/fail acceptance criterion |
| Roadmap reflects dependencies | Milestone column in §6, plus the roadmap drafted in `reviews/15-agent-F-report.md` |
| Assumptions and open decisions documented | §8, §9 |

### 2.5 Discovery pain points and facts

| Pain point / fact (source) | Requirements |
|---|---|
| Identity confusion: agents post as the human (integrations S1; fact 3) | CON-008, FR-140, FR-201, SEC-001 |
| Lost or unseen replies (Slack pattern 2) | FR-063, NFR-005 |
| Stalls without detection, 14 h (pattern 3) | FR-044, FR-125, NFR-003, FR-222 |
| Manual human relays (pattern 4) | FR-020 (coordinator invokes Claude directly), FR-241, TC-PIL-002 ("0 relays") |
| Delivery failures needing manual retry (pattern 5) | FR-223 |
| Duplicate or junk posts; token leaked by the test suite (pattern 6) | FR-221, NFR-001, OPS-004, CON-010 |
| Environment split: cloud vs Mac worktrees (pattern 7) | CON-016 |
| Evidence vs claims (pattern 8) | FR-064, FR-122, FR-181 |
| Linear `Todo` used as the queue (fact 5) | CON-004, FR-002 |
| Linear coding sessions as a second start path (fact 5) | FR-005, FR-904 |
| Linear GitHub integration auto-moves status (integrations C3) | FR-183, ADR-P10 |
| Personal-account repo; merge restriction is org-only (fact 4) | CON-014, OD-01 |
| Codex likely cannot commit in a sandboxed worktree (fact 7) | FR-140, TC-P0-006 |
| Claude runs repo hooks and `.mcp.json` headless (fact 6) | SEC-030, TC-SEC-001 |
| No whole-run timeout in either CLI (fact 8) | FR-044, NFR-083 |
| launchd: LaunchAgent only while logged in; detached children escape cleanup (fact 10) | FR-281, NFR-024, OPS-012 |
| TCC-protected folders (platform M6) | NFR-092 |
| SQLite durability on macOS (fact 11) | NFR-050 |
| Version churn in agent CLIs (runtimes §6) | NFR-090, NFR-093 |

---

## 3. Requirements

### Constraints (CON) — non-negotiable boundaries

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **CON-001** | MERCURY's design phase must not modify any host, repository setting, Linear workspace, GitHub resource or Slack workspace; implementation starts only after operator sign-off of the TDD. | Brief: Mission | M | Phase 4/5 review finds 0 write actions in agent evidence logs; TDD §32 sign-off recorded before M1 starts. | Inspection | TDD §32, §27 · `reviews/` |
| **CON-002** | The coordinator must run locally on the operator's Mac and must not require any public inbound network path to the Mac; all integrations are outbound. | Brief: Target operating model; Discovery fact 9 | M | Port scan of the Mac from outside shows no MERCURY listener; coordinator binds only to a Unix socket / loopback; all GitHub/Linear traffic is outbound HTTPS. | Inspection + Test | TDD §7, §18 · `architecture/overview.md; operations/macos-service.md` |
| **CON-003** | Role boundary: Claude makes development decisions, MERCURY coordinates execution, Codex implements, the operator holds final merge authority. No component may assume another's authority. | Brief: Core boundary | M | Every decision record in the store has a Claude run (or operator CLI action) as its originator; MERCURY code contains no decision heuristics beyond configured eligibility rules (code review checklist). | Inspection + Analysis | TDD §9 · `architecture/overview.md` |
| **CON-004** | A Linear status change alone must never start development work; it may only make an issue eligible for Claude evaluation. | Brief: Hard constraints; Invariant 3; Discovery fact 5 | M | Across all E2E and sandbox tests, 0 Codex runs start without an authorization record; moving 50 sandbox issues to Todo produces 0 Codex spawns before Claude authorization. | Test | TDD §11, §12 · `architecture/state-machine.md; integrations/linear.md` |
| **CON-005** | No Codex run may execute without a valid, unrevoked Claude authorization bound to the exact task, Linear issue and repository. | Invariant 1 | M | Spawn gate refuses 100% of runs in the negative test matrix (missing, revoked, expired, mismatched task/issue/repo); 0 unauthorized spawns across 1000 randomized SM runs. | Test | TDD §9, §11, §13 · `architecture/components.md` |
| **CON-006** | No Codex implementation run may execute without a Claude approval bound to the exact plan artifact hash; any plan revision invalidates earlier approval unless the revised artifact is explicitly re-approved. | Invariant 2; Brief: Hard constraints | M | Spawn gate refuses implementation when approval.plan_sha256 differs from current plan hash (100% of mutation cases); property test finds 0 counterexamples in 10,000 sequences. | Test | TDD §11, §14 · `architecture/state-machine.md` |
| **CON-007** | The human approval boundary must be enforced by GitHub repository protections and token permissions, not only by prompt instructions; no agent identity may satisfy required human approval or impersonate it. | Invariant 4; Brief: Hard constraints; Discovery fact 4 | M | Sandbox governance suite TC-GOV-001..004 passes; agent identities hold no `administration` permission and cannot be code owners. | Test + Inspection | TDD §15, §19 · `integrations/github.md; security/threat-model.md` |
| **CON-008** | Agents and the coordinator must never act under the operator's personal GitHub, Linear or Slack identity or credentials. | Discovery fact 3; integrations C6 | M | Every PR, commit, review and Linear write produced in sandbox and pilot is attributed to a non-human actor (App/bot); credential inventory contains no human PAT/OAuth token. | Test + Inspection | TDD §9, §15, §19 · `integrations/github.md; integrations/linear.md` |
| **CON-009** | The design must not assume work continues while macOS sleeps, is logged out, or is rebooting; every timer must tolerate indefinite pauses. | Brief: Hard constraints; Discovery fact 10 | M | No task transitions to FAILED solely due to a sleep gap in TC-SM-009 (virtual clock) and TC-REC-003 (real Mac). | Test | TDD §18, §20 · `operations/macos-service.md; operations/recovery.md` |
| **CON-010** | Secrets must never appear in docs, repositories, plists, process argv, logs, artifacts, PR bodies or Linear comments. | Brief: Hard constraints; Discovery fact 12 (leaked bot token) | M | Secret canary test finds 0 occurrences; repository secret scan of docs/ and MERCURY repo returns 0 findings. | Test + Inspection | TDD §19, §21 · `security/threat-model.md` |
| **CON-011** | Human-facing notifications must use existing GitHub and Linear notification channels (iPhone + Mac); MERCURY must not require a new dashboard, app or chat channel. | Brief: operating model footnote | M | All notification classes in FR-220 are delivered through GitHub or Linear in sandbox; no MERCURY UI component exists beyond the local CLI. | Inspection + Test | TDD §7, §12, §15 · `integrations/github.md; integrations/linear.md` |
| **CON-012** | Revision cycles (plan, PR review, CI fix) must be bounded per task, and exceeding a bound must escalate to the operator. | Brief: Hard constraints | M | TC-SM-008 shows the (N+1)th revision request transitions to BLOCKED with exactly one escalation for each loop type. | Test | TDD §11, §14 · `architecture/state-machine.md` |
| **CON-013** | MERCURY must coordinate work on target repositories (e.g. `usjbro/network_monitor`) distinct from its own repository and must not hard-code Linear team keys, issue prefixes, repository names or human logins. | Discovery fact 2; integrations constraint 1 | M | Grep of source for `JAM`, `network_monitor`, `usjbro` outside config/test fixtures returns 0; E2E passes with fixtures using a different team key and repo. | Inspection + Test | TDD §8, §12 · `architecture/components.md` |
| **CON-014** | On repositories owned by a personal GitHub account, 'only the operator merges' is detective (verify-after-merge + alert) unless the operator moves the repository to an organization (OD-01). The TDD must state which control is in force per repo. | Discovery fact 4; platform §1.4 | M | Per-repo governance report lists merge-actor control mode (preventive/detective); detective mode raises an alert in ≤ 10 min for a non-human merge in sandbox. | Inspection + Test | TDD §15, §19 · `integrations/github.md` |
| **CON-015** | All Mac-dependent behaviour marked as an ASSUMPTION must be verified by the Phase 0 checklist (or explicitly accepted by the operator) before the milestone that depends on it starts. | Discovery fact 1; 01-discovery-local | M | Phase 0 report shows every ASM-* that gates M1–M9 as Verified, Refuted-with-design-change, or Accepted; 0 Open. | Inspection | TDD §18, §30 · `operations/macos-service.md` |
| **CON-016** | Codex must execute only in coordinator-managed local worktrees on the Mac; cloud worktrees or Codex Cloud/Linear coding sessions are not part of the controlled path. | Discovery: integrations failure pattern 7; platform §3 L3 | M | Every Codex run record has `cwd` under the configured worktree root on the Mac; FR-006 detection covers Linear-native coding sessions. | Test + Inspection | TDD §13 · `integrations/codex.md` |
| **CON-017** | Each requirement and each contract is defined in exactly one place (requirement IDs only in planning/traceability.md and TDD §5); other documents reference IDs. | Brief: Documentation layout | M | ID lint script finds 0 requirement definitions outside traceability.md/TDD §5 and 0 references to undefined IDs. | Inspection | TDD §5, §29 · `planning/traceability.md` |

### FR — Intake, eligibility and dependencies (content area A; operating model 2)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-001** | The coordinator shall poll each configured Linear team incrementally using a durable `updatedAt` cursor with an overlap window, and shall record every issue change it observes exactly once (dedupe by issue id + updatedAt). | Discovery fact 9; platform E3 | M | With the sandbox team, 100 scripted issue updates (including updates during a poll) are all observed: 0 missed, 0 double-processed. | Test | TDD §12 · `integrations/linear.md` |
| **FR-002** | The coordinator shall classify an observed issue as eligible for Claude evaluation only when all configured eligibility rules hold (team in scope, workflow state in the configured set, required opt-in label present per OD-10, no `Not Speced` label, repository mapping resolves, not already a MERCURY task). | Brief: step 2; Discovery: Not Speced label; OD-10 | M | Rule-table unit tests cover every rule true/false (≥ 2 cases each); issues failing any rule never enter AWAITING_AUTHORIZATION. | Test | TDD §12, §11 · `integrations/linear.md; architecture/state-machine.md` |
| **FR-003** | The coordinator shall resolve each task to exactly one Linear issue and exactly one target repository via an explicit configuration mapping; an issue that maps to zero or multiple repositories shall not be eligible and shall be flagged once. | Baseline: Task definition | M | Resolver tests: 0, 1 and 2+ mappings produce not-eligible/eligible/not-eligible; one flag event per issue per change. | Test | TDD §8, §12 · `architecture/components.md` |
| **FR-004** | The coordinator shall not dispatch a task whose Linear issue has unresolved `blockedBy` relations (blocking issue not in a completed/canceled state) and shall re-evaluate when blockers change. | Brief: area A dependency resolution; Discovery: heavy blocks usage | M | E2E: task with an open blocker stays undispatched for ≥ 3 poll cycles; dispatches within 2 poll intervals after blocker reaches Done. | Test | TDD §8, §11, §12 · `architecture/components.md; integrations/linear.md` |
| **FR-005** | The coordinator shall detect Linear-native delegation or coding sessions (delegate set to a non-MERCURY agent) on MERCURY-managed or eligible issues, refuse to dispatch them, and flag the issue once. | Discovery fact 5; platform L3 | M | Fixture with `delegate` set yields state BLOCKED (reason `foreign_agent_delegation`) and exactly one flag. | Test | TDD §12 · `integrations/linear.md` |
| **FR-006** | The coordinator should pass all Linear relations, labels, priority and the full description to Claude triage, and should mark prose-only dependency references (e.g. legacy `#154`) as unverified context. | Discovery: prose dependency refs (JAM-117) | C | Triage input fixture contains relations and a `prose_refs` list for descriptions containing `#<n>` patterns. | Test | TDD §12, §14 · `integrations/linear.md` |

### FR — Claude triage and authorization (content area A; operating model 1–3)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-020** | The coordinator shall invoke Claude to evaluate and prioritize eligible issues and shall accept only a schema-valid decision (`authorize` \| `defer` \| `reject` \| `needs_human`) with priority and rationale. | Brief: steps 1–3 | M | Contract test: valid outputs accepted; invalid/missing `structured_output` → run failure, no state change beyond retry accounting. | Test | TDD §9, §14 · `integrations/claude.md; protocols/messages.md` |
| **FR-021** | For each `authorize` decision the coordinator shall write an immutable, versioned authorization record (`auth_` ID, version, task, issue, repo, spec hash, scope, limits: cycle bounds, budgets, deadline, expiry) derived only from schema-valid Claude output; records are never updated in place. | Brief: hard constraint (versioned record); area A | M | DB has no UPDATE path on authorization rows (trigger rejects); each record carries SHA-256 of its canonical JSON; re-authorization creates version n+1. | Test + Inspection | TDD §9, §16 · `architecture/components.md; protocols/messages.md` |
| **FR-022** | Before spawning any Codex run, the coordinator shall verify in the same transaction that claims the job that a current authorization exists, is unrevoked and unexpired, and matches task, issue and repository. | Invariant 1 | M | Spawn gate unit tests reach 100% branch coverage; 0 unauthorized spawns in TC-SM-004 and TC-REC-001. | Test | TDD §11, §13 · `architecture/components.md` |
| **FR-023** | Claude (via a decision run) or the operator (via the local CLI) shall be able to revoke an authorization; on revocation running Codex processes for that task are stopped and no further side effects (push, PR, Linear write) occur for it. | Brief: area A versioned authorization, cancel | M | E2E: revocation during implementation stops the run ≤ 30 s (awake) and produces 0 pushes/PRs afterwards. | Test | TDD §9, §11 · `architecture/state-machine.md` |
| **FR-024** | If the Linear issue's spec (title + description + acceptance criteria) hash changes after authorization, the coordinator should pause the task before its next agent run and require Claude re-authorization. | Brief: versioned authorization; Discovery: specs live in issue descriptions | S | E2E: editing the sandbox issue description after authorization yields AWAITING_AUTHORIZATION (reason `spec_changed`) before the next Codex run. | Test | TDD §11, §12 · `architecture/state-machine.md` |

### FR — Scheduling, dispatch and execution control (content area A)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-040** | The coordinator shall hold all pending work in a durable local queue and dispatch jobs by lease, such that at most one active agent run exists per task at any time. | Brief: area A duplicate-execution prevention; baseline | M | TC-CONC-004: 0 instances of two concurrent runs for one task across 1000 simulated lease expiries. | Test | TDD §8, §16 · `architecture/components.md` |
| **FR-041** | The coordinator shall enforce configurable concurrency limits: global agent runs, per-agent-type (Claude, Codex) and per-repository (defaults per OD-07). | Brief: area A concurrency limits | M | TC-CONC-001: observed concurrent runs never exceed any configured limit over 1000 simulated steps with 20 queued tasks. | Test | TDD §8, §23 · `architecture/components.md` |
| **FR-042** | The dispatcher shall order authorized work by Claude-assigned priority, then authorization time, and shall not starve tasks waiting on capacity for more than a configured bound. | Brief: steps 2, 4 | S | Scheduler unit tests: priority order respected; no queued task waits > configured bound (default 24 h awake time) in simulation. | Test | TDD §8 · `architecture/components.md` |
| **FR-043** | Each side-effecting step shall carry a deterministic `dedup_key` so that re-execution after a crash or retry has at most one external effect (exactly-once effect). | Brief: area A duplicate-execution prevention; area B dedup IDs | M | See NFR-001 (crash-injection: 0 duplicate side effects). | Test | TDD §10, §20 · `protocols/messages.md; operations/recovery.md` |
| **FR-044** | The coordinator shall detect agent failure by wall-clock deadline, progress-silence timeout and exit classification, and shall terminate the run's whole process group (SIGINT → SIGTERM → SIGKILL with grace periods). | Discovery fact 8; runtimes §1.9 | M | Hung fake agent with 3 descendant processes: all terminated within deadline + grace (≤ 45 s default); 0 surviving descendants. | Test | TDD §13, §18, §20 · `operations/recovery.md; integrations/codex.md` |
| **FR-045** | Each step shall have a bounded retry policy with exponential backoff for transient failures (network, rate limit, agent API retry) and shall route non-transient failures to FAILED or BLOCKED with escalation. | Brief: area C retry limits | M | Retry calculator tests; E2E with injected transient errors completes; injected permanent error yields exactly one escalation. | Test | TDD §11, §20 · `architecture/state-machine.md` |
| **FR-046** | The operator (CLI) and Claude (decision) shall be able to cancel a task from any non-terminal state; cancellation stops running processes, records the reason, leaves the task in CANCELLED and schedules worktree cleanup per FR-184. | Brief: area A cancel/resume | M | TC-SM-010: cancel succeeds from every non-terminal state; 0 processes survive; 0 side effects after cancel timestamp. | Test | TDD §11 · `architecture/state-machine.md` |
| **FR-047** | The operator shall be able to pause and resume a task; resume continues from the last durable checkpoint without repeating completed side effects. | Brief: area A cancel/resume | M | TC-SM-011: pause/resume from every pausable state; 0 repeated side effects. | Test | TDD §11, §20 · `architecture/state-machine.md` |
| **FR-048** | Only one coordinator instance may run per data directory (single-writer lock); auxiliary processes (CLI) shall read the store read-only or act via coordinator IPC. | Brief: area A multi-process coordination; Discovery fact 11 | M | Starting a second instance exits non-zero with a clear message within 5 s; DB writes from CLI go through IPC (inspection). | Test + Inspection | TDD §8, §16, §18 · `architecture/components.md` |
| **FR-049** | The coordinator shall expose task status (state, step, age, attempt counts, next deadline, waiting-on) through the local CLI. | Brief: area A status | M | `mercury status` returns all non-terminal tasks in ≤ 2 s with the listed fields. | Demo + Test | TDD §8, §21 · `architecture/components.md` |

### FR — Agent communication and contracts (content area B)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-060** | Every message exchanged between coordinator components and agent adapters shall use the versioned envelope (`schema`, `message_id`, `correlation_id`, `causation_id`, `dedup_key`, `occurred_at`, `issue`, `repo`, `run_id` where applicable). | Brief: area B; baseline identifier conventions | M | Envelope validator rejects messages missing any required field (one mutant per field). | Test | TDD §10, §17 · `protocols/messages.md` |
| **FR-061** | Message schemas shall exist for: task authorization, task assignment, implementation plan, plan review, plan approval, plan revision request, implementation progress, test results, PR creation, code review, security findings, revision requests, completion and failure events; each is validated on produce and consume. | Brief: area B | M | Every schema has ≥ 1 golden valid example and ≥ 3 invalid mutants in the contract suite; 100% pass. | Test | TDD §10, §17 · `protocols/messages.md; protocols/schemas/` |
| **FR-062** | Agent outputs shall be validated against the step's JSON Schema; a missing or schema-invalid output (including Claude `success` without `structured_output`) is a run failure, never a success. | Discovery: runtimes §2.1 result subtypes | M | Contract tests for each adapter and error subtype pass; TC-AFS-005 shows invalid output never advances state. | Test | TDD §13, §14, §17 · `integrations/claude.md; integrations/codex.md` |
| **FR-063** | Messages and external-effect intents shall be persisted before they are acted on (transactional inbox/outbox) and consumers shall be idempotent by `dedup_key`. | Discovery fact 12 (missed replies) | M | Duplicate delivery of 100 messages produces 100 effects, not 200; kill between persist and act loses 0 messages. | Test | TDD §10, §16, §20 · `protocols/messages.md; operations/recovery.md` |
| **FR-064** | Artifacts (plans, reviews, test reports, diff summaries) shall be immutable files in the MERCURY data directory (outside any worktree), referenced by ID and SHA-256, and verified on read. | Baseline: Artifact; Discovery: plan-as-file-in-worktree pain | M | Tampering with a stored artifact is detected on next read (hash mismatch → integrity alert); no artifact path is inside a worktree. | Test | TDD §10, §16 · `protocols/messages.md` |
| **FR-065** | Consumers should accept the current and previous minor version of each schema; breaking changes require a new major schema name. | Brief: area B schema versions | S | Contract suite validates N and N-1 examples for every schema. | Test | TDD §17 · `protocols/messages.md` |

### FR — Workflow state machine (content area C)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-080** | The coordinator shall implement the lifecycle state machine defined in architecture/state-machine.md and shall reject (and audit) any transition not in the transition table. | Brief: area C | M | TC-SM-001 accepts 100% of table transitions with guards true; TC-SM-002 rejects 100% of other (state, event) pairs. | Test | TDD §11 · `architecture/state-machine.md` |
| **FR-081** | Each transition shall record initiator, event, guard results, evidence references and timestamps in the same database transaction as the state change. | Brief: area C required evidence, persistent changes | M | Crash between state write and evidence write is impossible by construction (single transaction); TC-SM-003 verifies all fields present on 100% of transitions. | Test + Inspection | TDD §11, §16 · `architecture/state-machine.md` |
| **FR-082** | Each non-terminal state shall define a timeout and timeout action; timeouts are evaluated against wall-clock deadlines and awake-time budgets so that sleep gaps are treated as pauses. | Brief: area C timeouts; Discovery fact 10 | M | Virtual-clock test: 8 h sleep gap during IMPLEMENTING does not fire a failure; awake-time overrun does. | Test | TDD §11, §18, §20 · `architecture/state-machine.md; operations/recovery.md` |
| **FR-083** | Terminal states (COMPLETED, FAILED, CANCELLED) shall be absorbing; MERGED shall transition to COMPLETED only after post-merge verification and Linear update succeed. | Brief: area C terminal states; step 14 | M | TC-SM-006: 0 transitions out of terminal states; COMPLETED never reached without verification evidence. | Test | TDD §11 · `architecture/state-machine.md` |
| **FR-084** | State evolution shall be deterministic: replaying a task's recorded event log yields the identical state and counters. | Quality gate: deterministic lifecycle | M | TC-SM-005: replay equality for 10,000 generated event logs. | Test | TDD §11, §16 · `architecture/state-machine.md` |

### FR — Codex planning and Claude plan review (content area D; operating model 5–7)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-100** | For an authorized task the coordinator shall run Codex in planning mode (read-only sandbox, task worktree) and store the resulting plan as an immutable plan version (`pln_`, SHA-256) validated against the plan schema. | Brief: step 5 | M | E2E: plan artifact stored with hash; Codex argv contains `--sandbox read-only` and `--output-schema`. | Test | TDD §13 · `integrations/codex.md` |
| **FR-101** | Claude shall review each plan version against: spec compliance, acceptance-criteria coverage, architecture, dependencies, security, test strategy, scope, feasibility, maintainability; the verdict is machine-readable with per-criterion result, findings (ID, severity, location, required change) and explicit approval conditions. | Brief: step 6; area D | M | Plan-review schema enforces all 9 criteria; contract test rejects outputs missing any criterion. | Test | TDD §14 · `integrations/claude.md; protocols/messages.md` |
| **FR-102** | A plan approval record shall bind to the exact plan version hash and the current authorization version; any new plan version supersedes and invalidates prior approvals. | Brief: hard constraint; Invariant 2 | M | See CON-006 (TC-SM-007). | Test | TDD §11, §14 · `architecture/state-machine.md` |
| **FR-103** | On `revise`, the coordinator shall deliver Claude's actionable findings to Codex (resuming its session where possible) and store the resulting new plan version. | Brief: step 7; Discovery: JAM-204 M1–M5 findings | M | E2E: 2 revision cycles produce pln v1→v3 each linked to the review that caused it. | Test | TDD §13, §14 · `integrations/codex.md` |
| **FR-104** | Plan review cycles shall be limited (default 3 per authorization, OD-08); exceeding the limit escalates to the operator and blocks the task. | Brief: bounded revision cycles | M | TC-E2E-003: 4th rejection → BLOCKED + exactly 1 notification. | Test | TDD §11, §14 · `architecture/state-machine.md` |
| **FR-105** | Issues labelled `Security` (configurable) shall require an explicit security pass in plan review and PR review; a non-pass cannot be auto-approved. | Discovery: Security label, JAM-251 checklist | M | E2E with Security label: approval without security pass is rejected by the guard. | Test | TDD §14, §19 · `integrations/claude.md; security/threat-model.md` |
| **FR-106** | Claude may auto-approve a plan only when all mandatory criteria pass (policy per OD-11); conditional approvals record conditions that PR review must check. | Brief: step 7; area D explicit approval conditions | M | Guard test: approve with any failing mandatory criterion is rejected; conditions appear in PR-review input. | Test | TDD §14 · `integrations/claude.md` |

### FR — Implementation and testing (operating model 8–9; content area E/F)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-120** | The coordinator shall create one isolated git worktree per task from the base branch at a recorded base SHA, outside TCC-protected folders, with a branch name that contains the Linear identifier. | Brief: step 8; Discovery: branch naming drives Linear auto-link | M | Worktree path under configured root; branch matches `<prefix>/<issue-lower>-<slug>` regex; base SHA recorded. | Test | TDD §13, §15 · `integrations/github.md; operations/macos-service.md` |
| **FR-121** | The coordinator shall start a Codex implementation run (workspace-write sandbox, network off, minimal environment) only after FR-022 and the plan-approval gate pass, with the approved plan artifact as input. | Brief: step 8; Invariants 1–2 | M | Spawn audit shows both gate results for 100% of implementation runs; argv contains approved flags only. | Test + Inspection | TDD §13 · `integrations/codex.md` |
| **FR-122** | The coordinator shall execute the repository's configured test commands for the task and store a test-results artifact (commands, exit codes, counts, durations, log hash). | Brief: step 9; Discovery: evidence vs claims | M | Test-results artifact exists for 100% of PRs; PR body test summary matches artifact. | Test | TDD §13, §22 · `integrations/codex.md` |
| **FR-123** | Dependency installation needed by an implementation shall be performed by a coordinator-controlled step from lockfiles, not by Codex with network access (subject to OD-09). | Discovery: runtimes R2 | S | Codex run records show `network_access=false`; install step logged separately. | Test + Inspection | TDD §13 · `integrations/codex.md` |
| **FR-124** | Before committing, the coordinator shall compare the worktree diff against the approved plan's declared scope and shall refuse to commit changes to protected paths (e.g. CI workflows, CODEOWNERS, agent instruction/config files) unless the authorization explicitly permits them; exact path policy owned by SEC. | Discovery: AGENTS.md editable by Codex; runtimes §3.3 | M | Diff-guard tests: out-of-scope and protected-path changes block commit and return a revision request. | Test | TDD §13, §19 · `integrations/codex.md; security/threat-model.md` |
| **FR-125** | Codex progress (JSONL events) shall be converted into implementation-progress messages so stall detection and the audit trail reflect real activity. | Discovery: stalls without detection | M | Progress events recorded at ≥ 1 per completed Codex item; silence > configured threshold triggers FR-044. | Test | TDD §13, §21 · `integrations/codex.md` |

### FR — Git operations and pull requests (content area E; operating model 9)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-140** | The coordinator (not Codex or Claude) shall commit, push and open the PR using the MERCURY agent identity. | Discovery: runtimes R4, fact 7 | M | All sandbox PRs and commits are authored/pushed by the agent identity; agent processes hold no GitHub credentials. | Test | TDD §13, §15 · `integrations/github.md` |
| **FR-141** | Commits shall follow the commit convention with trailers for Linear issue, task ID, authorization ID and run ID. | Brief: area E commit conventions | S | Trailer parser finds all 4 trailers on 100% of MERCURY commits. | Test | TDD §15 · `integrations/github.md` |
| **FR-142** | The PR body shall be rendered from the PR template and contain the Linear link (magic word per OD-06), authorization ID+version, plan version+hash, test summary, and review status; the operator is requested as reviewer. | Brief: area E PR template, Linear linking; step 12 | M | Template renderer golden test; sandbox PR shows Linear linkback and a review request to the operator. | Test | TDD §15 · `integrations/github.md` |
| **FR-143** | PR creation shall be idempotent: before creating, the coordinator looks up an existing PR for the head branch; at most one open PR exists per task. | Brief: area A duplicates | M | Crash/timeout after create request but before response: retry yields the same PR (0 duplicates across 1000 crash-injection runs). | Test | TDD §15, §20 · `integrations/github.md; operations/recovery.md` |
| **FR-144** | The coordinator shall poll required check results for the PR head SHA and route failures to a bounded Codex CI-fix loop (default 2) or escalate. | Brief: area E checks; area G CI failures | M | E2E: failing check → fix run → green; persistent failure → BLOCKED + 1 notification. | Test | TDD §15 · `integrations/github.md` |

### FR — Claude PR review and revision loops (operating model 10–11)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-160** | Claude shall independently review each PR head SHA for functionality, maintainability, security, spec compliance, plan conformance and plan-approval conditions, returning a schema-valid verdict with findings. | Brief: step 10; area E | M | PR-review schema contract tests pass; verdict bound to head SHA in store. | Test | TDD §14 · `integrations/claude.md` |
| **FR-161** | A security review verdict (separate finding list, severity) shall be produced for every PR and is blocking for findings at or above the configured severity. | Brief: area E Claude security review | M | E2E: blocking security finding → CHANGES_REQUESTED regardless of functional verdict. | Test | TDD §14, §19 · `integrations/claude.md; security/threat-model.md` |
| **FR-162** | Review results shall be persisted as artifacts and posted to GitHub by the coordinator as a `COMMENT` or `REQUEST_CHANGES` review from the agent identity, never `APPROVE`. | Discovery: platform G4 | M | Sandbox: 100% of MERCURY reviews have event COMMENT/REQUEST_CHANGES; static check finds no APPROVE literal on the review path. | Test + Inspection | TDD §15 · `integrations/github.md` |
| **FR-163** | On `changes_requested`, the coordinator shall send actionable revision requests to Codex, and the new head is re-reviewed; PR review cycles are bounded (default 3, OD-08) with escalation. | Brief: step 11; bounded cycles | M | TC-E2E-004 passes; 4th failing review → BLOCKED + 1 notification. | Test | TDD §11, §14 · `architecture/state-machine.md` |
| **FR-164** | On a passing review, the task shall enter AWAITING_HUMAN_APPROVAL and the operator shall be notified through GitHub (review request) and, where configured, Linear. | Brief: step 12 | M | Sandbox: review request to operator present within NFR-043 bound. | Test | TDD §11, §15 · `integrations/github.md` |
| **FR-165** | Any new commit on the PR head after a Claude pass (including operator or third-party pushes) shall invalidate the pass and trigger re-review. | Brief: plan/PR approval binding by analogy; Discovery: approval of most recent push | M | E2E: human push to PR → state returns to CLAUDE_PR_REVIEW for new SHA. | Test | TDD §11, §14 · `architecture/state-machine.md` |

### FR — Merge verification and post-merge (operating model 13–14)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-180** | The coordinator shall never approve or merge a pull request and shall contain no code path invoking GitHub merge or approve endpoints. | Brief: step 13; platform G6 | M | Static analysis: 0 references to merge endpoints/`APPROVE`; network log over all tests: 0 merge calls. | Inspection + Test | TDD §15 · `integrations/github.md` |
| **FR-181** | After a merge is observed, the coordinator shall verify: `merged=true`, `merged_by` equals the configured operator login, an operator APPROVED review on the final head SHA, merge commit reachable on base branch, and required checks successful on the head SHA. | Brief: step 14; platform G7 | M | Predicate tests for each failing condition; sandbox merge by operator verifies OK. | Test | TDD §15 · `integrations/github.md` |
| **FR-182** | A failed merge verification shall raise a security escalation and keep the task out of COMPLETED. | Brief: area G security escalation; CON-014 | M | TC-GOV-004: non-operator merge → alert within 10 min, task state MERGE_UNVERIFIED/BLOCKED. | Test | TDD §15, §19 · `integrations/github.md; security/threat-model.md` |
| **FR-183** | Post-merge Linear updates (status, comment, attachment) shall be idempotent and consistent with the chosen Linear status ownership rule (OD-06), never fighting Linear's GitHub integration. | Discovery: integrations constraint 3; platform L2 | M | Sandbox: exactly one MERCURY comment and final state Done; 0 status flaps observed over 10 min. | Test | TDD §12 · `integrations/linear.md` |
| **FR-184** | The coordinator shall remove the task worktree and local branch after verified merge or cancellation once no unpushed commits or uncommitted changes remain (or after preserving them as an artifact), retaining all artifacts. | Brief: area F safe worktree cleanup | S | Cleanup refuses when unsaved changes exist; artifacts remain after cleanup. | Test | TDD §13, §18 · `operations/recovery.md` |
| **FR-185** | A PR closed without merge shall transition the task to a defined state (CANCELLED if closed by operator; Claude decision otherwise) with one notification. | Brief: area C completeness | S | E2E: closed PR → CANCELLED with reason `pr_closed`. | Test | TDD §11, §15 · `architecture/state-machine.md` |

### FR — Linear projection

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-200** | The coordinator shall project internal state onto the team's Linear workflow states via a configured mapping (internal states → 7 Linear states) and decision comments; the internal store remains authoritative. | Discovery: 7 states; integrations constraint 4 | M | Mapping table covers all internal states; projection unit tests. | Test | TDD §12 · `integrations/linear.md` |
| **FR-201** | Linear writes shall be attributable to a non-human actor (OAuth `actor=app` or equivalent per OD-05). | Discovery fact 3; platform L5 | M | Sandbox comments show the app actor as author. | Test | TDD §12 · `integrations/linear.md` |
| **FR-202** | Linear writes shall be idempotent (deterministic client IDs / upsert) with at most one comment per decision event. | Platform L4 | M | Network-interrupted write retried → 1 comment. | Test | TDD §12, §20 · `integrations/linear.md` |
| **FR-203** | No Linear text (description, comment, label) shall be interpreted as an authorization, approval or operator command. | Discovery: integrations constraint 10 | M | TC-GOV-006 and TC-PI-002 pass. | Test | TDD §12, §19 · `integrations/linear.md; security/threat-model.md` |

### FR — Human notifications (content area G)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-220** | The coordinator shall notify the operator for: repeated plan-review failure, decisions needing human judgment, security escalation, unrecoverable failures, PR ready for approval, CI failures needing intervention and merge completion, using GitHub review requests/@mentions and Linear comments/mentions. | Brief: area G | M | Sandbox: each of the 7 classes delivered through its configured channel. | Test | TDD §12, §15, §21 · `integrations/github.md; integrations/linear.md` |
| **FR-221** | Notifications shall be deduplicated by (task, class, state-entry) and never sent for unchanged status. | Discovery: 'report only on change' rule | M | TC-DUP-005: 0 repeated notifications across 100 unchanged polls; 1 per state entry. | Test | TDD §21 · `architecture/components.md` |
| **FR-222** | After a coordinator downtime or sleep longer than a configured threshold with in-flight tasks, the coordinator should send one summary notification on resume. | Discovery: unnoticed stalls | S | TC-REC-009: one summary per downtime episode. | Test | TDD §20, §21 · `operations/recovery.md` |
| **FR-223** | Undelivered notifications shall be persisted and retried with backoff until delivered or expired; delivery failure is itself logged. | Discovery: DNS notification failure needing manual retry | M | Network-down during notify → delivered once after recovery. | Test | TDD §21 · `architecture/components.md` |

### FR — Operator control

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-240** | A local CLI (`mercury`) shall provide status, show, cancel, pause, resume, retry, revoke, audit and health commands, restricted to the local operator account, with every mutating command audited. | Brief: areas A, F, I | M | CLI integration tests per command; audit event for each mutating command. | Test | TDD §8, §18 · `architecture/components.md` |
| **FR-241** | The operator shall resolve escalations (extend a cycle limit, request re-authorization, abandon) through an authenticated channel that agents cannot write to (local CLI; others per OD-12). | Discovery: JAM-160 approvals moved off Slack | M | Escalation resolution via CLI recorded with operator identity; GitHub/Linear comments cannot resolve escalations. | Test | TDD §9, §19 · `architecture/components.md; security/threat-model.md` |

### FR — Audit queries (content area I)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-260** | `mercury audit <task\|issue\|pr>` shall answer the ten brief §I questions: originating Linear issue; authorizing Claude record; approved plan version; Codex run(s) producing code; tests run and results; commits/PR; what Claude reviewed; security findings; who approved/merged; what happened after failures/restarts. | Brief: area I | M | TC-E2E-010: all 10 answers present and correct for E2E tasks incl. one with crash/restart. | Test | TDD §21 · `architecture/components.md` |
| **FR-261** | Every state transition, agent run (argv sans secrets, versions, exit, cost/tokens), external write and operator action shall produce an audit event linked by correlation and causation IDs. | Brief: area I | M | See NFR-060. | Test | TDD §21 · `architecture/components.md` |

### FR — Recovery (content area F; operating model 15)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-280** | On start, the coordinator shall recover every non-terminal task: reconcile recorded runs with live processes, reconcile external state (branch, PR, reviews, Linear) and resume or re-queue from the last durable checkpoint. | Brief: step 15; area F | M | TC-REC-001/004: 100% of non-terminal tasks recovered; 0 duplicates. | Test | TDD §20 · `operations/recovery.md` |
| **FR-281** | The coordinator shall reap orphaned agent processes using recorded pid, pgid and process start time (PID-reuse safe). | Discovery fact 10 (detached children escape launchd) | M | TC-REC-005: orphans killed; unrelated process with reused PID untouched. | Test | TDD §18, §20 · `operations/recovery.md` |
| **FR-282** | The coordinator shall detect wake from sleep (wall vs monotonic clock gap), probe connectivity with backoff, then re-evaluate deadlines and resume polling. | Platform §4.4 | M | Real-Mac sleep test: polling resumes ≤ 120 s after network available. | Test | TDD §18, §20 · `operations/macos-service.md; operations/recovery.md` |
| **FR-283** | During connectivity loss, the coordinator shall pause external effects, queue intents durably and resume without state corruption. | Brief: area F retry after connectivity loss | M | TC-NET-001..003 pass. | Test | TDD §20 · `operations/recovery.md` |

### FR — Migration from Slack workflow

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-300** | During the pilot, MERCURY-managed issues shall be explicitly marked (label per OD-10) and excluded from the legacy script workflow so that no issue is driven by both systems. | Discovery fact 2, integrations constraint 11 | M | Pilot log: 0 issues with both legacy gate files and MERCURY tasks. | Inspection + Demo | TDD §24, §27 · `planning/roadmap.md` |
| **FR-301** | After pilot exit criteria are met, Slack-based coordination for MERCURY-managed work shall be disabled and its bot token revoked. | Discovery fact 12; brief mission (replace Slack) | M | 2 weeks: 0 Slack posts for MERCURY tasks; Slack token revocation recorded. | Inspection | TDD §24, §27 · `planning/roadmap.md` |

### FR — Explicitly out of scope for this release (Won't)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **FR-900** | MERCURY will not provide a web dashboard or mobile app. | Brief: prefer existing notifications | W | No HTTP UI exists (inspection). | Inspection | TDD §3 · `architecture/overview.md` |
| **FR-901** | MERCURY will not accept inbound webhooks or expose any public endpoint (webhook payloads may only ever be hints, if a later ADR allows a relay). | Brief: no public inbound | W | See CON-002. | Inspection | TDD §3, §7 · `architecture/overview.md` |
| **FR-902** | MERCURY will not merge, approve, or enqueue PRs for merge, even when all checks pass. | Brief: step 13 | W | See FR-180. | Inspection | TDD §3, §15 · `integrations/github.md` |
| **FR-903** | MERCURY will not run on more than one Mac or provide high availability; one coordinator per operator. | Brief: locally hosted | W | Single-instance lock (FR-048). | Inspection | TDD §3 · `architecture/overview.md` |
| **FR-904** | MERCURY will not use Linear-native agent delegation / coding sessions or Codex Cloud as an execution path. | Discovery fact 5; CON-016 | W | See FR-005. | Inspection | TDD §3, §12 · `integrations/linear.md` |

### NFR — Reliability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-001** | External side effects (Codex run per step, push, PR, GitHub review, Linear comment, notification) shall be exactly-once in effect under crashes and retries. | Brief: area A; Discovery: duplicate/junk posts | M | 0 duplicate side effects across 1000 randomized crash-injection runs covering every instrumented crash point at least 10 times. | Test | TDD §20 · `operations/recovery.md` |
| **NFR-002** | After a coordinator crash, launchd shall restart it and it shall resume processing within 60 s of process start. | Platform M1 | M | 10 kill -9 trials on the Mac: restart ≤ 30 s, health OK ≤ 60 s in 10/10. | Test | TDD §18, §20 · `operations/macos-service.md` |
| **NFR-003** | Stalls shall be detected: any task not waiting on a human with no progress beyond its state timeout is flagged within timeout + 2 poll intervals of awake time. | Discovery: 14 h unnoticed stall | M | Fault tests: 100% of injected stalls detected within bound; pilot max undetected stall within bound. | Test | TDD §20, §21 · `operations/recovery.md` |
| **NFR-004** | During the pilot the coordinator shall be healthy for ≥ 99% of minutes in which the Mac is awake and the operator is logged in. | Discovery: monitoring only while chat open | S | Heartbeat log analysis over pilot ≥ 99%. | Analysis | TDD §20 · `operations/macos-service.md` |
| **NFR-005** | No GitHub or Linear state change relevant to an active task shall be missed, including across network interruptions and sleep. | Discovery: missed replies | M | Sandbox replay of 500 events with 20 injected interruptions: 0 missed. | Test | TDD §12, §15, §20 · `integrations/github.md; integrations/linear.md` |

### NFR — Recoverability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-020** | After kill -9, simulated power loss or reboot, 100% of non-terminal tasks shall resume or reach a defined state, and the database shall pass `quick_check`. | Brief: step 15; area F | M | TC-REC-001/002/004 pass with 0 lost tasks and 0 integrity errors. | Test | TDD §20 · `operations/recovery.md` |
| **NFR-021** | No task shall fail solely due to a sleep gap of any duration; processing resumes within 120 s after network becomes available on wake. | Discovery fact 10 | M | See TC-REC-003 / TC-NET-004. | Test | TDD §18, §20 · `operations/macos-service.md` |
| **NFR-022** | The store shall be backed up online at least daily; a restore drill shall recover a consistent store in ≤ 15 min with ≤ 24 h data loss (backup RPO). | Platform P2 | M | Restore drill timed; restored DB passes integrity_check and coordinator reconciles. | Test + Demo | TDD §20, §24 · `operations/recovery.md` |
| **NFR-023** | Schema migrations shall take a backup first and be forward-only within a transaction; a failed migration leaves the prior DB usable. | Platform P2 | M | Injected migration failure → original DB intact and openable. | Test | TDD §16, §24 · `operations/recovery.md` |
| **NFR-024** | On SIGTERM (logout, shutdown, launchctl bootout) the coordinator shall stop dispatching, checkpoint state, signal child process groups and exit within the configured ExitTimeOut (≥ 30 s). | Platform M1–M2 | M | 10/10 SIGTERM trials: exit before ExitTimeOut, checkpoint written, children signalled; next start recovers cleanly. | Test | TDD §18, §20 · `operations/macos-service.md` |

### NFR — Latency while awake (defaults; tunable)

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-040** | A relevant Linear change shall be observed within p95 ≤ 2 × Linear poll interval (default 60 s → 120 s). | Brief: event-driven; platform E3 | S | TC-PERF-002 over ≥ 100 sandbox changes. | Test | TDD §12, §23 · `integrations/linear.md` |
| **NFR-041** | GitHub review, check and merge events for active PRs shall be observed within p95 ≤ 120 s. | Platform E1 | S | TC-PERF-002 over ≥ 100 sandbox events. | Test | TDD §15, §23 · `integrations/github.md` |
| **NFR-042** | An authorized task with free capacity shall have its Codex run spawned within 30 s. | Brief: step 4 | S | TC-PERF-003 p95 ≤ 30 s. | Test | TDD §8, §23 · `architecture/components.md` |
| **NFR-043** | The operator shall be notified that a PR is ready for approval within 5 min of Claude's passing review. | Brief: step 12 | S | Sandbox p95 ≤ 5 min. | Test | TDD §15, §21 · `integrations/github.md` |
| **NFR-044** | Post-merge verification and Linear update shall complete within 10 min of merge (awake). | Brief: step 14 | S | Sandbox p95 ≤ 10 min. | Test | TDD §15, §12 · `integrations/github.md` |

### NFR — Durability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-050** | Committed state transitions shall survive power loss: SQLite WAL with `synchronous=FULL` and `fullfsync=ON`, verified by startup self-check. | Discovery fact 11; platform P1 | M | Startup self-check refuses to run with other pragma values; TC-REC-002 0 lost commits. | Inspection + Test | TDD §16, §20 · `operations/recovery.md` |
| **NFR-051** | Artifacts shall be written atomically (temp file + fsync + rename) and hash-verified on read. | Baseline: Artifact | M | Crash mid-write leaves no partial artifact visible. | Test | TDD §16 · `protocols/messages.md` |
| **NFR-052** | `PRAGMA quick_check` shall run at startup and `integrity_check` daily; failures stop dispatch and alert the operator. | Platform P2 | M | Corrupted DB fixture → refuse dispatch + notification. | Test | TDD §16, §20 · `operations/recovery.md` |

### NFR — Auditability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-060** | 100% of state transitions, agent runs and external writes shall have audit events with correlation_id; a task's history shall be reconstructable from the audit log alone. | Brief: area I | M | Audit-completeness checker over E2E corpus: 0 gaps. | Test | TDD §21 · `architecture/components.md` |
| **NFR-061** | Retention (defaults, OD-15): audit events and artifacts ≥ 1 year; operational logs ≥ 90 days; configurable; deletion itself audited. | Brief: area I retention | S | Config inspection; housekeeping test deletes only beyond retention. | Inspection + Test | TDD §21 · `architecture/components.md` |
| **NFR-062** | Logs shall be structured JSON with timestamp (RFC 3339 UTC), level, component, correlation/causation IDs, and pass through the redaction filter (patterns owned by SEC). | Brief: area I log structure, redaction | M | Log schema validation over E2E logs: 100% conformant; canary test passes. | Test | TDD §21 · `architecture/components.md; security/threat-model.md` |

### NFR — Operability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-070** | Install, upgrade and uninstall shall each be a single documented command that renders the LaunchAgent plist and is reversible. | Brief: area F; §24 | M | TC-OPS-001 on a clean macOS user account. | Demo | TDD §18, §24 · `operations/macos-service.md` |
| **NFR-071** | `mercury health` shall report poller lag, last successful poll per source, queue depth, DB status, agent CLI versions and governance-check status within 2 s. | Brief: area F supervision | M | TC-OPS-002. | Test | TDD §21 · `architecture/components.md` |
| **NFR-072** | Configuration shall be schema-validated at startup; invalid configuration prevents start with an actionable error. | Operability | M | TC-OPS-003: 10 invalid configs → 10 refusals with field-level messages. | Test | TDD §8, §24 · `architecture/components.md` |
| **NFR-073** | A runbook shall exist for every escalation and alert class. | Brief: area G | S | Runbook walkthrough demo per class. | Demo + Inspection | TDD §20, §21 · `operations/recovery.md` |

### NFR — Resource usage

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-080** | Idle coordinator (no active runs) shall use ≤ 250 MB RSS and ≤ 2% of one CPU core averaged over 1 h. | Mac is the operator's workstation | S | 24 h soak: TC-PERF-001. | Test | TDD §23 · `architecture/components.md` |
| **NFR-081** | Non-304 GitHub API usage shall stay ≤ 20% of the identity's hourly primary limit at 10 active PRs; Linear usage ≤ 20% of its hourly limit. | Platform §2 rate budget | M | TC-SBX-008 1 h measurement. | Test | TDD §23 · `integrations/github.md; integrations/linear.md` |
| **NFR-082** | The coordinator shall cap live worktrees and refuse new dispatch when free disk falls below a configured threshold (default 10 GB). | Resource safety | S | Disk-threshold fake triggers refusal + one notification. | Test | TDD §23 · `operations/macos-service.md` |
| **NFR-083** | Per-run agent limits (Claude `maxTurns`/`maxBudgetUsd`; Codex token caps and wall-clock) and per-task budget totals shall be enforced and recorded. | Discovery: runtimes §1.9, §3.6 | M | Exceeding any limit ends the run with classified reason; cost/tokens recorded per run. | Test | TDD §13, §14, §23 · `integrations/claude.md; integrations/codex.md` |

### NFR — Portability and version pinning

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-090** | Node.js, coordinator dependencies (lockfile), Claude Code / Agent SDK and Codex CLI shall be pinned to exact versions; startup self-test refuses to run on version mismatch. | Discovery: runtimes §6 V1–V5 | M | Self-test fails with mismatched fake binary version. | Test | TDD §24 · `integrations/claude.md; integrations/codex.md` |
| **NFR-091** | SQLite access shall be behind a repository interface allowing `node:sqlite` or `better-sqlite3`; the test suite runs against both. | Platform P3 | S | CI matrix passes for both drivers. | Test | TDD §16 · `architecture/components.md` |
| **NFR-092** | All MERCURY paths (DB, logs, artifacts, worktrees) shall be outside TCC-protected folders and require no Full Disk Access. | Platform M6 | M | Install self-check rejects protected paths; TC-P0-011 verified. | Test + Inspection | TDD §18 · `operations/macos-service.md` |
| **NFR-093** | Agent CLI contract tests shall run against each pinned version before an upgrade is accepted. | Discovery: runtimes V6 | M | Upgrade procedure blocks when contract suite fails. | Demo | TDD §24 · `integrations/codex.md` |
| **NFR-094** | The supported macOS version(s) shall be those verified in Phase 0; sandbox and launchd self-tests shall be re-run after each macOS update. | Discovery: runtimes V8 | S | Self-test report stored per OS build. | Demo | TDD §18, §24 · `operations/macos-service.md` |

### NFR — Maintainability and testability

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **NFR-100** | Claude, Codex, GitHub, Linear, clock and process-spawner shall be behind interfaces with fakes; core modules (state machine, gates, scheduler) reach 100% branch coverage and the rest ≥ 85% line coverage. | Brief: area J | S | Coverage report in CI. | Inspection | TDD §22 · `testing/verification-plan.md` |
| **NFR-101** | The coordinator shall support deterministic simulation (virtual clock, seeded randomness) for state-machine, recovery and concurrency tests. | Brief: area J | M | Same seed → identical trace in 100/100 runs. | Test | TDD §22 · `testing/verification-plan.md` |

### OPS — Operational requirements

| ID | Requirement | Rationale / source | Pri | Acceptance criterion (pass/fail) | Verification | Owning design |
|---|---|---|---|---|---|---|
| **OPS-001** | A read-only Phase 0 verification checklist shall be executed on the operator's Mac and its results recorded before M1 (Mac-dependent items) and before the milestone each item gates. | Discovery fact 1 | M | Phase 0 report committed with each check Pass/Fail/Accepted and evidence. | Inspection | TDD §18, §27 · `operations/macos-service.md` |
| **OPS-002** | Agent identities shall be provisioned before any write integration: GitHub App (or machine user, OD-02) with least privilege on target repos, Linear app actor (OD-05), and human-only CODEOWNERS. | Discovery fact 3, 4 | M | Identity inventory lists each identity, permissions and owner; TC-GOV-008 passes. | Inspection | TDD §15, §19 · `integrations/github.md; integrations/linear.md` |
| **OPS-003** | Repository governance (rulesets/branch protection, CODEOWNERS, Actions-approval setting) shall be configured by the operator on each target repo and checked read-only by the coordinator at startup and daily; drift raises an alert and stops new dispatch to that repo. | Platform G3 | M | Sandbox drift (rule relaxed) → alert ≤ 24 h and dispatch paused for repo. | Test | TDD §15, §19 · `integrations/github.md` |
| **OPS-004** | A dedicated sandbox GitHub repository and Linear team shall exist for integration and governance tests; no automated test may write to production repos or teams. | Discovery: test-suite token leak (JAM-160) | M | Test config allow-list contains only sandbox targets; CI guard fails on any other target. | Inspection + Test | TDD §22 · `testing/verification-plan.md` |
| **OPS-005** | Upgrades (coordinator, Node, agent CLIs) shall follow a documented procedure with backup, contract tests and rollback. | Discovery: version churn | M | Upgrade + rollback demo. | Demo | TDD §24 · `operations/macos-service.md` |
| **OPS-006** | Backup and restore procedures shall be documented and drilled at least quarterly. | Platform P2 | S | Drill log. | Demo | TDD §20, §24 · `operations/recovery.md` |
| **OPS-007** | Secrets shall be provisioned in the login Keychain with documented rotation (procedure content owned by SEC). | Platform M5 | M | See SEC-020..029. | Inspection | TDD §19 · `security/threat-model.md` |
| **OPS-008** | The pilot on `network_monitor` shall proceed shadow → supervised → cutover with explicit exit criteria per stage. | Brief: replace Slack; Discovery fact 2 | M | Exit criteria in roadmap met and recorded. | Demo + Analysis | TDD §27 · `planning/roadmap.md` |
| **OPS-009** | Slack decommission for MERCURY-managed work: disable `slack-notify.sh` paths, revoke the coordination bot token, record the date. | Discovery fact 12 | M | See FR-301. | Inspection | TDD §24 · `planning/roadmap.md` |
| **OPS-010** | An incident runbook shall cover unauthorized merge/approval detection, credential compromise and governance drift. | Brief: area G security escalation | M | Tabletop walkthrough recorded. | Demo | TDD §19, §20 · `security/threat-model.md; operations/recovery.md` |
| **OPS-011** | Logs, artifacts and worktrees shall be rotated/cleaned per retention policy without manual action. | NFR-061 | S | Housekeeping test. | Test | TDD §21, §23 · `operations/macos-service.md` |
| **OPS-012** | The operator shall be told (via `mercury health` and a one-time notification) if the LaunchAgent is disabled in Login Items or not loaded. | Platform M7 | S | Disabled-agent check demo. | Demo | TDD §18 · `operations/macos-service.md` |


---

## 4. Security requirements (reserved for Agent E)

Agent E owns all `SEC-*` statements, controls and acceptance criteria in `security/threat-model.md`. This file only **reserves the ID ranges**, records each range's scope as the brief states it, and seeds the test linkage so the RTM has no orphan rows. When Agent E defines `SEC-0nn` requirements, each one goes into the matching range, its row is added to the RTM below, and the requirement text stays in the threat model (single source). The anchor IDs (SEC-001, -010, …) may be used by Agent E as real requirements or retired as range headers.

| Reserved range | Anchor ID | Scope (from brief §H / discovery; statements and controls owned by Agent E) | Pri | Acceptance criterion | Verification | Owning design | Seed test cases | Milestone |
|---|---|---|---|---|---|---|---|---|
| SEC-001–009 | **SEC-001** | Identity & authN: distinct, non-human identities for every agent/coordinator action (brief H authn/agent identity). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TC-SEC-002, TC-SBX-002 | P0 |
| SEC-010–019 | **SEC-010** | AuthZ & least privilege: minimal token scopes per identity; separation of duties author ≠ approver (brief H authz, least privilege). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TC-GOV-008 | P0 |
| SEC-020–029 | **SEC-020** | Credential management & secret redaction (brief H credential mgmt, secret redaction). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TC-SEC-004 | M1 |
| SEC-030–039 | **SEC-030** | Agent execution isolation: filesystem protections, command restrictions, tool permission boundaries, repo-config (hooks/.mcp.json) isolation (brief H; discovery fact 6, 7). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TC-P0-012, TC-SEC-001, TC-SEC-003, TC-SEC-005, TC-SEC-006, TC-SEC-007 | M3 |
| SEC-040–049 | **SEC-040** | Untrusted content & prompt-injection defenses: repo content, Linear text/comments, PR content (brief H). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TC-PI-001, TC-PI-002, TC-PI-003, TC-PI-004, TC-PI-005 | M3 |
| SEC-050–059 | **SEC-050** | Human approval enforcement & merge governance controls (brief H; invariant 4). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TC-GOV-001, TC-GOV-002, TC-GOV-003, TC-GOV-004 | M5 |
| SEC-060–069 | **SEC-060** | Audit integrity (tamper evidence of audit/event log) (brief H). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TBD (E) | M8 |
| SEC-070–079 | **SEC-070** | Supply chain & dependency security (agent CLIs, npm deps, repo dependencies) (brief H). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TBD (E) | M8 |
| SEC-080–089 | **SEC-080** | Security review & escalation process (Claude security review policy, severity thresholds) (brief E/H). | M | TBD by Agent E (must be measurable) | TBD (E) | TDD §19 · `security/threat-model.md` | TC-E2E-012 | M6 |


`SEC-090`–`SEC-099` are unassigned and available to Agent E.

Requirements in other ranges that depend on SEC content: CON-007, CON-008, CON-010, FR-124 (protected-path list), FR-161 (severity threshold), FR-203, NFR-062 (redaction patterns), OPS-002, OPS-007, OPS-010.

---

## 5. Provisional ADR keys

Agent A owns ADR numbering. The keys below name the decision each requirement depends on. Phase 4 replaces them with real `ADR-nnn` IDs and adds a mapping table here.

| Key | Decision topic | Main requirements |
|---|---|---|
| ADR-P01 | Coordinator runtime: Node.js LTS + TypeScript | NFR-080, NFR-090, NFR-091 |
| ADR-P02 | Durable store and job queue: SQLite WAL, single writer | FR-040, FR-043, FR-048, FR-063, FR-081, NFR-001, NFR-020, NFR-022, NFR-023, NFR-050, NFR-052, NFR-091 |
| ADR-P03 | Event intake by outbound polling (ETag / updatedAt); no inbound webhooks | CON-002, FR-001, FR-901, NFR-005, NFR-040, NFR-041, NFR-081 |
| ADR-P04 | Agent identities: GitHub App + Linear app actor; never human credentials | CON-007, CON-008, FR-140, FR-162, FR-201, OPS-002 |
| ADR-P05 | Merge governance on personal vs organization repos | CON-007, CON-014, FR-180, FR-181, FR-182, FR-902, OPS-003 |
| ADR-P06 | Coordinator (not agents) performs git commit/push and PR creation | FR-124, FR-140 |
| ADR-P07 | Claude invocation via Agent SDK with isolated profile (CLI --bare fallback) | FR-020, FR-062, FR-101, FR-160, NFR-090 |
| ADR-P08 | Codex invocation via supervised `codex exec` subprocess | CON-016, FR-062, FR-100, FR-103, FR-121, NFR-090 |
| ADR-P09 | Supervision via per-user LaunchAgent; sleep-tolerant timers | CON-002, CON-009, FR-082, FR-281, FR-282, FR-903, NFR-002, NFR-021, NFR-024, NFR-070, OPS-012 |
| ADR-P10 | Ownership of Linear status transitions vs Linear GitHub integration | FR-005, FR-142, FR-183, FR-200, FR-904 |
| ADR-P11 | Immutable, versioned, hash-bound authorization and approval records | CON-003, CON-004, CON-005, CON-006, FR-021, FR-022, FR-023, FR-024, FR-102, FR-203 |
| ADR-P12 | Notifications through GitHub/Linear native channels only | CON-011, FR-164, FR-220, FR-900, NFR-043 |
| ADR-P13 | Inter-agent communication via SQLite queue + JSON artifacts (not MCP/HTTP) | FR-060, FR-061, FR-063, FR-064 |
| ADR-P14 | Dependency installation outside the Codex sandbox | FR-123 |
| ADR-P15 | Filesystem layout: data and worktrees outside TCC-protected folders | FR-120, FR-184, NFR-092 |

---

## 6. Requirements Traceability Matrix

Columns: requirement → design section(s) → ADR(s) → test case(s) → milestone → status. `Status` is a design status today. After Phase 4 it tracks the §1.3 lifecycle, with an evidence link for `Verified`. Milestone keys are listed in §7.

| Req | Pri | TDD § | Supporting doc(s) | ADR(s) (provisional keys) | Test case(s) | Milestone | Status |
|---|---|---|---|---|---|---|---|
| CON-001 | M | §32, §27 | `reviews/` | — | TC-OPS-010 | P0 | Design: TBD (pending Phase 2 docs) |
| CON-002 | M | §7, §18 | `architecture/overview.md; operations/macos-service.md` | ADR-P03, ADR-P09 | TC-OPS-001, TC-SEC-008 | M1 | Design: TBD (pending Phase 2 docs) |
| CON-003 | M | §9 | `architecture/overview.md` | ADR-P11 | TC-SM-004, TC-OPS-010 | M1 | Design: TBD (pending Phase 2 docs) |
| CON-004 | M | §11, §12 | `architecture/state-machine.md; integrations/linear.md` | ADR-P11 | TC-E2E-006, TC-SBX-001, TC-SM-004 | M2 | Design: TBD (pending Phase 2 docs) |
| CON-005 | M | §9, §11, §13 | `architecture/components.md` | ADR-P11 | TC-UNIT-011, TC-SM-004 | M3 | Design: TBD (pending Phase 2 docs) |
| CON-006 | M | §11, §14 | `architecture/state-machine.md` | ADR-P11 | TC-UNIT-012, TC-SM-007 | M4 | Design: TBD (pending Phase 2 docs) |
| CON-007 | M | §15, §19 | `integrations/github.md; security/threat-model.md` | ADR-P04, ADR-P05 | TC-GOV-001, TC-GOV-002, TC-GOV-003, TC-GOV-008 | M5 | Design: TBD (pending Phase 2 docs) |
| CON-008 | M | §9, §15, §19 | `integrations/github.md; integrations/linear.md` | ADR-P04 | TC-SBX-002, TC-SBX-005, TC-P0-009 | P0 | Design: TBD (pending Phase 2 docs) |
| CON-009 | M | §18, §20 | `operations/macos-service.md; operations/recovery.md` | ADR-P09 | TC-SM-009, TC-REC-003 | M8 | Design: TBD (pending Phase 2 docs) |
| CON-010 | M | §19, §21 | `security/threat-model.md` | — | TC-SEC-004, TC-OPS-009 | M1 | Design: TBD (pending Phase 2 docs) |
| CON-011 | M | §7, §12, §15 | `integrations/github.md; integrations/linear.md` | ADR-P12 | TC-SBX-006 | M7 | Design: TBD (pending Phase 2 docs) |
| CON-012 | M | §11, §14 | `architecture/state-machine.md` | — | TC-SM-008, TC-E2E-003 | M4 | Design: TBD (pending Phase 2 docs) |
| CON-013 | M | §8, §12 | `architecture/components.md` | — | TC-UNIT-061, TC-E2E-001 | M1 | Design: TBD (pending Phase 2 docs) |
| CON-014 | M | §15, §19 | `integrations/github.md` | ADR-P05 | TC-GOV-004, TC-OPS-005 | M7 | Design: TBD (pending Phase 2 docs) |
| CON-015 | M | §18, §30 | `operations/macos-service.md` | — | TC-P0-001, TC-P0-002, TC-P0-003 | P0 | Design: TBD (pending Phase 2 docs) |
| CON-016 | M | §13 | `integrations/codex.md` | ADR-P08 | TC-INT-005, TC-E2E-014 | M4 | Design: TBD (pending Phase 2 docs) |
| CON-017 | M | §5, §29 | `planning/traceability.md` | — | TC-OPS-010 | P0 | Design: TBD (pending Phase 2 docs) |
| FR-001 | M | §12 | `integrations/linear.md` | ADR-P03 | TC-INT-001, TC-SBX-001, TC-DUP-001, TC-CON-007 | M2 | Design: TBD (pending Phase 2 docs) |
| FR-002 | M | §12, §11 | `integrations/linear.md; architecture/state-machine.md` | — | TC-UNIT-001, TC-E2E-006 | M2 | Design: TBD (pending Phase 2 docs) |
| FR-003 | M | §8, §12 | `architecture/components.md` | — | TC-UNIT-002 | M2 | Design: TBD (pending Phase 2 docs) |
| FR-004 | M | §8, §11, §12 | `architecture/components.md; integrations/linear.md` | — | TC-UNIT-003, TC-E2E-011 | M2 | Design: TBD (pending Phase 2 docs) |
| FR-005 | M | §12 | `integrations/linear.md` | ADR-P10 | TC-E2E-014 | M2 | Design: TBD (pending Phase 2 docs) |
| FR-006 | C | §12, §14 | `integrations/linear.md` | — | TC-UNIT-004 | M3 | Design: TBD (pending Phase 2 docs) |
| FR-020 | M | §9, §14 | `integrations/claude.md; protocols/messages.md` | ADR-P07 | TC-CON-003, TC-E2E-001 | M3 | Design: TBD (pending Phase 2 docs) |
| FR-021 | M | §9, §16 | `architecture/components.md; protocols/messages.md` | ADR-P11 | TC-UNIT-010 | M3 | Design: TBD (pending Phase 2 docs) |
| FR-022 | M | §11, §13 | `architecture/components.md` | ADR-P11 | TC-UNIT-011, TC-SM-004, TC-REC-001 | M3 | Design: TBD (pending Phase 2 docs) |
| FR-023 | M | §9, §11 | `architecture/state-machine.md` | ADR-P11 | TC-E2E-007 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-024 | S | §11, §12 | `architecture/state-machine.md` | ADR-P11 | TC-UNIT-013, TC-E2E-008 | M3 | Design: TBD (pending Phase 2 docs) |
| FR-040 | M | §8, §16 | `architecture/components.md` | ADR-P02 | TC-INT-003, TC-CONC-004 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-041 | M | §8, §23 | `architecture/components.md` | — | TC-UNIT-022, TC-CONC-001, TC-CONC-002, TC-P0-014 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-042 | S | §8 | `architecture/components.md` | — | TC-UNIT-022 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-043 | M | §10, §20 | `protocols/messages.md; operations/recovery.md` | ADR-P02 | TC-DUP-003, TC-REC-001 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-044 | M | §13, §18, §20 | `operations/recovery.md; integrations/codex.md` | — | TC-UNIT-021, TC-INT-005, TC-AFS-002, TC-AFS-004 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-045 | M | §11, §20 | `architecture/state-machine.md` | — | TC-UNIT-020, TC-AFS-001, TC-AFS-006, TC-AFS-003 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-046 | M | §11 | `architecture/state-machine.md` | — | TC-SM-010 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-047 | M | §11, §20 | `architecture/state-machine.md` | — | TC-SM-011 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-048 | M | §8, §16, §18 | `architecture/components.md` | ADR-P02 | TC-INT-004, TC-CONC-003 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-049 | M | §8, §21 | `architecture/components.md` | — | TC-INT-010 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-060 | M | §10, §17 | `protocols/messages.md` | ADR-P13 | TC-UNIT-030, TC-CON-001 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-061 | M | §10, §17 | `protocols/messages.md; protocols/schemas/` | ADR-P13 | TC-CON-001 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-062 | M | §13, §14, §17 | `integrations/claude.md; integrations/codex.md` | ADR-P07, ADR-P08 | TC-CON-003, TC-CON-005, TC-AFS-005, TC-P0-013 | M3 | Design: TBD (pending Phase 2 docs) |
| FR-063 | M | §10, §16, §20 | `protocols/messages.md; operations/recovery.md` | ADR-P02, ADR-P13 | TC-INT-003, TC-DUP-003 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-064 | M | §10, §16 | `protocols/messages.md` | ADR-P13 | TC-UNIT-031 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-065 | S | §17 | `protocols/messages.md` | — | TC-CON-002 | M8 | Design: TBD (pending Phase 2 docs) |
| FR-080 | M | §11 | `architecture/state-machine.md` | — | TC-SM-001, TC-SM-002 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-081 | M | §11, §16 | `architecture/state-machine.md` | ADR-P02 | TC-SM-003 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-082 | M | §11, §18, §20 | `architecture/state-machine.md; operations/recovery.md` | ADR-P09 | TC-UNIT-062, TC-SM-009 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-083 | M | §11 | `architecture/state-machine.md` | — | TC-SM-006 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-084 | M | §11, §16 | `architecture/state-machine.md` | — | TC-SM-005 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-100 | M | §13 | `integrations/codex.md` | ADR-P08 | TC-CON-005, TC-E2E-001 | M4 | Design: TBD (pending Phase 2 docs) |
| FR-101 | M | §14 | `integrations/claude.md; protocols/messages.md` | ADR-P07 | TC-CON-003, TC-E2E-002 | M4 | Design: TBD (pending Phase 2 docs) |
| FR-102 | M | §11, §14 | `architecture/state-machine.md` | ADR-P11 | TC-SM-007, TC-UNIT-012 | M4 | Design: TBD (pending Phase 2 docs) |
| FR-103 | M | §13, §14 | `integrations/codex.md` | ADR-P08 | TC-E2E-002 | M4 | Design: TBD (pending Phase 2 docs) |
| FR-104 | M | §11, §14 | `architecture/state-machine.md` | — | TC-SM-008, TC-E2E-003 | M4 | Design: TBD (pending Phase 2 docs) |
| FR-105 | M | §14, §19 | `integrations/claude.md; security/threat-model.md` | — | TC-E2E-012 | M4 | Design: TBD (pending Phase 2 docs) |
| FR-106 | M | §14 | `integrations/claude.md` | — | TC-UNIT-012, TC-E2E-004 | M4 | Design: TBD (pending Phase 2 docs) |
| FR-120 | M | §13, §15 | `integrations/github.md; operations/macos-service.md` | ADR-P15 | TC-UNIT-040, TC-INT-006 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-121 | M | §13 | `integrations/codex.md` | ADR-P08 | TC-UNIT-011, TC-UNIT-012, TC-E2E-001 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-122 | M | §13, §22 | `integrations/codex.md` | — | TC-INT-008 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-123 | S | §13 | `integrations/codex.md` | ADR-P14 | TC-INT-009 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-124 | M | §13, §19 | `integrations/codex.md; security/threat-model.md` | ADR-P06 | TC-UNIT-043, TC-AFS-007, TC-GOV-007 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-125 | M | §13, §21 | `integrations/codex.md` | — | TC-CON-004, TC-AFS-004 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-140 | M | §13, §15 | `integrations/github.md` | ADR-P06, ADR-P04 | TC-INT-007, TC-SBX-002, TC-SEC-002 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-141 | S | §15 | `integrations/github.md` | — | TC-UNIT-041 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-142 | M | §15 | `integrations/github.md` | ADR-P10 | TC-UNIT-042, TC-SBX-002 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-143 | M | §15, §20 | `integrations/github.md; operations/recovery.md` | — | TC-DUP-004, TC-NET-002, TC-REC-001 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-144 | M | §15 | `integrations/github.md` | — | TC-E2E-005, TC-INT-002 | M6 | Design: TBD (pending Phase 2 docs) |
| FR-160 | M | §14 | `integrations/claude.md` | ADR-P07 | TC-CON-003, TC-E2E-004 | M6 | Design: TBD (pending Phase 2 docs) |
| FR-161 | M | §14, §19 | `integrations/claude.md; security/threat-model.md` | — | TC-E2E-012 | M6 | Design: TBD (pending Phase 2 docs) |
| FR-162 | M | §15 | `integrations/github.md` | ADR-P04 | TC-SBX-003, TC-GOV-005 | M6 | Design: TBD (pending Phase 2 docs) |
| FR-163 | M | §11, §14 | `architecture/state-machine.md` | — | TC-E2E-004, TC-SM-008 | M6 | Design: TBD (pending Phase 2 docs) |
| FR-164 | M | §11, §15 | `integrations/github.md` | ADR-P12 | TC-SBX-006 | M6 | Design: TBD (pending Phase 2 docs) |
| FR-165 | M | §11, §14 | `architecture/state-machine.md` | — | TC-E2E-013 | M6 | Design: TBD (pending Phase 2 docs) |
| FR-180 | M | §15 | `integrations/github.md` | ADR-P05 | TC-GOV-005 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-181 | M | §15 | `integrations/github.md` | ADR-P05 | TC-UNIT-052, TC-SBX-004, TC-CON-006 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-182 | M | §15, §19 | `integrations/github.md; security/threat-model.md` | ADR-P05 | TC-GOV-004 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-183 | M | §12 | `integrations/linear.md` | ADR-P10 | TC-SBX-004, TC-SBX-009 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-184 | S | §13, §18 | `operations/recovery.md` | ADR-P15 | TC-INT-006 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-185 | S | §11, §15 | `architecture/state-machine.md` | — | TC-E2E-009 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-200 | M | §12 | `integrations/linear.md` | ADR-P10 | TC-UNIT-050 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-201 | M | §12 | `integrations/linear.md` | ADR-P04 | TC-SBX-005, TC-P0-010 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-202 | M | §12, §20 | `integrations/linear.md` | — | TC-NET-003, TC-DUP-001 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-203 | M | §12, §19 | `integrations/linear.md; security/threat-model.md` | ADR-P11 | TC-GOV-006, TC-PI-002 | M3 | Design: TBD (pending Phase 2 docs) |
| FR-220 | M | §12, §15, §21 | `integrations/github.md; integrations/linear.md` | ADR-P12 | TC-SBX-006 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-221 | M | §21 | `architecture/components.md` | — | TC-UNIT-051, TC-DUP-005 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-222 | S | §20, §21 | `operations/recovery.md` | — | TC-REC-009 | M8 | Design: TBD (pending Phase 2 docs) |
| FR-223 | M | §21 | `architecture/components.md` | — | TC-NET-003 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-240 | M | §8, §18 | `architecture/components.md` | — | TC-INT-010 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-241 | M | §9, §19 | `architecture/components.md; security/threat-model.md` | — | TC-INT-010, TC-GOV-006 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-260 | M | §21 | `architecture/components.md` | — | TC-E2E-010 | M7 | Design: TBD (pending Phase 2 docs) |
| FR-261 | M | §21 | `architecture/components.md` | — | TC-SM-003, TC-E2E-010 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-280 | M | §20 | `operations/recovery.md` | — | TC-REC-001, TC-REC-004 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-281 | M | §18, §20 | `operations/recovery.md` | ADR-P09 | TC-REC-005 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-282 | M | §18, §20 | `operations/macos-service.md; operations/recovery.md` | ADR-P09 | TC-UNIT-062, TC-REC-003, TC-NET-004 | M8 | Design: TBD (pending Phase 2 docs) |
| FR-283 | M | §20 | `operations/recovery.md` | — | TC-NET-001, TC-NET-002, TC-NET-003 | M2 | Design: TBD (pending Phase 2 docs) |
| FR-300 | M | §24, §27 | `planning/roadmap.md` | — | TC-PIL-002, TC-P0-015 | M9 | Design: TBD (pending Phase 2 docs) |
| FR-301 | M | §24, §27 | `planning/roadmap.md` | — | TC-PIL-003 | M9 | Design: TBD (pending Phase 2 docs) |
| FR-900 | W | §3 | `architecture/overview.md` | ADR-P12 | TC-SEC-008 | M8 | Design: TBD (pending Phase 2 docs) |
| FR-901 | W | §3, §7 | `architecture/overview.md` | ADR-P03 | TC-SEC-008 | M8 | Design: TBD (pending Phase 2 docs) |
| FR-902 | W | §3, §15 | `integrations/github.md` | ADR-P05 | TC-GOV-005 | M5 | Design: TBD (pending Phase 2 docs) |
| FR-903 | W | §3 | `architecture/overview.md` | ADR-P09 | TC-INT-004 | M1 | Design: TBD (pending Phase 2 docs) |
| FR-904 | W | §3, §12 | `integrations/linear.md` | ADR-P10 | TC-E2E-014 | M2 | Design: TBD (pending Phase 2 docs) |
| NFR-001 | M | §20 | `operations/recovery.md` | ADR-P02 | TC-REC-001 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-002 | M | §18, §20 | `operations/macos-service.md` | ADR-P09 | TC-REC-006 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-003 | M | §20, §21 | `operations/recovery.md` | — | TC-AFS-002, TC-PIL-004 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-004 | S | §20 | `operations/macos-service.md` | — | TC-PIL-002 | M9 | Design: TBD (pending Phase 2 docs) |
| NFR-005 | M | §12, §15, §20 | `integrations/github.md; integrations/linear.md` | ADR-P03 | TC-SBX-001, TC-NET-001, TC-DUP-002 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-020 | M | §20 | `operations/recovery.md` | ADR-P02 | TC-REC-002, TC-REC-004, TC-REC-008 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-021 | M | §18, §20 | `operations/macos-service.md` | ADR-P09 | TC-REC-003, TC-NET-004 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-022 | M | §20, §24 | `operations/recovery.md` | ADR-P02 | TC-INT-011, TC-OPS-006 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-023 | M | §16, §24 | `operations/recovery.md` | ADR-P02 | TC-INT-012 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-024 | M | §18, §20 | `operations/macos-service.md` | ADR-P09 | TC-REC-007 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-040 | S | §12, §23 | `integrations/linear.md` | ADR-P03 | TC-PERF-002 | M2 | Design: TBD (pending Phase 2 docs) |
| NFR-041 | S | §15, §23 | `integrations/github.md` | ADR-P03 | TC-PERF-002 | M6 | Design: TBD (pending Phase 2 docs) |
| NFR-042 | S | §8, §23 | `architecture/components.md` | — | TC-PERF-003 | M4 | Design: TBD (pending Phase 2 docs) |
| NFR-043 | S | §15, §21 | `integrations/github.md` | ADR-P12 | TC-SBX-006 | M7 | Design: TBD (pending Phase 2 docs) |
| NFR-044 | S | §15, §12 | `integrations/github.md` | — | TC-SBX-004 | M7 | Design: TBD (pending Phase 2 docs) |
| NFR-050 | M | §16, §20 | `operations/recovery.md` | ADR-P02 | TC-INT-013, TC-REC-002, TC-PERF-004 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-051 | M | §16 | `protocols/messages.md` | — | TC-UNIT-031, TC-REC-001 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-052 | M | §16, §20 | `operations/recovery.md` | ADR-P02 | TC-REC-008 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-060 | M | §21 | `architecture/components.md` | — | TC-SM-003, TC-E2E-010 | M7 | Design: TBD (pending Phase 2 docs) |
| NFR-061 | S | §21 | `architecture/components.md` | — | TC-OPS-008 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-062 | M | §21 | `architecture/components.md; security/threat-model.md` | — | TC-SEC-004, TC-INT-010 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-070 | M | §18, §24 | `operations/macos-service.md` | ADR-P09 | TC-OPS-001 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-071 | M | §21 | `architecture/components.md` | — | TC-OPS-002 | M2 | Design: TBD (pending Phase 2 docs) |
| NFR-072 | M | §8, §24 | `architecture/components.md` | — | TC-UNIT-061, TC-OPS-003 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-073 | S | §20, §21 | `operations/recovery.md` | — | TC-OPS-004 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-080 | S | §23 | `architecture/components.md` | ADR-P01 | TC-PERF-001 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-081 | M | §23 | `integrations/github.md; integrations/linear.md` | ADR-P03 | TC-SBX-008, TC-NET-005 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-082 | S | §23 | `operations/macos-service.md` | — | TC-PERF-005 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-083 | M | §13, §14, §23 | `integrations/claude.md; integrations/codex.md` | — | TC-AFS-001, TC-UNIT-021 | M3 | Design: TBD (pending Phase 2 docs) |
| NFR-090 | M | §24 | `integrations/claude.md; integrations/codex.md` | ADR-P01, ADR-P07, ADR-P08 | TC-INT-013, TC-CON-008 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-091 | S | §16 | `architecture/components.md` | ADR-P01, ADR-P02 | TC-INT-003 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-092 | M | §18 | `operations/macos-service.md` | ADR-P15 | TC-P0-011, TC-OPS-001 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-093 | M | §24 | `integrations/codex.md` | — | TC-CON-004, TC-CON-008, TC-OPS-007 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-094 | S | §18, §24 | `operations/macos-service.md` | — | TC-P0-001, TC-OPS-007 | M8 | Design: TBD (pending Phase 2 docs) |
| NFR-100 | S | §22 | `testing/verification-plan.md` | — | TC-UNIT-011, TC-UNIT-012 | M1 | Design: TBD (pending Phase 2 docs) |
| NFR-101 | M | §22 | `testing/verification-plan.md` | — | TC-SM-005 | M1 | Design: TBD (pending Phase 2 docs) |
| OPS-001 | M | §18, §27 | `operations/macos-service.md` | — | TC-P0-001, TC-P0-002, TC-P0-003, TC-P0-004, TC-P0-005, TC-P0-006, TC-P0-007, TC-P0-008 | P0 | Design: TBD (pending Phase 2 docs) |
| OPS-002 | M | §15, §19 | `integrations/github.md; integrations/linear.md` | ADR-P04 | TC-P0-009, TC-P0-010, TC-GOV-008 | P0 | Design: TBD (pending Phase 2 docs) |
| OPS-003 | M | §15, §19 | `integrations/github.md` | ADR-P05 | TC-SBX-007, TC-OPS-005 | M5 | Design: TBD (pending Phase 2 docs) |
| OPS-004 | M | §22 | `testing/verification-plan.md` | — | TC-OPS-009, TC-SBX-001 | P0 | Design: TBD (pending Phase 2 docs) |
| OPS-005 | M | §24 | `operations/macos-service.md` | — | TC-OPS-007 | M8 | Design: TBD (pending Phase 2 docs) |
| OPS-006 | S | §20, §24 | `operations/recovery.md` | — | TC-OPS-006 | M8 | Design: TBD (pending Phase 2 docs) |
| OPS-007 | M | §19 | `security/threat-model.md` | — | TC-P0-003, TC-SEC-004 | P0 | Design: TBD (pending Phase 2 docs) |
| OPS-008 | M | §27 | `planning/roadmap.md` | — | TC-PIL-001, TC-PIL-002 | M9 | Design: TBD (pending Phase 2 docs) |
| OPS-009 | M | §24 | `planning/roadmap.md` | — | TC-PIL-003 | M9 | Design: TBD (pending Phase 2 docs) |
| OPS-010 | M | §19, §20 | `security/threat-model.md; operations/recovery.md` | — | TC-OPS-004 | M8 | Design: TBD (pending Phase 2 docs) |
| OPS-011 | S | §21, §23 | `operations/macos-service.md` | — | TC-OPS-008, TC-PERF-005 | M8 | Design: TBD (pending Phase 2 docs) |
| OPS-012 | S | §18 | `operations/macos-service.md` | ADR-P09 | TC-P0-002, TC-OPS-002 | M8 | Design: TBD (pending Phase 2 docs) |
| SEC-001 (SEC-001–009) | M | §19 | `security/threat-model.md` | TBD (E) | TC-SEC-002, TC-SBX-002 | P0 | TBD (E) |
| SEC-010 (SEC-010–019) | M | §19 | `security/threat-model.md` | TBD (E) | TC-GOV-008 | P0 | TBD (E) |
| SEC-020 (SEC-020–029) | M | §19 | `security/threat-model.md` | TBD (E) | TC-SEC-004 | M1 | TBD (E) |
| SEC-030 (SEC-030–039) | M | §19 | `security/threat-model.md` | TBD (E) | TC-P0-012, TC-SEC-001, TC-SEC-003, TC-SEC-005, TC-SEC-006, TC-SEC-007 | M3 | TBD (E) |
| SEC-040 (SEC-040–049) | M | §19 | `security/threat-model.md` | TBD (E) | TC-PI-001, TC-PI-002, TC-PI-003, TC-PI-004, TC-PI-005 | M3 | TBD (E) |
| SEC-050 (SEC-050–059) | M | §19 | `security/threat-model.md` | TBD (E) | TC-GOV-001, TC-GOV-002, TC-GOV-003, TC-GOV-004 | M5 | TBD (E) |
| SEC-060 (SEC-060–069) | M | §19 | `security/threat-model.md` | TBD (E) | TBD (E) | M8 | TBD (E) |
| SEC-070 (SEC-070–079) | M | §19 | `security/threat-model.md` | TBD (E) | TBD (E) | M8 | TBD (E) |
| SEC-080 (SEC-080–089) | M | §19 | `security/threat-model.md` | TBD (E) | TC-E2E-012 | M6 | TBD (E) |


### 6.1 Coverage summary (generated from the data behind this file)

| Type | Count | M | S | C | W |
|---|---|---|---|---|---|
| CON | 17 | 17 | 0 | 0 | 0 |
| FR | 85 | 71 | 8 | 1 | 5 |
| NFR | 36 | 23 | 13 | 0 | 0 |
| OPS | 12 | 9 | 3 | 0 | 0 |
| SEC (anchors, E to expand) | 9 | 9 | – | – | – |

| Milestone | P0 | M1 | M2 | M3 | M4 | M5 | M6 | M7 | M8 | M9 |
|---|---|---|---|---|---|---|---|---|---|---|
| Requirements first verified | 10 | 39 | 10 | 11 | 11 | 16 | 9 | 18 | 30 | 5 |

Test cases defined: 162. Requirements with ≥ 1 test case: 150/150.

Checks run while generating this file:
- Every `TC-*` cited in the RTM is defined in `testing/verification-plan.md` §8.
- Every defined `TC-*` covers at least one requirement.
- No requirement ID is duplicated.
- Every `ADR-Pnn` cited exists in §5.

---

## 7. Milestone keys

These are short keys used in the RTM. The full plan, with dependencies and estimates, is drafted in `reviews/15-agent-F-report.md` and moves to `planning/roadmap.md` in Phase 4.

| Key | Milestone | Exit gate (summary) |
|---|---|---|
| P0 | Environment verification and identity setup | Phase 0 checklist complete; agent identities and sandbox repo/team exist; blocking operator decisions recorded |
| M1 | Skeleton daemon, store and state machine with fakes | TC-SM-001…011, TC-INT-003/004/005/013 and TC-UNIT core pass; crash-injection harness runs |
| M2 | Linear and GitHub read-only pollers | TC-INT-001/002, TC-SBX-001, TC-NET-001 pass; shadow-mode status output |
| M3 | Claude decision adapter (triage and authorization) | TC-CON-003, TC-UNIT-010/011, TC-E2E-006, TC-SEC-001 pass |
| M4 | Codex planning and plan-review loop | TC-E2E-002/003, TC-SM-007/008, TC-CON-005 pass |
| M5 | Implementation, git operations and PR | TC-E2E-001 up to PR_OPEN, TC-SBX-002, TC-DUP-004, TC-GOV-001…003/008 pass |
| M6 | Claude PR review and revision loops | TC-E2E-004/005/013, TC-SBX-003 pass |
| M7 | Merge verification, Linear updates, notifications, audit | TC-SBX-004/005/006/009, TC-GOV-004, TC-E2E-010 pass |
| M8 | Hardening, recovery, security and performance | TC-REC-*, TC-NET-*, TC-PI-*, TC-SEC-*, TC-PERF-* pass on the Mac |
| M9 | Pilot on `network_monitor` and Slack cutover | TC-PIL-001…004 pass |

---

## 8. Operator decisions referenced by requirements

Each decision is linked to the requirements whose acceptance criteria depend on it. Context and options are in `reviews/15-agent-F-report.md` §8.

| ID | Decision | Affects | Needed by |
|---|---|---|---|
| OD-01 | Move target repos (and MERCURY) to a GitHub organization so that "only the operator merges" becomes preventive | CON-014, FR-182, TC-GOV-004 | Before M5 (sandbox governance tests) |
| OD-02 | GitHub agent identity: GitHub App (recommended) or machine user | CON-008, FR-140, OPS-002 | P0 |
| OD-03 | Claude authentication: Console API key via `apiKeyHelper`, or subscription `setup-token` | NFR-090, TC-P0-004 | P0 |
| OD-04 | Codex authentication and billing: `CODEX_API_KEY` or ChatGPT login | TC-P0-005, TC-P0-014 | P0 |
| OD-05 | Linear identity: OAuth `actor=app`, or a team-scoped key (still the human user) | FR-201, OPS-002 | P0 |
| OD-06 | Linear status ownership: disable the integration's PR automations, or use non-closing magic words with MERCURY setting Done, or let the integration own Done while MERCURY verifies | FR-142, FR-183, TC-SBX-009 | Before M7 |
| OD-07 | Concurrency defaults (proposal: Codex 1 global, Claude 2, 1 per repo) | FR-041 | M1 (configurable; default needed for pilot) |
| OD-08 | Cycle limits and budgets (proposal: plan 3, PR review 3, CI fix 2; per-task budget cap) | FR-104, FR-144, FR-163, NFR-083 | M4 |
| OD-09 | May Codex ever have network access, for example for dependency installation? | FR-123 | M5 |
| OD-10 | Eligibility signal (proposal: state `Todo` **and** an opt-in label such as `mercury`) | FR-002, FR-300 | M2 |
| OD-11 | Plan auto-approval policy: all issues, or an operator gate for `Security`-labelled or size-L issues | FR-106 | M4 |
| OD-12 | Escalation response channel: local CLI only, or also GitHub comments whose author is verified as the operator | FR-241 | M7 |
| OD-13 | Sandbox: names of the GitHub repo and Linear team, and whether a second test-human account is allowed (for automating governance tests) | OPS-004, TC-SBX-*, TC-GOV-* | P0 |
| OD-14 | Mac power policy while tasks run (desktop vs laptop; whether to hold an idle-sleep assertion) | CON-009, NFR-004 | M8 |
| OD-15 | Retention periods | NFR-061 | M8 |
| OD-16 | Pilot scope (which issues) and Slack decommission date | OPS-008, FR-301 | M9 |

---

## 9. Assumptions (Agent F)

| ID | Assumption | Impact if false | Verified by |
|---|---|---|---|
| ASM-F-01 | Latency NFR defaults (60 s Linear poll, ≤ 60 s GitHub poll for active PRs) fit within the rate budgets in discovery | NFR-040/041/081 need retuning | TC-SBX-008 |
| ASM-F-02 | A sandbox Linear team can be created in the existing workspace on its current plan | Linear sandbox tests need another workspace | P0 (OD-13) |
| ASM-F-03 | A GitHub App can be installed on personal-account repositories with the permission set in discovery (G2) | Machine-user fallback (OD-02) | TC-P0-009 |
| ASM-F-04 | Node's monotonic clock pauses during sleep on the operator's Mac | Wake detection needs another signal | TC-P0-007 |
| ASM-F-05 | Fullfsync commit latency stays below ~50 ms on the Mac's SSD | NFR-050 cost becomes significant; batch writes | TC-PERF-004 |
| ASM-F-06 | Governance tests that need a "human" approval are run with the operator in the loop, because a second human account may not be allowed | TC-GOV-*/TC-SBX-004 stay semi-manual | OD-13 |

---

## 10. Definition of Ready (MERCURY implementation issue)

An implementation issue (in MERCURY's own backlog) is **Ready** only when every item below holds.

| # | Criterion | Check |
|---|---|---|
| R1 | Linked to ≥ 1 requirement ID from this file whose status is `Baselined` or later | Issue body lists `Implements: FR-…` |
| R2 | Each linked requirement's mapped `TC-*` IDs are defined in `testing/verification-plan.md`, and the issue lists the TCs it will make pass | `Verifies: TC-…` |
| R3 | Acceptance criteria are copied or refined from the requirement and are measurable pass/fail | Reviewer check |
| R4 | Contracts touched (schemas, interfaces, DB tables) exist in their owning documents with a version | Links present |
| R5 | `blockedBy` dependencies are Done, or are explicitly marked parallel-safe with a stub or fake | Linear relations |
| R6 | Every gating `ASM-*` is Verified or Accepted in the Phase 0 report | Link to Phase 0 row |
| R7 | No open `OD-*` blocks the issue, or the issue implements a configurable default with the decision recorded as pending | §8 |
| R8 | Security impact noted. If the issue touches a `SEC-*` scope, it has the `Security` label and a threat-model reference | Label + link |
| R9 | Recovery semantics stated for any new persistent step or external effect (dedup key, crash point name) | Section "Recovery" in issue |
| R10 | Estimated P50 ≤ 3 days. Otherwise split | Size field |
| R11 | Required test environment (fake, sandbox or real Mac) is available | Env listed |
| R12 | Issue follows the existing description convention (Context / Scope / Security / Tests / Acceptance criteria / Size) and is not labelled `Not Speced` | Template |

## 11. Definition of Done

| # | Criterion |
|---|---|
| D1 | Merged to the protected default branch through a PR **approved and merged by the operator** (CODEOWNERS), with all required checks green. |
| D2 | All TCs listed on the issue are implemented and pass at their level. Sandbox and real-Mac TCs have a stored evidence report (run ID, date, versions). |
| D3 | Coverage gates met (NFR-100): 100% branch coverage on the state machine, gates and scheduler, and ≥ 85% lines elsewhere. No new lint or type errors. |
| D4 | Any new persistent step is registered in the crash-point registry and exercised by TC-REC-001. Any new external effect has a dedup key. |
| D5 | Audit events and structured logs exist for the new behaviour. The redaction canary (TC-SEC-004) passes. Secret scan is clean. |
| D6 | Claude PR review and security review completed. Findings at or above the blocking severity are resolved. `Security`-labelled issues also have the Agent E checklist completed. |
| D7 | The owning design document and any runbook are updated in the same PR (or a linked follow-up merged before the milestone exit). |
| D8 | RTM rows updated: requirement status set to `Implemented`, or to `Verified` with an evidence link. |
| D9 | Configuration keys documented with defaults and covered by the config validator (TC-UNIT-061). |
| D10 | Worktree and branch cleaned up, and the Linear issue Done through the normal verified flow. |
