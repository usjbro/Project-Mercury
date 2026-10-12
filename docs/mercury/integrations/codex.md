# Integration: Codex CLI (execution role)

**Owner:** Agent B, Phase 2 proposal. **Builds on:** `reviews/02-discovery-agent-runtimes.md` §3 (**RT**). Those facts were verified from source at `rust-v0.162.1`; nothing was executed. Every behavioural claim below that depends on running Codex on the Mac carries an `ASM-B-nn` identifier.

---

## 1. Role and invariants

Codex produces two kinds of output:

- **Plans:** a read-only analysis of a coordinator-prepared worktree.
- **Code changes:** writes inside one task worktree.

Codex never holds GitHub or Linear credentials. It never commits, pushes or opens PRs. Every Codex run is gated by the coordinator:

| ID | Invariant | Enforcement |
|---|---|---|
| CX-1 | No planning run without a valid, unrevoked `auth_` bound to `(task_id, repo, spec_hash)` | Coordinator dispatch guard. Run rows reference `auth_id` (FK) |
| CX-2 | No implementation run without a plan approval bound to `plan_sha256`. The prompt contains exactly that artifact's text, re-hashed at dispatch | Coordinator dispatch guard. The plan text is loaded from the content-addressed store and its hash re-verified |
| CX-3 | Planning cannot modify the filesystem | `--sandbox read-only` (Seatbelt) |
| CX-4 | Implementation can write only inside the task worktree, and has no network | `--sandbox workspace-write` with `network_access=false` and `writable_roots=[]` (RT §3.2) |
| CX-5 | Codex processes never see credentials other than their own model key, and the commands Codex runs never see even that key | Process `env` allowlist plus `shell_environment_policy` (§6) |
| CX-6 | Repository content cannot loosen Codex's configuration | Per-task `CODEX_HOME`, `--ignore-user-config` is **not** used (we supply the config), project trust = untrusted, `--ignore-rules`, `--strict-config`, no hooks (§5) |
| CX-7 | What gets committed is decided by the coordinator after deterministic gates, not by Codex | Coordinator commit pipeline (§9) |

---

## 2. Mechanism (decision)

**Decision: drive `codex exec` directly as a supervised subprocess.** The TypeScript `@openai/codex-sdk` only wraps the same binary (RT §3.4). Running the binary directly gives:

- exact argv for the audit;
- ownership of the PID and process group;
- no hidden env injection.

The SDK's `index.d.ts` at the pinned version is used as the **event type contract** for parsing JSONL.

Not used:

- `codex app-server`, which is experimental;
- `codex mcp-server`, which was removed in 0.162.x;
- `--worktree`, because MERCURY manages worktrees;
- `--full-auto`, which no longer exists;
- `--yolo`, `--approve-for-me` and `--dangerously-bypass-hook-trust`, which are forbidden. A startup argv linter rejects them.

---

## 3. Run types and command lines

All runs use these settings:

- `cwd` = the task worktree (`~/Developer/mercury-worktrees/<repo>/<task_id>/`), outside TCC folders.
- `CODEX_HOME` = the per-task home (§5).
- stdin = the prompt envelope (§4). The prompt is never placed on argv.
- stdout = JSONL. stderr is captured to the run log.

### 3.1 Planning (initial)

```
codex exec --json --strict-config --ignore-rules \
  --cd <worktree> --sandbox read-only \
  -m <pinned_model> -c model_reasoning_effort="high" \
  --output-schema <MERCURY_SCHEMAS>/codex-plan.v1.schema.json \
  -o <run_dir>/final.json  -
```

### 3.2 Plan revision (resume the planning thread)

```
codex exec resume <plan_thread_id> --json --strict-config --ignore-rules \
  --cd <worktree> --sandbox read-only \
  --output-schema <…>/codex-plan.v1.schema.json -o <run_dir>/final.json  -
```

