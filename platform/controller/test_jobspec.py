#!/usr/bin/env python3
"""Tests for jobspec.build_job.

1. The output equals the vendored example Job platform/controller/testdata/job-example.yaml, and that fixture equals
   the example in 16-agent-execution-and-job-lifecycle.md §4.1 when the doc is present (doc and code cannot drift;
   platform tests never depend on files outside platform/, R6 A-04).
2. The output is valid against the strict Kubernetes v1.33 Job schema, which rejects unknown fields.
3. Every security rule a Job spec can carry holds.

    python3 platform/controller/test_jobspec.py -v
Needs network once to fetch the Job schema into the cache (see platform/tools/validate_k8s.py).
"""
import copy, os, re, sys, unittest

import yaml
from jsonschema import Draft7Validator

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "platform", "tools"))
import jobspec as J  # noqa: E402
import validate_k8s as V  # noqa: E402

FIXTURE = os.path.join(HERE, "testdata", "job-example.yaml")
# Optional doc-sync check: the design doc lives outside platform/ (and after the ADR-030 split, in another repository).
DOC = os.environ.get("DEVPLAT_DOC16", os.path.join(ROOT, "docs/mercury/development-orchestration/16-agent-execution-and-job-lifecycle.md"))
PROFILES = yaml.safe_load(open(os.path.join(ROOT, "platform/agents/execution-profiles.yaml")))
PROFILE = next(p for p in PROFILES["profiles"] if p["role"] == "mdev-backend-engineer")
PROJECT = {"project_id": "mercury", "execution_target": {"cluster_ref": "default", "namespace_prefix": "proj-mercury"}}
CONTRACT = {"task_id": "DT-0001", "kind": "implementation", "contract_version": 1,
            "base_commit": "a39b1550333e5e5b20003720a65afa27bad32f6c", "budget": {"max_wall_minutes": 30, "max_turns": 10}}
RUN = {"attempt": 2,
       "contract_core_sha256": "4b1e0c3a9d7f25e86c1b0a4f3e9d2c7b6a5f4e3d2c1b0a9f8e7d6c5b4a392817",
       "role_definition_sha256": "0d3c5e7a9b1f2e4d6c8a0b2d4f6e8a0c2e4b6d8f0a2c4e6b8d0f2a4c6e8b0d2f",
       "fetch_image": "registry.devplat.internal/devplat/fetch@sha256:" + "1" * 64,
       "agent_image": "registry.devplat.internal/devplat/agent-node24@sha256:" + "2" * 64,
       "role_configmap": "devplat-roles-mercury-0d3c5e7a", "dns_ip": "10.96.100.53"}


def job(contract=None, profile=None, **run):
    return J.build_job(contract or CONTRACT, PROJECT, profile or PROFILE, PROFILES["defaults"], dict(RUN, **run))


def fixture_text():
    return open(FIXTURE).read().split("\n", 2)[2]          # drop the two-line vendoring header


