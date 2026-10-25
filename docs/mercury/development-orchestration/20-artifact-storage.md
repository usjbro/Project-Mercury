# 20 — Artifact Storage (devplat)

Status: **Proposed (R6 fix round applied).** This document **owns the artifact layout** (R6 D11); docs 16, 18, 24, the validator and the charts follow it. DB side (`artifacts`, `run_uploads`, `run_object_caps`, `register_artifact()`, `authorize_upload()`, `complete_upload()`, bucket / content-address / size / alias constraints, immutability trigger): **Implemented and tested** (`19-…` §13). `devplat-artifact-gateway`, gitbroker-fetch and the object store: **Designed, unverified** (no code, nothing deployed). The store product is an **operator decision** (§11). Decision record: ADR-026 (Proposed).
Reuses / supersedes: **supersedes for the platform** `07-handoff-and-recovery.md` §1 rule 4 storage locations (`$DEVORCH_EVIDENCE`, `$DEVORCH_HOME/evidence/…`, `import-evidence`, `MANIFEST.json`) and `04-contracts.md` §4 "`evidence_dir` outside `$DEVORCH_HOME`". **Keeps:** results are files and never gates by themselves; evidence is read once, hashed, and the hashed copy is what the record trusts (R5 N-04); every attempt keeps its own evidence; prior evidence is never deleted.

## 1. Store options

| Mode | Store | Use | Status |
|---|---|---|---|
| **External S3-compatible endpoint** (chart default and only chart-managed mode) | Cloud S3; GCS via the S3 interoperability API; Cloudflare R2; or a self-hosted S3-compatible store the operator runs | Servers, multi-node, cloud | Designed, unverified |
| **Filesystem / PVC** | `ReadWriteOnce` volume mounted only by the artifact-gateway and the controller, same key layout | Single workstation (Option A, **reduced assurance**) | Designed, unverified |
| MinIO (self-hosted, operator-installed) | **Option only, with a caveat:** the community edition went source-only in late 2025 and its repository was archived on 2026-04-25 (sources in `22-…`, `24-…`, ADR-027). The chart does not install it | Only if the operator accepts building and patching it | Not recommended as a default |

All platform components use one interface (`put`, `get`, `head`, `copy`, `presign_get`, `delete`); the mode is configuration. Optional store features (object lock, quotas) are probed at startup; a missing control lowers the reported assurance and is never assumed.

## 2. Layout (normative, R6 D11)

One bucket per project: **`devplat-<project>`** (enforced by DB constraint), plus **`devplat-platform`** (checkpoints, platform logs, PostgreSQL backups under their own prefix and credential).

| Prefix / object | Content | Written by | Cap | Mutability |
|---|---|---|---|---|
| `runs/<job-uid>/result.json` | Result (`devplat.task_result.v2`) | the Job, **through artifact-gateway only** | 1 MiB | Scratch, one-time per name |
| `runs/<job-uid>/result.bundle` | git bundle of the agent's commits | same | 256 MiB | same |
| `runs/<job-uid>/agent.stream.jsonl` | Claude Code stream (transcript) | same | 64 MiB | same |
| `runs/<job-uid>/runner.json` | Runner status, progress, usage | same | 64 MiB | same |
| `runs/<job-uid>/fetch.log` | Init-container fetch log | same | 64 MiB | same |
| — run total | | | **512 MiB** | |
| `src/<project>/<sha>.bundle` | Source bundle for a Job's fetch | gitbroker | — | Rebuildable cache |
| `sha256/<hex>` | **Immutable evidence**: every object an event cites, under its own SHA-256 | controller (copy after verification) | per kind (§7) | Immutable (§5) |
| `manifests/<task>/<attempt>/<role>-d<dispatch>.json`, `manifests/<task>/<attempt>/gate-G<n>.json` | Evidence manifest of one dispatch, or of one gate (§6); also stored as `sha256/<hex>` and recorded as `artifacts.alias_key` | controller | 16 MiB | Immutable |
| `checkpoints/<id>.json` (platform bucket) | Signed chain checkpoints (`19-…` §8) | controller | 16 MiB | Immutable |

The names are a closed list (`run_object_caps`): any other name is refused by `authorize_upload()` (tested). The per-object caps sum to 449 MiB, so the 512 MiB total is a backstop that the current list cannot reach.

## 3. Upload path — artifact-gateway is the only write path from pods (R6 D10)

Agent, planner, verifier, build and test pods **never reach the object store and never receive a store URL or credential**. Their NetworkPolicy allows the artifact-gateway Service (port **8082**) and nothing on the store (`18-…` §8–§9). There are **no presigned URLs in pods**; presigned URLs are used only between platform components (§4).

