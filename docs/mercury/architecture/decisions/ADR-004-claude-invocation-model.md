# ADR-004: Claude invoked by the coordinator as a headless decision service

| | |
|---|---|
| Status | **Accepted (pending operator decisions: OD-17, OD-29, OD-34)** |
| Date | 2026-10-12 (Phase 4 revision; first proposed Phase 2) |
| Owner | Agent A. Agent B owns the integration contract (`integrations/claude.md`); Agent C owns the output schemas (`protocols/schemas/output.*`) |
| Related ADRs | [ADR-003](ADR-003-coordinator-mediated-agent-communication.md), [ADR-011](ADR-011-authorization-records-and-verification.md), [ADR-013](ADR-013-agent-process-isolation.md), [ADR-017](ADR-017-claude-review-snapshot.md), [ADR-020](ADR-020-detached-runs-and-adoption.md) |

## Context
- The brief makes Claude "the primary orchestrator" and the decision maker, and the coordinator "a continuously running local coordinator" that "executes and tracks". Both must hold together.
- Two models are possible:
  - **(a)** the coordinator invokes Claude at decision points as a short-lived, isolated, schema-constrained run;
  - **(b)** a long-running Claude session drives the coordinator through a CLI or MCP tool surface.
- Facts:
  - A Claude session does not survive sleep, logout or restart, and its context compacts. The Slack workflow progressed only "while a chat session is open" (discovery fact 12).
  - Headless Claude runs repository hooks and `.mcp.json` unless isolated (discovery fact 6).
  - Under (b) Claude needs write tools that cause execution, in the same session that reads untrusted repository and Linear text.
- Phase 3 found that the decision catalogue differed between A, B and C (RA-11), that Claude was reading git worktrees rather than object snapshots (RA-13), and that Claude runs executed as the operator's uid (RE-01).

## Decision
1. **Model (a).** Claude holds the **authority**; `mercuryd` holds the **loop** (RD-20). Each decision is a fresh Claude run started by the `ClaudeAdapter` through the Agent SDK with the isolated profile defined in `integrations/claude.md` §2. The `claude -p` CLI is the documented fallback.
2. **Canonical decision types** (the only ones in v1):

   | Decision type | Purpose | Authority produced |
   |---|---|---|
   | `triage` | Rank eligible issues | None (a proposal) |
   | `authorization` (modes `initial`, `reauthorize`) | Authorize, decline, defer, ask for a spec, or escalate; in `reauthorize` mode also confirm same scope, amend scope or revoke ([ADR-011](ADR-011-authorization-records-and-verification.md)) | Authorization version |
   | `plan_review` | Approve or request revision of a plan version | Plan approval bound to the plan hash |
   | `pr_code_review` | Review the PR at an exact head SHA | Review verdict bound to the head SHA |
   | `pr_security_review` | Security review of every PR (depth scales with labels and policy hits) | Security verdict bound to the head SHA |
   | `revision_request` | Turn non-Claude feedback into a Codex instruction ([ADR-003](ADR-003-coordinator-mediated-agent-communication.md) item 6) | Revision instruction |

   Triggers, inputs, limits and readable roots per type are defined in `integrations/claude.md` §3–§4; output schemas in `protocols/schemas/`. A `failure_triage` decision type is **deferred** (OD-29): after automatic retries a failed run goes to `BLOCKED(run_exhausted)` and the operator decides.
