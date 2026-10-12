# ADR-009: Linear for spec and intent; coordinator for execution state and authority; GitHub for code and human approval

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12. Agent B owns the Linear state mapping detail (`integrations/linear.md`).

## Context
- Linear has 7 workflow states; MERCURY has ~18 (discovery fact 5). Specs live in Linear issue descriptions with AC checkboxes; relations are heavily used.
- Linear's GitHub integration moves issues to In Review / Done on PR events; Linear Coding sessions can start Claude/Codex on delegated issues (a second, unauthorized start path).
- Today `Todo` is the agents' queue signal, which conflicts with "a Linear status change alone never starts work".
- Several writers touch Linear (operator, integration, MERCURY); GitHub has its own truth about code and approvals.

## Decision
1. **System-of-record table** as in `architecture/overview.md` §9.1. In short:
   - **Linear**: issue content, spec, AC, labels, relations, and the operator's **eligibility** signal (state `Todo` + label `mercury`, excluding `Not Speced`).
   - **Coordinator (SQLite)**: authorizations, task state, runs, plans, approvals, reviews, audit, and the **projection** of coarse status to Linear.
   - **GitHub**: code, branches, PRs, checks, the operator's approval and the merge.
2. **Direction rules**:
   - Inbound observations may **stop, pause or invalidate** work; they may never **start or approve** it.
   - Outbound writes are idempotent projections with markers `<!-- mercury:{dedup_key} -->` and deterministic IDs.
   - The Linear projection is **monotonic** (never moves an issue backwards) and **lenient** (accepts the integration moving it ahead).
3. **Spec binding**: an authorization binds to a SHA-256 of a canonical issue snapshot (title, description, AC, labels, relations). A changed hash blocks the next phase until Claude re-authorizes.
4. **Conflict handling** per the table in `overview.md` §9.3 (C1–C10), including refusing to dispatch while a non-MERCURY Linear agent is delegated on the issue.
5. PRs use the non-closing phrase `Part of JAM-n`; the coordinator moves the issue to Done only after merge verification (ASM-A-07; operator decision OD-A-03).
6. Back-references (trailers, PR body, Linear comments) let an observer reconstruct history; they never restore authority after DB loss.

## Alternatives
- **Linear as full state store** (custom states/labels per MERCURY state): no transactions or leases; fields writable by humans and integrations; forgeable authority. Rejected.
- **Coordinator forces exact mirror in Linear**: fights the operator and the integration (flapping). Rejected.
- **Disable Linear's GitHub PR automations entirely**: cleaner single-writer, but changes the operator's existing workflow for non-MERCURY issues. Kept as an option if ASM-A-07 fails.
- **New Linear states** ("Awaiting authorization", "Plan review"): possible, but a workspace change the operator must make; not required.

## Consequences
- The operator keeps writing specs and choosing eligibility in Linear as today; MERCURY never edits issue descriptions.
- Linear shows coarse progress plus MERCURY comments; detail lives in `mercury trace` and the PR.
- Every conflict path ends in a bounded state with at most one notification.

## Related requirements
Brief steps 2, 14; hard constraint 3 (status change never starts work); §A (dependency resolution, status), §C, §G; AP-5, AP-7, AP-10.
