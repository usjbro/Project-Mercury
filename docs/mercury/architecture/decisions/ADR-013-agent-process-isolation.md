# ADR-013: Agent process isolation under a dedicated macOS uid

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-18, OD-31, OD-36)** |
| Date | 2026-10-12 |
| Owner | Agent A. Agent D owns the concrete design (`operations/macos-service.md` §3, §7, §9, §16); Agent C owns the `ProcessSupervisor` port and its `agent-ctl` adapter (`architecture/components.md` §8); Agent E owns SEC-201 and its verification (SEC-T-20) |
| Related ADRs | [ADR-004](ADR-004-claude-invocation-model.md), [ADR-005](ADR-005-codex-invocation-model.md), [ADR-008](ADR-008-agent-identities-and-merge-governance.md), [ADR-010](ADR-010-launchd-launchagent.md), [ADR-016](ADR-016-filesystem-layout.md), [ADR-020](ADR-020-detached-runs-and-adoption.md) |

## Context
- Phase 2 ran Claude, Codex, the L2 test runner and `deps_install` as the operator's uid with `HOME` set to the operator's home. Seatbelt allows broad reads. A hostile Codex run could read `~/.config/gh/hosts.yml`, `~/.ssh` or the `gh` Keychain item, encode it into a diff that no secret scanner recognises, and have the coordinator push it to a public branch. That is human impersonation, and it defeats every GitHub-side control (RE-01, RF-01, RD-01; Critical in three reviews).
- Threat-model SEC-201 makes agents under a separate uid a MUST, but no runtime design implemented it. Under a second uid several Phase 2 mechanisms break: the operator uid cannot `kill(2)` agent-uid processes; it may not see their argv; files created by the agent may not be writable by the coordinator; the agent has no Keychain; toolchains in the operator's home become unreachable; `sudo` drops env and file descriptors unless configured (RA-02, RD-01, RD-26).
- Two designs were proposed in Phase 3:
  - **U2** (E): run the whole MERCURY stack in a dedicated logged-in user account;
  - **agent uid** (A, B, C, D, F): keep the coordinator as an operator-uid LaunchAgent and run agents as a hidden role account through root-owned wrappers (D's review §4.5).
- The reconciliation (RD-1) adopted the agent-uid design.

## Decision
1. **Every process that executes model-directed or repository-derived code runs as `_mercuryagent`** (hidden role account, primary group `mercury`, no password, no login, no Keychain). This covers Codex planning and implementation runs, the L2 `verify` run, `deps_install` and Claude decision runs. The coordinator stays an operator-uid LaunchAgent ([ADR-010](ADR-010-launchd-launchagent.md)).
2. **Two root-owned, fixed-grammar wrappers** in a root-owned directory, invoked through a restricted sudoers drop-in that grants the operator uid lateral access to `_mercuryagent:mercury` for exactly these two binaries and nothing else:
   - **`agent-exec`** starts a run. It validates the run directory's realpath and the argv against a per-kind grammar (`codex_plan`, `codex_implement`, `codex_revise`, `verify`, `deps_install`, `claude`), builds the environment from an allowlist, reads the model key from fd 3, sets rlimits and a new session, writes `proc.json`, waits for the child, enforces the hard deadline and the supervisor lease ([ADR-020](ADR-020-detached-runs-and-adoption.md)) and writes `exit.json`. It replaces C's `runwrap`.
   - **`agent-ctl`** performs control operations as the agent uid: `signal`, `ps` (list marked agent processes), `stats` (group CPU and RSS), `purge` (realpath-limited removal), `fix-acl`.
   The exact grammar, sudoers text, binary pins and install commands are in `macos-service.md`.
3. **Secrets reach agents only on fd 3**, once per run. They never appear in env, argv or files. Agent `HOME` is `/Users/_mercuryagent` and holds caches only; `mercury doctor` scans it for credential files.
4. **Filesystem access** follows [ADR-016](ADR-016-filesystem-layout.md): the agent can reach only `WORK_ROOT` paths granted to the `mercury` group, writes only to its task worktree, its `CODEX_HOME/sessions` and its run scratch directories, and cannot open `MERCURY_HOME`, the operator's home or any Keychain. The operator's home is 0700 (verified by `doctor`).
5. **Claude runs** use the Agent SDK's custom spawner through `sudo -n -u _mercuryagent agent-exec --kind claude`, keeping the SDK pipes. If the Phase 0 spawn test fails, the fallback is B's ALT-B-1 (Messages API with coordinator-implemented, realpath-confined file tools), which removes the Claude subprocess.
6. **Seatbelt is the second layer.** Codex's sandbox and D's fail-closed L2 profile still apply inside the agent uid. Codex's writable roots exclude the run's `ctl/` directory, so Codex commands cannot forge `exit.json`.
7. **Toolchains** are installed per repository by `mercury toolchain sync` into `WORK_ROOT/toolchains` (coordinator-owned, agent read and execute only).
8. **Gates:**
   - Same-uid execution with Seatbelt deny profiles is allowed **only with fakes and the sandbox repository** (milestones M1–M4).
   - **No workspace-write Codex, `verify` or `deps_install` run against a non-sandbox repository until SEC-T-20 (credential canaries) passes on the real Mac**, together with D's Phase 0 checks P0-26 to P0-32.
   - Any `doctor` failure of the wrappers, sudoers or ACLs sets the `config_fatal` hold for agent dispatch.
9. **Failure mode is closed.** If an agent strips ACLs or makes its files unreadable, the coordinator's commit read fails, the run is classified `policy_violation`, and the task goes to `BLOCKED(security_policy_violation)`. Nothing unreadable can be pushed.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| **U2: whole MERCURY stack in a dedicated logged-in user** (E) | Protects the human's credentials, but leaves MERCURY's own App key, Linear token and control token readable by agents. A hostile agent could then forge the required `MERCURY / claude-review` check and post as MERCURY. It also needs a second always-logged-in GUI session and a manual login after each reboot. Kept as optional extra hardening for the coordinator (OD-36) |
| Same uid with Seatbelt and Claude deny rules only | Seatbelt read rules are hard to make complete; encoded exfiltration through the diff is undetectable. Allowed only on the sandbox repository before the gate |
| Root-owned broker LaunchDaemon running as the agent uid, with a Unix socket | True `waitpid` and logout survival, but needs an IPC protocol, stdio relaying for Claude and its own recovery; a long-lived agent-uid daemon is a target. Kept as a v2 option |
| Privileged helper via `SMAppService` / XPC | Requires an app bundle and code signing infrastructure for a headless tool |
| Containers or VMs (Docker, Virtualization.framework) | Heavy on a laptop; macOS toolchains for the target repositories would need re-provisioning; adds a service. Disproportionate for v1 |
| `sudo` to root for control operations | Over-privileged; the grant here is lateral to the agent uid only |

## Consequences
- **Positive:** the operator's credentials and MERCURY's own credentials are both out of reach of agent-executed code; this restores E's human-approval proof (`threat-model.md` §5.2).
- **Positive:** the coordinator can still supervise, signal, sample and clean up agent processes, and adoption keeps working through files.
- **Negative:** a one-time root-level setup by the operator in Phase 0 (user, group, wrappers, sudoers, `WORK_ROOT`, home permissions), with an uninstall path. MERCURY's design phase performs none of it.
- **Negative:** per-repo toolchains must be provisioned for the agent uid.
- **Residual risk:** sudo or kernel misconfiguration; agent argv visible across uids through `ps` (no secrets are on argv); a model key in a Codex process environment may be readable by Codex's child commands (mitigated by dedicated, spend-capped keys and `shell_environment_policy`).

## Related requirements
SEC-201, SEC-202, SEC-203, SEC-405, SEC-502, SEC-704; CON-007, CON-008, CON-010; FR-044, FR-281; NFR-092. Test gate SEC-T-20.

## Related findings
RF-01, RD-01, RE-01 (Critical), RA-02, RA-24, RB-08, RC-09, RD-02, RD-25, RD-26, RD-28, RE-29.

## Operator decisions
- **OD-18** agents under a separate macOS uid (default: adopt; this ADR assumes it).
- **OD-31** Keychain `-T /usr/bin/security` ACL (acceptable only together with OD-18).
- **OD-36** optional dedicated account for the coordinator (default: not in v1).
