#!/usr/bin/env python3
"""Tests for jobspec.build_job: strict Kubernetes v1.33 schema validity plus the security rules.

    python3 platform/controller/test_jobspec.py -v
Needs network once to fetch the Job schema into the cache (see platform/tools/validate_k8s.py).
"""
import copy, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import jobspec as J  # noqa: E402
import validate_k8s as V  # noqa: E402
from jsonschema import Draft7Validator  # noqa: E402

DIGEST = "ghcr.io/owner/devplat-agent-mercury@sha256:" + "0" * 64
CONTRACT = {"task_id": "DT-0001", "base_commit": "4cad0ef217ae938182454b3dba8b54570d36ba4a", "branch": "dev/merc-101-skeleton"}
PROJECT = {"project_id": "mercury", "execution_target": {"cluster_ref": "default", "namespace_prefix": "proj-mercury"}}
PROFILE = {"role": "backend-engineer", "agent_definition": "mdev-backend-engineer.md", "max_wall_minutes": 180,
           "workspace_size": "8Gi", "runtime_class": "gvisor",
           "resources": {"requests": {"cpu": "1", "memory": "2Gi"}, "limits": {"cpu": "2", "memory": "4Gi"}}}
RUN = {"attempt": 1, "contract_core_sha256": "a" * 64, "agent_image": DIGEST, "fetch_url_secret": "dp-run-fetch",
       "upload_url_secret": "dp-run-upload", "contract_configmap": "dp-contract-dt-0001-a1",
       "role_configmap": "devplat-role-backend-engineer"}


def job(**over):
    run = dict(RUN, **over.pop("run", {}))
    return J.build_job(over.get("contract", CONTRACT), over.get("project", PROJECT), over.get("profile", PROFILE), run)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sch, err = V.load_schema("v1.33.0", "job-batch-v1")
        if sch is None:
            raise unittest.SkipTest(f"Job schema unavailable: {err}")
        cls.validator = Draft7Validator(sch)

    def test_strict_schema_valid(self):
        errs = list(self.validator.iter_errors(job()))
        self.assertEqual(errs, [], [e.message for e in errs[:3]])

    def test_strict_schema_rejects_unknown_and_mistyped_fields(self):
        # guards against a vacuous "valid": the schema must catch typos and wrong types
        j = job(); j["spec"]["template"]["spec"]["automountServiceAcountToken"] = False
        self.assertTrue(list(self.validator.iter_errors(j)))
        j = job(); j["spec"]["backoffLimit"] = "0"
        self.assertTrue(list(self.validator.iter_errors(j)))

    def test_name_deterministic_and_dns_label(self):
        a, b = job()["metadata"]["name"], job()["metadata"]["name"]
        self.assertEqual(a, b)
        self.assertEqual(a, "dp-mercury-dt-0001-a1")
        long = J.job_name("a-very-long-project-identifier-x", "DT-0001-r1-and-a-long-suffix-here", 12)
        self.assertLessEqual(len(long), 63)
        self.assertRegex(long, r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
        self.assertNotEqual(J.job_name("p", "DT-0001", 1), J.job_name("p", "DT-0001", 2))

    def test_pod_has_no_credentials_or_host_access(self):
        spec = job()["spec"]["template"]["spec"]
        self.assertFalse(spec["automountServiceAccountToken"])
        for k in ("hostNetwork", "hostPID", "hostIPC"):
            self.assertFalse(spec[k])
        for v in spec["volumes"]:
            self.assertNotIn("hostPath", v)
        env = [e for c in spec["containers"] + spec["initContainers"] for e in c.get("env", [])]
        self.assertFalse([e for e in env if "TOKEN" in e["name"] or "API_KEY" in e["name"]])

    def test_container_hardening(self):
        spec = job()["spec"]["template"]["spec"]
        for c in spec["containers"] + spec["initContainers"]:
            s = c["securityContext"]
            self.assertTrue(s["runAsNonRoot"] and s["readOnlyRootFilesystem"])
            self.assertFalse(s["allowPrivilegeEscalation"] or s["privileged"])
            self.assertEqual(s["capabilities"]["drop"], ["ALL"])
            self.assertEqual(s["seccompProfile"]["type"], "RuntimeDefault")
            self.assertIn("limits", c["resources"])

    def test_exec_pool_runtime_and_retry_policy(self):
        j = job()
        spec = j["spec"]["template"]["spec"]
        self.assertEqual(spec["runtimeClassName"], "gvisor")
        self.assertEqual(spec["nodeSelector"], {"devplat.io/pool": "exec"})
        self.assertEqual(j["spec"]["backoffLimit"], 0)
        self.assertEqual(j["spec"]["activeDeadlineSeconds"], 180 * 60)
        self.assertEqual(j["metadata"]["namespace"], "proj-mercury-exec")
        p = dict(PROFILE, runtime_class="default")
        self.assertNotIn("runtimeClassName", job(profile=p)["spec"]["template"]["spec"])

    def test_image_must_be_digest_pinned(self):
        with self.assertRaises(ValueError):
            job(run={"agent_image": "ghcr.io/owner/devplat-agent:latest"})

    def test_idempotency_key_binds_contract_core_and_attempt(self):
        k1 = job()["metadata"]["annotations"]["devplat.io/idempotency-key"]
        k2 = job(run={"contract_core_sha256": "b" * 64})["metadata"]["annotations"]["devplat.io/idempotency-key"]
        k3 = job(run={"attempt": 2})["metadata"]["annotations"]["devplat.io/idempotency-key"]
        self.assertEqual(len({k1, k2, k3}), 3)


if __name__ == "__main__":
    unittest.main()
