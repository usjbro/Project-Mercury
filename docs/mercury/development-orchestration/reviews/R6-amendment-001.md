# R6 — Independent review of Amendment 001 (devplat)

Reviewers (read-only, dispatched 2026-10-17 against commit `8b17bf2`):

| Review | Agent | Re-ran | Verdict |
|---|---|---|---|
| Architecture and consistency | `mdev-lead-architect` | `test_jobspec.py` 11/11, `validate_projects.py` 2/2 | **accept_with_conditions** to adopt the direction (DOD-11). **Rejected** as a baseline for DP1 implementation until A-01…A-09 and A-11…A-17 are fixed |
| Security | `mdev-security-engineer` | base 121/121, CEL 93/93 compile, 61 cases / 0 mismatches, jobspec 11/11, DB 20/21 (the 21st imports `tools/devorch`). Wrote 11 exploit cases; every gap labelled E was accepted by the policies | **Changes required** |

Fix decisions D1…D26, binding for the fix round, are recorded in §3. Dispositions per finding are in §4, filled after the fix round.

## 1. Architecture findings (A-nn)

| ID | Sev | Issue (short) | Decision |
|---|---|---|---|
| A-01 | High | Hard-precondition facts are not per project; a platform-wide fact unlocks any project; keys disagree (DOD-03 / identity / DOD-13) | D1 |
| A-02 | High | devorch G1 rules lost in the DB port: interface-hash match, AWAITING_HUMAN dependency, per-task TDD/P0 facts | D7 |
| A-03 | High | Result checks weaker than devorch: result status, head binding, blocking findings computed by the controller, `contract_errors` not run on every record | D7 |
| A-04 | High | Platform core not project-agnostic: `mdev-*` and v1 keys seeded; tests import `tools/devorch` and `docs/mercury` | D6, D23 |
| A-05 | High | No result/handoff v2; the role definitions are Mercury- and v1-specific, so "12 updated definitions" is not delivered | D23 |
| A-06 | High | Schema lacks state other docs rely on: budgets, admission holds, test runs, config version, gateway role | D8 |
| A-07 | High | Roadmap not credible: no build vehicle for DP1–DP5; components missing; unmodelled estimates; DP0 gated on Mercury TDD approval; doc 27 contradicts it | Lead (doc 28) |
| A-08 | Medium | Task ids are global across projects | D3 |
| A-09 | Medium | Status model mismatch: an onboarding project cannot get tasks | D4 |
| A-10 | Medium | `network_class` vocabulary conflict | D5 |
| A-11 | Medium | Artifact contract inconsistent (names, caps, TTL, method, bucket rule, prefixes) | D11 |
| A-12 | Medium | Docs 16 and 21 disagree on adoption and orphan rules | D17 (doc 21 normative) |
| A-13 | Medium | AT-20 contradicts `podFailurePolicy` | Fixed in `9ea4b92` |
| A-14 | Medium | Two migration mechanisms; the startup route gives the controller owner rights | D9 |
| A-15 | Medium | Checkpoint anchoring through gitbroker is impossible under DOD-13 | D18 context: anchor in object-lock storage plus a signer (DOD-18) |
| A-16 | Medium | Human commits on a PR branch are undefined (force-push risk) | D21 |
| A-17 | Medium | Doc 18 still stale after `27f0d38` | Security group |
| A-18 | Medium | R6 file missing; README has no devplat status rows; branch header wrong | Lead (this file, README) |
| A-19 | Medium | Failure classification conflicts between docs 16, 17 and 21 | D17 |
| A-20 | Medium | Gaps in doc 27: schedule item, macos-service §1 CI row, ADR-018, reviewed-doc list | Core group |
| A-21 | Medium | RTO inconsistent with the task-lease TTL | D22 |
| A-22…A-29 | Low | Status labels, naming formulas, id limits, two profile taxonomies, false fairness claim, stale doc 15 topology, provenance (fixed `9ea4b92`), decisions presented as made | D23–D25, core group |
| A-30 | Low | Amendment text not in the repository | Fixed `9ea4b92` (`amendments/`) |

## 2. Security findings (S-nn)

