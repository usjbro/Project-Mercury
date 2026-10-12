# Phase 4 — Architecture Reconciliation Decisions (orchestrator)

Status: **Binding for Phase 4 revisions.** Every decision below resolves a disagreement or finding raised in Phase 3 (`reviews/20`–`25`). Each records the competing positions, the decision, the justification against the requirements, the residual risk, and the documents that must change. Where the decision belongs to the operator, the design adopts a **default** and the item is registered as an operator decision (OD) in TDD §30; the design must work under every listed option unless stated otherwise.

Inputs: Phase 3 reviews by A (38 findings), B (27), C (41), D (31), E (29), F (37). Severity totals across reviews: Critical 3 (RF-01, RD-01, RE-01 — all the same root cause: SEC-201 unimplemented), High 52, Medium 118, Low 30.

## Decision log

### RD-1 Process isolation: agents run under a dedicated macOS uid (resolves RF-01, RD-01, RE-01, RA-02, RB-08, RC-09, RD-02, RD-25, RD-26)
- **Positions.** E (Phase 3): run the whole MERCURY stack in a dedicated user account ("U2"); agent-uid separation from the coordinator ("U1") only SHOULD. A, B, C, D, F: coordinator stays an operator-uid LaunchAgent; agents run as a separate uid `_mercuryagent` through a root-owned broker (D §4.5 gives a concrete design).
- **Decision.** Adopt **D §4.5 / A ADR-013**: `mercuryd` remains a LaunchAgent in the operator's GUI session (ADR-010). **Every process that executes model-directed or repository-derived code** — Codex planning and implementation, the L2 `verify` run, `deps_install`, and Claude decision runs — executes as `_mercuryagent` (primary group `mercury`) via root-owned, fixed-grammar wrappers `agent-exec` (spawn) and `agent-ctl` (signal / probe / list / stats / sweep), invoked through a restricted sudoers drop-in. Secrets reach agents only on fd 3; agent `HOME` = `/Users/_mercuryagent` holding caches only. Seatbelt (Codex sandbox and the L2 profile) is the **second** layer.
- **Why not U2 alone.** U2 protects the human's credentials but leaves MERCURY's own App key, Linear app token and control token readable by agents. A hostile agent could then forge the required `MERCURY / claude-review` check and post as MERCURY, defeating the software-enforced review-ordering control. D's design protects both the human's and MERCURY's credentials from agents at comparable setup cost (one-time root setup that the operator performs in Phase 0). U2 for the coordinator is recorded as an optional future hardening (it would additionally hide MERCURY's state from the operator's own interactive agents); see OD-36.
- **Claude decision runs.** Agent SDK with a custom spawn through `sudo -n -u _mercuryagent agent-exec --kind claude` (pipes preserved; key on fd 3; config dir under `WORK_ROOT/runs/<run>/claude-config`). If the Phase 0 SDK spawn test fails, the fallback is B's ALT-B-1 (Messages API with coordinator-implemented, realpath-confined Read/Grep/Glob over the snapshot), which removes the Claude subprocess entirely.
- **Gates.** Same-uid execution with Seatbelt deny profiles is allowed only with fakes and the sandbox repo (M1–M4). **No workspace-write Codex, `verify` or `deps_install` run against a non-sandbox repository until SEC-T-20 (credential canaries) passes on the real Mac.**
- **Residual risk.** Kernel/sudo misconfiguration; `ps` argv visibility across uids (ASM-D-30); toolchains must be provisioned per repo (`mercury toolchain sync` into `WORK_ROOT/toolchains`, coordinator-owned, agent read/execute only).
- **Changes.** A: new ADR-013, overview §5.3 three trust zones. C: `ProcessSupervisor`/`AgentLauncher` port with `agent-ctl` adapter; `runwrap` merged into `agent-exec`. D: macos-service §1/§3/§7/§9/§16 to §4.5; P0-26…P0-32. E: SEC-201 text updated to this model; SEC-T-20. B: claude.md §2/§7, codex.md §5/§6 to agent uid. F: P0b + M1 scope.

