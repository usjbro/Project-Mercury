# 11 — MERCURY Self-Hosting Transition Plan

**Self-hosting** means MERCURY coordinates (part of) its own development on `usjbro/project-mercury`. Every stage is entered only on evidence, never because code exists. Every stage keeps a rollback path to this development orchestrator. Self-hosting never bypasses the TDD's deployment and unattended-operation restrictions.

| Stage | Description | Entry evidence (all required) | Exit / rollback |
|---|---|---|---|
| **A** | Claude Code orchestrator coordinates the 12 specialists (this package) | DOD-01 approved; ledger branch created; ruleset on `main` (DOD-02) | — |
| **B** | MERCURY coordinator core passes deterministic tests | M1 complete (MERC-101…113 G7). Evidence: PROP suite 0 violations / 10,000 sequences; crash harness 0 duplicate effects; all INV triggers tested on both drivers | No operational change; stays at A |
| **C** | MERCURY coordinates a controlled **sandbox** workflow (`mercury-sandbox` repo, Linear `MSB`) | **G-S1, G-S2, G-S3** recorded; M5–M6 complete; MERC-708 live-agent sandbox smoke passed; SEC-T-16 merge-attack suite passed on the sandbox ruleset | Stop `mercuryd`; continue at A |
| **D** | MERCURY coordinates **selected** development tasks on `project-mercury` under supervision | Stage C for ≥ 10 sandbox tasks without a duplicate side effect, a security finding ≥ High, or a manual state repair. `project-mercury` onboarded as a target (TDD §15 governance: rulesets, CODEOWNERS = operator, MERCURY checks pinned, **G-DETECT written acceptance or G-ORG**). **G-S4** recorded. Operator selects each task by `mercury` label (OD-10). Each task is authorized by MERCURY's Claude authorization run — not by this development orchestrator | Remove the `mercury` label; `mercury pause --all`; the development orchestrator re-takes the task (the ledger records the hand-back) |
| **E** | MERCURY coordinates approved development workflows within its security boundary, including unattended periods | **G-S5** (G-ORG on `project-mercury`, OD-36 decided/implemented, SEC-604 anchoring live, SAC-01…20 green); M8 recovery suite on the real Mac; 30-day pilot watch without Critical/High incidents | `mercury pause --all` + Stage D; Stage A remains available |

## Rules during the transition

1. **One coordinator per task.** A MERC task is owned either by the development ledger or by MERCURY, never both. Hand-over is a ledger record (`cancelled`, note "handed to MERCURY task tsk_…"), plus MERCURY's own authorization.
2. **Production rules apply to MERCURY's work on itself.**
   - Changes to `.claude/**`, `.mcp.json` and `.github/**` are **block-class** (SEC-310).
   - `CLAUDE.md`/`AGENTS.md` changes need policy acknowledgement.
   - Therefore **tasks that modify the development-orchestration configuration stay with Stage A forever.**
3. **No credential sharing.** MERCURY's `mercury-bot`/`mercury-ops` Apps and keys are separate from the development identity (DOD-03).
4. **Rollback is always available.** The development orchestrator, agents and ledger are kept until Stage E has run for 30 days. Even then they stay in the repository as the fallback.
5. **Evidence threshold.** Every stage gate needs operator sign-off recorded in `ESCALATIONS.md` (kind `operator_decision`).

## Required evidence checklist (brief Phase 12)

| Required | Where it comes from |
|---|---|
| Passed recovery tests | MERC-113, 801, 803; TC-REC suite |
| Passed authorization tests | MERC-304, 305; TC-SM/TC-SEC authorization cases |
| Passed security validation | G-S1…G-S3 (Stage C), G-S4 (D), G-S5 (E); MERC-805 |
| Reliable structured messaging | MERC-303 contract tests; 0 schema-invalid outputs accepted in Stage C |
| Durable task state | MERC-102/103 + crash injection |
| Verified process supervision | MERC-107, 108; G-S2 |
| Verified GitHub permission boundaries | MERC-024, 205, 508; SEC-T-16 |
| Successful sandbox integration tests | MERC-708 + Stage C run |
