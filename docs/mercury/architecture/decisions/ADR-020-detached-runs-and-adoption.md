# ADR-020: Detached agent runs, adoption after restart, and lost runs

| | |
|---|---|
| Status | **Accepted** |
| Date | 2026-10-12 |
| Owner | Agent A. Agent C owns the run model, adoption logic, reset policy and the `ProcessSupervisor` port (`architecture/components.md` §8–§9; `architecture/state-machine.md` §10); Agent D owns `agent-exec`, the supervisor lease, SIGTERM handling, durability settings and recovery procedures (`operations/macos-service.md` §3, §12; `operations/recovery.md`) |
| Related ADRs | [ADR-004](ADR-004-claude-invocation-model.md), [ADR-005](ADR-005-codex-invocation-model.md), [ADR-006](ADR-006-coordinator-owns-git-and-pr.md), [ADR-010](ADR-010-launchd-launchagent.md), [ADR-011](ADR-011-authorization-records-and-verification.md), [ADR-013](ADR-013-agent-process-isolation.md) |

## Context
- A Codex implementation run can take tens of minutes. Losing it on every coordinator crash, upgrade or logout wastes work and money.
- Claude SDK runs talk over pipes to the coordinator; when the coordinator dies, the pipes die.
- Phase 3 found:
  - three SIGTERM policies (RD-10);
  - runs kept alive while `mercuryd` is absent are unsupervised: no deadline, no stall kill (RD-10, RE-07);
  - recovery adopted results before re-validating authorization (RE-07);
  - a reboot was indistinguishable from a crash (RD-12);
  - git objects and `exit.json` were not flushed before the DB recorded them (RD-05);
  - run status vocabularies differed (RA-31).
- C and D already agreed on adopt-Codex, re-run-Claude (known disagreement 10); this ADR records it with the reconciliation's additions (RD-11).

## Decision
1. **Codex and `verify` runs are detached** under `agent-exec` ([ADR-013](ADR-013-agent-process-isolation.md)) with file-based stdio, `proc.json` and `exit.json`. After a coordinator restart they are **adopted** when the identity triple matches: `run_id` marker, process start time, and boot session.
2. **Claude runs are not adopted.** They are killed and re-run with the same `input_digest`, consuming no attempt. A Claude run whose validated final output was already persisted is finalized idempotently.
3. **Authority is re-checked before an adopted output is acted on** ([ADR-011](ADR-011-authorization-records-and-verification.md) item 6).
4. **`agent-exec` supervises in the coordinator's absence:**
   - it enforces the hard deadline in credited awake time;
   - it holds a **supervisor lease**: if the coordinator's liveness file (`run/coordinator.alive`, touched by the coordinator on every tick) is stale beyond the lease threshold of credited time, it sends SIGINT, then SIGTERM, then SIGKILL to the group and writes `exit.json{reason: supervisor_lost}`.
   Thresholds are in D's parameter table. Because `agent-exec` runs as the agent uid, the liveness file must live under `WORK_ROOT` (coordinator-writable, group-readable), not in `MERCURY_HOME`; its exact path is in `macos-service.md` §7.1.
5. **Run outcome `lost_by_host`:** the boot session changed or the supervisor was lost. It consumes no attempt. It has a separate per-step cap; exceeding it raises an ops alert, not `BLOCKED`.
6. **SIGTERM** (logout, shutdown, upgrade): stop dispatch; interrupt non-adoptable runs; keep adoptable runs; checkpoint; exit within `ExitTimeOut` ([ADR-010](ADR-010-launchd-launchagent.md)).
7. **Adopted runs are never kept through safe mode or a security halt**: those stop all agent groups through `agent-ctl`.
8. **Worktree reset policy** (single definition in `components.md` §9): archive uncommitted changes as a patch artifact → `reset --hard` to `tasks.last_commit_sha` (or `base_sha`) → `clean -ffd`, adding `-x` only when `deps_install` is re-queued. Checkpoint commits are not used.
9. **Durability ordering:**
   - mirror `core.fsync=committed,reference`;
   - git commit → fsync → DB transaction recording the SHA;
   - `exit.json` and `proc.json` written with fsync, rename and directory fsync;
   - recovery verifies the recorded commit and branch ref with `git cat-file -e`; if either is missing the run is `lost_by_host` and the step replays from the last durable commit.
10. **Run status vocabulary** is C's (`components.md` §6.3). "Interrupted" and "adopted" are not statuses: an interrupted run maps to `lost` with a failure class, and adoption is a flag.
11. **Event-loop safety:** backups and `integrity_check` run in a worker thread with their own read connection; lease rows are persisted at the interval in D's parameter table ([ADR-001](ADR-001-coordinator-runtime-and-language.md)).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Interrupt every run on SIGTERM or crash (A's and D's Phase 2 default) | Throws away long Codex runs on every upgrade or logout |
| Adopt Claude runs too | The SDK pipes do not survive; a relay would add a component for runs that are cheap to repeat |
| Keep runs with no supervision while the coordinator is away | No deadline, no stall detection, no kill on halt (RE-07) |
| Count host loss as a failed attempt | A reboot or power loss would exhaust retry budgets and escalate falsely |
| Checkpoint commits during implementation | Pollute history and complicate SHA binding; the patch archive covers recovery |
| Trust the DB's recorded SHA without verifying git | After a power loss the object or ref may not exist (RD-05) |

## Consequences
- **Positive:** coordinator restarts and upgrades lose no Codex work; host loss does not consume budgets; adopted results never bypass authority checks.
- **Positive:** "0 lost commits" becomes provable across SQLite and git.
- **Negative:** `agent-exec` carries supervision logic that must be tested separately (rlimits, lease, deadline).
- **Negative:** agent-uid processes may survive logout until the lease expires (Phase 0 check P0-31).

## Related requirements
FR-044, FR-045, FR-280, FR-281, FR-282; NFR-001, NFR-006, NFR-020, NFR-024, NFR-026, NFR-050; CON-009; SEC-704, SEC-902.

## Related findings
RD-04, RD-05, RD-10, RD-11, RD-12, RD-17, RA-31, RE-07; known disagreement 10.

## Operator decisions
None.