```mermaid
sequenceDiagram
    participant C as devplat-controller
    participant AG as devplat-artifact-gateway (:8082 uploads, :9444 admin)
    participant DB as PostgreSQL
    participant J as Job pod
    participant S as Object store
    C->>DB: dispatch_job(); set_job_tokens(job, sha256(gateway token), sha256(upload token), deadline)
    C->>AG: :9444 register run (job uid, project) — admin channel
    C->>J: Secret dp-JOB-io holds the upload token (ownerRef = Job); unsuspend
    J->>AG: :8082 PUT result.json (Bearer upload token, declared size)
    AG->>DB: authorize_upload(sha256(token), job uid, name, size)
    DB-->>AG: bucket devplat-P, key runs/UID/result.json — or refused (unknown name, cap, repeat, expired, foreign uid)
    AG->>S: streams the body with ITS OWN credential (write runs/ only), counts bytes, hashes
    AG->>DB: complete_upload(..., sha256, size)  (size must not exceed the declared size)
    C->>S: read runs/UID/*, re-hash, gitbroker validates result.bundle
    C->>S: copy verified objects to sha256/HEX; register_artifact()
    C->>DB: record_event(... evidence = sha256 refs, payload.result = checked summary)
```

Rules:
1. **Token.** One per Job, minted by the controller, stored in the DB only as a SHA-256 hash, bound to the Job's uid and project, valid until the Job deadline + 15 min (D11). The decision is made in PostgreSQL by `authorize_upload()`, so it survives gateway restarts and cannot be widened by the gateway's in-memory state.
2. **One-time per name.** A second upload of the same name for the same run is refused (tested).
3. **Caps.** Declared size ≤ the name's cap and run total ≤ 512 MiB before any byte is accepted; the gateway aborts the stream if more bytes arrive than declared, and `complete_upload()` refuses a stored size above the declaration.
4. **Scope.** The gateway's own store credential (Secret `devplat-artifacts-artifact-gateway`, `18-…` §8.1) may write only under `runs/`. It cannot read evidence, write `sha256/` or delete.
5. **Shared-service risk.** The gateway serves every project; a vulnerability in it crosses projects (`18-…` K-08). It holds no GitHub, LLM or DB-owner credential.

## 4. Downloads (platform components only)

- Operators: `devplat-api` checks the operator's project authorization and returns a presigned GET (TTL 5 min) for a `sha256/…` or `manifests/…` object. The URL goes to the operator's browser, never to a pod.
- gitbroker: reads `runs/<uid>/result.bundle` with its own read credential for validation in a quarantine repository; writes `src/<project>/<sha>.bundle`.
- gitbroker-fetch: reads `src/` with its own credential and serves one bundle once to the Job's init container (`18-…` §8.2).
- Agents never read artifacts. Correction inputs (prior result, findings) go into the contract ConfigMap or the fetch bundle.

## 5. Immutability, object lock and retention

| Class | Applies to | Retention | Lock |
|---|---|---|---|
| `ephemeral` | `runs/<uid>/*` | 7 days after collection (lifecycle rule) | None |
| `standard` | `log` (90 d), `test_report` (365 d), `result_bundle` (365 d) | `artifact_kinds.default_retention_days` | Governance mode where available |
| `evidence` | Everything an event cites (`result`, `evidence_manifest`, `sbom`, `scan_report`, `operator_upload`, `checkpoint`): 3650 d | 10 years (operator-adjustable) | **Compliance mode** where available |
| Legal hold | Any artifact on operator request | Until released | Object legal hold |

- Object lock support per store is **Unverified** (S3 needs it at bucket creation; GCS retention policies; R2 bucket locks; self-hosted stores vary). Without a lock, immutability rests on credentials (only the controller writes `sha256/`, nobody but an operator break-glass deletes) plus the DB's hash check on read — **reduced assurance**.
- The DB never shortens retention and refuses deletion of retained rows (trigger, tested); `expire_artifacts()` deletes only rows past retention, without legal hold, that no event cites.
- Filesystem mode: files 0444 owned by the gateway/controller uid; the host administrator can still alter them.

## 6. Evidence manifests

After each dispatch is collected the controller writes `manifests/<task>/<attempt>/<role>-d<dispatch>.json` (role as in the Job name, `jobspec.role_code()`), and at each gate `manifests/<task>/<attempt>/gate-G<n>.json`. The role is part of the key because one attempt runs Jobs of several roles (R6 re-check RC-1); the DB refuses a second object under one alias:

