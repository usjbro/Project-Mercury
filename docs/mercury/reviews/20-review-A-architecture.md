# Phase 3 Review: Architecture Coherence (Agent A, Principal AI Systems Architect)

| | |
|---|---|
| Reviewer | Agent A |
| Phase | 3, cross-agent design review |
| Date | 2026-10-12 |
| Focus | Coherence of the B, C, D, E and F designs with `architecture/overview.md` and ADR-001 to ADR-012. Also covered: component and responsibility boundaries (Claude decides, MERCURY coordinates, Codex implements, the human merges), system-of-record consistency, ADR revisions and new ADRs. My own Phase 2 work is reviewed with the same rigour. |
| Rules | Design only. This file is the only file written. No external writes. |

---

## 1. Scope and method

**Read in full:** `00-brief.md`, `03-design-baseline.md`, all six Phase 2 reports (`10`–`15`), `architecture/overview.md`, and ADR-001 to ADR-012.

**Read by section**, using `Grep` and offset reads for the sections that bear on architecture:

| Document | Sections examined |
|---|---|
| `architecture/state-machine.md` | §1–§11 (states, transitions T01–T40 and G1–G6, invariants I1–I20, holds, block reasons, timers, guards, merge verification, recovery) |
| `architecture/components.md` | §1, §4.0 name mapping, §5 control API, §6 table list and `runs` DDL, §7 derived queue, §9 worktree layout, §11 L11 |
| `protocols/messages.md` and `protocols/schemas/*.json` | Message catalogue. All `decision`, `action` and `event` enums were extracted from the 25 schema files with a script |
| `integrations/claude.md` | §1–§3 (invariants, SDK profile, decision types, readable roots) |
| `integrations/codex.md` | §3 (thread and resume policy), §5 (`CODEX_HOME`) |
| `integrations/github.md` | §2 (identity and permissions), §6 (review posting), §8 (merge verification), §9–§10, §18 (authority table) |
| `integrations/linear.md` | §5 (`spec_hash`), §6 (status ownership), §8 (spec drift) |
| `operations/macos-service.md` | §3 (process tree), §7 (directory layout and modes), §11.4 (ops alerts) |
| `operations/recovery.md` | §2 (failure classes), §3 (side-effect journal) |
| `security/threat-model.md` | §0, §4, §5.1 (SEC-1xx–6xx), §6.2 (identities per governance mode), §8.1 (layout), §8.5 (anchoring), §11 (requirements on other agents) |
| `planning/traceability.md` | §1.1 ID scheme, ADR-P01…P15 table, CON-003, FR-020/021/046/161/162/182/183 |
| `testing/verification-plan.md` | Not reviewed in depth. It is outside my focus and is covered by F's own review |

**Method.**
1. Built a matrix with one row per cross-cutting decision (queue, states, holds, filesystem, identities, permissions, review posting, security-review scope, spec drift, Linear ownership, merge verification, Claude inputs, `CODEX_HOME`, HMAC and anchoring, ID schemes) and one column per document.
2. Marked every cell that disagrees with another.
3. Checked each state-machine initiator and each control-API method against the authority boundary.

---

## 2. Summary verdict

**Verdict: coherent at the core, but not yet consistent. Rework is needed before the TDD is assembled.**

**What holds up.** All six designs keep the four authority invariants:
- Claude produces every decision.
- The coordinator records decisions and never makes them.
- Codex never runs without an authorization and, for implementation, a hash-bound approval.
- No agent identity can satisfy GitHub's required human approval.

In detail:
- C's DB triggers, the initiator column (I19) and the explicit "no approve/merge/authorize method" rule on the control API make the decide/execute separation enforceable, not just aspirational.
- E's proof in threat-model §5.2 shows the human-approval boundary survives full prompt injection.
- The system-of-record split (ADR-009) is accepted by every agent.

**What fails consistency.** About ten cross-document contradictions would make implementers diverge. Three would produce incorrect or unsafe behaviour if built as written:

1. **Spec-drift handling is three different designs** (RA-01): A blocks, C holds, and B interrupts and moves backwards to `AWAITING_AUTHORIZATION`, a transition that does not exist in C's table. The hash being compared is also defined three ways.
2. **Claude review posting.** B forbids bot `REQUEST_CHANGES`. C's T25, my ADR-008, E's SEC-102, F's FR-162 and the `code.review` schema all allow it. B's reasoning is correct: a bot `REQUEST_CHANGES` leaves a blocking review state (RA-04).
3. **The separate agent uid (SEC-201) changes process control and the filesystem.** C and D were designed for a single uid. A coordinator running as the operator cannot signal processes owned by `_mercuryagent`. Under the 0700 home, it also cannot share `~/Library/Mercury` or `~/MercuryWork` with that uid (RA-02, RA-03).

**My own Phase 2 work has the most stale content.** It was written first and has not been reconciled. Thirteen ADRs need revision or supersession (§3, group A), and eight new ADRs are needed (§3.3).

**Finding counts:** Critical 0 · High 11 · Medium 19 · Low 8 (38 total).

No finding is Critical: in every case the GitHub-enforced human approval remains the backstop. Several High items would be Critical if the GitHub protections were misconfigured, which is why E's drift monitor (SEC-108) must stay a MUST.

---

## 3. Findings

### 3.1 Cross-agent findings

