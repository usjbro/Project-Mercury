# Handoff — Project MERCURY design and development platform (as of 2026-10-23)

For the operator and for the next Claude Code session. Facts are separated from proposals.

**Nothing is merged, deployed or approved. No PR has been opened. No Linear issue has been created.**

## 1. Where everything is

| Branch | Stacked on | Content | State |
|---|---|---|---|
| `claude/mercury-tdd` | `main` (1 commit) | Mercury TDD v1.0-rc1 (32 sections), ADR-001…020, owner documents, reviews | Design only. **Not approved** (DOD-01) |
| `claude/dev-orchestration` | `claude/mercury-tdd` | v1 development orchestration ("local mode"): docs 00–13, devorch v2 tool + 30 tests, 13 agent definitions, settings deny rules, guard hook, reviews R1–R5 | Proposed. Tested in scratch repositories |
| `claude/devplatform-k8s` | `claude/dev-orchestration` | **Amendment 001: devplat**, a Kubernetes-native, multi-project platform. Docs 14–29, ADR-022…030, `platform/` (schemas, project configs, base manifests, Helm charts, PostgreSQL schema, Job generator, validators), review R6 and fix round | Proposed. **Never run on a cluster** |
| `claude/nice-edison-q1ai3u` | `claude/devplatform-k8s` | 2026-10-23: cross-group alignment, R6 dispositions, independent re-check and its fixes (§5) | Proposed. Offline-validated (§3, §8). **Never run on a cluster** |

**Start here:**
- Package index: `docs/mercury/development-orchestration/README.md`.
- Amendment texts: `amendments/`.
- Decisions awaiting you: **`OPERATOR-BRIEF.md`** (sequenced short list); full records in `12-amendments.md` (DOD-01…25).
- Review record: `reviews/R6-amendment-001.md`, `reviews/R6-dispositions.md`, `reviews/R6-recheck.md`.

## 2. What the design says (in one paragraph each)

**Mercury (the product).** Unchanged by the amendment. Mercury is a local coordinator on the operator's Mac: `mercuryd`, written in Node 24/TypeScript, using SQLite and run as a launchd LaunchAgent. Claude decides, Codex implements, and the operator alone approves and merges. Kubernetes is **not** a Mercury production dependency (`27-…`: 0 production changes; options P-1…P-4 would need their own ADRs).

**devplat (how Mercury gets built).** A project-agnostic control plane in Kubernetes, independent of Mercury and of Jupiter. It has these parts:
- **Controller** (deterministic): the task state machine ported from devorch, scheduling and admission, Job creation and reconciliation.
- **PostgreSQL:** the only writer is the controller, through SECURITY DEFINER functions.
- **gitbroker:** the only holder of the dev-bot App key. It validates agent output and pushes `dev/*` branches and **draft** PRs.
- **model gateway:** the only holder of the LLM key, with endpoint, tool-type and content-source allowlists (no server tools, no URL or file sources).
- **artifact gateway:** the only path for uploads from pods; each upload is authorized in PostgreSQL.
- **namespacer, devplat-dns, per-project read-only registry proxies.**

Every specialist run is a short-lived Job with:
- no credentials and no Kubernetes token;
- default-deny egress and gVisor, on a tainted exec node pool.

Gates G1–G7 work as in v1, and G7 is your observed merge. Tests that need macOS (Mercury T4) stay on an external macOS lane.

**Jupiter.** No repository, Linear project, Notion page or document was found. `platform/projects/jupiter.onboarding.yaml` is `draft` with every value unresolved and 24 questions for you. Nothing was invented.

## 3. Verified state (offline)

The single command, run in this container on 2026-10-23 at the head of `claude/nice-edison-q1ai3u`:

```
GO=/usr/local/go1.24.7/bin/go HELM=… KUBECONFORM=… platform/tools/validate_all.sh --strict
```

Helm v3.17.3 and kubeconform v0.6.7 were built from source into the session scratchpad (`go install`); nothing was installed on a host. Results are in §8.

**What these checks do not show:** runtime behaviour on a cluster (NetworkPolicy enforcement, gVisor, admission with typed objects, the Job lifecycle, recovery), GitHub behaviour (ruleset, App permissions), real images (none exist), the gateways, gitbroker, namespacer and controller (none are built), or the Claude Code headless flags (V-16-1).

## 4. Review status

| Review | Result |
|---|---|
| R1–R4 (v1) | Critical/High dispositions in `reviews/R0-dispositions.md` |
| R5 (v1 re-check) | Guard hook **did not fire** in live subagent dispatch (DOD-10). Dispositions in `R5-recheck.md` |
| R6 (Amendment 001) | Findings and decisions D1–D26: `reviews/R6-amendment-001.md`. Per-finding fix, location, check and status: `reviews/R6-dispositions.md` |
| R6 re-check (2026-10-23) | Independent, read-only, fresh-context reviews with the `mdev-lead-architect` and `mdev-security-engineer` briefs against `ea13dd5`: both **changes_required**: 2 new High (RA-1 Job name/key collision between roles; RS-1 model-gateway URL content sources) and 11 Medium. **All fixed** (RS-9 after the confirmation pass). Confirmation pass on `c249c51`: both **accept_with_conditions**; the conditions (RC-1 manifest alias without role, C-1 block-type and field allowlists) are fixed. Record: `reviews/R6-recheck.md` |

