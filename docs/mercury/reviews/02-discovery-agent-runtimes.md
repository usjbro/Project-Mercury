# Discovery: Agent Runtimes (Claude Code and OpenAI Codex CLI)

**Author:** Agent B (Solutions Architect), Phase 1 capability research
**Date:** 2026-10-12
**Status:** Discovery input to the TDD. This is not a design decision.
**Scope:** What each runtime can do programmatically and unattended on a Mac, and what that means for how the MERCURY coordinator should drive them.

## Evidence markers

Every claim carries one of these markers.

| Marker | Meaning |
|---|---|
| **[V-doc]** | Verified against official Anthropic docs (code.claude.com) fetched on 2026-10-12. |
| **[V-cli]** | Verified from `claude --help` output of Claude Code **2.1.296** installed in this container. |
| **[V-src]** | Verified by reading OpenAI Codex source at git tag **`rust-v0.162.1`** (github.com/openai/codex), or the published npm package **`@openai/codex-sdk@0.162.1`** / **`@openai/codex@0.162.1`**. Nothing was executed. |
| **[V-web]** | Seen in a web search summary of an official page, but the page itself could not be fetched. Medium confidence. |
| **[I]** | Inferred from verified facts. Not directly stated anywhere. |
| **[UNVERIFIED]** | Could not be confirmed. Do not rely on it until it is checked on the Mac. |

**Access limitation.** `developers.openai.com` was blocked by this container's egress proxy (HTTP 403 on CONNECT). The Codex repo's `docs/*.md` files now only point to that site. Codex facts therefore come from the **source code and the shipped npm packages at the latest release (0.162.1, published 2026-10-10)**. For behaviour, that is more authoritative than prose docs. Option names and defaults may still differ from what the documentation describes. Phase 0 on the Mac must re-check them with `codex exec --help`.

**Versions at research time.** These are the versions observed. The versions on the Mac are unknown.

- Claude Code CLI: 2.1.296 [V-cli]
- `@anthropic-ai/claude-agent-sdk`: 0.3.296 on npm [V-src (npm registry)]
- `@openai/codex` and `@openai/codex-sdk`: 0.162.1 latest, with a 0.163.0 alpha also published [V-src (npm registry)]

---

## 1. Summary

1. **Both runtimes can run headless with machine-readable output and schema-validated final answers.**
   - Claude: `claude -p --output-format json|stream-json --json-schema …` or the TypeScript Agent SDK with `outputFormat`.
   - Codex: `codex exec --json --output-schema FILE -o FILE`.
   - Both can resume sessions by ID, so the coordinator can drive plan → review → revise loops.
2. **The Claude Agent SDK is the richer control surface.** It offers:
   - an in-process permission callback (`canUseTool`)
   - in-process hook callbacks
   - in-process MCP tools (`createSdkMcpServer`)
   - `interrupt()`
   - `maxTurns` and `maxBudgetUsd`
   - typed result messages with cost and usage

   The SDK still **spawns the Claude Code binary as a subprocess** [V-doc], so it gives no stronger isolation than the CLI.
3. **The Codex TypeScript SDK is a thin wrapper.** It spawns `codex exec --experimental-json` and parses JSONL [V-src]. It adds no permission callbacks or hooks. The coordinator gains little from it compared with running `codex exec` directly.
4. **Codex as an MCP server (`codex mcp-server`) does not exist in 0.162.1.** The top-level command list has no such subcommand, and the `codex mcp` subcommands are only list/get/add/remove/login/logout [V-src]. An OpenAI docs page says the command was removed in favour of `codex app-server` [V-web]. `app-server` is labelled **"[experimental]"** in the CLI [V-src] and its JSON-RPC surface changes often. **Do not build on either.**
5. **Codex `exec` always runs with `approval_policy = never`** (unless the "auto-review" reviewer is configured) [V-src]. The **sandbox mode is the real control**:
   - `read-only` for planning
   - `workspace-write` for implementation
   - `network_access` defaults to **false** in workspace-write [V-src]

   **`--full-auto` no longer exists** in 0.162.1. `on-failure` is now only an alias of `on-request` [V-src].
6. **Critical security finding (Claude).** `claude -p` and Agent SDK sessions **never show the workspace-trust dialog**. They **run the hooks in a repository's `.claude/settings.json` and connect its `.mcp.json` servers without asking** [V-doc].
   - If Claude reviews a Codex-produced worktree with default settings, Codex-written files could execute code under Claude's identity.
   - Mitigations: `--bare`, `settingSources: []` / `--setting-sources user`, `--strict-mcp-config`, and `--settings '{"disableAllHooks":true}'` [V-doc]. These **must** be part of the design.
7. **Critical finding (Codex).** In workspace-write, Codex protects `.git`, `.codex`, `.agents` and `.aws` under writable roots [V-src].
   - **[I]:** In a linked git worktree, `git commit` writes into the main repository's `.git/worktrees/...` and object store. That is outside the worktree and inside a protected name, so it will likely be denied.
   - **Preliminary view:** the coordinator, not Codex, performs commits, pushes and PR creation. This also fits least-privilege, because agents never hold GitHub write credentials. Verify on the Mac.
8. **Unattended authentication**
   - **Claude:** Use a Console API key (`ANTHROPIC_API_KEY` or `apiKeyHelper`). The subscription route is `claude setup-token`, which produces a one-year OAuth token in `CLAUDE_CODE_OAUTH_TOKEN`. It is ignored in `--bare` mode [V-doc]. The Agent SDK docs say third-party products may not use claude.ai login without approval [V-doc]. Whether that applies to a personal tool on the operator's own Mac is an **open question for the operator** (Section 8).
   - **Codex:** Use `CODEX_API_KEY` (honoured by `exec`) [V-src], or a ChatGPT login stored in `$CODEX_HOME/auth.json`. File storage is the default [V-src].
9. **Neither runtime has a whole-run wall-clock timeout flag.**
   - Claude has `--max-turns` and `--max-budget-usd`.
   - Codex exits `1` on a failed or interrupted turn [V-src].
   - The coordinator must enforce deadlines and kill process trees itself. Claude exits `143` on SIGTERM [V-doc].
10. **Preliminary recommendation**
    - **Claude:** Agent SDK (TypeScript), pinned exactly, for all decision and review calls. Use isolation options (`settingSources: []`, explicit `tools`, `canUseTool` deny-by-default, `outputFormat`). Keep CLI `claude -p --bare` as a documented fallback.
    - **Codex:** Drive `codex exec` as a supervised subprocess. Use `--json --output-schema -o --cd <worktree> --sandbox <mode>`, a pinned version, and a controlled environment.
    - **Coordinator:** Owns git commit/push and PR creation.

---

## 2. Claude Code capabilities

### 2.1 Headless CLI (`claude -p`)

