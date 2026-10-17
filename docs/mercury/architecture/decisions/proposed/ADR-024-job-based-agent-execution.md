# ADR-024 — Job-based agent execution

| | |
|---|---|
| Status | **Proposed** (Architecture Amendment 001; requires operator approval) |
| Date | 2026-10-17 |
| Owner | Lead Architect (development platform) |
| Related ADRs | ADR-021 (roles and gates kept), ADR-022 (platform), ADR-023 (topology), ADR-025 (security, proposed separately). Mercury ADR-020 (detached runs and adoption) is a production decision and is **not** changed; the adoption pattern here is independent |

## Context

In v1 the 12 specialists run as Claude Code subagents inside the operator's session: same host, same uid, the operator's credentials in reach, and a guard hook that did not fire in live dispatch (R5). devplat needs an execution unit that is isolated, bounded in time and resources, observable, and safe to retry after a controller crash.

## Decision

1. **One attempt = one Kubernetes Job** named `dp-<project>-<task>-a<attempt>` (DNS-1123, ≤ 63 characters, hash fallback), labelled `devplat.io/{project,task,attempt,role,idempotency-key}`. Create is idempotent: `AlreadyExists` with the same idempotency key → adopt; different key → escalate, never delete.
2. **Kubernetes never retries.** `backoffLimit: 0`, `podReplacementPolicy: Failed`; retries are new attempts decided by the controller under the devorch budgets. `activeDeadlineSeconds` = wall budget + setup grace; `podFailurePolicy` (`FailJob` on disruption and on runner exit codes) as a classification hint; `ttlSecondsAfterFinished` as a backstop after the controller has collected the results.
3. **Suspended setup.** The Job is created `suspend: true`; the controller then creates the contract ConfigMap and the io Secret (one-time bundle URL, presigned upload targets under `runs/<job-uid>/`, per-Job gateway token) owned by the Job, and unsuspends it.
4. **Pod shape.** No ServiceAccount token, a per-project ServiceAccount with zero RBAC, non-root, read-only root filesystem, all capabilities dropped, seccomp `RuntimeDefault`, no privilege escalation, gVisor RuntimeClass, exec-pool toleration; `emptyDir` workspace. Init container `fetch` (bundle from gitbroker, verified); main container `agent` (devplat-runner → `claude -p --agent <role>`), sidecar-less; the runner always uploads `result.json`, a git bundle and logs.
5. **Role definitions reused.** `.claude/agents/mdev-*.md` stay byte-identical in the repository; an immutable per-project ConfigMap is generated from them (one recorded transform: the guard-hook path points into the read-only image). Each Job mounts only its own role. Kubernetes-specific data lives in `platform/agents/execution-profiles.yaml` (resources, wall time, network class, runtime class, workspace size, writes allowed, per-project concurrency).
6. **Results are claims.** Gitbroker validates the bundle (port of devorch `result_errors`); a verifier Job re-runs the required tests (G2); review subtasks run as fresh Jobs bound to the tested head (G3/G4). Usage authority is model-gateway metering.
7. **Planner Jobs** run the Principal Orchestrator's reasoning with the same contract/result schemas (new kind `plan_proposal`); they cannot dispatch, record, push or reach GitHub.
8. **The guard hook and tool denies remain tripwires.** The controls are NetworkPolicy, absence of credentials, admission policy, gitbroker validation and the GitHub ruleset.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Long-running agent Deployments pulling work | Shared state between tasks, harder isolation and accounting; v1 rule "one task per agent instance" |
| Bare Pods | No deadline/TTL/failure-policy semantics; manual garbage collection |
| Kubernetes-level retries (`backoffLimit > 0`) | Hides retries from the budgets and the audit trail; re-uses one-time URLs |
| Agent pushes directly with a scoped token | Any token in the pod is exfiltratable; validation would happen after the fact |
| Kueue-managed Jobs from the start | Kueue owns `spec.suspend` and knows nothing of dependencies, gates or token budgets; optional later (`17-…` §13) |

## Consequences

- **Positive:** credentials and the DB are out of the agent's reach; every attempt is bounded and individually auditable; controller crashes are recoverable by label-selector adoption.
- **Negative:** per-attempt start-up cost (image pull, fetch, dependency install); headless Claude Code behaviour under the pinned CLI version (flags, managed settings, read-only root filesystem, gVisor) must be verified before first use (`16-…` §11, V-16-1…8); the contract schema needs a v2 for the controller as creator, the planner role and non-Mercury projects.

## Status of the decision's elements

All elements are **Documented only**. The example Job manifest is validated against the strict Kubernetes v1.33 JSON schema only; the execution profiles are schema-validated. No Job has run.

## Related requirements

ADR-021 gates G1–G7 and budgets (unchanged). Specification: `development-orchestration/16-agent-execution-and-job-lifecycle.md`.