| ID | Sev | Type | Location(s) | Finding | Recommended resolution | Owner |
|---|---|---|---|---|---|---|
| RA-01 | High | contradiction | overview §9.3 C1; ADR-009 §3; state-machine §5 (`spec_changed` hold), §8.1; linear.md §5, §8; components §10.9 | **Spec drift has three incompatible designs.** (a) A: `BLOCKED(spec_changed)` at the next phase boundary; a running Codex run finishes. (b) C: `spec_changed` hold, runs continue, result not acted on. (c) B: interrupt runs. Pre-plan states **return to `AWAITING_AUTHORIZATION`**, which has no transition in C's table. Mid-states go to `BLOCKED(spec_drift)`, a reason code C lacks. PR states get a draft plus `action_required` check. **The hash also differs:** C compares `description_sha256`; B uses a canonical `spec_hash` (title, normalized description, AC, spec labels, blockers); A says "snapshot (title, description, AC, labels, relations)". | Adopt **C's hold** as the mechanism (no backward transition) and **B's `spec_hash` definition** as the single hash, defined once in linear.md §5. Add **B's PR-stage protection**: the check run goes to `action_required` while the hold is active, so stale-spec code cannot be merged. Specify how re-authorization ends: see RA-05. Add a test that a checkbox tick never sets the hold. | C (table), B (hash, PR effect), A (ADR-009 revision) |
| RA-02 | High | infeasible | threat-model SEC-201, §8.1, D-SEC-1; macos-service §3.1–§3.2, §7; components §8.2–§8.6, §10.6; state-machine §10 | **The separate agent uid breaks the process-control design as written.** A process running as the operator cannot `kill(2)` processes owned by `_mercuryagent`. It also cannot reliably read their `lstart`/cwd identity for adoption, or create the per-run files the agent must write. C's `runwrap` adoption, D's pgid kill ladder and orphan sweep, and caffeinate scoping all assume one uid. SEC-201 says only "sudoers wrapper or launchd broker; Agent D to design", and D has not designed it. | New **ADR-013 Agent process isolation** (see §3.3). A root-owned, fixed-grammar broker (sudoers to one binary, or a privileged launchd helper) performs `spawn-as-agent`, `signal(run_id, sig)`, `identify(run_id)` and `sweep`, keyed by `run_id`, with argv validation. C's `ProcessSupervisor` port gains a `Broker` adapter. The L2 `verify` runner and `deps_install` also run as the agent uid. Phase 0 must prove the broker before M5. | D (design), E (review), C (port) |
| RA-03 | High | contradiction | overview §5.4; ADR-002 §1; ADR-006 §2; claude.md §3.2; components §9.1; macos-service §7.1; threat-model §8.1 | **Five filesystem layouts.** Work root: `~/MercuryWork` (A, C), `~/Library/Application Support/Mercury/checkouts` (B), `~/Library/Mercury` (D), `/Users/Shared/mercury` (E). Under SEC-201, any work root inside the operator's 0700 home is unreachable by the agent uid. That includes Claude's `runs/<id>/inputs/` under `Application Support`, which B places there. | New **ADR-016 Filesystem layout and ownership** with three roots: `MERCURY_HOME` = `~/Library/Application Support/Mercury` (coordinator only: DB, artifacts, config, `run/`); `WORK_ROOT` = space-free and group-shared (mirrors, worktrees, snapshots, per-task `CODEX_HOME`, Claude inputs); logs = `~/Library/Logs/Mercury`. `WORK_ROOT` defaults to `/Users/Shared/Mercury` (0750, group `mercury-agents`) if SEC-201 is adopted, else `~/Library/Mercury`. D's §7.1 becomes the single source of truth; every other document references it. | D (owner), A (ADR), E |
| RA-04 | High | contradiction | github.md §6.3, claude.md CL-5; state-machine T25; ADR-008 §8; overview §8.2; threat-model SEC-102, §6.2; traceability FR-162; F App. C M6-2; schema `code.review` `github_review.event` enum | **`REQUEST_CHANGES` by the bot.** B forbids it because a bot `REQUEST_CHANGES` creates a blocking review that needs dismissal rights, which the App must not have (I9 forbids dismissal). Everyone else, including me, allows it. If built as C specifies, T25 leaves the PR with a stale bot block, and the operator cannot clear it without admin action. | `COMMENT` only. The gate is the required App check run (RA-06). Change T25, ADR-008, SEC-102 ("accepts only COMMENT"), FR-162, M6-2 and the schema enum to `["COMMENT"]`. | C, E, F, A |
| RA-05 | High | missing-requirement | state-machine §3 (T03 only from `AWAITING_AUTHORIZATION`), G1a, G4, §5 `spec_changed`; schema `output.task_authorization_decision` (enum `authorize, decline, defer, needs_spec, needs_human`); schema `task.authorization` (`authorize, amend, revoke`) | **Re-authorization, revocation and scope amendment have no complete contract.** (a) A `reauthorize`-mode run returning `decline`, `defer`, `needs_spec` or `needs_human` for a task in `PLANNING`…`AWAITING_HUMAN_APPROVAL` has no transition. (b) The Claude output contract cannot express `revoke` or `amend`, yet G1a ("Claude revocation decision") and G4 ("scope amendment") depend on them. No trigger says when the coordinator asks Claude to revoke or amend. (c) After a spec-driven re-authorization it is not stated whether the existing plan approval survives. It should not: the approval was judged against the old spec. | Add a `reauthorize` mode to the output contract with `decision ∈ {reauthorize_same_scope, amend_scope, revoke, needs_human}`. Then: `revoke` → G1a; `amend_scope` → G4; `needs_human` → `BLOCKED(needs_human_decision)`; `reauthorize_same_scope` clears the hold. Plan approvals also bind `spec_hash`, so any spec change forces a new `plan_review`, which may approve the same `plan_sha256`. Triggers are spec drift, expiry and operator `request reauth` only. Claude never revokes unprompted. | C, B, A (ADR-011) |
| RA-06 | High | contradiction | github.md §2.1, §6, §9.1; threat-model SEC-100, SEC-309/310, §6.2; ADR-008 identity table | **Gate mechanism and App permissions.** B gates on a check run `MERCURY / claude-review` (`checks:write`, `statuses:read`, `issues:none`). E gates on commit statuses `mercury/policy` and `mercury/claude-review` (`statuses:write`, `checks:read`, `issues:write`). My ADR-008 grants `checks:read`, `statuses:read`, `issues:write`: it can post neither, and it disagrees with both. | Use **check runs** for both gates: `MERCURY / claude-review` and `MERCURY / policy`, both required and pinned to the App's integration ID. A check run can only be created by an App, which is a stronger source binding than statuses. App-Main permissions: `contents:write`, `pull_requests:write`, `checks:write`, `statuses:read`, `actions:read`, `metadata:read`; no `issues`, `workflows` or `administration`. Revise ADR-008 and threat-model §6.2. | A, B, E |
| RA-07 | High | missing-requirement | macos-service §11.4/§11.6 (ops issue, heartbeat); threat-model SEC-604 (anchor credential), SEC-108 (`administration:read`); github.md §2.1 | **The identity inventory is incomplete and partly infeasible as one App.** GitHub App permissions apply to every repo an App is installed on. D's ops issue and heartbeat need `issues:write` on `project-mercury`; E's anchor needs `contents:write` on a private anchor repo; E's drift monitor needs `administration:read` on target repos. Adding these to App-Main widens it on every target repo. | ADR-008 revision with an **identity inventory**: App-Main (target repos, RA-06 set); **App-Ops** (installed only on `project-mercury` and `mercury-audit-anchors`: `issues:write`, `contents:write`); **App-Auditor** (target repos: `administration:read`, `metadata:read`; nothing else; optional, and without it SEC-108 degrades to POL); Linear app (`actor=app`); G-SPLIT deploy keys if chosen. Each is a separate Keychain item. | A, B, E, D |
| RA-08 | High | contradiction | codex.md §5 (per-task, needed for `exec resume`); components §9.1 (`codex-home/<task_id>`); macos-service §7.1 (per-run, deleted with the run); threat-model SEC-203 (per-run) | **Per-run `CODEX_HOME` breaks B's resume design.** Plan revisions and implementation revisions resume threads whose session files live in `CODEX_HOME/sessions`. D deletes a per-run home with the run directory, and E mandates per-run. | **Per-task `CODEX_HOME`** in `WORK_ROOT`, coordinator-generated `config.toml`, regenerated and byte-verified before each run. This meets E's hook-trust intent (SEC-203). Archive `sessions/` at terminal. E amends SEC-203 to "per task, regenerated per run". | B, D, E |
| RA-09 | High | security | components §5.2/§5.4 (`operator.token`, `task.ack_merge`, `task.grant`, `task.resume`); threat-model SEC-310 (operator acknowledges the `mercury/policy` escalation on the CLI); CON-003 ("or operator CLI action") | **Escalations meant for the human can be cleared by Claude.** Any process running as the operator can read `run/tokens/operator.token`. That includes the operator's own interactive Claude Code session, which has Bash. Such a process can `ack-merge`, acknowledge a SEC-310 protected-path escalation (which turns a required GitHub check green), grant budgets, or `resume --to`. C states that principal separation is policy-only for same-uid processes. The effect: an agent can satisfy the "human judgement" step that brief §G escalations exist for. GitHub human approval still gates `main`, which is why this is High and not Critical. | Classify control methods as **safety-relaxing**: `ack_merge`, policy acknowledgement, `grant`, `resume` of `security_*`/`injection_suspected`/`guard_integrity_failure`, and `outbox.retry` of security items. Require **user presence** for them: a LocalAuthentication (Touch ID or password) prompt from a small signed helper, verified by the daemon. Fall back to "TTY plus typed nonce" only if Phase 0 rejects the helper, recorded as POL. Add interactive Claude permission rules that deny these subcommands (policy layer). Tighten CON-003: operator CLI actions may stop, hold, grant or acknowledge; they may never authorize or approve. | C, E, F |
| RA-10 | High | contradiction | overview §9.1 note and OD-A-03; ADR-009 §5; state-machine §1.2 (projection writes `Done` at `COMPLETED`); linear.md §6; traceability OD-06 recommendation (b) | **Who writes Linear `Done` is incompatible with branch naming.** B shows that a branch name containing the issue ID is a *closing* link, so the integration closes the issue on merge whatever the PR phrase. My "`Part of JAM-n` keeps Done for the coordinator" (ASM-A-07) is therefore wrong while branches are `mercury/jam-123-…`. F recommends the same flawed option. C's projection has MERCURY writing `Done`, contradicting B's default. | Adopt **B's default** (`integration_owns_pr_states`): MERCURY writes only `→ In Progress`, comments and the `mercury:needs-human` label. `Done` is observed, never proof of merge. `mercury_owns_all` (branch without ID) stays an operator option (OD). C's projection table marks `In Review`/`Done` as "observed". I withdraw OD-A-03 and ASM-A-07. | A, C, F, Operator |
| RA-11 | High | contradiction | ADR-004 §2; overview §8.2; claude.md §3; state-machine (`claude_revision_request`, `claude_failure_triage` kind with no contract); ADR-006 Consequences | **The decision-kind catalogue differs.** A has six kinds including `FAILURE_TRIAGE` and no revision request. B has six including `revision_request` and no failure triage. C has B's six, plus a `claude_failure_triage` run kind with no contract, plus `reauthorize` mode. My ADR-006 sends base drift to `FAILURE_TRIAGE`, which nobody implements. | Canonical list (ADR-004 revision): `triage`, `authorization` (modes `initial`, `reauthorize`), `plan_review`, `pr_code_review`, `pr_security_review`, `revision_request`. `FAILURE_TRIAGE` is **deferred**: after retries, failures go to `BLOCKED(run_exhausted)` and the operator decides (the human outranks Claude, so the boundary is not blurred). Base conflicts follow C's `CHANGES_REQUESTED(merge_conflict)` path. Remove `claude_failure_triage` from the `runs.kind` CHECK until a contract exists. | A, C |
| RA-12 | Medium | contradiction | ADR-003 §5, overview §7.1 (in-process read-only `mercury` MCP server); threat-model SEC-204 (strict MCP with only that server); claude.md §2.1 (`mcpServers: {}`, "no MCP at all in v1") | MCP for Claude runs is both adopted and forbidden. | Adopt B: **no MCP in v1**. Bundles are files in the inputs directory read with Read/Grep/Glob, so there is one confinement mechanism. Revise ADR-003 §5 and SEC-204 wording. Re-evaluate the MCP server after Phase 0. | A, E |
| RA-13 | Medium | contradiction | threat-model SEC-205; claude.md §3.2; components §9.4 | **What Claude reads.** E requires a git-object snapshot (`ls-tree` plus `cat-file`, no `.git`, attributes not applied, symlinks as placeholders). B and C use detached `git worktree add` checkouts, which include a `.git` file pointing into the mirror and materialise symlinks. B's realpath hook denies `.git` segments, which narrows the gap but does not close it. | New **ADR-017 Claude review snapshot**: every tree Claude reads (reference at `base_sha`, review at `head_sha`) is a coordinator-built object snapshot under `WORK_ROOT/snapshots/`, 0444/0555, readable by the agent uid. It replaces "reference/review checkout" everywhere. Snapshots are content-keyed, so they can be shared by tree SHA. | C, B, E |
| RA-14 | Medium | contradiction | overview §8.2 (security review conditional); threat-model SEC-314 (MUST only for `Security` label or escalation); claude.md §3 (mandatory for every PR); state-machine T24 guard (both reviews required); FR-161 (every PR) | Whether security review runs on every PR. | **Every PR** (B, C, F). Depth scales with the label and SEC-310 hits. The cost is small next to a missed finding, and C's guard already requires it. E raises SEC-314 to MUST; I revise overview §8.2. | E, A |
| RA-15 | Medium | contradiction | ADR-002 §5, overview §5.2/§6 (`jobs` table, `claimDueJobs`); components §4.0, §7.1 (derived queue) | Two queue designs (known disagreement 2). | Adopt **C's derived queue** (see §4). Revise ADR-002 §4–§6 and overview §6. | A |
| RA-16 | Medium | contradiction | overview §6 ("per task: 1 active run of any kind"), NFR-REL-03; components §11 L11, §7.1 (parallel code and security reviews) | My duplicate-execution metric counts C's two parallel read-only Claude reviews as a violation. | Redefine NFR-REL-03 as **≤ 1 active mutating run per task and ≤ 1 active run per (task, kind)** (C's I2). Read-only Claude runs may overlap. | A, F |
| RA-17 | Medium | contradiction | github.md §8 M1, "Outcomes"; state-machine T33, G6, T35; overview §9.3 C6, C8; FR-182 | **Merge-verification failure and close-without-merge routing.** B: closed without merge → `CANCELLED(pr_closed)` regardless of actor; verification failure → stay in `MERGED` with an `integrity_alert`. C: closed by the operator → `CANCELLED`, by others → `BLOCKED(pr_closed_unexpectedly)`; verification failure → `BLOCKED(merge_verification_failed)`. A: "`MERGED` with `verification=failed`". | Adopt **C's routing** (see §4, item 12). Merge B's M1–M7 checks with C's check5 into one list in state-machine §8.5 and reference it from github.md. | C, B |
| RA-18 | Medium | missing-requirement | github.md §8 ("pause all new dispatch for that repo; Agent E decides"); state-machine §5 (no such hold) | Repo-wide pause after an integrity alert is undecided and has no hold kind. | Add hold `integrity_alert` (scope repo, `stop_runs = no`), set at T35, cleared only by operator `ack-merge` (user-presence, RA-09). Make it mandatory (my recommendation to E). | C, E |
| RA-19 | Medium | contradiction | ADR-011 §8, overview §8.3/§8.6 (HMAC optional; but `record_mac` shown as a required field); components (`record_mac` nullable); threat-model SEC-603 (MUST) | HMAC is optional in three places and required in one. My own record shape is internally inconsistent. | **HMAC required for authority rows** (authorizations, plan approvals, PR-review verdicts). The key is in the coordinator's Keychain (see §4, item 3). Make `record_mac` NOT NULL. | A, C |
| RA-20 | Medium | missing-requirement | threat-model SEC-604, C-SEC-4; components §6.3 (no `anchors` table); C report §7 | Off-host anchoring has no table, no outbox effect kind, no credential (RA-07) and no failure semantics. | C adds `audit_anchors (seq, hash, anchored_at, target, remote_ref)` and an outbox kind `audit.anchor` with natural-key reconcile (the anchor file path plus line). If anchoring is overdue by more than 24 h of awake time: an ops alert, but no halt (an anchor outage must not stop work). A failed chain verification still halts (SEC-602). | C, E, D |
| RA-21 | Medium | ambiguous-contract | state-machine I17, T01; overview §9.1; claude.md §3 `authorization` trigger | **Two paths create tasks with different preconditions.** C creates the task at triage or operator request. B's `authorization` runs when "free capacity and top-ranked eligible issue whose dependencies are satisfied". C checks dependencies only at T05. A runs `AUTHORIZE` for the "top k". | One rule in state-machine T01: task creation requires eligibility plus free WIP. Dependencies are checked at T05 (hold) and passed to Claude as context in the authorization bundle. B's trigger text references T01. | C, B |
| RA-22 | Medium | contradiction | ADR-010 (`ExitTimeOut 60`, `ThrottleInterval 10`, label `<reverse-dns>.mercuryd`); macos-service §5 (`45`, `30`, `com.usjbro.mercury`); NFR-REL-01 (60 s incl. 10 s throttle) vs REL-01 (restart ≤ 45 s) | Parameter drift between ADR-010 and D. | ADR-010 drops concrete values and references macos-service §5. Restart and recovery targets come from F's NFR IDs (§4, item 9). | A, D, F |
| RA-23 | Medium | unverifiable-assumption | overview §5.2 (Health Monitor: wall vs monotonic), ASM-A-04; F ASM-F-04; macos-service §8.2 (correction); state-machine §7.2 | ASM-A-04 and ASM-F-04 are **refuted** by D's source check: libuv on macOS uses `mach_continuous_time`, which keeps counting through sleep. | Delete ASM-A-04 and ASM-F-04. Sleep detection uses D's tick gap plus `kern.waketime`; awake-time crediting uses C's credit cap, which works whatever the clock does. | A, F |
| RA-24 | Medium | contradiction | overview §5.3 (T0: single user), §8.6 point 4; ADR-010 alternatives; threat-model §3.1 (zones H, C, A), SEC-201 | My trust-domain picture has agents inside the operator account. E requires a separate agent zone. These are different proposals: my §8.6 discussed a separate uid **for `mercuryd`**; E proposes one **for agents**, with `mercuryd` staying in the operator's uid. They are compatible. | Redraw overview §5.3 with E's three zones. Keep ADR-010 (LaunchAgent as the operator) and add ADR-013 for the agent uid. | A |
| RA-25 | Medium | ambiguous-contract | ADR-012 (M1 shadow ≥ 2 weeks, ≥ 90 % agreement "with actual gate approvals", M2 pilot 10 tasks); F App. A M9 (shadow ≥ 5 days, pilot ≥ 5 issues); traceability OD-16 | Migration exit criteria disagree. "Agreement with gate approvals" is not measurable until M0 has inventoried the legacy gate format. | F's roadmap is the source of truth for stage criteria. ADR-012 keeps only the partition rules (label opt-in, `legacy_claim` refusal, no Slack mirror). The agreement metric is defined after M0 or dropped. | F, A |
| RA-26 | Medium | contradiction | traceability §1.1 (SEC-001–099 reserved; TC refs SEC-030/040/050); threat-model (SEC-100…905); overview §10 (NFR-LAT-01…); macos-service §2 (REL-01…15); traceability ADR-P01…P15 | Requirement ID schemes collide (known disagreement 9). | See §4, item 9. | F |
| RA-27 | Medium | missing-requirement | brief §G; overview §5.2 (Notification Policy: "no new channel without an ADR"); macos-service §11.4–§11.5 (ops issue, `osascript`); github.md §6.4 (withheld security findings); F ADR-P12, OD-12 | **No ADR covers notification channels or how the operator answers from the iPhone.** Every escalation resolution (resume, grant, ack) needs the local CLI, so an operator on the iPhone can see an escalation but not resolve it. A-SEC-4 forbids GitHub or Linear text as a control input. | New **ADR-019 Notification and operator-response channels**. Channels: GitHub review requests and @mentions (workflow), Linear comments (issue-level), the App-Ops issue (ops), local notifications (credentials and disk only). Responses: local CLI only in v1. Record the iPhone limitation as an accepted tradeoff, with an operator decision on whether a verified-author response channel is wanted later (F OD-12). | A, F, Operator |
| RA-28 | Medium | ambiguous-contract | state-machine §1.2 (17 states), §1 `DISCOVERED`; overview §9.1 and github.md §18 ("18 states") | State count and `DISCOVERED` status are inconsistent (known disagreement 11). | See §4, item 11. | A, B |
| RA-29 | Medium | contradiction | FR-020 enum (`authorize, defer, reject, needs_human`); schema (`authorize, decline, defer, needs_spec, needs_human`); overview §8.2 (`authorize, decline, needs_spec`); claude.md `plan_review` "`needs_reauthorization`" (not in the enum) | Decision enums drift between the requirements, my overview, B and the schemas. | The schemas are the single source of truth for enums. FR-020 cites the schema ID instead of listing values. B removes `needs_reauthorization`; an out-of-scope plan is `reject` with finding code `scope_exceeded`, leading to `BLOCKED` and then reauth. | F, B, A |
| RA-30 | Medium | ambiguous-contract | state-machine §5 holds (no notification for `spec_changed`, `dependency_unresolved`, `deprioritized`) | Holds never notify. A hold that never clears (Claude re-auth keeps failing, a blocker that never closes) recreates the Slack-era silent stall (the 14 h pain point). | Every task-scoped hold gets `max_quiet` (default 72 h wall time). Exceeding it sends one `decision_needed` digest notification per hold epoch, without changing state. `mercury status` shows hold age. | C |
| RA-31 | Low | contradiction | components §7.2 (`runs.status` enum); macos-service §3, D report (`interrupted`, `adopted`) | D's run statuses are not in C's DDL. | C's enum wins. D maps `interrupted` to `lost` plus `failure_class = environment` and `adopted` to a flag. D updates its text. | D |
| RA-32 | Low | contradiction | recovery.md §3 (`side_effects` table); components (`outbox`); ADR-002 (`outbox`, `agent_runs`, `processes`, `reviews`) | Table names drift (`side_effects`/`outbox`, `agent_runs`/`runs`, `reviews`/`pr_reviews`, `processes` absent). | C's DDL names are canonical. A and D revise their references. | A, D |
| RA-33 | Low | contradiction | ADR-002 §8 (keep 14 daily backups; forward-only migrations); macos-service §13–§14 (7/4/5 retention; expand/contract migrations) | Backup and migration policy differs. | ADR-002 defers to D for both. | A |
| RA-34 | Low | contradiction | ADR-001 §3 (Octokit, zod or ajv); components §1 (no Octokit, Ajv, smol-toml) | Dependency list differs. | Adopt C's minimal set in ADR-001. | A |
| RA-35 | Low | contradiction | ADR-007 (2 min overlap, 15 min reconcile); linear.md §3.2 (5 min overlap, 30 min reconcile) | Polling parameters differ. | ADR-007 keeps the principle; values come from linear.md and github.md. | A |
| RA-36 | Low | ambiguous-contract | ADR-005 §3 (resume vs fresh left open); codex.md §3.3 (fresh implementation thread) | My ADR left open a choice B has made. | Revise ADR-005 to state a fresh implementation thread bound to `plan_sha256`, per-task `CODEX_HOME`, and agent-uid launch. | A |
| RA-37 | Low | other | overview §7.2 sequence (step "status Done via outbox"; `mercury.implementation_report.v1`; review posted "as COMMENT"); messages.md catalogue | My sequence diagram uses old schema IDs and the old Linear ownership. | Regenerate the diagram from messages.md IDs and B's ownership. | A |
| RA-38 | Low | other | brief step 9 vs ADR-006, codex.md finding 1 | All agents agree Codex prepares the *change* and the coordinator prepares the PR. It is still a deviation from the brief's literal wording. | Record it in TDD §25/§26 as a justified deviation, citing `.git` protection and least privilege. | Orchestrator |

