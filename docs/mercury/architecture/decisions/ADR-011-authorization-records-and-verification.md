# ADR-011: Immutable, hash-bound authorization and approval records, verified at every dispatch

## Status
Proposed (Phase 2, Agent A). Date 2026-10-12. Agent C owns the full schema and guard catalogue; Agent E evaluates the threat coverage.

## Context
- Hard constraints: no Codex run without a valid, unrevoked Claude authorization bound to the task and repo; no implementation without a Claude approval bound to the exact plan artifact hash; a plan revision invalidates earlier approval; authorization is a versioned record.
- Under [ADR-004](ADR-004-claude-invocation-model.md) Claude never writes the DB; the coordinator records Claude's verdicts. So the question is how the coordinator is prevented from fabricating authorizations — and how much that matters when coordinator, DB and operator share one OS user.

## Decision
1. **Record shape** as `AuthorizationRecord` / plan approval in `architecture/overview.md` §8.3: immutable fields; `version` + `supersedes`; bound to issue snapshot hash, repo, base branch, scope, limits, expiry; and a `decision` block with Claude `run_id`, session id, model, prompt template hash, input bundle hash, output hash, transcript hash.
2. **Revocation and supersession** are separate append-only rows (`authorization_revocations`, newer `version`). Revocable by a Claude decision or an operator CLI command (operator can always stop work, never start it).
3. **Database-enforced provenance** (defence against coordinator bugs):
   ```sql
   CREATE TRIGGER authz_requires_claude_run BEFORE INSERT ON authorizations
   WHEN NOT EXISTS (
     SELECT 1 FROM agent_runs r
     WHERE r.run_id = NEW.decision_run_id
       AND r.agent = 'claude' AND r.decision_kind = 'AUTHORIZE'
       AND r.status = 'succeeded'
       AND r.output_sha256 = NEW.decision_output_sha256
       AND json_extract(r.output_json, '$.decision') = 'authorize'
       AND json_extract(r.output_json, '$.issue_snapshot_sha256') = NEW.issue_snapshot_sha256
   )
   BEGIN SELECT RAISE(ABORT, 'authorization requires a succeeded Claude AUTHORIZE run'); END;

   CREATE UNIQUE INDEX authz_one_per_run ON authorizations(decision_run_id);
   CREATE TRIGGER authz_immutable BEFORE UPDATE ON authorizations
   BEGIN SELECT RAISE(ABORT, 'authorizations are immutable'); END;
   CREATE TRIGGER authz_no_delete BEFORE DELETE ON authorizations
   BEGIN SELECT RAISE(ABORT, 'authorizations are immutable'); END;
   ```
   Same pattern for `plan_approvals` (`decision_kind='PLAN_REVIEW'`, `$.verdict='approve'`, `$.plan_sha256 = NEW.plan_sha256`).
4. **Single writer module**: only `DecisionRecorder` holds the prepared insert statements (lint rule + test).
5. **Dispatch guard** (`overview.md` §8.5) re-verifies the record, hashes, expiry, revocation, plan binding, dependencies and limits **inside the transaction that claims the job**.
6. **Hash-chained audit log** (`prev_hash`, `entry_hash`) verified at startup and daily.
7. **External back-references**: commit trailers and PR body carry `auth_id` + version and plan hash; a Linear comment records each authorization summary.
8. **HMAC over canonical record JSON** with a Keychain key: **optional hardening for Milestone 2**, retained only if Phase 0 shows another local process (e.g. a sandboxed Codex) could write the DB file (ASM-A-06).

## How much this matters (explicit position)
Inside one OS user, nothing stops a fully compromised coordinator from forging records; cryptography cannot fix that. The controls above target the realistic risks — coordinator bugs creating a second start path, agent processes touching state files, and auditability. The **enforcement backstop is GitHub** ([ADR-008](ADR-008-agent-identities-and-merge-governance.md)): a forged authorization can at worst produce an unwanted PR, never unreviewed code on a protected branch. Stronger isolation (separate macOS user for `mercuryd`) is a recorded future option.

## Alternatives
- **Claude signs its own decisions** (give Claude a signing key/tool): the key would live in the same user domain and in a process that reads untrusted text; no real gain. Rejected.
- **Store authorizations in Linear** (comment or label): writable by the human identity and integrations; forgeable. Rejected.
- **External notarisation** (append record hashes to a GitHub gist/issue): adds tamper evidence off-Mac; low value given trailers already leave external copies. Deferred.
- **Mutable `status` column on authorizations**: simpler, loses history. Rejected.

## Consequences
- Every Codex run is traceable to one authorization version and (for implementation) one plan hash — NFR-AUD-01 becomes a query.
- Spec edits, plan revisions and expiry automatically invalidate dispatch without special code paths.
- Contract tests must try to insert forged records and confirm the triggers abort.

## Related requirements
Hard constraints 1–3; authority invariants 1–3 (`03-design-baseline.md`); brief §A (versioned authorization records), §D, §I; NFR-AUD-01, NFR-AUD-02; AP-1, AP-6, AP-10.