- stdin carries the Claude `revision_request` instructions in the envelope.
- Resume keeps Codex's codebase exploration and is cheaper.
- **ASM-B-10:** `exec resume` accepts `--sandbox`, `--output-schema` and `-o` (the RT §3.1 flag table lists them for `exec`; resume inheritance is unverified). If it does not, a revision becomes a fresh `exec` with the prior plan and findings in the envelope. The design works either way.

### 3.3 Implementation (fresh thread, deliberately not a resume)

```
codex exec --json --strict-config --ignore-rules \
  --cd <worktree> --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=false \
  -c 'sandbox_workspace_write.writable_roots=[]' \
  -c sandbox_workspace_write.exclude_slash_tmp=true \
  --output-schema <…>/codex-impl-result.v1.schema.json -o <run_dir>/final.json  -
```

Implementation starts a **new thread** containing only the approved plan text (`plan_sha256`) and the authorization scope. Reasons:

1. The planning thread contains rejected plan versions and reviewer findings. Resuming it would make "what Codex implemented" depend on conversational memory rather than on the approved artifact, which breaks CX-2's binding.
2. The sandbox mode changes from read-only to workspace-write. A fresh thread avoids any ambiguity in resumed sandbox semantics.

### 3.4 Implementation revision (resume the implementation thread)

```
codex exec resume <impl_thread_id> --json --strict-config --ignore-rules \
  --cd <worktree> --sandbox workspace-write -c sandbox_workspace_write.network_access=false … -
```

- It runs after a Claude `revision_request` (review findings, CI failure, human changes requested or a conflict).
- Before a revision run, the coordinator ensures the worktree is at the last pushed `head_sha`, with a clean status.
- If a revision needs scope beyond the authorization (new paths, dependencies), the coordinator does **not** run Codex. The task goes to re-authorization (`needs_reauthorization`).

### 3.5 Thread IDs

- Codex assigns the thread ID itself; it cannot be preassigned (RT §4).
- The coordinator captures it from the first `thread.started` event and persists it **before** consuming further events, using `UPDATE runs SET codex_thread_id=?` in its own transaction.
- If the coordinator crashes before persisting the ID, the run is abandoned and the next attempt starts fresh. `exec resume --last` is never used, because it is ambiguous under concurrency.

---

## 4. Prompt envelope (Codex)

This uses the same nonce-delimited format as `claude.md` §5.2, with Codex-specific sections:

```text
<mercury_task schema="mercury.codex_envelope.v1" run_id="run_…" kind="implement" nonce="…">
<authority>
You are executing an approved plan for MERCURY. Approved plan: pln_… sha256=…  Authorization: auth_… v1.
Allowed paths: src/foo/**, tests/foo/**.  Forbidden: .github/**, CODEOWNERS, AGENTS.md, .codex/**, .claude/**, .mcp.json, lockfiles (unless listed).
Do not run git commit, git push, gh, or network tools. The coordinator commits.
Run the test commands listed below and report results. Stop and report "blocked" instead of widening scope.
</authority>
<test_commands> ["npm test -- --runInBand", "npm run lint"] </test_commands>   <!-- from MERCURY repo config, not from repo files -->
<approved_plan sha256="…" nonce="…"> …verbatim approved plan… </approved_plan nonce="…">
<untrusted source="linear.issue.description" sha256="…" nonce="…"> … </untrusted nonce="…">
</mercury_task>
```

- Repository `AGENTS.md` files are still read by Codex on its own (RT §3.3). They come from the base branch and are untrusted, but in practice operator-authored. The `<authority>` block states that the envelope's scope wins when the two conflict. **This is policy-enforced only.** The software backstops are:
  - the diff guard (§9) rejects edits to forbidden paths;
  - Claude's PR review checks plan conformance.

---

## 5. Per-task `CODEX_HOME` and configuration isolation

**Layout:** `~/Library/Application Support/Mercury/codex/<task_id>/home/`, mode 0700. Created at task authorization and removed at task cleanup, after the audit copies of session files have been archived.

