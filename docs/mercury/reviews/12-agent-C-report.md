# Agent C Report — Staff Engineer: Components, State Machine, Protocols

Phase 2. Design only. Author: Agent C.

Deliverables:

- [`architecture/state-machine.md`](../architecture/state-machine.md): 17 states, 40 numbered transitions + 6 global ones, invariants I1–I20, holds, guards, counters, timers, recovery per state.
- [`architecture/components.md`](../architecture/components.md): module architecture, TypeScript ports, control API, SQLite DDL with invariant-enforcing triggers, dispatch, process supervision, worktrees, pseudocode, locking rules, tests.
- [`protocols/messages.md`](../protocols/messages.md) and [`protocols/schemas/`](../protocols/schemas/): envelope, 15 message schemas (draft 2020-12), 8 strict agent output contracts (draft-07 subset), versioning rules.

---

## 1 Findings

1. **The baseline state list mixes three different things**: phases of work, waits for people, and machine conditions (sleep, offline, rate limits, spec edits). Modelling conditions as states would double the transition table and lose the resume point. They are better modelled as **holds** that block new work without changing state.
2. **`DISCOVERED` is an issue property, not a task state.** Making every eligible Linear issue a task would fill the task table with rows without authority and weaken the "one active task per issue" constraint.
3. **`TESTING` must be a separate state**: the authoritative test run is executed by the coordinator (Agent B's L2 layer), not Codex, on a commit that exists, with its own evidence and failure route.
4. **`MERGED` and `COMPLETED` are both needed**: `MERGED` is the crash-safe checkpoint between "merge observed" and "verified + Linear updated".
5. **Binding invalidation can be derived instead of mutated.** A Claude PR review is valid if and only if its `head_sha` equals the current head; a plan approval matches only its `plan_id`/`plan_sha256` and authorization `scope_version`. No "invalidate" update is needed, so the authority tables can be fully append-only.
6. **Many invariants can be enforced by SQLite itself** (partial unique indexes, CHECKs, triggers): one active task per issue, one mutating run per task, Codex runs need an authorization row, implementation runs need a matching approval, authority rows only from succeeded Claude runs with matching output hash, transitions in sequence, terminal states final, worktree removal only after archive.
7. **`node:sqlite`'s synchronous API lets the design enforce "no await inside a transaction"**, which gives atomicity relative to all other in-process logic without locks.
8. **Detached agents survive a coordinator crash.** With stdout redirected to files and a tiny `runwrap` writing `exit.json`, Codex and test runs can be *adopted* after a restart instead of killed. Claude SDK runs (piped) cannot, and are cheap to re-run.

## 2 Recommended design (summary)

- **Runtime:** Node 24 LTS (pinned), TypeScript strict, `node:sqlite` behind a `Store` port (fallback `better-sqlite3`), Ajv, smol-toml; no other runtime dependencies. One process, one write connection. Hexagonal layering enforced by `dependency-cruiser` ([components §1–§3](../architecture/components.md#1-runtime-and-technology-decisions)).
- **State machine:** 17 states in 5 classes (work, gate, decision point, human wait, terminal); transition table as data with initiator restrictions; holds for conditions; `BLOCKED` = human needed, with reason codes and an explicit resume table; `FAILED` = abandoned; `CANCELLED` = deliberate stop ([SM §1–§6](../architecture/state-machine.md)).
- **Revision budgets:** plan N=3, Claude PR review M=3, test/CI/diff-gate fixes K=3, human change requests H=5; caps in config; only operator `budget_grants` raise them; exhaustion → `BLOCKED` with one notification per epoch ([SM §9](../architecture/state-machine.md#9-revision-cycle-counters-and-escalation)).
- **Queue:** derived from task state (`nextAction`), claimed in one `BEGIN IMMEDIATE` transaction that re-checks version, holds, limits and guards, inserts the run with a lease and fencing token; spawn after commit ([components §7](../architecture/components.md#7-job-queue-and-dispatch)).
- **Processes:** `runwrap` in a new session/process group, files for stdio, identity = pid + pgid + `lstart` + argv marker; awake-time deadlines that never count sleep; SIGINT/interrupt → SIGTERM → SIGKILL on `-pgid`; orphan sweep; adopt-or-reap at startup ([components §8](../architecture/components.md#8-process-execution)).
- **Worktrees:** bare partial mirror per repo; task worktrees, shared read-only reference checkouts and per-head-SHA review checkouts under a space-free `~/MercuryWork`; archive (bundle + patch) before any removal; disk holds ([components §9](../architecture/components.md#9-worktree-management)).
- **Control API:** Unix domain socket, 0600 in a 0700 dir, JSON lines, principal tokens (`operator`, `claude_session`, `readonly`); CLI never writes SQLite; offline read-only status ([components §5](../architecture/components.md#5-internal-control-api-and-the-mercury-cli)).
- **Protocol:** agents emit only strict output contracts with binding echoes; the coordinator wraps validated content in envelopes written in the transition transaction ([messages §1–§5](../protocols/messages.md)).

### Alignments made after reading other agents' outputs

| Source | Alignment |
|---|---|
| Agent A `overview.md` §8.1 | Interactive Claude sessions can only **request** decisions (`request.authorize/triage/reauth`); authorization rows come only from coordinator-launched Claude runs (DB trigger, I18) |
| Agent A §8.4 | DecisionRecorder as sole writer; trigger checks run + output hash; optional `record_mac` column |
| Agent A §9.3 C2/C6/C7/C8/C9/C10 | Linear cancel → `CANCELLED`; PR closed by operator → `CANCELLED`, by others → `BLOCKED`; foreign push → `BLOCKED(foreign_push)` with adopt/reset; merge mismatch → security escalation; foreign delegation → `BLOCKED(foreign_agent)`; DB restore → `BLOCKED(reauthorization_required)` |
| Agent A §6 concurrency | Codex 1, Claude 2 default |
| Agent B `claude.md` §3, §6 | Six decision types incl. Claude-authored `revision_request`; reviews in parallel per head SHA; mandatory security review; V1–V4 validation; `ClaudeVerdictCommon` fields; reference/review checkouts |
| Agent B `codex.md` | Per-task `CODEX_HOME`, thread IDs persisted, coordinator commit pipeline with diff gate and secret scan, L2 test runner in `TESTING`, `deps_install` step, failure classes, CI timeout still proceeds to Claude review |
| Agent E C-SEC-1, §7.3, SEC-303/305/306/308 | Binding echo fields in every verdict contract; `files_reviewed[]`; `dependency_changes_allowed ∈ {false,"escalate"}`; `injection_suspected` forces escalation; `request_id` (= run_id) |
| Agent E C-SEC-3 | `BLOCKED(security_escalation)` reason and the review guard require deterministic gates (diff gate, secret scan) passed before review |
| Agent E C-SEC-5 | `actor` envelope field with SEC-601 vocabulary; free text in display-only fields |

## 3 Alternatives considered

| Topic | Alternative | Why not chosen |
|---|---|---|
| States | Keep all 18 baseline states (incl. `DISCOVERED`) | Task rows without authority; see Finding 2 |
| States | `TESTING` as a sub-state of `IMPLEMENTING` | Different executor, evidence and failure route (Finding 3) |
| States | `PAUSED`, `WAITING_FOR_HOST` as states | Holds instead (Finding 1) |
| Conditions | Agent A's `BLOCKED` with auto-resume for spec change, deprioritization, new blocker (overview §9.3 C1/C3/C5) | `BLOCKED` should mean "a person must act"; auto-resolving conditions as holds avoid notification noise (the Slack-era pain). **Disagreement for Phase 4** |
| Queue | Separate `jobs` table (overview §6 `claimDueJobs`) | Two sources of truth (job vs state) can diverge; derived queue + runs leases has identical semantics |
| Control API | CLI writes SQLite directly; command files; loopback HTTP | Second writer and guard bypass; no feedback; TCP listener (components §5.1) |
| Process | Kill all agent processes on coordinator restart | Wastes up to 2 h of Codex work after a crash or upgrade restart; adoption is safe with identity checks |
| Store | `better-sqlite3` as primary | Native addon supply chain and ABI rebuilds; kept as fallback |
| Worktrees | Non-bare clone (overview §5.4 `clones/`) | A bare mirror has no working tree to get dirty; worktrees attach to it |
| Schemas | One schema family for agent output and messages | Agents would have to produce IDs/hashes they could forge; strict-mode constraints differ |
| Revision instructions | Always a Claude `revision_request` run (CL §3) | For sources that are already Claude reviews, the required changes are rendered verbatim (still Claude's words); an extra run adds cost and latency. Claude run kept for CI, tests, human comments, conflicts |

## 4 Tradeoffs

- **Strict closed schemas** give integrity but make additive change a version bump with a registry of revisions (messages §6).
- **DB triggers duplicate guards.** Extra migration complexity and slightly slower inserts, in exchange for invariants that hold even with application bugs.
- **Adoption of detached runs** adds the `runwrap` component and identity probing via `ps`; in return restarts do not waste work.
- **One mutating run per task and Codex concurrency 1** limit throughput (human review is the real bottleneck anyway).
- **Holds vs BLOCKED** keep the table small but add a second concept operators must learn (`mercury status` shows both).
- **Synchronous transactions** forbid async work inside them; some flows need a "prepare I/O, then re-validate in tx" pattern (L5).

## 5 Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-C-1 | `node:sqlite` RC behaviour or API rename breaks the store | `Store` port; `better-sqlite3` fallback; contract tests on pinned Node |
| R-C-2 | Codex `--output-schema` rejects or ignores parts of the contracts (e.g. `enum` with mixed types `[false,"escalate"]` is only in a Claude contract, but other strict-mode limits may apply) | Phase 0 self-test with the real contracts (ASM-C-07); contracts kept in the simplest keyword subset |
| R-C-3 | PID reuse or missing `lstart` precision leads to signalling a wrong process | Marker + `lstart` + pgid triple; never kill on mismatch |
| R-C-4 | Sandbox escapes via `setsid` grandchildren survive group kill | Seatbelt process restrictions (Agent E); post-kill scan; ASM-C-16 |
| R-C-5 | Trigger logic errors block legitimate transitions in production | One positive and one negative test per trigger (DBT-01); triggers are simple existence checks |
| R-C-6 | Derived-validity of reviews depends on fresh head observations | Review guard requires an observation newer than the review run end (SM §8.3); fresh `getPull` before recording |
| R-C-7 | Transition table drift between doc and code | Doc is generated from `TRANSITION_TABLE` and diffed in CI (SMT-01) |
| R-C-8 | Space in `~/Library/Application Support` breaks repo build scripts if worktrees are placed there | Worktrees/checkouts under `~/MercuryWork` (conflicts with CL §3.2 paths; Phase 4) |

## 6 Assumptions

| ID | Assumption | Verify in |
|---|---|---|
| ASM-C-01 | `node:sqlite` in the pinned Node 24 supports synchronous transactions, `timeout`, `backup()`, and the PRAGMAs used | Phase 0 / CI |
| ASM-C-02 | Node `process.hrtime` on macOS may or may not advance during system sleep; design works either way (credit cap) | Phase 0 experiment |
| ASM-C-03 | Codex workspace-write Seatbelt (network off) denies `connect()` to UNIX sockets outside writable roots | Phase 0 (Agent E test) |
| ASM-C-04 | Detached (setsid) children are not killed by launchd when `mercuryd` crashes or is restarted by `kickstart -k`, but are killed at logout | Phase 0 |
| ASM-C-05 | `ps -o lstart=,pgid=,command= -p` is available and stable on macOS for identity checks | Phase 0 |
| ASM-C-06 | Agent SDK `spawnClaudeCodeProcess` allows spawning via `runwrap` in a new process group | Phase 0 / SDK contract test |
| ASM-C-07 | Codex `--output-schema` accepts the contracts (type arrays for null, all-required objects, enums) | Phase 0 |
| ASM-C-08 | Claude `outputFormat` accepts contracts without `$schema`/`$id` and validates them as draft-07 | Phase 0 |
| ASM-C-09 | `codex exec resume <thread_id>` works across process restarts with a per-task `CODEX_HOME` (CX ASM-B-10) | Phase 0 |
| ASM-C-10 | Linked worktrees of a bare mirror work with Codex (`.git` file, project root detection) and keep `.git` metadata outside writable roots | Phase 0 |
| ASM-C-11 | macOS `sun_path` limit is 104 bytes | Known; check at startup |
| ASM-C-12 | `sandbox-exec` (or `codex sandbox macos`) is usable for the L2 test runner | Phase 0 (Agent B/E) |
| ASM-C-13 | GitHub issue events give `closed_by` for PRs; pulls API gives `merged_by`, `merge_commit_sha`; reviews give `commit_id` | Integration test |
| ASM-C-14 | Linear relation edits may not bump the blocked issue's `updatedAt`; periodic full refresh needed | Integration test |
| ASM-C-15 | A child writing to inherited file fds continues after the parent exits | Standard POSIX; test |
| ASM-C-16 | Sandbox profiles can restrict daemonization of agent grandchildren | Agent E |
| ASM-C-17 | Partial (`blob:none`) bare clones work with `git worktree add` and GitHub App token auth | Phase 0 |
| ASM-C-18 | Linear `commentCreate` with a client-supplied UUID rejects duplicates recognisably (idempotent retry) | Integration test |

## 7 Dependencies

- **Agent A:** confirm holds vs `BLOCKED` for C1/C3/C5; derived queue instead of `jobs`; bare mirror; failure-triage decision kind (kept optional, contract not defined in v1).
- **Agent B:** prompt envelopes must carry every binding field listed in messages §5; confirm verbatim rendering of Claude review `required_change` without a `revision_request` run; final Linear state mapping; branch prefix `mercury/`; rebase vs merge for conflicts; required checks list source; checkout paths (space-free).
- **Agent D:** `MERCURY_HOME`, `~/MercuryWork`, `ExitTimeOut` ≥ 30 s, backup schedule, migration backup, socket path length, downtime notice wording, Keychain locked handling.
- **Agent E:** HMAC mandatory (SEC-603 MUST) vs optional (overview §8.6): `record_mac` column exists, nullable; the `anchors` table (C-SEC-4) is not yet in the DDL; `Redacted<string>` sink typing (C-SEC-7) to be adopted in the port signatures; agent uid `_mercuryagent` (D-SEC-1) would change process spawning (sudo/launchd broker) and file modes; control socket token location vs Codex read access.
- **Agent F:** requirement IDs; adopt SMT/DBT/CT/RT test lists with pass/fail criteria.

## 8 Unresolved questions

| ID | Question | Owner |
|---|---|---|
| OD-C-01 | Automatic triage on (`triage.auto = true`) or only on operator request? | Operator |
| OD-C-02 | Revision budget defaults N/M/K/H = 3/3/3/5 acceptable? | Operator |
| OD-C-03 | Should human review *comments* without a `CHANGES_REQUESTED` review start a revision (e.g. via a `mercury:revise` label)? | Operator / B |
| OD-C-04 | `blocked_ttl` 30 days before `FAILED`, or never auto-fail? | Operator |
| OD-C-05 | Operator merges before Claude review: verification failure (current design) or allowed with a warning? | Operator / E |
| OD-C-06 | Keep `claude_failure_triage` (overview §8.2) in v1? | A / B |
| OD-C-07 | Does Agent E's separate agent uid replace or complement the per-run process-group design? | D / E |

## 9 Supporting evidence

- `reviews/02-discovery-platform.md` §5 (SQLite WAL/`fullfsync`, `node:sqlite` RC status, `detached` → setsid, `-pgid` kill), §4 (launchd process-group cleanup, sleep semantics, TCC), §1.2/§2 (merge verification recipe, ETag polling).
- `reviews/02-discovery-agent-runtimes.md` §2.2 (SDK `spawnClaudeCodeProcess`, draft-07 `outputFormat`), §3.1 (Codex JSONL events, exit codes, `--output-schema`), §3.2 (protected `.git`), Summary 9 (no whole-run timeout).
- `reviews/01-discovery-integrations.md` (Slack failure patterns motivating holds/dedup; Linear relations; branch naming with issue IDs).
- `architecture/overview.md` §5–§9, `integrations/claude.md` §3, §6, `integrations/codex.md` §3–§12, `security/threat-model.md` §7.3, C-SEC-1…7.
- Schema validation: all 25 schema files checked against their metaschemas with `jsonschema` 4.26; strict-subset lint over output contracts; fixtures for `plan`, `task.authorization` (revoke), `output.codex_plan`, `output.code_review` validate; an unknown top-level field is rejected.

## 10 Confidence level

| Recommendation | Confidence | Why |
|---|---|---|
| State list, classes, holds vs BLOCKED | High | Covers every brief scenario; disagreement with A is narrow |
| Transition table and invariants | Medium-High | Complete for designed flows; edge cases (concurrent external events) need property testing |
| DB-enforced invariants (triggers, partial indexes) | High | Standard SQLite features; testable |
| Derived queue + claim protocol | High | Single process makes it simple |
| Process adoption via `runwrap` | Medium | Depends on ASM-C-04/05/06/15 |
| UDS control API | High | Simple and local; principal separation is honestly policy-level for same-uid processes |
| Message/contract schemas | Medium-High | Validated structurally; agent acceptance of contracts (ASM-C-07/08) unverified |
| Sleep-safe timing | Medium | Works regardless of clock semantics, but needs a real-Mac experiment |
| Worktree layout and cleanup | Medium | Path choice conflicts with B; partial clone (ASM-C-17) unverified |
