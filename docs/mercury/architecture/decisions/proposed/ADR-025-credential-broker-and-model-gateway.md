# ADR-025 — Credential broker (gitbroker) and model gateway: no credentials in agent pods

| | |
|---|---|
| Status | **Proposed** (requires operator approval: Architecture Amendment 001, DOD-11…DOD-16; dev-bot App DOD-13) |
| Date | 2026-10-17 |
| Owner | Security Engineer (devplat security model, `development-orchestration/18-kubernetes-security-model.md`) |
| Related ADRs | ADR-021 (development orchestration), ADR-022…024, ADR-026…030 (Amendment 001, proposed); production ADR-006, ADR-008, ADR-013, ADR-014 (not superseded) |

## Context

In v1 local mode, every agent process runs as the operator's OS user. It can reach the operator's GitHub authorization, Claude credentials and files. The only boundary is the `main` ruleset plus a separate development identity (DOD-02/03). Claude Code deny rules and the guard hook are tripwires, and R5 showed that the hook did not fire in live dispatch. R2 rated S-01 (shared GitHub authorization), S-02 (credential reads only blocked by policy) and S-03 (MCP write tools reachable) as Critical.

devplat runs specialists as Kubernetes Jobs whose code must be treated as attacker-controlled (prompt injection, malicious repository content, compromised dependencies). It still needs to:

- read and push source;
- open draft PRs;
- call LLM APIs under budgets;
- store evidence.

## Decision

1. **No long-lived credential in any agent, planner, verifier, build or test pod.** No GitHub token, LLM API key, DB credential or Kubernetes ServiceAccount token. Pods get only per-Job capabilities that expire: a one-time bundle URL, presigned upload targets scoped to `runs/<job-uid>/`, and a gateway token bound to `(project, job uid)` with a budget.
2. **`devplat-gitbroker` is the sole holder of the dev-bot GitHub App key** (DOD-03 (a) / DOD-13; separate from `mercury-bot`). It mints scoped installation tokens, prepares source bundles, validates agent output bundles (port of devorch `result_errors`, in a quarantine repository with its own git config), pushes `dev/*` only after G1–G5, and opens **draft** PRs. It has no code path to merge, approve, enable auto-merge, mark ready or change rulesets. The App has no `administration` or `workflows` permission and is not a CODEOWNER. Only the controller can reach gitbroker.
3. **`devplat-gitbroker-fetch` serves bundles to pods and holds no GitHub credential**, so untrusted pods never reach the key holder.
4. **`devplat-model-gateway` is the sole holder of LLM provider keys.** It injects the key upstream, allows only provider hosts, meters per Job and per project, and enforces budgets (DOD-08). Pods authenticate with the per-Job token. The gateway is unreachable from build and test namespaces and from Jobs of network class `none`.
5. **Each platform credential is pinned to one ServiceAccount** by ValidatingAdmissionPolicy `devplat-secret-pinning`. Project pods may reference only per-run `dp-*` Secrets (`devplat-proj-pod-identity`). Secrets are encrypted at rest; cloud profiles use External Secrets or workload identity.
6. **Network enforces the broker pattern:** default-deny in every namespace. Agent pods reach only devplat-dns (no forwarder), gitbroker-fetch, the artifact store, and, by network class, the model gateway and registry proxy. They never reach GitHub, Linear, the DB, the kube-apiserver or the internet.
7. **Human authority is unchanged:** DOD-02 ruleset with no bypass actors, draft PRs only, G7 observed from GitHub.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Short-lived GitHub installation token in the agent pod, scoped to one repo | A token with `contents:write` lets an injected agent push arbitrary content to `dev/*`, delete branches, comment, and (without a ruleset) touch `main`. Validation would happen after the push, not before |
| LLM API key as a Secret in the agent pod | Key exfiltration by any injected agent; no enforced per-project budget |
| One "platform broker" holding both GitHub and LLM credentials | One compromise exposes both. GitHub and LLM traffic have different validation needs |
| Rely on Claude Code permission rules or hooks inside the pod | Tripwires, not a boundary (R2 S-02/S-04, R5 N-01) |
| Agents push through a git proxy that checks refs | Ref checks cannot validate content (restricted paths, renames, hidden index) before it reaches GitHub. Bundle validation can |
| Service mesh with an egress gateway instead of in-app allowlists | Possible later as defence in depth. It adds a dependency and does not remove the need for application-level validation |

## Consequences

- **Positive:**
  - R2 S-01, S-02 and S-03 are resolved structurally for agents: no credential is present to read or misuse.
  - R5's hook failure no longer lowers assurance.
  - Spend is enforced centrally.
  - Every push is preceded by a code-level validation.
- **Negative:**
  - Two more platform services (gitbroker, gitbroker-fetch) plus the gateway are on the critical path, and are high-value targets (doc 18 K-12, K-13).
  - Every new egress need goes through the gateway or the registry proxy.
  - Workflows that require `workflows` permission cannot be pushed by the bot (operator push or a scoped exception).
- **Limits:**
  - A compromised controller can still forge gate records (doc 18 K-10). The ruleset and operator review (G7) are the backstop.
  - On a personal repository the merge actor is detected after the fact (G-DETECT).
  - On a single-node workstation a container escape reaches the brokers' keys (reduced assurance).
- **Status:** Documented only. Base manifests are Implemented (untested on a cluster). gitbroker, gitbroker-fetch and model-gateway code does not exist. The App is awaiting operator approval (DOD-13).

## Related requirements

CON-003 (role boundary, operator merge authority), CON-007 (human approval enforced by GitHub) and the intent of CON-008 (no automation under the operator's identity) are applied to the development platform. Production MERCURY's identities (`mercury-bot`, `mercury-ops`) and ADR-006 / ADR-008 / ADR-014 are unchanged. Development and production credentials stay separate (separation rules S1–S2).
