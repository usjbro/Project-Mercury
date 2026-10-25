# ADR-003: Coordinator-mediated agent communication; no direct agent-to-agent channel

| | |
|---|---|
| Status | **Accepted** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent C owns message and agent-output schemas (`protocols/messages.md`, `protocols/schemas/`) |
| Related ADRs | [ADR-004](ADR-004-claude-invocation-model.md), [ADR-005](ADR-005-codex-invocation-model.md), [ADR-017](ADR-017-claude-review-snapshot.md) |

## Context
- Today Claude and Codex coordinate through Slack threads, gate files and plan files in worktrees. The operator documented lost replies, a 14 h unanswered question, a 3.5 h "no plan received" gap, identity confusion and manual relays (`01-discovery-integrations.md`, Slack failure patterns 1–8).
- The brief asks for an evaluation of JSON messages, local persistent queues, SQLite event processing, CLI execution, MCP, filesystem artifacts, IPC and HTTP (§B).
- Runtime facts: `codex mcp-server` is gone in 0.162.1 and `app-server` is experimental; `claude mcp serve` exposes tools, not judgement; both agents have stable headless one-shot modes with schema-constrained output (`02-discovery-agent-runtimes.md` §1, §4).
- Phase 3 found that this ADR adopted an in-process read-only MCP server for Claude while `integrations/claude.md` §2.1 forbids MCP in v1 (RA-12), and that the source of the words in a Codex revision prompt was undecided (RD-8).

## Decision
1. **Hub-and-spoke.** `mercuryd` is the only party that talks to each agent. Claude and Codex never call each other, never share a session and never see each other's credentials.
2. **Transport = child-process invocation + files + SQLite.** For each run the coordinator writes an input bundle into the run directory under `WORK_ROOT/runs/<run_id>/` ([ADR-016](ADR-016-filesystem-layout.md)), spawns the agent as the agent uid ([ADR-013](ADR-013-agent-process-isolation.md)) with a JSON Schema for its final output, parses the event stream, validates the final output against the **canonical** schema, and stores it as a content-addressed artifact. Agents receive a CI-generated **wire copy** of the schema restricted to the provider's strict-mode subset (RD-15).
3. **Messages** are SQLite rows using the baseline envelope, written in the same transaction as the transition that produced them (transactional outbox). The catalogue and schemas are defined only in `protocols/`.
4. **No MCP in v1.** Claude reads its bundle and repository snapshots as files with Read, Grep and Glob inside realpath-confined roots (`integrations/claude.md` §2–§3). There is one confinement mechanism, not two. An MCP lookup surface may be reconsidered by a later ADR after Phase 0.
5. **Cross-agent content** reaches the other agent only as coordinator-rendered, schema-validated data inside the next input bundle, delimited and labelled as untrusted.
6. **Revision requests (RD-8):**
   - When the source is a validated Claude review bound to the current plan hash or head SHA, its `required_change` items are rendered **verbatim** into the Codex prompt through a fixed, hashed template. The words are Claude's; the coordinator chooses none.
   - Every other source (CI failures, local test failures, merge conflicts, human `CHANGES_REQUESTED` reviews, diff-gate violations, conflicting or `needs_plan_change` reviews) requires a Claude `revision_request` decision run first. CI logs are untrusted and never go to Codex without Claude mediation.
   - `mercury.revision.request.v1` carries `producer.kind` and provenance (`protocols/messages.md`).
7. Files written by Codex in a worktree (for example a plan file) have no meaning until the coordinator hashes and registers them as artifacts.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Direct MCP between agents | The Codex MCP server was removed; it would bypass the dispatch guard and couple agent versions |
| Read-only in-process MCP server for Claude (Phase 2 text) | A second confinement mechanism next to the realpath-confined file tools, with no capability the bundle files lack. Rejected for v1 (RA-12) |
| Shared files as the signal (gate files, plan files) | Today's failure mode: no acknowledgement, no atomicity, writable by agents |
| Slack or another chat bus | Recreates identity confusion and lost messages; adds a third-party channel |
| Local pub/sub (NATS, Redis) | Adds a service without adding authority control; still needs durable state elsewhere |
| Local HTTP endpoints per agent | Agents are batch CLIs; adds listeners |
| Linear comments as the channel | Writable by the human identity and integrations; cannot carry authority; rate-limited |
| A Claude `revision_request` run for every revision (B's Phase 2 position) | An extra run whose output would restate a review Claude already produced. The verbatim path keeps Claude's words without it |
| Coordinator-composed revision prompts | The coordinator would be choosing instructions, which breaks the decide/execute boundary |

## Consequences
- **Positive:** one authoritative state per task; every hand-off is acknowledged by a DB commit; a complete, hashed audit; agents are replaceable behind adapters; agents hold no credentials beyond a per-run model key.
- **Negative:** no free-form back-and-forth between agents. A clarification is a typed revision request or an escalation. Each run rebuilds its context (token cost).
- **Negative:** Codex cannot ask Claude a question mid-run. If it needs clarification it ends the run with a `needs_plan_change` or `blocked` status, which routes through a Claude `revision_request` run (`state-machine.md` T17, T19).

## Related requirements
FR-060, FR-061, FR-062, FR-063, FR-064, FR-103, FR-163; CON-003, CON-005, CON-006; SEC-204 (no MCP), SEC-313 (untrusted external text). IDs per `planning/traceability.md` and `security/threat-model.md`.

## Related findings
RA-12 (MCP adopted and forbidden), RA-37 (stale schema IDs in the overview), RB-22 and known disagreement 7 (revision request source).

## Operator decisions
None.

## Revision history
- Phase 4: MCP removed for v1; run directory moved to `WORK_ROOT`; wire-copy schemas; RD-8 hybrid revision-request rule.
