# ADR-017: Claude reads git-object snapshots, never checkouts

| | |
|---|---|
| Status | **Accepted** |
| Date | 2026-10-12 |
| Owner | Agent A. Agent C owns the `SnapshotBuilder` and the `snapshots` table (`architecture/components.md` §9); Agent B owns readable roots per decision type (`integrations/claude.md` §3); Agent E owns SEC-205 |
| Related ADRs | [ADR-004](ADR-004-claude-invocation-model.md), [ADR-011](ADR-011-authorization-records-and-verification.md), [ADR-013](ADR-013-agent-process-isolation.md), [ADR-016](ADR-016-filesystem-layout.md) |

## Context
- Claude reads repository trees for authorization and plan review (at `base_sha`) and for PR review (at `head_sha`).
- Phase 2 B and C used detached `git worktree add` checkouts. A checkout:
  - contains a `.git` file pointing into the mirror;
  - applies in-tree `.gitattributes` (`working-tree-encoding`, `eol`, `ident`, filters), so Claude can read bytes different from the blob GitHub shows the human;
  - materialises symlinks, which the CLI fallback cannot confine as well as the SDK hook;
  - stays owner-writable, so the content Claude reviewed is not provable after the SHA is fixed (RA-13, RE-06, RF-05, RC-24).
- Audit question 7 in the brief asks what exactly Claude reviewed.

## Decision
1. **Every tree Claude reads is a coordinator-built snapshot** built from `git ls-tree -r -z` and `git cat-file` in the mirror:
   - no `.git`;
   - gitattributes not applied, so `export-ignore` cannot hide files and filters cannot change bytes;
   - symlinks and submodules rendered as text placeholders;
   - files 0444 and directories 0555, under `WORK_ROOT/snapshots/<tree_sha>/` ([ADR-016](ADR-016-filesystem-layout.md)), readable by the agent uid.
2. **Snapshots are content-keyed** by tree SHA and may be shared between tasks and runs. A manifest hash is recorded at build time and verified after each run.
3. **The review binding records `snapshot_tree_sha`** (= `head^{tree}` for PR review) together with the head SHA ([ADR-011](ADR-011-authorization-records-and-verification.md)).
4. This **replaces "reference checkout" and "review checkout"** everywhere. Claude never runs inside a Codex worktree.
5. The snapshot builder is in place before Claude reads any repository content (milestone M3), and its test (SEC-T-24) is a gate.

## Alternatives considered
| Alternative | Why rejected |
|---|---|
| Detached worktree checkout with `chmod -R a-w` (Phase 2 B, C) | `.git` present, attributes applied, symlinks materialised, directories writable by the owner |
| `git archive` | Applies `export-ignore` and `export-subst`, so the reviewed tree can differ from the merged tree |
| Claude reads the diff only | Reviews need context beyond the changed lines; architecture and security review read surrounding code |
| Claude reads blobs through a tool that calls `git cat-file` | Gives Claude a git-executing tool; a file tree with the standard read tools is simpler to confine |

## Consequences
- **Positive:** "what Claude reviewed" is provable byte-for-byte and matches what GitHub shows; snapshot content cannot change after the review.
- **Negative:** building snapshots costs disk and time for large repositories; content-keying and retention limits keep it bounded (disk thresholds in D's parameter table).
- **Negative:** Claude sees placeholders instead of symlink targets and submodule contents; reviews of such changes rely on the diff and the placeholder text.

## Related requirements
SEC-205; FR-101, FR-160, FR-161, FR-260; CON-003.

## Related findings
RA-13, RE-06, RF-05, RC-24.

## Operator decisions
None.
