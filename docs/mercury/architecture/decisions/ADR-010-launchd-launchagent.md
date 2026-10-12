# ADR-010: Run `mercuryd` as a per-user launchd LaunchAgent (provisional)

## Status
Proposed — **provisional**. Agent D owns the detail in `operations/macos-service.md` and `operations/recovery.md`. Date 2026-10-12.

## Context
- `mercuryd` must restart after crashes, start at login, and stop gracefully (brief §F).
- A LaunchAgent in `gui/<uid>` runs only while the user is logged in, has the login Keychain, and is sent SIGTERM then SIGKILL after `ExitTimeOut`. A LaunchDaemon lacks the login Keychain. Children spawned `detached` escape launchd's process-group cleanup. TCC protects `~/Documents`, `~/Desktop`, `~/Downloads` (discovery fact 10).

## Decision
1. Install `~/Library/LaunchAgents/<reverse-dns>.mercuryd.plist` with: `RunAtLoad=true`, `KeepAlive={SuccessfulExit=false}`, `ProcessType=Standard`, `ExitTimeOut=60`, `ThrottleInterval=10`, explicit `PATH`, absolute pinned `node` path, `StandardOutPath`/`StandardErrorPath` under `~/Library/Logs/Mercury/`, no secrets.
2. SIGTERM handler: stop claiming jobs; send SIGINT to agent process groups; checkpoint; SIGTERM groups after 20 s; exit 0 before 60 s. Interrupted runs are marked `interrupted` and handled by recovery on next start.
3. Startup: integrity check → orphan reaping (pid + pgid + start time from DB) → full reconcile → scheduler.
4. All MERCURY paths outside TCC-protected folders; no Full Disk Access requirement.
5. Hold `caffeinate -i -w <mercuryd pid>` (idle-sleep prevention) only while agent runs are active; never relied on for correctness.
6. Known limitation accepted: MERCURY does not run before login after a reboot, nor during sleep. The operator is told (one notification) when a gap > 8 h left tasks waiting.

## Alternatives
- LaunchDaemon: no login Keychain, separate TCC context; rejected.
- Login item app / menu-bar app: needs an app bundle; no advantage for a headless process.
- Separate macOS user for MERCURY: stronger isolation, but loses the operator's GUI session Keychain; future option (overview §8.6).
- tmux/manual start: not supervised; rejected.

## Consequences
- "Allow in the Background" toggle in System Settings can disable the agent; Phase 0 checks it and `mercury doctor` reports it.

## Related requirements
Brief §F (launchd, login-session behaviour, supervision, graceful shutdown, crash recovery, orphaned processes); NFR-REL-01, NFR-REL-02, NFR-AVL-01; AP-8.
