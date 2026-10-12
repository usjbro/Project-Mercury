# Agent E (Application Security Architect): Phase 2 Report

| Field | Value |
|---|---|
| Agent | E — Application Security Architect (independent reviewer) |
| Phase | 2: initial threat model |
| Date | 2026-10-12 |
| Detailed deliverable | [`security/threat-model.md`](../security/threat-model.md) |
| Not yet written | `security/security-review.md` (Phase 5) |

## 1 Findings

1. **GitHub can enforce the human approval boundary with no reliance on prompts.** The controls are:
   - CODEOWNERS = `* @usjbro` with Code Owner review required;
   - approval of the most recent push required;
   - stale approvals dismissed;
   - no bypass;
   - force push blocked;
   - a GitHub App identity, which can never be a code owner.

   The proof is in threat-model §5.2.2: every path to a protected branch is blocked by a GitHub- or OS-enforced control. This holds even if Claude or Codex is fully prompt-injected, and even if the coordinator posts an APPROVE.
2. **"Only the human clicks merge" cannot be enforced on a personal-account repository** if the pushing identity has `contents:write` (discovery fact 4). I propose three modes (SEC-109):
   - **G-ORG:** move to an organization and restrict updates to `main`. Preferred.
   - **G-SPLIT:** a deploy key pushes; an App with `contents:read` opens PRs; no MERCURY credential can merge. This is a new option and depends on ASM-E-01/02/07.
   - **G-DETECT:** a `merged_by` check after the fact, with written risk acceptance.

   In every mode, the merged code is the code the human approved.
3. **Critical (new): the operator's own credentials on the Mac are the real weak point.**
   - The Seatbelt defaults (Codex `workspace-write`, the Claude Bash sandbox) allow reading most of `$HOME`.
   - Claude's Read, Grep and Glob tools are not sandboxed at all.

   An injected agent that reads the `gh` token or the Linear key can impersonate the human, and that defeats every GitHub control. **SEC-201 requires that agents run under a separate macOS uid** that has no access to credential stores. Until that is verified, R-03 is Critical.
4. **High (new): Linear can approve and merge GitHub PRs as the human.** This comes from Linear Reviews and the diff merge/review operations. MERCURY must use a Linear `actor=app` identity and never the human's key. Agents must have no Linear or GitHub MCP connectors (SEC-801/802).
5. **High (new): `.gitattributes` undermines review integrity.**
   - `export-ignore` hides files from `git archive`-based review snapshots.
   - `linguist-generated` collapses files in GitHub's diff view, so the human may not see them.

   Review snapshots must be built with `ls-tree`/`cat-file`, and `.gitattributes` must escalate to the human.
6. **High: workflow files on same-repo branches run with repository secrets** (ASM-E-07). Changes under `.github/**` must be blocked before push (SW). The App gets no `workflows` permission (GH). The repo must hold no PR-reachable secrets.
7. **Prompt injection is contained by code-validated bindings, not by model robustness.** Every verdict echoes the IDs and hashes it is bound to (issue, spec hash, auth, plan hash, head SHA, diff hash), and the coordinator checks them. Claude cannot widen an authorization's scope. Deterministic pre-checks feed a **required** `mercury/policy` status, so an escalation blocks the merge on GitHub.
8. Claude headless runs execute repo hooks and `.mcp.json` by default (discovery fact 6). Isolation must therefore stack: `settingSources: []`, strict MCP, `disableAllHooks`, root-owned managed settings, and **never running Claude in a Codex worktree**. Claude reviews a read-only snapshot instead.

## 2 Recommended design (summary)

Details and IDs are in [`security/threat-model.md`](../security/threat-model.md).

- **Three trust zones** (§3.1):
  - H: the operator's credentials, unreachable by MERCURY.
  - C: the coordinator, which is the sole holder of MERCURY credentials and the sole DB writer.
  - A: the agent uid, which holds no credentials and only has its model API.
- **Requirements catalogue** SEC-100…905, each tagged [SW]/[GH]/[OS]/[POL] (§5.1). The core MUSTs:
  - SEC-100/104 rulesets and CODEOWNERS;
  - SEC-102 GitHub client endpoint allowlist, with no APPROVE and no merge;
  - SEC-201 separate uid;
  - SEC-204/205 Claude isolation plus snapshot;
  - SEC-305/306/308 binding validation;
  - SEC-310 protected-path escalation;
  - SEC-501/502 redaction and pre-push secret blocking;
  - SEC-602/604 hash chain plus off-host anchor;
  - SEC-108 governance drift monitor;
  - SEC-905 merge verification.
