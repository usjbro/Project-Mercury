# ADR-029 — Versioned project configuration contract (`devplat.project.v1`)

| | |
|---|---|
| Status | **Proposed** (requires operator approval: DOD-11; Architecture Amendment 001) |
| Date | 2026-10-17 |
| Owner | Lead Architect (development platform) |
| Related ADRs | ADR-021 (development orchestration), ADR-022…028 (devplat), ADR-030 (platform independence); Mercury ADR-001…020 unaffected |

## Context

The v1 development orchestration builds exactly one project. Mercury's facts are wired into the tooling: `tools/devorch/assignments.json` maps MERC issues to agents, each contract repeats hand-written `restricted_paths`, branch rules and WIP limits live in prose (`06-…`, `09-…`). Amendment 001 requires a project-agnostic platform that onboards a second project (Jupiter) **without controller code changes**, keeps Mercury's production design separate, and never weakens the security model. Discovery found no repository, tracker or document for Jupiter, so the contract must be able to say "unknown" without inventing values.

## Decision

1. **One file per project** in a project registry (`platform/projects/<id>.yaml`), validated against `platform/schemas/project-config.schema.json` (JSON Schema Draft 2020-12, `schema: devplat.project.v1`). It is the only source of project facts for the controller, gitbroker, model-gateway and the `devplat-project` chart. Platform code holds no project literal.
2. **Strict schema.** `additionalProperties: false` everywhere. Security-relevant invariants are schema constants that no project file can weaken: draft-only PRs, human merge, approver = repository owner, G7 required, Pod Security `restricted`, no extra egress, a closed list of agent GitHub actions (push to the branch prefix, open draft PR, comment). Secrets appear by **name and holder only**; an agent Job can never be a holder.
3. **Explicit unknowns.** Unknown values are `{unresolved: "<question>"}`; designed-but-absent commands are `{planned, ref}`. A project has a `status`: `draft` (nothing runs), `onboarding` (security core resolved; planning and design only), `active` (nothing unresolved; secrets provisioned; governance applied and verified; design approved; images digest-pinned).
4. **Validation in two places.** `platform/tools/validate_projects.py` (schema, status rules, cross-field rules including "no role scope inside a restricted path", secret-value detection) runs in the registry's CI; the controller re-applies the status rules at every admission.
5. **Versioning.** Major in `schema` (breaking → `v2`; controller accepts N and N-1 during a migration); additive changes bump `schema_minor`; each file has a monotonic `config_version` recorded on every task event; tightening applies at the next admission and at result application, loosening a security-core field needs an operator-approved PR plus a Security review.
6. **Role binding by intersection.** A Job's effective permission = role definition ∩ execution profile ∩ project role entry (`enabled`, `writes`, `path_scopes`) ∩ contract (`allowed_paths` ⊆ path scopes, outside `restricted_paths`).
7. **Kubernetes mapping by rendering.** A config renderer turns a validated file into `devplat-project` chart values (namespaces from `execution_target.namespace_prefix`, quotas, LimitRanges, RuntimeClass requirement, NetworkPolicies, registry allowlist, Secret names per holder, bucket). Moving a project to another cluster changes `execution_target.cluster_ref` only.
8. **Initial registry.** `mercury.yaml` (`onboarding`; every value traced to the TDD or the development package; 22 unresolved) and `jupiter.onboarding.yaml` (`draft`; every project fact unresolved with the operator question; 53 unresolved).

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep project facts in code or `assignments.json` | A second project would need code changes; violates amendment requirement 5 |
| Free-form YAML without a schema | Typos become silent defaults; security fields could be weakened unnoticed |
| Defaults for unknown values (e.g. assume Node or npm for Jupiter) | Invents requirements; the brief forbids it |
| Kubernetes CRD (`DevplatProject`) as the source | Ties the contract to a cluster and to RBAC on CRD writes; a reviewed Git file is auditable and works before any cluster exists. A CRD may later be *rendered* from the file |
| Helm values as the contract | Mixes project facts with deployment mechanics; cannot express unresolved, status or role scopes |

## Consequences

- **Positive:** onboarding is a reviewed PR, not code; the status gate prevents running a half-known project; security invariants are mechanically non-negotiable per project; Mercury's configuration is traceable value by value (`26-…` §2.2).
- **Negative:** one more artefact to keep in sync with role definitions and execution profiles; the renderer and the controller's admission check are not implemented yet (**Documented only**).
- **Open:** Q-M3 (`docs/**` and `.github/**` restricted for all Mercury roles vs. the v1 DevOps and Lead Architect scopes); the `cluster_ref` name (`default` vs. chart example `local`).
- **Mercury production:** unchanged. The configuration describes how devplat builds Mercury; it does not describe or alter `mercuryd` (`27-…`).

## Related documents

`26-project-configuration.md` (contract, Mercury values, Jupiter onboarding), `15-platform-architecture.md` §5–§8, `16-agent-execution-and-job-lifecycle.md`, `27-tdd-amendment-proposal.md`.
