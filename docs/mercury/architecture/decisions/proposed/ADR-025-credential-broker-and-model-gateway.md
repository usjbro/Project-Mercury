# ADR-025 — Credential brokers (gitbroker, artifact-gateway) and model gateway: no credentials in agent pods

| | |
|---|---|
| Status | **Proposed** (requires operator approval: Architecture Amendment 001, DOD-11…DOD-24; dev-bot App DOD-13; R6 fix decisions D10, D12, D13, D14, D26) |
| Date | 2026-10-17; revised 2026-10-22 (R6 fix round) |
| Owner | Security Engineer (devplat security model, `development-orchestration/18-kubernetes-security-model.md`) |
| Related ADRs | ADR-021 (development orchestration), ADR-022…024, ADR-026…030 (Amendment 001, proposed); production ADR-006, ADR-008, ADR-013, ADR-014 (not superseded) |

## Context

In v1 local mode, every agent process runs as the operator's OS user. It can reach the operator's GitHub authorization, Claude credentials and files. The only boundary is the `main` ruleset plus a separate development identity (DOD-02/03). Claude Code deny rules and the guard hook are tripwires, and R5 showed that the hook did not fire in live dispatch. R2 rated S-01 (shared GitHub authorization), S-02 (credential reads only blocked by policy) and S-03 (MCP write tools reachable) as Critical.

devplat runs specialists as Kubernetes Jobs whose code must be treated as attacker-controlled. It still needs to read and push source, open draft PRs, call LLM APIs under budgets, and store evidence.

The R6 security review found four weaknesses in the first version of this ADR:
- the model gateway passed provider-side tools through (S-1);
- agent pods could reach the shared object store, and so could PUT to an attacker's presigned URL (S-2);
- agent-written code runs in GitHub Actions (S-3);
- the claim "the App cannot merge or approve" was false (S-14).

## Decision

1. **No long-lived credential in any agent, planner, verifier, build or test pod.** No GitHub token, LLM key, DB credential, object-store credential or presigned URL, and no Kubernetes ServiceAccount token. Pods get only per-Job capabilities that expire:
   - a one-time bundle URL (gitbroker-fetch);
   - an upload token (artifact-gateway);
   - a model token (model-gateway).
2. **`devplat-gitbroker` is the only holder of the dev-bot GitHub App key** (DOD-13; separate from `mercury-bot`). It:
   - mints repository-scoped installation tokens;
   - prepares source bundles;
   - validates agent output bundles in a quarantine repository (port of devorch `result_errors`);
   - pushes `dev/*` only after G1–G5;
   - opens **draft** PRs.

   It has no code path to approve, merge, enable auto-merge, mark ready or change rulesets. Callers must present the controller's audience-bound projected ServiceAccount token, which gitbroker verifies against the cluster issuer's JWKS (`callerAuth: projected-token`; base binds `system:service-account-issuer-discovery` to gitbroker). mTLS is the documented alternative. Network position alone is not enough (S-23). Only the controller may call it.
3. **The App's permissions do not prevent approval or merge.** With `contents:write` + `pull_requests:write` the App can submit reviews and call the merge API. The preventive control is the per-repository ruleset on `main` (DOD-02): required code-owner review (operator), no bypass actors, and the App cannot update `main`. The App has no `administration` or `workflows` permission and is not a CODEOWNER.
4. **D13 is part of the DOD-02 checklist, per repository:**
   - read-only default workflow token;
   - Actions may not create or approve PRs;
   - `dev/**` workflows run with `contents: read` and no secrets;
   - no `pull_request_target`;
   - tag and release protection.

   Probe N10 **attempts** approve, merge, auto-merge, a push to `main` and a ruleset change in a sandbox repository. It passes only if each attempt is refused or, for the approval, ineffective (doc 18 §13).
5. **`devplat-gitbroker-fetch` serves bundles to pods and holds no GitHub credential.** Untrusted pods never reach the key holder.
6. **`devplat-artifact-gateway` is the only artifact path for pods (D10).** Pods upload `runs/<job-uid>/…` with a per-Job one-time token, within the size caps of D11. The gateway writes with its own S3 credential. Presigned URLs are used only between platform components. Project pods have no route to the object store.
7. **`devplat-model-gateway` is the only holder of LLM provider keys (D12).** It allows only `POST /v1/messages` and `POST /v1/messages/count_tokens`. It rejects:
   - every tool except one without `type` or with `type: custom` (an allowlist: web search, web fetch, code execution, computer use and any server-side type added later are refused);
   - image or document content blocks whose `source.type` is not `base64` or `text` (a `url` source makes the provider fetch an agent-chosen URL; a `file` source refers to the Files API), and any `file_id` (R6 re-check RS-1);
   - any content block type other than `text`, `image`, `document`, `tool_use`, `tool_result`, `thinking`, `redacted_thinking`, and any top-level request field outside an allowlist (`model`, `messages`, `system`, `max_tokens`, `tools`, `tool_choice`, `temperature`, `top_p`, `top_k`, `stop_sequences`, `stream`, `metadata`, `thinking`) — so `mcp_servers`, `container` and future fields are refused without being named (C-1);
   - `mcp_servers` and `container`;
   - Files and Batches APIs;
   - non-allow-listed `anthropic-beta` headers.

   It binds the project to the per-Job token (not the URL), enforces per-token and per-project budgets (DOD-08), and uses a separate spend-limited key for reduced-assurance projects (D16). It is unreachable from build and test namespaces and from Jobs of network class `none`.
