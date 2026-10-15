# ADR-021 — Temporary development orchestration for building MERCURY

| | |
|---|---|
| Status | **Proposed** (requires operator approval: DOD-01) |
| Date | 2026-10-15 |
| Owner | Lead Architect (development orchestration package) |
| Related ADRs | ADR-003, ADR-008, ADR-012, ADR-014 (none superseded) |

## Context

The MERCURY TDD specifies a production coordinator that does not exist yet. Building it requires coordinated work by several specialists while preserving:

- the design authority of the TDD;
- the operator's exclusive merge authority;
- auditability.

The design phase showed that conversation-held state is lost when subagents are interrupted.

## Decision

1. **Orchestration.** Build MERCURY with a Claude Code **main session** acting as Principal Orchestrator. It coordinates 12 project subagents (`.claude/agents/mdev-*.md`) with no nesting and no peer messaging.
2. **Durable state.** Keep development state in a hash-chained ledger on branch `devorch/state`, written only by `tools/devorch/devorch.py`. GitHub stays authoritative for code, CI and human approval.
3. **Gates.** Enforce development gates G1–G7, with completion based on independently re-verified evidence. Map them to TDD gates G-S1…G-S5 as READY preconditions.
4. **Separation.** The development system holds no production authority, schema or identity (separation rules S1–S4). It is retired according to the self-hosting plan (Stages A–E).

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Build parts of `mercuryd` first and use them to orchestrate their own development | Implementation before design approval; it blurs the two systems |
| Linear as the development state store | Linear writes are not authorized; Linear lacks hash-chained history |
| Purely conversational orchestration | State is lost on interruption (observed in the design phase) |
| One generalist agent | Loses independent review and security separation |

## Consequences

- **Positive:** auditable development work; resumable after session loss; independent review; clean hand-over to MERCURY.
- **Negative:** process overhead per task (modelled at ≈ 0.45 day per task).
- **Limits of the controls:** the Claude Code deny rules are not a security boundary, so the real guarantee depends on the `main` ruleset and the development identity decision (DOD-02/03).

## Related requirements

CON-003 (role boundary, operator merge authority), CON-007 (human approval enforced by GitHub), CON-008 (no MERCURY action under the operator's identity) and the TDD §32 conditions C1–C7 remain unchanged and apply to production MERCURY. CON-008 does not formally bind the development system, but DOD-03 option (a) applies its intent to development agents too.
