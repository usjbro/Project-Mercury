# Phase 4 Revision — Agent B (Solutions Architect): Disposition

Scope: `integrations/claude.md`, `integrations/codex.md`, `integrations/linear.md`, `integrations/github.md`. Implements RD-1, RD-5…RD-9, RD-11, RD-13…RD-18 and Addenda A/B of `reviews/30-reconciliation.md`. Aligned with the finished `operations/macos-service.md` (paths §7.1, parameter table §2, `agent-exec` grammar §3.5, credential inventory §9.1, env allowlist §9.4), ADR-013…020 and `security/threat-model.md` (SEC-101/102/110/113/114/507/905/906 etc.).

## 1. Summary of changes per document

**claude.md**
- Claude runs as `_mercuryagent`: SDK `spawnClaudeCodeProcess` → `sudo … agent-exec --run-dir`, spec `kind: claude`, key on fd 3, pipes kept; per-run `CLAUDE_CONFIG_DIR`; `claude` token table for `agent-exec` (B-owned). Fallback ALT-B-1 (Messages API, coordinator-implemented realpath-confined read tools over the snapshot, `anthropic-messages` wire profile). CLI `claude -p` fallback withdrawn.
- Claude reads only git-object snapshots (CL-7, ADR-017); inputs in `runs/<run_id>/in/`.
- Canonical decision list (no failure_triage), authorization modes `initial`/`reauthorize`, plan out-of-scope = `reject` + `scope_exceeded`, security review on every PR, hybrid revision-request table (RD-8, SEC-316).
- No `fallbackModel`; V1 model check; actual model ids recorded (CL-8).
- `allowedTools` + hook confinement; self-test is a hard gate run through the production path, incl. "programmatic hooks still fire" and OS canaries; binaries pinned in `agent.conf`.
- C's contract ids used verbatim; B's §6.1 field interface removed (schemas are the source); V4 rules referenced to messages §5.1; wire-copy profiles defined.
- Parameter values removed; deadline/stall cite `run.claude_<kind>.*`, kill ladder `supervisor.kill_ladder_s`; failure classes aligned to the unified vocabulary; Claude runs non-adoptable, re-run with the same `input_digest`; audit row in `runs`.

**codex.md**
- All Codex kinds via `agent-exec` (detached, file stdio, adoptable); B-owned Codex token table (§3.7); paths per D §7.1 (`worktrees/<owner>__<repo>/<issue-lower>-<ulid8>`, `codex-home/<task_id>`, `runs/<run_id>/{in,out,tmp}`), agent `HOME`, toolchains, `agent.gitconfig`.
- Per-task `CODEX_HOME`, config regenerated and byte-verified before every run; trust key from `WORK_ROOT`.
- `codex-strict` wire schemas; schema rejection = `config_fatal`.
- Resume only if the worktree was not reset; revisions start from `tasks.last_commit_sha`; `--cd` on resume.
- Liveness = stdout growth or group CPU (`agent-ctl stats`); stall ≥ `repo.test_timeout_min` while a command runs.
- Commit pipeline rewritten: git hardening, `.git` pointer verification, temporary index, plumbing commit in the mirror, CAS `update-ref`, durability order; block/escalate classes from SEC-310 incl. editor auto-run paths; SEC-312/403/404/502 checks.
- `verify` and `deps_install` as agent uid under root-owned Seatbelt profiles; no network for `verify`; lockfile installs only after `MERCURY / policy` acknowledgement.
- Failure mapping: `timeout` consumes run attempts only; `blocked`/`partial` → Claude path; `lost_by_host`; adoption with guard re-evaluation; single reset policy (C §9).

