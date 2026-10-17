# 14 — Amendment 001: inspection of existing work and Kubernetes gap analysis

Status: **Proposed** (Architecture Amendment 001, 2026-10-17; awaits operator approval, see `12-amendments.md` DOD-11…DOD-16). Branch `claude/devplatform-k8s`, stacked on `claude/dev-orchestration` (nothing merged).
Reuses / supersedes: keeps docs 00–13 as **v1 "local mode"** (one Claude Code session, git ledger). Docs 15–29 define **v2 "devplat"**, the Kubernetes-native, multi-project platform. Where they conflict, v2 governs the development platform (amendment §Final instruction). Mercury's production design (TDD) is unchanged unless an ADR approved separately says otherwise (`27-…`).

## 1. Inspection: what already exists (facts, checked on 2026-10-17)

| Item | Where | Status | Reuse in v2 |
|---|---|---|---|
| Mercury TDD v1.0-rc1 with 32 sections, ADR-001…020, owner documents | `docs/mercury/**` on `claude/mercury-tdd` | Design only. **Not approved** (DOD-01 open). No Mercury application code | Unchanged. Impact analysis in `27-…` |
| Development orchestration package v1 (docs 00–13) | `docs/mercury/development-orchestration/` | Documented. Reviewed R1–R5 | Concepts kept: authority split, gates G1–G7, contracts, subtasks, budgets, evidence over claims, human merge. Host-specific parts (git ledger worktree, `../mercury-wt`, macOS paths, a single session) become the "local mode" |
| Contract / result / handoff schemas v1 | `schemas/*.json` | Implemented and validated | Kept as the wire format between the controller and Jobs; `task_events` mirrors the handoff record (`19-…`) |
| `devorch.py` v2 (state machine, gates, bound reviews, evidence hashing, worktree checks, push rules) | `tools/devorch/` | **Implemented and tested** in scratch git repositories: 30 regression tests passing | Its rules are the specification for the controller and gitbroker. Two parts are ported: `check_transition`/`replay` into PostgreSQL (`platform/db`), and `result_errors` into gitbroker validation. The CLI stays usable as local mode |
| 12 specialist definitions plus the orchestrator | `.claude/agents/mdev-*.md` (from `gen_agents.py`) | Configured. Loaded as agent types after a restart (verified). Hook firing **failed** in live dispatch (R5) | Kept unchanged as role definitions. Mounted into Jobs via a ConfigMap. Execution profiles added (`platform/agents/`) |
| Project settings with 119 denies, guard hook | `.claude/settings.json`, `tools/devorch/hooks/` | Configured. Tripwires | Kept for local and interactive sessions. In Kubernetes they are defence in depth only; the controls become infrastructure (`18-…`) |
| Schedule model v2 | `tools/devorch/schedule_model.py`, `05-…` | Implemented (estimate model) | Kept. Multi-project capacity reasoning in `17-…` |
| DAG (82 issues, 0 cycles) | `data/dag.json` | Generated | Kept as the Mercury backlog input |
| Proposed ADR-021 (development orchestration) | `architecture/decisions/proposed/` | Proposed | Kept; ADR-022…030 extend it |
| Linear | workspace | No Mercury or Jupiter project or issue | — |
| GitHub | `usjbro/Project-Mercury` | `main` has 1 commit. Branches `claude/mercury-tdd` and `claude/dev-orchestration` are unmerged. No PR, no CI, no ruleset (DOD-02 open) | — |
| **Project Jupiter** | GitHub repos visible to this account (8), Linear projects and issues, Notion search, all branches of this repo | **Not found anywhere.** No repository, specification, tracker or document | Onboarding contract only, with every project fact `unresolved` (`26-…` §3). Nothing invented |

## 2. Gap analysis against Amendment 001

Legend: ✅ satisfied by existing work · 🟡 partly · ❌ missing.

