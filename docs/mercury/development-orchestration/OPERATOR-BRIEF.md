# Operator decision brief — devplat (Amendment 001)

Prepared 2026-10-23 for the repository owner. **Nothing here is decided until you decide it.** Each item gives the recommendation, what saying no costs, and what it unblocks. The full decision records are the DOD rows in `12-amendments.md`; the gating per phase is `28-roadmap-k8s.md` §4.

## Where things stand

- The design package (docs 14–29, ADR-022…030, `platform/`) is proposed and validated offline only: `platform/tools/validate_all.sh --strict` passes with nothing skipped. Nothing has run on a cluster, no component of devplat is built, nothing is merged, and no PR is open.
- Review R6 is closed offline. Two independent read-only reviews found 2 High and 11 Medium issues after the fix round; all are fixed except one Low (`reviews/R6-recheck.md`). A confirmation pass by the same reviewers accepted, with two conditions that are now fixed.
- What only a cluster can show (NetworkPolicy enforcement, gVisor, typed admission, the gateways' request filtering, recovery) is listed as verification items in docs 16 and 29.

## 1. Decide first — these unblock DP1

| ID | Decision | Recommendation | If you say no / defer | Unblocks |
|---|---|---|---|---|
| **DOD-11** | Adopt devplat, topology B: one cluster, a dedicated tainted exec node pool, gVisor | **Adopt B**; allow topology A only as a declared reduced-assurance workstation mode | Mercury is built with v1 local mode (devorch on your Mac) with the R5 residuals (DOD-16), or not built yet | All platform work; turns the schedule estimate into a modelled one |
| **DOD-25** | What builds devplat itself (DP1–DP4) | **V1**: supervised interactive Claude Code sessions on the platform repository, you review and merge every PR (DP1–DP3); **V3** (you) for cluster setup; devplat builds itself from DP5 as project #0 | V2 (devorch) adds risk without speed while every PR waits for you | DP1 |
| **DOD-12** | Create a dedicated platform repository and move `platform/` and this package there (ADR-030) | **Create** — agents cannot create repositories | devplat stays inside Project-Mercury, which breaks the independence criterion (A-07) | DP1 |
| **DOD-13** | GitHub App for the dev bot: `contents:write` on `dev/*`, draft PRs, no `workflows`, no administration, not a ruleset bypass actor | **Approve as scoped**, first for the platform repository | No pushes by the platform at all; every change is hand-pushed | Platform repository pushes (roadmap §4 places this at DP1 for the platform repository; the DOD-13 row says DP3, which is when Mercury needs it) |
| **DOD-02** (platform repository) | Ruleset on `main` (PR, code-owner review by you, approval of the latest push, required checks, no force-push or deletion, **no bypass actors**) **plus** CI hardening H1–H8 (`23-…` §2a) | **Apply** before the first agent-authored PR | The App can approve and merge through the API (S-14); without the ruleset nothing stops it | Any agent push |

**Important correction carried in these records:** the App *can* approve and merge with the permissions it needs (S-14). The ruleset in DOD-02 is the control, not the App's scope.

## 2. Next — DP2 and DP3

| ID | Decision | Recommendation | Unblocks |
|---|---|---|---|
| **DOD-14** | OIDC provider for operator actions (facts, approvals, budgets) and the operator allowlist | GitHub OAuth restricted to you, via Dex or oauth2-proxy | Authenticated operator facts (needed before any project can become `active`) — DP2 exit |
| **DOD-19** | PostgreSQL: CloudNativePG in-cluster or managed | CNPG on the workstation; managed for server and cloud | DP2 |
| **DOD-15** | First cluster target and authority to install software on it | Workstation kind or k3d for DP3; a server or cloud cluster for DP4 (gVisor, several nodes) | DP3 and every runtime check |
| **DOD-20** | LLM keys: one key with per-project budgets, or one per project | Per project where the provider supports it | DP3 |
| **DOD-22** | Artifact store (MinIO community edition is reported archived) | Filesystem PVC on the workstation for DP3; external S3 afterwards | DP3 |

## 3. Later (DP4–DP5), recorded so they are not forgotten

DOD-17 (dedicated namespacer Deployment from DP4 — the charts already assume it), DOD-21 (TLS from DP4; mTLS for topology C), DOD-18 (signed `task_events` checkpoints before any unattended operation; anchored in object-lock storage, not git).

## 4. Mercury-specific (DP6 only — they do not block devplat)

| ID | Decision | Recommendation |
|---|---|---|
| DOD-01 | Approve the Mercury TDD as the design baseline | Approve for P0–M2 when you are ready; it no longer gates devplat |
| DOD-02, DOD-13 (Mercury repository) | Ruleset + CI hardening; dev-bot App installed on Project-Mercury | As for the platform repository, before Mercury code tasks |
| DOD-16 | Interim Mercury work in v1 local mode before DP4 | **No**, unless the schedule requires it (R5 residuals: the guard hook did not fire, DOD-10) |
| DOD-23 | Mercury path policy: `docs/**` restricted for agents | Allow `docs/mercury/architecture/decisions/proposed/**` for the Lead Architect with design review. `.github/**` stays restricted (now enforced by H8) |
| DOD-24 | T3 sandbox credentials as cluster Secrets | Keep T3 on the Mac lane until DP4 passes |
| DOD-05 | Linear import and writes | Now per project: writes need the project's own `issue_tracker.write_fact`, recorded by you |
| DOD-03…10 | v1 local-mode decisions | Only needed if you choose v1 local mode (DOD-16 yes, or DOD-25 V2) |

## 5. Choices made in this round that you may reverse

These were applied by the agent within the recorded decisions; each is easy to undo.

1. **A-05 direction:** project-neutral role definitions plus a section generated from each project's configuration, instead of per-project hand-written overlays. The generator is built and tested; the 13 neutral definitions are not written (they belong in the platform repository). If you prefer overlays, say so before DP1.
2. **O-5:** Mercury's toolchain and agent images are built in devplat CI, not in the cluster (`mercury.yaml` config_version 3). Reversing it needs DOD-15, enabling builds (D20) and spike S-B1.
3. **Cross-project dependencies** are refused by the DB until they are designed (they were documented as working but could not be stored correctly).
4. **The verifier is no longer exempt** from the project-status check at dispatch (the exemption could never take effect).

## 6. What the agent will not do without you

Open PRs (your original brief requires authorization), merge or approve anything, create repositories or GitHub Apps, change rulesets or settings, provision secrets, or install software on any host or cluster.

## 7. Time (estimates, not measured)

devplat DP0–DP4: about 33–36 working days at 100 % of your availability, 36–40 at 50 %, 78–85 at 20 % (P90 ≈ ×1.5). Mercury after DP4: 92 working days at 100 %. Your review time is the dominant factor because every PR waits on you (`28-…` §3).
