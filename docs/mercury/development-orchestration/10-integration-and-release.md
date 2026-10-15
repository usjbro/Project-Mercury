# 10 — Integration and Release Process

## 1. Integration

1. **Batching.** At a wave boundary, or whenever ≥ 2 tasks reach AWAITING_INTEGRATION, the orchestrator issues an integration contract to `mdev-integration-release-engineer`. The contract lists `{task_id, branch, reviewed_head}` for each included task.
2. **Building the branch.** The engineer creates `devint/<wave>-<n>` from current `main` and merges or cherry-picks each reviewed branch in dependency order.
3. **Verification.** The engineer then:
   - runs the full suite plus integration tests (TC-INT, TC-E2E with fakes);
   - proves patch-id equality: `git range-diff <base>..<reviewed_head> main..devint/...`.
4. **Pass (G5).** Each task gets `integration_verified`. PRs are still **one per task**, so the operator reviews small units. The integration branch is evidence, not a delivery vehicle.
5. **Fail.**
   - A **textual conflict** sends a correction task to the later task's owner, rebased on main.
   - A **semantic failure** gets diagnosis by the Integration Engineer. The fix becomes a new task with its own reviews. The Integration Engineer **never** fixes reviewed logic in place.

## 2. Pull request template (development PRs to `main`)

```markdown
## Summary
<what and why> — MERC-nnn (`planning/issue-breakdown.md`)
## Design references
docs/...§...@<sha> (operator-approved)
## Evidence
- Devorch task: DT-nnnn (contract v<k>, attempt <n>); ledger: devorch/state:ledger/DT-nnnn.jsonl@<sha>
- G2 tests: <commands, results>
- G3 review: <file>; G4 security: <file or n/a>; G5 integration: devint/<..>@<sha>
## Requirements / tests
FR-…, SEC-… / TC-…
## Risk
<security-sensitive? migrations? new deps?>
## Human gate
Approve and merge only if the head SHA equals <reviewed head>.
```

## 3. Releases (for MERCURY's own versions)

| Step | Owner | Evidence |
|---|---|---|
| Version bump (semver) and `CHANGELOG.md` | Integration and Release Engineer (task) | PR |
| Release candidate build from a `main` commit: `npm ci --ignore-scripts`, build, test, package, SHA-256 checksums | DevOps workflow (MERCURY CI) | CI artefacts + checksums |
| Rollback verification: install RC N over N-1 in a scratch prefix, then roll back (macos-service §13) | Reliability Engineer (VM / Mac lane) | Logs |
| Release readiness assessment | Integration and Release Engineer | Report: G1–G6 for every included task, open defects, SAC status |
| Tag and publish | **Operator** (or the orchestrator on an explicit operator instruction per release) | Tag on the reviewed commit |
| Install on the Mac | **Operator** only (operator-controlled deployment) | — |

A release never includes a commit that lacks G7, and never bypasses CI or a security finding.