| ID | Sev | Issue (short) | Decision |
|---|---|---|---|
| S-1 | High | Model gateway allows provider-side tools (web fetch/search, MCP connector, code execution) and the Files/Batches APIs: data exfiltration and instruction intake | D12 |
| S-2 | High | Exec, build and test pods reach the shared external S3 endpoint: PUT to an attacker's presigned URL | D10 |
| S-3 | High | Agent-written code runs in GitHub Actions on `dev/*` before review, with a GITHUB_TOKEN and internet access | D13 |
| S-4 | Medium | Any subject from an enabled IdP can record operator facts; empty allowlist by default | D2 |
| S-5 | Medium | A platform-wide fact satisfies per-project preconditions | D1 |
| S-6 | Medium | Namespacer policy checks names only; open egress or unbounded quota is possible | D19 |
| S-7 | Medium | buildkitd unconfined in the host user namespace | D20 |
| S-8 | Medium | Compromised-controller blast radius under-stated | Security group (K-10) |
| S-9 | Medium | The CNPG owner login lives in an unpinned Secret, so the event log can be rewritten | D9 |
| S-10 | Medium | Failure class taken from self-reported signals gives free retries | D17 |
| S-11 | Medium | Planner contracts and revisions accepted without operator review; revision resets budgets without limit | D18 |
| S-12 | Medium | Shared, publish-capable registry proxy (dependency confusion across projects) | D14 |
| S-13 | Medium | Global image-prefix allowlist (cross-project images; project images in platform namespaces) | D15 |
| S-14 | Medium | "App cannot merge/approve" is false with `contents:write` + `pull_requests:write`; ruleset shape unresolved | D13 |
| S-15 | Medium | T3 sandbox class: egress to GitHub next to sandbox keys; the controller holds keys | DOD-24 recommendation (keep T3 on the Mac lane); security group documents it |
| S-16 | Medium | Reduced-assurance mode unchanged for code dispatch | D16 |
| S-17…S-24 | Low | SA-token Secret type; Job update not pinned; PV binding; Service externalIPs; seLinuxOptions; CNPG label mismatch; label-only auth to gitbroker push; shared workload-identity annotations | Security and charts groups |
| Overclaims 1–10 | — | "Resolved" without built components; "no route to internet"; "cannot merge/approve"; PI-7; one credential, one holder; no cross-project cache; doc 24 §10 not reproducible; `validate_all.sh` silent skips; doc 18 §15; minor inconsistencies | D26; lead (validator), charts group (doc 24 §10) |

## 3. Fix decisions D1–D26

The binding text the fix groups worked from (copied from the lead's decision record):

1. **D1** — Hard preconditions are per project and take project-scoped facts only. Keys: `DOD-02` and `DOD-13`. The list comes from project config, not from DB seeds.
2. **D2** — `operator_identities` allowlist, checked in `record_operator_fact`. The chart refuses an empty allowlist.
3. **D3** — Task identity is `(project_id, task_id)`.
4. **D4** — DB project statuses are draft, onboarding, active, paused and archived. FULL-lifecycle dispatch and pushes are allowed only when the project is active and holds the D1 facts.
5. **D5** — `network_class` is `none | model-only | deps`.
6. **D6** — The role catalogue is loaded from execution profiles. There are no seeded literals. `mdev-` is a historical prefix.
7. **D7** — The devorch G1, result and contract rules are restored in the DB, with tests ported.
8. **D8** — New schema state: budget reservations, admission decisions, test runs, `config_version`/`assurance_mode` on events, and the gateway role.
9. **D9** — Migrations run as a Helm hook Job with `devplat_migrator`. The owner role is NOLOGIN, and the controller never migrates.
10. **D10** — `devplat-artifact-gateway`: agents never reach the object store.
11. **D11** — One artifact layout, owned by doc 20.
12. **D12** — Model-gateway endpoint allowlist and server-tool rejection; projects bound by token.
13. **D13** — Per-repository GitHub CI hardening added to DOD-02. Claims about App merge/approve corrected; probe N10 attempts both.
14. **D14** — Read-only registry proxy per project.
15. **D15** — Image prefixes per project and per namespace role.
16. **D16** — Reduced-assurance mode needs a per-project fact. In that mode: a sandbox-only App, a separate key, and no builds.
17. **D17** — `environmental` is decided only from platform signals. Doc 21 is normative.
18. **D18** — Planner contracts and revisions need operator approval. Revision cap 3.
19. **D19** — Namespacer as a Deployment with a fixed template, plus content-validating policies.
20. **D20** — Builds off by default. `buildkitd` needs `hostUsers: false` and Localhost seccomp.
21. **D21** — Human commits are taken as the next base after validation. Never force-push.
22. **D22** — RTO = task-lease TTL + election. Fence-transfer of leases on election.
23. **D23** — Result and handoff v2 schemas; a runtime preamble for role definitions.
24. **D24** — Project id ≤ 24 characters.
25. **D25** — One profile taxonomy, P1–P6.
26. **D26** — Status label "Designed, unverified" when the components are not built.

## 4. Dispositions

Filled after the fix round. See `R6-dispositions.md`.
