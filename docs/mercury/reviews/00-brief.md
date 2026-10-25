# Project MERCURY — Design Brief (orchestrator's capture of the mission)

This file restates the operator's mission so every subagent works from the same requirements. It is the input to the design process, not a design decision.

## Mission
Produce an implementation-ready Technical Design Document for **Project MERCURY**: a locally hosted (Apple Mac, macOS), event-driven, multi-agent software development orchestration platform that **replaces Slack** as the coordination channel between **Claude Code** (orchestrator / decision maker / reviewer) and **OpenAI Codex CLI** (planner + implementer). GitHub = source control, PRs, review, CI/CD. Linear = issues, specs, dependencies, status.

**Design only. No implementation. Do not modify any host, repository settings, Linear, GitHub, or Slack.** Code/config snippets are examples for review.

## Core boundary (must not blur)
Claude makes development decisions. MERCURY (the coordinator) coordinates execution. Codex performs implementation. The human operator retains final merge authority.

## Target operating model
1. Claude is the primary orchestrator.
2. Claude evaluates and prioritizes eligible Linear issues.
3. Claude explicitly authorizes each development task.
4. A continuously running local coordinator executes and tracks authorized tasks.
5. Codex receives a task and produces an implementation plan.
6. Claude reviews the plan against the Linear spec + architecture, security, testing requirements.
7. Claude may approve automatically or request revisions.
8. Codex implements approved plans in isolated Git worktrees.
9. Codex runs relevant tests and prepares a GitHub PR.
10. Claude independently reviews the PR (functionality, maintainability, security, spec compliance).
11. Failed reviews produce actionable revision requests; task returns to Codex.
12. Successful reviews notify the human via GitHub and, where appropriate, Linear.
13. Only the human operator can approve and merge protected-branch PRs.
14. After merge, the coordinator verifies repository state and updates Linear.
15. All unfinished tasks recover safely after coordinator restarts.

Human uses iPhone + Mac. Prefer existing GitHub/Linear notifications over any new dashboard/app. **No public inbound access to the Mac.**

## Hard constraints
- Coordinator must NEVER autonomously start development based solely on a Linear status change. Claude authorization is required, and it is a versioned record.
- Codex cannot execute unapproved implementation work through the coordinator.
- Human approval boundary must be enforceable by **technical permissions + GitHub protections**, not only prompt instructions. Agent approvals must not be able to impersonate human approvals.
- Do not assume work continues while macOS sleeps. Mac may sleep, restart, lose connectivity.
- A plan revision invalidates earlier approval unless the revised artifact is explicitly re-approved.
- Bounded revision cycles with escalation to the human.
- Never expose secrets in docs.

## Required content areas (TDD must cover in detail)
A. Agent orchestration (authorization authority, scheduling/dispatch, concurrency limits, dependency resolution, status, failure detection, cancel/resume, duplicate-execution prevention, multi-process coordination, versioned authorization records).
B. Agent communication (evaluate JSON messages, local persistent queues, SQLite event processing, CLI execution, MCP, filesystem artifacts, IPC, HTTP). Schemas for: task authorization, task assignment, implementation plan, plan review, plan approval, plan revision request, implementation progress, test results, PR creation, code review, security findings, revision requests, completion and failure events. Include correlation IDs, schema versions, timestamps, issue IDs, repo IDs, execution IDs, dedup IDs.
C. Workflow state machine: Discovered, Awaiting Claude authorization, Authorized, Planning, Awaiting Claude plan review, Plan revision requested, Plan approved, Implementing, Testing, PR opened, Claude PR review, Changes requested, Awaiting human approval, Merged, Completed, Failed, Blocked, Cancelled (renames allowed if justified). Valid transitions, guards, initiator, required evidence, persistent changes, retry limits, timeouts, recovery semantics, terminal states. Full transition table + Mermaid diagram.
D. Claude plan approval: spec compliance, AC coverage, architecture, dependencies, security, test strategy, scope, feasibility, maintainability. Machine-readable results, explicit approval conditions, max revision cycles, escalation.
E. GitHub PR workflow: branch/worktree naming, commit conventions, PR template, Linear linking, checks, Claude code review, Claude security review, review persistence, revision loops, required human approval, merge verification, post-merge Linear updates. Branch protection, rulesets, token privileges, service identities, separation of duties.
F. Local execution: launchd, login-session behavior, supervision, graceful shutdown, crash recovery, DB integrity, durable checkpoints, retry after connectivity loss, orphaned agent processes, safe worktree cleanup, restart after incomplete tasks.
G. Human notifications: repeated plan-review failure, decisions needing human judgment, security escalation, unrecoverable failures, PR ready for approval, CI failures needing intervention, merge completion. Avoid duplicates/low-value alerts.
H. Security: authn/authz, agent identity, least privilege, credential mgmt, secret redaction, filesystem protections, command execution restrictions, tool permission boundaries, prompt-injection defenses, repo content trust, malicious Linear comments, malicious PR content, human approval enforcement, audit integrity, supply chain, dependency security. Distinguish software-enforced vs policy-enforced controls.
I. Observability/audit: answer — which Linear issue started the task; which Claude authorization permitted Codex; which plan version was approved; which Codex run produced code; what tests ran + results; which commits/PR; what Claude reviewed; which security findings; who approved merge; what happened after failure/restart. Log structure, correlation, retention, redaction.
J. Testing: unit, integration, state-machine, contract, E2E, GitHub/Linear integration, agent failure simulation, network interruption, Mac restart recovery, duplicate events, concurrency, security boundary, unauthorized merge attempts, prompt-injection resistance. Measurable pass/fail criteria.

