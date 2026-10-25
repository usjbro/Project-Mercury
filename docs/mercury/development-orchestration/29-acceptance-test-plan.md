# 29 — Validation and acceptance test plan (devplat, Amendment 001)

Status: **Proposed**. §2 lists what was actually executed in the authoring environment, with commands and results. Everything else is **not yet run**: no Kubernetes cluster was available, and none was created (DOD-15).
Reuses: the v1 regression suite (`tools/devorch/test_devorch.py`, 30 cases) is the specification for AT-03…AT-07. The Mercury verification plan (`docs/mercury/testing/verification-plan.md`) is unchanged.

## 1. Acceptance criteria → tests

Levels:
- **U** — unit or schema, no cluster.
- **DB** — real PostgreSQL.
- **K1** — single-node local cluster with an enforcing CNI.
- **K2** — multi-node cluster with an exec pool and gVisor.
- **GH** — sandbox GitHub repository with the dev bot App and a ruleset.

| AT | Acceptance criterion (amendment §15 / §14) | Test | Level | Status |
|---|---|---|---|---|
| AT-01 | The platform is independent of Mercury and Jupiter | The platform repository builds, tests and deploys with no Mercury or Jupiter checkout. A static check shows no `mercury`/`jupiter` literal in controller code outside `projects/` and tests | U, CI | Partly run here: `jobspec.py` has no project literal. The repository is not yet split |
| AT-02 | Manifests are valid for the target API | `platform/tools/validate_k8s.py platform/deploy/base` against strict v1.33 schemas | U | **Run** (§2) |
| AT-03 | Task state survives restarts; transitions are transactional and legal | DB suite: legal path, illegal refusal, G4 not skippable, duplicate gate, budgets, append-only events, hash chain | DB | **Run** (§2) |
| AT-04 | Idempotent dispatch; no duplicate execution | Concurrent dispatch with the same idempotency key gives one `job_runs` row. A deterministic Job name gives AlreadyExists, then adopt | DB, U, K1 | DB and U **run**; K1 not run |
| AT-05 | Leases and fencing | An expired lease can be taken over; a stale holder's write is refused | DB | **Run** (§2) |
| AT-06 | Agents cannot self-approve gates | Agent pods hold no DB credentials (the DB role check passes); a planner proposal cannot record a gate; `operator_facts` cannot be written by the controller role | DB, K1 | DB **run**; K1 not run |
| AT-07 | devorch parity | All 30 devorch regression cases are ported to the controller and pass | U, DB | Not run (DP2) |
| AT-08 | Jobs are supervised independently | Create a Job, observe phases, collect the result; the Job → task state mapping (`16-…`) holds | K1 | Not run |
| AT-09 | Job spec least privilege | `jobspec` output is strict-valid and hardened: no SA token, non-root, read-only root, drop ALL, seccomp, digest-pinned image, exec pool, `backoffLimit 0` | U | **Run** (§2) |
| AT-10 | Results are validated before anything is pushed | gitbroker refuses empty-commit hiding, renames out of restricted paths, hidden index entries, and out-of-scope files (ports of devorch tests) | U | Not run (DP3); the devorch originals pass |
| AT-11 | PR is prepared, then the platform stops at human approval | The sandbox repository gets a draft PR from the dev bot. Calls by the bot to merge, approve, or change rulesets return 403/404. G7 is recorded only after a human merge is observed | GH | Not run |
| AT-12 | Bootstrap steps 1–9 | A scripted bootstrap on kind/k3d, followed by the sample agent Job and the result in PostgreSQL and the artifact store | K1 | Not run |
| AT-13 | No agent reaches the Kubernetes API | From an agent pod: no token mounted; an anonymous request to `kubernetes.default` is refused or blocked by NetworkPolicy | K1 | Not run |
| AT-14 | No agent reaches GitHub, Linear, the DB or credentials | From an agent pod, connections to api.github.com, api.linear.app, PostgreSQL and gitbroker admin all fail. Only the model gateway, the artifact store (presigned) and, for the `deps` class, the registry proxy succeed | K1 | Not run |
| AT-15 | Cross-project isolation | A Mercury agent pod cannot reach any `proj-jupiter-*` pod or service, nor read Jupiter's artifacts (presigned URL scope, bucket policy) | K1 | Not run |
| AT-16 | Admission blocks dangerous pods | Each of these is rejected in `proj-*` namespaces: privileged, hostPath, docker.sock, hostNetwork, a missing runtimeClass on the exec pool, an unpinned image | K1 | Not run |
| AT-17 | Untrusted-code isolation | Exec pods run under gVisor on the exec pool (`runsc` visible in the pod sandbox). The reduced-assurance mode is flagged on a single node without gVisor | K2 | Not run |
| AT-18 | Container crash recovery | Kill the agent container. Expected: attempt_failed or env_retry per classification, a new attempt within budget, evidence kept | K1 | Not run |
| AT-19 | Controller restart recovery | Delete the leader pod during a run. Expected: a new leader within the lease duration, Jobs adopted by label, no duplicate Job, no lost event | K1 | Not run |
| AT-20 | Node failure | Drain or kill the exec node. Expected: the pod gets `DisruptionTarget`; `podFailurePolicy` fails the Job (`FailJob`); the controller classifies it as environmental and records `env_retry`; a new dispatch (`-d<n+1>`, new uid) runs in the same attempt; side effects stay idempotent; the evidence of the failed dispatch is kept | K2 | Not run |
| AT-21 | Network interruption and rate limits | Fault proxy in front of GitHub, Linear and the LLM. Expected: backoff, no duplicate outbox side effects (dedup keys) | K1 | Not run |
| AT-22 | Bootstrap step 10 | Simulated worker failure recovered, with evidence | K1 | Not run |
| AT-23 | Concurrency when safe | The amendment's mix runs together: 2 backend Mercury, 1 DB Jupiter-dummy, 1 test Mercury, 1 review Jupiter-dummy. Quotas and fair share are respected; ownership conflicts are refused | K1/K2 | Not run |
| AT-24 | Budgets | A project exceeding its daily token or cost budget gets no new admissions; other projects continue | K1 | Not run |
| AT-25 | New projects by configuration | A dummy project is onboarded with a project config and the `devplat-project` chart only. No controller change | K1 | Schema-level **run** (§2); K1 not run |
| AT-26 | Works on local and cloud | Profiles from `25-…`: kind or k3d on Linux, on macOS (Docker Desktop or OrbStack) and on Windows (WSL2). One managed cloud | K1, cloud | Not run |
| AT-27 | amd64 and arm64 | Every published image is built and smoke-tested on both architectures, or is recorded as single-architecture | CI | Not run |
| AT-28 | No macOS dependency in the core | The core runs on Linux nodes only. The Mercury T4 lane is the only macOS element, external and optional | K1 | Design-reviewed only |
| AT-29 | Evidence survives failure | After AT-18…AT-20 every attempt's logs, result and bundle are in the artifact store with matching sha256 | K1 | Not run |
| AT-30 | Human approval preserved end to end | AT-11 plus the ruleset check (`integrations/github.md` ruleset JSON) on the platform and Mercury repositories | GH | Not run (DOD-02) |

