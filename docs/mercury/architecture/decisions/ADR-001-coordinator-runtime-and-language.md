# ADR-001: Coordinator runtime and language — Node.js 24 LTS + TypeScript

| | |
|---|---|
| Status | **Accepted** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A |
| Related ADRs | [ADR-002](ADR-002-sqlite-store-and-queue.md), [ADR-010](ADR-010-launchd-launchagent.md), [ADR-013](ADR-013-agent-process-isolation.md) |

## Context
- MERCURY needs one continuously running local process (`mercuryd`) on the operator's Mac. It supervises Claude and Codex runs, polls GitHub and Linear, and keeps a durable state machine (brief §A, §F).
- The strongest programmatic control surface for Claude is the **Claude Agent SDK**, which exists only for TypeScript and Python. It provides `canUseTool`, in-process hooks, `outputFormat` (JSON Schema), `interrupt()`, `maxTurns`, `maxBudgetUsd` and a custom process spawner (`02-discovery-agent-runtimes.md` §2.2). The custom spawner is what lets a Claude run execute as the agent uid ([ADR-013](ADR-013-agent-process-isolation.md)).
- Codex is an external binary driven through `codex exec --json`. Its TS SDK `.d.ts` is a usable, version-pinned description of the JSONL event contract (§3.4).
- Node 24 is Active LTS until 2026-10-20 and Maintenance LTS until 2028-04-30. Node 26 becomes LTS on 2026-10-28. `node:sqlite` is Release Candidate in Node 24 (`02-discovery-platform.md` §5.2).
- There is one operator, and MERCURY will itself be implemented largely by Claude and Codex.

## Decision
1. Implement `mercuryd` and the `mercury` CLI in **TypeScript** (strict mode) on **Node.js 24 LTS**, pinned to an exact patch version. Move to Node 26 LTS once it is LTS and the contract suite passes on it.
2. **One OS process, one event loop, one SQLite write connection.** Agent work and git run as child processes. Long blocking maintenance work (online backup, `integrity_check`) runs in a worker thread with its own read connection, so it cannot stall the tick (RD-11).
3. **Runtime dependencies are minimal**, exactly as fixed in `architecture/components.md` §1: `@anthropic-ai/claude-agent-sdk` (exact pin), `ajv`, `smol-toml`. GitHub and Linear are reached through the built-in `fetch` with thin typed wrappers (no Octokit). ULID, RFC 8785 canonical JSON and SHA-256 are implemented in-repo or come from `node:crypto`. Install with `npm ci --ignore-scripts`.
4. SQLite is accessed through `node:sqlite` **behind the `Store` port**, with `better-sqlite3` as the drop-in fallback ([ADR-002](ADR-002-sqlite-store-and-queue.md)).
5. Install layout, the pinned `node` path and the upgrade procedure are owned by `operations/macos-service.md` (§13, and the paths in §7.1). This ADR does not restate them.

## Alternatives considered
Scored in `architecture/overview.md` §11 (weighted, max 5.00):

| Option | Score | Why rejected |
|---|---|---|
| Node.js + TypeScript | **4.40** | Chosen |
| Python + SQLite | 4.05 | Viable fallback. Managing the Python runtime and venv under launchd is more fragile on macOS, and the typed GitHub and Linear clients are thinner |
| Go single binary | 3.80 | No official Claude Agent SDK, so `canUseTool`, in-process hooks and the custom spawner are lost |
| Temporal + TS worker | 3.50 | A second always-on service on a laptop; determinism rules; no benefit while the Mac sleeps |
| Redis/BullMQ | 3.40 | Two stores break the single-transaction "state plus effect" commit |
| GitHub-Actions-hosted | 2.90 | Cannot reach the Mac; secrets would live in a public repository's Actions |
| Linear as state store | 2.85 | No transactions or leases; authority would be forgeable |
| Claude-session loop, no daemon | 2.75 | Stops when the session stops, which is the Slack-era failure |

## Consequences
- **Positive:** one language for coordinator, CLI, tests and schema-derived types; typed SDK events; JSON Schemas are shared between the agents' wire copies and the coordinator's validators.
- **Positive:** a small dependency tree (three runtime packages) keeps the npm supply-chain surface small.
- **Negative:** npm supply-chain exposure remains for the three packages and the dev toolchain. Mitigated by exact pins, a lockfile, `--ignore-scripts` and dependency review in MERCURY's own CI.
- **Negative:** Node major upgrades require re-testing the `node:sqlite` API, which is still changing.
- **Follow-up:** Phase 0 records the Mac's Node version; the agent CLI contract suite (NFR-093) gates every upgrade.

## Related requirements
NFR-080 (idle footprint), NFR-090 (version pinning), NFR-091 (driver-independent store), NFR-095 (startup self-test time); CON-002; brief §A, §F, §J. IDs as registered in `planning/traceability.md`.

## Related findings
RA-34 (dependency list drift, fixed by item 3).

## Operator decisions
None.

## Revision history
- Phase 4: dependency set aligned with `components.md` §1 (RA-34); worker-thread exception for backup and integrity checks (RD-11); install details delegated to `macos-service.md`.
