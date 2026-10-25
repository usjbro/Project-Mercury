# Agent A Report — Principal AI Systems Architect (Phase 2)

Date 2026-10-12. Design only; nothing outside `docs/mercury/` was modified and no external system was written to.

Deliverables:
- `docs/mercury/architecture/overview.md` — system context, component architecture, trust domains, principles, communication pattern, Claude decision model, authorization integrity, system-of-record and conflict tables, NFRs, technology matrix, governance options, migration, tradeoffs, assumptions, operator decisions.
- `docs/mercury/architecture/decisions/ADR-001` … `ADR-012` (all Status: Proposed).

---

## 1 Findings

1. **The brief's two roles conflict unless "orchestrator" is read as "authority".** Claude cannot hold the loop: a session does not survive sleep, restart or compaction, and the Slack workflow failed precisely because progress depended on an open chat session (discovery fact 12; Slack failure patterns 3, 4). The coordinator must hold the loop and Claude the decisions.
2. **A long-running Claude session driving the coordinator would merge decide and execute** in one session that also reads untrusted repo and Linear text; an injection could dispatch work. Headless Claude also loads repo hooks and `.mcp.json` unless isolated (discovery fact 6).
3. **Direct agent-to-agent communication has no stable substrate** (Codex `mcp-server` removed; `app-server` experimental) and would bypass the dispatch guard.
4. **Authorization integrity inside one OS user is limited.** Code in the same user account can forge any local record. The meaningful backstop is GitHub's code-owner + last-push approval; local controls should target bugs, confused deputies and auditability.
5. **Personal-account GitHub** makes "human approves" preventable but "only human merges" only detectable, unless repos move to an organization (discovery fact 4).
6. **Linear has many writers** (operator, GitHub integration, Linear Agent/Coding sessions, MERCURY). A strict single-owner model per datum plus "inbound may stop, never start" is necessary.
7. **SQLite's single-transaction state + queue + outbox** is the simplest way to reach zero duplicate executions; a separate broker cannot join that transaction.
8. **Migration risk is concurrent ownership of one issue** by the legacy scripts and MERCURY; partitioning by an opt-in label removes it.

## 2 Recommended design

Summary (details and links in `architecture/overview.md` §3):

| # | Recommendation | Where |
|---|---|---|
| R1 | Single local daemon `mercuryd`, Node.js 24 LTS + TypeScript, one process, child processes for agents | ADR-001, overview §5–6 |
| R2 | SQLite WAL `synchronous=FULL` `fullfsync=ON` as store, queue, outbox and audit; duplicate prevention by unique partial indexes; immutability by triggers | ADR-002 |
| R3 | Hub-and-spoke communication; no direct agent-to-agent channel; read-only in-process MCP for Claude context | ADR-003, overview §7 |
| R4 | Claude invoked per decision point as an isolated headless decision service (TRIAGE, AUTHORIZE, PLAN_REVIEW, PR_REVIEW, SECURITY_REVIEW, FAILURE_TRIAGE); interactive Claude sessions may only *request* decisions via the CLI | ADR-004, overview §8.1–8.2 |
| R5 | Codex via supervised `codex exec`, read-only sandbox for planning, workspace-write without network for implementation (provisional) | ADR-005 |
| R6 | Coordinator owns commit/push/PR with trailers and diff guards; never merges | ADR-006 |
| R7 | Outbound polling with ETags and `updatedAt` cursors; full reconcile on start, wake and every 15 min | ADR-007 |
| R8 | GitHub App + Linear `actor=app` identities; CODEOWNERS = operator, last-push approval, stale dismissal, no bypass; merge verification; G-1 (personal) for MVP, G-2 (org) as target | ADR-008, overview §12 |
| R9 | System-of-record split: Linear = spec/intent/eligibility; coordinator = execution + authority; GitHub = code + human approval; 10 conflict rules | ADR-009, overview §9 |
| R10 | Per-user LaunchAgent (provisional) | ADR-010 |
| R11 | Immutable, hash-bound authorization/approval records; DB triggers require a succeeded Claude run with matching output hash; dispatch guard re-verifies in the claim transaction; HMAC optional | ADR-011, overview §8.3–8.6 |
| R12 | Migration M0 inventory → M1 shadow (dry-run) → M2 label-scoped pilot → M3 cutover → M4 decommission | ADR-012, overview §13 |
| R13 | 27 measurable NFRs, e.g. authorization → Codex start p95 ≤ 30 s / max ≤ 120 s; crash recovery ≤ 60 s; duplicate executions = 0; 100 % Codex runs traceable to authorization + plan hash | overview §10 |

