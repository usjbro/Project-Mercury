# MERCURY — Phase 5 Independent Security Review

| Field | Value |
|---|---|
| Owner | Agent E — Application Security Architect |
| Phase | 5 (independent final design validation) |
| Date | 2026-10-13 |
| Deliverable | "Security review report with severity-ranked findings" (brief, documentation layout) |
| Status | Design review only. Nothing here was validated on the operator's Mac or against live GitHub/Linear. Items that need the Mac or live services are marked **UNVERIFIABLE IN DESIGN — P0-xxx**. |

---

## 1. Scope, method, documents and versions reviewed

### 1.1 Scope

The reconciled MERCURY design (TDD 1.0-rc and every supporting document revised in Phase 4), checked against:

- the brief's hard constraints (`reviews/00-brief.md`). The main one: *"Human approval boundary must be enforceable by technical permissions + GitHub protections, not only prompt instructions"*;
- the binding reconciliation decisions RD-1…RD-20 and Addenda A–C (`reviews/30-reconciliation.md`);
- the security requirements SEC-1xx…9xx, SAC-01…20 and gates G-S1…G-S5 in `security/threat-model.md` (TM).

Out of scope: implementation code (none exists), live configuration, and threats the TM excludes (root or kernel compromise, a malicious operator, compromise of a SaaS provider).

### 1.2 Method

| Technique | Applied to |
|---|---|
| Full read | TDD.md; `reviews/30-reconciliation.md` (incl. Addenda A–C); `reviews/44-revision-E.md`; TM (all sections) |
| Targeted read (section-level) | `integrations/github.md` §2, §6–§10; `integrations/claude.md` §2, §7, §8; `integrations/codex.md` §3, §9; `integrations/linear.md` §2, §7–§9; `architecture/components.md` §4.9–§4.16, §5, §9; `architecture/state-machine.md` §5, §6, §8; `operations/macos-service.md` §3, §7, §9, §15, §16; ADR-008, ADR-013, ADR-018, ADR-019; `planning/roadmap.md`; `planning/traceability.md` §10–§11; `testing/verification-plan.md` §7.2 |
| Pattern search (ripgrep) across `docs/mercury` | Forbidden GitHub endpoints (`merge`, `/merges`, `update-branch`, `auto-merge`, `enablePullRequestAutoMerge`, `dismiss`, `APPROVE`, `REQUEST_CHANGES`); `neutral`; `mercury-ops` and `metadata:read`; `statuses`; `add-dir`; `fd 0`; anchor carriers; `M1–M8`/`M9`/`unexpected_base_commit`; `P0-049`; `G-S5`; presence-tier method names; `redact` |
| Trace | Each path of the human-approval-boundary proof (TM §5.2.2), followed from the requirement to the component, the API surface and the GitHub rule that enforces it |
| Cross-document consistency | Presence-tier method lists (four documents); protected-path lists (TM, codex.md, github.md, SM, TDD); App permissions (TM, ADR-008, github.md, macos-service, overview); merge-verification numbering (TM, github.md, SM, TDD, verification plan) |

Every result below cites its evidence as `file §section` (and a line number where it helps). I wrote the TM myself, so I did not mark any of its SEC statements as passing because the TM says so. A SEC counts as satisfied only when the component that implements it specifies it.

### 1.3 Documents and versions reviewed

All files are as of 2026-10-12/13 in the working tree (no commits were made in this phase).

| Document | Version / status as read |
|---|---|
| `TDD.md` | 1.0-rc, "Conditionally ready for human review" |
| `security/threat-model.md` | Phase 4 revision; **amended in this phase** (see §3, VE-19 and TM header) |
| `integrations/github.md`, `claude.md`, `codex.md`, `linear.md` | Phase 4 (B), dispositions in `reviews/41-revision-B.md` |
| `architecture/components.md`, `state-machine.md`, `protocols/messages.md` | Phase 4 (C), `reviews/42-revision-C.md` |
| `operations/macos-service.md`, `recovery.md` | Phase 4 (D), `reviews/43-revision-D.md` |
| `architecture/overview.md`, ADR-001…020 | Phase 4 (A), `reviews/40-revision-A.md` |
| `planning/*.md`, `testing/verification-plan.md` | Phase 4 (F), `reviews/45-revision-F.md` |

---

## 2. Verdict

**Approve with conditions.**

