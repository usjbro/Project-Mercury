# Agent B (Solutions Architect): Phase 2 Report

**Scope:** integration architecture for Claude, Codex, Linear and GitHub, plus the cross-cutting integration concerns.
**Detailed files:**
- [`integrations/claude.md`](../integrations/claude.md)
- [`integrations/codex.md`](../integrations/codex.md)
- [`integrations/linear.md`](../integrations/linear.md)
- [`integrations/github.md`](../integrations/github.md). Part B (§11–§18) holds the cross-cutting material: event strategy, Mermaid sequences, dedup keys, retry matrix, credential boundary, compatibility matrix and the authority table.

**Inputs used:**
- `00-brief.md` and `03-design-baseline.md`;
- the discovery files `01-discovery-integrations.md` (DI), `02-discovery-agent-runtimes.md` (RT) and `02-discovery-platform.md` (DP);
- Linear docs fetched through Linear's documentation search on 2026-10-12;
- a web search on Linear OAuth and rate limits.

Design only. No external writes were made.

---

## 1. Findings

1. **Commits must belong to the coordinator, not to Codex.** Codex's `workspace-write` sandbox protects `.git`, and a linked worktree writes into the main repo's `.git/worktrees/` (RT §3.2). Coordinator ownership also forces every change through deterministic gates: the diff guard, the secret scan and the L2 tests. Agents never hold GitHub credentials. This **disagrees with brief step 9** ("Codex … prepares a GitHub PR"). Codex prepares the *change*; the coordinator prepares the PR.
2. **The new exfiltration path is "secret into diff", not "secret over the network."**
   - Codex's Seatbelt profile allows broad reads (RT §2.5 and §3.2).
   - Codex commands can therefore read the operator's `~/.config/gh/hosts.yml` (an admin token) or `~/.ssh`, and write them into the worktree.
   - The coordinator would then push them to a **public** repo.
   - The mandatory software control is a secret scan plus the diff guard before commit (codex.md §9). Deny-read profiles are a second layer (ASM-B-14).
   - A dedicated macOS user is the strongest fix (OQ-B-05).
3. **Claude review ordering can be made software-enforced** with a required check run, `MERCURY / claude-review`, pinned to the App's integration ID (github.md §9.1). The human then cannot merge a head SHA that Claude has not passed. The cost: when MERCURY is down, its PRs cannot merge without a ruleset edit.
4. **Bot `REQUEST_CHANGES` is a trap.** It leaves a blocking review state that needs dismissal rights. Claude therefore posts `COMMENT` only, and the gate is carried by the check run (github.md §6).
5. **Linear branch-name links are closing links.** Linear's documentation notes that a branch named with an issue ID can cause the wrong ticket to close on merge. Keeping `jam-<n>` in MERCURY branch names therefore means the Linear GitHub integration owns `Done`. MERCURY can own `Done` only if branch names drop the ID (linear.md §6).
6. **"Human" in Linear is not provably human today.** Claude and Codex connectors write as the operator's own Linear user (DI). Linear signals must stay eligibility-only, and even the "label added by operator" check (E3) is weak until agents stop using that identity.
7. **Linear Coding sessions require a GitHub *organization* owner** to enable (Linear docs). On the current personal account they are effectively unavailable, which helps LN-6. Detection is still required (linear.md §9).
8. **Client-credentials OAuth gives a non-human Linear app actor without an interactive install**, according to Linear's docs as surfaced in search (30-day token, public teams) (ASM-B-30). This is the cleanest identity for MERCURY's Linear writes.
9. **Codex resume and sandbox interplay is unverified.** Implementation therefore deliberately starts a **fresh thread** containing only the approved plan text. This binds "what was implemented" to `plan_sha256` rather than to conversation memory (codex.md §3.3).
10. **Claude reviews must read a detached review checkout at the exact pushed SHA, never the live Codex worktree.** Otherwise "what Claude reviewed" is not provable (claude.md §3.2).

## 2. Recommended design (summary)

