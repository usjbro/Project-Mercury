# Phase 3 Review (Agent B, Solutions Architect): Software Interfaces and Integration Assumptions

| | |
|---|---|
| Reviewer | Agent B (Solutions Architect) |
| Date | 2026-10-12 |
| Focus | Whether Agent C's components, state machine, messages and schemas, Agent D's operations docs, and Agent E's controls assume only what Claude Code / Agent SDK, Codex CLI, GitHub and Linear can actually do. Self-review of B's own `integrations/*.md` included. |
| Mode | Design review only. No repository, GitHub, Linear or host changes. Vendor sources read through public documentation and public source mirrors (see §7). |

---

## 1 Scope and method

**Read in full:** `reviews/00-brief.md`, `03-design-baseline.md`, and all six Phase 2 reports (`10`–`15`).

**Read section by section (the parts in my focus):**
- `architecture/components.md`: §4.6–4.17 (ports), §7, §10 (all pseudocode), §11–§13.
- `architecture/state-machine.md`: §3.4–3.7 (PR, merge and global transitions), §8.3–8.6.
- `protocols/messages.md` (all). All 8 `protocols/schemas/output.*.schema.json` files were read and machine-linted (see below).
- `operations/macos-service.md`: §3, §8, §9, §11.6, §16–17.
- `operations/recovery.md`: startup steps, failure catalogue FM-01…21, side-effect journal.
- `security/threat-model.md`: §5–§6.2, SEC-1xx/2xx/3xx/8xx/9xx, ASM-E-01…15, B-SEC/C-SEC items.
- My own `integrations/claude.md`, `codex.md`, `linear.md` and `github.md`.
- The discovery evidence in `02-discovery-agent-runtimes.md` (RT) and `02-discovery-platform.md` (DP).

**New evidence gathered for this review.** Each item is tagged with how it was established.
- **[V-src] Codex `codex-rs` at `rust-v0.162.1`:**
  - `codex-api/src/common.rs`: `create_text_param_for_request` sends `text.format = {type:"json_schema", strict:<output_schema_strict>, schema, name:"codex_output_schema"}`.
  - `core/src/client_common.rs`: `Prompt::default()` has `output_schema_strict: true`.
  - `exec/src/lib.rs`: `load_output_schema` passes the file **verbatim** (it only checks that the file parses as JSON). The `exec resume` branch also loads `--output-schema`. Resume builds `ThreadResumeParams` from the current config, including sandbox/permissions and cwd.
- **[V-doc] Claude Agent SDK structured outputs (code.claude.com, fetched 2026-10-12):**
  - The SDK *validates and re-prompts*.
  - Draft-07 only; "schemas that declare a newer version are rejected".
  - An invalid schema fails at startup (v2.1.205+).
  - `format` is not enforced.
  - `success` without `structured_output` must be treated as a failure.
  - A model fallback can retract an already-completed output and end with `error_max_structured_output_retries`.
- **[V-doc] Claude API structured-output limits (platform.claude.com):**
  - `minLength`/`maxLength`, `minimum`/`maximum`, and `minItems` > 1 are **not supported** (400).
  - Limits: 24 optional parameters and 16 union-typed parameters per request.
  - SDK helpers strip unsupported constraints and validate client-side.
  - These apply to ALT-B-1 (Messages API), not to the Agent SDK path.
- **[V-doc-src] GitHub docs source (`github/docs`, `src/github-apps/data/fpt-2022-11-28/server-to-server-permissions.json` and content pages). Permissions:**
  - `POST /pulls`: **pull_requests:write only**.
  - `PUT /pulls/{n}/merge`: **contents:write**.
  - `PUT …/reviews/{id}/dismissals`: pull_requests:write.
  - `PUT /pulls/{n}/update-branch`: pull_requests:write.
  - `POST /check-runs`: checks:write.
  - `POST /statuses/{sha}`: statuses:write.
  - `GET /rulesets` and `GET /rules/branches/{b}`: **metadata:read**.
  - `GET /branches/{b}/protection` and `GET /actions/permissions`: administration:read.
  - `GET /collaborators`: metadata:read.
- **[V-doc-src] GitHub docs source, behaviour:**
  - Ruleset "expected source" for a required check: "The app must be installed in the repository with the **`statuses:write`** permission, must have recently submitted a check run".
  - Deploy keys are bypass-eligible **only on GHES**.
  - "Deploy keys with write access can perform the same actions as … a collaborator on a personal repository".
  - Unauthenticated REST limit: **60 requests/h per IP**.
  - An authorized `304` is free; `GET /rate_limit` does not count against the primary limit.
  - Secondary limits: 100 concurrent requests, 900 points/min per REST endpoint, 80 content-creating requests/min and 500/h.
  - App installation limit: 5,000/h, scaling to at most 12,500/h.
  - Auto-merge: "people with write permissions can configure" it.
