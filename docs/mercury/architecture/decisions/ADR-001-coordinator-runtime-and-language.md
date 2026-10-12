# ADR-001: Coordinator runtime and language — Node.js 24 LTS + TypeScript

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12.

## Context
- MERCURY needs one continuously running local process (`mercuryd`) on the operator's Mac that supervises Claude and Codex child processes, polls GitHub and Linear, and keeps a durable state machine (brief §A, §F).
- The strongest programmatic control surface for Claude is the **Claude Agent SDK**, which is TypeScript and Python only. It gives `canUseTool`, in-process hooks, in-process MCP tools, `outputFormat` (JSON Schema), `interrupt()`, `maxTurns` and `maxBudgetUsd` (`02-discovery-agent-runtimes.md` §2.2).
- The Codex TS SDK is a thin wrapper over `codex exec --json`, but its `.d.ts` is a ready-made, version-pinned event contract (§3.4).
- Node 24 is Active LTS until 2026-10-20, then Maintenance until 2028-04-30. Node 26 becomes LTS on 2026-10-28. `node:sqlite` is Release Candidate (1.2) in Node 24 (`02-discovery-platform.md` §5.2).
- The operator is a single person. MERCURY will itself be implemented largely by Claude and Codex.

## Decision
1. Implement `mercuryd` and the `mercury` CLI in **TypeScript** (strict mode) on **Node.js 24 LTS**, pinned to an exact patch version, with a planned move to Node 26 LTS after it reaches LTS and passes the test suite.
2. One OS process, one event loop. Agent work happens in child processes. No worker threads in the MVP.
3. Dependencies kept minimal and pinned with a lockfile: `@anthropic-ai/claude-agent-sdk` (exact), a GitHub REST client (Octokit core + `@octokit/auth-app`), a minimal GraphQL client for Linear, `zod` or `ajv` for schema validation, a ULID library. Install with `npm ci`; disable install scripts where the package allows it.
4. SQLite access through `node:sqlite` **behind a repository interface**, with `better-sqlite3` as a drop-in fallback ([ADR-002](ADR-002-sqlite-store-and-queue.md)).
5. Distribution: a versioned directory under `~/Library/Application Support/Mercury/app/<version>/` containing the built JS and `node_modules`, run by a pinned `node` binary path referenced in the LaunchAgent plist ([ADR-010](ADR-010-launchd-launchagent.md)).

## Alternatives
Scored in `architecture/overview.md` §11 (weighted, max 5.00):

| Option | Score | Why not chosen |
|---|---|---|
| Node.js + TypeScript | **4.40** | Chosen |
| Python + SQLite | 4.05 | Viable fallback. Python runtime and venv management under launchd is more fragile on macOS; GitHub/Linear typed clients are thinner |
| Go single binary | 3.80 | No official Claude Agent SDK; would lose `canUseTool` and in-process hooks |
| Temporal + TS worker | 3.50 | Second always-on service on a laptop; determinism rules; no benefit while the Mac sleeps |
| Redis/BullMQ | 3.40 | Two stores break single-transaction state + effect |
| GitHub-Actions-hosted | 2.90 | Cannot reach the Mac; secrets in a public repo's Actions |
| Linear as state store | 2.85 | No transactions or leases; forgeable authority |
| Claude-session loop, no daemon | 2.75 | Stops when the session stops — the Slack-era failure |

## Consequences
- Positive: one language for coordinator, CLI, tests and schema types; typed SDK events; easy JSON Schema reuse between agents and coordinator.
- Negative: npm supply-chain exposure (mitigated by pinning, lockfile, `--ignore-scripts` where possible, Dependabot on the MERCURY repo, and a small dependency set). Node major upgrades require re-testing `node:sqlite` API changes (class rename `DatabaseSync` → `Database`).
- Follow-ups: Phase 0 must record the Mac's Node version (ASM-A-10 area); Agent D defines the install and upgrade procedure.

## Related requirements
Brief §A, §F, §J; NFR-RES-01, NFR-MNT-01; AP-11, AP-12 (`overview.md` §4).