| Area | Recommendation | Detail |
|---|---|---|
| Claude invocation | Agent SDK (pinned) with an isolation profile: `settingSources: []`, no MCP, `disableAllHooks`, tools `[]` or Read/Grep/Glob, `permissionMode: dontAsk`, deny-all `canUseTool`, in-process realpath confinement hook, `outputFormat` schema, `maxTurns`/`maxBudgetUsd`, replaced `env`, isolated `CLAUDE_CONFIG_DIR`. Six decision types: triage, authorization, plan_review, pr_code_review, pr_security_review, revision_request. Nonce-delimited untrusted-content envelope. Four-stage validation (schema, Ajv, binding echo, semantic). `claude -p --bare` as fallback | claude.md |
| Codex invocation | Direct `codex exec --json --output-schema -o --strict-config --ignore-rules` subprocess. Read-only planning; plan revisions resume the planning thread; implementation is a fresh workspace-write thread with network off; implementation revisions resume that thread. Per-task `CODEX_HOME` with a generated config. Env allowlist plus `shell_environment_policy`. JSONL heartbeats and stall detection. Exit and JSONL classification table | codex.md |
| Tests | L1 Codex (advisory), **L2 coordinator sandboxed run (gating)**, L3 GitHub CI (gating). Test commands come from MERCURY's per-repo config, never from repo files. Dependency install is a separate coordinator step; Codex never gets network | codex.md §10 |
| Commits / push | Coordinator: diff guard → secret scan → commit as App bot with `Mercury-*` trailers → compare-and-set push with a narrowed App token via askpass | codex.md §9, github.md §4 |
| Linear | OAuth app actor via client credentials. 60 s `updatedAt` polling without label filter, 5 min overlap, 30 min reconciliation. Eligibility = label `mercury` (added by operator), Todo/Backlog, no `Not Speced`/hold, no delegate, parsable AC. `spec_hash` drift forces re-authorization. MERCURY owns → In Progress; the GitHub integration owns In Review and Done; MERCURY only comments. Comments are data only | linear.md |
| GitHub | GitHub App on selected repos with minimal permissions (no workflows, no admin). Per-purpose narrowed installation tokens. Branches `mercury/<issue>-<slug>`. Draft PR until both Claude reviews pass, then ready plus review request to the operator. `COMMENT` reviews plus a required check run. ETag polling. Seven-point merge verification. Ruleset JSON with code owners, last-push approval, stale dismissal, empty bypass and required checks | github.md Part A |
| Event strategy | Polling only. Webhook relays are excluded from v1 (hints only, if ever). Transactional inbox and outbox with dedup keys | github.md §11–§14 |
| Governance gap | Personal account: human approval is preventive, human merge is detective. Recommend an ADR for transferring to a free org, which gives a "Restrict updates" ruleset and makes merges preventive | github.md §10 |

## 3. Alternatives considered

| ID | Alternative | Disposition |
|---|---|---|
| ALT-B-1 | Claude via the Messages API with coordinator-implemented read tools (no Claude Code binary) | Strong isolation, more code to own. **Preferred escape hatch** if Agent SDK isolation semantics change |
| ALT-B-2 | `@openai/codex-sdk` instead of the raw CLI | Equivalent; rejected for argv audit and process-group ownership |
| ALT-B-3 | Codex commits itself (`writable_roots` += `.git/worktrees/<n>`) | Rejected: it weakens the sandbox and bypasses gates |
| ALT-B-4 | A separate token-broker process holding the GitHub App key | Optional hardening; adds IPC |
| ALT-B-5 | Commits through the Git Data API (Verified signatures) | Adopt if a signed-commit rule is wanted |
| ALT-B-6 | Linear status mode `mercury_owns_all` (contributing magic word, branch without issue ID) | Configurable; the default is integration-owned `Done` (OQ-B-06) |
| ALT-B-7 | Claude review as bot `REQUEST_CHANGES` / `APPROVE` | Rejected (finding 4, GH-1/GH-2) |
| ALT-B-8 | Webhooks via smee or a cloud relay | Rejected for v1 |
| ALT-B-9 | Machine-user GitHub account | Rejected: classic PAT, approvals count |
| ALT-B-10 | Implementation resumes the planning thread | Rejected (finding 9) |
| ALT-B-11 | Branch prefix `jamesmbrownjr/…` (the existing convention) | Rejected: it denotes the human |

