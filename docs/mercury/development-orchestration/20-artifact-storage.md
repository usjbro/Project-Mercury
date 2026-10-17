# 20 — Artifact Storage (devplat)

Status: **Proposed — Documented only**, except the DB side (`artifacts` table, `register_artifact()`, content-address, bucket and size constraints, immutability trigger), which is **Implemented and tested** (`19-…` §13). No object store has been deployed or tested here. **The store product is an operator decision (DOD, see §11).** Decision record: ADR-026 (Proposed).
Reuses / supersedes: **supersedes for the platform** `07-handoff-and-recovery.md` §1 rule 4 storage locations (`$DEVORCH_EVIDENCE`, `$DEVORCH_HOME/evidence/…`, `import-evidence`, `MANIFEST.json`) and `04-contracts.md` §4 "`evidence_dir` outside `$DEVORCH_HOME`". **Keeps:** results are files and never gates by themselves; evidence is read once, hashed, and the hashed copy is what the record trusts (R5 N-04); every attempt keeps its own evidence; prior evidence is never deleted.

## 1. Store options

| Mode | Store | Use | Status |
|---|---|---|---|
| **External S3-compatible endpoint** (chart default and only chart-managed mode) | Cloud S3; GCS via the XML/S3 interoperability API; Cloudflare R2; or any self-hosted S3-compatible store the operator runs and points devplat at | Servers, multi-node, cloud (P2–P6 in `25-…`) | Documented only |
| **Filesystem / PVC** | A `ReadWriteOnce` PVC (or host directory) mounted only by the controller, with the same key layout | Single workstation (Option A, **reduced assurance**) | Documented only |
| MinIO (self-hosted, operator-installed) | **Option only, with a caveat.** The community edition went source-only in late 2025 and its repository was archived on 2026-04-25 (sources in `22-…`, `24-…`, ADR-027). There are no maintained community binaries or images, so the operator would build and patch it or buy a subscription. The devplat chart does **not** install it | Only if the operator accepts that maintenance burden | Not recommended as a default |

The controller talks to every mode through one interface (`put`, `get`, `head`, `copy`, `presign_put`, `presign_get`, `delete`), so a mode is configuration, not code (`26-…`). Features that only some stores have (object lock, POST policies, quotas) are capability-probed at startup and reported on the dashboard. A missing control lowers the reported assurance and is never silently assumed.

## 2. Layout and content addressing

Bucket per project: `devplat-<project>` (configurable name, recorded in `projects.artifact_bucket`; it cannot change after creation). Platform buckets: `devplat-platform` (checkpoints, platform logs) and `devplat-pg-backup` (CNPG base backups and WAL, separate credentials).

| Prefix | Content | Writer | Mutability |
|---|---|---|---|
| `runs/<job-uid>/` | Raw uploads of one Job: `result.json`, `out.bundle` (git bundle), `logs/agent.log.zst`, `progress.json` (heartbeat), test reports | The Job, through presigned URLs only | Scratch; deleted 7 days after collection |
| `sha256/<hex>` | **Immutable evidence**: every object a record cites, stored under its own SHA-256 | Controller (copy after verification) | Immutable (object lock where available, §5) |
| `bundles/<task>/<seq>-<gate>.json` | Evidence-bundle manifest per gate (§6). The manifest itself is also stored at `sha256/<hex>` | Controller | Immutable |
| `checkpoints/<checkpoint_id>.json` (platform bucket) | Signed chain checkpoints (`19-…` §8) | Controller | Immutable, compliance retention |

Rules:
1. The DB enforces `object_key = 'sha256/' ‖ sha256`, `UNIQUE(project_id, sha256)`, and that the bucket is the project's bucket (tested).
2. The controller computes the hash itself while streaming the object from `runs/…` to `sha256/…`. A client-supplied hash is never trusted. If an object already exists at that hash, it only extends retention.
3. Event evidence cites `{kind, ref: "sha256/<hex>", sha256}`. `record_event()` refuses file evidence that is not a registered artifact of the task's project (tested).

## 3. Upload path (agents)

