# Handoff — Project MERCURY design and development platform (as of 2026-10-23)

For the operator and for the next Claude Code session. Facts are separated from proposals.

**Nothing is merged, deployed or approved. No PR has been opened. No Linear issue has been created.**

## 1. Where everything is

| Branch | Stacked on | Content | State |
|---|---|---|---|
| `claude/mercury-tdd` | `main` (1 commit) | Mercury TDD v1.0-rc1 (32 sections), ADR-001…020, owner documents, reviews | Design only. **Not approved** (DOD-01) |
| `claude/dev-orchestration` | `claude/mercury-tdd` | v1 development orchestration ("local mode"): docs 00–13, devorch v2 tool + 30 tests, 13 agent definitions, settings deny rules, guard hook, reviews R1–R5 | Proposed. Tested in scratch repositories |
| `claude/devplatform-k8s` | `claude/dev-orchestration` | **Amendment 001: devplat**, a Kubernetes-native, multi-project platform. Docs 14–29, ADR-022…030, `platform/` (schemas, project configs, base manifests, Helm charts, PostgreSQL schema, Job generator, validators), review R6 and fix round | Proposed. Offline-validated (§3). **Never run on a cluster** |

**Start here:**
- Package index: `docs/mercury/development-orchestration/README.md`.
- Amendment texts: `amendments/`.
- Decisions awaiting you: `12-amendments.md` (DOD-01…25).
- Review record: `reviews/R6-amendment-001.md`.

## 2. What the design says (in one paragraph each)

**Mercury (the product).** Unchanged by the amendment. Mercury is a local coordinator on the operator's Mac: `mercuryd`, written in Node 24/TypeScript, using SQLite and run as a launchd LaunchAgent. Claude decides, Codex implements, and the operator alone approves and merges. Kubernetes is **not** a Mercury production dependency (`27-…`: 0 production changes; options P-1…P-4 would need their own ADRs).

**devplat (how Mercury gets built).** A project-agnostic control plane in Kubernetes, independent of Mercury and of Jupiter. It has these parts:
- **Controller** (deterministic): the task state machine ported from devorch, scheduling and admission, Job creation and reconciliation.
- **PostgreSQL:** the only writer is the controller, through SECURITY DEFINER functions.
- **gitbroker:** the only holder of the dev-bot App key. It validates agent output and pushes `dev/*` branches and **draft** PRs.
- **model gateway:** the only holder of the LLM key, with an endpoint allowlist that rejects server tools.
- **artifact gateway:** the only path for uploads from pods.
- **namespacer, devplat-dns, per-project read-only registry proxies.**

Every specialist run is a short-lived Job with:
- no credentials and no Kubernetes token;
- default-deny egress and gVisor, on a tainted exec node pool.

Gates G1–G7 work as in v1, and G7 is your observed merge. Tests that need macOS (Mercury T4) stay on an external macOS lane.

**Jupiter.** No repository, Linear project, Notion page or document was found. `platform/projects/jupiter.onboarding.yaml` is `draft` with every value unresolved and 24 questions for you. Nothing was invented.

## 3. Verified state (offline, in the authoring container)

The latest full run is summarized in §3.1. The single command is:

```
GO=/usr/local/go1.24.7/bin/go HELM=… KUBECONFORM=… platform/tools/validate_all.sh --strict
```

Helm v3.17.3 and kubeconform v0.6.7 were built from source into the scratchpad. They were not installed on any host.

Last results reported by the fix groups (2026-10-22):

| Check | Result |
|---|---|
| devorch v1 regression | 30/30 |
| Job generator (`platform/controller/test_jobspec.py`) | 13/13. Output equals the doc 16 example via a vendored fixture |
| Project configs + validator self-test | 2/2 valid; 46/46 mutations rejected |
| Base manifests, strict Kubernetes 1.33 | 140/140 |
| Admission policies | 128 CEL expressions compile; 115 cases / 133 decisions, 0 mismatches. Includes 10 exploit regressions from the security review, all denied |
| PostgreSQL state (`platform/db/test_schema.py`, real PostgreSQL 16.15, applied by the migrator login) | 47/47, stable over 6 runs; 17/17 rule mutations caught |
| Charts (`platform/tools/charts/run.sh`) | 51 passed, 0 skipped. Includes 30 negative renders and chart/base parity |

**What these checks do not show:** runtime behaviour on a cluster (NetworkPolicy enforcement, gVisor, admission with typed objects, the Job lifecycle, recovery), GitHub behaviour (ruleset, App permissions), real images (none exist), or the Claude Code headless flags (V-16-1).

### 3.1 Latest full run

`validate_all.sh --strict` at commit `b26ff34` on 2026-10-23: see §8. If §8 is empty, the run did not finish in the handoff session.

## 4. Review status

| Review | Result |
|---|---|
| R1–R4 (v1) | Critical/High dispositions in `reviews/R0-dispositions.md` |
| R5 (v1 re-check) | Guard hook **did not fire** in live subagent dispatch (DOD-10). Dispositions in `R5-recheck.md` |
| R6 (Amendment 001) | Architecture: accept_with_conditions for the direction, rejected as an implementation baseline until fixes land. Security: changes_required (3 High: model-gateway server tools, S3 egress, agent code in CI). Fix decisions D1–D26 applied by four groups (database, security/base, core docs and schemas, charts/build) |

**R6 is not yet closed.** Remaining work:
1. Write `reviews/R6-dispositions.md`: per finding A-01…A-30 and S-1…S-24, its fix, location and test.
2. An **independent re-check** of the High findings against the current head. This is required before calling the package ready for operator review.

## 5. Open items for the next session (in order)

1. **Cross-group mismatches** reported by the database group, not yet applied:
   - Doc 26 still lets `onboarding` projects run `design` Jobs. D4 and the DB allow only short-lifecycle read-only kinds.
   - The project-config schema needs `issue_tracker.write_fact` (the per-project Linear write fact, replacing hard-coded DOD-05).
   - The task-contract v2 dependency items need optional `path`/`sha256` for `INTERFACE_FROZEN`.
   - Doc 18 §8.2: upload tokens are registered by the controller (`set_job_tokens()`) and authorized in PostgreSQL. Port 9444 is an admin channel only.
   - Docs 16/17 must say that `dispatch_job()` requires an admission decision of at most 10 minutes.
   - The DB has no task kind `plan_proposal`, so planner Jobs can't be dispatched yet. Add it as a SHORT kind.
2. `platform/projects/mercury.yaml` still plans in-cluster toolchain builds. Builds are off by default (D20), so builds move to platform CI (doc 22 O-5).
3. A-05 is only partly closed: the 12 role definitions still contain Mercury scopes and paths. The runtime preamble overrides only the v1 mechanics. Decide between per-project role overlays and a neutral rewrite.
4. Write R6 dispositions, run the independent re-check (`mdev-security-engineer` and `mdev-lead-architect`, read-only), fix any new Critical or High findings, and re-run `validate_all.sh --strict`.
5. Then prepare the operator decision brief: the short list in §6. Optionally open a **draft** PR per branch for review, **only if the operator authorizes PRs** (the original brief forbade opening PRs without authorization).

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

Filled in by the handoff session from `validate_all.sh --strict`.