**Baseline deviations:**
- Brief step 9 (see finding 1).
- `revision_request` is added as an explicit Claude decision type.
- I propose that Agent C add a sub-state or flag for "approved, awaiting merge" inside `AWAITING_HUMAN_APPROVAL`, and an `integrity_alert` flag on `MERGED`.
- No state renames.

## 4. Tradeoffs

| Choice | Benefit | Cost |
|---|---|---|
| Required `MERCURY / claude-review` check | Ordering is software-enforced | Operator blocked when MERCURY is down; needs a runbook procedure |
| Draft PR until Claude passes | Operator notified only when there is a decision to make | Linear "In Review" timing depends on team draft automation |
| Fresh implementation thread | Exact plan binding | Loses planning exploration context; more tokens |
| Polling only | No inbound exposure, simple | Detection latency of 1–3 min; small API cost |
| Integration owns Linear `Done` | Keeps existing behaviour and branch convention | `Done` ≠ verified merge; verification failures are comment-only |
| Coordinator L2 tests | Authoritative and independent of Codex claims | Runs untrusted code in a second sandbox that MERCURY must own |
| Opus 5.5 for all decision types | Consistent quality | Cost; the operator may downgrade triage |

## 5. Risks

| ID | Risk | L/I | Mitigation |
|---|---|---|---|
| R-B-01 | Codex reads operator credentials from disk and smuggles them via the diff into a public repo | M/Critical | Secret scan plus diff guard (mandatory), deny-read profile, dedicated macOS user (OQ-B-05), Phase 0 self-test 5 |
| R-B-02 | The App (`contents:write`) merges a PR on the personal account | L/High | GH-3 (no merge code), detective M2, auto-merge off, org transfer (OQ-B-09) |
| R-B-03 | Agents act as the human in Linear, weakening E3 and any human-actor signal | H/Medium | Linear is eligibility-only; operator stops agent connectors writing as the human |
| R-B-04 | Fast-moving CLIs (Codex 0.16x, Claude 2.1.x) change flags or semantics | H/High | Exact pins, startup self-tests, `--strict-config`, contract tests, no auto-update |
| R-B-05 | MERCURY down blocks merges because of the required check | M/Low | Runbook: the operator edits the ruleset temporarily (audited) |
| R-B-06 | Security findings published in PR reviews on a public repo | M/Medium | Withheld-finding mode (OQ-B-07) |
| R-B-07 | Linear GraphQL field assumptions (history, delegate, botActor) are wrong | M/Medium | Introspection in Phase 0; ASM-B-32 to ASM-B-39 |
| R-B-08 | Cost overrun from long reviews or retries | M/Medium | Per-run budgets, daily cap, workspace and project spend limits |
| R-B-09 | Two systems (MERCURY and the Linear integration) jointly define the Linear status a human sees | M/Low | Single writer per transition; MERCURY verifies and comments only |
| R-B-10 | Model API key readable by sandboxed commands through process listing | L/Medium | ASM-B-16 test; capped dedicated keys; rotation |

## 6. Assumptions (Phase 0 verification)