## 2. Executed in the authoring environment (2026-10-17, commit 8b17bf2 and later)

**Environment.** Linux x86_64 container. Python 3.13, jsonschema 4.26.0, PyYAML 6.0.1. PostgreSQL 16.15 server binaries were preinstalled; tests start a private instance as `nobody`. Go 1.24.7 was preinstalled. Two tools were built from source into the scratchpad only, never installed on a host: Helm v3.17.3 and kubeconform v0.6.7, both via proxy.golang.org with checksums verified against sum.golang.org. **No Kubernetes cluster was used.**

**One command runs everything:**

`GO=… HELM=… KUBECONFORM=… platform/tools/validate_all.sh` → **ALL CHECKS PASSED**

| Check | Covers | Result |
|---|---|---|
| `tools/devorch/test_devorch.py` | v1 regression, the specification for AT-07 | 30/30 |
| `tools/devorch/gen_examples.py --check` | v1 examples unchanged | OK |
| `platform/controller/test_jobspec.py` | AT-09, AT-04 naming. Output **equals** the doc 16 §4.1 example; strict v1.33 valid for all 13 profiles; negative strictness; hardening; digest pinning; per-dispatch names | 11/11 |
| `platform/tools/validate_projects.py` (+ `--self-test`) | AT-25 at schema level. Mercury valid (`onboarding`, 0 unresolved security-core fields); Jupiter valid (`draft`, 53 unresolved); the self-test (50/50 checks, 2026-10-23) rejected | pass |
| Execution profiles and task contract v2 schemas | 13 profiles; converted v1 example | valid |
| `platform/tools/validate_k8s.py platform/deploy/base` | AT-02 | 121/121 strict-valid |
| `platform/tools/admission/run.sh` | AT-16 offline. 93 CEL expressions compile in the Kubernetes v0.33 CEL environment; 61 admission cases match expectations, including doc 16's example Job and pod | 0 mismatches |
| `platform/db/test_schema.py` | AT-03, AT-04 (DB), AT-05, AT-06 (DB). Real PostgreSQL 16 | 21/21, stable over 6 consecutive runs after the dispatch race fix (R6-local) |
| `helm lint` + `helm template \| kubeconform -strict` | Chart validity | devplat 33/33 valid; devplat-project 21/21 valid; rendering without digests refused |

**What these results do not show:**
- runtime behaviour on a cluster (NetworkPolicy enforcement, gVisor, admission with typed objects and defaulting, Job lifecycle, recovery);
- GitHub behaviour (ruleset, App permissions);
- any cross-architecture image.

Those are AT-08…AT-30 at levels K1, K2 and GH. All of them are **not run**.

## 3. Rules

1. A capability is reported as **implemented and tested** only when its AT has passed at the stated level, with evidence stored.
2. K1 and K2 tests need a cluster the operator has approved (DOD-15). They are never run against a cluster that hosts anything else.
3. Security tests (AT-13…AT-17) run from inside agent pods, using the same image and service account as real runs.
