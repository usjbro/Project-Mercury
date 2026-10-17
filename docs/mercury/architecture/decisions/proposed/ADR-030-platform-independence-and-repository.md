# ADR-030 — Platform independence and a dedicated platform repository

| | |
|---|---|
| Status | **Proposed** (requires operator approval: DOD-12; Architecture Amendment 001). The repository does **not** exist; only the operator can create it |
| Date | 2026-10-17 |
| Owner | Lead Architect (development platform) |
| Related ADRs | ADR-021 (development orchestration), ADR-029 (project configuration contract); Mercury ADR-001…020 unaffected |

## Context

devplat (the Kubernetes-native development platform, `platform/` plus `docs/mercury/development-orchestration/`) currently lives on the branch `claude/devplatform-k8s` of `usjbro/Project-Mercury`, stacked on the unmerged branches `claude/dev-orchestration` and `claude/mercury-tdd`. Keeping it there has three problems:

1. **Coupling.** The platform that builds Mercury and Jupiter would be versioned, reviewed and released with one of its tenants. A Mercury ruleset change, a broken Mercury `main` or a Mercury history rewrite would affect the platform; a Jupiter onboarding PR would land in Mercury's repository.
2. **Authority confusion.** Mercury's repository is a target governed by its own rules (P0d, MERC-030); devplat's controller, gitbroker and chart need their own reviewers, CI and release cadence. Separation rules S1–S4 (`01-…` §1) say the development system must not blur with production Mercury.
3. **Self-reference.** devplat's restricted paths for Mercury include `platform/**`, so a Mercury task can never change the platform; that is easier to guarantee when the platform is not in the same repository at all.

Acceptance test AT-01 (`29-…`) requires that the platform builds, tests and deploys with no Mercury or Jupiter checkout.

## Decision

1. **Recommend a dedicated repository** owned by the operator (name proposed: `devplat`; final name is the operator's choice), containing `platform/` and the development-orchestration package (`docs/mercury/development-orchestration/` moved to `docs/`, keeping history with `git filter-repo` or a subtree split performed by the operator). The project registry (`platform/projects/`) moves with it.
2. **Creation is an operator action.** Agents cannot create repositories (settings deny; CLAUDE.md: no agent changes repository settings, rulesets, Apps or credentials). The operator creates it, applies the same ruleset as DOD-02 (PR, owner approval of the most recent push, CODEOWNERS = owner, no bypass actors, no force-push or deletion), and installs no App with merge or admin rights.
3. **Independence rules** (enforced by review and AT-01):
   - devplat images are built only from the platform repository;
   - no Mercury or Jupiter code, schema (`mercury.*`) or identity is imported (S1); project facts come only from the registry (ADR-029);
   - Mercury and Jupiter repositories contain **no** devplat code; at most a pointer in their docs;
   - a project's failure never stops the platform or another project (`15-…` §8);
   - Mercury self-hosting never makes devplat depend on Mercury.
4. **Until the repository exists**, devplat stays on `claude/devplatform-k8s` (not merged into Mercury's `main`), and Mercury's project configuration marks `platform/**` restricted for every Mercury role.
5. **Mercury's design documents** keep only the cross-reference W-1 (`27-…` §5) once the move happens; the ADR-021…030 proposals move with the package, and Mercury's ADR index lists them as "development platform, external" if the operator accepts them.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep devplat in Project-Mercury on `main` under `platform/` | Couples platform releases and governance to a tenant; Jupiter config would live in Mercury's repository; violates the independence acceptance criterion |
| Keep it on a long-lived unmerged branch indefinitely | No review or CI on `main`; history stacked on unmerged design branches; fragile |
| One monorepo for platform + all projects | Every tenant's governance and access applies to every other tenant |
| Put devplat in Jupiter's repository | Jupiter does not exist; same coupling problem |

## Consequences

- **Positive:** clean ownership, independent CI and releases, simpler proof of AT-01, Mercury's repository stays a pure target.
- **Negative:** one more repository to govern; cross-repository links in documentation; the move must preserve history and review records (`reviews/`).
- **Migration:** (1) operator creates the repository and ruleset; (2) operator performs the history-preserving split of `platform/` and `docs/mercury/development-orchestration/`; (3) a reviewed PR in the new repository fixes paths (e.g. `.claude/agents/mdev-*.md` role definitions are copied as the platform's role catalogue, byte-identical, and Mercury's copies stay for local mode); (4) a reviewed PR in Project-Mercury removes the moved files or leaves a pointer; (5) the dev bot App (DOD-13) is installed on the platform repository too, with the same restrictions.
- **Status today:** **Awaiting operator approval**; nothing has been created or moved.

## Related documents

`15-platform-architecture.md` §8, `26-project-configuration.md` §1.1, `27-tdd-amendment-proposal.md` I-30 and W-1, `28-roadmap-k8s.md` DP0, `29-acceptance-test-plan.md` AT-01, `12-amendments.md` DOD-12.