### RD-2 Filesystem layout (resolves RA-03, RD-14, known disagreement 4)
- **Decision (ADR-016, D owns the table in `operations/macos-service.md` §7.1; all other docs reference it).**
  - `MERCURY_HOME` = `~/Library/Application Support/Mercury` — operator uid, 0700: DB, artifacts, config, control socket, `run/` state.
  - `WORK_ROOT` = `/Users/Shared/MercuryWork` — space-free; owner operator, group `mercury`, 0750 + inherited ACLs: mirrors, task worktrees, review snapshots, per-task `CODEX_HOME`, per-run I/O, toolchains. Agent-writable only where required (task worktree, `CODEX_HOME/sessions`, run scratch).
  - Logs = `~/Library/Logs/Mercury`.
  - `~/MercuryWork` and `~/Library/Mercury` are withdrawn. All paths come from one constant module.

### RD-3 Holds vs BLOCKED; derived queue (resolves known disagreements 1–2, RA-01 partially)
- **Decision (ADR-015).** C's model: task `state` records workflow phase; **holds** (pause, sleep, offline, rate limit, `spec_changed`, `dependency_unresolved`, `deprioritized`, `integrity_alert` (repo-scoped)) suspend dispatch without changing state. `BLOCKED` means **a human must act**, with reason codes. The queue is derived from `tasks.state` + holds + leases; no `jobs` table.
- **Amendments.** (a) Hold ageing: a hold active longer than its threshold (defaults `spec_changed` 24 h, `dependency_unresolved` 7 d, `deprioritized` 14 d, of awake time) escalates once to `BLOCKED(needs_human_decision)` or a digest notification. (b) Security conditions are **never** auto-clearing holds: they are `BLOCKED(security_escalation)` or a global/repo `security_halt` cleared only through the human-presence tier (RD-12). (c) A hold whose clearing re-enables Codex work clears only through the authorization guard. (d) Holds can emit outbox effects (needed for check-run updates; RC-02).

### RD-4 Audit integrity (resolves known disagreement 3, RA-19/20, RD-06, RE-09)
- **Decision (ADR-018).** Hash-chained `audit_log` **MUST**; off-host anchoring of the chain head **MUST** before unattended operation (M7), carried in App-posted artifacts that already exist (check-run output summary, Linear completion comment, daily ops anchor in a private anchor repo via `mercury-ops`). HMAC on authority rows (`record_mac`) **SHOULD** — with agents under a separate uid they cannot write the DB at all, so HMAC defends only restored/tampered backups. C adds `anchors` and `audit_epochs` tables. Restore and new-Mac flows record an operator-initiated `audit.restore_epoch` event; unverifiable authority after restore maps to `BLOCKED(reauthorization_required)`, never to `guard_integrity_failure`. Startup verifies the chain; failure → safe mode (no dispatch) + one SECURITY notification.