- **[V-src] Linear SDK GraphQL schema (`linear/linear` master, `packages/sdk/src/schema.graphql`):**
  - `CommentCreateInput.id`: "The identifier in **UUID v4 format**".
  - Fields that exist: `Issue.delegate`, `User.app`, `Comment.botActor`/`externalUser`, `IssueHistory.actor/botActor/addedLabels/removedLabels/fromState/toState`, `IssueUpdateInput.addedLabelIds/removedLabelIds/stateId`, `AgentSession`, `Query.rateLimitStatus`.
  - `PaginationOrderBy` has no direction field.
  - No public diff-review or diff-merge mutation was found.
- **[I] Not reachable (DNS or proxy policy):** platform.openai.com, developers.openai.com and community.openai.com. The *keyword subset* of OpenAI strict structured outputs therefore rests on secondary sources, which conflict (see RB-01).

**Schema lint.** I wrote a script over the 8 output contracts. It checked:
- every object has `additionalProperties:false` and every property in `required`;
- union count, keyword inventory, `enum` without `type`, `minItems > 1`, and nesting depth.

Result:
- All 8 contracts pass the "all required + closed objects" rule.
- Keywords used: `pattern` (4–14 per file), `minLength`/`maxLength` (2–23 per file), `minimum`/`maximum` (Claude contracts), and `minItems: 8` (`code_review`, `plan_review` criteria).
- Every file has an `enum` with no `type`.
- Union-typed fields: 0–9 per file.
- Maximum depth: 5.

---

## 2 Summary verdict

**Mostly sound, with a cluster of contract gaps at the GitHub boundary, one Codex-schema risk that needs to be designed out now rather than discovered in Phase 0, and one cross-document contradiction (per-run vs per-task `CODEX_HOME`) that would break revision resume.** Every external call in C's pseudocode maps to a real REST/GraphQL operation with a permission the App can hold. However:

- The **GitHub gate mechanisms that B and E rely on** are missing from C's ports, effect catalogue and transition side effects:
  - the required `MERCURY / claude-review` check run, or E's `mercury/policy` and `mercury/claude-review` statuses;
  - my own permission table cannot make the App the ruleset's expected source.
- **Bot `REQUEST_CHANGES`** is designed in by A, C, D, E and F, but contradicts B's GH-2. It can leave PRs blocked because the design forbids both APPROVE and dismissal.
- **G-SPLIT is half-verified.** An App without `contents` can open PRs, according to the docs data. But a write deploy key may still be able to merge **by pushing the approved head to `main`**, and the App may be able to enable auto-merge. Neither has been ruled out.
- **Some dedup keys are edge-triggered**, e.g. `head:<sha>` and `rel:<a>:<b>:<present>`, so A→B→A sequences are lost.
- **Unauthenticated connectivity probes** in C exceed GitHub's 60/h per-IP limit.

**Counts:**

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 8 |
| Medium | 15 |
| Low | 4 |
| **Total** | **27** |

---

## 3 Findings