| Capability | Detail | Evidence |
|---|---|---|
| Non-interactive run | `claude -p "<prompt>"`. Reads stdin, which is capped at 10 MB. Not every flag combines with `-p` (for example `--bg` is rejected). | [V-doc] headless; [V-cli] |
| Output formats | `--output-format text\|json\|stream-json`. `json` returns one object with `result`, `session_id` and metadata. `stream-json` is NDJSON whose last line is a `result` message. | [V-doc] headless, cli-reference |
| Streaming input | `--input-format stream-json` gives realtime streaming input. `--replay-user-messages` echoes input back for acknowledgement. | [V-doc]; [V-cli] |
| Structured output | `--json-schema '<schema>'` (print mode only). The output appears in the `structured_output` field of the JSON result. An invalid schema causes a startup error (v2.1.205+). The `format` keyword is not enforced. | [V-doc] headless, cli-reference |
| Turn limit | `--max-turns N` (print mode). "Exits with an error when the limit is reached. No limit by default." **It is not listed in `claude --help`**, but it is documented. The docs say `--help` "does not list every flag". | [V-doc]; absence from help [V-cli] |
| Budget limit | `--max-budget-usd <amount>` (print mode). Uses a client-side estimate and "Spend can pass the cap". | [V-doc]; [V-cli] |
| Resume / session ID | `--resume <id\|name\|path.jsonl>`, `--continue`, `--session-id <uuid>` (a preassigned UUID, useful as a coordinator-chosen correlation key), `--fork-session`, `--no-session-persistence`. | [V-doc]; [V-cli] |
| Permission mode | `--permission-mode default\|manual\|acceptEdits\|plan\|auto\|dontAsk\|bypassPermissions`. Without the flag, a `-p` run "takes the built-in starting permission mode, which can be `auto`", **so always pass it explicitly**. | [V-doc]; [V-cli] |
| Unattended prompts | `--permission-prompts none` (v2.1.259+) denies anything that would prompt and removes `AskUserQuestion`. With stream-json, denials appear as `permission_denied` messages and in `permission_denials` on the result. | [V-doc]; [V-cli] |
| Tool control | `--tools "Read,Grep,Glob"` restricts which built-in tools exist. `--allowedTools` auto-approves (it does not restrict). `--disallowedTools` removes tools (bare name) or denies matching calls (scoped rule). `--tools` does not affect MCP tools; use `--disallowedTools "mcp__*"` for those. | [V-doc] cli-reference |
| Settings injection | `--settings <file-or-json>` overrides keys for this session. `--setting-sources user,project,local` selects which files load. | [V-doc]; [V-cli] |
| MCP config | `--mcp-config <files-or-json>` with `--strict-mcp-config` (only those servers). With `-p`, it waits up to `MCP_TIMEOUT` (30 s default) for servers. `system/init` reports `mcp_servers` and `mcp_server_errors`. | [V-doc] |
| System prompt | `--append-system-prompt[-file]`, `--system-prompt[-file]`. The system prompt is snapshotted on first request and reused on resume until compaction (`--system-prompt-snapshot`). | [V-doc] cli-reference |
| Extra dirs | `--add-dir <dirs>` grants file access but does not load most `.claude/` config from those dirs. | [V-doc] |
| Bare mode | `--bare` skips auto-discovery of hooks, skills, plugins, MCP servers, CLAUDE.md and auto-memory. **Auth is strictly `ANTHROPIC_API_KEY` or `apiKeyHelper` via `--settings`.** OAuth and keychain are never read, and `CLAUDE_CODE_OAUTH_TOKEN` is ignored. Docs: "recommended mode for scripted and SDK calls, and will become the default for `-p` in a future release." | [V-doc] headless, authentication; [V-cli] |
| Restricted mode | `--restricted` (v2.1.248+) removes code-running tools and WebFetch unless named in `--tools`. It ignores user/project/local settings, confines file tools to working dirs, and refuses `bypassPermissions`. | [V-doc]; [V-cli] |
| Cost / usage | JSON result includes `total_cost_usd` and a per-model breakdown (`modelUsage`), plus `usage`, `num_turns`, `duration_ms`, `duration_api_ms`, `is_error`, `permission_denials`, `stop_reason`. Costs are **client-side estimates**. On resume, totals include earlier runs. | [V-doc] headless; SDK type in 2.2 |
| Result subtypes | `success`, `error_max_turns`, `error_during_execution`, `error_max_budget_usd`, `error_max_structured_output_retries`. `success` without `structured_output` must also be treated as a failure. | [V-doc] SDK typescript, structured-outputs |
| Exit codes | 0 on success, non-zero on failure. Invalid flags go to stderr before the run. Failures inside the run (for example missing auth) are printed **as the result on stdout**. **SIGTERM gives exit 143**, kills running Bash process trees, runs `SessionEnd` hooks, and leaves the turn unfinished. Send SIGINT or `interrupt()` first for a clean turn end. | [V-doc] headless |
| Background waits | After the turn, `-p` may wait for background work (default idle cap 10 min, `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`). | [V-doc] headless |
| Retry events | `system/api_retry` events carry `attempt`, `max_retries`, `retry_delay_ms`, `error_status` and an `error` category (e.g. `rate_limit`, `authentication_failed`, `billing_error`). | [V-doc] headless |
| Worktrees | `-w/--worktree [name]` creates `<repo>/.claude/worktrees/<name>`. **[I]** MERCURY should manage worktrees itself rather than use this. | [V-doc]; [V-cli] |

### 2.2 Claude Agent SDK (TypeScript, `@anthropic-ai/claude-agent-sdk`)

