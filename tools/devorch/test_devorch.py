#!/usr/bin/env python3
"""Regression tests for tools/devorch/devorch.py (development orchestration tooling).

Each test reproduces a finding from the Phase 14 reviews (R1 C-01/H-0x, R2 S-0x, R4 F0x) in scratch
git repositories and checks that devorch now refuses or detects it.  Run:
    python3 tools/devorch/test_devorch.py -v
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "devorch.py")
sys.path.insert(0, HERE)
import devorch as D  # noqa: E402


def sh(cmd, cwd, env=None, ok=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, shell=isinstance(cmd, str))
    if ok and r.returncode != 0:
        raise AssertionError(f"{cmd} failed: {r.stdout}{r.stderr}")
    return r


class Env:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="devorch-test-")
        self.home = os.path.join(self.root, "home")
        self.ev = os.path.join(self.root, "evidence")
        self.repo = os.path.join(self.root, "repo")
        for d in (self.home, self.ev, self.repo):
            os.makedirs(d)
        for d in ("tasks", "ledger"):
            os.makedirs(os.path.join(self.home, d))
        sh("git init -q -b main . && git config user.email t@t && git config user.name t", self.repo)
        os.makedirs(os.path.join(self.repo, "src/core"))
        open(os.path.join(self.repo, "README.md"), "w").write("x\n")
        sh("git add -A && git commit -qm base", self.repo)
        self.base = sh("git rev-parse HEAD", self.repo).stdout.strip()
        self.env = dict(os.environ, DEVORCH_HOME=self.home, DEVORCH_TEST_MODE="1", DEVORCH_EVIDENCE=self.ev)

    def run(self, *args, ok=None):
        r = subprocess.run([sys.executable, TOOL, *args], env=self.env, capture_output=True, text=True)
        if ok is True and r.returncode != 0:
            raise AssertionError(f"devorch {args} failed: {r.stdout}{r.stderr}")
        if ok is False and r.returncode == 0:
            raise AssertionError(f"devorch {args} unexpectedly succeeded: {r.stdout}")
        return r

    def contract(self, tid, kind="implementation", agent="mdev-backend-engineer", branch="dev/merc-101-x", **kw):
        c = {"schema": "devorch.task_contract.v1", "task_id": tid, "contract_version": 1, "kind": kind,
             "linear_issue": None, "merc_issue": kw.pop("merc", "MERC-101" if kind == "implementation" else None),
             "assigned_agent": agent, "objective": "test objective here", "requirements": [], "dependencies": [],
             "approved_design_refs": [f"docs/x.md§1@{self.base}"],
             "allowed_paths": kw.pop("allowed", ["src/core/**"] if kind not in D.READ_ONLY_KINDS else []),
             "restricted_paths": kw.pop("restricted", ["docs/**", ".github/**"]), "interface_contracts": [],
             "acceptance_criteria": ["works"], "required_tests": kw.pop("tests", []),
             "required_reviewers": kw.pop("reviewers", ["mdev-code-reviewer", "mdev-security-engineer"]),
             "required_gates": ["G1", "G2", "G3", "G4", "G5", "G6", "G7"], "security_sensitive": kw.pop("sec", False),
             "branch": branch, "worktree": self.repo, "base_commit": self.base,
             "evidence_dir": os.path.join(self.ev, tid, "attempt-1"), "status": "READY", "attempt": 1,
             "budget": {"max_attempts": kw.pop("max_attempts", 3), "max_turns": 10, "max_wall_minutes": 30},
             "created_at": "2026-10-15T00:00:00Z", "created_by": "principal-orchestrator"}
        c.update(kw)
        os.makedirs(c["evidence_dir"], exist_ok=True)
        json.dump(c, open(os.path.join(self.home, "tasks", tid + ".json"), "w"))
        return c

    def write(self, name, obj):
        p = os.path.join(self.root, name)
        json.dump(obj, open(p, "w"))
        return p

    def rec(self, tid, event, *evidence, ok=True, **kw):
        args = ["record", "--task", tid, "--event", event]
        for e in evidence or ("log:" + self.write(f"ev-{tid}-{event}.json", {"e": event}),):
            args += ["--evidence", e]
        for k, v in kw.items():
            args += [f"--{k}", v]
        return self.run(*args, ok=ok)

    def commit(self, path, content="x", msg="c", branch="dev/merc-101-x"):
        sh(f"git checkout -q -B {branch} 2>/dev/null || git checkout -q {branch}", self.repo)
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(content)
        sh(f"git add -A && git commit -qm {msg}", self.repo)
        return sh("git rev-parse HEAD", self.repo).stdout.strip()

    def result(self, c, **kw):
        tip = sh(f"git rev-parse {c['branch']}", self.repo, ok=False).stdout.strip()
        rev = [x for x in sh(f"git rev-list {self.base}..{c['branch']}", self.repo, ok=False).stdout.split() if x]
        files = sorted(x for x in sh(f"git diff --no-renames --name-only {self.base} {c['branch']}", self.repo, ok=False).stdout.split("\n") if x)
        r = {"schema": "devorch.task_result.v1", "task_id": c["task_id"], "contract_version": 1, "attempt": c["attempt"],
             "agent": c["assigned_agent"], "status": "completed", "summary": "did the work as asked",
             "head_commit": tip if rev else None, "modified_files": files, "commits": rev, "tests": [],
             "defects": [], "findings": [], "outstanding_dependencies": [], "blocking_conditions": [],
             "recommended_next_action": "next", "evidence_refs": []}
        r.update(kw)
        p = os.path.join(c["evidence_dir"], "result.json")
        json.dump(r, open(p, "w"))
        return p

    def to_awaiting_review(self, tid="DT-0001", sec=False):
        c = self.contract(tid, sec=sec)
        head = self.commit("src/core/a.ts")
        self.rec(tid, "created")
        self.rec(tid, "unblocked", f"design_ref:docs/x.md@{self.base}")
        self.rec(tid, "assigned")
        self.rec(tid, "tests_passed", "test_run:" + self.write("g2.log.json", {"ok": 1}), head=head)
        return c, head

    def review(self, parent, head, kind="code_review", agent="mdev-code-reviewer", suffix="r1", accept=True):
        sid = f"{parent}-{suffix}"
        c = self.contract(sid, kind=kind, agent=agent, merc=None, parent_task_id=parent, reviewers=[],
                          review_target={"implementation_task_id": parent, "base_commit": self.base, "head_commit": head})
        res = self.result(c, reviewed_head_commit=head, recommendation="accept" if accept else "changes_required",
                          commits=[], modified_files=[], head_commit=None)
        self.run("check-result", res, os.path.join(self.home, "tasks", sid + ".json"), ok=True)
        self.rec(sid, "created")
        self.rec(sid, "unblocked", f"design_ref:x@{self.base}")
        self.rec(sid, "assigned")
        self.rec(sid, "result_accepted", "result_file:" + res)
        return sid

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class T(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        self.e.cleanup()

    # --- check-result (R4 F01/F02/F10/F11/F28, R1 H-01) -----------------------------------
    def test_empty_commits_cannot_hide_restricted_change(self):
        c = self.e.contract("DT-0001")
        self.e.commit(".github/workflows/x.yml")
        p = self.e.result(c, commits=[], modified_files=[], head_commit=None)
        r = self.e.run("check-result", p, os.path.join(self.e.home, "tasks/DT-0001.json"), ok=False)
        self.assertIn("restricted", r.stdout)

    def test_rename_out_of_restricted_path_detected(self):
        self.e.commit("docs/secret.md", branch="main")
        self.e.base = sh("git rev-parse HEAD", self.e.repo).stdout.strip()
        c = self.e.contract("DT-0001")
        sh("git checkout -q -b dev/merc-101-x && mkdir -p src/core && git mv docs/secret.md src/core/s.md && git commit -qm mv", self.e.repo)
        p = self.e.result(c)
        r = self.e.run("check-result", p, os.path.join(self.e.home, "tasks/DT-0001.json"), ok=False)
        self.assertIn("docs/secret.md", r.stdout)

    def test_glob_semantics(self):
        self.assertTrue(D.matches("README.md", ["**/*.md"]))
        self.assertFalse(D.matches("src/core/deep/x.ts", ["src/core/*.ts"]))
        self.assertTrue(D.matches("src/core/deep/x.ts", ["src/core/**"]))
        self.assertFalse(D.matches("src/x.ts", ["*"]))

    def test_dirty_worktree_rejected(self):
        c = self.e.contract("DT-0001")
        self.e.commit("src/core/a.ts")
        open(os.path.join(self.e.repo, "docs-untracked.txt"), "w").write("x")
        p = self.e.result(c)
        r = self.e.run("check-result", p, os.path.join(self.e.home, "tasks/DT-0001.json"), ok=False)
        self.assertIn("uncommitted", r.stdout)

    def test_valid_result_passes(self):
        c = self.e.contract("DT-0001")
        self.e.commit("src/core/a.ts")
        p = self.e.result(c)
        self.e.run("check-result", p, os.path.join(self.e.home, "tasks/DT-0001.json"), ok=True)

    # --- gates and lifecycle (R1 C-01/H-02/H-03/H-05, R4 F03/F05/F07/F08/F09/F24, R2 S-06) ---
    def test_full_happy_path_with_bound_reviews(self):
        c, head = self.e.to_awaiting_review()
        r1 = self.e.review("DT-0001", head)
        self.e.rec("DT-0001", "code_review_passed", f"subtask:{r1}")
        s1 = self.e.review("DT-0001", head, "security_review", "mdev-security-engineer", "s1")
        self.e.rec("DT-0001", "security_review_passed", f"subtask:{s1}")
        ic = self.e.contract("DT-0001-i1", kind="integration", agent="mdev-integration-release-engineer", merc=None,
                             covers_tasks=["DT-0001"], reviewers=[], allowed=[])
        ires = self.e.result(ic, commits=[], modified_files=[], head_commit=None, recommendation="accept",
                             integrated_heads=[f"DT-0001@{head}"])
        for ev in ("created",):
            self.e.rec("DT-0001-i1", ev)
        self.e.rec("DT-0001-i1", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0001-i1", "assigned")
        self.e.rec("DT-0001-i1", "result_accepted", "result_file:" + ires)
        self.e.rec("DT-0001", "integration_verified", "subtask:DT-0001-i1")
        self.e.rec("DT-0001", "pr_prepared", "pr:https://example/pr/1", head=head)
        self.e.rec("DT-0001", "human_merged", "github_merge:merged_by=operator", head=head)
        self.e.run("verify-ledger", ok=True)

    def test_security_review_cannot_be_skipped(self):
        c, head = self.e.to_awaiting_review()
        r1 = self.e.review("DT-0001", head)
        self.e.rec("DT-0001", "code_review_passed", f"subtask:{r1}")
        r = self.e.rec("DT-0001", "integration_verified", "subtask:x", ok=False)
        self.assertIn("illegal transition", r.stderr)

    def test_review_of_stale_head_refused(self):
        c, head = self.e.to_awaiting_review()
        old = self.e.base
        sid = "DT-0001-r1"
        self.e.contract(sid, kind="code_review", agent="mdev-code-reviewer", merc=None, parent_task_id="DT-0001", reviewers=[],
                        review_target={"implementation_task_id": "DT-0001", "base_commit": self.e.base, "head_commit": head})
        res = self.e.result(load(self.e, sid), reviewed_head_commit=head, recommendation="accept", commits=[], modified_files=[], head_commit=None)
        for ev in ("created",):
            self.e.rec(sid, ev)
        self.e.rec(sid, "unblocked", f"design_ref:x@{old}")
        self.e.rec(sid, "assigned")
        self.e.rec(sid, "result_accepted", "result_file:" + res)
        # implementation moves on after the review: correction loop and new head
        self.e.rec("DT-0001", "code_review_changes_required", "log:" + res)
        bump(self.e, "DT-0001")
        newhead = self.e.commit("src/core/b.ts")
        self.e.rec("DT-0001", "tests_passed", "test_run:" + self.e.write("g2b.json", {}), head=newhead)
        r = self.e.rec("DT-0001", "code_review_passed", f"subtask:{sid}", ok=False)
        self.assertIn("not bound to the current tested head", r.stderr)

    def test_forged_actor_refused(self):
        self.e.contract("DT-0001")
        self.e.rec("DT-0001", "created")
        r = self.e.rec("DT-0001", "unblocked", f"design_ref:x@{self.e.base}", actor="mdev-backend-engineer", ok=False)
        self.assertIn("actor must be one of", r.stderr)

    def test_forged_ledger_detected_by_replay(self):
        c, head = self.e.to_awaiting_review()
        # an attacker appends a well-chained but illegal G7 record by hand
        lp = os.path.join(self.e.home, "ledger/DT-0001.jsonl")
        last = json.loads(open(lp).read().strip().split("\n")[-1])
        forged = dict(last, seq=last["seq"] + 1, event="human_merged", from_state="AWAITING_REVIEW", to_state="COMPLETED",
                      gate="G7", prev_hash=last["hash"])
        forged["hash"] = hashlib.sha256(D.canon(forged).encode()).hexdigest()
        open(lp, "a").write(json.dumps(forged) + "\n")
        r = self.e.run("verify-ledger", ok=False)
        self.assertIn("illegal transition", r.stdout)

    def test_contract_tamper_detected(self):
        self.e.contract("DT-0001")
        self.e.rec("DT-0001", "created")
        p = os.path.join(self.e.home, "tasks/DT-0001.json")
        c = json.load(open(p)); c["allowed_paths"] = ["**"]; json.dump(c, open(p, "w"))
        r = self.e.rec("DT-0001", "unblocked", f"design_ref:x@{self.e.base}", ok=False)
        self.assertIn("contract changed without a contract_revised", r.stderr)

    def test_short_lifecycle_operator_task_completes(self):
        self.e.contract("DT-0002", kind="operator_action", agent="operator", merc="MERC-020", reviewers=[], allowed=[])
        self.e.rec("DT-0002", "created")
        self.e.rec("DT-0002", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0002", "assigned")
        self.e.rec("DT-0002", "result_accepted", "operator_statement:decisions recorded in ESCALATIONS.md", actor="operator")
        st = self.e.run("status", ok=True).stdout
        self.assertIn("COMPLETED", st)

    def test_failed_can_be_revised(self):
        self.e.contract("DT-0001", max_attempts=1)
        self.e.rec("DT-0001", "created")
        self.e.rec("DT-0001", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0001", "assigned")
        r = self.e.rec("DT-0001", "attempt_failed", ok=False)
        self.assertIn("budget", r.stderr)
        self.e.rec("DT-0001", "failed")
        p = os.path.join(self.e.home, "tasks/DT-0001.json")
        c = json.load(open(p)); c["contract_version"] = 2; c["objective"] = "split: smaller objective"; json.dump(c, open(p, "w"))
        self.e.rec("DT-0001", "contract_revised")

    def test_duplicate_gate_refused(self):
        c, head = self.e.to_awaiting_review()
        r1 = self.e.review("DT-0001", head)
        self.e.rec("DT-0001", "code_review_passed", f"subtask:{r1}")
        r = self.e.rec("DT-0001", "code_review_passed", f"subtask:{r1}", ok=False)
        self.assertIn("already recorded", r.stderr)

    def test_review_budget_enforced(self):
        c, head = self.e.to_awaiting_review()
        for i in range(3):
            self.e.rec("DT-0001", "code_review_changes_required")
            bump(self.e, "DT-0001")
            h = self.e.commit(f"src/core/f{i}.ts")
            self.e.rec("DT-0001", "tests_passed", "test_run:" + self.e.write(f"t{i}.json", {}), head=h)
        r = self.e.rec("DT-0001", "code_review_changes_required", ok=False)
        self.assertIn("review loop budget", r.stderr)

    # --- ledger robustness (R4 F04/F12/F13, R1 H-04) --------------------------------------
    def test_lock_and_escalations_do_not_break_verify(self):
        self.e.contract("DT-0001"); self.e.rec("DT-0001", "created")
        open(os.path.join(self.e.home, "ESCALATIONS.md"), "w").write("# x\n")
        self.e.run("lock", "acquire", "--session", "s1", ok=True)
        self.e.run("verify-ledger", ok=True)

    def test_partial_tail_detected_and_repairable(self):
        self.e.contract("DT-0001"); self.e.rec("DT-0001", "created")
        open(os.path.join(self.e.home, "ledger/DT-0001.jsonl"), "a").write('{"seq": 2, "trunc')
        self.e.run("verify-ledger", ok=False)
        self.e.run("verify-ledger", "--repair-tail", ok=True)

    def test_missing_evidence_file_refused(self):
        self.e.contract("DT-0001")
        r = self.e.rec("DT-0001", "created", "result_file:evidence/none.json", ok=False)
        self.assertIn("not found", r.stderr)

    def test_evidence_dir_inside_home_refused(self):
        c = self.e.contract("DT-0001", evidence_dir=os.path.join(self.e.home, "evidence/DT-0001/attempt-1"))
        r = self.e.run("check-contract", os.path.join(self.e.home, "tasks/DT-0001.json"), ok=False)
        self.assertIn("outside DEVORCH_HOME", r.stdout)

    def test_path_ownership_conflict(self):
        self.e.contract("DT-0001")
        self.e.rec("DT-0001", "created"); self.e.rec("DT-0001", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0001", "assigned")
        self.e.contract("DT-0003", merc="MERC-102", allowed=["src/core/x/**"], branch="dev/merc-102-y")
        r = self.e.run("check-contract", os.path.join(self.e.home, "tasks/DT-0003.json"), ok=False)
        self.assertIn("ownership conflict", r.stdout)


def load(e, tid):
    return json.load(open(os.path.join(e.home, "tasks", tid + ".json")))


def bump(e, tid):
    p = os.path.join(e.home, "tasks", tid + ".json")
    c = json.load(open(p)); c["attempt"] += 1; json.dump(c, open(p, "w"))


if __name__ == "__main__":
    unittest.main()