- **Defence-in-depth stack** L0–L8 and the proof (§5.2). It includes a single-technical-control failure analysis: only the loss of SEC-201 combined with an exfiltration path breaks the invariant.
- **Permission matrix** per identity and capability (§6.1), and SaaS identity permissions per governance mode (§6.2).
- **Prompt-injection defences**: nonce-delimited provenance tags, strict schemas, context separation per role, a deterministic pre-check pipeline, and a 15-case adversarial corpus with deterministic oracles (§7).
- **Execution controls**:
  - Codex wrapper and flags;
  - hardened git (env plus `-c` overrides, config allowlist, tree checks);
  - redaction pipeline;
  - anchoring evaluation, recommending a private anchor repo plus the chain head in PR review comments;
  - supply-chain pins (§8).
- **Risk register** R-01…R-26 (§9), **acceptance criteria** SAC-01…12, the **test list** SEC-T-*, and **assumptions** ASM-E-01…15 (§10).
- **Requirements on other agents** A-SEC/B-SEC/C-SEC/D-SEC/F-SEC (§11).

## 3 Alternatives considered

| Topic | Alternative | Decision |
|---|---|---|
| Merge-actor control | Accept G-DETECT only (baseline/discovery G5) | Kept as the third option. G-SPLIT added as a GitHub-enforced option for personal repos. G-ORG preferred. |
| Agent confidentiality | Rely on the Codex Seatbelt and Claude permission rules only | Rejected as the end state. The Seatbelt defaults allow reads, and Claude's file tools are not sandboxed. A separate uid is OS-enforced and covers both agents. Kept only as an interim fallback with tests. |
| Claude reviewing the Codex worktree directly with isolation flags | — | Rejected. Too many execution vectors (hooks, git, symlinks). A read-only snapshot built from git objects removes them structurally. |
| `git archive` for snapshots | — | Rejected, because `.gitattributes` `export-ignore`/`export-subst` let the author shape what the reviewer sees. |
| Claude posts APPROVE on success | Simpler signalling | Rejected. Statuses (`mercury/claude-review`) plus COMMENT reviews. APPROVE is unrepresentable in code. |
| Anchoring the audit chain in Linear comments | — | Rejected as primary (editable or deletable by members). A private GitHub anchor repo is primary; the PR review comment is secondary. |
| Agents opening PRs themselves | Fewer coordinator responsibilities | Rejected (agrees with discovery R4). Agents never hold write credentials. |
| Baseline `PR_OPEN` before `CLAUDE_PR_REVIEW` | — | No objection. I add a `security_escalation` blocked reason and a guard requiring pre-checks to pass or be acknowledged (C-SEC-3). |

## 4 Tradeoffs

- **A separate uid adds operational complexity**: a sudoers wrapper or launchd broker, shared-group directory modes, and `safe.directory` entries. In exchange, the most critical risk (R-03) gets OS-level confidentiality.
- **G-SPLIT uses two GitHub credentials, and a deploy key has no `workflows` gating.** The workflow-file risk then rests on SEC-310 (SW) plus SEC-105 (no secrets). In exchange, no MERCURY credential can merge.
- **Escalating the protected-path list** (lockfiles, manifests, `.gitattributes`) adds human work on dependency changes. That is accepted because dependency confusion is a High risk.
- **A required `mercury/policy` status with a local-CLI acknowledgement** is an extra gate the operator must clear. The acknowledgement is not a GitHub approval, so it cannot be confused with one.
- **Fail-closed drift monitoring may halt work** on benign settings changes. The golden-policy update is a deliberate operator action.

## 5 Risks

The top items from threat-model §9:
- R-03 (Critical until SEC-201 is verified): an agent reads the operator's credentials.
- R-05 (High, inherent): a subtle backdoor passes both Claude and the human.
- R-08 (High): the Linear merge-as-human path and coding sessions.
- R-09 (High): CI workflow modification.
- R-13 (High): dependency confusion or typosquatting.
- R-19 (High): governance drift.
- R-22 (High): approval fatigue or rubber-stamping.

Design risk: several controls depend on unverified platform behaviour (ASM-E-01/02/03/05/07). If Phase 0 refutes them, the fallbacks are G-ORG or G-DETECT, plus policy.

## 6 Assumptions

ASM-E-01…15, listed in threat-model §10.3. The ones that matter most:
- ASM-E-01/02: G-SPLIT capabilities.
- ASM-E-04: home-directory permissions against a second uid.
- ASM-E-05: a Linear app actor cannot merge or approve.
- ASM-E-07: branch workflows get secrets, and deploy keys skip `workflows` gating.
- ASM-E-11: claude.ai connectors are not loaded in API-key or bare runs.
- ASM-E-15: Codex Seatbelt reads the whole filesystem.

