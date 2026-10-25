# Project Mercury — Architecture Amendment 001 (version b, as received 2026-10-17)

Kubernetes-Native, Multi-Project AI Development Platform

> Reference copy of the operator's instruction (verbatim content). See `README.md` in this folder.

> **Instructions:** Give this document to Claude Code in the same Project Mercury session as the original multi-agent master prompt. This amendment supersedes conflicting development-platform instructions while preserving completed work and human approval requirements.

## 1. Continuation of previous instructions

This prompt amends the previously supplied Project Mercury Multi-Agent Development Orchestration Master Prompt.

- Do not restart the project, discard completed work, or duplicate agent definitions, documentation, issues, configurations, or tasks.
- Preserve valid work completed under the earlier prompt.
- Change the development system's target architecture from macOS-centric to Kubernetes-native and platform-independent.
- The development system itself must run in Kubernetes and must build and test Project Mercury and Project Jupiter using isolated Kubernetes-managed environments.
- Keep this development platform independent of both Mercury and Jupiter, so either project can be repaired even when its own application is unavailable.
- Retain exclusive human GitHub approval and protected-branch merge authority.

## 2. Target architecture

Create a shared, project-agnostic AI development control plane containing:

- Principal Development Orchestrator
- Twelve specialist agent definitions and on-demand execution workers
- Dependency-aware task scheduler and execution controller
- GitHub and Linear adapters
- Durable PostgreSQL task state and audit records
- Artifact storage, structured logs, and execution evidence
- Testing, review, security, and integration gates
- Monitoring dashboard and resource/cost tracking

Agent runs should generally use short-lived Kubernetes Jobs; persistent control-plane services may use Deployments or other appropriate workload types. Distinguish Claude Code subagents (roles/configuration) from Kubernetes Jobs (execution units).

Use standard OCI images and support AMD64 and ARM64 where verified compatible. Target local Kubernetes on macOS, Windows, and Linux; multi-node clusters; and managed cloud Kubernetes. Do not depend on macOS launchd or any other host-specific mechanism in the core orchestration layer.

## 3. Three logical environments

**A. AI development platform.** Runs the shared orchestrator, specialist agent execution, integrations, task-state services, and dashboard.

**B. Project Mercury.** An isolated Kubernetes development and testing environment supporting source checkout, dependencies, compilation, unit and integration tests, security and end-to-end tests, image builds, deployment validation, and pull-request preparation.

**C. Project Jupiter.** A separately isolated Kubernetes development and testing environment with its own repository, specifications, languages, dependencies, resource limits, credentials, tests, and release process. Discover Jupiter's actual repository and design before writing project-specific requirements. Where unknown, produce a project onboarding specification and list unresolved information rather than inventing details.

Begin by evaluating one cluster with separate namespaces, but document when dedicated nodes or independent clusters are required. Namespaces are not security boundaries sufficient for hostile or untrusted code execution.

## 4. Keep and adapt the 12 specialist roles

Maintain the existing roles and configurations wherever possible:

1. Lead Software Architect
2. Technical Program Manager
3. Backend Engineer
4. Database Engineer
5. AI Integration Engineer
6. Platform Integration Engineer
7. Security Engineer
8. DevOps Engineer
9. Test Automation Engineer
10. Reliability Engineer
11. Independent Code Reviewer
12. Integration and Release Engineer

Each specialist needs versioned inputs/outputs, limited tools, resource requirements, acceptance criteria, review expectations, and escalation rules. Only launch workers when eligible work and cluster capacity justify them. One role may execute many separate Jobs; do not keep one Pod permanently running per role without justification.

## 5. Project-agnostic configuration

Define a validated, versioned configuration schema for onboarding projects without modifying the control plane. Include:

- Project ID; repository URL, branch, and issue tracker mapping
- Requirements/TDD/ADR locations and architecture constraints
- Coding standards, supported languages, toolchains and container images
- Build, lint, test, scan, and deployment-validation commands
- Required resources, network access, identities, secrets boundaries, and policies
- Agent permissions, review gates, GitHub pull-request policies, and human approvals
- Artifact destinations, retention, and execution budgets

Produce verified Mercury configuration and a Jupiter configuration or onboarding template clearly marking unknowns.

## 6. Kubernetes execution lifecycle

For every ready task:

1. Verify prerequisites, approved design, authorization, and project policy.
2. Select the specialist role, resource budget, and project environment.
3. Allocate an isolated checkout/worktree and immutable base commit.
4. Create an appropriately restricted Kubernetes Job with a versioned task contract.
5. Observe its lifecycle and collect structured output, logs, modified-file evidence, and artifacts.
6. Persist state transitions and reconcile actual cluster state after interruptions.
7. Run automated tests, independent review, security review when applicable, and integration validation.
8. Prepare a pull request where permitted, then stop at human approval/merge.
9. After confirming the human merge, reevaluate dependent tasks.

Avoid overlapping file ownership or concurrent edits to common interfaces without explicit coordination. Agents must not be able to self-approve their gates.

## 7. Persistence and failure recovery

Evaluate PostgreSQL as the distributed state store. Define transactional transitions, idempotency keys, leases, retry budgets, audit logs, durable handoffs, and reconciliation between PostgreSQL, Kubernetes, GitHub, and Linear.

