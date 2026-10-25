# Phase 4 Revision Disposition — Agent A (Principal AI Systems Architect)

| | |
|---|---|
| Agent | A |
| Date | 2026-10-12 |
| Basis | `reviews/30-reconciliation.md` (RD-1…RD-20, binding); Phase 3 findings addressed to A in `reviews/20`–`25` |
| Files changed | `architecture/overview.md`; `architecture/decisions/ADR-001`…`ADR-012` (revised); `ADR-013`…`ADR-020` (new); `architecture/decisions/README.md` (new ADR index); this file |

---

## 1. Summary of changes per document

### `architecture/overview.md` (rewritten)
- Header lists the single-source-of-truth owners; the document now references C, B, D, E and F instead of restating their content.
- §1 role table: credentials per role updated (model keys on fd 3, two Apps); RD-20 reading of "primary orchestrator".
- §2 system context diagram redrawn with zones H, C, A, `WORK_ROOT`, `mercury-ops`, sudo wrappers.
- §3 at-a-glance table covers ADR-001…020.
- §4 principles: AP-2, AP-3, AP-8, AP-9, AP-11 revised; AP-13 (stop is cheap, relax needs presence) and AP-14 (one source of truth) added.
- §5.1 component diagram uses C's module names; §5.2 boundaries table updated (derived queue, `agent-ctl`, `SnapshotBuilder`, hardened git, `MergeVerifier`); §5.3 **three trust zones** per RD-1 with a boundary-strength table; §5.4 filesystem now only references ADR-016 and `macos-service.md` §7.1.
- §6 main loop: derived queue, credited awake time, run adoption, guard at result application; concurrency by reference; one-active-mutating-run rule.
- §7: MCP rejected for v1; RD-8 revision rule; sequence diagram regenerated with `protocols/messages.md` IDs and the `integration_owns_done` default.
- §8: decision types by reference to ADR-004; TypeScript record shape removed (schemas are the source); integrity controls re-layered (agent uid, chain MUST, anchors, HMAC SHOULD, presence tier); guards by reference; §8.6 rewritten.
- §9: system-of-record table (17 task states, issue-level `discovered`, check runs, audit anchors, mode-dependent Linear ownership); conflict table uses C's holds and reason codes; new C11 (ruleset drift).
- §10 NFR section: **no IDs or targets defined**; maps quality attributes to F's NFR IDs and to mechanisms; Phase 2 aliases retired.
- §12 governance → G-ORG/G-SPLIT/G-DETECT summary; §13 migration → `MIG-0…4`; §14 tradeoffs T5 revised, T9–T11 added; §15 → README; §16 assumptions updated (ASM-A-04 refuted, -05/-06 superseded, -07 withdrawn, -09/-10 rewritten, -12 new); §17 OD references to F's register; OD-A-01…05 retired.
- All four Mermaid diagrams validated with the Mermaid 11 parser.

### ADRs revised
| ADR | Change |
|---|---|
| 001 | Dependency set per `components.md` §1 (RA-34); worker-thread exception; Status Accepted |
| 002 | Derived queue, `jobs` removed (RA-15); SQL removed; one-active-mutating-run rule (RA-16); C's table names (RA-32); backups/migrations defer to D (RA-33) |
| 003 | No MCP in v1 (RA-12); run dir in `WORK_ROOT`; wire-copy schemas; RD-8 hybrid revision rule |
| 004 | Canonical six decision types + `reauthorize` mode (RA-11); `failure_triage` deferred (OD-29); agent-uid spawn + ALT-B-1 fallback; snapshots (RA-13); no fallback model; security review every PR (RA-14) |
| 005 | Fresh implementation thread (RA-36, RF-37); per-task `CODEX_HOME` (RA-08); agent uid; `verify`/`deps_install` under Seatbelt as agent uid; CPU liveness; toolchains; absorbs ADR-P14 |
| 006 | `COMMENT` only (RA-04); hardened plumbing commits and mirror pushes with fd askpass (RE-03); durability order (RD-05); branch naming tied to OD-06 (RA-10); draft PRs; conflict path via `revision_request` (RA-11); brief step-9 deviation recorded (RA-38) |
| 007 | Values by reference (RA-35); dedup catalogue, retry matrix and probe from B |
| 008 | Becomes the **identity inventory** (RD-6): `mercury-bot`, `mercury-ops`, Linear app, model keys, `_mercuryagent`, operator, G-SPLIT deploy key; governance moved to ADR-014 (RA-06, RA-07, RE-10) |
| 009 | Two Linear status modes (RD-9); `spec_hash` and hold-based drift (RD-13, RA-01); `DISCOVERED` issue-level (RD-14); `Part of` premise withdrawn |
| 010 | Coordinator-only scope; values by reference (RA-22); startup/exit contract and SIGTERM per RD-11 (RD-10); U2 → OD-36 (RD-28) |
| 011 | Reauthorize/amend/revoke contract (RA-05); approvals bind `spec_hash`; guard at result application (RE-07, RE-14); integrity → ADR-018 with HMAC SHOULD (RA-19, RD-4); SQL removed; restore semantics |
| 012 | Partition rules only; criteria in roadmap (RA-25); `MIG-0…4` mapped to M9a–c (RF-18); legacy claim → eligibility exclusion |

