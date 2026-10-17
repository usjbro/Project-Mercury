# ADR-027 — Container image build approach for the development platform

| | |
|---|---|
| Status | **Proposed** (requires operator approval; Architecture Amendment 001) |
| Date | 2026-10-17 |
| Owner | Lead Architect (devplat, development platform) |
| Related | ADR-021 (development orchestration), ADR-023 (topology), ADR-025 (security); `development-orchestration/22-build-test-architecture.md` §9, `23-ci-cd-integration.md` §5 |
| Scope | **Development platform (devplat) only.** No change to MERCURY's production design: MERCURY ships as a macOS daemon, and its release process (`10-…` §3) is unchanged |

## Context

The amendment requires Kubernetes-based build and test workflows without a Docker socket. Facts checked on 2026-10-17:
- Kaniko's upstream repository was archived on 2025-06-03; a Chainguard fork is maintenance-only.
- Rootless BuildKit on Kubernetes needs seccomp/AppArmor relaxations (`Unconfined` in the upstream example, or Localhost profiles) and user namespaces on nodes. It is never privileged.
- No documentation was found for BuildKit inside gVisor.
- Mercury needs no container release image. Jupiter is unresolved.

## Decision

1. **No Docker socket and no privileged builders**, anywhere in the platform. Admission denies hostPath, privileged containers and added capabilities in build namespaces.
2. **Release and platform images are built by repository CI** (GitHub Actions, CI of record):
   - BuildKit/buildx, native per architecture where available;
   - scanned and given an SBOM;
   - signed with cosign keyless;
   - consumed by digest.
3. **In-cluster builds** (test images only, when a project configuration declares them):
   - **rootless BuildKit**, one Job per build in `proj-<P>-build`, on nodes without gVisor (dedicated `build` pool where available);
   - the builder image is allowlisted by digest;
   - no API token, no Secrets;
   - egress only through the registry proxy;
   - output is an OCI layout plus attestations into the project's bucket.

   As in the canonical security model (doc 18 §10.1, `platform/deploy/base`), build namespaces carry PSA `enforce: privileged` (audit/warn `restricted`). The real controls are VAPs: `devplat-build-exceptions` permits the BuildKit exceptions (Unconfined or Localhost seccomp/AppArmor, `allowPrivilegeEscalation` for `newuidmap`) **only** for the container `buildkitd` with the pinned image, and `devplat-pod-hardening` forbids every privileged feature. The project chart adds a per-project builder allowlist. Hardening targets: user namespaces (`hostUsers: false`), then Localhost profiles, which would allow PSA `baseline`.
4. **Phase 1 runs no in-cluster builds.** Build namespaces exist with an empty builder allowlist.
5. **Multi-arch.** An architecture is claimed for an image digest only after a smoke test on a native node of that architecture (`verified_platforms`). QEMU binfmt registration is never done in the shared cluster.
6. **Kaniko** is an alternative only (a maintained fork, built from source, pinned). Buildah/Podman rootless is the second choice if BuildKit proves infeasible on the chosen node OS.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Docker socket / DinD | Host root or a privileged pod: violates the amendment and the isolation model |
| Kaniko as default | Upstream archived (2025-06); the fork is maintenance-only, with images limited to its vendor's customers; runs as root in the container |
| BuildKit rootful | Privileged |
| BuildKit under gVisor as default | Unverified; capabilities and network requirements unknown. Kept as a spike |
| All builds in cloud build services | Fine for release images (adopted through CI); unsuitable for per-task test images (latency; agent-written Dockerfiles in a credentialed context) |

## Consequences

- **Positive:** no build path needs node-level privileges; release images have provenance independent of the platform; Mercury is unaffected.
- **Negative:**
  - in-cluster builds need node preparation (user namespaces, Localhost profiles) and a spike before use;
  - importing built images to kubelet needs an in-cluster registry or importer (documented only).
- **Status of the controls:** Documented only. The chart allowlist and policy are Implemented (untested): rendered offline, never applied.

## Verification required before acceptance

1. Spike S-B1: rootless BuildKit with Localhost profiles under PSA `baseline` on the chosen node OS. Separately, BuildKit under gVisor.
2. Probe N11 (`22-…` §7) passes on the target cluster.
3. One multi-arch platform image is verified natively on amd64 and arm64.