- **The hard constraint is met in design.** Every path by which a commit can reach a protected branch is blocked by at least one control that does not depend on a prompt: GitHub rulesets and App permissions [GH], the `_mercuryagent` uid and root-owned wrappers [OS], or deterministic code [SW] (§5). The single exception is **N1**, the operator's own interactive agents, which hold the operator's own credentials. N1 is controlled by policy only (OD-E-02, RISK-28). This is declared, and it is not a MERCURY control failure.
- **No Critical or High findings are open.** I found 0 Critical, 0 High, 8 Medium and 12 Low findings (§3). Every Medium is a cross-document inconsistency left over from the Phase 4 addenda, or a gap in a list. None of them breaks invariant H. If any were implemented as written, it would either fail closed or be caught by an existing test, with one exception: VE-05 would weaken the protected-path policy if an implementer followed the TDD text instead of SEC-310.
- **Conditions** (detail in §7): fix the Medium findings before the milestones named in §3. Pass G-S2 (SEC-T-20 on the real Mac) before any non-sandbox write run. Before any unattended operation, adopt G-ORG and decide OD-36.

---
## 3. Severity-ranked findings

Severity scale (Phase 5 common rules): **Critical** = violates a hard constraint or authority invariant, or makes the design unimplementable or unrecoverable. **High** = incorrect behaviour, data loss, duplicate side effects, security exposure, or major rework. **Medium / Low** = defects of lesser impact. "Fixed in place" applies only to my own files (TM, this report). Every other finding is routed to its owner with a proposed fix.

**Totals: Critical 0 · High 0 · Medium 8 · Low 12.** Medium findings fixed in place: 1 (VE-19). Low findings fixed in place: 3 (VE-09 E part, VE-11 E part, VE-14 E part).