| Capability | Detail | Evidence |
|---|---|---|
| Packaging | Ships a native Claude Code binary as a platform optional dependency (e.g. `…-darwin-arm64`) and **spawns it as a subprocess**. `pathToClaudeCodeExecutable` overrides the binary and `spawnClaudeCodeProcess` takes over spawning. | [V-doc] SDK typescript |
| Entry point | `query({ prompt: string \| AsyncIterable<SDKUserMessage>, options }) → Query` (an `AsyncGenerator<SDKMessage>`). | [V-doc] |
| Key options | `permissionMode`, `canUseTool`, `hooks`, `mcpServers` (stdio/sse/http/**sdk** in-process), `allowedTools`, `disallowedTools`, `resume`, `sessionId`, `forkSession`, `abortController`, `maxTurns`, `maxBudgetUsd`, `outputFormat: {type:'json_schema', schema}`, `settingSources`, `cwd`, `additionalDirectories`, `systemPrompt` (string or `{type:'preset',preset:'claude_code'}`), `env` (**replaces** the subprocess environment), `sandbox`. | [V-doc] |
| **settingSources default** | **When omitted, all three sources (user, project, local) load.** Pass `[]` to disable. Security-relevant: see 2.6. | [V-doc] |
| Custom tools | `tool(name, desc, zodSchema, handler, {annotations})` and `createSdkMcpServer({name, tools, …})`. These are in-process MCP tools that the coordinator implements, e.g. `submit_plan_review`. | [V-doc] |
| Permission callback | `canUseTool` runs **only when the permission flow falls through to a prompt**. It returns `{behavior:"allow"\|"deny"}`. Deny rules in settings and `disallowedTools` scoped rules apply before it, "in every mode, including `bypassPermissions`". | [V-doc] |
| Hooks | All 33 `HookEvent` values are available as callbacks, including `PreToolUse`, `PostToolUse`, `PermissionRequest`, `PermissionDenied`, `Stop`, `SessionStart`/`SessionEnd`, `SubagentStart`/`SubagentStop`. | [V-doc] SDK typescript, hooks |
| Control | `Query.interrupt()`, `close()`, `setPermissionMode()`, `setModel()`, `stopTask()`, `streamInput()`, `mcpServerStatus()`, `accountInfo()`, `rewindFiles()` (needs file checkpointing). | [V-doc] |
| Structured output | `outputFormat` validates against JSON Schema **draft-07** and re-prompts on mismatch. On failure, subtype is `error_max_structured_output_retries`. A single-shot `query()` **throws after yielding an error result**. | [V-doc] structured-outputs |
| Result type | `SDKResultMessage` includes `session_id`, `total_cost_usd`, `usage` (main loop only), `modelUsage` (all models, including subagents; use this for accounting), `permission_denials` (authoritative), `errors[]` on error subtypes, and `num_turns`. | [V-doc] |
| Changelog | github.com/anthropics/claude-agent-sdk-typescript/blob/main/CHANGELOG.md. Version 0.3.x tracks the CLI 2.1.x build number (0.3.296 ↔ 2.1.296), but the mapping is **[I]**. | [V-doc]; [I] |

### 2.3 Hooks

| Topic | Detail | Evidence |
|---|---|---|
| Events | 33 events: Session (`SessionStart`, `Setup`, `SessionEnd`), turn (`UserPromptSubmit`, `Stop`, `StopFailure`), tool loop (`PreToolUse`, `PermissionRequest`, `PermissionDenied`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`), subagents/tasks, compaction, config/env (`ConfigChange`, `CwdChanged`, `FileChanged`, `WorktreeCreate`/`Remove`), and `Notification`/`Elicitation`. | [V-doc] hooks |
| Types | `command`, `http`, `mcp_tool`, `prompt`, `agent` (experimental). | [V-doc] |
| Blocking | Exit code 2 blocks, and stderr becomes the reason. Alternatively, JSON `hookSpecificOutput.permissionDecision: allow\|deny\|ask\|defer`. "Staying silent doesn't approve it." Exit 2 blocks even if the JSON says allow. | [V-doc] |
| Precedence | Settings **deny and ask rules are still evaluated after a hook returns "allow"**: a hook cannot override a deny. A hook exiting 2 blocks before rules are evaluated. | [V-doc] permissions |
| Timeouts | Default 600 s for command/http/mcp_tool, 30 s for prompt, 60 s for agent. **A timed-out hook does not block by default.** `"onFailure":"block"` changes this (v2.1.295+). | [V-doc] hooks |
| Managed lock-down | Managed `allowManagedHooksOnly` blocks user, project, local and plugin hooks. | [V-doc] |
| Guidance | Docs warn that `if` filters are best-effort: "use the permission system rather than a hook to enforce a hard allow or deny." | [V-doc] |

### 2.4 Permission rules, settings precedence, managed settings

- **Rule evaluation:** deny → ask → allow, first match wins, and specificity does not reorder it. A broad deny cannot be carved out by a narrower allow. Deny rules from any scope beat allows from any scope. [V-doc] permissions
- **Rule syntax:** for example `Bash(git diff *)`, where the space before `*` matters; also `Read(...)`, `Edit(...)`, `WebFetch(domain:…)`, `mcp__server__tool`. [V-doc] headless, permissions
- **Precedence:** managed > command line > local > project > user. "No other level, including command line arguments, can override a managed permission rule." [V-doc] permissions
- **Managed settings on macOS:**
  - file: `/Library/Application Support/ClaudeCode/managed-settings.json`, optional `managed-settings.d/`, and `managed-mcp.json`
  - MDM preference domain: `com.anthropic.claudecode`
  - **An unparseable managed source makes Claude Code refuse to start.** [V-doc] managed-settings
- **Lock-down keys:**
  - `permissions.disableBypassPermissionsMode: "disable"` and `permissions.disableAutoMode: "disable"` work from any scope and are strongest in managed settings.
  - `allowManagedPermissionRulesOnly` (managed only) [V-doc]
  - `allowedProviders` (managed, v2.1.285+) [V-doc] authentication
- **[I]:** A root-owned managed-settings file on the Mac is a software-enforced control (Section H of the brief). Even a compromised agent prompt cannot loosen it, provided the agent cannot write `/Library/Application Support/ClaudeCode/`.

### 2.5 Sandboxing (Claude Code Bash sandbox)

- **Scope:** OS-enforced around **shell commands only** (Bash, PowerShell, Monitor and their children). **The file tools (Read/Edit/Write), WebFetch, MCP servers and hooks run outside the sandbox** and are governed by permission rules instead. [V-doc] sandboxing
- **Platform:** macOS uses built-in **Seatbelt**. Linux and WSL2 use bubblewrap + socat. [V-doc]
- **Default writes:** cwd, per-user temp, and added dirs. Protected paths stay write-denied. **Default reads cover most of the machine, including `~/.ssh` and `~/.aws/credentials`, unless `filesystem.denyRead` is set.** [V-doc]
- **Network:** no direct route out. All traffic goes through a local proxy checking `network.allowedDomains` (empty by default). [V-doc]
- **Keys:**
  - `sandbox.enabled`, `autoAllowBashIfSandboxed` (default true), `excludedCommands`
  - `allowUnsandboxedCommands` (set **false** to disable the `dangerouslyDisableSandbox` retry escape hatch; "Strict sandbox mode")
  - `failIfUnavailable` (exit instead of running unsandboxed)
  - `filesystem.allowWrite/denyWrite/denyRead/allowRead`, `network.allowedDomains/deniedDomains`
  - `credentials` (deny or mask secrets; masking needs `network.tlsTerminate`)

  [V-doc]
- **Escape hatch:** a matching allow rule such as `Bash(curl *)` **also approves an unsandboxed retry**. [V-doc]
- **[I] Implication:** For Claude in the reviewer role, the simplest strong control is **not giving Claude Bash at all** (`--tools "Read,Grep,Glob"`). If Bash is required (e.g. to run tests during review), set `sandbox.enabled:true`, `allowUnsandboxedCommands:false` and `failIfUnavailable:true`, with denyRead over credential paths.

### 2.6 Repository-content trust under `-p` / SDK (security-critical)

The docs state that a `claude -p` run or an SDK session **never shows the trust dialog** [V-doc] permissions. For a folder that was never trusted:

| What the repo supplies | Behaviour under `-p` or the SDK |
|---|---|
| Hooks in `.claude/settings.json`, the `env` block, and helpers like `apiKeyHelper` | **Used** |
| `permissions.allow` rules in project settings | Not used (a warning is printed) |
| Servers in `.mcp.json` | **Connected without asking.** The SDK connects them only when `settingSources` includes project. |

Documented mitigations [V-doc]:

- `--setting-sources user` or SDK `settingSources` without `project`
- `--bare`
- `--settings '{"disableAllHooks": true}'`. Setting this in user settings alone is not enough, because project settings outrank user settings.
- `disabledMcpjsonServers`

**[I] MERCURY implication.** Every Claude invocation that touches a Codex-modified worktree or an untrusted PR checkout must run with the following. Contract tests (brief §J) should assert that a planted `.claude/settings.json` hook in a worktree does **not** execute.

- `settingSources: []` (SDK) or `--bare` (CLI)
- `--strict-mcp-config` with coordinator-supplied MCP only
- explicit `tools`
- `disableAllHooks: true` injected via `--settings` (or SDK hooks supplied in-process only)

### 2.7 Subagents

- Defined via `--agents <json|file>` (the file form needs v2.1.281+), `.claude/agents/`, or the SDK `agents` option. Subagent messages carry `parent_tool_use_id` in stream-json. `--forward-subagent-text` includes their text. Subagent spend counts toward `--max-budget-usd`. [V-doc] cli-reference, headless
- **[I]:** MERCURY can use a subagent for a dedicated "security review" pass inside one Claude review call. Separate top-level calls give cleaner audit records, though.

### 2.8 Authentication for unattended use

Precedence order [V-doc] authentication:

1. Cloud provider env (Bedrock, Vertex, Foundry)
2. `ANTHROPIC_AUTH_TOKEN`
3. `ANTHROPIC_API_KEY` (always used in `-p` when present)
4. `apiKeyHelper`
5. `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`; a one-year subscription token, model requests only, **not read in `--bare`**)
6. Anthropic profiles / WIF
7. Subscription `/login` OAuth

Storage and status:

- **macOS storage:** credentials live in the **Keychain**. "When the Keychain rejects the write, such as when it's locked in an SSH session, Claude Code stores your login in `~/.claude/.credentials.json` (0600)". `CLAUDE_CONFIG_DIR` keys a separate Keychain entry and config dir. [V-doc]
- **Status check:** `claude auth status` returns JSON. It exits 0 if logged in and 1 if not, and reports `authMethod` (`none|claude.ai|oauth_token|api_key|api_key_helper|third_party`). [V-doc] cli-reference
- **Policy:** "Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods…" [V-doc] agent-sdk/overview.

**[I] Under launchd.**

- A **LaunchAgent** in the operator's GUI session (`gui/<uid>`) can generally read the login Keychain once it is unlocked. A **LaunchDaemon** cannot.
- An expired or locked Keychain means silent auth failures, surfaced as `authentication_failed` retry events or an error result.
- **Recommendation:** an API key provided through `apiKeyHelper`. The helper reads from a coordinator-owned Keychain item or a 0600 file. This works with `--bare` and avoids OAuth refresh and login-expiry problems in unattended sessions (the docs explicitly warn that unattended sessions "stop making progress once the credential expires").
- Verify the launchd and Keychain behaviour on the Mac in Phase 0.

### 2.9 MCP

- **Client:** transports stdio, HTTP (recommended), SSE (deprecated) and WebSocket. Scopes are local, project (`.mcp.json`) and user, with `managedMcpServers` and `managed-mcp.json` for admins. [V-doc] mcp
- **Server:** `claude mcp serve` runs a stdio MCP server that "only exposes Claude Code's tools to your MCP client". "Your own client is responsible for implementing user confirmation for individual tool calls." [V-doc]; [V-cli]
- **[I]:** This is not useful for MERCURY. It exposes tools rather than Claude's judgement, and moves permission enforcement onto the caller.

### 2.10 GitHub PRs

- Claude Code has no built-in PR API. It opens PRs by running `gh pr create` through Bash when it has `gh` credentials. `--from-pr` links sessions to PRs that "Claude creates". [V-doc] cli-reference
- There is also `claude ultrareview <PR> --post` (posts a comment from the user's GitHub account, using a cloud-hosted review). [V-doc]
- **[I]:** Not suitable here. It posts as the operator's account, which blurs agent and human identity (brief §E/§H).

---

## 3. Codex CLI capabilities

### 3.1 `codex exec` (non-interactive)

All entries are from `codex-rs/exec/src/cli.rs` and `codex-rs/utils/cli/src/shared_options.rs` at `rust-v0.162.1` [V-src] unless marked otherwise.

| Flag | Meaning (help text paraphrased or quoted) |
|---|---|
| `codex exec [OPTIONS] [PROMPT]` (alias `e`) | "If not provided as an argument (or if `-` is used), instructions are read from stdin." |
| `--json` (alias `--experimental-json`) | "Print events to stdout as JSONL." |
| `--output-schema <FILE>` | "Path to a JSON Schema file describing the model's final response shape." |
| `-o, --output-last-message <FILE>` | "File where the last message from the agent should be written." |
| `-C, --cd <DIR>` | "Tell the agent to use the specified directory as its working root." |
| `--add-dir <DIR>` | "Additional directories that should be writable alongside the primary workspace." |
| `--skip-git-repo-check` | "Allow running Codex outside a Git repository." Without it, exec exits 1 with "Not inside a trusted directory and --skip-git-repo-check was not specified." `--dangerously-bypass-approvals-and-sandbox` also skips this check. |
| `--ephemeral` | "Run without persisting session files to disk." **Incompatible with resume [I].** |
| `-m, --model <MODEL>` | Model. `--oss` / `--local-provider` select local providers. |
| `-p, --profile <NAME>` | "Layer `$CODEX_HOME/<name>.config.toml` on top of the base user config." **Note: a separate file per profile**, in addition to the `profiles` table in config.toml (schema key `profiles` exists). The interaction between the two is **[UNVERIFIED]**. |
| `-s, --sandbox read-only\|workspace-write\|danger-full-access` | "Select the sandbox policy to use when executing model-generated shell commands." |
| `--dangerously-bypass-approvals-and-sandbox` (alias `--yolo`) | "Skip all confirmation prompts and execute commands without sandboxing. EXTREMELY DANGEROUS. Intended solely for running in environments that are externally sandboxed." |
| `--approve-for-me` (alias `--not-so-yolo`) | Sets `approvals_reviewer="auto_review"`, `approval_policy="on-request"`, `sandbox_mode="workspace-write"` (a model-based auto-reviewer of approvals). |
| `--dangerously-bypass-hook-trust` | "Run enabled hooks without requiring persisted hook trust… DANGEROUS." |
| `--worktree` | "Run the session in a new managed Git worktree." **[I]** MERCURY should manage worktrees itself. |
| `-c, --config key=value` | TOML-literal config override, repeatable. This is how the SDK sets `approval_policy`, `sandbox_workspace_write.network_access`, `model_reasoning_effort` and `web_search`. |
| `--strict-config` | "Error out when config.toml contains fields that are not recognized by this version of Codex." **Useful for version-drift detection.** |
| `--ignore-user-config` | "Do not load `$CODEX_HOME/config.toml`; auth still uses `CODEX_HOME`." |
| `--ignore-rules` | "Do not load user or project execpolicy `.rules` files." |
| `-i, --image` | Attach images. |
| `codex exec resume [SESSION_ID\|--last] [PROMPT]` | Resume by UUID or thread name. `--all` disables cwd filtering. |
| `codex exec fork <SESSION_ID> [PROMPT]` | Fork a session. |
| `codex exec review --uncommitted\|--base B\|--commit SHA` | Non-interactive code review by Codex (also top-level `codex review`). |
| **`--full-auto`** | **Not present** in 0.162.1. Neither the shared options nor the exec CLI define it. Older docs and blogs use it, so treat it as removed. |
| `-a/--ask-for-approval` | Defined only in the **TUI** CLI (`tui/src/cli.rs`), not in exec. In exec, set approval via `-c approval_policy=…`. |

**Defaults in exec mode.**

- Approval: "Default to never ask for approvals in headless mode": `approval_policy: Some(AskForApproval::Never)`, unless the resolved reviewer is AutoReview. [V-src] `exec/src/lib.rs`
- Permission elicitation: requests from the server in exec mode are rejected ("permissions approval is not supported in exec mode") and mark the run as errored. [V-src]
- Sandbox: when no `--sandbox` is passed, the configured `sandbox_mode` or permission profile applies. The built-in default for an untrusted project is **[UNVERIFIED]** (historically `read-only`). **Always pass `--sandbox` explicitly.**

**JSONL events (`--json`).** Verified in `exec/src/exec_events.rs` and the SDK `index.d.ts` [V-src].

- `thread.started` {`thread_id`}
- `turn.started`
- `turn.completed` {`usage`: `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`}
- `turn.failed` {`error.message`}
- `item.started` / `item.updated` / `item.completed` {`item`}
- `error` {`message`}

Item types:

- `agent_message` (text, or JSON when an output schema is used)
- `reasoning`
- `command_execution` (`command`, `aggregated_output`, `exit_code`, `status`)
- `file_change` (`changes[{path, kind: add|delete|update}]`, `status`)
- `mcp_tool_call`
- `web_search`
- `todo_list`
- `error`

**There is no cost in USD, only token usage.** [V-src]

**Exit codes.** `exec` tracks `error_seen` and calls `process::exit(1)` when [V-src]:

- a non-retrying error notification arrives for the turn
- the turn completes with status `Failed` or `Interrupted`
- a server request cannot be handled
- config, cwd or `-c` parsing fails, or the git check fails

Otherwise it exits 0. No other distinct codes were found. **[I]:** MERCURY must classify failures from the JSONL plus stderr, not from the exit code.

**Timeouts.** No whole-run timeout flag exists in exec [V-src]. A config key `background_terminal_max_timeout` exists [V-src (schema)]. Its semantics and the per-command timeout behaviour are **[UNVERIFIED]**.

### 3.2 Sandbox and approvals

- **Modes:** `read-only`, `workspace-write`, `danger-full-access` (schema enum `SandboxMode`). [V-src]
- **`sandbox_workspace_write` table:** `writable_roots` (absolute paths, default `[]`), `network_access` (**default false**), `exclude_tmpdir_env_var` (default false), `exclude_slash_tmp` (default false). [V-src] `core/config.schema.json`
- **Newer permission profiles:** `default_permissions` (names starting `:` are built-ins) and a `[permissions.<name>]` table with per-path `filesystem` rules (e.g. `"/path/.env"="deny"`) and network domain rules. The SDK README shows `default_permissions: "audit"` with `permissions.audit.filesystem={":root"="read", …}`. [V-src] README/schema. **[I]** This appears to be the successor to `sandbox_mode`. Track it, because it may change.
- **macOS implementation:** Seatbelt via `/usr/bin/sandbox-exec`. The code deliberately uses only the `/usr/bin` path, to avoid PATH tampering. Policy files: `seatbelt_base_policy.sbpl`, `seatbelt_network_policy.sbpl`, among others. Linux uses Landlock and bubblewrap. [V-src] `codex-rs/sandboxing/src/`
- **Protected metadata:** `.git`, `.agents`, `.codex` and `.aws` "stay protected under writable roots". [V-src] `protocol/src/permissions.rs`. See Summary item 7 for the commit implication [I].
- **Approval policies:** `untrusted` (internal `UnlessTrusted`: "Commands require approval unless an explicit exec policy rule allows them"), `on-request` ("The model decides when to ask"), **`on-failure` is a serde alias of `on-request`**, `granular` (per-category booleans), and `never` ("Failures are immediately returned to the model, and never escalated"). [V-src] `protocol/src/protocol.rs`
- **Execpolicy:** `.rules` files (user and project) can allow, prompt or forbid commands. `codex execpolicy check` is hidden. Skip loading with `--ignore-rules`. [V-src]
- **Managed requirements:** `requirements.toml` sits next to the managed config path. `allow_managed_hooks_only = true` there ignores user, project and session hooks. A test shows `approval_policy = "never"` can be disallowed by requirements. [V-src] `docs/config.md`, `exec/src/lib_tests.rs`. The exact macOS path of managed config is **[UNVERIFIED]**.

### 3.3 config.toml and environment

- **Location:** `$CODEX_HOME/config.toml`. `CODEX_HOME` defaults to `~/.codex`. If `CODEX_HOME` is set, it must exist (startup errors otherwise). [V-src] `utils/home-dir`
- **Relevant keys** [V-src] schema: `model`, `model_provider(s)`, `model_reasoning_effort`, `approval_policy`, `approvals_reviewer`, `sandbox_mode`, `sandbox_workspace_write`, `default_permissions`, `permissions`, `shell_environment_policy`, `mcp_servers`, `notify`, `profiles`, `profile`, `projects` (per-path `trust_level: trusted|untrusted`), `hooks`, `project_doc_max_bytes` (default 32768), `project_doc_fallback_filenames`, `project_root_markers`, `cli_auth_credentials_store`, `forced_login_method` (`chatgpt|api`), `web_search`, `history`, `sqlite_home`, `log_dir`, `otel`.
- **`shell_environment_policy`:**
  - `inherit` controls the base set (enum values **[UNVERIFIED]**; historically `all|core|none`)
  - `ignore_default_excludes`
  - legacy `exclude` / `include_only` regex lists
  - newer keyed `filters`
  - `set`
  - `experimental_use_profile`

  [V-src] **[I]:** Set `inherit` to the minimal option plus an explicit `include_only`, so `GITHUB_TOKEN`, `ANTHROPIC_API_KEY` and similar never reach Codex's shell commands. Also pass a minimal `env` to the process itself.
- **`notify`:** "Optional external command to spawn for end-user notifications" (array argv). [V-src] **[I]** Not needed. The JSONL stream is the better signal.
- **AGENTS.md discovery** [V-src] `core/src/agents_md.rs`:
  1. Find the project root by walking up from cwd to a `project_root_markers` entry (default `.git`).
  2. Concatenate every `AGENTS.md` from the root down to cwd. An `AGENTS.override.md` is preferred where present, with fallback filenames configurable.
  3. Never walk past the root.
  4. Combine with user/home instructions using a separator. Total size is capped by `project_doc_max_bytes`.

  **[I] Security:** AGENTS.md is repository content and therefore untrusted (brief §H). Codex can edit it in `workspace-write`, because it is a file and not a protected directory. The coordinator should diff-guard instruction files.

### 3.4 Codex SDK, app-server and MCP

| Surface | Status | Evidence |
|---|---|---|
| `@openai/codex-sdk` (TS) | `new Codex({codexPathOverride, baseUrl, apiKey, config, configOverrides, env})` → `startThread({model, sandboxMode, workingDirectory, skipGitRepoCheck, approvalPolicy, networkAccessEnabled, webSearchMode, additionalDirectories, modelReasoningEffort})` → `thread.run()` / `runStreamed()`, with `outputSchema` and `signal: AbortSignal` per turn, and `resumeThread(id)`. The implementation spawns `codex exec --experimental-json …` and writes the prompt to stdin. A non-zero exit throws `Codex Exec exited with code N: <stderr>`. If `env` is given, the parent env is **not inherited**, and the SDK still injects `CODEX_API_KEY` if `apiKey` is set. The SDK depends on the exactly-pinned `@openai/codex` version. | [V-src] npm package `dist/index.js`, `index.d.ts`, README |
| `codex app-server` | "[experimental] Run the app server or related tooling." JSON-RPC with thread/turn APIs, approvals and streaming. The README is a list of fast-moving feature notes. `exec` itself is implemented on an in-process app-server client. | [V-src] `cli/src/main.rs`, `app-server/README.md`, `exec/src/lib.rs` |
| `codex mcp-server` | **Absent in 0.162.1** (no subcommand, no `mcp-server` crate). An OpenAI docs page (fr-FR) says it was removed and points to app-server. Third-party posts say it was deprecated in 0.149.x. | [V-src]; [V-web] |
| Codex as an MCP client | `mcp_servers` config. `codex mcp add\|list\|get\|remove\|login\|logout` supports stdio and streamable HTTP with OAuth. | [V-src] `cli/src/mcp_cmd.rs` |

### 3.5 Authentication

- **Login methods:** `codex login` (browser, or device code with `--device-auth`), `--with-api-key` ("Read the API key from stdin (e.g. `printenv OPENAI_API_KEY | codex login --with-api-key`)"), and `--with-access-token` (stdin). Passing `--api-key` directly is deprecated and exits with guidance. [V-src] `cli/src/main.rs`
- **Env vars:** `CODEX_API_KEY` takes precedence over other auth when the caller enables it, which `exec` does. `OPENAI_API_KEY` is read for login and providers. `CODEX_ACCESS_TOKEN` is also recognised. [V-src] `login/src/auth/manager.rs`, `exec/src/lib.rs`. A web summary of the official page says "CODEX_API_KEY is only supported in codex exec" and advises scoping it to the single invocation. [V-web]
- **Storage:** `cli_auth_credentials_store = file|keyring|auto|ephemeral`. **Default is `file`, i.e. `$CODEX_HOME/auth.json`.** [V-src] `config/src/types.rs`. MCP OAuth credentials default to `auto` (keyring if available). [V-src]
- **API keys and managed config:** API keys cannot fetch workspace-managed (cloud) configuration, according to a code comment. [V-src]
- **[I] Under launchd:** file-based auth avoids Keychain-access problems. However, ChatGPT tokens refresh and rewrite `auth.json`, and concurrent processes sharing one `CODEX_HOME` could race on that refresh **[UNVERIFIED]**. An API key (`CODEX_API_KEY`) avoids this. ChatGPT-plan billing versus API billing is an **operator decision**.

### 3.6 Known limitations and operational notes

- **Git requirement:** exec refuses to run outside a git repo unless `--skip-git-repo-check` is passed. A linked worktree satisfies this [I]. [V-src]
- **Concurrency:** multiple `codex exec` processes share `$CODEX_HOME` (sessions, sqlite state per `sqlite_home`, logs, auth). Safety under parallel use is **[UNVERIFIED]**. **[I]** Mitigation: a per-task `CODEX_HOME` (copying a minimal config, using `CODEX_API_KEY` for auth) or a strict concurrency limit of 1–2 with a serialised resume.
- **Sessions:** persisted under `~/.codex/sessions` (SDK README). `--ephemeral` disables them. [V-src]
- **No cost field:** budget control must be token-based in the coordinator. [V-src]
- **Hooks:** Codex has lifecycle hooks with a **trust** model. Unattended exec runs need persisted hook trust or the dangerous bypass flag. [V-src] **[I]** Do not rely on Codex hooks for enforcement. Use the sandbox, environment, and coordinator-side checks.

### 3.7 GitHub PRs

- Codex CLI has no PR-creation command. It could run `gh` only if network is allowed and credentials are present in its environment, and both are disabled by the recommended configuration. Codex Cloud/Web can open PRs, but that is out of scope for a local design. [V-src] (subcommand list); cloud [I]

---

## 4. Comparison table

| Capability | Claude Code | Codex CLI | Evidence | Confidence |
|---|---|---|---|---|
| Headless one-shot | `claude -p` | `codex exec` | [V-doc] / [V-src] | High |
| Machine-readable event stream | `--output-format stream-json` (NDJSON; `system/init`, assistant/user, `result`) | `--json` JSONL (`thread.*`, `turn.*`, `item.*`) | [V-doc] / [V-src] | High |
| Final structured output | `--json-schema` / SDK `outputFormat` → `structured_output`, with retry and error subtype | `--output-schema FILE`; final `agent_message` text is JSON; `-o` writes it to a file. No explicit validation-failure subtype found | [V-doc] / [V-src] | High / Medium (Codex validation semantics unverified) |
| Resume by ID | `--resume <id>`, preassign `--session-id <uuid>` | `exec resume <id>`; thread ID from `thread.started` | [V-doc] / [V-src] | High |
| Cannot preassign session ID | n/a | Codex: ID is assigned by the runtime; capture it from the first event | [V-src] | High |
| Turn / budget limits | `--max-turns`, `--max-budget-usd` | None found; coordinator enforces | [V-doc] / [V-src] | High |
| Cost reporting | `total_cost_usd` (estimate), `modelUsage` | Token usage only | [V-doc] / [V-src] | High |
| Exit codes | 0 / non-zero; 143 on SIGTERM; in-run errors appear in the stdout result | 0 / 1 | [V-doc] / [V-src] | High |
| Permission / approval model | deny/ask/allow rules, modes, `canUseTool`, hooks, managed settings | sandbox mode + approval policy (`never` forced in exec) + execpolicy rules + requirements.toml | [V-doc] / [V-src] | High |
| In-process permission callback | Yes (`canUseTool`, hook callbacks) | No (SDK has none) | [V-doc] / [V-src] | High |
| OS sandbox on macOS | Seatbelt, **Bash only**; file tools are governed by rules | Seatbelt for model-generated commands; `.git/.codex/.agents/.aws` protected | [V-doc] / [V-src] | High |
| Network default | Sandbox proxy with empty allowlist (when the sandbox is enabled) | `network_access=false` in workspace-write | [V-doc] / [V-src] | High |
| Env-var filtering | SDK `env` replaces the env; `sandbox.credentials` deny/mask | `shell_environment_policy`; SDK `env` replaces the env | [V-doc] / [V-src] | High (option values for `inherit` unverified) |
| Repo-content trust in headless | **Repo hooks and `.mcp.json` run under `-p`/SDK unless disabled** | Project config needs `trust_level`; hooks need trust; AGENTS.md always read | [V-doc] / [V-src] | High / Medium |
| Custom tools for the coordinator | In-process SDK MCP tools | Via MCP servers in config | [V-doc] / [V-src] | High |
| Acts as MCP server | `claude mcp serve` (exposes tools only) | Removed (`mcp-server` gone; app-server is experimental) | [V-doc] / [V-src] | High |
| Official TS SDK | `@anthropic-ai/claude-agent-sdk` (rich) | `@openai/codex-sdk` (thin exec wrapper) | [V-doc] / [V-src] | High |
| Unattended auth | API key / `apiKeyHelper` (works in `--bare`); `setup-token` OAuth token (not in `--bare`) | `CODEX_API_KEY` (exec); `auth.json` (ChatGPT or key) | [V-doc] / [V-src] | High |
| Credential storage on Mac | Keychain, with 0600 file fallback | `$CODEX_HOME/auth.json` (default `file`) | [V-doc] / [V-src] | High |
| Managed / admin policy | `/Library/Application Support/ClaudeCode/managed-settings.json`, MDM `com.anthropic.claudecode` | `requirements.toml` (macOS path unverified) | [V-doc] / [V-src] | High / Medium |
| Opens GitHub PRs natively | No (via `gh` in Bash) | No (CLI); cloud product only | [V-doc] / [V-src] | High |
| Git repo required | No | Yes, unless `--skip-git-repo-check` | [V-src] | High |

---

## 5. Recommended integration mechanism (preliminary)

**R1. Claude: TypeScript Agent SDK, isolated profile.** This is the primary path; `claude -p --bare` is the fallback.

Rationale:

- typed `SDKResultMessage`
- `outputFormat` with a draft-07 schema for plan-review and PR-review verdicts
- `canUseTool` deny-by-default with an audit log of every request
- in-process hook callbacks (no shell hooks)
- `interrupt()` for clean cancellation
- `maxTurns` and `maxBudgetUsd` as runaway guards
- in-process MCP tools that let Claude *read* coordinator state (e.g. `get_authorization`, `get_plan_version`) without filesystem access

Required options for every call:

```ts
// Illustrative only; not an implementation.
query({
  prompt,
  options: {
    settingSources: [],                       // never load repo/user settings (2.6)
    systemPrompt: { type: "preset", preset: "claude_code" }, // or a custom prompt; decide in Phase 2
    tools: ["Read", "Grep", "Glob"],          // reviewer: no Bash/Edit/Write/WebFetch
    disallowedTools: ["mcp__*"],              // except coordinator SDK server (allow-list instead)
    mcpServers: { mercury: createSdkMcpServer({ name: "mercury", tools: [/* read-only lookups */] }) },
    permissionMode: "dontAsk",                // anything not explicitly allowed is denied
    canUseTool: async () => ({ behavior: "deny", message: "not permitted" }),
    outputFormat: { type: "json_schema", schema: PlanReviewV1 },
    maxTurns: 40, maxBudgetUsd: 5,
    cwd: worktreePath, additionalDirectories: [],
    env: minimalEnv,                          // replaces process.env; only auth + PATH
    pathToClaudeCodeExecutable: pinnedClaudePath,
    abortController,
  },
});
```

- **Authorization decisions** (the "Claude authorizes task X" record, brief §A) are *Claude's verdicts*. The **coordinator** writes and versions the record after validating `structured_output`. Claude never writes the DB.
- **[I] Trade-off:** the SDK spawns the CLI anyway. So the process-supervision story (deadline, SIGINT then SIGTERM, orphan sweep) is the same as for a CLI subprocess. The SDK only buys richer in-process control. If the SDK proves unstable on the pinned version, the CLI equivalent is: `claude -p --bare --output-format stream-json --json-schema … --tools Read,Grep,Glob --permission-mode dontAsk --permission-prompts none --strict-mcp-config --mcp-config <coordinator.json> --settings '{"disableAllHooks":true}' --session-id <uuid> --max-turns N --max-budget-usd X`.

**R2. Codex: supervised `codex exec` subprocess (CLI directly).**

```
codex exec --json --output-schema <plan.schema.json> -o <out.json> \
  --cd <worktree> --sandbox read-only            # planning
