# ADR-004: Claude invoked by the coordinator as a headless decision service

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12. Agent B owns the integration detail (`integrations/claude.md`).

## Context
- The brief makes Claude "the primary orchestrator" and the decision maker, and the coordinator "a continuously running local coordinator" that "executes and tracks". Both must hold together.
- Two models are possible:
  - **(a) Coordinator invokes Claude** at decision points as a short-lived, isolated, schema-constrained run.
  - **(b) A long-running Claude session drives the coordinator** through a CLI or MCP tool surface (`mercury authorize`, `mercury dispatch`, …).
- Facts:
  - A Claude session does not survive sleep, logout or restart, and its context compacts. The Slack workflow progressed only "while a chat session is open" (discovery fact 12).
  - Headless Claude runs repository hooks and `.mcp.json` unless isolated (`settingSources: []` / `--bare`, `--strict-mcp-config`, `disableAllHooks`) (discovery fact 6).
  - Under (b), Claude needs write tools that cause execution, in the same session that reads untrusted repository and Linear text. A prompt injection could then authorize or dispatch.

## Decision
1. Adopt **(a)**. Claude holds the **authority**; `mercuryd` holds the **loop**. Each decision is a fresh Claude run started by the Decision Gateway, through the Agent SDK `query()` with the isolated profile (`settingSources: []`, explicit read-only `tools`, `permissionMode` explicit and deny-by-default `canUseTool`, `outputFormat` JSON Schema, `maxTurns`, `maxBudgetUsd`, minimal `env`, pinned binary). CLI fallback: `claude -p --bare … --json-schema …`.
2. Decision kinds: `TRIAGE`, `AUTHORIZE`, `PLAN_REVIEW`, `PR_REVIEW`, `SECURITY_REVIEW`, `FAILURE_TRIAGE` (`overview.md` §8.2). Each has a versioned prompt template (hashed) and an output schema.
3. The coordinator decides **only when to ask**, by deterministic rules. It never substitutes its own judgement for a missing decision: if Claude is unavailable, the task waits, and after a configurable timeout (default 4 h awake) escalates to the operator.
4. Claude's output is never written to the DB by Claude. The Decision Recorder validates it and creates the immutable record ([ADR-011](ADR-011-authorization-records-and-verification.md)).
5. Each decision runs in a **fresh session** (no `resume`). Context comes from the input bundle and the read-only `mercury` MCP tools. Prior reviews are included as data.
6. **Interactive path, no second authority:** an operator's interactive Claude Code session may use the `mercury` CLI to read status (`mercury status`, `mercury trace JAM-123`) and to *request* a decision (`mercury request authorize JAM-123 --note …`). A request enqueues a normal decision run; it cannot create an authorization itself.
7. Claude never receives GitHub, Linear or Codex credentials and has no shell. If a review needs tests executed, the coordinator runs them and passes the report.

## Alternatives
| Alternative | Reason rejected |
|---|---|
| (b) Long-running Claude session driving the coordinator via CLI/MCP | Stops on sleep/restart; merges decide and execute in one session exposed to untrusted content; depends on an open session (the Slack-era failure) |
| Resumed Claude session per task (one session id across plan review and PR review) | Saves tokens, but carries possibly injected content forward and makes each decision harder to reproduce. Can be revisited as an optimisation with `forkSession` |
| Coordinator heuristics for "easy" approvals (e.g. auto-approve tiny plans) | Violates "Claude makes development decisions" |
| Claude subagents inside one run for PR + security review | Allowed later as an optimisation; separate top-level runs give clearer audit records for the MVP |

## Consequences
- Positive: decisions continue whenever `mercuryd` runs, independent of any chat session; each decision has a reproducible input bundle hash, prompt template hash, transcript hash and cost; least privilege for Claude.
- Negative: "Claude is the primary orchestrator" becomes "Claude is the decision authority"; the loop is code. This is a deliberate reading of the brief and must be confirmed by the operator. More tokens per decision than a persistent session.
- Risk: decisions are only as good as the bundle. Agent C/B must specify bundle contents per decision kind.

## Related requirements
Brief target operating model steps 1–3, 6–7, 10–11; §A (authorization authority), §D, §H (prompt injection, tool permission boundaries); AP-1, AP-2, AP-7.