| ID | Sev | Owner | Finding (evidence) | Proposed fix | Needed before |
|---|---|---|---|---|---|
| VE-01 | Medium | A | **Stale App inventory, contradicting Addenda B/C.** ADR-008 §Decision table row `mercury-ops` (line 23): installed on "target repositories (read-only)" with `metadata:read` for the drift monitor; line 33 and Alternatives (line 41) repeat it; `mercury-bot` row omits `statuses:read`. `overview.md` §C11 (line 481): "Drift monitor via `mercury-ops`". Addendum C §1: `mercury-ops` is **not** installed on targets, and the drift monitor uses a `mercury-bot` `audit` token (`metadata:read`). Addendum B §1: `statuses:read` added to `mercury-bot`. `github.md` §2.3 and the TDD §15 are correct. | Update ADR-008 rows and §33/§41 and overview C11 to match github.md §2–§3 | P0c (identity creation) |
| VE-02 | Medium | A | **ADR-018 §Decision 2 lists the `MERCURY / claude-review` check-run summary as an anchor carrier with no condition.** Addendum B §2 and OD-24 default: carrier on **private repos only**, never on public repos. The implementers (components §4.16, github.md §6.1) are correct. | Qualify the bullet "private repositories only (Addendum B, OD-24)" | M7 |
| VE-03 | Medium | D | **Credential inventory has stale App permissions.** `macos-service.md` §9.1 (lines 678–679): `mercury-bot` lacks `statuses:read`; `mercury-ops` has "`metadata:read` on targets" and "ruleset drift reads". §9.1 is the single source for the credential inventory, so P0c could install `mercury-ops` on targets, which SEC-110 forbids. | Copy github.md §2.2/§2.3 permissions; move "ruleset drift reads" to the `mercury-bot` row | P0c |
| VE-04 | Medium | D | **The `agent-exec` grammar does not take the Addendum C §4 changes.** (a) §3.4 line 277: fd 0 = `/dev/null` for Codex kinds, but codex.md §3 (line 47) and TDD §13 put the prompt on fd 0. (b) §3.5 line 301 / step 5: `claude` allows `--add-dir` only equal to `cwd`, and `cwd` only `snapshots/<tree_sha>`. claude.md §2.2 needs `--add-dir runs/<run_id>/in` and `cwd = runs/<run_id>/in` for snapshot-less runs (triage). As written, both run kinds fail closed (`config_fatal`), so this is not a security exposure, but the design cannot be implemented as written. | Amend §3.4 fd table (fd 0 = `runs/<run>/in/prompt.txt` opened read-only by `mercuryd`, Codex kinds) and §3.5 `claude` row and step 5 (allow `--add-dir` ∈ {`cwd`, `runs/<run_id>/in`}; `cwd` ∈ {`snapshots/<tree>`, `runs/<run_id>/in`}). `in/` is operator-owned 0750/0640 (§7.1), so it stays read-only to the agent | M3 (Claude), M4 (Codex) |
| VE-05 | Medium | Orchestrator | **TDD §19 "Prompt-injection defences" misclassifies protected paths.** It puts `.claude/**` and `.mcp.json` in the policy-acknowledgement (escalate) class. SEC-310 makes them **block-class**: a planted hook must never be pushed, because it would run under the operator's interactive Claude (TH-20, TH-38). The TDD is the summary an implementer reads first. | Change the clause to: "`.github/**`, `.claude/**`, `.mcp.json`, `.codex/**`, `.agents/**`, editor/env auto-run files → blocked; CODEOWNERS, lockfiles/manifests, build scripts, `.gitattributes`, `AGENTS*.md`, `CLAUDE.md` → policy acknowledgement (SEC-310)" | Before M5 |
| VE-06 | Medium | B | **Managed Claude settings are weaker than SEC-204.** `claude.md` §7.3: only `disableBypassPermissionsMode` and `disableAutoMode`, labelled "Recommended", "CL-1…CL-8 do not depend on it". SEC-204 (MUST, OD-19 default *yes*) also requires `allowManagedHooksOnly`, deny rules for credential paths, and an empty managed MCP configuration. These close TH-20 for any Claude process, including the operator's interactive one. | List the SEC-204 keys in §7.3 and validate them in the §8 self-test when OD-19 = yes (P0-048) | M3 (G-S1) |
| VE-07 | Medium | D | **The watchdog check needs a permission SEC-101 forbids.** `macos-service.md` §11.6 (line 865): `doctor` reads `GET /repos/{o}/{r}/actions/workflows/{id}` with the `mercury-ops` token. That endpoint needs `actions:read`. SEC-101 says no MERCURY credential holds `actions`, and github.md §2.3 does not grant it. As written, the check either fails with 403 or forces a silent permission widening. | Prefer an operator attestation (POL, monthly, like the SEC-108 admin-read checks). Alternatively, a separate OD with an ADR granting `actions:read` to `mercury-ops` on `project-mercury` only; E would then add a SEC-101 exception | M7 (watchdog) |
| VE-19 | Medium | E | **TM had not taken the Addenda.** SEC-101 and §6.3 lacked `statuses:read` and still had `mercury-ops` on targets. SEC-113 used `neutral` for `MERCURY / policy`, which GitHub treats as passing. SEC-604, §8.5 and A-12 made the check summary an unconditional carrier. SEC-905, §8.9 and §0 item 11 used merge-verification numbering (M1–M9) that differs from github.md §8, and §8.9 scoped M8 (MERCURY review state) to the repo where GH §8 and SM §8.5 scope it globally. SEC-310 and SAC-16 required a new acknowledgement for every head, contradicting the digest carry-forward of github.md §6.2 and SM §8.7. ASM-E rows had P0 "new". | **Fixed in place** (TM revised 2026-10-13; see §6.2) | — |
| VE-08 | Low | B | `github.md` §9.4 O6: "**Both** Apps installed with exactly the permissions of §2" on the target repo, contradicting §2.3 and Addendum C. §9.6 scopes governance drift and `unexpected_base_commit` as **global** halts. TM §8.9 now states the repo halt as the **minimum** scope, so global is compliant but costs availability. | O6: "`mercury-bot` installed; `mercury-ops` not installed". Optionally narrow §9.6 to a repo halt | P0c |
| VE-09 | Low | B (E part fixed) | `codex.md` §9 step 2 makes `CODEOWNERS`, `.gitattributes`, `.gitmodules`, `AGENTS*.md`, `CLAUDE.md`, `.tool-versions` **block-class**, where SEC-310 makes them escalate-class. It also adds `.husky/**`, `.npmrc`, `.yarnrc*`, which SEC-310 did not list. Stricter is safe, but the two documents now disagree. | **E:** SEC-310 now adds `.husky/**`, `.npmrc`, `.yarnrc*` to block-class and allows repo policy to move escalate-class paths to block-class. **B:** state that codex.md follows the stricter repo-policy option, or align with SEC-310 | M5 |
| VE-10 | Low | C | `components.md` §9.6 git flag set is a subset of SEC-401 / TM §8.3 / codex.md §9. It lacks `--no-textconv --no-ext-diff`, `core.attributesFile=/dev/null`, `credential.helper=`, `submodule.recurse=false`, `transfer.fsckObjects`, `core.protectHFS/NTFS`, and the SEC-402 mirror-config key allowlist check before worktree-naming calls (codex.md has only a start-up hash). No execution path exists today, because config cannot come from the worktree. | Reference codex.md §9 / TM §8.3 as the complete set; add the SEC-402 per-invocation config check (or start-up hash plus an fs-event re-check) | M5 (G-S3) |
| VE-11 | Low | C (E part fixed) | SM §8.8 instruction-file guard compares with `tasks.last_commit_sha`, but SEC-209 said "base-SHA versions". Under SEC-310, `AGENTS*.md`/`CLAUDE.md` are escalate-class, so once acknowledged they can differ from base and steer later Codex runs. | **E:** SEC-209 amended to accept the last MERCURY commit **only** where the difference carries a presence-bound `policy ack`. **C:** state that rule in §8.8 | M4 |
| VE-12 | Low | C | SM §5.1 `security_halt` row: "any SEC-902 trigger (E owns the list)". SEC-902 is the kill switch; the trigger list is SEC-906 / TM §8.9. | Replace with "any trigger of TM §8.9 (SEC-906)" | M5 |
| VE-13 | Low | D, C | The presence helper uses `LAContext.evaluatePolicy(.deviceOwnerAuthentication)` (macos-service §9.5, components §5.2). That policy offers the password even when Touch ID is available. TM §8.8 requires biometrics first, with the password only when biometry is unavailable (lower exposure to synthetic-input attacks, RISK-30). | Evaluate `.deviceOwnerAuthenticationWithBiometrics`; on `biometryNotAvailable`/`biometryNotEnrolled` fall back to `.deviceOwnerAuthentication` and record `presence_method` in `control_requests`. Verify in P0-045 | M5 |
| VE-14 | Low | A (E part fixed) | Presence-tier method lists differ in four places. ADR-019 §33 omits restore-epoch confirmation (Addendum B §5) and security `outbox retry`. macos-service §9.5 omits `outbox retry`, `resume --reopen/--discard-worktree-changes`, `orphan adopt`. TM SEC-115 listed a `guard_integrity_failure` resume that SM §6.1 does not offer. components §5.2 is the superset (§6.8 below). | **E:** SEC-115 now names components §5.2/§5.4 as the authoritative method classification and is aligned with it. **A/D:** reference components §5.2 instead of restating the list | M5 |
| VE-15 | Low | C | `components.md` §4.16 Redactor lists exact-match and pattern stages but not SEC-501's **encodings** of loaded secrets (base64, hex, URL-encoded) or the **entropy stage, fail-closed, for public sinks**. | Add both to §4.16; TC-SEC-150 already tests 40 formats and encodings | M5 (G-S3) |
| VE-16 | Low | D | `macos-service.md` §13.2 step 2: `mercury upgrade` "optionally `gh attestation verify` with the operator's own `gh`". SEC-103 says MERCURY never runs `gh`. If the CLI runs it, MERCURY executes with the human credential. | Make it a separate operator step in the runbook ("before `mercury upgrade`, run `gh attestation verify …`"), never invoked by MERCURY code | M8 |
| VE-17 | Low | F | `traceability.md` §10 row ASM-E-06: "SEC-206 (SHOULD); G-S2 if chosen". The `deps_install` registry-egress part of SEC-206 is **MUST** and gates G-S2 through SAC-18. The P0-049 procedure is now specified (TM §10.4). | Mark P0-049 gating for G-S2 whenever `deps_install` is enabled for a non-sandbox repo | P0b |
| VE-18 | Low | A, Operator | `mercury-ops` has App-level `contents:write` on public `project-mercury`, which holds `pins.json` (TM §8.6). Narrowing per token is SW-only (github.md §2.3). The residual is bounded because `project-mercury` `main` uses the target-repo ruleset (macos-service §15.1), so a push cannot reach `main` without the operator. | Keep the ruleset on `project-mercury` a P0d gate (drift-monitored); optionally host the anchor repo under a separate account/installation | P0d |
| VE-20 | Low | Orchestrator | TDD §15 "Merge verification (M1–M8)" paraphrases checks that are not in github.md §8 ("no foreign pushes; PR body/marker intact; ruleset unchanged"). It omits the MERCURY-review-state check (GH M8) and the base-commit audit (GH §9.6). | Replace with the GH §8 list by ID, or reference it only | Before M7 |