| # | Amendment requirement | v1 state | Gap | Closed by |
|---|---|---|---|---|
| 1 | Control plane runs in Kubernetes; containerized; OCI; amd64/arm64 | ❌ Claude Code main session on a host; git ledger in a worktree | Everything | `15-…`, `16-…`, `24-…`, chart |
| 2 | Three logical environments (platform, Mercury, Jupiter) isolated | ❌ one repository, one session | Namespaces, node pools, execution targets | `15-…`, `18-…`, `platform/deploy/base` |
| 3 | Topology A/B/C evaluated; migration to separate clusters without redesign | ❌ | Evaluation and the execution-target abstraction | `15-…` §topology, ADR-023 |
| 4 | Keep 12 roles; distinguish definition / container / Job / task record / project config | 🟡 roles exist; execution is in-process subagents | Execution model, profiles | `16-…`, `platform/agents/execution-profiles.yaml`, ADR-024 |
| 5 | Project-agnostic; versioned project configuration contract | ❌ Mercury hard-wired (assignments, paths, DAG) | Schema, Mercury configuration, Jupiter onboarding | `26-…`, `platform/schemas/project-config.schema.json`, `platform/projects/` |
| 6 | Execution controller creating and supervising Jobs; narrow RBAC; no Docker socket | ❌ | Controller design, RBAC, admission policy | `16-…`, `18-…`, `platform/controller/jobspec.py` |
| 7 | Durable external persistence (PostgreSQL); leases, idempotency, reconciliation | 🟡 rules exist (devorch); storage is a git ledger with a single writer that can't be enforced (R5 residual 3) | PostgreSQL schema; the controller as sole writer; agents without DB access | `19-…`, `platform/db/` (tested on PostgreSQL 16), ADR-026 |
| 8 | Kubernetes-based build and test for both projects; disposable namespaces; independent CI | ❌ | Build/test architecture, image builds without a socket, CI correlation | `22-…`, `23-…`, ADR-027 |
| 9 | Bootstrap without Mercury or Jupiter; Helm / GitOps; declarative | ❌ (v1 bootstrap = RB-D1 on a host) | Bootstrap steps 1–10, charts | `24-…`, `platform/deploy/charts/` |
| 10 | Multi-project scheduling: quotas, fairness, budgets, admission; profiles A–D | 🟡 single-project schedule model, WIP limits | Multi-project admission, fair share, per-project budgets | `17-…`, `25-…` |
| 11 | Security: no autonomous merge, no exposed credentials, enforced at infrastructure / API level | 🟡 human merge is preserved by design but depends on DOD-02/03; enforcement was tripwires (R5) | Credential broker, model gateway, NetworkPolicy, no agent tokens, OIDC-authenticated operator facts | `18-…`, ADR-025 |
| 12 | TDD compatibility review; distinguish platform vs Mercury production changes | ❌ | Impact table per requirement and ADR | `27-…` |
| 13 | 23 deliverables | 🟡 | See README index | docs 14–29, ADR-022…030, `platform/` |
| 14 | Validation against installed tooling and Kubernetes APIs | — | No kubectl, helm or cluster here | Strict v1.33 JSON-schema validation, a real PostgreSQL 16, unit tests (`29-…` §2) |

### 2.1 What v1 risks the Kubernetes design closes, and what it does not

| v1 residual (R5) | Why it stays open in v1 | v2 mechanism | Still open |
|---|---|---|---|
| Guard hook not firing (N-01) | Hooks are a Claude Code feature | Agents run in pods with no credentials, default-deny egress, no Kubernetes API token and no DB access. The hook becomes irrelevant to safety | Correct NetworkPolicy and admission configuration has to be verified on a real cluster |
| Ledger writable by the agent uid (residual 3) | Same host and same uid | Agents and the controller run in different pods. Only the controller's DB role can call `record_event`; the DB is unreachable from agent pods | A DB superuser or cluster admin can still rewrite. Mitigated by signed checkpoints (`19-…`) |
| Self-asserted operator facts (N-06) | `--actor` is a CLI flag | Facts are written only by `devplat-api` with an OIDC-authenticated human subject | The OIDC provider has to be chosen and configured (DOD-14) |
| Credential reads by agents (S-02) | Same uid as the operator | GitHub key only in gitbroker; LLM key only in model-gateway; agent pods hold none | Gateway and broker compromise become the critical risks (`18-…`) |
| Merge authority (S-01) | Operator credentials are shared | Dev bot GitHub App (DOD-03 a) used only by gitbroker; draft PRs only | **Still requires DOD-02 and DOD-03.** Kubernetes does not change GitHub governance |
| macOS-only validation (Mercury T4) | — | — | **Cannot run in Kubernetes.** It remains an external macOS lane (`22-…`) |

## 3. Reuse rules

1. **v1 docs are amended, not duplicated.** Doc 07 is superseded for Kubernetes by doc 21, which keeps 07's failure taxonomy. Doc 08's gates are kept; the security matrix is extended by doc 18. Doc 09 is extended by doc 17 and doc 25. Doc 13 keeps the local-mode runbooks; doc 24 adds the cluster bootstrap.
2. **The 12 agent files stay byte-identical.** Kubernetes-specific data lives in `platform/agents/execution-profiles.yaml`, not in the frontmatter (unknown frontmatter fields are ignored by Claude Code).
3. **devorch rules are the specification.** The controller's tests must include ports of the 30 devorch regression cases (`29-…` §3).
4. **Local mode remains** for single-workstation use before a cluster exists. It does not become the production of the platform.
