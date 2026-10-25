# 28 — Updated implementation roadmap (devplat, Amendment 001)

Status: **Proposed** (revised after R6 A-07). Nothing here is authorized to start before the decisions in §4.
Reuses / supersedes:
- Mercury's roadmap and issue DAG (`planning/`, `05-…`) are **unchanged**.
- This document adds the platform track **DP0–DP6**, which comes before agent-driven Mercury implementation on devplat.
- v1 local mode remains available for Mercury design and planning work.

## 1. What builds devplat (the build vehicle)

devplat cannot build itself before it exists. The DP1–DP4 code (controller, gitbroker, gateways, namespacer, API, images) needs a vehicle. This is operator decision **DOD-25**:

| Option | How | Controls | Assessment |
|---|---|---|---|
| **V1: Interactive Claude Code sessions on the platform repository** | One supervised session per DP issue (as in this session). Every change goes through a draft PR that the operator reviews and merges | Platform repository ruleset (DOD-12/DOD-02 shape) and human review of every PR. No unattended agents | **Recommended for DP1–DP3.** Lowest new risk; throughput limited by operator review |
| V2: v1 local mode (devorch) pointed at the platform repository | devorch with a DP DAG and assignments | Needs DOD-02, DOD-03, DOD-09 and DOD-10 for that repository; the R5 residuals stay | Possible, but adds risk without much speed while the operator reviews every PR anyway |
| V3: The operator writes the code | — | — | Possible for small parts (bootstrap scripts, cluster setup) |
| **Then: devplat builds devplat** | From DP4 exit, the platform repository is registered as project `devplat` (project #0) and its remaining issues run as Jobs | All devplat controls apply to its own repository. A broken devplat is repaired with V1 | **Recommended from DP5** |

Rule: devplat never deploys itself. Upgrades of the running platform are operator actions (`24-…` §6).

## 2. Phases

| Phase | Goal | Deliverables (components) | Vehicle | Exit evidence (`29-…`) |
|---|---|---|---|---|
| **DP0** Decisions | Platform decisions, independent of Mercury's TDD approval | DOD-11…15, DOD-25; platform repository created (DOD-12); dev-bot App created for the platform repository (DOD-13); OIDC provider (DOD-14) | Operator | Recorded decisions |
| **DP1** Repository and CI | Independent home and CI of record | Move `platform/` and the package docs; platform CI (`validate_all.sh --strict`, image build/scan/sign); ruleset plus CI hardening (DOD-02 shape, `23-…`) | V1 | AT-01, AT-02 in the platform CI |
| **DP2** State and controller core | Deterministic controller without a cluster | `platform/db` hardened (R6 D1–D9); **migration runner** (Helm hook Job); controller reconciler with a fake Kubernetes client; port of the 30 devorch cases; `devplat-api` (operator facts, approvals, OIDC, `operator_identities`); **v1 ledger import tool** | V1 | AT-03…AT-07 |
| **DP3** Execution path | First real agent Job on a workstation cluster | Agent and fetch images; runner; **gitbroker** (validation port + push + draft PR) and **gitbroker-fetch**; **model gateway** (endpoint allowlist, D12); **artifact gateway** (D10); **devplat-dns**; **role ConfigMap generator** (exists); **project-config renderer** (config → `devplat-project` values); bootstrap steps 1–9 | V1 | AT-08…AT-12 |
| **DP4** Hardening and recovery | Infrastructure-enforced boundaries proven | **namespacer** Deployment (D19); **per-project read-only registry proxy** (D14); NetworkPolicy enforcement on an enforcing CNI; gVisor on the exec pool; admission with typed objects; recovery drills; bootstrap step 10; **checkpoint signer** (DOD-18) | V1, then V3 for cluster work | AT-13…AT-22 |
| **DP5** Multi-project and operations | Two projects; dashboard; budgets | Admission fair share; budget reservations; dashboard; Linear adapter (read-only until a project's `write_fact` is recorded); a dummy third project onboarded by configuration only; **devplat registered as project #0** | devplat itself (with V1 fallback) | AT-23…AT-28 |
| **DP6** Project work | Mercury, and Jupiter once onboarded | Mercury tasks as Jobs; macOS lane wired as `mac_validation` tasks; Jupiter `draft` → `active` per `26-…` §3.4 | devplat | Mercury W0–W1 issues through G7 |

## 3. Effort and calendar (estimate, not measured)

Effort is estimated per phase in **agent-days** (session work) and **operator-days** (decisions, PR reviews, cluster actions). With vehicle V1, every PR also costs operator review time. The calendar for a phase is roughly the larger of the agent work and the operator work divided by operator availability. Phases run serially (DP5 may overlap DP4).

| Phase | Agent-days (P50) | Operator-days (P50) | PRs (≈) |
|---|---|---|---|
| DP0 | 0.5 | 2.5 | 0 |
| DP1 | 3 | 1.5 | 6 |
| DP2 | 9 | 3 | 14 |
| DP3 | 12 | 4.5 | 18 |
| DP4 | 7 | 4 | 10 |
| **DP0–DP4** | **31.5** | **15.5** | **48** |

| Operator availability | Calendar working days, DP0–DP4 (P50) | Comment |
|---|---|---|
| 100 % | ≈ 33–36 | Agent-bound |
| 50 % | ≈ 36–40 | Operator-bound in DP0 and DP4 |
| 20 % (two half-days per week) | ≈ 78–85 | Operator-bound throughout |

P90 ≈ P50 × 1.5, because of first-of-kind risks: gVisor and BuildKit spikes, CNI enforcement, the GitHub App shape on a personal account.

**Method.** Phase sums only; there is no issue-level DAG yet. When DOD-11 is approved, a DP issue DAG (≈ 50 issues) will be generated and run through `tools/devorch/schedule_model.py`, using the same operator-lane model as Mercury (`05-…` §4). That replaces this table.

**Effect on Mercury.**
- Agent-driven Mercury implementation on devplat starts after DP4. That is roughly 7–8 weeks after DP0 at 100 % operator availability, and 16–17 weeks at 20 %.
- Mercury W0 operator tasks and design/planning work can run in parallel.
- The Mercury schedule itself (92 working days at 100 %, `05-…`) is unchanged and starts later.
- The alternative is v1 local mode for Mercury implementation before DP4 (DOD-16), which keeps the R5 residual risks.
- `27-…` records this impact on TDD §27 and roadmap §6.

## 4. Decisions gating the roadmap

These are listed in full in `12-amendments.md`.

| Decision | Gates |
|---|---|
| DOD-11: adopt devplat and topology B | DP0 |
| DOD-25: build vehicle (§1) | DP1 |
| DOD-12: platform repository (ADR-030) | DP1 |
| DOD-13: dev-bot App (platform repository first, then each project repository) | DP1 (platform repository), DP6 (Mercury) |
| DOD-14: OIDC provider | DP2 exit |
| DOD-15: first cluster target and authority to install software on it | DP3 |
| DOD-17…22: namespacer, checkpoint signing, PostgreSQL deployment, LLM keys, TLS, artifact store | DP2–DP4 as noted there |
| DOD-01…03 (Mercury TDD approval, Mercury ruleset, identity) | **DP6 only.** Building devplat does not depend on Mercury's TDD approval (independence, R6 A-07) |
| DOD-16, DOD-23, DOD-24 | Mercury work on devplat |

## 5. Issue breakdown

No DP issues are created yet: there is no Linear project, and Linear writes are not authorized (DOD-05). After DOD-11 and DOD-25, a breakdown of about 50 DP issues with dependencies and estimates is proposed for operator approval. Each issue follows the v1 DoR/DoD and gates. The platform's acceptance tests in `29-…` are its exit criteria.