## Required TDD sections (docs/mercury/TDD.md)
1 Executive Summary · 2 Problem Statement · 3 Goals and Non-Goals · 4 Existing System Assessment · 5 Requirements · 6 Architecture Principles · 7 Architecture Overview · 8 Component Design · 9 Agent Responsibilities and Authority · 10 Agent Communication Protocol · 11 State Machine and Workflow Lifecycle · 12 Linear Integration Design · 13 Codex Execution Design · 14 Claude Review and Approval Design · 15 GitHub Integration and Merge Governance · 16 Data Model and Persistence · 17 API and Message Contracts · 18 macOS Runtime and Service Management · 19 Security Architecture and Threat Model · 20 Reliability and Failure Recovery · 21 Logging, Monitoring, and Auditability · 22 Testing and Verification · 23 Performance and Resource Management · 24 Deployment and Upgrade Strategy · 25 Alternatives and Tradeoffs · 26 ADRs · 27 Implementation Roadmap · 28 Issue Breakdown and Dependencies · 29 Requirements Traceability Matrix · 30 Risks, Assumptions, Open Questions · 31 Subagent Review Findings · 32 Final Design Validation and Sign-Off Status.

Mermaid diagrams required: architecture, task workflows, agent message sequences, data relationships, state transitions, failure recovery.

## Documentation layout
```
docs/mercury/
  TDD.md                          (authoritative; orchestrator-owned)
  architecture/overview.md        (Agent A)
  architecture/components.md      (Agent C, with A)
  architecture/state-machine.md   (Agent C)
  architecture/decisions/ADR-*.md (Agent A)
  integrations/claude.md codex.md linear.md github.md (Agent B)
  protocols/messages.md + protocols/schemas/*.json   (Agent C, with B)
  security/threat-model.md        (Agent E)
  security/security-review.md     (Agent E)
  operations/macos-service.md recovery.md (Agent D)
  testing/verification-plan.md    (Agent C + D + E inputs; owned by F for criteria? see assignments)
  planning/roadmap.md issue-breakdown.md traceability.md (Agent F)
  reviews/                        (process record: brief, discovery, agent reports, peer reviews)
```
Single source of truth rule: each requirement/contract is defined in exactly one place and referenced elsewhere. Requirement IDs are owned by Agent F (planning/traceability.md + TDD §5).

## Quality gates
Every subagent delivered or limitation recorded; all major interfaces contracted; deterministic lifecycle; every transition has authorization rules; persistence + recovery specified; communication versioned + traceable; Claude authorization required before development; Codex cannot run unapproved work via the coordinator; human approval enforced via GitHub permissions/protections; security independently reviewed; failure scenarios documented; measurable verification criteria; roadmap reflects dependencies; incremental implementability; assumptions and open decisions documented. Do not confuse theoretical design completeness with validated implementation.

## Per-agent report format (Phase 2)
Findings · Recommended design · Alternatives considered · Tradeoffs · Risks · Assumptions · Dependencies · Unresolved questions · Supporting evidence · Confidence level.