Every ADR now uses the Phase 4 template: header (Status, Date 2026-10-12, Owner, Related), Context, Decision, Alternatives considered (with reasons), Consequences (+/−), Related requirements, Related findings, Operator decisions, Revision history.

### ADRs new
ADR-013 agent process isolation (RD-1); ADR-014 merge-actor enforcement and required MERCURY checks (RD-5, RD-14); ADR-015 task condition model (RD-3, RD-14); ADR-016 filesystem layout (RD-2, referencing D's §7.1); ADR-017 Claude review snapshot (RD-7); ADR-018 audit integrity (RD-4); ADR-019 notification channels, operator response and presence tier (RD-12, RD-19); ADR-020 detached runs, adoption and lost runs (RD-11).

### `architecture/decisions/README.md` (new)
ADR index (number, title, status, supersedes/revises, related ADRs, RD references), status vocabulary, template, and the retired `ADR-Pnn` → final-number map.

---

## 2. Finding dispositions

### 2.1 My own review (RA-*)

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RA-01 | 20 | Fixed (A part): hold-based drift, `spec_hash`, PR-stage check effect. C/B own table and hash text | ADR-009 item 4; ADR-015; overview §9.3 C1 |
| RA-02 | 20 | Fixed: broker design adopted as `agent-exec`/`agent-ctl` via sudoers (D's design) | ADR-013; overview §5.2–§5.3 |
| RA-03 | 20 | Fixed: three roots; D's §7.1 is the source | ADR-016; overview §5.4 |
| RA-04 | 20 | Fixed in A's documents; C (T25, schema enum), E (SEC-102), F (FR-162, M6-2) deferred to those owners | ADR-006 item 9; ADR-008; ADR-014 item 6 |
| RA-05 | 20 | Fixed at architecture level (contract and plan-approval invalidation); schema enum and transitions deferred (C, B) | ADR-011 item 3 |
| RA-06 | 20 | Fixed: check runs for both gates; permissions per RD-6 (see Objection 1 on `statuses:read`) | ADR-008; ADR-014 item 4 |
| RA-07 | 20 | Fixed per RD-6: `mercury-ops` covers ops issue, anchors and drift read; the proposed App-Auditor is not created | ADR-008 |
| RA-08 | 20 | Fixed (A part); B, D, E text deferred | ADR-005 item 4 |
| RA-09 | 20 | Fixed: presence tier | ADR-019 items 6–8; overview AP-13 |
| RA-10 | 20 | Fixed: two modes, default `integration_owns_done`; OD-A-03 and ASM-A-07 withdrawn | ADR-009 item 3; ADR-006 item 5; overview §16 |
| RA-11 | 20 | Fixed (A part); removal of `claude_failure_triage` from `runs.kind` deferred (C) | ADR-004 item 2; ADR-006 item 10 |
| RA-12 | 20 | Fixed; SEC-204 wording deferred (E) | ADR-003 item 4; overview §7.1 |
| RA-13 | 20 | Fixed | ADR-017 |
| RA-14 | 20 | Fixed; SEC-314 deferred (E) | ADR-004 item 2; overview §8.2 |
| RA-15 | 20 | Fixed | ADR-002 item 5; ADR-015 item 5; overview §6 |
| RA-16 | 20 | Fixed; F restates the property (RC-18) | ADR-002 item 6; overview §6 |
| RA-17 | 20 | Fixed (routing); single recipe list deferred (C, B) | ADR-014 item 9; overview §9.3 C6, C8 |
| RA-18 | 20 | Fixed (repo-scoped `integrity_alert` hold, presence-tier exit); hold kind deferred (C) | ADR-014 item 9; ADR-015 item 2 |
| RA-19 | 20 | Fixed per RD-4: HMAC is SHOULD (my Phase 3 "required" recommendation is superseded by the reconciliation; I accept its reasoning) | ADR-018 item 3; ADR-011 item 7 |
| RA-20 | 20 | Fixed (A part); `anchors`/`audit_epochs` tables and outbox kind deferred (C) | ADR-018 |
| RA-21 | 20 | Partially fixed (task row created only on triage shortlist or operator request); T01 wording deferred (C, B) | ADR-009 item 5 |
| RA-22 | 20 | Fixed | ADR-010 |
| RA-23 | 20 | Fixed: ASM-A-04 refuted; behaviour-based wording | overview AP-8, §5.2, §6, §16 |
| RA-24 | 20 | Fixed | overview §5.3 |
| RA-25 | 20 | Fixed | ADR-012 item 1 |
| RA-26 | 20 | Fixed in overview (F IDs only); registry is F's | overview §10 |
| RA-27 | 20 | Fixed | ADR-019 |
| RA-28 | 20 | Fixed (A part); `github.md` §18 deferred (B) | overview §9.1; ADR-015 item 1 |
| RA-29 | 20 | Fixed in A's documents (no enums restated; schemas are the source); FR-020 and B's text deferred (F, B) | overview §8.2; ADR-004 |
| RA-30 | 20 | Fixed per RD-3(a): hold ageing escalates once (replaces my proposed 72 h digest) | ADR-015 item 4 |
| RA-31 | 20 | Fixed (A part); D text deferred | ADR-020 item 10 |
| RA-32 | 20 | Fixed | ADR-002; overview §5 |
| RA-33 | 20 | Fixed | ADR-002 item 8 |
| RA-34 | 20 | Fixed | ADR-001 item 3 |
| RA-35 | 20 | Fixed | ADR-007 |
| RA-36 | 20 | Fixed | ADR-005 item 3 |
| RA-37 | 20 | Fixed | overview §7.2 |
| RA-38 | 20 | Fixed in ADR-006 Context; TDD §25/§26 entry deferred (orchestrator) | ADR-006 |

### 2.2 Findings from other reviews that name A or A's files

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RB-03 | 21 | Fixed (ADR-008 part) | ADR-006 item 9; ADR-008; ADR-014 item 6 |
| RC-04 | 22 | Fixed (overview C1) | overview §9.3 C1; ADR-009 item 4 |
| RC-18 | 22 | Fixed (overview) | overview §6; ADR-002 item 6 |
| RC-20 | 22 | Fixed (overview no longer uses `NFR-REL-*`; INV IDs are C's) | overview §6, §10 |
| RC-21 | 22 | Fixed (overview uses C's hold kinds and reason codes) | overview §9.3 |
| RC-23 | 22 | Fixed (overview C3 uses `deprioritized`/`operator_hold` holds) | overview §9.3 C3 |
| RC-30 | 22 | Fixed (A part) | ADR-016; overview §5.4 |
| RC-31 | 22 | Fixed (overview duplicate metric removed) | overview §6, §10 |
| RD-01 | 23 | Fixed (A: ADR) | ADR-013 |
| RD-03 | 23 | Fixed (A part); FR-282 and FakeClock deferred (F, C) | overview AP-8, §5.2, §6, §16 |
| RD-05 | 23 | Fixed (ADR-006 part) | ADR-006 item 4; ADR-020 item 9 |
| RD-10 | 23 | Fixed (ADR-010 decision 2 replaced) | ADR-010 item 4; ADR-020 items 4, 6 |
| RD-14 | 23 | Fixed (A part) | ADR-016 |
| RD-21 | 23 | Fixed (A part: values removed) | ADR-010; overview §10 |
| RD-22 | 23 | Fixed (A part: measurement rule referenced; F defines it) | overview §10 |
| RD-25, RD-26 | 23 | Fixed (A part) | ADR-004 item 3; ADR-013 items 5, 7; ADR-005 item 8 |
| RD-28 | 23 | Fixed | ADR-010 item 8; ADR-013 |
| RE-01 (A-SEC-2, A-SEC-3) | 24 | Fixed per RD-1 (agent uid rather than E's U2; U2 recorded as OD-36) | ADR-013; overview §5.3, §8.6 |
| RE-04 | 24 | Fixed (architecture); method classification in C | ADR-019 items 6–7 |
| RE-05 | 24 | Fixed (architecture); posting in B, guard in C, list in E | ADR-014 item 4 |
| RE-06 | 24 | Fixed | ADR-017 |
| RE-07 | 24 | Fixed | ADR-020 items 3–7; ADR-011 item 6 |
| RE-08 | 24 | Fixed (policy recorded) | ADR-019 item 8; ADR-008 rule 4 |
| RE-09 | 24 | Fixed per RD-4 | ADR-018 |
| RE-10 | 24 | Fixed | ADR-008 |
| RE-11 | 24 | Fixed (architecture rule); texts are D's | ADR-019 item 4 |
| RE-12 | 24 | Noted in ADR-006 item 6; renderer owned by C, B | ADR-006 |
| RE-13 | 24 | Fixed (worktrees out of the operator's home) | ADR-016 |
| RE-14 | 24 | Fixed | ADR-011 item 6; ADR-009 item 4 |
| RE-25 | 24 | Fixed (architecture: security never auto-clears; `security_halt`) | ADR-015 item 4; ADR-014 item 9 |
| RE-26 | 24 | Fixed (ADR numbers canonical, `ADR-Pnn` retired); SEC numbering is E/F | decisions/README.md |
| A-SEC-1 | 24 §3.2 | Fixed | ADR-014 |
| A-SEC-5 | 24 §3.2 | Fixed (chain failure → safe mode) | ADR-010 item 3; ADR-018 item 4 |
| RF-01 | 25 | Fixed (A: ADR) | ADR-013 |
| RF-04 | 25 | Fixed (A part: overview defines no targets) | overview §10 |
| RF-08 | 25 | Fixed per RD-9 (default `integration_owns_done`, which differs from F's recommendation; reconciliation governs) | ADR-009 item 3 |
| RF-10 | 25 | Fixed per RD-6 (`mercury-ops` rather than `mercury-audit`) | ADR-008; ADR-018 item 2 |
| RF-14 | 25 | Fixed (A part: OD-A-05 values removed) | overview §17 |
| RF-15 | 25 | Fixed (A part) | overview §16 ASM-A-04 |
| RF-16 | 25 | Fixed (A part) | ADR-009; ADR-015; overview C1 |
| RF-18 | 25 | Fixed | ADR-012; overview §13 |
| RF-19 | 25 | Fixed (overview C10 uses `reauthorization_required`) | overview §9.3 C10 |
| RF-20 | 25 | Fixed (A part: A's targets mapped to F IDs) | overview §10 |
| RF-25 | 25 | Fixed | ADR-013…020; decisions/README.md |
| RF-27 | 25 | Fixed per RD-14 scoping (global halt vs repo `integrity_alert`, not RF-27's per-repo pause for all failures) | ADR-014 item 9 |
| RF-32 | 25 | Fixed (A part: NFR-083/084 referenced); cost model deferred (F) | overview §10 |
| RF-36 | 25 | Fixed (A part); traceability update deferred (F) | decisions/README.md |
| RF-37 | 25 | Fixed | ADR-005 item 3 |

---

## 3. Objections to reconciliation decisions

I implemented every decision as written. Three points for the orchestrator to reconsider:

1. **RD-6 drops `statuses:read` from `mercury-bot`.** RD-5 says T22 waits on non-MERCURY required checks derived from `GET /rules/branches/{base}`. If a target repository's required context is a **commit status** (third-party CI, some Actions setups) rather than a check run, reading it needs `statuses:read`. Recommendation: B confirms in Phase 0 whether any required context of the target repositories is a status; if so, add `statuses:read` (read-only, low risk). ADR-008 lists the RD-6 set unchanged.
2. **RD-4 places the chain head in the `MERCURY / claude-review` check-run summary**, which is public on public target repositories. F's OD-24 default is "no public chain-head embed". The leak is small (sequence number and hash reveal activity cadence only), but the two statements contradict each other. Recommendation: either accept the check-summary carrier explicitly in OD-24, or drop it for public repositories and rely on the Linear comment and the private anchor repository. ADR-018 follows RD-4 and points to OD-24.
3. **RD-11 names `run/coordinator.alive` without a root.** `agent-exec` runs as `_mercuryagent` and cannot read `MERCURY_HOME` (RD-2). The liveness file must be under `WORK_ROOT`. ADR-020 states this; D fixes the path in §7.1. This is a clarification, not a change of decision.

---

## 4. Remaining open items

| # | Item | Owner |
|---|---|---|
| 1 | Assign `P0-nnn` check IDs for ASM-A-01…ASM-A-12 in the unified register (only P0-26 and P0-27 are cited from D) | F |
| 2 | Register the new NFR IDs that overview §10 cites from F's §6.4 resolution (NFR-006, -007, -025, -026, -027, -045, -063, -084, -095) and the alias map for the retired `NFR-LAT/REL/…` IDs | F |
| 3 | `reviews/25` §6.5 proposed other numbers for ADR-013…019; traceability must use the numbering in `decisions/README.md` | F |
| 4 | Hold kinds and reason codes referenced by ADR-014/015: `integrity_alert` (repo), `security_halt` (global/repo), `operator_hold`, `policy_ack_required`; re-authorization enum; removal of `claude_failure_triage` | C |
| 5 | Legacy-claim refusal as an issue-level eligibility exclusion (ADR-012 item 3) | C, B |
| 6 | Liveness-file path under `WORK_ROOT`; the parameter table's final section number (ADRs cite it by name) | D |
| 7 | `statuses:read` decision (Objection 1); CI-on-draft onboarding requirement | B |
| 8 | OD-24 vs RD-4 check-summary anchor (Objection 2) | Orchestrator, operator |
| 9 | TDD §25/§26 entry for the brief step-9 deviation (RA-38) and TDD §11 brief-state mapping table | Orchestrator |
| 10 | ASM-A-12 (presence helper feasibility) is new and needs a Phase 0 check | F, D |