Handle container failure, controller restart, Kubernetes node loss, interrupted sessions, exhausted agent budget, API rate limits, and orphaned Jobs. Do not assume exactly-once execution: prevent duplicate external side effects through idempotency and reconciliation. Report tested recovery separately from proposed recovery.

## 8. Security and authorization

Provide a threat model and enforce least privilege through:

- Kubernetes RBAC and restricted service accounts
- Namespace/network policies and resource quotas
- Credential isolation and workload identity where possible
- Read-only filesystems, privilege restrictions, and appropriate security contexts
- Sandboxed runtimes, dedicated nodes, or separate clusters for higher-risk untrusted builds
- Carefully scoped control-plane API permissions; no broad Kubernetes admin credentials in agent Jobs
- No host Docker socket mounting into untrusted build containers
- Protected branch rules and independent, enforceable human merge authority
- Defenses against prompt injection in issues, repositories, tool output, and documents

Do not change GitHub permissions, branch protection, cluster-wide privileges, production secrets, or production deployments without explicit authorization. A prompt instruction is not a substitute for technical enforcement.

## 9. Build, test, and release

Design Kubernetes-based pipelines for both projects including unit, integration, API-contract, end-to-end, negative-path, concurrency, recovery, security, dependency, and image scans. Use disposable environments where appropriate, with separate CI evidence for each repository. Choose an image-build approach that does not require a privileged host Docker socket. Verify multi-architecture image compatibility before claiming it.

Plan Helm-based or similarly declarative deployment, repeatable bootstrap and teardown, observability, rollback, and disaster recovery. The control plane must remain functional when Mercury or Jupiter is down.

## 10. Scheduling and capacity

Support concurrent Mercury and Jupiter engineering tasks subject to:

- Global and per-project concurrency limits
- Task dependencies and critical-path priority
- CPU, memory, storage, network, and API budgets
- Fairness across projects and admission controls
- Git file conflicts, interface contracts, and security reviews

Compare workstation, dedicated server, multi-node cluster, and managed-cloud configurations. The previously discussed M2 Air with 16 GB is a resource planning example, not a platform requirement. Do not assume Kubernetes itself provides Mercury's application-level task scheduling.

## 11. Preserve the difference between development and production architecture

The development platform must be Kubernetes-native. Mercury and Jupiter must be buildable and testable in Kubernetes. Whether either application's production runtime must require Kubernetes is a separate architectural decision unless explicitly approved.

Review existing Mercury TDD/ADRs for macOS/launchd, local supervision, SQLite, sandboxes, Claude/Codex integration, recovery, credentials, and deployment assumptions. For each affected design choice document the existing decision, proposed amendment, rationale, migration impact, compatibility, security tradeoffs, and approval needed. Never silently replace an approved production design.

## 12. Deliverables

Create or update the existing development-orchestration package with:

1. Updated multi-agent architecture and three-environment Kubernetes topology
2. Principal orchestration and Kubernetes Job-controller specifications
3. Twelve adjusted specialist configurations and task/handoff schemas
4. Project registration schema, Mercury config, and Jupiter onboarding config
5. Security model, authorization matrix, and threat assessment
6. PostgreSQL state model, artifact store, failure recovery, and reconciliation design
7. Dependency-aware multi-project scheduler and resource budgets
8. Build/test/CI architecture and independent quality-gate matrix
9. Helm/declarative deployment, bootstrap, operations, rollback, and portability plan
10. Gap analysis, revised roadmap, TDD/ADR amendments, and acceptance tests

Reuse existing documentation paths and configuration files rather than creating duplicates. Place proposed changes on an isolated branch if authorized. Keep reports explicit about implemented, configured, documented only, unverified, blocked, and awaiting human approval.

## 13. Required workflow and authorization

First: Inspect all results of the original master prompt and the current GitHub/Linear/TDD state. Identify reusable work, files needing change, existing design decisions, and unresolved blockers.

Second: Produce the Kubernetes gap analysis and recommend one-cluster namespaces vs dedicated nodes vs separate clusters with security and cost tradeoffs.

Third: Draft the updated architecture, contracts, security model, deployment design, and issue dependency/critical-path changes.

Fourth: Create or revise proposed documentation and project-scoped configurations only where existing permissions allow. Validate actual files/configurations and report commands/results.

Fifth: Present the operator with a concise set of architectural decisions and actions requiring approval. Do not deploy infrastructure, change privileged settings, merge branches, or start Mercury/Jupiter application implementation without appropriate approval.

## 14. Acceptance criteria

The architecture must demonstrate that:

- The AI development platform operates independently of Mercury and Jupiter.
- The control plane and specialist workers run in Kubernetes.
- Mercury and Jupiter each have isolated Kubernetes-managed build and test environments.
- Both projects share reusable agent roles but have separate project policies and evidence.
- Workers execute only eligible, authorized tasks and support safe concurrency.
- Durable task state and recovery survive process/Pod restarts.
- No agent has protected-branch merge authority.
- Local, multi-node, and cloud deployment models are supported in the design, with implementation status disclosed.
- New projects can be onboarded via validated configuration.
- Proposed production changes are distinguished from development-platform changes.

Proceed with repository discovery and architectural amendment preparation now. Preserve all valid work from the previous prompt. Report facts separately from assumptions, and request authorization before crossing any approval boundary.