codex exec resume <thread_id> --json --output-schema … -o … \
  --cd <worktree> --sandbox workspace-write \
  -c sandbox_workspace_write.network_access=false \
  -c shell_environment_policy.inherit=<minimal> --strict-config   # implementation
```

- Rationale: the TS SDK adds no control beyond this, and a direct subprocess gives exact argv for audit logs, PID ownership and process-group kill. Using the SDK is acceptable if the team prefers typed events; its `.d.ts` can serve as the event contract either way.
- Dependency installation during implementation needs network access. **[I]** Run it as a separate coordinator-controlled step (e.g. `npm ci` with a lockfile, outside Codex) rather than enabling `network_access` for Codex.
- **Never** use `--dangerously-bypass-approvals-and-sandbox`, `--approve-for-me` or `--dangerously-bypass-hook-trust`. Enforce this with managed `requirements.toml` if feasible **[UNVERIFIED path]**.

**R3. Not MCP as the inter-agent bus.** Codex's MCP server is gone, and app-server is experimental. `claude mcp serve` exposes tools, not decisions. The coordinator's SQLite queue plus subprocess calls with JSON artifacts is the more deterministic choice (brief §B).

**R4. The coordinator does git commit, push and PR creation.**

- Codex likely cannot commit in a sandboxed worktree because `.git` is protected **[I]**.
- Agents never hold GitHub write tokens, so prompt injection cannot open, approve or merge PRs (brief §E/§H).
- The PR author identity is a GitHub App or service account, distinct from the human approver.
- Claude's review is posted by the coordinator as a `COMMENT` or `REQUEST_CHANGES` review from the bot identity. Branch protection must not count bot approvals. That control belongs to Agent E/F.

**Trade-off of letting agents open PRs themselves:**

- It is simpler.
- But it requires a write-scoped token in an agent environment that executes untrusted repo code.
- It mixes identities.
- It moves PR metadata (Linear links, authorization IDs) out of the coordinator's control.

**Not recommended.**

---

## 6. Version-sensitivity risks (pin or verify on the Mac)

| # | Risk | Action |
|---|---|---|
| V1 | Claude flags introduced recently: `--permission-prompts` (2.1.259), `--restricted` (2.1.248), invalid `--json-schema` erroring (2.1.205), `onFailure:"block"` for hooks (2.1.295), `mcp_server_errors` (2.1.219), MCP wait (2.1.221). | Pin the Claude Code version (`claude install <version>`). Have the coordinator check `claude --version` and the `system/init.capabilities` array at startup and refuse to run below a minimum. |
| V2 | `--bare` "will become the default for `-p` in a future release" [V-doc]. | Always pass explicit flags; never rely on defaults. |
| V3 | The default permission mode for `-p` "can be `auto`". | Always pass `--permission-mode` / `permissionMode`. |
| V4 | Agent SDK bundles its own CLI binary (`…-darwin-arm64`), so the SDK version and the global `claude` version can diverge. | Pin `@anthropic-ai/claude-agent-sdk` exactly. Either set `pathToClaudeCodeExecutable` to the pinned binary or rely on the bundled one, and record which in the audit log. |
| V5 | Codex changes fast: `--full-auto` was removed, `on-failure` became an alias, `mcp-server` was removed, permission profiles are new, and app-server is experimental. | Pin `@openai/codex` (or the Homebrew cask) exactly. Run `--strict-config`. Have a startup self-test parse `codex exec --help` for the required flags. Disable auto-update (`check_for_update_on_startup=false`, schema key exists). |
| V6 | Codex JSONL is typed by the SDK at the same version, but the `--experimental-json` alias name suggests instability. | Contract-test the event schema per pinned version (brief §J), and tolerate unknown item types. |
| V7 | Codex auth precedence and `CODEX_API_KEY` scope may change. | Phase 0: run `codex login status` (subcommand existence **[UNVERIFIED]**) and a dry exec in a scratch repo. |
| V8 | macOS Seatbelt (`sandbox-exec`) is deprecated by Apple but still used by both tools. | Track macOS upgrades. Re-run the sandbox self-tests after each OS update. |
| V9 | Managed-settings parse errors make Claude refuse to start. | Validate the managed JSON in deployment; test with `claude doctor`. |

---

## 7. Unknowns (to verify on the Mac in Phase 0)

1. Installed versions of `claude` and `codex`, their install method (npm, native, Homebrew), and whether auto-update is enabled.
2. Whether a LaunchAgent can use Claude's Keychain-stored credentials while the screen is locked or after reboot before login. Whether `apiKeyHelper` reading a Keychain item works from launchd.
3. Whether `git commit` / `git add` succeed inside `codex exec --sandbox workspace-write` in a **linked worktree** (the expected answer is no). Whether adding the main repo's `.git/worktrees/<name>` to `writable_roots` changes that, and whether doing so is safe.
4. Codex default sandbox in exec when `--sandbox` is omitted, for trusted versus untrusted projects.
5. Codex `shell_environment_policy.inherit` accepted values in 0.162.1.
6. Codex behaviour when the `--output-schema` result does not validate (retry? error? exit code?).
7. Safety of concurrent `codex exec` processes sharing one `CODEX_HOME` (sqlite state, auth refresh).
8. Codex per-command timeout defaults and whether long test suites are killed.
9. Path of Codex managed `requirements.toml` on macOS, and whether it can forbid `danger-full-access` and the bypass flags.
10. Whether the operator's existing `~/.claude` or `~/.codex` configuration contains hooks or MCP servers that would leak into runs. Isolation flags avoid this, but it needs confirming.
11. Whether `ANTHROPIC_API_KEY` (Console billing) versus subscription OAuth (`setup-token`) is acceptable to the operator, given the Agent SDK policy note.
12. Whether Codex reads AGENTS.md from the coordinator-controlled worktree only, and whether `project_root_markers` needs adjusting for linked worktrees, where `.git` is a file.

---

## 8. Decisions needed from the operator (surface in TDD §30)

- **Billing and auth mode for each agent:**
  - Claude: Console API key or subscription token.
  - Codex: ChatGPT plan or API key.

  This affects `--bare` usability and the Agent SDK policy note.
- **Dependency installation:** may Codex ever have network access during implementation, or does the coordinator perform all dependency installation?

---

## 9. Sources

All accessed 2026-10-12.

**Anthropic (official)**

- https://code.claude.com/docs/en/cli-reference: full flag table (`--max-turns`, `--json-schema`, `--permission-prompts`, `--bare`, `--restricted`, `--session-id`, `--settings`, `--setting-sources`, `--strict-mcp-config`, `--tools`); "`claude --help` does not list every flag"; `claude auth status` JSON and exit codes; `setup-token`.
- https://code.claude.com/docs/en/headless: `-p` usage; output formats; `structured_output` field; exit-code behaviour; SIGTERM → 143; bare mode auth (API key only) and "will become the default"; `--permission-prompts none`; `system/init`, `api_retry` and `mcp_server_errors` fields; `total_cost_usd`.
- https://code.claude.com/docs/en/agent-sdk/overview: SDK runs the Claude Code binary; claude.ai-login policy note; changelog links.
- https://code.claude.com/docs/en/agent-sdk/typescript: `query()`, Options (`settingSources` default = all), `tool()`/`createSdkMcpServer()`, Query methods, `SDKResultMessage` union, `HookEvent` union, bundled platform binary.
- https://code.claude.com/docs/en/agent-sdk/structured-outputs: `outputFormat`; draft-07; `error_max_structured_output_retries`; success-without-output case.
- https://code.claude.com/docs/en/hooks: 33 events, hook types, exit 2 / `permissionDecision`, timeouts, `allowManagedHooksOnly`.
- https://code.claude.com/docs/en/permissions: deny → ask → allow; settings precedence; `disableBypassPermissionsMode`; "What runs before you trust a folder" table; mitigations.
- https://code.claude.com/docs/en/managed-settings: macOS path `/Library/Application Support/ClaudeCode/managed-settings.json`; MDM domain `com.anthropic.claudecode`; refuse-to-start on parse error.
- https://code.claude.com/docs/en/sandboxing: Bash-only scope; Seatbelt on macOS; default read/write/network; `allowUnsandboxedCommands`, `failIfUnavailable`, `excludedCommands`, credential masking.
- https://code.claude.com/docs/en/authentication: precedence list; Keychain and file fallback; `setup-token`; `CLAUDE_CODE_OAUTH_TOKEN` not read in bare mode; unattended login-expiry warning.
- https://code.claude.com/docs/en/mcp: `claude mcp serve` (tools only; client must confirm); scopes; `.mcp.json` auto-connect in `-p`/SDK.
- Local: `claude --help`, `claude mcp --help`, `claude auth --help`, `claude setup-token --help` (Claude Code 2.1.296).

**OpenAI Codex (source and packages, tag `rust-v0.162.1`)**

- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/exec/src/cli.rs: exec flags, `resume`/`fork`/`review` subcommands.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/utils/cli/src/shared_options.rs: `--sandbox`, `--yolo`, `--approve-for-me`, `--cd`, `--add-dir`, `--profile`, `--worktree`, `--dangerously-bypass-hook-trust`; no `--full-auto`.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/utils/cli/src/approval_mode_cli_arg.rs: CLI approval values `on-request`, `never`.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/exec/src/lib.rs: headless `approval_policy = Never`; git-repo check and message; `process::exit(1)` on failed or interrupted turn; permission requests rejected in exec.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/exec/src/exec_events.rs: JSONL event type names.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/protocol/src/protocol.rs: `AskForApproval` (`untrusted`, `on-request` with alias `on-failure`, `granular`, `never`).
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/protocol/src/permissions.rs: protected metadata `.git`, `.agents`, `.codex`, `.aws`.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/config.schema.json: config keys; `sandbox_workspace_write` defaults (`network_access=false`); `shell_environment_policy`; `notify`; `profiles`; `AuthCredentialsStoreMode`.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/config/src/types.rs: CLI auth store default `file`.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/login/src/auth/manager.rs: `CODEX_API_KEY` / `OPENAI_API_KEY` / `CODEX_ACCESS_TOKEN`; env-key precedence.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/cli/src/main.rs: subcommand list (no `mcp-server`; `app-server` "[experimental]"); `login --with-api-key`/`--with-access-token`/`--device-auth`.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/cli/src/mcp_cmd.rs: `codex mcp` subcommands.
- https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/agents_md.rs: AGENTS.md discovery rules.
- https://github.com/openai/codex/tree/rust-v0.162.1/codex-rs/sandboxing/src: Seatbelt via `/usr/bin/sandbox-exec`; Landlock/bubblewrap on Linux.
- https://github.com/openai/codex/blob/rust-v0.162.1/docs/config.md: `allow_managed_hooks_only` in `requirements.toml`; links to developers.openai.com.
- npm `@openai/codex-sdk@0.162.1` (README, `dist/index.js`, `dist/index.d.ts`): exec-wrapping design, options, event and item types, `env` non-inheritance, `~/.codex/sessions`, git-repo requirement.
- npm `@openai/codex@0.162.1` (README, package.json): install methods, ChatGPT-plan versus API-key note, platform binaries.

**Secondary (search summaries; official pages not fetchable from this container)**

- https://developers.openai.com/codex/noninteractive.md (via search summary): `CODEX_API_KEY` for CI, exec-only; `--output-schema` with `-o`.
- https://developers.openai.com/fr-FR/docs/mcp-server (via search summary): `codex mcp-server` removed; migrate to app-server.
- Third-party posts were consulted only to explain disagreements and are not relied on: codex.danielvaughan.com (2026-08-25/28/30) on the mcp-server deprecation in 0.149.x, and vincentschmalbach.com on `--full-auto` mapping history.