**Resolved disagreement (no finding): G-S5 placement.** E's Phase 4 text said "Unattended … (M7)"; F's roadmap §4 says "G-S5 at M9c entry; controls built in M7". These are compatible. The **controls** (anchoring, SEC-906, merge verification) are built and evidenced in M7–M8. The **gate** (G-ORG on targets, OD-36 decided, SAC-01…20 green) is recorded at M9c entry and is a precondition for any unattended or overnight dispatch, including during M9b. TM §8.10 now says this. One recommendation: OD-36 should be decided at **M8 exit**, as F proposes (`traceability.md` OD-36 row), so that option (b) (MERC-807b) does not delay M9c.

---
## 4. SEC requirement compliance matrix (against the final documents)

Status key: **S** satisfied in design (the implementing document specifies the control) · **P** partial (specified, but a gap or an inconsistency remains; finding cited) · **M** missing · **C** contradicted by a final document. "UNVERIFIABLE" means the control is fully specified but its effect can only be proven on the Mac or the live service. GH = `integrations/github.md`, CL = `claude.md`, CX = `codex.md`, LN = `linear.md`, CMP = `components.md`, SM = `state-machine.md`, MS = `macos-service.md`, REC = `recovery.md`.

| SEC | Tag | Status | Evidence (implementing location) | Note |
|---|---|---|---|---|
| 100 | GH | S | GH §9.1 ruleset JSON (PR, 1 approval, code owner, last push, stale dismissal, strict checks with integration ids, no bypass, deletion/non-FF); GH §9.4 O3/O4 | Live behaviour UNVERIFIABLE — TC-GOV-116 (SEC-T-16) in sandbox |
| 101 | GH | **P** | GH §2.2–§2.3, §3 token purposes correct | Contradicted by ADR-008 and MS §9.1 (VE-01, VE-03) |
| 102 | SW | S | GH §10.4 allowlist + explicit forbidden list; CMP §4.11 (no methods), CMP D6 lint, CT-04; SM INV-09 | §6.1 below |
| 103 | SW/POL | **P** | GH §2.1 row "Operator"; MS §9.1 last para | VE-16 (`gh attestation verify` inside `mercury upgrade`) |
| 104 | GH | S | GH §9.4 O2 | |
| 105 | GH | S | GH §9.5; O1 (CI on drafts); O9 attestation (POL part) | |
| 106 | POL | S | LN §9 operator policy; TM SEC-106; P0-074 checklist (verification plan §7.2 G-S1) | Policy only (N1) |
| 107 | SW | S | CMP §4.11 ownership by App user id; GH §7.6–§7.7 | |
| 108 | SW | S | GH §9.6 (start-up, wake, interval key `gov.drift_check_interval_min`) | Bound ≤ 60 min is in MS §2 table — UNVERIFIABLE timing, SEC-T-15 |
| 109 | GH/POL | S | GH §10.1–§10.2; ADR-014 | G-SPLIT gated by P0-233/P0-238 |
| 110 | GH | **P** | GH §2.3 (`mercury-ops` not on targets; `mercury-bot` not on ops repos) | MS §9.1, ADR-008, GH §9.4 O6 contradict (VE-01, VE-03, VE-08) |
| 111 | SW | S | CX §9 step 5; GH §4.2 | |
| 112 | GH | S | GH §9.5 tag ruleset | SHOULD |
| 113 | SW+GH | S | GH §6, §6.1, §6.2 (`action_required`, never `neutral`/`skipped`); CMP §4.11 `CheckConclusion` type; GH §9.1 integration-id pin | TM amended (VE-19); pinning UNVERIFIABLE — P0 ASM-B-56/57, SEC-T-17 |
| 114 | SW | S | GH §6.1 / TDD §15 (draft until CR success; review request after); SM §5.1 `spec_changed` re-draft | |
| 115 | SW+OS | S | CMP §5.2/§5.4 (★ methods, presence assertion bound to nonce + params); MS §9.5 helper; SM §6.1 ★ actions | VE-13, VE-14 (Low); helper UNVERIFIABLE — P0-045 |
| 201 | OS | S | MS §3.3–§3.5, §7.1, §3.11 gates; ADR-013; CMP §4.7 | **UNVERIFIABLE — P0-026…032, SEC-T-20 (G-S2)** |
| 202 | SW+OS | S | MS §3.5 steps 6–7, §3.6, §9.4; CL §7.2; sudoers `env_reset, !setenv` (MS §3.4) | Residual ASM-B-16 (model key via Codex env), accepted |
| 203 | SW | S | CX §5–§6; MS §7.1 `codex-home` row (config 0640 op, regenerated and byte-verified) | |
| 204 | SW+OS | **P** | CL §2.1 (settingSources [], no MCP, dontAsk, tool lists, confinement hook, no fallback model), CL §8 self-test | Managed-settings content incomplete (VE-06); `disableAllHooks` vs SDK hook UNVERIFIABLE — P0-201 |
| 205 | SW+OS | S | CMP §9.5; MS §7.1 snapshots row; MS §3.5 step 5 (`claude` cwd = snapshot) | §6.5 below |
| 206 | OS | **P** | MUST no-network for Codex and `verify`: CX sandbox flags, `verify.sb` (TM §8.7). `deps_install` allowlist mechanism: **specified now in TM §10.4 (P0-049)** | UNVERIFIABLE — P0-049, SEC-T-25 |
| 207 | SW/OS | S | MS §7.1 `runs/<run>/tmp`; CMP §9.7 | |
| 208 | SW+OS | S | MS §3.5 Codex row (allow-list grammar, forbidden list); CX §3 line 36; managed `requirements.toml` P0-048 | |
| 209 | SW | **P** | SM §8.8 (before every dispatch and resume) | Comparison base differs (VE-11; TM amended) |
| 210 | SW | S | MS §3.10 `doctor` table (sudoers digests, wrapper hashes, agent home scan) | |
| 211 | OS | S | CX §3; OD-09 | |
| 212 | OS+SW | S | MS §3.5 (12-step validation), §3.7 (`agent-ctl` identity triple, purge roots) | Fuzzing SEC-T-28 in `test-wrappers` CI + Mac |
| 213 | OS+SW | S (MUST) / M (SHOULD) | MUST: MS §7.3 Seatbelt writable roots, §3.9 per-repo caches | SHOULD worktree seal not specified in CMP §9 (optional; not a finding) |
| 214 | SW+OS | S | MS §3.5 step 11, §3.8; ADR-020 | |
| 215 | OS | S | TM §8.7 rules; MS §3.4 profiles path, §3.5 `verify`/`deps_install` grammar with pinned profile hash | Profile text not yet written; UNVERIFIABLE — P0-037, P0-049 |
| 301 | SW | S | CL §5.2 nonce-delimited untrusted blocks; LN LN-2 | |
| 302 | SW | S | LN LN-1/LN-2; CMP §5.4 (no approve/authorize methods); SM INV-17 | |
| 303 | SW | S | CL §6, §6.1 (wire copies + Ajv); messages.md §5 | |
| 304 | SW | S | CMP §4.16 `Redacted<NeutralisedText>`; LN §7 line 228; GH §5 | |
| 305 | SW | S | SM §8.1 authorization guard; CMP §4.10 `withinEscalateAllowance` | |
| 306 | SW | S | SM T09, T14, §8.2 | |
| 307 | SW | S | SM §5.1 `spec_changed` (AG@apply, CR `action_required`), §8.1 | |
| 308 | SW | S | SM §8.3; GH §6 (per-SHA check runs) | |
| 309 | SW | S | CMP §4.10 pipeline order; CX §9 steps 1–4 | |
| 310 | SW+GH | **P** | CX §9 step 2; GH §6.2; SM §8.7; TM SEC-310 (amended) | TDD §19 contradicts block-class for `.claude/**`/`.mcp.json` (VE-05); CX stricter (VE-09) |
| 311 | SW | S | CL §8 upgrade procedure; verification plan TC-PI-130 | |
| 312 | SW | S | CX §9 step 2 (bidi, zero-width, mixed script) | |
| 313 | SW | S | GH §7.3–§7.4 (operator numeric ids; label actor) | |
| 314 | SW | S | SM T24/T25 (two reviews); TDD §14 | |
| 315 | SW | S | SM §9 | |
| 316 | SW | S | SM T25 (`producer_kind = verbatim_render`); CL §3.3 hybrid rule | |
| 401 | SW | **P** | CX §9 hardening list; CMP §9.6 | CMP flag subset (VE-10) |
| 402 | SW | **P** | CX §9 pointer + `commondir`/`gitdir` check; CMP §9.3 `verifyGitPointer` | Mirror-config allowlist only hashed at start (VE-10) |
| 403 | SW | S | CX §9 step 2 | |
| 404 | SW | S | CX §9 step 1; CMP §4.10 | |
| 405 | OS | S | MS §7.1 (single source), §3.10 `doctor` modes | |
| 406 | SW+OS | S | MS §3.7 `purge`; CMP §9.7 | ASM-E-09 unit test TC-SEC-143 |
| 407 | SW | S | GH §10.4 (receive-pack to `refs/heads/mercury/**` only); MS §9.3 askpass fd; CMP §9.2; GH §9.3 FF-only | |
| 501 | SW | **P** | CMP §4.16 Redactor; MS §9.3 `Secret` type | Encodings and entropy stage not in CMP (VE-15) |
| 502 | SW | S | CX §9 step 3 (gitleaks + own patterns + exact match) | |
| 503 | OS/SW | S | MS §9.1–§9.3 (helper-only ACL, read once) | UNVERIFIABLE — P0-036 (else RISK-29 and signed helper in v1, Addendum A) |
| 504 | POL/SW | S | MS §9.1 rotation column | |
| 505 | SW | S | CMP §4.16 last para, §6.5 retention table | |
| 506 | GH | S | GH §9.5 | SHOULD |
| 507 | SW | S | GH §6.4; CMP §4.15 row `security_escalation` (generic text on public repos) | |
| 601 | SW | S | CMP §4.16 `AuditAppender.actorKind`; CMP §5.2 `control_requests` | |
| 602 | SW | S | CMP §4.16 chain; REC §4 step 7 | |
| 603 | SW | S | CMP §4.16 HMAC (SHOULD) → `reauthorization_required` | |
| 604 | SW+GH | **P** | CMP §4.16, GH §6.1 (private only), LN §7 `completed` comment | ADR-018 contradicts (VE-02); TM amended (VE-19) |
| 605 | SW | S | CMP §4.16 `AuditVerifier` | |
| 606 | SW | S | CMP §6.5 | SHOULD |
| 607 | SW | S | CMP §4.16 epochs (★ `restore --confirm`); MS §14.4; REC step 7 | |
| 701 | SW/POL | S | MS §13.5, §3.4 `agent.conf` hashes | |
| 702 | SW | S | CX §9 step 2 (escalate + lockfile lint); issue-breakdown MERC-5xx | |
| 703 | SW/OS | S | MS §3.5 `deps_install` row; CMP §8 (line 1768) | |
| 704 | SW/OS | S | MS §2.2–§2.3, §3.5 steps 8/11; §10 | |
| 705 | SW | S | LN §7 (mutation budget); MS §2 parameters | |
| 706 | SW | S | MS §13.2 (`npm ci --ignore-scripts`), §15.1 (SHA-pinned Actions, `supply-chain` job) | |
| 707 | POL/SW | S | GH §9.4 O9 attestation | SHOULD |
| 708 | SW/OS | S | MS §3.9 | |
| 801 | SW/POL | S | LN §2 (app actor, team restriction in code via `linear.teams`) | UNVERIFIABLE — P0-225 (ASM-E-05) |
| 802 | SW | S | CL §2.1 (`mcpServers: {}`); CX `CODEX_HOME` config (no `mcp_servers`) | |
| 803 | SW | S | LN §9 (delegate, coding session, foreign PR → `BLOCKED(foreign_agent)`) | |
| 804 | POL | S | LN §9 operator policy | |
| 805 | SW | S | LN §7 (line 224) write allowlist | |
| 806 | POL | S | roadmap M9c (Slack token revoked) | |
| 901 | SW | S | CMP §4.15 matrix | |
| 902 | SW | S | CMP §5.4 `pause` (operator), `unpause --safe-mode` ★ | |
| 903 | SW | S | SM §5.1 `security_halt` (sandbox violation); TM §8.9 | |
| 904 | SW | S | SM §8.3 | |
| 905 | SW | S | GH §8 M1–M8, GH §9.6 base-commit audit; SM §8.5 | TDD §15 paraphrase (VE-20) |
| 906 | SW | S | SM §5.1 holds, §8.5; TM §8.9 (amended to GH numbering) | |
| 907 | SW/POL | S | MS §11.6 (locked conversations, templates, App badge) | |
| 908 | SW | S | MS §5.2; REC §4; SM `integrity_check_failed` | |

