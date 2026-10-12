# ADR-003: Coordinator-mediated agent communication; no direct agent-to-agent channel

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12.

## Context
- Today Claude and Codex coordinate through Slack threads, gate files and plan files in worktrees. The operator documented lost replies, a 14 h unanswered question, a 3.5 h "no plan received" gap, identity confusion and manual relays (`01-discovery-integrations.md`, Slack failure patterns 1–8).
- The brief asks to evaluate JSON messages, local persistent queues, SQLite event processing, CLI execution, MCP, filesystem artifacts, IPC and HTTP (§B).
- Runtime facts: `codex mcp-server` is gone in 0.162.1 and `app-server` is experimental; `claude mcp serve` exposes tools, not judgement; both agents have stable headless one-shot modes with schema-constrained output (`02-discovery-agent-runtimes.md` §1, §4).

## Decision
1. **Hub-and-spoke.** `mercuryd` is the only party that talks to each agent. Claude and Codex never call each other, never share a session, and never see each other's credentials.
2. **Transport = child-process invocation + files + SQLite.** For each run the coordinator writes an input bundle (`runs/<run_id>/prompt.md`, `input.json`), spawns the agent with a JSON Schema for its final output, parses the event stream, validates the final output, and stores it as a content-addressed artifact.
3. **Messages** are SQLite rows using the baseline envelope (`schema`, `message_id`, `correlation_id`, `causation_id`, `dedup_key`, `occurred_at`, `issue`, `repo`, `run_id`) and are written in the same transaction as the transition that produced them (transactional outbox). Agent C owns the schemas.
4. **Cross-agent content** (Claude's findings to Codex; Codex's plan to Claude) is passed only as coordinator-rendered, schema-validated data inside the next input bundle, delimited and labelled as untrusted data.
5. **MCP is used only inside Claude decision runs** as an in-process, read-only `mercury` tool server (`get_task`, `get_issue_snapshot`, `get_plan`, `get_diff_summary`, `get_test_report`). It has no write tools.
6. Files written by Codex in a worktree (for example a plan file) have no meaning until the coordinator hashes and registers them as artifacts.

## Alternatives
| Alternative | Reason rejected |
|---|---|
| Direct MCP between agents | Codex MCP server removed; would bypass the dispatch guard; couples agent versions |
| Shared files as the signal (gate files, plan files) | Today's failure mode; no acknowledgement, no atomicity, writable by agents |
| Slack or another chat bus | Recreates identity confusion and lost messages; adds a third-party channel |
| Local pub/sub (NATS, Redis) | Adds a service without adding authority control; still needs durable state elsewhere |
| Local HTTP endpoints per agent | Agents are batch CLIs; adds listeners |
| Linear comments as the channel | Writable by human identity and integrations; cannot carry authority; rate-limited |

## Consequences
- Positive: one authoritative state per task; every hand-off is acknowledged by a DB commit; complete, hashed audit; agents are replaceable behind adapters; no agent needs network credentials beyond its model API.
- Negative: no free-form back-and-forth between agents; a clarification must be modelled as a typed revision request or escalation. Each run rebuilds context (token cost).
- Codex cannot ask Claude a question mid-run. If it needs clarification it ends the run with a `needs_clarification` output, which becomes a Claude decision.

## Related requirements
Brief §B (all message types, correlation and dedup IDs), §I; hard constraint "Codex cannot execute unapproved work through the coordinator"; AP-1, AP-6, AP-7.