## 5. Done on 2026-10-23, and open items

**Done** (branch `claude/nice-edison-q1ai3u`, stacked on `claude/devplatform-k8s`):
1. The six cross-group mismatches: `plan_proposal` is a DB kind (SHORT, read-only, ids `<task>-pN` / `PL-<nnnn>`); `issue_tracker.write_fact` (config schema minor 2); contract v2 `path`/`sha256` for `INTERFACE_FROZEN`; per-Job tokens registered by `set_job_tokens()` and authorized in PostgreSQL (docs 16, 18, charts, base); the 10-minute admission rule (docs 16, 17, DB test); the onboarding rule (the stale text was in ADR-029, not doc 26).
2. `mercury.yaml` config_version 3: no in-cluster build environment; images are built in devplat CI (doc 22 O-5).
3. A-05 direction (subject to your review): project-neutral role bodies plus a project section generated from the project config. The generator part is implemented and tested; the 13 neutral bodies are not written (R-1).
4. `reviews/R6-dispositions.md`; decisions that had never reached the files were applied (A-15 checkpoint anchoring; D13 CI hardening in the DOD-02 row; contract v2 `frozen_by`).
5. Independent re-check run, its findings fixed, confirmation pass run and its two conditions fixed (`reviews/R6-recheck.md`); strict validation green.
6. Operator decision brief: `OPERATOR-BRIEF.md`.

**Open, in order:**
1. Open residuals in `R6-dispositions.md` §4 (R-1 neutral role bodies after DOD-12; R-2 every runtime check; R-5 your decisions; R-7 a cluster-scoped baseline deny for project namespaces at DP4).
2. PRs: the original brief forbade opening PRs without your authorization. None has been opened.

## 6. Decisions only the operator can make

The full list is in `12-amendments.md`. The ones that unblock the most:

| ID | Decision | Unblocks |
|---|---|---|
| DOD-11 | Adopt devplat with topology B (one cluster, dedicated exec nodes, gVisor) | Everything on the platform track |
| DOD-25 | Build vehicle for devplat itself. Recommended: supervised interactive sessions with your review of every PR (DP1–DP3); devplat builds itself from DP5 | DP1 |
| DOD-12 | Create a dedicated platform repository (agents cannot create repositories) | Independence; DP1 |
| DOD-13 | GitHub App for the dev bot (`contents:write` on `dev/*`, draft PRs; it *can* merge or approve through the API, so the ruleset is the control) | Any push |
| DOD-02 | Per repository: ruleset on `main` (code-owner review, no bypass actors) **plus** CI hardening (read-only workflow token, Actions cannot create or approve PRs, no secrets for `dev/**`, tag/release protection) | Any code task |
| DOD-14 | OIDC provider and the operator allowlist | Authenticated operator facts |
| DOD-15 | First cluster and authority to install software on it (workstation kind/k3d first) | DP3, every runtime test |
| DOD-01 | Approve the Mercury TDD | Mercury implementation (DP6) only. It no longer gates devplat |
| DOD-16 | Allow interim Mercury work in v1 local mode before DP4 (not recommended) | Mercury timing |

## 7. Schedule (estimates, not measured)

- **devplat DP0–DP4:** about 33–36 working days at 100 % operator availability, 36–40 at 50 %, and 78–85 at 20 %. P90 ≈ ×1.5. See `28-…` §3. This becomes a modelled schedule once DOD-11 is approved.
- **Mercury after DP4:** 92 working days at 100 % (118 at 50 %, 219 at 20 %), per the v1 model in `05-…`.
- **Your availability is the dominant factor,** because every PR waits on your review and merge.

## 8. Final validation log

`GO=… HELM=… KUBECONFORM=… platform/tools/validate_all.sh --strict` on 2026-10-23 at the head of `claude/nice-edison-q1ai3u`: **ALL CHECKS PASSED (nothing skipped), exit 0.**

| Check | Result |
|---|---|
| devorch v1 regression | 30 tests OK |
| devorch examples drift | OK |
| Job generator (`test_jobspec.py`) | 14 tests OK; output equals the doc 16 example via the vendored fixture |
| Project configs, plus validator self-test | 2/2 valid; self-test 50/50 |
| Execution profiles schema; task contract v2 example | pass |
| Task contract v2 rules (`platform/schemas/test_schemas.py`) | 7 tests OK |
| Generated base manifests up to date | pass |
| Base manifests, strict Kubernetes 1.33 | 140 valid |
| Role ConfigMap generator tests; output | 12 tests OK; output valid |
| PostgreSQL state schema (real PostgreSQL 16) | 53 tests OK |
| Admission policies (CEL compile and behavioural cases) | 131 expressions compiled; 125 cases / 143 decisions; 0 mismatches |
| Charts | 58 passed, 0 failed, 0 skipped |

Mutation checks run this round (each weakened rule made at least one test fail): DB 8 (plan_proposal id branch, kind writable, `PL-` pattern, admission TTL, mandatory hard preconditions, write-fact separation, role-less jobspec formulas, NULL execution target); generator 4; charts 1 (`db-paths`).

All results are offline. No cluster or GitHub behaviour is covered (§3).