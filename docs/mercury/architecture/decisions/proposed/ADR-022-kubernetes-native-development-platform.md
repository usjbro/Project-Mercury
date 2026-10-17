# ADR-022 — Kubernetes-native, multi-project AI development platform (devplat)

| | |
|---|---|
| Status | **Proposed** (Architecture Amendment 001; requires operator approval) |
| Date | 2026-10-17 |
| Owner | Lead Architect (development platform) |
| Related ADRs | ADR-021 (extended, not superseded); ADR-023, ADR-024 (this amendment); ADR-025…030 (security, persistence, builds — proposed separately). Mercury ADR-001…020: **none affected** |

## Context

ADR-021 builds MERCURY with one Claude Code main session as Principal Orchestrator, 12 project subagents and a hash-chained git ledger. Reviews R1–R5 left residual risks that cannot be closed on one host under one uid:

- the specialist guard hook did not fire in live dispatch (R5 N-01) and tool denies match command text only;
- any process running as the agent's uid can forge a consistent ledger (R5 residual 3);
- operator facts are self-asserted (`--actor operator`, R5 N-06);
- agents run with the operator's credentials reachable (S-02, S-10).

Amendment 001 also asks for one platform that builds several projects (Mercury now, Jupiter later — Jupiter is not yet specified), runs in Kubernetes, and keeps working when any project is broken.

## Decision

1. **devplat is a separate, project-agnostic platform.** It is not Mercury and holds no Mercury production authority, schema or identity (ADR-021 separation rules S1–S4 kept). Mercury's production design is unchanged unless a separate ADR says otherwise.
2. **Control plane in Kubernetes** (`devplat-system`): `devplat-controller` (Deployment, 2 replicas, Lease leader election) is the deterministic task state machine — a port of devorch `check_transition` / `replay`, gates G1–G7, budgets and bound reviews — plus the multi-project scheduler and Job reconciliation. It is the **only writer** of task state. `devplat-api` (OIDC) records operator facts and approvals with an authenticated identity. `devplat-gitbroker` alone holds the dev-bot GitHub App key, validates result bundles (port of devorch `result_errors`), pushes `dev/*` and opens **draft** PRs. `devplat-model-gateway` alone holds the LLM API key and enforces per-project budgets.
3. **Durable state in PostgreSQL** (operator-managed in cluster, or managed): `tasks`, append-only hash-chained `task_events`, `evidence`; artifacts in an S3-compatible, content-addressed store. Details: ADR-026 (proposed).
4. **Agents are untrusted workloads**: each attempt runs as a Kubernetes Job with no credentials, no Kubernetes token, no DB route and default-deny egress (ADR-024).
5. **The Principal Orchestrator role is split**: the mechanical loop becomes the controller; LLM reasoning runs as short-lived `planner` Jobs whose outputs are proposals that the controller validates.
6. **Projects are configuration**: a versioned project config and an execution target `{cluster_ref, namespace_prefix}` per project (topology: ADR-023).
7. **Human authority unchanged**: draft PRs only; G7 is an observed human merge; DOD-02 (ruleset on `main`) and DOD-03 (dev-bot identity without merge/approve) remain hard preconditions for code work.
8. **v1 stays as local mode** for use before a cluster exists.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep v1 (one session, git ledger) and add parallel cloud sessions | Every session holds the operator's GitHub authorization; ledger forgery and hook failure remain; no multi-project isolation |
| Task CRDs + operator, state in etcd | etcd is not an append-only audit store; relational queries (READY, budgets, fair share) are awkward; two sources of truth |
| Let an LLM orchestrator decide transitions inside the cluster | Authority must be code; LLM output is untrusted (rule U) |
| Use Mercury itself to orchestrate its own development | Mercury does not exist; circular; violates S1–S4 |
| A generic CI system (e.g. GitHub Actions) as the platform | No dependency-aware admission, gates or bound reviews; runners would hold repository credentials |

## Consequences

- **Positive:** credentials leave the agent's reach; the single-writer rule becomes enforceable (separate pod, DB role, NetworkPolicy); operator facts become authenticated; several projects share one platform with isolation; the platform survives a broken project.
- **Negative:** much more infrastructure to build and operate (controller, brokers, PostgreSQL, artifact store, chart); nothing of it exists yet; a workstation install only reaches reduced assurance (ADR-023).
- **New critical assets:** gitbroker (GitHub App key) and model-gateway (API key) become the highest-value targets (threat analysis in `18-…`).
- **Unchanged limits:** Kubernetes does not change GitHub governance — merge authority still depends on DOD-02/03. Mercury T4 (launchd, Keychain, Seatbelt, `_mercuryagent`) cannot run in Kubernetes and stays an external macOS lane.

## Status of the decision's elements

All elements are **Documented only**. The devorch rules being ported are Implemented+tested in v1 (30 tests). Nothing is deployed or tested on Kubernetes.

## Related requirements

CON-003, CON-007 and CON-008 and TDD §32 conditions C1–C7 continue to bind production MERCURY and are not changed. Specification: `development-orchestration/15-platform-architecture.md`, `16-…`, `17-…`.
