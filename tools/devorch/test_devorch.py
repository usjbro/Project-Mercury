#!/usr/bin/env python3
"""Regression tests for tools/devorch/devorch.py (development orchestration tooling).

Each test reproduces a finding from the Phase 14 reviews (R1 C-01/H-0x, R2 S-0x, R4 F0x) in scratch
git repositories and checks that devorch now refuses or detects it.  Run:
    python3 tools/devorch/test_devorch.py -v
"""
import glob, hashlib, json, os, shutil, subprocess, sys, tempfile, unittest

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
    def __init__(self, facts=True):
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
        issue = {"deps": [], "conditional": False, "gates": "", "p0_refs": [], "longest_path_p50": 1, "downstream": 0,
                 "needs_mac_or_operator": False, "title": "t"}
        json.dump({"issues": {k: dict(issue) for k in ("MERC-101", "MERC-102", "MERC-020")}},
                  open(os.path.join(self.home, "dag.json"), "w"))
        if facts:   # the hard preconditions for code tasks (DOD-02 ruleset, DOD-03 identity), recorded by the operator
            for kind, fid in (("decision", "DOD-02"), ("identity", "DOD-03")):
                self.run("fact", "--kind", kind, "--id", fid, "--status", "verified", "--actor", "operator",
                         "--evidence", "test", ok=True)

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

    def implement(self, tid, path, branch="dev/merc-101-x"):
        """Agent commits and writes result.json; orchestrator records the checked result."""
        head = self.commit(path, branch=branch)
        res = self.result(load(self, tid))
        self.rec(tid, "implementation_completed", "result_file:" + res, head=head)
        return head

    def to_awaiting_review(self, tid="DT-0001", sec=False):
        c = self.contract(tid, sec=sec)
        self.rec(tid, "created")
        self.rec(tid, "unblocked", f"design_ref:docs/x.md@{self.base}")
        self.rec(tid, "assigned")
        self.rec(tid, "dispatched", session="s1")
        head = self.implement(tid, "src/core/a.ts")
        self.rec(tid, "tests_passed", "test_run:" + self.write("g2.log.json", {"ok": 1}), head=head)
        return c, head

    def correction(self, tid, path):
        bump(self, tid)
        self.rec(tid, "dispatched", session="s2")
        head = self.implement(tid, path)
        self.rec(tid, "tests_passed", "test_run:" + self.write(f"g2-{os.path.basename(path)}.json", {}), head=head)
        return head

    def review(self, parent, head, kind="code_review", agent="mdev-code-reviewer", suffix="r1", accept=True,
               branch="dev/merc-101-x", tests=()):
        sid = f"{parent}-{suffix}"
        c = self.contract(sid, kind=kind, agent=agent, merc=None, parent_task_id=parent, reviewers=[], branch=branch,
                          tests=list(tests),
                          review_target={"implementation_task_id": parent, "base_commit": self.base, "head_commit": head})
        res = self.result(c, reviewed_head_commit=head, recommendation="accept" if accept else "changes_required",
                          commits=[], modified_files=[], head_commit=None,
                          tests=[{"id": t["id"], "command": t["command"], "exit_code": 0, "outcome": "passed"} for t in tests])
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
        ires = self.e.result(ic, recommendation="accept",
                             integrated_heads=[f"DT-0001@{head}"])
        for ev in ("created",):
            self.e.rec("DT-0001-i1", ev)
        self.e.rec("DT-0001-i1", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0001-i1", "assigned")
        self.e.rec("DT-0001-i1", "result_accepted", "result_file:" + ires)
        self.e.rec("DT-0001", "integration_verified", "subtask:DT-0001-i1")
        self.e.rec("DT-0001", "pr_prepared", "pr:https://example/pr/1", "ci_run:" + self.e.write("ci.json", {"ok": 1}), head=head)
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
        self.e.correction("DT-0001", "src/core/b.ts")
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
        r = self.e.run("verify-ledger", ok=False)   # replay compares the contract file with the last record
        self.assertIn("contract file edited after the last record", r.stdout)

    def test_short_lifecycle_operator_task_completes(self):
        self.e.contract("DT-0002", kind="operator_action", agent="operator", merc="MERC-020", reviewers=[], allowed=[])
        self.e.rec("DT-0002", "created")
        self.e.rec("DT-0002", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0002", "assigned")
        r = self.e.rec("DT-0002", "result_accepted", "log:" + self.e.write("x.json", {}), ok=False)
        self.assertIn("recorded by the operator", r.stderr)  # R5 N4: the orchestrator cannot complete it
        self.e.rec("DT-0002", "result_accepted", "operator_statement:" + self.e.write("op.md", {"done": 1}), actor="operator")
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

    def revise(self, tid, **core):
        p = os.path.join(self.e.home, "tasks", tid + ".json")
        c = json.load(open(p))
        c["contract_version"] += 1
        c.update(core)
        json.dump(c, open(p, "w"))

    def test_revision_does_not_reinterpret_earlier_records(self):
        # Codex review on PR #5: replay judged every record by the CURRENT contract, so a revision that adds a required
        # reviewer made the old G3 record fail and `contract_revised` itself could never be appended
        c, head = self.e.to_awaiting_review()
        r1 = self.e.review("DT-0001", head)
        self.e.rec("DT-0001", "code_review_passed", f"subtask:{r1}")
        self.revise("DT-0001", required_reviewers=c["required_reviewers"] + ["mdev-reliability-engineer"])
        self.e.rec("DT-0001", "contract_revised")
        self.e.run("verify-ledger", ok=True)

    def test_revision_may_lower_the_attempt_budget_below_recorded_failures(self):
        self.e.contract("DT-0001", max_attempts=3)
        for ev in ("created",):
            self.e.rec("DT-0001", ev)
        self.e.rec("DT-0001", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0001", "assigned")
        self.e.rec("DT-0001", "attempt_failed")
        self.e.rec("DT-0001", "attempt_failed")
        self.revise("DT-0001", budget={"max_attempts": 2, "max_turns": 10, "max_wall_minutes": 30})
        self.e.rec("DT-0001", "contract_revised")
        self.e.run("verify-ledger", ok=True)

    def test_contract_snapshot_tamper_detected(self):
        c, head = self.e.to_awaiting_review()
        r1 = self.e.review("DT-0001", head)
        self.e.rec("DT-0001", "code_review_passed", f"subtask:{r1}")
        self.revise("DT-0001", required_reviewers=c["required_reviewers"] + ["mdev-reliability-engineer"])
        self.e.rec("DT-0001", "contract_revised")
        snaps = glob.glob(os.path.join(self.e.home, "contracts", "DT-0001", "*.json"))
        self.assertGreaterEqual(len(snaps), 2, "one snapshot per distinct contract core")
        old = json.load(open(snaps[0])); old["allowed_paths"] = ["**"]; json.dump(old, open(snaps[0], "w"))
        r = self.e.run("verify-ledger", ok=False)
        self.assertIn("snapshot", r.stdout)

    def test_ledger_without_snapshots_verifies_only_while_unrevised(self):
        # ledgers written before snapshots existed: the contract file is the contract of every record while it is unchanged
        c, head = self.e.to_awaiting_review()
        shutil.rmtree(os.path.join(self.e.home, "contracts"))
        self.e.run("verify-ledger", ok=True)
        self.revise("DT-0001", objective="a different objective")
        r = self.e.rec("DT-0001", "contract_revised", ok=False)
        self.assertIn("snapshot", r.stderr)   # cannot be told apart from a deleted snapshot: refused, not guessed

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
            self.e.correction("DT-0001", f"src/core/f{i}.ts")
        r = self.e.rec("DT-0001", "code_review_changes_required", ok=False)
        self.assertIn("review loop budget", r.stderr)

    def test_result_accepted_requires_checking_result(self):
        # R0: record re-runs check-result; an integration result that claims a head it does not contain is refused
        c, head = self.e.to_awaiting_review()
        ic = self.e.contract("DT-0001-i1", kind="integration", agent="mdev-integration-release-engineer", merc=None,
                             covers_tasks=["DT-0001"], reviewers=[], allowed=[], branch="dev/dt-0001-int-w1-1")
        sh(f"git branch -f dev/dt-0001-int-w1-1 {self.e.base}", self.e.repo)
        ires = self.e.result(ic, recommendation="accept", integrated_heads=[f"DT-0001@{head}"])
        self.e.rec("DT-0001-i1", "created")
        self.e.rec("DT-0001-i1", "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0001-i1", "assigned")
        r = self.e.rec("DT-0001-i1", "result_accepted", "result_file:" + ires, ok=False)
        self.assertIn("not contained in the integration tip", r.stderr)

    def test_correction_attempt_keeps_contract_core(self):
        # attempt and evidence_dir are per-attempt fields; changing them needs no contract_revised
        c, head = self.e.to_awaiting_review()
        self.e.rec("DT-0001", "code_review_changes_required")
        bump(self.e, "DT-0001")
        self.e.rec("DT-0001", "dispatched", session="s2")
        p = os.path.join(self.e.home, "tasks/DT-0001.json")
        c = json.load(open(p)); c["allowed_paths"] = ["**"]; json.dump(c, open(p, "w"))
        r = self.e.rec("DT-0001", "started", ok=False)
        self.assertIn("contract changed without a contract_revised", r.stderr)

    # --- R5 re-review findings ------------------------------------------------------------
    def test_g2_requires_checked_implementation_at_that_head(self):
        # R5 N1: G2 without implementation_completed, or at a head committed after it, is refused
        self.e.contract("DT-0001")
        for ev in ("created", "assigned"):
            if ev == "assigned":
                self.e.rec("DT-0001", "unblocked", f"design_ref:x@{self.e.base}")
            self.e.rec("DT-0001", ev)
        h = self.e.commit(".github/x.yml")
        r = self.e.rec("DT-0001", "tests_passed", "test_run:" + self.e.write("t.json", {}), head=h, ok=False)
        self.assertIn("checked implementation_completed", r.stderr)

    def test_forged_legal_chain_with_fake_subtasks_fails_verify(self):
        # R5 N2/N-05: well-chained, legal-looking records citing nonexistent subtasks fail replay
        c, head = self.e.to_awaiting_review()
        lp = os.path.join(self.e.home, "ledger/DT-0001.jsonl")
        last = json.loads(open(lp).read().strip().split("\n")[-1])
        forged = dict(last, seq=last["seq"] + 1, event="code_review_passed", from_state="AWAITING_REVIEW",
                      to_state="AWAITING_REVIEW", gate="G3", prev_hash=last["hash"],
                      evidence=[{"kind": "subtask", "ref": "DT-0001-r9"}])
        forged.pop("head_commit", None)
        forged["hash"] = hashlib.sha256(D.canon(forged).encode()).hexdigest()
        open(lp, "a").write(json.dumps(forged) + "\n")
        r = self.e.run("verify-ledger", ok=False)
        self.assertIn("DT-0001-r9 has no contract", r.stdout)

    def test_swapped_review_result_after_acceptance_refused(self):
        # R5 N3/N-04: the ledger trusts the hashed copy in HOME, and the copy is hash-checked
        c, head = self.e.to_awaiting_review()
        sid = self.e.review("DT-0001", head, accept=False)
        self.e.rec("DT-0001", "code_review_changes_required")
        # attacker rewrites the agent-writable original: no effect, the HOME copy is used
        orig = os.path.join(load(self.e, sid)["evidence_dir"], "result.json")
        r = json.load(open(orig)); r["recommendation"] = "accept"; json.dump(r, open(orig, "w"))
        h2 = self.e.correction("DT-0001", "src/core/b.ts")
        r = self.e.rec("DT-0001", "code_review_passed", f"subtask:{sid}", ok=False)
        self.assertIn("did not accept", r.stderr)
        # tampering with the HOME copy is detected by replay
        rec = [json.loads(l) for l in open(os.path.join(self.e.home, f"ledger/{sid}.jsonl"))][-1]
        copy = os.path.join(self.e.home, rec["evidence"][0]["ref"])
        x = json.load(open(copy)); x["recommendation"] = "accept"; json.dump(x, open(copy, "w"))
        r = self.e.run("verify-ledger", ok=False)
        self.assertIn("changed after it was recorded", r.stdout)

    def test_forged_worktree_pointer_refused(self):
        # R5 N-02: a .git pointer to a foreign git dir (fsmonitor/ref spoofing) is refused
        sh("git worktree add -q ../wt1 -b dev/merc-101-wt", self.e.repo)
        wt = os.path.join(self.e.root, "wt1")
        common = os.path.join(self.e.repo, ".git")
        self.assertTrue(D.worktree_git(wt, common))
        evil = os.path.join(self.e.root, "evil"); os.makedirs(evil)
        open(os.path.join(wt, ".git"), "w").write(f"gitdir: {evil}\n")
        with self.assertRaises(D.Refused):
            D.worktree_git(wt, common)

    def test_skip_worktree_hidden_change_refused(self):
        # R5 N-03: a committed change hidden from status by skip-worktree fails check-result
        c = self.e.contract("DT-0001")
        self.e.commit("src/core/a.ts", "backdoor")
        sh("git update-index --skip-worktree src/core/a.ts && printf clean > src/core/a.ts", self.e.repo)
        p = self.e.result(c)
        r = self.e.run("check-result", p, os.path.join(self.e.home, "tasks/DT-0001.json"), ok=False)
        self.assertIn("hidden from status", r.stdout)

    def test_g1_requires_ready_including_hard_preconditions(self):
        # R5 M2/N-06: G1 is refused while the task is not READY by the `ready` rules
        e = Env(facts=False)
        try:
            e.contract("DT-0001"); e.rec("DT-0001", "created")
            r = e.rec("DT-0001", "unblocked", f"design_ref:x@{e.base}", ok=False)
            self.assertIn("fact DOD-02", r.stderr)
        finally:
            e.cleanup()

    def test_push_requires_state_and_operator_facts(self):
        # R5 N-06 / M5: no push before AWAITING_INTEGRATION, nor without the DOD-02 and identity facts
        c, head = self.e.to_awaiting_review()
        self.e.run("git-baseline", "record", ok=True)
        r = self.e.run("push", "--task", "DT-0001", ok=False)
        self.assertIn("push only from AWAITING_INTEGRATION", r.stderr)
        for k in ("security_review", "code_review"):
            sid = self.e.review("DT-0001", head, k, "mdev-security-engineer" if k == "security_review" else "mdev-code-reviewer",
                                "s1" if k == "security_review" else "r1")
            self.e.rec("DT-0001", "security_review_passed" if k == "security_review" else "code_review_passed", f"subtask:{sid}")
        self.e.run("fact", "--kind", "decision", "--id", "DOD-02", "--status", "revoked", "--actor", "operator",
                   "--evidence", "ruleset removed", ok=True)
        r = self.e.run("push", "--task", "DT-0001", ok=False)
        self.assertIn("operator facts missing", r.stderr)

    # --- ledger robustness (R4 F04/F12/F13, R1 H-04) --------------------------------------
    def test_lock_and_escalations_do_not_break_verify(self):
        self.e.contract("DT-0001"); self.e.rec("DT-0001", "created")
        open(os.path.join(self.e.home, "ESCALATIONS.md"), "w").write("# x\n")
        self.e.run("lock", "acquire", "--session", "s1", ok=True)
        self.e.run("verify-ledger", ok=True)

    def test_preflight_tolerates_own_lock_but_not_foreign_changes(self):
        h = self.e.home
        sh("git init -q -b devorch/state . && git config user.email t@t && git config user.name t", h)
        self.e.contract("DT-0001"); self.e.rec("DT-0001", "created")
        sh("git add -A && git commit -qm l", h)
        self.e.run("git-baseline", "record", ok=True)
        sh("git add -A && git commit -qm b", h)
        self.e.run("lock", "acquire", "--session", "s1", ok=True)
        self.e.run("preflight", "--session", "s1", ok=True)
        open(os.path.join(h, "ledger/x.txt"), "w").write("foreign")
        r = self.e.run("preflight", "--session", "s1", ok=False)
        self.assertIn("uncommitted", r.stdout)

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


    def test_ownership_rechecked_at_assigned(self):
        # Codex review on PR #2: two overlapping tasks created while both were inactive must not both enter RUNNING
        for tid, merc, br in (("DT-0001", "MERC-101", "dev/merc-101-x"), ("DT-0003", "MERC-102", "dev/merc-102-y")):
            self.e.contract(tid, merc=merc, allowed=["src/core/**"], branch=br)
            self.e.rec(tid, "created"); self.e.rec(tid, "unblocked", f"design_ref:x@{self.e.base}")
        self.e.rec("DT-0001", "assigned")
        r = self.e.rec("DT-0003", "assigned", ok=False)
        self.assertIn("ownership conflict with active task DT-0001", r.stderr)

    def test_baseline_detects_user_config_change(self):
        # Codex review on PR #2: user configuration was snapshotted but never compared
        fake_home = os.path.join(self.e.root, "user-home")
        os.makedirs(fake_home)
        self.e.env["HOME"] = fake_home
        gc = os.path.join(fake_home, ".gitconfig")
        open(gc, "w").write("[user]\n\tname = op\n")
        self.e.run("git-baseline", "record", ok=True)
        self.e.run("git-baseline", "verify", ok=True)
        open(gc, "a").write("[url \"https://attacker.example/\"]\n\tinsteadOf = https://github.com/\n")
        r = self.e.run("git-baseline", "verify", ok=False)
        self.assertIn("user configuration changed: ~/.gitconfig", r.stdout)
        b = os.path.join(self.e.home, "baseline.json")
        old = json.load(open(b)); old.pop("user_config"); json.dump(old, open(b, "w"))
        r = self.e.run("git-baseline", "verify", ok=False)
        self.assertIn("no user configuration snapshot", r.stdout)


class ScheduleModel(unittest.TestCase):
    """tools/devorch/schedule_model.py: every phase of every issue is scheduled, stacked or not."""

    def dag(self):
        issue = lambda deps, lp: {"deps": deps, "conditional": False, "p50": 1.0, "env": ["T0"], "needs_mac_or_operator": False,
                                  "root": False, "security": False, "longest_path_p50": lp, "downstream": 1 - len(deps)}
        return {"issues": {"MERC-201": issue([], 2), "MERC-202": issue(["MERC-201"], 1)}}

    def test_stacked_mode_still_schedules_reviews(self):
        # Codex review on PR #2: stacked mode released a task at G6 and then never ran its PR review
        sys.path.insert(0, os.path.dirname(TOOL))
        import schedule_model as SM
        kw = dict(workers=1, k_agent=1.0, ovh=0.0, sec_ovh=0.0, integ=0.0, pr_review=10.0)
        flat, stacked = SM.sim(self.dag(), **kw), SM.sim(self.dag(), stacked=True, **kw)
        self.assertGreaterEqual(stacked[0], 20, stacked)          # two 10-day reviews on one operator lane
        self.assertGreater(stacked[2], 0, stacked)
        self.assertLessEqual(stacked[0], flat[0], (stacked, flat))  # stacking only lets B's agent work start earlier


def load(e, tid):
    return json.load(open(os.path.join(e.home, "tasks", tid + ".json")))


def bump(e, tid):
    """Correction attempt: attempt and evidence_dir change, the contract core does not."""
    p = os.path.join(e.home, "tasks", tid + ".json")
    c = json.load(open(p)); c["attempt"] += 1
    c["evidence_dir"] = os.path.join(e.ev, tid, f"attempt-{c['attempt']}")
    os.makedirs(c["evidence_dir"], exist_ok=True)
    json.dump(c, open(p, "w"))


if __name__ == "__main__":
    unittest.main()