```json
{"schema": "devplat.evidence_manifest.v1", "project": "mercury", "task": "DT-0001", "attempt": 2, "role": "mdev-backend-engineer", "dispatch": 1,
 "job": {"name": "dp-mercury-dt-0001-a2-backend-engineer-d1", "uid": "<uid>", "image": "<digest>"},
 "config_version": "<project config_version>", "event": {"seq": 6, "hash": "<task_events.hash>", "gate": "G2"},
 "items": [{"name": "result.json", "kind": "result", "sha256": "<hex>", "size": 1834}]}
```

The manifest names the event hash, so the event cannot name the manifest; the hourly checkpoint (`19-…` §8) ties manifests and chain together. G6/G7 manifests are linked from the draft PR description (`23-…`).

## 7. Evidence kinds and size limits (`artifact_kinds`, enforced by `register_artifact()`)

| Kind | Max | Default retention | From |
|---|---|---|---|
| `result` | 1 MiB | 3650 d | `result.json` (also review results) |
| `result_bundle` | 256 MiB | 365 d | `result.bundle` after gitbroker validation |
| `log` | 64 MiB | 90 d | `agent.stream.jsonl`, `runner.json`, `fetch.log`, pod logs |
| `test_report` | 64 MiB | 365 d | Verifier output (G2), JUnit XML |
| `evidence_manifest` | 16 MiB | 3650 d | §6 |
| `sbom`, `scan_report` | 64 MiB | 3650 d | Build Jobs (`22-…`) |
| `checkpoint` | 16 MiB | 3650 d | `19-…` §8 |
| `operator_upload` | 256 MiB | 3650 d | Mac-lane (T4) evidence through devplat-api |

Logs may contain prompt text and model output. Pods hold no long-lived secret; the per-Job model-gateway and upload tokens expire with the Job and are still scrubbed (pattern scrub, best effort) before the copy to `sha256/`.

## 8. Encryption

| | External S3 | Filesystem |
|---|---|---|
| In transit | TLS (https endpoint required) between platform components and the store; pod → artifact-gateway inside the cluster (mTLS when cross-cluster, DOD-21) | Local mount |
| At rest | Provider SSE (SSE-S3 or SSE-KMS per installation) | Host disk encryption (operator) |
| Integrity | SHA-256 re-checked by the controller on every read | Same |

## 9. Access matrix

| Identity | `runs/<own uid>/` | `runs/*` | `src/` | `sha256/*`, `manifests/` | `checkpoints/` | Delete |
|---|---|---|---|---|---|---|
| Agent / planner / verifier / build / test pod | **write via artifact-gateway :8082 only, with the Job's token; no route to the store** | — | — (bundle served by gitbroker-fetch) | — | — | — |
| devplat-artifact-gateway | write (own credential) | write | — | — | — | — |
| devplat-controller | read | read; delete after collection | — | write (create), read | write, read | `runs/*`; `sha256/*` only via `expire_artifacts()` |
| devplat-gitbroker | read `result.bundle` | read bundles | write | — | — | — |
| devplat-gitbroker-fetch | — | — | read | — | — | — |
| devplat-api | — | — | — | presign GET for authorised operators; write `operator_upload` | read | — |
| devplat-model-gateway | — | — | — | — | — | — |
| Operator (break-glass) | via provider IAM, logged | | | | | legal hold, retention |

Credentials: one per component (`devplat-artifacts-<component>` Secrets, `18-…` §8.1) or workload identity, scoped by bucket policy to the prefixes above. **Configured** in no environment yet.

## 10. Not verified

1. artifact-gateway, gitbroker-fetch and the controller collection path (no code).
2. Object-lock, retention and legal-hold semantics per candidate store.
3. Bucket policies restricting each credential to its prefixes, per store.
4. Throughput and cost for 256 MiB bundles (not measured).
5. Filesystem mode on a workstation volume.
6. Log scrubbing completeness.
7. MinIO's status was reported by another drafter (`22-…`/`24-…`), not re-checked here.

## 11. Operator decisions

| Decision | Options | Recommendation |
|---|---|---|
| Object store per profile | Cloud S3 / GCS (S3 interop) / R2 / a self-hosted S3-compatible store | Provider-native in cloud; on-premises, a maintained store with verified object lock |
| Evidence retention | 3650 d default | Keep until Mercury's own retention policy is decided |
| Workstation mode | Filesystem/PVC (reduced assurance) or an external bucket | External bucket where the workstation has network access |