Inherited: discovery facts 1–12 and the Agent B and D assumptions about the Mac runtime.

## 7 Dependencies

- **Agent A:** ADRs for merge-actor enforcement and for the separate uid (A-SEC-1/2). Trust zones in the overview.
- **Agent B:** Claude and Codex invocation profiles, the GitHub and Linear endpoint allowlists, the identity set per governance mode (B-SEC-1…6).
- **Agent C:** binding fields in the schemas, the dispatch-guard transaction, the audit and HMAC tables, `Redacted<string>` sinks (C-SEC-1…7).
- **Agent D:** the agent uid, wrapper, directory modes, Keychain items, pins, kill switch, and Phase 0 checklist (D-SEC-1…6).
- **Agent F:** RTM import, Phase 0 governance before any agent execution, SAC gates (F-SEC-1…3).
- **Operator:** the G-ORG / G-SPLIT / G-DETECT decision; disabling Linear coding sessions; Actions settings; 2FA; retiring the legacy scripts and confirming the old Slack token was rotated.

## 8 Unresolved questions

1. Will the operator move target repos (and `project-mercury`) to a GitHub organization? This decides SEC-109.
2. Can the coordinator obtain a **read-only** credential for rulesets and branch protection (SEC-108)? If not, which parts of drift detection become manual?
3. Should the coordinator itself run as the operator's uid or as a dedicated `mercury` uid (Agent D)? Security prefers a dedicated uid, but the requirement only demands agent uid ≠ coordinator uid.
4. Is Codex allowed network access for dependency installs (an operator decision from discovery §8)? This threat model assumes **no**, with installs done by the coordinator under SEC-703.
5. Should the security review be a separate Claude run for every PR, or only for escalated or `Security`-labelled PRs? The current draft makes it a MUST only for escalated or `Security`-labelled PRs.
6. Is a public chain-head embed in PR comments acceptable to the operator (it reveals activity cadence only)?

## 9 Supporting evidence

- `reviews/02-discovery-platform.md` §1.1–1.4: rulesets and protection capabilities; the org-only bypass and restrict-push; Apps cannot be code owners; last-push rule; `contents:write` = merge; Actions approve setting; §3 Linear Reviews merge as human and Coding sessions; §4.5 Keychain and TCC.
- `reviews/02-discovery-agent-runtimes.md` §1.6, §2.4–2.6: repo hooks and `.mcp.json` executing under `-p`/SDK; managed settings; Bash-only sandbox scope with default reads of `~/.ssh`. §3.2–3.6: Codex `.git` protection, `network_access=false`, `shell_environment_policy`, AGENTS.md discovery, hook trust, the dangerous flags.
- `reviews/01-discovery-integrations.md`: identity confusion (agents acting as `usjbro` and "James Brown"), the Codex review bot, Todo-as-queue, the leaked Slack token (JAM-160).
- `reviews/03-design-baseline.md`: authority invariants 1–4 and discovery facts 1–12.
- Linear MCP tool surface visible in this session includes `submit_diff_review` and `merge_diff`, corroborating finding 4 (not called).

## 10 Confidence level

| Recommendation | Confidence | Why |
|---|---|---|
| GitHub-enforced approval boundary (SEC-100/104, proof §5.2) | **High** | Built on documented GitHub rules (code owners, last-push, stale dismissal, no bypass), verified in discovery. |
| SEC-102 endpoint allowlist / no APPROVE path | High | Pure software. Easy to test. |
| G-SPLIT viability | **Low–Medium** | Depends on ASM-E-01/02/07, which are unverified. |
| Separate uid for agents (SEC-201) | Medium | It is the right control. macOS implementation details (sudoers vs broker, home perms, Keychain ACLs) are unverified. |
| Claude isolation plus snapshot review (SEC-204/205) | High | Documented flags, plus a structural removal of execution vectors. |
| Binding validation and scope narrowing (SEC-305/306/308) | High | Deterministic code checks; testable. |
| Protected-path escalation via a required status (SEC-310) | Medium–High | Depends on the App being able to post a required status pinned to its identity (discovery S1). |
| Linear app actor cannot merge (SEC-801) | Low–Medium | ASM-E-05 is unverified. |
| Audit hash chain plus GitHub anchor | Medium–High | Standard technique. Anchor credential design still to be settled with B and D. |
| Prompt-injection corpus thresholds (SAC-04) | Medium | The code-enforced oracles are solid. The LLM-judgement threshold (≥ 95%) is an initial target to calibrate. |