8. **Read-only package proxies per project (D14).** `devplat-registry-proxy-<project>` has publish and adduser disabled and allows only the project's upstreams. The OCI mirror is pushed only by platform CI with a separate identity.
9. **Each platform credential is pinned to one ServiceAccount** by ValidatingAdmissionPolicy `devplat-secret-pinning`. Project pods may reference only per-run `dp-*` Secrets of type Opaque. Secrets are encrypted at rest; cloud profiles use External Secrets or workload identity, with one identity per ServiceAccount.
10. **The network enforces the broker pattern:** default-deny in every namespace. Agent pods reach only devplat-dns (no forwarder), gitbroker-fetch, the artifact-gateway and, by network class, the model gateway and their own project's proxy. They never reach GitHub, Linear, the DB, the object store, the kube-apiserver or the internet.
11. **Human authority is unchanged:** draft PRs only; G7 observed from GitHub (`merged_by` = operator, code-owner approval on the G6 head).

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Short-lived GitHub installation token in the agent pod, scoped to one repo | A token with `contents:write` lets an injected agent push arbitrary content to `dev/*`, delete branches and comment. Validation would happen after the push, not before |
| LLM API key as a Secret in the agent pod | Key exfiltration by any injected agent; no enforced per-project budget |
| Presigned S3 URLs handed to pods (first version of this ADR) | A pod that can reach the object store can also PUT to an attacker-supplied presigned URL. Size and prefix checks happen too late (S-2) |
| Transparent model proxy that forwards any Messages API feature | Provider-side tools (web fetch, MCP connector, code execution) become exfiltration and instruction-intake channels (S-1) |
| One "platform broker" holding GitHub, LLM and S3 credentials | One compromise exposes all of them; each path needs different validation |
| Rely on Claude Code permission rules or hooks inside the pod | Tripwires, not a boundary (R2 S-02/S-04, R5 N-01) |
| Rely on App permissions to prevent merge/approve | False: `pull_requests:write` + `contents:write` allow both through the API. Only the ruleset prevents them |
| Service mesh with an egress gateway instead of in-app allowlists | Possible later as defence in depth; it does not replace application-level validation |

## Consequences

- **Positive (by design; Designed, unverified until the services exist):**
  - R2 S-01, S-02 and S-03 are addressed structurally for agents, because no credential is present to read or misuse.
  - R6 S-1 and S-2 are addressed at the gateways.
  - R5's hook failure no longer lowers assurance.
  - Spend is enforced centrally, and every push is preceded by a code-level validation.
- **Negative:**
  - Four platform services (gitbroker, gitbroker-fetch, artifact-gateway, model-gateway) plus a proxy per project are on the critical path and are high-value targets (doc 18 K-12, K-13).
  - Every new egress need goes through a gateway or a proxy. The D12 allowlist must be maintained as the provider API evolves.
  - Workflows that need the `workflows` permission cannot be pushed by the bot.
  - Existing CI workflows still execute agent-written code on `dev/*` (read-only token, no secrets).
- **Limits:**
  - A compromised controller can still forge gate records and mint tokens within budgets (doc 18 K-10). The ruleset, operator review (G7) and signed checkpoints (DOD-18) are the backstop.
  - On a personal repository the merge actor is detected after the fact (G-DETECT).
  - On a single-node workstation a container escape reaches the brokers' keys. That is why reduced-assurance projects use a sandbox-only App installation and a separate key (D16).
- **Status (D26):**
  - Base manifests (NetworkPolicies, Secret pinning, admission) are Implemented (untested on a cluster).
  - gitbroker, gitbroker-fetch, artifact-gateway, model-gateway and the registry proxies are **Designed, unverified**: no code exists.
  - DOD-02 with D13 and the dev-bot App (DOD-13) are awaiting operator approval.

## Related requirements

CON-003 (role boundary, operator merge authority), CON-007 (human approval enforced by GitHub) and the intent of CON-008 (no automation under the operator's identity) are applied to the development platform. Production MERCURY's identities (`mercury-bot`, `mercury-ops`) and ADR-006 / ADR-008 / ADR-014 are unchanged. Development and production credentials stay separate (separation rules S1–S2).