| ID | Assumption |
|---|---|
| ASM-B-01 | Agent SDK accepts a `settings` override (or extra args) to set `disableAllHooks:true` |
| ASM-B-02 | `persistSession` and transcripts land under `CLAUDE_CONFIG_DIR` |
| ASM-B-03 | CLI fallback permission rules (`Read(./**)` allow plus `dontAsk`) confine reads to cwd |
| ASM-B-04 | The SDK exposes a reasoning-effort option |
| ASM-B-05 | A custom `systemPrompt` (no preset) works correctly with built-in Read/Grep/Glob |
| ASM-B-06 | `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` is the current variable name |
| ASM-B-10 | `codex exec resume` accepts `--sandbox`, `--output-schema`, `-o` |
| ASM-B-11 | Config values (`web_search="disabled"` etc.) are valid in the pinned version |
| ASM-B-12 | `cli_auth_credentials_store="ephemeral"` works together with `CODEX_API_KEY` |
| ASM-B-13 | `shell_environment_policy.inherit="core"` and default `*KEY*` excludes behave as described |
| ASM-B-14 | Codex permission profiles support deny-read paths |
| ASM-B-15 | Codex needs the real `HOME` for toolchains |
| ASM-B-16 | Sandboxed commands cannot read the parent env through `ps` |
| ASM-B-17 | ChatGPT-login refresh rotates tokens, so copies diverge |
| ASM-B-18 | Auth cannot be shared across separate `CODEX_HOME`s |
| ASM-B-19 | `git commit` inside workspace-write in a linked worktree is denied |
| ASM-B-20 | A `codex sandbox macos -- <cmd>` style subcommand exists for L2 reuse |
| ASM-B-21 | Codex behaviour on `--output-schema` mismatch (exit code / output) |
| ASM-B-30 | Linear client-credentials grant yields a 30-day app-actor token for public teams |
| ASM-B-31 | `actor=app` versus `actor=application` parameter value |
| ASM-B-32 | `Issue.delegate` and `User.app` fields exist |
| ASM-B-33 | `Comment.botActor` and `externalUser` fields exist |
| ASM-B-34 | `IssueHistory` exposes actor, added/removed labels, and from/to state |
| ASM-B-35 | `orderBy: updatedAt` is descending |
| ASM-B-36 | Rate limiting surfaces as `RATELIMITED` and/or HTTP 429 |
| ASM-B-37 | `commentCreate` honours a client-supplied `id` idempotently |
| ASM-B-38 | `issueUpdate` accepts `addedLabelIds`/`removedLabelIds` |
| ASM-B-39 | Linear agent-session activity is detectable via the API |
| ASM-B-50 | GitHub rejects App pushes touching `.github/workflows/**` without the `workflows` permission |
| ASM-B-51 | `GET /rules/branches/{branch}` works with metadata read |
| ASM-B-52 | GitHub Actions integration ID is 15368 |
| ASM-B-53 | An App with `pull_requests:write` can enable auto-merge when the repo allows it |
| ASM-B-54 | An org "Restrict updates" ruleset blocks PR merges by non-bypass Apps |

## 7. Dependencies

- **Agent C (Staff Engineer):**
  - canonical schemas for the IDs referenced in claude.md §3 and §6.1 (`mercury.triage_proposal.v1`, `task_authorization_decision.v1`, `plan_review.v1`, `code_review.v1`, `security_review.v1`, `revision_request.v1`, `codex-plan.v1`, `codex-impl-result.v1`, `test_results.v1`, `implementation_progress.v1`);
  - `inbound_events`, `outbound_ops` and `agent_runs` tables;
  - states and flags for approved-awaiting-merge, `integrity_alert`, `BLOCKED` reasons (`spec_drift`, `foreign_agent`, `foreign_push`, `operator_hold`), and revision counters.
- **Agent D (DevOps/Platform):**
  - Keychain broker;
  - sleep-aware clock and connectivity gate;
  - process-group supervision and orphan sweep;
  - worktree and checkout paths and cleanup;
  - toolchain prefix for pinned binaries;
  - the runbook for "MERCURY down, operator needs to merge";
  - the dedicated-user question.
- **Agent E (Security):**
  - redaction filter;
  - secret-scan ruleset;
  - L2 sandbox profile;
  - withheld security findings policy;
  - decision on mandatory pause after an integrity alert;
  - managed-settings approval.
- **Agent A (Principal Architect):** ADRs for polling-only, coordinator-owned commits, the repo-ownership (org) decision, and Agent SDK versus Messages API.
- **Agent F (TPM):** Phase 0 checklist items from §6; a roadmap gate for org transfer before unattended mode.