3. **Claude runs as the agent uid.** The SDK's custom spawner starts the Claude process through `agent-exec --kind claude` as `_mercuryagent` ([ADR-013](ADR-013-agent-process-isolation.md)). The model key arrives on fd 3 only; the Claude config directory is per run under `WORK_ROOT/runs/<run_id>/`. If the Phase 0 SDK spawn test fails, the fallback is B's ALT-B-1: the Messages API with coordinator-implemented, realpath-confined Read, Grep and Glob over the snapshot, which removes the Claude subprocess entirely.
4. **Claude reads only coordinator-built snapshots** of repository trees (at `base_sha` for authorization and plan review, at `head_sha` for PR review), never a git checkout and never a Codex worktree ([ADR-017](ADR-017-claude-review-snapshot.md)).
5. **The coordinator decides only when to ask**, by deterministic rules. It never substitutes its own judgement. If Claude is unavailable the task waits, under the state timers in `state-machine.md` §7.3, and escalates once.
6. **Authority decisions run without a fallback model.** The model actually used is recorded on the run (RD-18). Model choice per decision type is configuration (OD-34).
7. Claude's output is never written to the DB by Claude. The `DecisionRecorder` validates it and creates the immutable record ([ADR-011](ADR-011-authorization-records-and-verification.md)).
8. **Fresh session per decision** (no `resume`). Prior reviews are included in the bundle as data.
9. **Interactive path, no second authority.** An operator's interactive Claude Code session may use the `mercury` CLI to read status and to *request* a decision. The request starts a normal isolated decision run; only that run's output carries authority. The interactive session cannot clear escalations ([ADR-019](ADR-019-notifications-and-operator-presence.md)).
10. Claude never receives GitHub, Linear or Codex credentials and has no shell. Tests are run by the coordinator's `verify` step and passed to Claude as a report.
11. Crash behaviour: Claude runs use pipes and are not adoptable. After a coordinator restart they are killed and re-run with the same `input_digest`, consuming no attempt ([ADR-020](ADR-020-detached-runs-and-adoption.md)).

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| (b) Long-running Claude session driving the coordinator | Stops on sleep and restart; puts decide and execute in one session exposed to untrusted content; depends on an open session (the Slack-era failure) |
| Resumed Claude session per task | Saves tokens, but carries possibly injected content forward and makes decisions harder to reproduce. May be revisited with `forkSession` |
| Coordinator heuristics for "easy" approvals | Violates "Claude makes development decisions" (CON-003) |
| `failure_triage` decision type in v1 | No contract exists, and the human outranks Claude for "give up or retry" questions. Deferred (OD-29) |
| Claude as the operator's uid with deny rules only | Leaves the operator's and MERCURY's credentials readable by a process that reads untrusted text (RE-01). Replaced by [ADR-013](ADR-013-agent-process-isolation.md) |
| Security review only for labelled PRs | A missed finding costs more than one run per PR; the review binding guard already requires both reviews (RA-14, OD-23) |

## Consequences
- **Positive:** decisions continue whenever `mercuryd` runs, independent of any chat session. Each decision has a reproducible input digest, prompt template hash, transcript hash, model and cost.
- **Positive:** least privilege: read-only tools over immutable snapshots, as a uid that cannot read any credential.
- **Negative:** "Claude is the primary orchestrator" is read as "Claude is the decision authority"; the loop is code. This reading needs operator confirmation (OD-17).
- **Negative:** more tokens per decision than a persistent session; Claude has no memory across decisions.
- **Risk:** decisions are only as good as the bundle; the per-type input lists in `claude.md` §4 are normative.

## Related requirements
FR-020, FR-021, FR-023, FR-101, FR-106, FR-160, FR-161, FR-163; CON-003, CON-005, CON-006; SEC-201, SEC-204, SEC-205. IDs per `planning/traceability.md` and `security/threat-model.md`.

## Related findings
RA-11 (decision catalogue), RA-13 (snapshots), RA-14 (security review on every PR), RA-29 (enum drift: schemas are the single source), RE-01, RB-08, RD-25 (Claude under the agent uid).

## Operator decisions
- **OD-17** meaning of "primary orchestrator" (default: decision authority; the coordinator holds the loop).
- **OD-29** `failure_triage` in v1 (default: deferred).
- **OD-34** model per decision type (default: the same pinned model for all types in the pilot).
- OD-23 (security review on every PR) is decided by this ADR's default.

## Revision history
- Phase 4: canonical six decision types with `reauthorize` mode; `FAILURE_TRIAGE` deferred; agent-uid spawn and ALT-B-1 fallback; snapshots; no fallback model; MCP removed; Claude-unavailable timer delegated to `state-machine.md` §7.3.