## 3 Alternatives considered

| Topic | Alternatives | Outcome |
|---|---|---|
| Runtime | Python, Go, Temporal, Redis/BullMQ, GitHub-Actions-hosted, Linear-as-store, Claude-session loop | Weighted matrix (overview §11): Node/TS 4.40, Python 4.05, Go 3.80, Temporal 3.50, BullMQ 3.40, Actions 2.90, Linear-store 2.85, Claude loop 2.75 |
| Claude model | Long-running session driving coordinator via CLI/MCP; resumed session per task; coordinator heuristics | Rejected (ADR-004) |
| Communication | MCP direct, shared files, Slack-like bus, local HTTP, Linear comments | Rejected (ADR-003) |
| Authorization integrity | Claude-held signing key; Linear-stored authorization; external notarisation; mutable status | Rejected or deferred (ADR-011) |
| Governance | Machine user; operator token; fork model | Rejected (ADR-008) |
| Migration | Big-bang; Slack mirror; wrapping scripts | Rejected (ADR-012) |

**Disagreements with or refinements to the baseline (`03-design-baseline.md`):**
- *Refinement:* "Claude (decision role)… invoked by the coordinator" is kept, but I make explicit that this reinterprets the brief's "Claude is the primary orchestrator" as **decision authority, not loop control**. Operator should confirm.
- *Refinement:* `TRIAGE` output carries **no authority**; only `AUTHORIZE` creates an authorization. The baseline lists triage and authorization together.
- *Addition:* `FAILURE_TRIAGE` decision kind so that retry/replan/escalate after failures remains a Claude decision, not coordinator logic.
- *Suggestion for Agent C:* keep `BLOCKED` as one state with typed reason codes (`spec_changed`, `dependency`, `deprioritized`, `foreign_push`, `foreign_agent`, `legacy_claim`, `reauthorization_required`, `budget`, `revision_limit`, `external_state_conflict`) rather than adding states.
- *Technology:* baseline says "Node.js (LTS)"; I pin **Node 24** now with a move to 26 after its LTS date.

## 4 Tradeoffs

See overview §14 (T1–T8). Most significant:
- T1 Per-decision Claude runs: robust and least-privilege, but more tokens and no conversational memory.
- T3 Coordinator owns git: agents hold no credentials, but one commit per implementation round.
- T5 G-1 for MVP: quick start, but "human clicks merge" is detective only.
- T8 Lenient Linear projection: no fights with operator or integration, but Linear can briefly be ahead of verified state.

## 5 Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| RA-1 | Operator expected Claude to be a conversational orchestrator; the decision-service model feels indirect | Medium | Medium | Interactive CLI path (`mercury status/trace/request`); confirm in Phase 4 |
| RA-2 | Under G-1 the App could merge an approved PR (compromise or bug) | Low | Medium | No merge method in client (static test); merge verification alert; G-2 migration |
| RA-3 | Linear GitHub integration closes issues on merge despite `Part of` phrasing | Medium | Low | Lenient projection; option to disable PR automations (ASM-A-07) |
| RA-4 | `node:sqlite` RC regressions or API renames | Medium | Medium | Repository interface; `better-sqlite3` fallback; pinned Node |
| RA-5 | Agent CLI version drift breaks flags | High over time | High | Pinning; startup self-test (AP-12); contract tests per version |
| RA-6 | Decision quality depends on context bundles | Medium | High | Bundle spec per decision kind (Agent B/C); shadow-mode agreement metric |
| RA-7 | Coordinator is a single process: a bug can stall all tasks | Medium | Medium | launchd restart, stall detection, `mercury doctor`, one-shot escalation |
| RA-8 | Mac asleep or logged out for long periods stalls work | High | Low | Accepted; gap notification; tasks pause, not fail |
| RA-9 | Same-user trust domain allows forged records by malware | Low | Medium | GitHub backstop; optional HMAC; separate-user future option |

## 6 Assumptions

ASM-A-01 … ASM-A-11 in overview §16 (TCC-free paths; LaunchAgent Keychain access; fullfsync latency; monotonic clock pauses during sleep; Codex shared-home concurrency; Codex sandbox cannot write MERCURY state; Linear `Part of` behaviour; repo transfer keeps Linear links; GitHub App on personal account with required permissions; Claude API-key auth under launchd; Linear `actor=app` without webhooks). All require Phase 0 checks.