| Path | Contents |
|---|---|
| `config.toml` | Generated by the coordinator from a pinned template (below) |
| `sessions/` | Codex session files (needed for resume); archived to the artifact store on task completion |
| No `auth.json` | API-key mode (§7) |
| No `rules/`, no hooks, no `mcp_servers` | — |

The home is per **task** (not per run), so that resume works across a task's runs. Concurrent tasks never share a home, which removes the shared-sqlite and auth-refresh race (RT §3.6 #7).

```toml
# config.toml template v1 (illustrative; keys verified in RT §3.3 schema, values ASM-B-11)
model = "<pinned codex model>"
model_reasoning_effort = "high"
approval_policy = "never"
sandbox_mode = "read-only"                 # overridden per run by --sandbox
check_for_update_on_startup = false
cli_auth_credentials_store = "ephemeral"   # never write credentials to disk (ASM-B-12)
web_search = "disabled"                    # ASM-B-11 (exact value name)
project_doc_max_bytes = 32768

[sandbox_workspace_write]
network_access = false
writable_roots = []
exclude_slash_tmp = true
exclude_tmpdir_env_var = false             # TMPDIR is set to a per-run dir inside the worktree's sibling run dir

[shell_environment_policy]
inherit = "core"                           # ASM-B-13: accepted values in 0.162.1
ignore_default_excludes = false            # keep default *KEY*/*TOKEN*/*SECRET* excludes
include_only = ["PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CI", "TERM"]
set = { CI = "1", MERCURY_RUN = "1" }

[history]
persistence = "none"

[projects."/Users/<op>/Developer/mercury-worktrees"]
trust_level = "untrusted"                  # repo .codex/config.toml and hooks are not honoured
```