**linear.md**
- Two status modes (`integration_owns_done` default, `mercury_owns_all`) with per-mode tables; never write state after `MERGED` in default mode; Done never merge proof (LN-7).
- `spec_hash` single, precise definition (normalization, labels, exclusions), echoed as `spec_sha256`; spec drift = hold, results not acted on, re-authorization as a new version, PR-stage protection.
- Deterministic v4-shaped comment ids (algorithm given) with author-checked marker fallback.
- Eligibility changes mapped to holds (`deprioritized`, `operator_hold`, `spec_changed`), `DISCOVERED` as issue-level status; relation ids; [V-src] markings; token reach (ASM-B-64); magic-word neutralisation; SEC-805 write allowlist; parameter names from D §2.5/§2.7; Keychain names from D §9.1.

**github.md**
- Identities: `mercury-bot` (contents/pull_requests/checks write, metadata read, **statuses:read** per Addendum B, statuses:write only if Phase 0 requires); `mercury-ops` only on `project-mercury` and the anchor repo (see Objection 1); per-purpose token table.
- Gates: `MERCURY / claude-review` and `MERCURY / policy` lifecycle tables (SEC-113), external_id, update semantics, never `neutral`/`skipped`; COMMENT-only reviews; body-only mode if thread resolution required; SEC-507 publication policy; chain head in check output on private repos only (Addendum B).
- Draft policy (SEC-114) and onboarding checklist O1–O10 (CI on drafts, CODEOWNERS, rulesets only, pinned integration ids, `allow_auto_merge=false`, App permissions, toolchains).
- Required contexts from `/rules/branches`; operator input filtered by numeric id; base-moved via coordinator merge (T41); foreign push `--reset` as fast-forward tree-restoring commit; closed-PR routing.
- Merge verification M1–M8 with per-check scope (global `security_halt` / repo `integrity_alert` / policy notice); drift monitor incl. base-commit audit → global `security_halt`.
- Governance modes G-ORG/G-SPLIT/G-DETECT, G-SPLIT tests, endpoint allowlist with explicit forbidden list (SEC-102), updated ruleset JSON (rulesets only) and G-ORG snippet.
- Part B: authenticated ETag probe, wake rules, five current sequence diagrams (incl. spec drift), single dedup catalogue (§13) with observation sequence and `<cause>` for set-to outbound ops, polling budget recomputed (≤ 670/h worst case), single retry matrix (§15) with accounting table, circuit breakers and mutation budgets, credential boundary, compatibility matrix, authority table (17 states), Phase 0 register P0-201…P0-241.

## 2. Finding dispositions