### 3.2 Responsibility-boundary audit

**Method.** I checked every transition initiator in state-machine §3, every control-API method in components §5.4, and the decision tables in B and E against the core boundary.

| Boundary | Status | Evidence | Gap |
|---|---|---|---|
| Only Claude decides authorization, plan approval and PR acceptance | **Held** | I18/I19, DB triggers, no control-API method for approve or authorize, the Decision Recorder as sole writer | RA-05 (revoke and amend contract missing); RA-11 (catalogue drift) |
| MERCURY coordinates and never substitutes judgement | **Held, with two soft spots** | Deterministic diff gate, holds, budgets. Claude cannot raise budgets (C R3) | (a) T15 says a file "outside plan but inside scope is not a rejection". This is a deterministic rule, so acceptable, but Claude's PR review must receive the out-of-plan file list as a fact (SEC-309 does this). (b) RA-09: operator-only escalation acknowledgements are reachable by same-uid agents |
| Codex implements only approved work | **Held** | I3/I4 CHECKs, approval guard, implementation prompt built from artifact bytes, never from the worktree | Re-authorization must also invalidate the plan approval (RA-05c) |
| Codex never decides | **Held** | `needs_plan_change` and `blocked` statuses route through a Claude `revision_request` (T17, T19) | — |
| Human holds merge authority | **Approval: preventive. Merge actor: detective unless G-ORG or G-SPLIT** | E §5.2 proof, B ruleset, merge verification | See §4, item 6 |
| Human decisions stay human | **Weak** | Control socket principals are policy-only | RA-09 |
| Linear can only stop work | **Held** | I17, overview §9.2 rule 1 | B's spec-drift design moves tasks backwards to `AWAITING_AUTHORIZATION` (RA-01). That is still a "stop", but outside the table |