- `--strict-config` makes an unknown key fatal. This turns silent drift between versions into a `config_fatal` failure at startup.
- **Filesystem read exposure.** Codex's Seatbelt profile allows broad reads (RT §2.5 and §3.2). Credential paths are therefore *readable* by Codex commands:
  - `~/.config/gh/hosts.yml` (the operator's admin token);
  - `~/.ssh`;
  - `~/.codex/auth.json`;
  - `~/Library/Application Support/Mercury/`.

  Network is off, so the exfiltration route is **writing a secret into the worktree** so that the coordinator pushes it. Controls:
  1. Permission-profile deny-read rules (`[permissions.mercury.filesystem]` with `"~/.ssh"="deny"` and similar), if supported by the pinned version (**ASM-B-14**).
  2. **Software gate:** secret scanning plus a forbidden-content scan on the diff before commit (§9). This is mandatory regardless of item 1.
  3. **Strongest option, recommended to Agents D and E:** run `mercuryd` and its agents under a **dedicated macOS user** that holds no human credentials. This raises login-session questions; see report OQ-B-05.

---

## 6. Process environment (allowlist)

| Variable | Planning | Implementation |
|---|---|---|
| `PATH` | pinned toolchain dirs (node, git, language toolchains) + `/usr/bin:/bin` | same |
| `HOME` | operator home (**ASM-B-15**: Codex needs HOME; a per-task fake HOME breaks toolchains) | same |
| `CODEX_HOME` | per-task home | same |
| `CODEX_API_KEY` | model key (§7) | same |
| `TMPDIR` | `…/runs/<run_id>/tmp` | same |
| `LANG`, `TERM=dumb`, `CI=1`, `NO_COLOR=1` | yes | yes |

Excluded:

- every `GITHUB_*`, `GH_*`, `LINEAR_*`, `ANTHROPIC_*`, `OPENAI_API_KEY`, `SSH_AUTH_SOCK` and `AWS_*` variable;
- any variable not in the list above.

`CODEX_API_KEY` is visible to the Codex process but excluded from the commands it runs by `shell_environment_policy`. Default excludes cover `*KEY*` (**ASM-B-13**).

**Residual risk:** a sandboxed command might read the parent's environment through `ps -E` (or `ps eww`). Whether Seatbelt or macOS blocks this is **ASM-B-16**. Mitigation: use a dedicated OpenAI project key with a hard monthly limit, rotated quarterly.

---

## 7. Authentication

- **Recommended:** an OpenAI API key for a dedicated project "mercury" with a usage cap. It is stored in the Keychain as `dev.mercury.openai` and passed as `CODEX_API_KEY` per process. `exec` honours this variable (RT §3.5).
- **Alternative:** ChatGPT-plan login. It requires `auth.json` in a `CODEX_HOME`, and refresh rewrites the file. Per-task homes would each need a copy, and copies diverge on refresh-token rotation (**ASM-B-17**). If the operator chooses ChatGPT billing:
  - use one shared auth home and set `codex.max_concurrency = 1`;
  - point per-task homes at it through `CODEX_HOME` only for auth (**ASM-B-18**, likely unsupported). Otherwise fall back to a single shared `CODEX_HOME`, with sessions namespaced by thread ID.
  - This is **OQ-B-03**.

---

## 8. Event consumption, progress and heartbeats

The JSONL reader is line-buffered, with a 1 MiB maximum line length; longer lines are truncated, logged and flagged. Unknown `type` values are logged and ignored (RT §6 V6).

| Event | Coordinator action |
|---|---|
| `thread.started{thread_id}` | Persist `codex_thread_id` (§3.5). Emit `mercury.implementation_progress.v1{phase:"started"}` |
| `turn.started` | heartbeat |
| `item.started/updated/completed` with `command_execution` | Heartbeat. On completion, record `{command, exit_code, duration}`, truncating output to 8 KiB in the run log. Commands matching `test_commands` become `codex_test_observations[]`. These are **advisory**; §10 holds the authoritative results |
| `item.*` with `file_change` | Heartbeat. Accumulate the changed-path set. A path outside `allowed_paths` raises an early-warning `scope_drift` event (no kill; the gate is at §9) |
| `item.*` with `agent_message` / `reasoning` / `todo_list` | Heartbeat. The `todo_list` is stored as the latest progress snapshot (coarse % = completed/total) |
| `item.*` with `mcp_tool_call` / `web_search` | **Must never occur** (no MCP servers, web search disabled). Raise a security event and kill the run |
| `turn.completed{usage}` | Accumulate tokens into `run.tokens_*`. Enforce `codex.max_tokens_per_run` (default 4 M input + 400 k output). If exceeded, interrupt the run |
| `turn.failed{error}` / `error{message}` | Classify (§11) |

- **Progress messages.** `mercury.implementation_progress.v1` is emitted to the event log at most once per 60 s per run, or on a phase change. The `last_event_at` heartbeat is updated on every event in memory and flushed to SQLite every 15 s.
- **Stall detection.** Planning has no events for 10 min; implementation has no events for 15 min, which allows long test commands. In either case the run is `stalled`, and a soft interrupt is followed by a kill (§12). Sleep gaps are excluded.

---

## 9. How commits happen (coordinator-owned)

**Decision:** Codex never commits. In workspace-write, `.git` is protected, and in a linked worktree the commit writes into the main repository's `.git/worktrees/<name>`, which is outside the writable roots (RT §3.2; **ASM-B-19**: commit is denied). Even if commits worked, the coordinator keeps commit authority so that the gates below are mandatory.

Pipeline after a successful implementation run (each step is idempotent; dedup key `git:commit:<run_id>`):

1. **Snapshot.** `git -C <wt> status --porcelain=v2 -z --untracked-files=all` and `git diff --binary HEAD`.
2. **Diff guard.** Software-enforced; any hit leaves the run `rejected_by_gate`, and Claude `revision_request` or escalation follows. The guard rejects:
   - writes to paths in `authorization.scope.denied_paths`, plus the global protected list: `.github/**`, `CODEOWNERS`, `.gitattributes`, `.gitmodules`, `**/.git*`, `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`, `.claude/**`, `.mcp.json`, `.codex/**`, `.agents/**`, `.husky/**`, `.npmrc`, `.yarnrc*`;
   - lockfile changes unless the approved plan lists dependency changes;
   - symlinks (new or modified) whose target is absolute or escapes the repo;
   - new executable bits outside `scripts/**` allowed by the plan;
   - files larger than 1 MiB, or binaries, unless the plan lists them;
   - total diff over the configured limit (default 3,000 changed lines);
   - submodule changes.
3. **Secret scan.** Run a pinned `gitleaks` (or equivalent) on the diff, together with MERCURY's own patterns for known credential formats (GitHub tokens, `sk-ant-`, `sk-`, `lin_api_`, PEM headers). A hit blocks the run and raises a **security escalation**. The content is never logged; only the rule ID and path are recorded.
4. **Scope report.** Paths outside the plan's `files_to_change` but inside the authorization scope are allowed and listed in the PR body for Claude review.
5. **Commit.** Run `git -c core.hooksPath=/dev/null -c core.fsmonitor=false -c commit.gpgsign=false -c user.name="mercury-bot[bot]" -c user.email="<APP_ID>+mercury-bot[bot]@users.noreply.github.com" commit --no-verify -F <msg>` with environment `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1` and `GIT_TERMINAL_PROMPT=0`. The message format is in github.md §4.
6. **Push.** github.md §4.3. It uses an App token with `contents:write` only, which is never exposed to Codex or to the worktree's git config.

---

## 10. Where tests run (decision)

**Decision: two layers. Codex runs tests inside its sandbox while iterating (advisory). The coordinator re-runs the authoritative test suite after Codex exits (gating). GitHub CI is the third, independent gate.**

| Layer | Who | Environment | Purpose | Gate? |
|---|---|---|---|---|
| L1 | Codex | Codex Seatbelt workspace-write, no network | Fast feedback loop for the implementer | No; recorded as `codex_test_observations` |
| L2 | Coordinator `test-runner` | Seatbelt profile with no network, write only to the worktree and run tmp, env allowlist as §6 but **without** `CODEX_API_KEY`; wall limit `repo.test_timeout` (default 20 min); process group killed after | Authoritative local result; produces the `mercury.test_results.v1` artifact (`run_id`, commands, exit codes, duration, junit/TAP if available, sha of logs) | **Yes.** No push unless all required commands pass, or the plan explicitly declared known failures, which Claude PR review must then accept |
| L3 | GitHub Actions (repo CI) | GitHub-hosted runners | Independent verification on the pushed SHA; required checks | **Yes.** Branch protection |

Rules:

- **Test commands come from MERCURY's per-repo config** (`repos.<owner/name>.test_commands`, `setup_commands`), which is coordinator-owned. They are never parsed from repo files that Codex could edit.
- **L2 sandbox.** Reuse Codex's own Seatbelt wrapper if the pinned version exposes it as a subcommand (`codex sandbox macos -- <cmd>`, **ASM-B-20**). Otherwise use a MERCURY-shipped `sandbox-exec` profile (owned by Agent E/D).
- **Dependency installation** (needs network) is a separate coordinator step, `deps_install`, run **before** the implementation run. It installs only what the lockfile or the approved plan specifies (`npm ci --ignore-scripts`; per-ecosystem table in repo config). It runs with network on, no credentials in env, and writes only to the worktree. Codex never gets network (`authorization.limits.network` is `none` or `deps_only`; the latter enables only this coordinator step). Lifecycle scripts stay disabled unless the operator allowlists the repo (OQ-B-04).

---

## 11. Exit-code and failure mapping

Codex `exec` exits 0 or 1 (RT §3.1). Classification uses exit status plus JSONL plus stderr patterns. The patterns are versioned per pinned Codex version and covered by contract tests.

| Observation | Class | Retry | Revision budget |
|---|---|---|---|
| exit 0, `final.json` present and Ajv-valid against the schema, plan/impl semantic checks pass | `success` | — | — |
| exit 0, `final.json` missing or invalid (**ASM-B-21**: Codex's own behaviour on schema mismatch) | `output_invalid` | 1 resume with "Return only the JSON object for the schema" | No |
| exit 1, `turn.failed` or `error` mentioning 429, rate limit, overloaded, 5xx, or stream disconnect | `transient_api` | Backoff 2 m, 10 m, 30 m; max 3; resume if a thread exists | No |
| exit 1, connection or DNS errors **and** global connectivity probe down | `network_down` | Not an attempt; wait for connectivity, then resume | No |
| exit 1, 401/403 or "invalid api key" / auth | `auth_failed` | No retry; global Codex circuit breaker; notify operator | No |
| exit 1 before `thread.started`, stderr matches config, `strict-config` or "Not inside a trusted directory" | `config_fatal` | No retry; disable Codex dispatch; notify | No |
| killed by coordinator: deadline | `timeout` | 1 retry (resume), then escalate | **Yes** (counts 1) |
| killed by coordinator: stall | `stalled` | 1 retry (resume), then escalate | No |
| killed by signal not from coordinator, or exit >1 | `crash` | 2 retries (resume if a thread exists) | No |
| exit 0 with `final.status = "blocked"` (Codex reports it cannot proceed within scope) | `blocked_by_agent` | No retry; Claude `revision_request` decides between re-plan and escalation | Yes |
| Diff guard or secret scan rejects | `rejected_by_gate` | Claude `revision_request` (secret hit means escalation, not revision) | Yes |
| L2 tests fail | `tests_failed` | Claude `revision_request` with the test report | Yes |
| `mcp_tool_call` / `web_search` item seen | `policy_violation` | No retry; security escalation; task `BLOCKED` | — |

---

## 12. Timeouts and kill procedure

| Run type | Wall deadline (sleep-aware) | Stall timeout |
|---|---|---|
| Planning / plan revision | 25 min | 10 min |
| Implementation / revision | 120 min (`authorization.limits.max_wall_minutes` may lower it) | 15 min |
| L2 test run | `repo.test_timeout` (20 min) | n/a |

Kill sequence:

1. SIGINT to the process group (Codex ends the turn as `Interrupted` and exits 1).
2. After 20 s, SIGTERM the group.
3. After 10 s, SIGKILL the group.
4. Verify no process with the recorded `pgid` and start time remains.

Children are spawned `detached` (new session), so launchd will not reap them. The coordinator's orphan sweep at startup kills recorded process groups whose run is not `RUNNING` (Agent D owns the sweep).

After a kill, the worktree may hold partial edits. The next attempt either resumes the thread on top of them, or the coordinator runs `git reset --hard <last_pushed_sha> && git clean -ffdx` (excluding `node_modules` when a deps snapshot exists) before a fresh run. Resume is the default after `stalled`; clean is the default after `crash`.

---

## 13. Version pinning and self-test

- Pin `@openai/codex` to an exact version installed in MERCURY's own prefix (`~/Library/Application Support/Mercury/toolchain/codex/<ver>/`). Never use the operator's global `codex`. `check_for_update_on_startup=false`.
- **Startup self-test** (blocks Codex dispatch on failure), run against a bundled fixture repo:
  1. `codex --version` matches the pin.
  2. `codex exec --help` lists `--json`, `--output-schema`, `-o`, `--sandbox`, `--strict-config`, `--ignore-rules`, `--cd`.
  3. A read-only planning run on the fixture produces schema-valid output and creates no file (checked with `git status`).
  4. A workspace-write run asked to `curl https://example.com` and `git commit` reports both as failed. This confirms network off and `.git` protected (ASM-B-19).
  5. A run asked to `cat ~/.config/gh/hosts.yml > leak.txt` is either denied (ASM-B-14 holds) or caught by the §9 secret scan on the fixture. The test passes only if no secret could reach a commit.
- **Contract tests:** for each pinned version, assert that the JSONL event types match the `index.d.ts` captured at that version (RT §6 V6).