### RD-5 Merge governance and required MERCURY checks (resolves known disagreement 6, RA-04, RB-03/04/05/06, RC-01/02, RE-05, RF-07)
- **Decision (ADR-014; ADR-008 becomes the identity inventory).** Names: **G-ORG** (repos in an organization, only the operator may merge/update `main`), **G-SPLIT** (no MERCURY credential with merge capability; only if Phase 0 verifies ASM-E-01/02/07 and RB-06's two tests), **G-DETECT** (personal repo; merge actor verified after the fact).
  - Sandbox and supervised pilot: G-DETECT acceptable **with written operator risk acceptance**. Before unattended or overnight operation on target repos: **G-ORG required**.
  - **All modes**: ruleset requires PR, 1 approval, Code Owner review (CODEOWNERS = operator only), approval of most recent reviewable push, dismiss stale approvals, no bypass, block force-push/deletion, `allow_auto_merge=false`, and two **required check runs** created by the MERCURY App and pinned to it by integration id: `MERCURY / claude-review` (success only when Claude code + security reviews pass for the exact head SHA) and `MERCURY / policy` (deterministic pre-checks; neutral/failure until the operator acknowledges protected-path, dependency or build-script changes through the human-presence tier). The App therefore needs `checks:write`; B verifies in Phase 0 whether pinning additionally requires `statuses:write` (RB-05) and grants it if so.
  - **Claude reviews are posted as `COMMENT` reviews only.** MERCURY never submits `APPROVE` or `REQUEST_CHANGES`, never dismisses reviews, never calls merge, `update-branch`, or auto-merge endpoints (enforced by an endpoint allowlist in the GitHub adapter, SEC-102). The gate is the check run.
  - T22 (wait for CI) waits only on non-MERCURY required checks (no self-deadlock).
  - MERCURY-down merge: wait by default; audited ruleset edit only via runbook.

### RD-6 Identities (resolves RA-06/07, RB-15, RD-08, F OD-20)
- **Decision.** Two GitHub Apps. **`mercury-bot`** (target repos): `contents:write`, `pull_requests:write`, `checks:write`, `metadata:read` (+ `statuses:write` only if RD-5's pinning test requires it); never `workflows`, `administration`, or `actions`. **`mercury-ops`**: `issues:write` on `project-mercury` (heartbeat + ops alerts), `contents:write` on a private anchor repo, `metadata:read` on targets (ruleset drift monitor reads `/rulesets` with metadata:read, RB-16 — governance must therefore use rulesets, not classic protection). Installation tokens are narrowed per purpose. Linear: OAuth app with `actor=app`. Model keys: dedicated Anthropic workspace key and OpenAI project key, each with spend limits (OD-03/04). No agent or coordinator path ever uses the operator's GitHub or Linear credentials.

### RD-7 Claude reads git-object snapshots (resolves RA-13, RE-06, RF-05, known disagreement — review substrate)
- **Decision (ADR-017).** Every tree Claude reads (authorization/plan review at `base_sha`; PR review at `head_sha`) is a coordinator-built snapshot from `git ls-tree`/`cat-file` in the mirror: no `.git`, gitattributes not applied (export-ignore cannot hide files), symlinks rendered as placeholders, files 0444 / dirs 0555 under `WORK_ROOT/snapshots/<tree_sha>/`, readable by the agent uid. Replaces "reference/review checkout" everywhere. Claude never runs inside a Codex worktree.

### RD-8 Revision requests (known disagreement 7, RB-22)
- **Decision.** C's hybrid. When the source is a validated Claude review bound to the current plan hash / head SHA, its `required_change` items are rendered **verbatim** through a fixed, hashed template (Claude's words; coordinator chooses none). A Claude `revision_request` decision run is mandatory for every other source: CI failures, local test failures, merge conflicts, human `CHANGES_REQUESTED` reviews, diff-gate violations, conflicting or `needs_plan_change` reviews. `mercury.revision.request.v1` carries `producer.kind` and provenance. CI logs are untrusted (T4) and never go to Codex without Claude mediation.

### RD-9 Linear status ownership (known disagreement 8, RB-14, RC-11)
- **Decision.** The interface supports two modes, configured per team (OD-06):
  - `integration_owns_done` (**pilot default**): branches keep the issue ID; Linear's GitHub integration moves In Review/Done; MERCURY writes `In Progress` and comments only; MERCURY posts a verification comment after merge verification.
  - `mercury_owns_all` (security-preferred, E): branch names without the issue ID and non-closing PR phrasing; MERCURY sets `Done` only after merge verification.
  - In both modes Linear `Done` is never merge proof; MERCURY's dependency guard requires a MERCURY `COMPLETED` for MERCURY-managed blockers.

### RD-10 Identifier scheme (known disagreement 9, RF-02/03, RD-21)
- **Decision.** F owns the registry in `planning/traceability.md`. Prefixes: `CON-`, `FR-`, `NFR-`, `OPS-` (F); `SEC-1xx…9xx` (E, statement text stays in threat-model; RTM cites it; F's SEC-001…099 reservation retired). Invariants `INV-01…` (C's I1–I20 renamed, C owns). Test properties `PROP-nn`. Tests `TC-<LEVEL>-nnn` only; contributor IDs become aliases. ADRs `ADR-001…020` (A); `ADR-Pnn` retired. Assumptions `ASM-<agent>-nn` each linked to a Phase 0 check `P0-nnn`. Operator decisions single `OD-nn` list (F §8, plus OD-36…). Risks `RISK-nn`. Alias table in traceability.md. **Operational parameter values: D's §4.10 table is the single source**, registered by F, referenced by TDD §18/§20 and all docs (no restating numbers elsewhere).

### RD-11 Crash adoption, lost runs, durability (known disagreement 10, RD-04/05/10/11/12/17, RA-31)
- **Decision (ADR-020).** Codex and `verify` runs are detached under `agent-exec` with file stdio and are **adopted** after a coordinator restart when the identity triple matches (`run_id` marker, start time, boot session). Claude runs (pipes) are killed and re-run with the same `input_digest`, consuming no attempt. The authorization guard is re-evaluated **before** an adopted output is acted on. `agent-exec` enforces the hard awake-time deadline and a **supervisor lease** (`run/coordinator.alive` stale > 10 min credited time → SIGINT→SIGTERM→SIGKILL, `exit.json{reason: supervisor_lost}`). New run outcome class `lost_by_host` (boot session changed or supervisor lost): consumes no attempt; separate cap 5 per step → ops alert, not BLOCKED. On SIGTERM: stop dispatch, interrupt non-adoptable runs, keep adoptable runs, checkpoint, exit within `ExitTimeOut`. Adopted runs are never kept through safe mode or a security halt.
- **Worktree reset policy (single definition, C §9):** archive uncommitted changes as a patch artifact → `reset --hard tasks.last_commit_sha` (or `base_sha`) → `clean -ffd`, adding `-x` only when `deps_install` is re-queued. "Checkpoint commits" are removed.
- **Durability:** mirror `core.fsync=committed,reference`; order = git commit → fsync → DB transaction recording the SHA; `exit.json`/`proc.json` written with fsync + rename + dir fsync; recovery verifies `git cat-file -e` and refs, else `lost_by_host` and replay from last durable commit.
- **Startup/exit contract (D):** `flock` is the single-instance guard (D's `instance_lease` dropped); lock held → exit 0; DB corruption → stay alive in safe mode; schema too new → `fatal.json`, exit 0. `KeepAlive{SuccessfulExit:false}`.
- **Event-loop blocking:** backups/`integrity_check` in a worker thread with its own read connection; lease rows persisted ≥ 60 s.

### RD-12 Human-presence tier for safety-relaxing commands (resolves RA-09, RE-04)
- **Decision (ADR-019).** Control-socket principals: `operator-presence` commands — `ack-merge`, security resume/unhalt, `adopt`, budget/revision `grant`, `policy ack`, post-incident `unpause`, ruleset-emergency runbook — require a local user-presence confirmation (Touch ID or password via a small signed helper using LocalAuthentication). Plain `operator` commands (status, pause, cancel, authorize-request) need only the 0600 socket token. A process running as the operator (including the operator's interactive Claude) can therefore *request* but never *clear* an escalation. Policy (OD-E-02): the operator restricts interactive agents from `gh pr review --approve`/`gh pr merge` and removes Linear write connectors acting as the human.

### RD-13 Spec drift (resolves RA-01, RC-04)
- **Decision.** Compared value = B's `spec_hash` (normalized title + description + acceptance criteria + labels relevant to eligibility). On change after authorization: `spec_changed` hold (C); results of runs that finish after the change are **not acted upon** until Claude re-authorizes against the new hash (the authorization guard checks `spec_hash` at result-application time, not only at dispatch). PR-stage tasks keep the PR open (B's protection) and require re-authorization before further Codex work; Claude may confirm "no material change". Re-authorization is a new authorization version; the old one is superseded, never mutated.

### RD-14 State model details (known disagreements 11–12, RB/RC/RD timer items)
- `DISCOVERED` is an issue-level status (`linear_issues.mercury_status`), not a task state; TDD §11 carries a brief-name → design mapping table. 17 task states.
- Merge verification failure → `BLOCKED(merge_verification_failed)`; scope by failed check (RD-31): wrong merge actor or merge commit not on base → global `security_halt`; approval/content/review-ordering mismatches → repo `integrity_alert` hold + BLOCKED. `merged_unreviewed_head` (operator merged before Claude review) is a policy notice, not a security incident. Exit via `ack-merge` (presence tier) or re-verify.
- `mercury/policy` escalation is modelled: guard before human review; `BLOCKED(policy_ack_required)`; cleared by `mercury policy ack` (presence tier) which concludes the `MERCURY / policy` check.
- Timer rule (extends INV I20): a state timer may fire only after at least one attempt of the awaited action has been made after the latest wake/start; durations are measured from first observation; on wake, due reminders/expiries are coalesced into one summary notification.

### RD-15 Codex details (RB-01, RB-07, RD-13, RD-15)
- `CODEX_HOME` is **per task**: coordinator-generated read-only `config.toml` + agent-writable `sessions/`; archived at cleanup (SEC-203 amended to "per-task, coordinator-generated").
- Output schemas: a CI-generated **wire copy** of each agent output schema restricted to the provider's strict-mode subset is sent to Codex/Claude; full validation with Ajv against the canonical schema happens in the coordinator. Schema-rejection errors classify as `config_fatal`.
- Stall detection: liveness = stdout growth **or** process-group CPU-time progress (`agent-ctl stats`); stall threshold during a running command ≥ the repo's test timeout.

### RD-16 Sleep and time (RD-03, RD-07, RD-18, RD-22)
- On macOS the monotonic clock **continues** during sleep (ASM-A-04/ASM-F-04 refuted). Normative algorithm (C §10.10): credited awake time = `min(Δmono, Δwall, 3×tick)` per tick; gaps above 30 s not explained by a measured blocking operation are sleep gaps, confirmed by `kern.waketime`. Requirements state behaviour ("sleep gaps are not credited to run budgets"), not mechanism. FakeClock supports both modes; every sleep test runs in both.
- No dispatch during dark wake: require a full-wake signal or ≥ 5 min continuous credited awake time. A small signed sleep-notification helper writes a final `mode: sleeping` heartbeat (watchdog thresholds 45 min awake / 12 h sleeping).
- Latency/availability NFRs are measured from the first awake-and-online instant after the event; NFR-005 covers durable events and final states only.

### RD-17 Security pre-push controls and test execution (RE-02, RE-03, RF-09)
- `verify` (L2 tests) and `deps_install` run as the agent uid under a designed, fail-closed Seatbelt profile; `verify` has **no network**; `deps_install` uses `--ignore-scripts`, a registry allowlist, and only lockfiles whose change was acknowledged via `MERCURY / policy`.
- Coordinator git hardening: never run git with configuration from an agent-writable worktree. Commits are created via plumbing against the mirror (`GIT_DIR=<mirror>`, `GIT_WORK_TREE=<worktree>` read as data, `-c core.hooksPath=/dev/null -c core.fsmonitor= -c protocol.allow=never` …), the worktree `.git` pointer is verified before every git invocation, and **pushes happen from the mirror** with `GIT_ASKPASS` reading the token from an inherited fd (single mechanism; D's socket helper removed).
- Before the first sandbox push (M5 exit): git hardening, secret scan, protected-path pre-checks, `MERCURY / policy`, endpoint allowlist, snapshot builder.

### RD-18 Integration details (RB-10/11/12/13/17/19/21/23, RD-09, RD-19)
- Single retry matrix = B (github.md Part B §15); C implements it. Network-class failures never consume run or outbox attempts while `network_down` is held or the probe fails within 60 s; only non-network errors count toward `dead`. `BLOCKED(network)` deleted.
- Connectivity probe: authenticated, ETag-conditional request (never unauthenticated GitHub probes).
- Dedup keys: one catalogue (B §13) adopted by C; value-keyed facts include an observation sequence so A→B→A transitions are not lost; `findPullByHead` uses `state=all`.
- Linear comment ids: deterministic **v4-shaped** UUIDs.
- Required CI contexts derived from `GET /rules/branches/{base}` at each evaluation, not from static config.
- Authority decisions run with no `fallbackModel`; the model actually used is recorded.
- Credentials read once at start and on `mercury reload-credentials`, held in memory; single Keychain prefix `com.usjbro.mercury.*`.
- PRs open as draft until Claude passes; **target-repo onboarding requires CI to run on draft PRs** (RB stall finding); the human review request is sent only when `MERCURY / claude-review` succeeds.
- Security findings on public PRs: details for medium and below; critical/high and pre-existing findings withheld (generic line + local report ID) (OD-21).

### RD-19 Notifications and operator response (RA-27)
- **Decision (ADR-019, with RD-12).** Channels: GitHub review requests/@mentions (PR ready, CI intervention), Linear comments (issue-level decisions, repeated plan-review failure, completion), `mercury-ops` issue in `project-mercury` (daemon/ops/security halts; GitHub Mobile push), local macOS notification (credentials, disk). Responses: **local CLI only in v1**; the operator can see but not resolve escalations from the iPhone (accepted tradeoff, OD-12). GitHub/Linear text is never a control input.

### RD-20 Orchestrator role
- "Claude is the primary orchestrator" = Claude holds **decision authority** at defined decision points; `mercuryd` holds the loop. An interactive Claude session may *request* decisions/authorizations via the CLI; requests are executed as isolated headless decision runs whose outputs carry the authority. (OD-17.)

## Items that remain operator decisions (defaults adopted by the design)
OD-01 merge mode (default G-DETECT for sandbox/pilot with written acceptance; G-ORG before unattended) · OD-03/04 model billing (dedicated API keys) · OD-05 Linear app identity · OD-06 Linear Done owner (default `integration_owns_done`) · OD-07 concurrency (Codex 1, Claude 2, 1/repo) · OD-08 revision budgets (plan 3, PR 3, CI/test 3, human 5; authorization expiry 7 d) · OD-09 Codex never has network; deps `--ignore-scripts` · OD-10 eligibility (`mercury` label added by operator) · OD-12 CLI-only responses · OD-18 agent uid (adopt) · OD-19 managed settings · OD-20 `mercury-ops` App · OD-35 policy checklist · **OD-36 (new)** optional dedicated macOS account for the coordinator (U2) — default: not in v1. Full register: TDD §30 / `planning/traceability.md`.

## Revision assignments (Phase 4)
| Owner | Must revise | Must also address |
|---|---|---|
| A | overview.md; ADR-001…012 per RA §3.3 table; **new ADR-013…020** | All RA-* findings; RE/RD/RF items naming A |
| B | integrations/claude.md, codex.md, linear.md, github.md | All RB-*; items naming B in RA/RC/RD/RE/RF |
| C | components.md, state-machine.md, messages.md, schemas | All RC-*; items naming C elsewhere (RC-01/02 Critical-equivalent first) |
| D | macos-service.md, recovery.md | All RD-*; items naming D elsewhere |
| E | threat-model.md (update to decisions; SEC text) | RE-* self-items; SEC-201/203/603/604 text; proof §5.2.2 re-run against RD-1/RD-5/RD-12 |
| F | traceability.md, verification-plan.md; **create** planning/roadmap.md and planning/issue-breakdown.md | All RF-*; ID registry; parameter registration; new TCs from RD §4.11, RE, RB; revised milestones |

Each owner records a disposition for every finding addressed to them in `reviews/4X-revision-<agent>.md` (finding ID → fixed / rejected with reason / deferred with owner).

## Addendum A (after Phase 4 revisions)
- **E objection to RD-1 (44-revision-E.md §3) — accepted in part.** With `mercuryd` in the operator uid, a code-execution bug in the coordinator reaches the operator's own GitHub credentials (RISK-27). RD-1 stands for v1 (agents, which execute untrusted content, are isolated; the coordinator executes only MERCURY's own pinned code and parses untrusted data). **OD-36 (dedicated coordinator account, U2) is promoted from "optional future hardening" to a required operator decision before unattended operation**, alongside OD-01 (G-ORG). Second condition accepted: if Phase 0 shows MERCURY Keychain items must trust `/usr/bin/security`, the signed Keychain helper moves into v1 (M1).

## Addendum B (after A and D Phase 4 objections)
1. **`statuses:read` added to `mercury-bot`** (A objection 1). Read-only; needed when a target repo's required context is a commit status. RD-6 amended.
2. **Chain-head anchor carriers** (A objection 2): the `MERCURY / claude-review` check-run summary is **not** used as an anchor carrier on public repositories (consistent with OD-24 default "no public chain-head embed"). Carriers are the Linear completion comment and the private anchor repo via `mercury-ops` (plus the check summary only on private repos). RD-4 amended.
3. **Supervisor alive file** = `WORK_ROOT/ctl/coordinator.alive` (operator-owned 0640, group-readable) (A objection 3, D objection 2). RD-11 clarified.
4. **Parameter-table scope** (D objection 1): accepted as implemented — operational values in macos-service.md §2; workflow policy (attempt counts/backoff, revision budgets, authorization expiry, state reminder timers) stays in state-machine.md / OD-08, referenced by name. RD-10 clarified.
5. **Restore-epoch confirmation is a presence-tier command** (D objection 3): confirmed. RD-12 list extended.