## 7 Dependencies

| On | Needed | Assumed until delivered |
|---|---|---|
| Agent B | Claude/Codex adapter contracts, context bundle per decision kind, GitHub/Linear polling and projection detail, Linear state mapping | Overview §8.2, §9.1 projection table; ADR-005/006/007 constraints |
| Agent C | State machine and transition table, full DDL, message schemas, guard catalogue | Baseline state names; `BLOCKED` with reason codes; tables named in ADR-002/011 |
| Agent D | launchd plist, shutdown, recovery procedures, backup/restore, wake detection | ADR-010; NFR-REL-01/02 |
| Agent E | Threat model validating §8.6 position and ADR-008 controls; prompt-injection tests | AP-2, AP-7 |
| Agent F | Requirement IDs, NFR acceptance criteria, migration stages in roadmap | NFR IDs in overview §10 are proposals |
| Operator | OD-A-01 … OD-A-05 (overview §17) | Recommended defaults |

## 8 Unresolved questions

1. Does the operator accept "Claude = decision authority, coordinator = loop" as the meaning of "primary orchestrator"? (RA-1)
2. OD-A-01: stay personal (G-1) or move target repos to an organization (G-2), and when?
3. OD-A-02: eligibility marker `Todo` + `mercury` label, or a new Linear state?
4. Should HMAC on records be implemented at all (depends on ASM-A-06)?
5. Can Codex share one `CODEX_HOME` concurrently, or should each task get its own (Agent B, ASM-A-05)?
6. Should `PR_REVIEW` and `SECURITY_REVIEW` be one Claude run with a subagent, or two runs (cost vs audit clarity)? Proposed: two runs for MVP.
7. Does Claude re-authorize automatically on minor spec edits (typo) or always? Proposed: always; Claude may answer quickly with the diff in the bundle.

## 9 Supporting evidence

- `reviews/00-brief.md`: roles, hard constraints, required areas.
- `reviews/03-design-baseline.md`: vocabulary, authority invariants, discovery facts 1–12.
- `reviews/01-discovery-integrations.md`: Slack failure patterns; Linear states, labels, `Todo` queue; identity confusion (JAM-160); branch naming; Linear GitHub automation; legacy scripts.
- `reviews/02-discovery-agent-runtimes.md`: §1 summary items 2–10; §2.2 Agent SDK options; §2.6 repo-content trust; §3.1–3.2 `codex exec`, sandbox, `.git` protection; §3.4 MCP status; §5 R1–R4.
- `reviews/02-discovery-platform.md`: §1.1–1.4 protections, App vs machine user, personal-account gap; §2 polling and rate limits; §3 Linear API, `actor=app`, coding sessions; §4 launchd, sleep, TCC, Keychain; §5 SQLite durability and Node versions.
- `reviews/01-discovery-local.md`: Mac unobservable → Phase 0.

## 10 Confidence level

| Recommendation | Confidence | Why |
|---|---|---|
| R1 Node/TS daemon | High | Clear SDK advantage; matrix robust to weighting; Python is a close fallback |
| R2 SQLite store + queue | High | Load is tiny; transactional state + effect is the key property; durability pragmas documented |
| R3 Hub-and-spoke | High | Direct alternatives lack stable substrate and bypass guards |
| R4 Claude decision service | Medium-High | Technically strong; Medium only because it reinterprets "primary orchestrator" and needs operator agreement |
| R5 Codex exec | Medium | Provisional; several Codex behaviours unverified (ASM-A-05, ASM-A-06) |
| R6 Coordinator owns git | High | Least privilege; aligns with `.git` protection whether or not Codex could commit |
| R7 Polling | High | Only option without inbound access or third parties |
| R8 Identities & governance | High for App + protections; Medium for the G-1/G-2 choice | GitHub behaviour verified from docs; choice is the operator's risk appetite |
| R9 System-of-record split | Medium-High | Linear integration interaction (ASM-A-07) unverified |
| R10 LaunchAgent | Medium | Mac unobserved; Agent D to confirm |
| R11 Authorization records | High for triggers/hash binding; Low-Medium for value of HMAC | Same-user trust domain limits cryptographic value |
| R12 Migration | Medium | Legacy scripts not yet read (M0) |
| R13 NFR targets | Medium | Targets are reasoned, not measured; Phase 0 benchmarks may move them |