def doc_block():
    text = open(DOC).read()
    sec = text[text.index("### 4.1"):text.index("### 4.2")]
    return re.search(r"```yaml\n(.*?)```", sec, re.S).group(1)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sch, err = V.load_schema("v1.33.0", "job-batch-v1")
        if sch is None:
            raise unittest.SkipTest(f"Job schema unavailable: {err}")
        cls.validator = Draft7Validator(sch)

    def test_equals_vendored_example(self):
        self.assertEqual(job(), yaml.safe_load(fixture_text()))

    def test_vendored_example_equals_doc(self):
        if not os.path.exists(DOC):
            self.skipTest("design doc not present (split repository); fixture is authoritative for the test")
        self.assertEqual(fixture_text(), doc_block())

    def test_gateways_and_registry_proxy(self):
        env = {e["name"]: e.get("value") for e in job()["spec"]["template"]["spec"]["containers"][0]["env"]}
        # R6 D12: the project is bound to the per-Job token, never selected by the URL path
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "http://devplat-model-gateway.devplat-system.svc:8080")
        # R6 D10: uploads only through the artifact gateway; no object-store endpoint or presigned URL in the pod spec
        self.assertEqual(env["DEVPLAT_ARTIFACT_GATEWAY"], "http://devplat-artifact-gateway.devplat-system.svc:8082")
        self.assertFalse([k for k in env if k.startswith(("AWS_", "S3_", "MINIO"))])
        # R6 D14: one read-only registry proxy per project
        self.assertEqual(env["NPM_CONFIG_REGISTRY"], "http://devplat-registry-proxy-mercury.devplat-system.svc:4873/")
        ro = next(p for p in PROFILES["profiles"] if p["network_class"] == "model-only")
        env2 = {e["name"] for e in job(profile=ro)["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertNotIn("NPM_CONFIG_REGISTRY", env2)

    def test_strict_schema_valid(self):
        errs = list(self.validator.iter_errors(job()))
        self.assertEqual(errs, [], [e.message for e in errs[:3]])

    def test_strict_schema_rejects_unknown_and_mistyped_fields(self):
        # guards against a vacuous "valid": the schema must catch typos and wrong types
        j = job(); j["spec"]["template"]["spec"]["automountServiceAcountToken"] = False
        self.assertTrue(list(self.validator.iter_errors(j)))
        j = job(); j["spec"]["backoffLimit"] = "0"
        self.assertTrue(list(self.validator.iter_errors(j)))

    def test_every_profile_builds_a_valid_job(self):
        for p in PROFILES["profiles"]:
            errs = list(self.validator.iter_errors(job(profile=p)))
            self.assertEqual(errs, [], (p["role"], [e.message for e in errs[:2]]))

    def test_name_deterministic_and_dns_label(self):
        self.assertEqual(job()["metadata"]["name"], job()["metadata"]["name"])
        self.assertEqual(job()["metadata"]["name"], "dp-mercury-dt-0001-a2-backend-engineer-d1")
        long = J.job_name("a-very-long-project-identifier-x", "DT-0001-r1-and-a-long-suffix-here", 12,
                          "mdev-platform-integration-engineer")
        self.assertLessEqual(len(long + "-contract"), 63)
        self.assertRegex(long, r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
        self.assertNotEqual(J.job_name("p", "DT-0001", 1, "verifier"), J.job_name("p", "DT-0001", 2, "verifier"))

    def test_roles_of_one_attempt_get_distinct_names_and_keys(self):
        # job_runs is UNIQUE (project, task, attempt, role, dispatch_no) and idempotency_key is globally UNIQUE: the
        # assigned role's Job and the verifier's Job of the same attempt and dispatch must not collide (R6 RA-1)
        core = RUN["contract_core_sha256"]
        roles = [p["role"] for p in PROFILES["profiles"]] + ["verifier"]
        self.assertEqual(len({J.job_name("mercury", "DT-0001", 2, r) for r in roles}), len(roles))
        self.assertEqual(len({J.idempotency_key("mercury", "DT-0001", core, 2, r) for r in roles}), len(roles))
        long = [J.job_name("a-very-long-project-identifier-x", "DT-0001-r1-and-a-long-suffix-here", 12, r) for r in roles]
        self.assertEqual(len(set(long)), len(roles))

    def test_pod_has_no_credentials_or_host_access(self):
        spec = job()["spec"]["template"]["spec"]
        self.assertFalse(spec["automountServiceAccountToken"])
        self.assertEqual(spec["serviceAccountName"], "mercury-agent")
        self.assertEqual(spec["dnsPolicy"], "None")             # never kube-dns (DNS exfiltration)
        self.assertEqual(spec["dnsConfig"]["nameservers"], ["10.96.100.53"])
        for k in ("hostNetwork", "hostPID", "hostIPC"):
            self.assertFalse(spec.get(k, False))
        for v in spec["volumes"]:
            self.assertNotIn("hostPath", v)
        envs = [e for c in spec["containers"] + spec["initContainers"] for e in c.get("env", [])]
        # the only credential is the per-Job gateway token, read from the run's own Secret; never an API key
        self.assertFalse([e for e in envs if "API_KEY" in e["name"] or "GITHUB" in e["name"]])
        tok = [e for e in envs if e["name"] == "ANTHROPIC_AUTH_TOKEN"][0]
        self.assertEqual(tok["valueFrom"]["secretKeyRef"]["name"], "dp-mercury-dt-0001-a2-backend-engineer-d1-io")

    def test_container_hardening(self):
        j = job()
        spec = j["spec"]["template"]["spec"]
        self.assertTrue(spec["securityContext"]["runAsNonRoot"])
        self.assertEqual(spec["securityContext"]["seccompProfile"]["type"], "RuntimeDefault")
        for c in spec["containers"] + spec["initContainers"]:
            s = c["securityContext"]
            self.assertTrue(s["readOnlyRootFilesystem"])
            self.assertFalse(s["allowPrivilegeEscalation"])
            self.assertEqual(s["capabilities"]["drop"], ["ALL"])
            self.assertIn("limits", c["resources"])

    def test_exec_pool_runtime_retry_and_deadline(self):
        j = job()
        spec = j["spec"]["template"]["spec"]
        self.assertEqual(spec["runtimeClassName"], "gvisor")
        self.assertEqual(spec["nodeSelector"], {"devplat.io/pool": "exec"})
        self.assertEqual(j["spec"]["backoffLimit"], 0)
        self.assertTrue(j["spec"]["suspend"])
        self.assertEqual(j["spec"]["activeDeadlineSeconds"], 30 * 60 + PROFILES["defaults"]["setup_grace_seconds"])
        p = dict(PROFILE, runtime_class="default")
        self.assertNotIn("runtimeClassName", job(profile=p)["spec"]["template"]["spec"])

    def test_images_must_be_digest_pinned(self):
        with self.assertRaises(ValueError):
            job(agent_image="ghcr.io/owner/devplat-agent:latest")
        with self.assertRaises(ValueError):
            job(fetch_image="ghcr.io/owner/devplat-fetch:1.0")

    def test_idempotency_key_binds_task_contract_core_and_attempt(self):
        k = lambda **r: job(**r)["metadata"]["labels"]["devplat.io/idempotency-key"]
        self.assertEqual(len({k(), k(contract_core_sha256="b" * 64), k(attempt=3), k(dispatch_no=2)}), 4)

    def test_env_retry_gets_a_new_job_not_the_failed_one(self):
        # R6/C finding: an environmental retry within the same attempt must not adopt the failed Job
        self.assertNotEqual(job()["metadata"]["name"], job(dispatch_no=2)["metadata"]["name"])


if __name__ == "__main__":
    unittest.main()