**Summary:** 90 SEC rows. S = 79 (SEC-213 counted on its MUST part); P = 11 (101, 103, 110, 204, 206, 209, 310, 401, 402, 501, 604); M = 0 among MUST requirements (only the SHOULD worktree seal of SEC-213 is unspecified); **C = 0 at the requirement level**. The contradictions (VE-01/02/03/05) are in secondary documents; each requirement's owning implementer is correct.

---
## 5. Re-verification of the human-approval-boundary proof

**Invariant H** (TM §5.2): no commit authored or modified by an agent or by the coordinator becomes reachable from a protected branch unless the operator approved the exact head after the last push.

Method: for each path of TM §5.2.2 I traced the controls into the **final implementing documents** (not the TM's own claims). I classed each control as GH, OS or SW, and asked whether it would still hold if every LLM involved behaved adversarially (a prompt-level failure).

| # | Path | Controls actually specified (final docs) | Prompt-independent? | Verdict |
|---|---|---|---|---|
| 1 | Direct push to `main` | GH §9.1 ruleset: `pull_request` rule, `non_fast_forward`, `deletion`, `bypass_actors: []` (GH). GH §10.4: receive-pack only to `refs/heads/mercury/**` (SW). MS §3.6, §9.4: agents hold no GitHub credential; key only on fd 3 (OS) | Yes: GH alone suffices | **Blocked** |
| 2a | Counting approval by an agent or MERCURY | GH §9.1 `require_code_owner_review` + CODEOWNERS `* @<operator>` (GH §9.4 O2); `require_last_push_approval` (the bot is the last pusher) (GH). CMP §4.11 `createReview` typed `event: "COMMENT"`; D6 lint; GH §10.4 forbidden list (SW). Agents: no credential (OS). Detective GH §8 M8 → global halt | Yes | **Blocked** (GH alone suffices) |
| 2b | Approval for different code (TOCTOU, replay) | GH §9.1 `dismiss_stale_reviews_on_push`, `require_last_push_approval`, strict checks (GH). GH §6: check runs per SHA, `external_id` binds `task:head:gate`; SM §8.3 review binding (SW) | Yes | **Blocked** |
| 2c | Human approves misleading but genuine code | H holds by definition. Quality controls: `MERCURY / policy` `action_required` until a presence-bound ack (GH §6.2, CMP §5.2); draft until CR success (GH §6.1); separate security review (SM T24); neutraliser (CMP §4.16); SEC-507 | Partly: the acknowledgement path is SW + TCB; review quality is inherently LLM + human | **Holds**; residual RISK-05 |
| 2d | Non-human merge after genuine approval | G-ORG: GH §9.2 `update` rule, operator-only team bypass (GH). G-DETECT: GH §8 M2 global halt (SW, detective). Auto-merge: `allow_auto_merge=false` (GH §9.5) and no endpoint (GH §10.4). Update-branch: no endpoint; base moves only through the coordinator merge commit, which dismisses the approval (GH §7.5, SM T41) | Yes | **Holds** (preventive under G-ORG; detective under G-DETECT, accepted in writing) |
| 3 | Weakening the rules | No MERCURY App holds `administration` (GH §2.2–§2.3; contradicted only by stale ADR-008/MS §9.1 text, which grants nothing extra; VE-01/03). `.github/**` block-class (CX §9). Agents cannot read human credentials (MS §3.3, §7.1 0700 home). Drift monitor (GH §9.6) | Yes | **Blocked** (gated on SEC-T-20 for the OS layer) |
| 4 | Workflow with write power | GH §9.5 (Actions approve off, read-only token); no `workflows` permission (GH §2.2); `.github/**` block (CX §9); forged check: integration-id pin `1000001`/`15368` (GH §9.1) | Yes | **Blocked** |
| 5 | Human impersonation via Linear | LN §2 app actor, no `app:assignable`; CL §2.1 no MCP; agents cannot read human Linear session (OS) | Yes | **Blocked** for MERCURY agents (UNVERIFIABLE — P0-225 for the app actor's own reach) |
| 6 | Agent code through an unrelated human merge | `mercury/**` only (GH §10.4); per-PR last-push rule; foreign push → `BLOCKED(foreign_push)` (GH §7.6); base-commit audit (GH §9.6) | Yes | **Covered by 2** |
| N1 | Operator's interactive agents (human credential) | SEC-106 / OD-E-02 deny rules (POL); presence tier stops them clearing escalations (CMP §5.2, OS-backed helper); neutraliser reduces injection surface | **No** (policy) | **Open by design**, RISK-28 |
| N2 | Push redirection via worktree `.git`/config | CX §9 pointer check + explicit `GIT_DIR`; CMP §9.6; GH §10.4 push from mirror with fixed URL; MS §9.3 askpass fd | Yes (SW) | **Blocked**; and leaks only the App token, which cannot approve (L5) |
| N3 | Control-socket principal abuse | CMP §5.2 principals; ★ methods need `mercury-presence` nonce (MS §9.5); CMP §5.4: no approve/merge/authorize method exists | Yes (SW + TCB) | **Blocked**; cannot reach H in any case |

**Confirmation of the brief's constraint ("not relying solely on prompt instructions").** **Confirmed in design.** Paths 1, 2a, 2b, 2d, 3 and 4 are each closed by a GitHub-enforced control that neither the agents nor the coordinator can change: the ruleset in GH §9.1 combined with the App permissions in GH §2.2, which contain no `administration`. That control holds even if all of MERCURY's software fails, which is TM §5.2.3, row "Coordinator compromised", for MERCURY's *own* credentials. Path 5 and the credential half of path 3 rest on OS uid separation. In every path, prompts are layer L0 only and are assumed to fail.

Two qualifications are carried into §7:

1. **SEC-201 is load-bearing and unverified.** If an agent-class process can read any operator or MERCURY credential *and* any publish path exists, H fails, and a secret scanner cannot compensate (TM §5.2.3, RE-24). The design gates this correctly: MS §3.11, ADR-013 and roadmap G-S2 forbid non-sandbox write runs before SEC-T-20. The proof is therefore conditional on P0-027 / SEC-T-20.
2. **Coordinator compromise reaches the human's `gh` credential** (RISK-27). The GitHub layers stop MERCURY's tokens, not the human's. This is accepted for supervised operation, and OD-36 must be decided before unattended operation (Addendum A).

Single-control-failure re-check (TM §5.2.3): every row still matches the final documents. The row "`MERCURY / claude-review` forged by another identity" now also depends on the Phase 0 confirmation that the latest App-authored run of a name governs the requirement (GH §6, ASM-B-56). That is **UNVERIFIABLE IN DESIGN — P0 for ASM-B-56/57, SEC-T-17**.

---
