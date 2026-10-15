# 12 — Proposed Roadmap Amendments, ADR Amendments and Operator Decisions

None of these is in effect. Each needs operator approval. **The TDD's design is not changed** by this package. The amendments add a development-process layer and roadmap sequencing advice.

## 1. Proposed ADR

**ADR-021 (Proposed): Temporary development orchestration for building MERCURY.** Draft: `architecture/decisions/proposed/ADR-021-development-orchestration.md`.

- Records the decision to build MERCURY with a Claude Code main-session orchestrator and 12 project subagents, with a git-ledger branch.
- Records the separation rules S1–S4 (`01-…` §1) and that the development system holds no production authority.
- **Interaction with existing ADRs:** none superseded.
  - ADR-003 is unaffected; the development hub-and-spoke model mirrors it.
  - ADR-008 is unaffected: development identities are separate (DOD-03).
  - ADR-014's governance applies to `project-mercury` only at self-hosting Stage D (`11-…`).

## 2. Roadmap amendments (proposals to `planning/roadmap.md` and `issue-breakdown.md`)

| # | Amendment | Rationale | Effect |
|---|---|---|---|
| RA-D1 | Add issue **MERC-031 "Development orchestration bootstrap"** to E0d. Scope: create the `devorch/state` branch, validate agents after a session restart (`claude --debug`), run the example ledger. P50 0.5 d. Blocked by MERC-030 | Makes Stage A verifiable | +0.5 d, off the critical path |
| RA-D2 | Make MERC-030 explicitly include: ruleset on `main` (DOD-02); development identity (DOD-03); MERCURY CI with **GitHub-hosted macOS runners** for T1 macOS tests | The human boundary for development work, plus Mac-lane offload (scenario C′) | No change to estimate |
| RA-D3 | Insert an **interface-freeze task** at the start of M1 (MERC-100, Lead Architect, P50 1 d, blocked by MERC-030). Freezes `src/ports/*` and the transition-table format, letting 112/402a/303/107/201/202 start against fakes | Converts a hidden coordination need into a scheduled item | +1 d at the start of the chain; enables W1/W2 parallelism |
| RA-D4 | **Mac validation windows.** Batch Mac-lane steps into scheduled operator sessions (e.g. 2 × ½ day per week), with scripts prepared in advance by agents | The operator lane is the binding constraint; batching cuts context switching | Planning practice; the schedule model assumes availability equivalent to this |
| RA-D5 | Run MERC-001/002/003 and MERC-020/021/022 **in the first week**, before most code | They gate 40–70 downstream issues each | Pulls the critical path forward |
| RA-D6 | Keep the 82-issue backlog in `issue-breakdown.md` until DOD-05. The TPM drafts the Linear import as a file for operator approval; no bulk creation without approval | Brief: "do not create a large Linear backlog without approval" | — |

## 3. New operator decisions for development orchestration (DOD)

| ID | Decision | Options | Recommended | Needed by |
|---|---|---|---|---|
| **DOD-01** | Approve this development orchestration package (Stage A) **and** approve the TDD, at least scoped for P0–M1, as the design baseline for Gate 1 | approve / approve scoped / reject | Approve the TDD for P0–M2 scope + this package | Before any implementation task |
| **DOD-02** | Ruleset on `project-mercury` `main` | as in `08-…` §4 | Require PR + operator approval + CI; block force-push/deletion | MERC-030 |
| **DOD-03** | GitHub identity for development agents | (a) dev bot / (b) operator-authored with 0 required approvals / (c) none | (a) | Before the first code PR |
| **DOD-04** | Where the orchestrator runs | cloud sessions / the Mac / both | Cloud for agent-only work; the Mac only for the Mac lane | Stage A start |
| **DOD-05** | When and how to import MERC issues into Linear | now / after DOD-01 / never (keep in repo) | After DOD-01, as a reviewed import file, one team project | Optional |
| **DOD-06** | Review of root-level artefacts (sudoers, wrappers, installers) before the operator runs them | operator review required / Security Engineer only | Operator review required | MERC-010 |
| **DOD-07** | Allow extra parallel cloud sessions as workers | no / yes with cap | No until 10 tasks have been measured | After W1 |
| **DOD-08** | Daily development cost cap | amount | Set by the operator; dispatch stops at 80 % | Stage A start |

## 4. Proposed TDD change summary

**No normative TDD content changes.** One cross-reference is proposed for TDD §27 (Implementation Roadmap), for the operator to approve:

> "Implementation is executed by the temporary development orchestration system described in `docs/mercury/development-orchestration/` (ADR-021, proposed), which holds no production authority and is retired per its self-hosting plan."