### 3.3 ADR disposition (my Phase 2 ADRs and needed new ADRs)

| ADR | Disposition | Required change |
|---|---|---|
| ADR-001 Runtime | Revise (minor) | Dependency set per C (RA-34) |
| ADR-002 SQLite store and queue | **Revise** | Derived queue; C's table names; one mutating run per task; backups and migrations defer to D (RA-15/16/32/33) |
| ADR-003 Hub-and-spoke | Revise (minor) | No MCP in v1 (RA-12); revision instructions per §4, item 7 |
| ADR-004 Claude decision service | **Revise** | Canonical six decision types plus `reauthorize` mode; `FAILURE_TRIAGE` deferred; Claude reads snapshots only; "Claude unavailable" timer aligned with C §7.3 (24 h wall, not 4 h awake) (RA-11/13) |
| ADR-005 Codex invocation | Revise | Fresh implementation thread, per-task `CODEX_HOME`, agent uid via broker, `deps_install` and `verify` as agent uid (RA-08/36, RA-02) |
| ADR-006 Coordinator owns git and PR | Revise | `COMMENT` only; merge-conflict path per C; protected-path list from SEC-310; branch naming tied to the Linear ownership mode (RA-04/10/11) |
| ADR-007 Polling | Revise (minor) | Parameters by reference (RA-35) |
| ADR-008 Identities and governance | **Split and supersede** | Becomes the **identity inventory** (App-Main, App-Ops, App-Auditor, Linear app, optional deploy keys, permissions per RA-06/07). Governance options move to the new ADR-014 |
| ADR-009 System-of-record split | **Revise** | Linear status ownership per B's default; `spec_hash` definition; drift by hold (RA-01/10) |
| ADR-010 LaunchAgent | Revise (minor) | Values by reference to D; note that it covers the coordinator only, while agents follow ADR-013 (RA-22/24) |
| ADR-011 Authority records | **Revise** | HMAC required; `scope_version`; plan approval binds `spec_hash`; reauth, revoke and amend contract; operator revocations table (RA-05/19) |
| ADR-012 Migration | Revise | Partition rules only; criteria in the roadmap (RA-25) |
| **ADR-013 (new)** | Agent process isolation via a separate macOS uid | The broker for spawn, signal, identify and sweep; interim fallback with exit criteria; Phase 0 gate (RA-02; E's A-SEC-2) |
| **ADR-014 (new)** | Merge-actor enforcement and required MERCURY checks | G-ORG, G-SPLIT, G-DETECT, plus the required `MERCURY / claude-review` and `MERCURY / policy` check runs; written risk acceptance for G-DETECT (E's A-SEC-1; F's ADR-P05) |
| **ADR-015 (new)** | Task condition model: holds vs `BLOCKED`, and the derived queue | Known disagreements 1 and 2 |
| **ADR-016 (new)** | Filesystem layout and ownership | Three roots (RA-03; F's ADR-P15) |
| **ADR-017 (new)** | Claude review snapshot | Git-object snapshots for all Claude-readable trees (RA-13) |
| **ADR-018 (new)** | Audit integrity | Hash chain, HMAC on authority rows, off-host anchor via App-Ops, failure semantics (RA-19/20) |
| **ADR-019 (new)** | Notification and operator-response channels, plus user presence for safety-relaxing commands | RA-09, RA-27; F's ADR-P12 |
| **ADR-020 (new, small)** | Detached agent runs and adoption after a coordinator crash | `runwrap`, file-based stdio, adopt Codex and `verify`, re-run Claude (known disagreement 10) |

Coordinator-owned commits (ADR-006) and the system-of-record split (ADR-009) need revisions but **not** new ADRs.

**Mapping of F's provisional keys to final ADR numbers:**

| F key | Final ADR |
|---|---|
| P01 | 001 |
| P02 | 002 + 015 |
| P03 | 007 |
| P04 | 008 |
| P05 | 014 |
| P06 | 006 |
| P07 | 004 |
| P08 | 005 |
| P09 | 010 |
| P10 | 009 (revised) |
| P11 | 011 + 018 |
| P12 | 019 |
| P13 | 003 |
| P14 | 005 §6 (deps install) |
| P15 | 016 |

F has no keys for ADR-009, -012, -013, -017 or -020; F adds them.

---

## 4. Positions on the known disagreements

1. **`BLOCKED` with auto-resume (A) vs holds separate from states (C). Recommendation: C's holds.**
   - I withdraw my position. `BLOCKED` should mean "a person must act", so that each `BLOCKED` notification is actionable. Conditions that clear themselves (spec change pending Claude, dependency, deprioritized, sleep, network, rate limit) do not change the phase, and keeping the state preserves the resume point without a resume table.
   - Two amendments: RA-30 (a quiet-period digest, so holds cannot become silent stalls) and RA-18 (a repo-scoped `integrity_alert` hold).
   - AP-9 in my overview changes to "fail closed: hold or block, and escalate once".

2. **`jobs` table (A) vs a queue derived from task state (C). Recommendation: C's derived queue.**
   - Every claim already creates a `runs` row with a lease and fencing token. A separate `jobs` row would be a second record of "what should happen next" that can diverge from `tasks.state`.
   - The derived queue keeps the property ADR-002 was written for: state, run claim and outbox commit in one transaction.
   - Polling and housekeeping, which are not task actions, run on C's timer service and need no queue.

3. **HMAC on authority records optional (A, C) vs required (E); hash-chain anchoring table missing. Recommendation: HMAC required; anchoring required before unattended operation, with the table added now.**
   - My earlier argument (no value inside one uid) is weaker once SEC-201 creates a second uid. HMAC then defends against an agent-uid process with write access to a mis-moded file, and against a restored or tampered backup. The cost is roughly 30 lines plus a Keychain item MERCURY already reads.
   - It still does not defend against a same-uid attacker. The TDD must say so (E already does).
   - Anchoring needs App-Ops (RA-07) and the RA-20 table. It should be live before the M9 cutover, not in M1.

4. **Filesystem layout. Recommendation: ADR-016 with three roots (RA-03).**
   - State in `~/Library/Application Support/Mercury` (four of five agents agree).
   - Space-free `WORK_ROOT`. Its location depends on the SEC-201 decision: `/Users/Shared/Mercury` if there is an agent uid, `~/Library/Mercury` otherwise.
   - `~/MercuryWork` (mine and C's) is withdrawn, because it puts work trees in a visible home folder for no gain over D's choice.

5. **Separate macOS agent user (E: SEC-201 MUST) vs same-user process groups (C, D). Recommendation: adopt SEC-201 as the target, with ADR-013 and a Phase 0 go/no-go gate.**
   - E's analysis is correct: agents that can read `~/.config/gh` or the Linear key can impersonate the human, and that defeats every GitHub control. This is the only path where one technical failure breaks the invariant.
   - Before adoption, D must design the root-owned broker (RA-02). C's process-group and adoption design stays, executed through the broker.
   - Interim operation without the uid (E's deny-profile fallback plus canary tests) is acceptable only in the sandbox and the shadow stage. Supervised pilot on real repos requires the uid or a written risk acceptance.

6. **Merge governance: G-1/G-2 (A) vs G-ORG/G-SPLIT/G-DETECT (E) vs B's detect-after. Recommendation: one ADR (ADR-014) using E's names.**
   - G-1 = G-DETECT and G-2 = G-ORG.
   - **G-ORG is preferred** for target repos before unattended operation. **G-DETECT** is acceptable for sandbox and supervised pilot with written risk acceptance. **G-SPLIT** is an alternative only if Phase 0 confirms ASM-E-01, -02 and -07. It adds a second credential, and deploy keys bypass the `workflows` check, so SEC-310 becomes the only workflow-file control.
   - **In all modes**, adopt B's required, App-pinned `MERCURY / claude-review` check (plus `MERCURY / policy`, RA-06). It makes "human merges only Claude-reviewed SHAs" preventive even on a personal account.
   - Accept B's tradeoff: when MERCURY is down, MERCURY PRs cannot merge without an audited ruleset edit (runbook in recovery.md).

7. **`revision_request` as a separate Claude decision (B) vs verbatim forwarding (C). Recommendation: C's hybrid.**
   - When the source is already a validated Claude review (plan review or PR review), Codex receives that review's `required_change` texts verbatim. They are Claude's words, bound to the review hash, rendered by a fixed template whose hash is recorded.
   - A Claude `revision_request` run is mandatory for non-Claude sources: CI, local tests, human review, merge conflict, diff gate and Codex deviation.
   - This satisfies B's invariant ("the coordinator never edits an instruction into a Codex prompt by itself"): the coordinator chooses no words. It also avoids an extra run.
   - B amends claude.md §3 trigger (a).

8. **Linear status ownership: B (MERCURY → In Progress; integration → In Review/Done) vs A's open decision on who closes. Recommendation: B's default** (RA-10).
   - My premise was wrong: branch names with the issue ID are closing links.
   - The operator may choose `mercury_owns_all` (branch names without the ID) if a verified `Done` matters more than the familiar branch convention.
   - Either way, Linear `Done` is never treated as merge proof (C §8.4 already holds blockers until MERCURY verifies).

9. **Requirement ID schemes. Recommendation:**
   - **F owns IDs.** FR, NFR, CON and OPS are canonical.
   - **E's SEC-100…905 are adopted as-is** (they are already cited across documents), and F drops the SEC-001–099 reservation, remapping TC references.
   - My NFR-LAT, REL, AUD, SEC, NOT, RES, AVL, MNT and COST IDs and D's REL-01…15 become **aliases**. F maps each to an NFR number in one table in traceability.md, and the aliases are then removed from overview.md and macos-service.md, which cite F's IDs. Where targets differ (restart ≤ 45 s vs ≤ 60 s), F picks one and records why.
   - ADR keys follow the §3.3 mapping.

10. **Re-attach vs re-run after a crash. Recommendation: no real disagreement.**
    - C and D agree: Codex and `verify` runs (detached, file-based stdio, `exit.json`) are adopted; Claude SDK runs (pipes) are killed and re-run without consuming an attempt, using the same `input_digest`.
    - What is missing is an ADR (ADR-020) and the RA-31 status vocabulary.
    - Under SEC-201, adoption runs through the broker (RA-02).

11. **`DISCOVERED` removed as a task state (C) vs the brief. Recommendation: accept C's change.**
    - The brief allows renames with justification, and C's justification holds: without it, the one-active-task-per-issue index would be meaningless, and hundreds of authority-less rows would be created.
    - `DISCOVERED` survives as `linear_issues.mercury_status = 'discovered'`. TDD §11 must include a mapping table from brief names to design states and issue properties, so a reader can confirm every brief state is represented.
    - Overview §9.1 and github.md §18 change "18 states" to "17 task states plus the issue-level `discovered` status".

12. **`MERGE_UNVERIFIED` / integrity alert (B, F asked; C). Recommendation: no new state.**
    - Use C's `BLOCKED(merge_verification_failed)` (T35). It is non-terminal, stays out of `COMPLETED` (FR-182 satisfied), and exits only by operator `ack-merge` (T40, user-presence) or re-verify.
    - Add the repo-scoped `integrity_alert` hold (RA-18).
    - B's "stay in `MERGED` with a flag" is rejected because `MERGED` is a work state that the dispatcher would keep trying to complete.
    - F's acceptance text should say `BLOCKED(merge_verification_failed)`.

---

## 5. Items needing operator decision

| # | Decision | Options | Architect's recommendation |
|---|---|---|---|
| OP-1 | Meaning of "Claude is the primary orchestrator" | (a) Claude holds decision authority; the coordinator holds the loop (all designs assume this). (b) A conversational Claude session drives the loop | (a). Interactive sessions may *request* decisions through the CLI |
| OP-2 | Merge-actor mode (ADR-014) | G-ORG / G-SPLIT / G-DETECT | G-ORG before unattended operation; G-DETECT with written acceptance for sandbox and pilot |
| OP-3 | Separate agent macOS user (ADR-013) | Adopt (needs a one-time root setup: user, group, broker) / defer with written acceptance of R-03 | Adopt; it gates the supervised pilot on real repos |
| OP-4 | Linear `Done` owner | Integration (branch keeps the issue ID) / MERCURY (branch without ID) | Integration (B's default) |
| OP-5 | Additional GitHub identities | App-Ops (ops issue and anchors) required; App-Auditor (read-only drift monitor) optional | Create both; without App-Auditor, SEC-108 becomes a manual check |
| OP-6 | Operator response channel for escalations | Local CLI only / also a verified GitHub channel later | CLI only in v1. Accept that escalations cannot be resolved from the iPhone |
| OP-7 | User-presence prompt for safety-relaxing CLI commands | Touch ID or password helper / TTY plus nonce (policy) | Touch ID or password helper |
| OP-8 | MERCURY-down merge procedure | Audited ruleset edit removing the required MERCURY checks / wait | Wait by default; audited edit only via the runbook |
| OP-9 | Previously listed decisions still open | OD-A-02 (eligibility marker), OD-A-04 (billing), OD-A-05 (expiry and limits); B's OQ-B-01…09; C's OD-C-01…07; F's OD-01…16 | Deduplicate into one decision register in TDD §30, with F owning the numbering. OD-A-03 is withdrawn (RA-10) |

---

## 6. Confidence

| Area | Confidence | Basis |
|---|---|---|
| Contradiction findings (RA-01, 03, 04, 06, 08, 10–12, 14–17, 19, 22, 26, 29, 31–35) | **High** | Each is cited from two or more documents read directly; schema enums were extracted by script |
| RA-02 (a cross-uid signalling limit makes the broker mandatory) | **High** for the POSIX rule (`kill(2)` needs the same uid or privilege); **Medium** for the broker design, not yet specified |
| RA-09 (agent can clear human escalations) | **High** that the path exists (C states it is policy-only); **Medium** that a LocalAuthentication helper is feasible in a LaunchAgent context (Phase 0) |
| RA-05 (reauth, revoke and amend contract gap) | **High**: no schema or transition covers the cases listed |
| Positions in §4 | **Medium-High**: they reconcile designs rather than resting on measured behaviour; items 3, 5 and 6 depend on Phase 0 results (ASM-E-01/02/04/07, broker feasibility) |
| Completeness of this review | **Medium**: the verification plan and a full line-by-line read of components.md and threat-model.md were outside my focus; other reviewers cover those |
