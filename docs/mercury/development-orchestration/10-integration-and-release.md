# 10 — Integration and Release Process

## 1. Integration

1. **Batching.** At a wave boundary, or whenever ≥ 2 tasks reach AWAITING_INTEGRATION, the orchestrator writes an integration **subtask** contract `DT-nnnn-iN` (short lifecycle) for `mdev-integration-release-engineer`: `kind: integration`, `merc_issue: null`, `covers_tasks` = the task ids included, and in `notes` each task's branch and tested head (the G2 `head_commit`, which G3/G4 are bound to). `check-contract` refuses an integration contract without `covers_tasks`.
2. **Worktree.** The orchestrator creates the integration branch (`dev/dt-<nnnn>-int-<wave>-<n>`, `06-…` §2) from current `main` and its worktree with `git -c core.hooksPath=/dev/null worktree add …`; specialists cannot run `git worktree`.
3. **Building the branch.** The engineer merges or cherry-picks each covered branch in dependency order, at exactly its tested head.
4. **Verification.** The engineer then:
   - runs the full suite plus integration tests (TC-INT, TC-E2E with fakes);
   - proves patch-id equality per task: `git range-diff <base>..<tested_head> main..<integration branch>`;
   - writes `result.json` to `evidence_dir` with `integrated_heads: ["DT-nnnn@<sha>", …]`, one entry per covered task, and `recommendation`.
5. **Pass (G5).** `check-result` treats the union of the covered tasks' `allowed_paths` (plus the subtask's own) as the integration scope and checks that every `integrated_heads` entry is contained in the integration tip and equals the task's tested head. After `import-evidence`, the orchestrator records `result_accepted` on the subtask (→ COMPLETED), then `integration_verified` on each covered task with `subtask:DT-nnnn-iN` evidence. `record` refuses G5 unless the subtask is COMPLETED, its `covers_tasks` contains the task, its accepted result has `status: completed` and `recommendation` accept (or accept_with_conditions), and its `integrated_heads` entry for the task equals that task's tested head. PRs are still **one per task**, so the operator reviews small units. The integration branch is evidence, never pushed and never a delivery vehicle.
6. **Fail.** The orchestrator records `integration_failed` on the affected task (→ RUNNING; limit 2 per task, then `failed` or `escalated`).
   - A **textual conflict** sends a correction attempt to the later task's owner.
   - A **semantic failure** gets diagnosis by the Integration Engineer. The fix becomes a new task with its own reviews. The Integration Engineer **never** fixes reviewed logic in place.
   - Any correction changes the head, so G2–G5 are redone at the new head.
7. **To G6.** `devorch.py push --task <id>` (dev/* branch, tip = tested head, G1–G5 recorded, baseline verified) → create a **draft** PR → CI → `record pr_prepared --head <sha>` (`06-…` §6). The orchestrator never edits the PR body or base afterwards.

## 2. Pull request template (development PRs to `main`)

```markdown
## Summary
<what and why> — MERC-nnn (`planning/issue-breakdown.md`)
## Design references
docs/...§...@<sha> (operator-approved)
## Evidence
- Devorch task: DT-nnnn (contract v<k>, attempt <n>); ledger: devorch/state:ledger/DT-nnnn.jsonl@<sha>
- G2 tests: <commands, results>
- G3 review: DT-nnnn-r<k> (reviewed_head_commit <sha>); G4 security: DT-nnnn-s<k>; G5 integration: DT-nnnn-i<k> (integrated head <sha>)
## Requirements / tests
FR-…, SEC-… / TC-…
## Risk
<security-sensitive? migrations? new deps?>
## Human gate
Draft PR opened by the development identity. Approve and merge only if the head SHA equals <tested head>; G7 is recorded from the merge (merged_by checked).
```

## 3. Releases (for MERCURY's own versions)

| Step | Owner | Evidence |
|---|---|---|
| Version bump (semver) and `CHANGELOG.md` | Integration and Release Engineer (task) | PR |
| Release candidate build from a `main` commit: `npm ci --ignore-scripts`, build, test, package, SHA-256 checksums | DevOps workflow (MERCURY CI) | CI artefacts + checksums |
| Rollback verification: install RC N over N-1 in a scratch prefix, then roll back (macos-service §13) | Reliability Engineer (VM / Mac lane) | Logs |
| Release readiness assessment | Integration and Release Engineer | Report: G1–G7 for every included task (from `devorch.py status` output that the orchestrator supplies as an evidence file), open defects, SAC status |
| Tag and publish | **Operator** (or the orchestrator on an explicit operator instruction per release) | Tag on the reviewed commit |
| Install on the Mac | **Operator** only (operator-controlled deployment) | — |

A release never includes a commit that lacks G7, and never bypasses CI or a security finding.