```mermaid
sequenceDiagram
    participant C as devplat-controller
    participant K as Kubernetes API
    participant J as Job pod (agent)
    participant S as Object store
    participant G as gitbroker
    C->>K: create Job (suspended), learn job uid
    C->>C: presign PUT for runs/UID/{result.json,out.bundle,logs/agent.log.zst,progress.json} (TTL = activeDeadlineSeconds + 10 min)
    C->>K: Secret JOB-io (ownerRef = Job) with URLs; unsuspend
    J->>S: PUT each object (no credentials, only the URLs)
    C->>S: HEAD / GET runs/UID/* (size check first)
    C->>G: validate out.bundle (port of result_errors)
    C->>S: copy verified objects to sha256/HEX, register_artifact()
    C->>C: record_event(implementation_completed / result_accepted, evidence = sha256 refs)
```

1. **Scoped per Job.** URLs are presigned for exact keys under `runs/<job-uid>/`. An S3 presigned PUT covers one key, so a Job cannot write elsewhere, list, read or delete. The Job never holds store credentials.
2. **Size.** A presigned PUT cannot bound the body size. Where the store supports POST policies with `content-length-range`, the controller uses them. Otherwise it HEADs every object before reading it, rejects oversize objects (`attempt_failed`, reason `output_too_large`) and deletes them. A per-Job total of 2.5 GiB is enforced the same way. Whether each target store supports POST policies is **Unverified**.
3. **TTL.** URLs expire 10 minutes after the Job deadline, and a re-dispatch gets new URLs under a new uid.
4. **Network.** Pods can reach only the store endpoint (and model-gateway, `18-…`). For an external store this is an egress allow by FQDN or CIDR, which needs a CNI that supports FQDN policies or an egress proxy (`18-…`).

## 4. Downloads

- Operators: `devplat-api` checks the operator's project authorization and returns a presigned GET (TTL 5 min) for `sha256/…` objects.
- gitbroker: reads `runs/<uid>/out.bundle` through a presigned GET minted by the controller, or with its own read-only credential on the `runs/` prefix.
- Agents never read artifacts. A correction attempt's inputs (prior result, review findings) are copied into the Job's contract ConfigMap or fetched through gitbroker's one-time URL, as in `07-…` §1 rule 5.

## 5. Immutability, object lock and retention

| Class | Applies to | Retention | Lock |
|---|---|---|---|
| `ephemeral` | `runs/<uid>/*` raw uploads | 7 days after collection (lifecycle rule) | None |
| `standard` | Logs (`log`, 90 d), `test_log` (365 d), `git_bundle` (365 d) | Per `artifact_kinds.default_retention_days` | Governance mode where available |
| `evidence` | Everything cited by an event (`result`, `review`, `evidence_bundle`, `sbom`, `scan_report`, `operator_upload`, `checkpoint`): 3650 d | 10 years (operator-adjustable) | **Compliance mode** where available |
| Legal hold | Any artifact on operator request | Until released | Object legal hold |

- S3 Object Lock must be enabled at bucket creation. GCS uses bucket retention policies or object retention. R2 bucket locks and self-hosted stores vary. Support per store is **Unverified** and is probed at startup. Without a lock, immutability rests on IAM (no delete permission on `sha256/` for any identity except an operator break-glass) plus the DB's `sha256` check on read. This mode is reported as **reduced assurance**.
- The DB never shortens retention (trigger, tested). `expire_artifacts()` removes rows only when retention has ended, there is no legal hold, and no event cites the hash. The controller then deletes the object, or a store lifecycle rule does.
- Filesystem mode: files are created read-only (0444) by the controller uid. The host administrator can still alter them. **Reduced assurance**, as for all of Option A.

## 6. Evidence bundles per gate

At each gate event, the controller writes `bundles/<task>/<seq>-<gate>.json` after the event commits:

```json
{"schema": "devplat.evidence_bundle.v1", "project": "mercury", "task": "DT-0001", "seq": 6, "gate": "G2",
 "event_hash": "<task_events.hash>", "head_commit": "<sha>", "contract_core_sha256": "<sha>",
 "items": [{"kind": "test_run", "sha256": "<hex>", "size": 18234, "media_type": "application/zstd"}],
 "job": {"name": "dp-mercury-dt-0001-a2", "uid": "<uid>", "image": "<digest>"}}
```

The bundle names the event hash, and the event cannot name the bundle (it does not exist yet), so the hourly checkpoint (`19-…` §8) is what ties bundles and chain together. The G6/G7 bundles are attached to the draft PR description as links (`23-…`).

## 7. Artifact kinds and size limits

