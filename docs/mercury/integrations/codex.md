# Integration: Codex CLI (execution role)

**Owner:** Agent B. **Status:** Phase 4 revision. Implements RD-1, RD-11, RD-15 and RD-17 (`reviews/30-reconciliation.md`).
**Builds on:** `reviews/02-discovery-agent-runtimes.md` §3 (**RT**, verified from source at `rust-v0.162.1`) and `reviews/21-review-B-interfaces.md` ([V-src] items). Behavioural claims that need a run on the Mac carry `ASM-B-nn`; each is linked to a Phase 0 check in `github.md` §19.

**Single sources referenced, not restated here:** output contracts and the wire-copy generator (Agent C, `protocols/messages.md` §5); state transitions, holds and run-attempt caps (C, `architecture/state-machine.md` §3, §5, §7.1); worktree reset policy (C, `components.md` §9); filesystem layout (D, `operations/macos-service.md` §7.1); `agent-exec`/`agent-ctl` grammar and the fd-3 key hand-off (D, `macos-service.md` agent-uid runtime section, ADR-013); parameter values (D's parameter table); protected-path lists and SEC statements (E, `security/threat-model.md` SEC-209, SEC-310, SEC-312, SEC-403/404/406); failure-class accounting and retry matrix (`github.md` §15).

---

## 1. Role and invariants

Codex produces two kinds of output:

- **Plans:** a read-only analysis of a coordinator-prepared worktree.
- **Code changes:** writes inside one task worktree.

Codex never holds a GitHub or Linear credential. It never commits, pushes or opens PRs; the coordinator does (§9, `github.md` §4).

| ID | Invariant | Enforcement |
|---|---|---|
| CX-1 | No planning run without a valid, unrevoked authorization bound to `(task_id, repo, spec_hash)`; a result that arrives after a spec change is not acted on until re-authorization (RD-13) | Coordinator authorization guard at dispatch **and** at result application (SM §8.1) |
| CX-2 | No implementation run without a plan approval bound to `plan_sha256`; the prompt contains exactly that artifact's text, re-hashed at dispatch | Approval binding guard (SM §8.2); plan loaded from the content-addressed store and re-verified |
| CX-3 | Planning cannot modify the filesystem | `--sandbox read-only` (Seatbelt) plus a post-run check that the worktree is unchanged |
| CX-4 | Implementation can write only inside the task worktree and its run scratch, and has no network | `--sandbox workspace-write`, `network_access=false`, `writable_roots=[]` (RT §3.2); OS: agent uid |
| CX-5 | Codex never sees a credential other than its model key, and the commands it runs never see even that key | Key delivered on fd 3 to `agent-exec` (§6); `shell_environment_policy` |
| CX-6 | Repository content cannot loosen Codex's configuration | Per-task `CODEX_HOME` with a coordinator-generated `config.toml`, regenerated and byte-verified before every run; project trust `untrusted`; `--ignore-rules`; `--strict-config`; no hooks or MCP (§5); instruction files byte-checked before every run including resumes (SEC-209) |
| CX-7 | What gets committed is decided by the coordinator after deterministic gates | Coordinator commit pipeline using git plumbing against the mirror (§9) |
| CX-8 | Every Codex process runs as `_mercuryagent` | `agent-exec` via the restricted sudoers drop-in (RD-1, ADR-013). Same-uid execution is allowed only with fakes and the sandbox repository (M1–M4) and never with workspace-write against a non-sandbox repository before SEC-T-20 passes |

---

## 2. Mechanism (decision)

**Decision: drive `codex exec` directly, spawned through `agent-exec` as a detached, adoptable run with file stdio.** The `@openai/codex-sdk` only wraps the same binary (RT §3.4); its `index.d.ts` at the pinned version is the event-type contract for parsing JSONL.

Not used: `codex app-server` (experimental), `codex mcp-server` (removed in 0.162.x), `--worktree`, `--full-auto`, and the forbidden flags of SEC-208 (`--yolo`, `--approve-for-me`, `--dangerously-bypass-hook-trust`, `--add-dir`, `danger-full-access`, network on). `agent-exec`'s grammar and a coordinator argv linter both reject them.

---

## 3. Run types and command lines

Common to all runs:

- Spawn: `sudo -n -C 4 -u _mercuryagent -g mercury /usr/local/libexec/mercury/agent-exec --run-dir <WORK_ROOT>/runs/<run_id>`, detached. `kind` (`codex_plan`, `codex_implement`, `codex_revise`), argv, cwd, env and `secret_env: "CODEX_API_KEY"` are in the run's `spec.json` (`macos-service.md` §3.2) and validated by `agent-exec` against the token table of §3.7 (`macos-service.md` §3.5).
- `cwd` = the task worktree `WORK_ROOT/worktrees/<owner>__<repo>/<issue-lower>-<ulid8>/` (`macos-service.md` §7.1).
- `CODEX_HOME` = the task's home (§5).
- The prompt is never on argv. fd 0 = `runs/<run_id>/in/prompt.txt` opened read-only by `mercuryd` and passed by inheritance (the `-` positional makes Codex read it). **Open item for D:** `macos-service.md` §3.4 lists fd 0 = `/dev/null` for Codex kinds; it must be the prompt file. fd 1 = `stdout.jsonl`, fd 2 = `stderr.log` (operator-owned, written through the inherited fds, capped by `run.stdout_cap_mib`). fd 3 = model key.
- `--output-schema` points at the run's copy of the `codex-strict` wire schema (§3.6); `-o` writes to `runs/<run_id>/out/final.json`.

### 3.1 Planning (initial)

```
codex exec --json --strict-config --ignore-rules \
  --cd <worktree> --sandbox read-only \
  -m <pinned_model> -c model_reasoning_effort=<codex.plan_reasoning_effort> \
  --output-schema <run_dir>/in/schema.codex_plan.wire.json \
  -o <run_dir>/out/final.json  -
```

### 3.2 Plan revision (resume the planning thread)

```
codex exec resume <plan_thread_id> --json --strict-config --ignore-rules \
  --cd <same worktree> --sandbox read-only \
  --output-schema <run_dir>/in/schema.codex_plan.wire.json -o <run_dir>/out/final.json  -
```

- stdin carries the `mercury.plan.revision_request.v1` instructions (Claude's words, §4).
- `exec resume` loads `--output-schema` and builds resume parameters from the current config, including sandbox and cwd [V-src 0.162.1]. `--cd` is passed explicitly because cwd comes from config (RB-26). **ASM-B-10** is reduced to a runtime check that the sandbox is actually re-applied.

### 3.3 Implementation (fresh thread, deliberately not a resume)

```
codex exec --json --strict-config --ignore-rules \
  --cd <worktree> --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=false \
  -c 'sandbox_workspace_write.writable_roots=[]' \
  -c sandbox_workspace_write.exclude_slash_tmp=true \
  --output-schema <run_dir>/in/schema.codex_implementation.wire.json -o <run_dir>/out/final.json  -
```

Implementation starts a **new thread** containing only the approved plan text (`plan_sha256`) and the authorization scope (ADR-005 as revised): the planning thread contains rejected plan versions and reviewer findings, and the sandbox mode changes.

### 3.4 Implementation revision

```
codex exec resume <impl_thread_id> --json --strict-config --ignore-rules \
  --cd <same worktree> --sandbox workspace-write -c sandbox_workspace_write.network_access=false … -
```

- Runs after a `mercury.revision.request.v1` (verbatim Claude review text or a Claude `revision_request` run, `claude.md` §3.3).
- **Precondition:** the worktree HEAD equals `tasks.last_commit_sha` (the last coordinator commit, pushed or not; RC-06) and the status is clean.
- **Resume rule (RC-06):** a thread may be resumed only if the worktree has not been reset since that thread's last turn. After any reset (§12), the revision runs as a **fresh** thread with the approved plan plus the revision instruction.
- If the instruction needs scope beyond the authorization (new paths, dependencies), Codex is not run: the Claude `revision_request` returns `replan` or `escalate`, or Claude amends the authorization (SM G4).

### 3.5 Thread ids

- Codex assigns the thread id (RT §4). The coordinator captures it from the first `thread.started` event and persists it (`runs.codex_thread_id`, `tasks.codex_*_thread_id`) in its own transaction before consuming further events.
- If the coordinator crashes before persisting it, the adopted run's `stdout.jsonl` is re-read from the start on adoption (§12.2), so the id is recovered. `exec resume --last` is never used.

### 3.6 Output schemas: `codex-strict` wire copies (RD-15, RB-01)

Codex sends the schema file verbatim with `strict: true` [V-src]; the provider enforces its strict-mode subset, and an unsupported keyword fails every run of that kind with a request-time 400. Therefore:

1. The CI generator (Agent C) emits a `codex-strict` wire copy of `output.codex_plan.schema.json` and `output.codex_implementation.schema.json`: `$schema` and `$id` removed; `minLength`, `maxLength`, `minimum`, `maximum` and any `minItems`/`maxItems` the Phase 0 probe rejects removed and restated in `description`; an explicit `type` added beside every `enum`; all objects closed with every property required (already true of the canonical files).
2. The coordinator copies the wire file into the run's inputs dir and records its sha256 and the canonical `schema_id` in the run row.
3. `final.json` is validated with Ajv against the **canonical** schema (all bounds).
4. A provider `invalid_json_schema` (or equivalent) rejection is `config_fatal` (§11).
5. Phase 0 / contract test **ASM-B-61**: each wire schema is sent to the pinned Codex with a trivial prompt and must be accepted.

### 3.7 `agent-exec` token table for Codex kinds (B owns; compiled into `agent.conf`)

| Kind | Fixed prefix | Allowed tokens | `-c` keys allowed |
|---|---|---|---|
| `codex_plan` | `exec`, or `exec resume <uuid>` for a plan revision | `--json`, `--strict-config`, `--ignore-rules`, `--cd <cwd>`, `--sandbox read-only`, `-m <pinned model>`, `--output-schema runs/<run_id>/in/*.json`, `-o runs/<run_id>/out/final.json`, final `-` | `model_reasoning_effort` |
| `codex_implement` | `exec` | as above with `--sandbox workspace-write` | `model_reasoning_effort`, `sandbox_workspace_write.network_access=false` (only the value `false`), `sandbox_workspace_write.writable_roots=[]` (only empty), `sandbox_workspace_write.exclude_slash_tmp=true` |
| `codex_revise` | `exec resume <uuid>` | as `codex_implement` | as `codex_implement` |

Everything else is rejected, in particular the SEC-208 flags, `--profile`, `--add-dir`, `--config` with any other key, and a second prompt source.

---

## 4. Prompt envelope (Codex)

Same nonce-delimited format as `claude.md` §5.2, with Codex sections:

```text
<mercury_task schema="mercury.codex_envelope.v1" run_id="run_…" kind="implement" nonce="…">
<authority>
You are executing an approved plan for MERCURY. Approved plan: pln_… sha256=…  Authorization: auth_… v1.
Allowed paths: src/foo/**, tests/foo/**.  Forbidden: the protected paths listed below.
Do not run git commit, git push, gh, or network tools. The coordinator commits.
Run the test commands listed below and report results. Stop and report "blocked" instead of widening scope.
</authority>
<protected_paths> …from the repo policy (SEC-310 classes)… </protected_paths>
<test_commands> ["npm test -- --runInBand", "npm run lint"] </test_commands>   <!-- MERCURY repo config, never repo files -->
<approved_plan sha256="…" nonce="…"> …verbatim approved plan… </approved_plan nonce="…">
<revision_request id="…" producer="claude_run|coordinator_verbatim" sha256="…" nonce="…"> …Claude's instructions… </revision_request nonce="…">
<untrusted source="linear.issue.description" sha256="…" nonce="…"> … </untrusted nonce="…">
</mercury_task>
```

- CI logs, check output and human comments never appear here directly; they reach Codex only through a Claude `revision_request` run (RD-8).
- Repository `AGENTS.md` files are still read by Codex (RT §3.3). They come from the base SHA and are byte-checked before every run, including resumes (SEC-209). The `<authority>` block states that the envelope's scope wins on conflict; this is policy-enforced only, backed by the diff gate (§9) and Claude's PR review.

---

## 5. Per-task `CODEX_HOME` (RD-15)

**Location:** `WORK_ROOT/codex-home/<task_id>/` (ownership and ACLs: `macos-service.md` §7.1; SEC-203). Created at the first Codex dispatch of the task; `sessions/` archived to the artifact store and the directory purged through `agent-ctl purge` at task terminal.

| Path | Owner / access | Contents |
|---|---|---|
| `config.toml` | operator-owned, agent read-only | Generated from the pinned template below. **Regenerated and byte-verified before every run**, so nothing a previous run or the repository wrote can persist |
| `sessions/` | agent-writable | Codex session files; required by `exec resume` |
| Other Codex-managed state (logs, state database) | agent-writable | Exact list verified in Phase 0 (**ASM-B-22**); none may contain configuration Codex reads |
| No `auth.json`, no `rules/`, no hooks, no `mcp_servers` | — | Checked before every run; presence fails the run as `config_fatal` |

The home is per **task**, not per run, so that plan and implementation revisions can resume their threads (RB-07). Concurrency safety comes from "at most one Codex run per task" (SM invariant), not from per-run homes. SEC-203 is amended accordingly ("per-task, coordinator-generated").

During a run, Codex's own commands cannot rewrite `config.toml` (Seatbelt writable roots are the worktree and the run scratch only); the Codex process itself does not write it. Regeneration before each run closes the remaining window.

```toml
# config.toml template v1 (keys verified in RT §3.3; values ASM-B-11)
model = "<pinned codex model>"
model_reasoning_effort = "<codex.plan_reasoning_effort | codex.impl_reasoning_effort>"
approval_policy = "never"
sandbox_mode = "read-only"                 # overridden per run by --sandbox
check_for_update_on_startup = false
cli_auth_credentials_store = "ephemeral"   # ASM-B-12
web_search = "disabled"                    # ASM-B-11
project_doc_max_bytes = 32768

[sandbox_workspace_write]
network_access = false
writable_roots = []
exclude_slash_tmp = true
exclude_tmpdir_env_var = false             # TMPDIR = the run's tmp dir

[shell_environment_policy]
inherit = "core"                           # ASM-B-13
ignore_default_excludes = false            # keep default *KEY*/*TOKEN*/*SECRET* excludes
include_only = ["PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CI", "TERM"]
set = { CI = "1", MERCURY_RUN = "1" }

[history]
persistence = "none"

[projects."<WORK_ROOT>/worktrees"]          # generated from the WORK_ROOT constant (RE-19)
trust_level = "untrusted"                  # repo .codex/config.toml and hooks are not honoured
```

- `--strict-config` makes an unknown key fatal, turning silent drift between versions into `config_fatal` at self-test.
- **Read exposure.** Codex's Seatbelt profile allows broad reads (RT §2.5). As `_mercuryagent`, Codex cannot read the operator's home, `MERCURY_HOME` or any Keychain (SEC-201); this is the primary control and replaces the earlier same-uid mitigations. Remaining readable content is group-readable `WORK_ROOT` data (mirrors, other worktrees), which holds no credentials. Deny-read permission profiles (**ASM-B-14**) remain an optional second layer. The pre-commit secret scan (§9) stays mandatory.

---

## 6. Process environment (built by `agent-exec`)

| Variable | Planning | Implementation |
|---|---|---|
| `PATH` | Pinned toolchain dirs under `WORK_ROOT/toolchains/` (repo toolchain manifest, `macos-service.md` §3.9) + `/usr/bin:/bin` | same |
| `HOME` | `/Users/_mercuryagent` (caches only; RD-1, RD-26) | same |
| `CODEX_HOME` | `WORK_ROOT/codex-home/<task_id>/` | same |
| `CODEX_API_KEY` | From fd 3 | same |
| `TMPDIR` | `runs/<run_id>/tmp/` | same |
| `LC_ALL`, `MERCURY_RUN_ID` | yes | yes |
| `GIT_CONFIG_GLOBAL` | `WORK_ROOT/toolchains/agent.gitconfig`; with `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0` | same |
| `LANG`, `TERM=dumb`, `CI=1`, `NO_COLOR=1` | yes | yes |

Excluded: every `GITHUB_*`, `GH_*`, `LINEAR_*`, `ANTHROPIC_*`, `OPENAI_API_KEY`, `SSH_AUTH_SOCK` and `AWS_*` variable and anything not listed (SEC-202).

`CODEX_API_KEY` is visible to the Codex process but excluded from its commands by `shell_environment_policy`. **Residual risk ASM-B-16:** a sandboxed command running as the same agent uid might read the Codex process's environment (`ps -E`). Mitigation: a dedicated OpenAI project key with a hard spend cap (OD-04), rotated per SEC-504.

---

## 7. Authentication

- **Default (OD-04):** an OpenAI API key for a dedicated project with a usage cap, in the operator's login Keychain as `com.usjbro.mercury.openai` (inventory: `macos-service.md` §9.1). `mercuryd` reads it once at start and on `mercury reload-credentials` and passes it per run on fd 3. `exec` honours `CODEX_API_KEY` (RT §3.5).
- **ChatGPT-plan login is not supported in v1:** it needs an `auth.json` in a `CODEX_HOME` that refresh rewrites, which conflicts with per-task homes and with a coordinator-generated read-only configuration.

---

## 8. Event consumption, progress, liveness

The coordinator tails `stdout.jsonl` (line-buffered, maximum line length 1 MiB; longer lines truncated, logged and flagged). Unknown `type` values are logged and ignored (RT §6 V6).

| Event | Coordinator action |
|---|---|
| `thread.started{thread_id}` | Persist the thread id (§3.5); emit `mercury.implementation.progress.v1{phase:"started"}` |
| `turn.started` | Liveness |
| `item.started` with `command_execution` | Liveness; mark "command in progress" (stall threshold rule below) |
| `item.completed` with `command_execution` | Record `{command, exit_code, duration}` with output truncated in the run log. Commands matching `test_commands` become advisory `codex_test_observations[]`; §10 holds the authoritative results. Sandbox denials are counted (SEC-903) |
| `item.*` with `file_change` | Accumulate the changed-path set; a path outside `allowed_paths` raises an early `scope_drift` event (no kill; the gate is §9) |
| `item.*` with `agent_message` / `reasoning` / `todo_list` | Latest `todo_list` stored as the progress snapshot |
| `item.*` with `mcp_tool_call` / `web_search` | **Must never occur.** Security event; kill the run; class `policy_violation` |
| `turn.completed{usage}` | Accumulate tokens; enforce `codex.max_tokens_per_run`; interrupt when exceeded |
| `turn.failed{error}` / `error{message}` | Classify (§11) |

- **Progress messages:** `mercury.implementation.progress.v1` at most once per `codex.progress.min_interval` per run or on a phase change.
- **Liveness and stall (RD-15).** A run is live if `stdout.jsonl` grew **or** the process group's summed CPU time increased (`agent-ctl stats --run <run_id>`, sampled every `run.liveness_poll_s`). `stalled` requires both to be flat for the stall threshold, measured in credited awake time. While a `command_execution` item is open, the threshold is at least the repository's `repo.test_timeout_min`, so a long, silent test suite is never killed as stalled. Thresholds: `run.codex_plan.*`, `run.codex_implement.*` / `run.codex_revise.*` (`macos-service.md` §2.3), with the effective stall `max(stall, repo.test_timeout_min)` while a command runs.

---

## 9. How commits happen (coordinator-owned, RD-17)

Codex never commits: in workspace-write the linked worktree's git admin data lives in the mirror, outside the writable roots (RT §3.2; **ASM-B-19**), and the agent uid has read-only access to the mirror. Even if commits worked, the coordinator keeps commit authority so that the gates are mandatory.

**Git hardening (applies to every coordinator git invocation, not only commits):**

- Never run git with configuration discovered from an agent-writable directory. Every invocation sets `GIT_DIR` explicitly to the mirror or to the worktree's admin directory inside the mirror (`<mirror>/worktrees/<name>/`, coordinator-writable, agent read-only), and `GIT_WORK_TREE` to the worktree, which is read as data only.
- Before every invocation, verify that the worktree's `.git` entry is a regular file (not a symlink) whose content is exactly `gitdir: <mirror>/worktrees/<name>`, and that the admin directory's `commondir` and `gitdir` files point back as expected. A mismatch is `policy_violation` (worktree quarantined).
- Fixed options: `-c core.hooksPath=/dev/null -c core.fsmonitor= -c core.untrackedCache=false -c protocol.allow=never -c core.sshCommand=/usr/bin/false -c core.attributesFile=/dev/null -c diff.external= -c core.pager=cat -c commit.gpgsign=false`; environment `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, `GIT_OPTIONAL_LOCKS=0`, `GIT_NO_REPLACE_OBJECTS=1`, `GIT_ATTR_NOSYSTEM=1`; diffs with `--no-textconv --no-ext-diff`.
- The mirror's own config is coordinator-written, includes `core.fsync=committed,reference`, and its hash is verified at startup.

**Pipeline after a successful implementation run** (one `git_step` run; idempotent with key `git:commit:<run_id>`; if the branch tip already carries `Mercury-Run: <run_id>`, the step is skipped):

1. **Snapshot of changes.** Using a coordinator-owned temporary index (`GIT_INDEX_FILE=<run_dir>/commit.index`) seeded with `read-tree tasks.last_commit_sha` (or `base_sha`), stage the worktree with `add -A` and compute `diff --cached --binary --no-renames`. Files are read with `O_NOFOLLOW`-equivalent checks; a path whose components resolve outside the worktree is rejected (SEC-404).
2. **Diff gate** (deterministic; any hit leaves the run `rejected_by_gate`). Classes and lists come from SEC-310 and the repo policy:
   - **Block class** (SEC-310; agent configuration, governance, editor auto-run): e.g. `.github/**`, `CODEOWNERS`, `.gitattributes`, `.gitmodules`, `AGENTS*.md`, `CLAUDE.md`, `.claude/**`, `.mcp.json`, `.codex/**`, `.agents/**`, `.husky/**`, `.vscode/**`, `.idea/**`, `.devcontainer/**`, `.envrc`, `.tool-versions`, `.npmrc`, `.yarnrc*` (RE-13). A hit is a security policy violation (SM T19).
   - **Escalate class** (SEC-310; allowed only if the authorization and approved plan list them; then `MERCURY / policy` requires operator acknowledgement, `github.md` §6.2): dependency manifests and lockfiles (lockfile lint, SEC-702), build scripts, other SEC-310 escalate classes.
   - Also rejected: paths in `authorization.scope.denied_paths`; symlinks whose target is absolute or escapes the repository; new executable bits not allowed by the plan; files over `gate.max_file_bytes` or binaries not listed in the plan; total diff over `gate.max_changed_lines`; submodule changes; `..` path components and APFS case-insensitive collisions (SEC-403); Unicode bidi controls, zero-width characters in identifiers and mixed-script identifiers (SEC-312).
3. **Secret scan (SEC-502).** Pinned `gitleaks` (or equivalent) on the staged diff, plus MERCURY's own patterns (GitHub tokens, `sk-ant-`, `sk-`, `lin_api_`, PEM headers) and exact-match of every secret value the coordinator holds (SEC-501). A hit blocks the run and raises a security escalation; only the rule id and path are recorded.
4. **Scope report.** Paths outside the plan's file list but inside the authorization scope are allowed and listed for Claude review and the PR body.
5. **Commit via plumbing.** `write-tree` → `commit-tree <tree> -p <parent> -F <msg>` with author and committer `mercury-bot[bot] <APP_ID+mercury-bot[bot]@users.noreply.github.com>` (message format and trailers: `github.md` §4.2) → `update-ref refs/heads/<branch> <new> <old>` (compare-and-set) in the mirror → update the worktree's index in the admin directory to the new commit (`read-tree` with the explicit `GIT_DIR`).
6. **Durability (RD-11).** Order: git commit (objects and ref fsynced by `core.fsync`) → DB transaction recording `tasks.last_commit_sha`. Recovery verifies `git cat-file -e` and the ref before trusting a recorded SHA.
7. **Push.** From the mirror, never from the worktree (`github.md` §4.3).

Checkpoint commits do not exist; the only commits are the ones created by this pipeline (RD-11).

---

## 10. Where tests run (decision, RD-17)

**Two local layers plus CI.** Codex runs tests inside its sandbox while iterating (advisory). The coordinator then runs the authoritative `verify` run as the agent uid. GitHub CI is the third, independent gate.

| Layer | Who and how | Environment | Gate? |
|---|---|---|---|
| L1 | Codex, inside its run | Codex Seatbelt workspace-write, no network, agent uid | No; recorded as `codex_test_observations` |
| L2 `verify` | `agent-exec` (spec `kind: verify`), as `_mercuryagent` | `sandbox-exec -f profiles/verify.sb` (root-owned, fail-closed; E designs, D installs; SEC-206, SEC-703): **no network**, writes only to the worktree and run scratch, denies Keychain/`securityd` lookups (RE-29); environment as §6 **without** any model key; awake deadline `repo.test_timeout_min` | **Yes.** Produces `mercury.test.results.v1` (`source = local_verify`). No push unless every required command passes, or the plan declared the exact known failures, which Claude's PR review must accept |
| L3 | GitHub Actions | GitHub-hosted runners, on the pushed head SHA; must run on draft PRs (`github.md` §9.4) | **Yes**, through required checks |

Rules:

- **Commands come from MERCURY's per-repo config** (`repos.<owner/name>.test_commands`, `setup_commands`, toolchain manifest), never from repository files Codex can edit.
- **`deps_install`** (`agent-exec`, spec `kind: deps_install`, `sandbox-exec -f profiles/deps.sb`, agent uid) runs before implementation when the repo config requires it: lockfile-only installs with lifecycle scripts disabled (`npm ci --ignore-scripts` and per-ecosystem equivalents), egress limited to the registry allowlist, no credentials. A lockfile **changed by this task** is installed only after its change has been acknowledged through `MERCURY / policy` (`github.md` §6.2); until then `verify` runs against the base lockfile's dependencies and any resulting failure is reported as such. Codex never has network (OD-09).
- Both `verify` and `deps_install` are detached and adoptable like Codex runs (RD-11).

---

## 11. Exit-code and failure mapping

Codex `exec` exits 0 or 1 (RT §3.1). Classification uses the exit status, JSONL and stderr patterns (versioned per pinned Codex version, covered by contract tests). Accounting follows `github.md` §15.1; attempt caps per run kind are in SM §7.1.

| Observation | Class | Next step |
|---|---|---|
| exit 0, `final.json` present and Ajv-valid against the canonical schema, semantic checks pass | `success` | — |
| exit 0, `final.json` missing or invalid (**ASM-B-21**) | `output_invalid` | One resume with "Return only the JSON object for the schema" |
| exit 0, `status = "partial"` | `incomplete` | One resume; then the same path as `blocked` (RC-13) |
| exit 0, `status = "blocked"` | `blocked_by_agent` | `CHANGES_REQUESTED` with source `codex_deviation` → Claude `revision_request` decides `revise`, `replan` or `escalate` (RC-13) |
| exit 0, `status = "needs_plan_change"` | — (result) | SM T17 |
| exit 1, `turn.failed`/`error` with 429, rate limit, overloaded, 5xx or stream disconnect | `transient_api` | Backoff `backoff.model_api`; resume if a thread exists |
| exit 1, connection or DNS errors while the connectivity probe fails within the probe window | `network_down` | Not an attempt; wait for the probe |
| exit 1, 401/403 or invalid key | `agent_auth_failed` | `agent_auth_failed{codex}` hold; notify |
| exit 1 before `thread.started` with config, `strict-config` or trust errors; or a provider schema rejection (`invalid_json_schema`, RB-01) | `config_fatal` | `config_fatal` hold for Codex dispatch; notify |
| killed by coordinator at the awake deadline | `timeout` | Consumes a **run attempt** only, never a revision budget (RC-08) |
| killed by coordinator for stall (§8) | `stalled` | Consumes a run attempt; resume (no reset happened) |
| exit > 1 or a signal not from MERCURY | `crash` | Consumes a run attempt; reset per §12.3, then a fresh thread |
| boot session changed or supervisor lease lost | `lost_by_host` | No attempt; separate cap per step; ops alert |
| diff gate (non-security rule) | `rejected_by_gate` | SM T18 → Claude `revision_request` (source `diff_gate`) |
| diff gate security class, secret-scan hit, `mcp_tool_call`/`web_search`, `.git` pointer mismatch | `policy_violation` | SM T19 `BLOCKED(security_policy_violation)`; worktree quarantined |
| L2 `verify` fails | result, not a failure class | SM T21 → Claude `revision_request` (source `local_tests`) |

---

## 12. Deadlines, kill procedure, adoption and reset

### 12.1 Deadlines (parameter keys)

| Run kind | Deadline and stall (`macos-service.md` §2.3) |
|---|---|
| `codex_plan` (initial and revision) | `run.codex_plan.*` |
| `codex_implement` / `codex_revise` | `run.codex_implement.*` / `run.codex_revise.*` (an authorization's limit may lower the deadline) |
| `verify` | `run.verify.*` (deadline = `repo.test_timeout_min`) |
| `deps_install` | `run.deps_install.*` |

### 12.2 Kill and adoption

- Kill sequence through `agent-ctl signal --run <run_id> --sig …` with the `supervisor.kill_ladder_s` ladder: SIGINT to the group (Codex ends the turn and exits 1), then SIGTERM, then SIGKILL; then verify through `agent-ctl probe` / `agent-ctl list` that no process with the run's pgid, start time and marker remains.
- `agent-exec` independently enforces the hard awake deadline and the supervisor lease (`WORK_ROOT/ctl/coordinator.alive` older than `supervisor.lease_stale_min` → kill ladder, `exit.json{reason: supervisor_lost}`).
- **Adoption after a coordinator restart (RD-11, ADR-020).** Codex, `verify` and `deps_install` runs are detached with file stdio and are adopted when the identity triple matches (`run_id` marker, start time, boot session). The coordinator re-reads `stdout.jsonl` from the start (recovering the thread id), resumes tailing, and **re-evaluates the authorization guard before acting on an adopted run's output**. Adopted runs are never kept through safe mode or a `security_halt`.
- On SIGTERM of `mercuryd`: stop dispatch, keep adoptable runs, interrupt non-adoptable (Claude) runs, checkpoint, exit within `ExitTimeOut`.

### 12.3 Worktree reset

The single reset policy is defined by Agent C (`components.md` §9): archive uncommitted changes as a patch artifact, `reset --hard tasks.last_commit_sha` (or `base_sha`), `clean -ffd`, adding `-x` only when `deps_install` is re-queued in the same step. It runs as a coordinator `git_step` with the hardening of §9, and file removal goes through `agent-ctl purge` where the agent owns the files. After any reset the next Codex run starts a fresh thread (§3.4).

---

## 13. Version pinning and self-test

- `@openai/codex` is pinned to an exact version, installed by `mercury toolchain sync` under `WORK_ROOT/toolchains/agents/` (coordinator-owned, agent read/execute); its SHA-256 is pinned in `agent.conf` and checked by `agent-exec` at every spawn and by `mercury doctor` at start (SEC-210). The operator's global `codex` is never used.
- If the pinned version supports a managed `requirements.toml` that pins sandbox and approval settings (ASM-E-10), the coordinator uses the root-owned managed `requirements.toml` (OD-19, `macos-service.md` §7.1); otherwise the generated `config.toml` plus `--strict-config` is the control.
- **Startup self-test** (hard gate for Codex dispatch), run through the production path (`agent-exec`, agent uid) against a bundled fixture repository:
  1. `codex --version` matches the pin; `codex exec --help` lists `--json`, `--output-schema`, `-o`, `--sandbox`, `--strict-config`, `--ignore-rules`, `--cd`.
  2. Each `codex-strict` wire schema is accepted (ASM-B-61).
  3. A read-only planning run produces schema-valid output and leaves the worktree unchanged.
  4. A workspace-write run asked to `curl https://example.com` and to `git commit` reports both as failed (network off, `.git` admin data not writable; ASM-B-19).
  5. The fixture contains `.codex/config.toml` with a hook that would touch a canary; the canary is not touched (RE-19).
  6. A run asked to `cat` canary files in the operator's home and `MERCURY_HOME` into the worktree fails with a permission error (SEC-T-20 subset); the secret scan would also catch the content.
- **Contract tests** per pinned version: JSONL event types match the captured `index.d.ts` (RT §6 V6); the argv the coordinator generates is accepted by the `agent-exec` grammar.
