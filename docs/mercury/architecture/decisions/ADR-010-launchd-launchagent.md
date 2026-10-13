# ADR-010: Run the coordinator (`mercuryd`) as a per-user launchd LaunchAgent

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-14, OD-36)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2 as provisional) |
| Owner | Agent A. Agent D owns the plist, values and procedures (`operations/macos-service.md` §4–§6, §12, parameter table; `operations/recovery.md`) |
| Scope | **The coordinator only.** Agent processes run under a separate uid per [ADR-013](ADR-013-agent-process-isolation.md) |
| Related ADRs | [ADR-013](ADR-013-agent-process-isolation.md), [ADR-016](ADR-016-filesystem-layout.md), [ADR-020](ADR-020-detached-runs-and-adoption.md) |

## Context
- `mercuryd` must restart after crashes, start at login and stop gracefully (brief §F).
- A LaunchAgent in `gui/<uid>` runs only while the user is logged in, has the unlocked login Keychain, and receives SIGTERM then SIGKILL after `ExitTimeOut`. A LaunchDaemon has no login Keychain. TCC protects `~/Documents`, `~/Desktop` and `~/Downloads` (discovery fact 10).
- Phase 3 found that this ADR's concrete values (`ExitTimeOut`, `ThrottleInterval`, label, downtime notice) differed from D's (RA-22, RD-21), that its SIGTERM policy conflicted with C's adoption design (RD-10), and that it listed a separate macOS user only as a future option while E required agent separation (RD-28, RA-24).

## Decision
1. **`mercuryd` is a LaunchAgent in the operator's GUI session**, running as the operator uid, so it can read MERCURY's credentials from the login Keychain. The plist (label, `RunAtLoad`, `KeepAlive={SuccessfulExit=false}`, `ProcessType`, `ExitTimeOut`, `ThrottleInterval`, paths) is defined only in `macos-service.md` §5; numeric values are in D's parameter table.
2. **Agents are not children in the launchd sense of this job's trust.** Every model-directed or repository-derived process runs as `_mercuryagent` through `agent-exec` ([ADR-013](ADR-013-agent-process-isolation.md)). No second launchd job is introduced for agents.
3. **Startup and exit contract (RD-11):**
   - `flock` on a lock file in `MERCURY_HOME/run/` is the single-instance guard. If the lock is held, the new instance exits 0 (so `KeepAlive` does not loop).
   - Startup order: lock → DB integrity check → audit chain verification ([ADR-018](ADR-018-audit-integrity.md)) → run adoption and orphan sweep ([ADR-020](ADR-020-detached-runs-and-adoption.md)) → full reconcile → dispatch.
   - DB corruption or a failed chain verification → stay alive in **safe mode** (no dispatch, status and CLI available), one notification.
   - Schema newer than the binary → write `run/fatal.json`, exit 0.
4. **SIGTERM (logout, shutdown, `bootout`, upgrade):** stop dispatch; interrupt non-adoptable runs (Claude); keep adoptable runs (Codex, `verify`) under their own `agent-exec` supervision; checkpoint; exit within the internal shutdown budget and before `ExitTimeOut` ([ADR-020](ADR-020-detached-runs-and-adoption.md)).
5. All MERCURY paths are outside TCC-protected folders ([ADR-016](ADR-016-filesystem-layout.md)); no Full Disk Access is required.
6. A `caffeinate -i` assertion is held only while agent runs are active (OD-14); correctness never depends on it.
7. **Known limitation accepted:** MERCURY does not run before login after a reboot, or during sleep. Downtime with pending work is reported once on resume, and an external watchdog alerts if the heartbeat stops ([ADR-019](ADR-019-notifications-and-operator-presence.md); thresholds in D's parameter table).
8. **A dedicated macOS account for the coordinator ("U2") is not used in v1.** It is recorded as optional future hardening (OD-36): it would hide MERCURY's state from the operator's own interactive agents, but needs a second logged-in session and a second login Keychain.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| LaunchDaemon | No login Keychain; secrets would need the System keychain (root) or files |
| Coordinator in a dedicated macOS user (U2, E's Phase 3 proposal) | Protects the human's credentials but, without agent separation, leaves MERCURY's own App key and tokens readable by agents. With [ADR-013](ADR-013-agent-process-isolation.md) in place it adds only a further layer, at the cost of a second always-logged-in session (Fast User Switching) and a manual login after each reboot. Kept as OD-36 |
| Login-item or menu-bar app | Needs an app bundle; no advantage for a headless process |
| tmux or manual start | Not supervised |
| Interrupt all runs on SIGTERM (Phase 2 text) | Throws away Codex work on every upgrade or logout; adoption makes it unnecessary (RD-10) |

## Consequences
- **Positive:** the login Keychain, standard launchd supervision, and a simple install.
- **Negative:** the "Allow in the Background" setting can disable the agent; `mercury doctor` and the watchdog report it (OPS-012).
- **Negative:** the coordinator shares a uid with the operator's other processes; the presence tier ([ADR-019](ADR-019-notifications-and-operator-presence.md)) and policy OD-35 cover the resulting risk from the operator's interactive agents.

## Related requirements
FR-048, FR-280, FR-281, FR-282; NFR-002, NFR-004, NFR-007, NFR-021, NFR-024, NFR-025, NFR-027, NFR-070, NFR-092; OPS-012; CON-009.

## Related findings
RA-22, RA-24, RD-10, RD-21, RD-28, RE-01 (coordinator placement part), RD-17.

## Operator decisions
- **OD-14** power policy (default: `caffeinate -i` only while runs are active).
- **OD-36** dedicated macOS account for the coordinator (default: not in v1; **must be decided before unattended operation / gate G-S5**, reconciliation Addendum A).

## Revision history
- Phase 4: values removed and referenced; scope limited to the coordinator; startup and exit contract per RD-11; SIGTERM keeps adoptable runs; U2 recorded as OD-36.