From the `artifact_kinds` table (enforced by `register_artifact()`, tested for `result`):

| Kind | Max size | Default retention | Notes |
|---|---|---|---|
| `result` | 1 MiB | 3650 d | `result.json` (`devorch.task_result.v1`-compatible) |
| `review` | 1 MiB | 3650 d | Review findings |
| `test_log` | 256 MiB | 365 d | Verifier re-run output, JUnit XML |
| `log` | 256 MiB | 90 d | Agent transcript or log (zstd). Pod logs are fetched by the controller from the Kubernetes API (`kube_pod_log`) |
| `git_bundle` | 2 GiB | 365 d | Agent output bundle after gitbroker validation |
| `sbom` | 64 MiB | 3650 d | SPDX or CycloneDX per image digest (`22-…`) |
| `scan_report` | 64 MiB | 3650 d | Vulnerability or secret scan per image or head |
| `evidence_bundle` | 2 GiB | 3650 d | Gate manifests (normally small) |
| `checkpoint` | 16 MiB | 3650 d | Chain checkpoints |
| `operator_upload` | 256 MiB | 3650 d | Mac-lane (T4) evidence uploaded by the operator through the api |
| `other` | 64 MiB | 30 d | — |

Logs may contain prompt text and model output. Agents hold no long-lived secrets (`18-…`). The per-Job gateway token expires with the Job and is still scrubbed from logs by the controller before the copy to `sha256/` (a pattern scrub, best effort).

## 8. Encryption

| | External S3 | Filesystem |
|---|---|---|
| In transit | TLS only (`https` endpoint required; presigned URLs are https) | Not applicable (local mount) |
| At rest | Provider SSE (SSE-S3 or SSE-KMS with a per-installation key). The key policy denies anyone outside the controller role, gitbroker and the operator | Host disk encryption (FileVault / LUKS); operator responsibility |
| Integrity | SHA-256 content address re-checked on every read by the controller (`GET` → hash → compare) | Same |

## 9. Access matrix

| Identity | `runs/<own uid>/` | `runs/*` | `sha256/*` | `bundles/` | `checkpoints/` | Delete |
|---|---|---|---|---|---|---|
| Agent / planner / verifier Job | PUT through presigned URLs only | — | — | — | — | — |
| devplat-controller | R | R, W (copy), delete after collection | W (create), R | W, R | W, R | `runs/*` only; `sha256/*` only through `expire_artifacts()` after retention |
| devplat-gitbroker | R (bundle) | R (bundle only) | — | — | — | — |
| devplat-api | — | — | Presign GET for authorized operators; W `operator_upload` objects | R | R | — |
| devplat-model-gateway | — | — | — | — | — | — |
| CNPG backup | — | — | — | — | — | Own bucket `devplat-pg-backup` only |
| Operator (break-glass) | Through provider console or IAM; logged | | | | | Legal hold, retention changes |

Credentials: workload identity (IRSA / GKE Workload Identity / Azure Workload Identity) where available; otherwise one static key pair per component in a Kubernetes Secret, scoped by bucket policy to the prefixes above. **Configured** in no environment yet.

## 10. Not verified

1. Object-lock, retention and legal-hold support and semantics on each target store (S3, GCS interoperability, R2, any self-hosted store).
2. Presigned POST with `content-length-range` on those stores, and presigned-URL behaviour through the cluster egress path.
3. FQDN-based egress policy to an external endpoint in each CNI (`18-…`).
4. Throughput and cost for multi-GiB git bundles. No measurement was made.
5. Filesystem-mode behaviour on a workstation PVC (hostPath / local-path provisioner).
6. Log scrubbing completeness.
7. MinIO's status is reported by another drafter (`22-…`/`24-…`). It was not re-checked by this author.

## 11. Operator decisions

| Decision | Options | Recommendation |
|---|---|---|
| Object store for server and cloud profiles | Cloud S3 / GCS (S3 interop) / R2 / a self-hosted S3-compatible store of the operator's choice | Use the cloud provider's native store in P6. For on-premises, choose a maintained S3-compatible store and verify object lock before adoption |
| Evidence retention period | 3650 d default | Keep until Mercury's own retention policy is decided |
| Workstation mode | Filesystem/PVC (reduced assurance) or an external bucket | External bucket if the workstation has network access; otherwise filesystem |