| ID | Sev | Type | Location(s) | Finding | Recommended resolution | Owner |
|---|---|---|---|---|---|---|
| RB-01 | High | unverifiable-assumption | `protocols/schemas/output.codex_plan.schema.json`, `output.codex_implementation.schema.json`; messages §5 ("bounded strings and arrays… satisfies OpenAI strict mode"); C ASM-C-07 | Codex sends the contract **verbatim** with `strict: true` [V-src]. The OpenAI server therefore enforces its strict-mode subset. The contracts satisfy the structural rules (closed objects, all fields required, nullable through type arrays). But `codex_plan` uses 22 `minLength` and 23 `maxLength` keywords, and both contracts use `enum` without `type`. Whether strict mode accepts `minLength`/`maxLength` (and an untyped `enum`) is **unverified and contested** in the reachable sources. An unsupported keyword gives a request-time 400, which fails **every** Codex run of that kind. | Design it out now. **(1)** Define a *wire copy* per contract, generated in CI from the canonical file. It strips `$schema`, `$id`, `minLength`, `maxLength`, `minimum`, `maximum` and any `minItems`/`maxItems` that a Phase 0 probe rejects. It adds an explicit `type` beside every `enum` and moves stripped bounds into `description` text. **(2)** Keep the full canonical schema for Ajv V2 validation, the same pattern the Anthropic SDK helpers use. **(3)** Record `schema_sha256` of the wire bytes (already in messages §5). **(4)** Add a Phase 0 / CT test that sends each wire schema to the pinned Codex with a trivial prompt. **(5)** Classify an `invalid_json_schema` 400 as `config_fatal`, not a retryable failure (codex.md §11 failure table). | C (schemas, CI), B (codex.md failure table) |
| RB-02 | Medium | unverifiable-assumption | `output.code_review/plan_review/security_review/task_authorization_decision/triage_proposal`; claude.md ALT-B-1 | The Agent SDK path validates client-side and re-prompts, so `minItems: 8`, `minLength` and `minimum` are fine there [V-doc]. But B's documented escape hatch ALT-B-1 (Messages API structured outputs) **rejects** `minLength`/`maxLength`, `minimum`/`maximum` and `minItems` > 1 with a 400. It also caps union-typed parameters at 16 and optional parameters at 24 per request. `code_review` alone has 7 unions. | Use the same wire-copy generator as RB-01 for an ALT-B-1 profile. State in claude.md §2 that ALT-B-1 needs SDK-style schema transformation, with full constraints enforced only by Ajv V2. | B |
| RB-03 | High | contradiction | components §4.11 `createReview(event: "COMMENT" \| "REQUEST_CHANGES")`, §10.5 T25 outbox `github.review.post(REQUEST_CHANGES)`; SM T25; threat-model AC-02, SEC-102 / B-SEC-3, §6.2; ADR-008 item 8; FR-162; TC-SBX-003; recovery.md journal vs github.md GH-2, claude.md CL-5 | Everyone except B allows the App to post `REQUEST_CHANGES`. Under the required-review rules, a "changes requested" review from a write-capable reviewer keeps the PR unmergeable until that reviewer approves or the review is dismissed. The design (correctly) has **no APPROVE and no dismiss path** (components §4.11 I9). After a revise cycle passes, the stale bot `REQUEST_CHANGES` therefore remains: the operator must dismiss it by hand on every such PR, or the merge stays blocked. Whether App reviews count as "write-capable" is unverified. Under G-SPLIT the App has `contents:read`, which makes the behaviour differ by mode. | Adopt GH-2 everywhere: Claude verdicts post only as `COMMENT` reviews. The **gate** is the required check run (RB-04). Remove `REQUEST_CHANGES` from the port type, the T25 effects, SEC-102, FR-162 and TC-SBX-003. Add a sandbox test that proves the App's `COMMENT` review never blocks the merge box. | C, E, F, A (ADR-008) |
| RB-04 | High | missing-requirement | components §4.11 (no check-run or status method), §4.14 effect catalogue, §10.5, SM T22/T24/T25/T26; threat-model SEC-100/308/309/310/904 (`mercury/policy`, `mercury/claude-review` statuses); github.md §6/§9.1 (`MERCURY / claude-review` check run) | The required MERCURY gate that both B and E rely on for **software-enforced review ordering and escalation blocking** has no interface. There is no `createCheckRun`/`updateCheckRun`/`createStatus` in `GitHubPort`, no `github.check.*` effect, and no transition that emits it. B and E also disagree on the mechanism (Checks API check run vs commit status) and the names (`MERCURY / claude-review` vs `mercury/claude-review`, plus E's separate `mercury/policy`). As written: if the rulesets require these contexts, every PR is unmergeable; if they do not, the claimed enforcement does not exist. | **(1)** Choose **check runs** for both gates: `MERCURY / claude-review` and `MERCURY / policy`. Check runs carry `external_id` for idempotent lookup, `output` text, and `action_required`. **(2)** Add `createCheckRun`/`updateCheckRun` to `GitHubPort`, and effects `github.check.upsert` (idempotency: `GET /commits/{sha}/check-runs?check_name=` plus `external_id = <task_id>:<head_sha>:<gate>`). **(3)** Emit `in_progress` at claim, then `success` at T24 and `failure` at T25/T26, all on `head_sha`. Emit `MERCURY / policy` from SEC-309 pre-checks before review; it stays `failure` until operator ack. **(4)** Exclude MERCURY's own contexts from T22's "all required checks concluded" wait. Otherwise T22 waits on a check that is only set after T24 (deadlock). | C (ports/SM), E (rename), B (github.md) |
| RB-05 | High | infeasible (self) | github.md §2.1 (Commit statuses **read**), §9.1 ruleset JSON (`integration_id: 0`); threat-model TH-50, SEC-100 | GitHub docs state the expected-source App "must be installed … with the `statuses:write` permission, must have recently submitted a check run". B's App has `statuses:read`, so it **cannot be pinned** as the source of `MERCURY / claude-review`. Then any write identity (including a workflow's `GITHUB_TOKEN`) can forge the gate (TH-50). | Add `statuses:write` to the App permission set (§2.1) and to the narrowed `check` token. Keep checks:write. Replace `integration_id: 0` with "the App ID, captured after first check run" in the onboarding runbook. Add a doctor/drift check that the ruleset's `integration_id` equals the App's ID. | B |
| RB-06 | High | unverifiable-assumption / security | threat-model §6.2 G-SPLIT, SEC-109, ASM-E-01/02/07, L4 | Docs data now **confirms** that `POST /pulls` needs only `pull_requests:write`, and that merge needs `contents:write` (half of ASM-E-02 verified). Deploy keys cannot be bypass actors on github.com, so rulesets apply to them. Two paths could still let a MERCURY credential cause a merge without the human clicking merge. **(a)** A write deploy key "can perform the same actions as a collaborator" over git. Whether GitHub accepts a *push* of an approved, all-green PR head to `main` under a "require PR" rule (a local-merge path) is untested. **(b)** Auto-merge can be configured by "people with write permissions". Whether an App with `pull_requests:write` and no `contents` can call `enablePullRequestAutoMerge` is untested (B's ASM-B-53). If either works, G-SPLIT is no stronger than G-DETECT. | Add to ASM-E-01/02 and SEC-T-12: (i) after the human approves, attempt `git push <deploy-key> <head>:main` (expect rejection); (ii) the App calls `enablePullRequestAutoMerge` (expect FORBIDDEN). Require repo setting `allow_auto_merge=false` under every mode, read by the drift monitor. Keep G-SPLIT "conditional" until both pass. Note that G-SPLIT needs one deploy key **per repo** (keys cannot be reused), with SSH transport and a non-expiring credential (SEC-504 rotation applies). | E, B |
| RB-07 | High | contradiction | macos-service §9 ("`runs/<run_id>/codex_home/` is a per-run `CODEX_HOME` … deleted with the run directory"), E6 vs codex.md §5, components §9.1 (`codex-home/<task_id>`), C report | Plan and implementation revisions use `codex exec resume <thread_id>` (codex.md §3, C T12/T28). Codex resolves the thread from `CODEX_HOME` state. A per-run home that is deleted with the run means **every resume fails** (or the design silently degrades to fresh threads). That breaks the "revision resumes the thread" contract and wastes tokens. | Per-task `CODEX_HOME` (B/C), retained until task archive. Concurrency safety comes from "one Codex run per task" (I2), not from per-run homes. D updates §9 and E6 (parallel runs = two *tasks*). | D |
| RB-08 | High | missing-requirement | components §8 / ProcessSupervisor, §4.6 `spawnClaudeCodeProcess`; macos-service §3; threat-model SEC-201; codex.md env table (`HOME` = operator home) | If SEC-201 (separate agent uid) is adopted, several interface assumptions break: **(1)** `kill(-pgid)` and `kill(pid,0)` from the coordinator uid return `EPERM` for agent-uid processes. Probe and kill need a privileged broker, and EPERM must read as "alive", not "dead". **(2)** `sudo` resets the environment, so `ANTHROPIC_API_KEY`/`CODEX_API_KEY` delivery needs `apiKeyHelper`, an fd or a broker. **(3)** Files written by the agent uid in worktrees must be committable by the coordinator uid (group mode, `safe.directory`). **(4)** Codex needs a real `HOME` with toolchains (ASM-B-15), which must be the agent's home, not the operator's. **(5)** SDK `spawnClaudeCodeProcess` must call the broker. None of this is specified. | Introduce a `LaunchBroker` port now (spawn-as, signal-group, probe), with an in-process implementation for same-uid and a root-owned broker for SEC-201. Add Phase 0 tests for EPERM probe semantics and env delivery. Update codex.md §6 (`HOME`) to "agent home". | D (broker), C (port), B (env tables), E |
| RB-09 | High | ambiguous-contract | SM T22/T24, github.md §5 (draft until Claude passes) | MERCURY opens PRs as **draft** and un-drafts only after Claude passes (T24). T22 requires CI on the head before Claude review. Many repos' workflows skip drafts (`if: !github.event.pull_request.draft`, or `types: [ready_for_review]`). Then CI never runs, T22 waits until `ci_wait_minutes` (90) and proceeds `timed_out`. Merge-verification check M6/check4 later depends on CI that only runs after un-draft. Result: a 90-minute delay on every task, and Claude reviews without CI evidence. | Repo onboarding check (doctor / `mercury repo add`): the required checks must trigger on draft `pull_request` events (inspect workflow `on:` and `if:`). If not, the repo policy uses `open_as_draft=false`, and the PR stays un-requested (no reviewer request) until T24. Record the choice in repo config. | B, C |
| RB-10 | Medium | infeasible | components §10.10 (`probe(api.github.com, api.linear.app)` HEAD every 30 s); macos-service §8.5 (HEAD `…/zen`-style probes) | Unauthenticated GitHub requests count against **60/h per IP** [V-doc-src]. C's 30 s probe is 120/h, which exceeds the limit. It would also starve the operator's own unauthenticated tools on the same IP, and `/zen` is itself rate-limited. | Use **passive** liveness: the last successful authenticated poll. When an active probe is needed, use an authenticated `GET /rate_limit`, which does not count against the primary limit, or a TLS connect without an HTTP request. Linear: a `rateLimitStatus` query, or rely on the poll. | C, D |
| RB-11 | Medium | ambiguous-contract | components §4.13 dedup keys `pr:<repo>#<n>:head:<sha>`, `rel:<a>:<b>:<present>`, `review:<id>`; SM G5 `--reset` | Facts keyed only by value are **edge-lossy**. **Head:** A → B (foreign) → A (operator `--reset` pushes A back) drops the second `head:A`, so `pull_requests.head_sha` stays B and the task can stay blocked or fail guards. **Relation:** a blocker removed and re-added (`present=true` twice) is dropped. **Review:** dismissal changes the state under the same `review:<id>`. | Key observation facts by **source version**: `pr:<repo>#<n>:upd:<pull.updated_at>:<head>`, the Linear relation `id` (re-adds get new ids) plus present, and `review:<id>:<state>`. Better still, have pollers write **level** snapshots (current head, current relations) that the InboxProcessor diffs against stored state, and keep edge facts for audit only. | C |
| RB-12 | Medium | contradiction | components §4.13 (`issue:<id>:<updatedAt>`, overlap 2 min, table `events_inbox`); linear.md §3.2 (`ln:issue:<uuid>:<updatedAt>`, overlap 5 min, table `inbound_events`); github.md §13 key catalogue (`gh:check:…:<check_run_id>:<conclusion>` vs C `ci:<repo>@<sha>:<digest>`); recovery.md FM-14 `(source, entity_id, version)` and 10-min rewind | Three dedup-key schemes, three overlap windows, and two table names for the same inbox. Implementers will diverge, and "same fact → same key" (messages §4) fails across code paths. | One registry in messages §4 (C owns). B's github.md §13 and linear.md §3.2 reference it. Overlap: 5 min steady state, 10 min after restart or wake. Table name: `events_inbox`. | C, B, D |
| RB-13 | Medium | unverifiable-assumption | components §4.12, §10.7 (`id = UUIDv5(namespace, key)`); ASM-C-18, ASM-B-37 | Linear documents `CommentCreateInput.id` as "UUID **v4** format". A v5 UUID may be rejected by validation. Duplicate-id behaviour (a recognisable "already exists" error) is still unverified. | Derive a **deterministic v4-shaped** UUID: hash(key) → 16 bytes, then set the version nibble to 4 and the RFC 4122 variant bits. Keep the body marker plus `findCommentByMarker` as the fallback idempotency path. Add an integration test for duplicate-id behaviour. | C |
| RB-14 | Medium | contradiction | components §10.8 (`linear.issue.set_state(Done)` always), SM T34 vs linear.md §6 (default: GitHub integration owns In Review/Done; MERCURY comments only), OQ-B-06 / OD-06 | C always writes Done. In B's default mode the integration writes it too (branch names carry the issue ID), so there are two writers. That is harmless by set-to semantics, but it violates "single writer per transition" and can set Done on a PR that MERCURY found unverified if ordering differs. F's OD-06 recommends (b), which is MERCURY-owned Done. | Make the projection effect conditional on `linear.status_mode ∈ {integration_owns_done, mercury_owns_all}`. T34 then waits for "Done observed **or** set", per mode. In `mercury_owns_all`, branch names drop the issue ID and PR bodies use contributing (non-closing) phrasing. Operator decides (OD-06). | C, B, Operator |
| RB-15 | Medium | missing-requirement | github.md §2.1 (Issues: none); macos-service §11.6 (heartbeat issue edits, ops-alert issue comments need `issues:write`); threat-model anchor repo (`contents:write` on anchor repo) | D's watchdog and ops alerts and E's audit anchor need App capabilities that B's permission table does not grant. These are separate repositories with different blast radius. | Add a per-repo permission matrix to github.md: target repos (as §2.1 plus statuses:write); `project-mercury` (`issues:write`); private anchor repo (`contents:write`). All tokens are narrowed per repo at mint. Alternatively, a second App for ops and anchors (aligns with SEC-110). | B |
| RB-16 | Medium | other (positive correction) | threat-model SEC-108, ASM-E-03; github.md ASM-B-51 | Docs data: `GET /repos/{o}/{r}/rulesets` and `/rules/branches/{b}` need only **metadata:read**. Classic branch protection and Actions settings need administration:read. SEC-108 drift monitoring is therefore achievable without an admin-read credential **if governance uses rulesets, not classic protection**. Unverified: whether `bypass_actors` is returned to a metadata-only reader. | Mandate rulesets, not classic protection, for MERCURY-managed repos. Drift monitor: rulesets, collaborators (metadata:read), CODEOWNERS blob, and the App's own installation permissions (App JWT). Actions settings remain a POL / periodic manual check unless ASM-E-03 is satisfied. Add a test that `bypass_actors` is visible. | E, B |
| RB-17 | Medium | ambiguous-contract | components §13 `required_checks` (static config) vs SM §8.5 check4; github.md M6 | The required-check set comes from hand config, while GitHub's truth is the ruleset. Drift means MERCURY passes T22 on checks GitHub does not require, or waits on ones it does not run. | Derive required contexts from `GET /rules/branches/{base}` (metadata:read) at each T22/T34 evaluation. Treat config as an *expected* list compared by the drift monitor. Exclude MERCURY's own contexts (RB-04). | C |
| RB-18 | Medium | unverifiable-assumption | claude.md §2.1 (`canUseTool` deny-all, `tools: []`), components §4.6 | The SDK produces structured output through its own mechanism (validate and re-prompt). Whether a deny-all `canUseTool`, `tools: []` or `disallowedTools` patterns interfere with that internal step is undocumented. If they do, every decision run fails with `error_max_structured_output_retries`. | Phase 0 / CT: run each decision type with the exact isolation profile and a minimal prompt, and assert `success` plus `structured_output`. In the `canUseTool` allow-path, document any internal tool name that must be allowed. | B |
| RB-19 | Medium | missing-requirement | claude.md §6 V1, components §4.6 `DecisionResult` | The SDK documents that a **model fallback** can retract a completed output, and a fallback model may silently change which model made an authority decision. The audit records `usage` but not the model actually used. | Set no `fallbackModel` for authority decisions (authorization, plan review, PR/security review); classify a fallback as `output_invalid` and retry. Record the result's per-model usage (actual model ids) in `runs` and in the authorization/review rows. | B, C |
| RB-20 | Medium | ambiguous-contract | threat-model SEC-100 (require conversation resolution, SHOULD); github.md §6 (inline `COMMENT` review comments); OQ-B-08 | If conversation resolution is required, every inline comment from Claude creates a thread that **the human must resolve** before merging. That is toil on each PR, and the design has no `resolveReviewThread` capability. | Either do not require conversation resolution, or post Claude's findings as the review **body** only (no inline threads) in that mode. Decide in OQ-B-08 / SEC-100. | E, B, Operator |
| RB-21 | Medium | unverifiable-assumption | components §4.13 polling cadence; github.md §7 (30 s for 10 min, then 60 s); F ASM-F-01 (≤ 20 % budget) | Worst case without 304s: 4 active PRs × 3 endpoints × 120/h ≈ 1,440/h, plus reviews and merge verification. That is **29 %** of the 5,000/h installation limit, above F's 20 % target. ETags make most polls free [V-doc-src], but each hourly token re-mint (and each narrowed per-purpose token) may invalidate cached ETags, if the server varies on `Authorization`. | Use one long-lived `read`-purpose token per installation for all polling. Apply B's tapered cadence (30 s → 60 s, and 300 s in AWAITING_HUMAN after 1 h). Measure in M2 the 304 ratio across token rotations (TC-PERF). Budget: ≤ 1,000 non-304 requests/h. | B, C |
| RB-22 | Medium | contradiction | components §4.6 `DecisionKind` incl. `revision_request` + messages vs C report "verbatim rendering" (§10.4/10.5 `renderVerbatim`) vs claude.md §3 | See known disagreement 7 (§4). Interface consequence: `mercury.revision.request.v1` has two producers with different provenance (Claude run vs coordinator rendering of Claude text). | Add `producer.kind` and `source_review_ids[]` plus `source_sha256s[]` to the revision message. A rendering must quote only fields from reviews whose hashes are bound. | C |
| RB-23 | Medium | ambiguous-contract | components §10.7 `github.pr.upsert` (`findPullByHead`); §4.11 | `findPullByHead` must use `GET /pulls?head=<owner>:<branch>&state=all`. Otherwise a closed MERCURY PR is invisible, and a second PR is created. A human editing the PR body can remove the `mercury:task` marker, which flips a legitimate PR to "foreign → dead". | Specify `state=all` and the `owner:` prefix. Identify ownership by **author = App bot plus head branch**, not by the body marker alone; the marker is a secondary check. A closed MERCURY PR goes to SM G6 logic, not to a new create. | C |
| RB-24 | Low | other | components §4.11 (absent `update-branch`), SM T23 conflicts | `PUT /pulls/{n}/update-branch` needs only pull_requests:write [V-doc-src]. It is a server-side push to the head that would look like a foreign push. The design correctly omits it, but the endpoint allowlist (SEC-102) should name it explicitly as forbidden, because it also exists under G-SPLIT. | Add to the SEC-102 deny list and the port's "intentionally absent" comment. | E, C |
| RB-25 | Low | other | linear.md ASM-B-32/33/34/38/39; threat-model TH-61 / ASM-E-05 | Verified against the Linear SDK schema: `Issue.delegate`, `User.app`, `Comment.botActor`, `IssueHistory` actor/label/state fields, `IssueUpdateInput.addedLabelIds`, `AgentSession`. No diff-review or merge mutation exists in the public schema, so E's "merge as human" path is exposed through the Linear MCP or app, not the documented API. ASM-B-35 (sort direction) remains open: `PaginationOrderBy` has no direction. | Mark these ASMs [V-src] in linear.md. In TH-61, test the MCP tools and the Linear UI path, not GraphQL. Keep the descending-order fallback. | B, E |
| RB-26 | Low | other | codex.md ASM-B-10, C ASM-C-09 | `exec resume` loads `--output-schema` and builds resume params from current config (sandbox or permissions, cwd) [V-src 0.162.1]. Flag acceptance is therefore verified at source level. Runtime behaviour (sandbox actually re-applied) still needs Phase 0. | Downgrade ASM-B-10 to "runtime check only". Pass `--cd <same worktree>` on resume, because cwd comes from config. | B |
| RB-27 | Low | contradiction (self) | claude.md §3.2/§11 paths, schema ids (`mercury.triage_proposal.v1`, `codex-plan.v1.schema.json`) vs messages §7 mapping | B's documents use pre-alignment schema ids, file names and checkout paths. messages §7 maps them, but two names for one contract invites drift. | B adopts C's ids and file names verbatim and the Phase 4 path decision (§4, item 4). | B |

---

## 4 Positions on the known disagreements

1. **BLOCKED with auto-resume (A) vs holds (C).** **Recommend C's holds.**
   - From the integration side, spec edits, Linear deprioritisation and new blockers are high-frequency, externally caused and self-resolving. Modelling them as `BLOCKED` would fire notifications on routine Linear edits, which repeats the Slack noise problem.
   - Condition: a hold that persists longer than a timer (e.g. `spec_changed` with no re-authorization within 24 h) must escalate to `BLOCKED(needs_human_decision)` with one notification. A gets visibility; C keeps the table small.
2. **`jobs` table (A) vs derived queue (C).** **Recommend C.**
   - External effects already have their own durable queue: the outbox with leases.
   - Runs have leases and fencing tokens.
   - A third queue adds a divergence surface without new semantics.
3. **HMAC optional (A, C) vs required (E); anchoring table missing.**
   - **Hash chain plus off-host anchor: required.** C must add the `anchors` table. Anchor writes go through a narrowed token for a private anchor repo (RB-15).
   - **HMAC: optional until SEC-201 exists.** With same-uid agents the key is readable by whoever can forge rows. With a separate agent uid, HMAC becomes meaningful against agents and should become required at that point. The `record_mac` column stays.
4. **Paths.** I withdraw B's `~/Library/Application Support/Mercury/checkouts/…` for checkouts.
   - State (DB, artifacts, runs, Claude config): `~/Library/Application Support/Mercury/`. No builds run there, and the socket path stays under 104 bytes.
   - All git working directories (mirrors, task worktrees, reference and review checkouts, per-task `CODEX_HOME`): one space-free root.
   - I prefer D's `~/Library/Mercury/`. It keeps everything under `~/Library` (not synced, not TCC-protected, not cluttering `$HOME`); C's `~/MercuryWork` is equivalent.
   - D owns `MERCURY_HOME` and `MERCURY_WORK`. Under SEC-201 the work root must be group-accessible to the agent uid, so it cannot be inside the operator's 0700 trees.
5. **Separate agent uid (E SEC-201 MUST) vs same-user process groups (C, D).** **Recommend E's target with a staged interface:**
   - Add a `LaunchBroker` port now (RB-08), so same-uid and separate-uid are two implementations rather than a redesign.
   - Same-uid plus deny-read profiles is allowed only for sandbox and M1–M4 with fakes or sandbox repos.
   - A separate uid is required before any real target repo with operator credentials on disk (M5 gate).
   - Reason: B's own R-B-01 (secret into the diff) and E's R-03 are only structurally solved by the OS.
6. **Merge governance (A G-1/G-2; E G-ORG/G-SPLIT/G-DETECT; B detect-after).** These are the same axis with different names: G-1 = G-DETECT and G-2 = G-ORG. **Recommend:**
   - G-ORG as the target before unattended operation.
   - G-DETECT plus the required `MERCURY / claude-review` check (corrected per RB-04/RB-05) for MVP.
   - G-SPLIT only if RB-06's two tests pass.
   - The docs data confirms that the PR-opening half of G-SPLIT works. The merge-by-git-push and auto-merge paths are the open risks.
   - One ADR (A) with E's three names.
7. **`revision_request` as a separate Claude decision (B) vs verbatim forwarding (C).** **Accept C, with conditions:**
   - When the source is one or two Claude reviews bound to the current head, forwarding their `required_change` text verbatim is still Claude's decision and saves a run.
   - A Claude `revision_request` run is kept for CI failures, test failures, merge conflicts, human review comments, and cases where the code and security reviews' required changes **conflict** or one review says `needs_plan_change`.
   - The message must carry provenance (RB-22).
8. **Linear status ownership.** This is an operator decision (OD-06 / OQ-B-06). The **interface** must support both modes (RB-14):
   - **Default `integration_owns_done`.** Zero conflict with the existing Linear GitHub integration and branch convention; MERCURY writes only `In Progress` and comments. A's question "who closes" is then answered: the integration closes, and MERCURY verifies and comments.
   - **`mercury_owns_all`.** If the operator wants "Done = verified", choose this mode. It requires branch names without the issue ID and non-closing PR phrasing.
   - F's recommendation (b) is valid but has that prerequisite.
9. **Requirement ID schemes.** F owns IDs (brief rule). A's NFR-xxx, D's REL-xx and E's SEC-xxx map into F's bands (SEC into F's reserved SEC range or kept as E's own namespace, cross-referenced). ADR-P01…P15 map to A's ADR-001…012 in a table in traceability. B's ASM-B/OQ-B ids are local and should not become requirement ids.
10. **Re-attach vs re-run after crash.** C and D agree in substance:
    - Codex and test runs are adopted when their identity matches.
    - Claude SDK runs (pipes) are killed and re-run.
    - The remaining difference is D's shutdown default ("interrupt Codex on SIGTERM unless `--keep-runs`"), which is a safe default.
    - Interface addition: under SEC-201, adoption probes go through the broker (EPERM ≠ dead, RB-08).
    - Claude runs could become adoptable through the CLI fallback with file stdio. This is not worth it; decision runs are cheap.
11. **DISCOVERED removed as a task state (C).** **Agree.**
    - Keep a `linear_issues` row with eligibility and triage status so the audit can answer "which Linear issue started the task".
    - Creating tasks without authority would contradict CON-004 and the "a Linear status change never starts work" invariant.
12. **MERGE_UNVERIFIED / integrity alert.** C's `BLOCKED(merge_verification_failed)` plus T35 (security notification) plus T40 (operator ack) covers B's `integrity_alert` and F's MERGE_UNVERIFIED. No new state is needed.
    - Requirement: the merge verification artifact records which checks failed.
    - `check5` (merged before Claude review) is distinguished in the notification text from `check1` (non-operator merger), because only the latter is a security incident.

---

## 5 Items needing operator decision

| # | Decision | Recommendation |
|---|---|---|
| OD-R1 | Governance mode for target repos (G-ORG / G-SPLIT / G-DETECT) | G-ORG before unattended mode; G-DETECT plus required claude-review check for MVP; G-SPLIT only after RB-06 tests |
| OD-R2 | Linear status mode (`integration_owns_done` vs `mercury_owns_all`) | `integration_owns_done` unless "Done = verified merge" matters more than the existing branch convention |
| OD-R3 | Require conversation resolution on protected branches | No, if Claude posts inline comments; otherwise body-only reviews (RB-20) |
| OD-R4 | Grant the App `statuses:write` and `issues:write` (on `project-mercury` only) | Yes (RB-05, RB-15) |
| OD-R5 | Allow auto-merge setting on target repos | Off (`allow_auto_merge=false`) in every mode (RB-06) |
| OD-R6 | Separate macOS agent user before the first real target repo | Yes (§4 item 5) |
| OD-R7 | Open PRs as draft when target CI skips drafts | Per-repo setting decided at onboarding (RB-09) |

---

## 6 Confidence

| Area | Confidence | Basis |
|---|---|---|
| Codex sends schemas verbatim with `strict:true` | High | Read in `rust-v0.162.1` source |
| Exact OpenAI strict keyword subset (`minLength`/`maxLength`, untyped `enum`) | **Low** | Official pages unreachable; secondary sources conflict. Hence RB-01 designs the risk out instead of asserting an answer |
| Claude SDK validation semantics; Messages API limits | High | Vendor docs fetched |
| GitHub App permission mapping (create PR, merge, statuses, rulesets) | High | GitHub docs data files |
| Expected-source needs `statuses:write` | High | Docs text; B's own table was wrong |
| Bot `REQUEST_CHANGES` blocking merge | Medium | Documented for write-capable reviewers; App specifics unverified, so it needs a sandbox test. The recommendation is safe either way |
| G-SPLIT merge-by-push and auto-merge loopholes | Medium-Low | Plausible from docs wording; untested |
| Linear schema field existence | High | SDK schema; runtime permission behaviour still unverified |
| Rate-limit arithmetic | Medium | Limits verified; ETag behaviour across token rotation unverified |
| Dedup edge-loss analysis | High | Follows directly from the key definitions |

---

## 7 Sources

- OpenAI Codex source, tag `rust-v0.162.1`: `codex-rs/codex-api/src/common.rs`, `codex-rs/core/src/client_common.rs`, `codex-rs/exec/src/lib.rs` (raw.githubusercontent.com/openai/codex).
- Claude Agent SDK, structured outputs: https://code.claude.com/docs/en/agent-sdk/structured-outputs
- Claude API, structured outputs (JSON Schema limitations, complexity limits, SDK transformation): https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- GitHub docs source (github/docs, `main`): `src/github-apps/data/fpt-2022-11-28/server-to-server-permissions.json`; `content/rest/using-the-rest-api/rate-limits-for-the-rest-api.md`; `best-practices-for-using-the-rest-api.md`; `data/reusables/rest-api/secondary-rate-limit-rest-graphql.md`, `primary-rate-limit-unauthenticated-users.md`, `primary-rate-limit-github-app-installations.md`; `managing-rulesets/available-rules-for-rulesets.md`; `data/reusables/repositories/rulesets-bypass-step.md`, `deploy-keys-write-access.md`; `managing-protected-branches/about-protected-branches.md`; `managing-auto-merge-for-pull-requests-in-your-repository.md`; `authentication/connecting-to-github-with-ssh/managing-deploy-keys.md`.
- Linear SDK schema: https://github.com/linear/linear/blob/master/packages/sdk/src/schema.graphql
- Secondary, used only to establish that the OpenAI keyword subset is contested: https://community.openai.com/t/structured-outputs-gets-nifty-improvements/1266968 ; https://community.openai.com/t/min-maxitems-are-not-supported-in-structured-output/958567 ; https://ractogateway.readthedocs.io/en/latest/_modules/ractogateway/adapters/_openai_schema.html