| Finding | Source | Disposition | Where |
|---|---|---|---|
| RB-01 | 21 | fixed (B side: wire copy, `config_fatal`, P0-211); generator is C's | codex.md §3.6, §11 |
| RB-02 | 21 | fixed | claude.md §2.3, §6.1 |
| RB-03 | 21 | fixed (B); C/E/F own their docs | github.md GH-2, §6.3, §10.4 |
| RB-04 | 21 | fixed (op names, lifecycle, T22 exclusion) | github.md §6 |
| RB-05 | 21 | fixed (P0-235, integration id placeholder, drift check) | github.md §2.2, §9.1, §9.4 O4 |
| RB-06 | 21 | fixed (B side) | github.md §10.1–§10.2, §9.5 |
| RB-07 | 21 | fixed (B) | codex.md §5 |
| RB-08 | 21 | fixed (env tables, agent home, launcher use) | claude.md §2.2, §7.2; codex.md §3, §6 |
| RB-09 | 21 | fixed | github.md §5.2, §9.4 O1 |
| RB-10 | 21 | fixed | github.md §11.2 |
| RB-11 | 21 | fixed | github.md §13.2–§13.3; linear.md §3 |
| RB-12 | 21 | fixed (single catalogue, `events_inbox`, D overlap param) | github.md §13; linear.md §3.2 |
| RB-13 | 21 | fixed | linear.md §7.3 |
| RB-14 | 21 | fixed (B side) | linear.md §6 |
| RB-15 | 21 | fixed (second App) | github.md §2 |
| RB-16 | 21 | fixed (rulesets only, P0-231) | github.md §9, §9.6 |
| RB-17 | 21 | fixed | github.md §7.2 |
| RB-18 | 21 | fixed | claude.md §8 (P0-214) |
| RB-19 | 21 | fixed | claude.md §2.1, §6 V1, §11 |
| RB-20 | 21 | fixed (default off; body-only mode) | github.md §6.3, §9.1 |
| RB-21 | 21 | fixed | github.md §14 |
| RB-22 | 21 | fixed (B side; schema fields are C's) | claude.md §3.3 |
| RB-23 | 21 | fixed | github.md §5.1 |
| RB-24 | 21 | fixed | github.md §10.4 |
| RB-25 | 21 | fixed | linear.md §3.1, §9 |
| RB-26 | 21 | fixed | codex.md §3.2 |
| RB-27 | 21 | fixed (C ids/files verbatim; D paths) | all four |
| RA-01 | 20 | fixed (B: hash, PR effect) | linear.md §5, §8 |
| RA-03 | 20 | fixed (references D §7.1) | all four |
| RA-04 | 20 | fixed (B) | github.md §6.3 |
| RA-05 | 20 | fixed (B: triggers, approvals bind spec hash); output fields are C's | claude.md §3; linear.md §8 |
| RA-06 | 20 | fixed per RD-5/RD-6 (check runs, App permissions) | github.md §2, §6 |
| RA-07 | 20 | fixed per RD-6, with objection 1 | github.md §2.3 |
| RA-08 | 20 | fixed | codex.md §5 |
| RA-10 | 20 | fixed | linear.md §6 |
| RA-11 | 20 | fixed (B list) | claude.md §3 |
| RA-12 | 20 | fixed (no MCP) | claude.md §2.1, §2.4 |
| RA-13 | 20 | fixed | claude.md §3.2, CL-7 |
| RA-14 | 20 | fixed | claude.md §3 |
| RA-17 | 20 | fixed (C routing; single M-list in github.md §8) | github.md §7.7, §8 |
| RA-18 | 20 | fixed (scope per RD-14) | github.md §8 |
| RA-21 | 20 | fixed | claude.md §3; linear.md §4 |
| RA-27 | 20 | fixed (B side: channels per ADR-019) | github.md §10.3 |
| RA-28 | 20 | fixed (17 states) | github.md §18 |
| RA-29 | 20 | fixed | claude.md §3 |
| RA-35 | 20 | fixed (values in D §2.5) | linear.md §3; github.md §7.1 |
| RA-36 | 20 | consistent (A owns ADR-005) | codex.md §3.3 |
| RA-38 | 20 | n/a to B (orchestrator); design consistent | codex.md §1, §9 |
| RC-01 | 22 | fixed (B side) | github.md §6.3 |
| RC-02 | 22 | fixed (op names confirmed: `github.check.upsert`) | github.md §6 |
| RC-03 | 22 | fixed: one mechanism = check run `MERCURY / policy` | github.md §6.2 |
| RC-04 | 22 | fixed (no interrupt, no "mark superseded", no carry-forward field) | linear.md §8 |
| RC-05 | 22 | fixed | codex.md §5 |
| RC-06 | 22 | fixed (resume rule, `last_commit_sha`) | codex.md §3.4, §12.3 |
| RC-08 | 22 | fixed | github.md §15.1; codex.md §11 |
| RC-10 | 22 | fixed (C table names, reconcile-before-retry, 5xx/network never dead) | github.md §13.1, §15.1 |
| RC-11 | 22 | fixed (B confirms mode-dependent projection) | linear.md §6 |
| RC-12 | 22 | fixed (B side; T41 is C's) | github.md §7.5 |
| RC-13 | 22 | fixed | codex.md §11 |
| RC-16 | 22 | fixed (numeric ids, M-list canonical) | github.md §8 |
| RC-17 | 22 | consistent (B side) | github.md §8 |
| RC-21 | 22 | fixed (B uses SM hold names) | linear.md §4, §11; github.md §15 |
| RC-22 | 22 | fixed (B uses `runs`, `run_meta_json`) | claude.md §11 |
| RC-23 | 22 | fixed (holds; cancel as option) | linear.md §4 |
| RC-24 | 22 | fixed | claude.md §3.2 |
| RC-26 | 22 | fixed (B: per-source counters in SM §9) | github.md §7.4 |
| RC-30 | 22 | fixed (D layout) | all |
| RC-36 | 22 | fixed | github.md §5.1, §6.3 |
| RC-37 | 22 | fixed (values in D §2.3, behaviour in SM) | claude.md §3.1; codex.md §12.1 |
| RC-38 | 22 | fixed (no run while BLOCKED) | github.md §7.6 |
| RD-01 | 23 | fixed (B side) | claude.md §2.2; codex.md §3 |
| RD-02 | 23 | fixed | codex.md §10 |
| RD-04 | 23 | fixed | codex.md §12.3 |
| RD-08 | 23 | fixed via `mercury-ops` | github.md §2 |
| RD-09 | 23 | fixed | github.md §15 |
| RD-13 | 23 | fixed | codex.md §5 |
| RD-14 | 23 | fixed | all |
| RD-15 | 23 | fixed | codex.md §8 |
| RD-19 | 23 | fixed (read once, D inventory names) | claude.md §7; codex.md §7; linear.md §2; github.md §3 |
| RD-20 | 23 | fixed (askpass fd only) | github.md §3, §4.3 |
| RD-25 | 23 | fixed (SDK via agent-exec; ALT-B-1 fallback) | claude.md §2 |
| RD-26 | 23 | fixed (agent home, toolchains) | codex.md §6 |
| RE-09 | 24 | fixed per Addendum B (Linear comment; check summary private repos only) | linear.md §7.2; github.md §6.1 |
| RE-10 | 24 | fixed | github.md §2 |
| RE-12 | 24 | fixed (renderer rules referenced at every sink) | github.md §5.3; linear.md §7.2 |
| RE-13 | 24 | fixed (protected additions; quarantine is D's) | codex.md §9 |
| RE-14 | 24 | consistent (guard is C's; result-application check stated) | linear.md §8 |
| RE-15 | 24 | fixed | github.md §6.3 |
| RE-16 | 24 | fixed (M8; base-commit audit) | github.md §8, §9.6 |
| RE-17 | 24 | fixed (B side; cadence param, global halt, mutation budgets) | github.md §9.4–§9.6, §15.3 |
| RE-18 | 24 | fixed | claude.md §2.1, §7.3, §8; codex.md §13 |
| RE-19 | 24 | fixed | codex.md §5, §13 |
| RE-21 | 24 | fixed | claude.md §4; github.md §7.4 |
| RE-22 | 24 | fixed (P0-225; SEC-803 rule) | linear.md §2, §9 |
| RE-23 | 24 | fixed (B side) | codex.md §4, §8, §9 |
| RE-25 | 24 | fixed (B side: which checks set `security_halt`) | github.md §8, §9.6 |
| RE-28 | 24 | fixed | github.md §7.6 |
| RE-29 | 24 | fixed (B side: verify profile denies securityd; profile is E/D) | codex.md §10 |
| RF-01 | 25 | fixed (B side) | claude.md §2.2; codex.md §3 |
| RF-05 | 25 | fixed | claude.md §3.2 |
| RF-06 | 25 | fixed | codex.md §5 |
| RF-07 | 25 | fixed | github.md §6.2, §9.1 |
| RF-08 | 25 | fixed (both modes, branch naming per mode) | linear.md §6; github.md §4.1 |
| RF-10 | 25 | fixed (anchor via `mercury-ops`) | github.md §2.3, §2.4 |
| RF-11 | 25 | fixed (no administration:read anywhere; Actions settings POL) | github.md §2, §9.4 O9, §9.6 |
| RF-13 | 25 | consistent | claude.md §3 |
| RF-21 | 25 | deferred (C owns matrix); B channel usage stated | github.md §10.3 |
| RF-28 | 25 | fixed (superset, full sha256) | github.md §4.2 |
| RF-29 | 25 | n/a (D decided; referenced) | codex.md §3 |
| RF-32 | 25 | input provided (§4 below) | — |
| RF-37 | 25 | n/a to B (A); consistent | codex.md §3.3 |

## 3. Objections to reconciliation decisions

1. **RD-6 "`mercury-ops` metadata:read on targets" conflicts with SEC-110 and GitHub App mechanics.** App permissions apply to the whole installation, and a personal account has one installation per App, so installing `mercury-ops` on target repos grants `issues:write` and `contents:write` there (SEC-110 MUST forbids this). Implemented instead: `mercury-ops` only on `project-mercury` and the anchor repo; the drift monitor uses a `mercury-bot` token narrowed to `metadata:read`. If separation of drift reads from the pushing App is wanted, a third read-only App is needed. Orchestrator please confirm.
2. **RD-5 / SEC-113 "`MERCURY / policy` neutral until acknowledged".** GitHub treats `neutral` (and `skipped`) as passing for required checks, so `neutral` would not block the merge. Implemented `action_required` (and `failure` on pipeline error). E should amend SEC-113.
3. **RD-6 omits `actions:read`** (kept out as decided). Consequence: CI-failure revision requests see check-run output and annotations, not raw job logs. Suggest an optional OD for `actions:read` if revision quality suffers.

## 4. Remaining open items

**For D (macos-service.md):**
- §3.4 spawn table lists fd 0 = `/dev/null` for Codex kinds; Codex reads the prompt from fd 0 (`runs/<run_id>/in/prompt.txt`, codex.md §3).
- §3.5 `claude` grammar: allow `--add-dir runs/<run_id>/in` and, for tool-less runs (triage), `cwd = runs/<run_id>/in` (claude.md §2.2).
- §3.5: compile B's token tables from codex.md §3.7 and claude.md §2.2.
- Register proposed defaults (agent configuration, from the Phase 2 values): `claude.<type>.max_turns` triage 3 / authorization 30 / plan_review 40 / code & security review 60 / revision_request 20; `claude.<type>.max_budget_usd` 1 / 3 / 5 / 8 / 2; `claude.<type>.max_input_tokens` 150k / 100k / 150k / 300k / 100k; `claude.<type>.model` `claude-opus-5-5`; `claude.daily_budget_usd` 60; `claude.triage.min_interval` 30 min; `claude.max_path_denials` 5; `claude.limit_retry_factor` 1.5; `codex.max_tokens_per_run` 4 M in + 400 k out; `codex.progress.min_interval` 60 s; `gate.max_file_bytes` 1 MiB; `gate.max_changed_lines` 3,000; `github.review.max_inline_comments` 30; `linear.eligibility.max_age` 10 min; `linear.done_observe_timeout` 10 min; `linear.label_removed_action` `hold`; `outbox.pending_escalation` 24 h; `budget.github_mutations_per_hour` / `budget.linear_mutations_per_hour` 60 (SEC-705); `github.security_findings.private_full` true.
- **For C:** adopt github.md §13 catalogue (observation sequence table/columns, `<cause>`), `github.check.upsert` with hold effects, M1–M8 reference in SM §8.5, T41, `reauthorize` output fields, `producer.kind`, `spec_sha256` = linear.md §5 definition, wire-copy generator profiles (`claude-sdk`, `anthropic-messages`, `codex-strict`), source `codex_deviation` for Codex `blocked`.
- **For E:** SEC-113 `neutral` (objection 2); SEC-110 vs RD-6 (objection 1).
- **For F:** register P0-201…P0-241 (github.md §19) and the cost model input: per task happy path ≈ authorization $1–3, plan review $1–5 per cycle, two PR reviews $2–8 each per head, revision requests ≤ $2 each; typical $8–20 per task at 1–2 revision cycles, wall time dominated by Codex (≤ 45 + 120 min awake) and human wait.
- Phase 0 outcomes that can change the design: P0-213 (ALT-B-1 switch), P0-235 (`statuses:write`), P0-236 (check-run update semantics), P0-224 (`mercury_owns_all` linking), P0-233/238 (G-SPLIT).