## 8. Unresolved questions

| ID | Question | For |
|---|---|---|
| OQ-B-01 | Claude auth: Console API key (recommended) or subscription `setup-token`? | Operator |
| OQ-B-02 | Install root-owned Claude managed settings (this also affects interactive use)? | Operator, E |
| OQ-B-03 | Codex billing: API key (recommended) or ChatGPT plan (forces concurrency 1)? | Operator |
| OQ-B-04 | May dependency lifecycle scripts run during `deps_install` for specific repos? | Operator, E |
| OQ-B-05 | Run MERCURY under a dedicated macOS user without human credentials? | Operator, D, E |
| OQ-B-06 | Linear `Done` owner: integration (default) or MERCURY (branch names without issue ID)? | Operator |
| OQ-B-07 | Publish security findings on public PRs, or withhold them to the local report? | E, Operator |
| OQ-B-08 | Require review-thread resolution? | Operator |
| OQ-B-09 | Transfer target repos to a free GitHub org to make "human merges" preventive? | Operator, A |

## 9. Supporting evidence

- RT §2.1–§2.8 (Claude flags, SDK options, repo-content trust, auth); RT §3.1–§3.6 (Codex exec flags, JSONL, sandbox, `.git` protection, config keys, auth); RT §5 and §6 (preliminary mechanism, version risks).
- DP §1.1–§1.4 (rulesets, approvals, App permissions, personal-account gap); DP §2 (polling, ETags, merge verification recipe); DP §3 (Linear API, OAuth app actor, magic words, Coding sessions); DP §4.5 (Keychain, TCC).
- DI: JAM team states and labels, branch convention, agents writing as the human, Linear GitHub automation, Codex review bot, Slack failure patterns.
- Linear Docs (via Linear documentation search, 2026-10-12):
  - "Coding sessions": delegation starts Claude Code or Codex; triage automations; setup requires a GitHub org owner.
  - "Reviews": the `linear:extension` `onBehalfOf` block; approve and merge from Linear under the human's identity.
  - "GitLab": magic words, contributing words, branch-specific rules (same model as the GitHub integration).
  - "Jira": a branch named with an issue ID can close the issue on merge.
- Web search, 2026-10-12: Linear OAuth client-credentials grant (app actor, 30-day token) — https://linear.app/developers/oauth-2-0-authentication ; Linear rate limits (OAuth 5,000 req/h; API key 2,500 req/h; complexity budgets; numbers vary across doc versions) — https://linear.app/developers/rate-limiting . Both pages could not be fetched directly (DNS blocked); these are search excerpts only.

## 10. Confidence

| Recommendation | Confidence | Why |
|---|---|---|
| Coordinator owns commits, push and PR | High | Supported by sandbox facts and least privilege; gates need it |
| Claude via Agent SDK with the isolation profile | Medium-High | Options are documented (RT); several details unverified (ASM-B-01 to ASM-B-05). ALT-B-1 exists as an escape hatch |
| Nonce-delimited envelope plus four-stage validation | High | Deterministic, testable; does not rely on model obedience for authority |
| Codex invocation and per-task `CODEX_HOME` | Medium | Source-verified flags but nothing executed; resume semantics and config values unverified |
| L1/L2/L3 test layering | High (design) / Medium (L2 sandbox mechanics) | — |
| Linear app actor via client credentials | Medium | Docs surfaced only via search excerpt |
| Linear polling design and drift handling | Medium-High | Field names unverified (ASM-B-32 to ASM-B-39) |
| GitHub App permissions, ruleset and `COMMENT`-only reviews | High | Grounded in DP's vendor-doc verification |
| Required `MERCURY / claude-review` check | High | Standard GitHub feature; operational trade-off is explicit |
| Merge verification M1–M7 | High | REST fields verified in DP |
| Personal-account gap analysis and org recommendation | High (analysis) / Medium (ASM-B-54) | — |
