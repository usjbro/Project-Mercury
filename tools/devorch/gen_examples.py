#!/usr/bin/env python3
"""Generate docs/mercury/development-orchestration/examples/ by running a real devorch v2 scenario.

Every contract, result and ledger in examples/ is produced here by devorch.py itself (check-contract,
check-result and record), so the examples cannot drift from the tool. The scenario runs in a scratch
directory (DEVORCH_TEST_MODE=1 skips only the devorch/state worktree check), then copies the files.

    python3 tools/devorch/gen_examples.py            # regenerate examples/
    python3 tools/devorch/gen_examples.py --check    # rerun the scenario, write nothing

Scenario (DT-0001 = MERC-101): implementation -> G2 -> code review r1 requests changes -> correction
attempt 2 -> G2 on the new head -> review r2 accepts (G3) -> security review s1 accepts (G4) ->
integration i1 covers DT-0001 at that head (G5) -> pr_prepared (G6) -> human_merged (G7) -> closed.
Commit SHAs and timestamps differ on every run; the structure does not.
"""
import json, os, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_devorch import Env, bump, load, sh  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "docs", "mercury", "development-orchestration", "examples")
DESIGN = ["docs/mercury/architecture/components.md§2", "docs/mercury/operations/macos-service.md§2",
          "docs/mercury/architecture/decisions/ADR-016-filesystem-layout.md"]
TESTS = [{"id": "TC-UNIT-061", "command": "npm test -- test/unit/core/config", "env": "T1"},
         {"id": "TC-SEC-150", "command": "npm test -- test/unit/core/log/redactor", "env": "T1"},
         {"id": "typecheck", "command": "npm run typecheck", "env": "T0"}]


TASKS = ("DT-0001", "DT-0001-r1", "DT-0001-r2", "DT-0001-s1", "DT-0001-i1")


def passed(tests):
    return [{"id": t["id"], "command": t["command"], "exit_code": 0, "outcome": "passed", "runs": 1} for t in tests]


def scenario(e):
    T = "DT-0001"
    c = e.contract(T, branch="dev/merc-101-skeleton", merc="MERC-101", sec=True, tests=TESTS,
                   allowed=["src/core/config/**", "src/core/paths.ts", "src/core/log/**", "test/unit/core/**"],
                   restricted=["docs/**", ".github/**", ".claude/**", "migrations/**", "src/ports/**"],
                   objective="Project skeleton, config schema and validator with parameter clamps, single paths module, "
                             "structured logger with redactor sinks (issue-breakdown MERC-101).",
                   requirements=["NFR-072", "NFR-062", "SEC-501", "CON-013"],
                   approved_design_refs=[f"{d}@{e.base}" for d in DESIGN],
                   acceptance_criteria=["TC-UNIT-061 and TC-SEC-150 pass", "No parameter hard-coded outside the config module",
                                        "Redactor applied on every log sink"])
    cp = os.path.join(e.home, "tasks", T + ".json")
    e.run("check-contract", cp, ok=True)
    e.rec(T, "created")
    e.rec(T, "unblocked", *[f"design_ref:{d}@{e.base}" for d in DESIGN])
    e.rec(T, "assigned")
    e.rec(T, "dispatched", session="sess-example-1")
    e.commit("src/core/config/load.ts", "export const load = () => ({});\n", "config", c["branch"])
    h1 = e.commit("src/core/log/redact.ts", "export const redact = (s: string) => s;\n", "log", c["branch"])
    r = e.result(c, tests=passed(TESTS), summary="Config loader, paths module and redacting logger added; required tests pass.")
    e.run("check-result", r, cp, ok=True)
    e.rec(T, "implementation_completed", "result_file:" + r, head=h1)
    e.rec(T, "tests_passed", "test_run:" + e.write("g2-attempt1.json", {"rerun_by": "principal-orchestrator", "head": h1}), head=h1)
    res = {"impl1": r}

    # review r1: changes required (blocking finding), accepted as a valid review result
    sid = f"{T}-r1"
    rc = e.contract(sid, kind="code_review", agent="mdev-code-reviewer", merc=None, parent_task_id=T, reviewers=[],
                    branch=c["branch"],
                    tests=TESTS, review_target={"implementation_task_id": T, "base_commit": e.base, "head_commit": h1})
    rr = e.result(rc, reviewed_head_commit=h1, recommendation="changes_required", commits=[], modified_files=[], head_commit=None,
                  tests=passed(TESTS), gate_result={"gate": "G3", "result": "fail"}, blocking_conditions=["CR-DT0001-01"],
                  summary="One blocking finding: out-of-range config values are accepted instead of clamped.",
                  findings=[{"id": "CR-DT0001-01", "severity": "medium", "blocking": True, "location": "src/core/config/load.ts:1",
                             "design_ref": "docs/mercury/operations/macos-service.md§2",
                             "description": "Values above the hard cap are accepted unchanged.",
                             "required_correction": "Clamp to the cap, log config.clamped with the key name (no value), add a negative test."}],
                  recommended_next_action="Correction attempt 2 for mdev-backend-engineer.")
    e.run("check-result", rr, os.path.join(e.home, "tasks", sid + ".json"), ok=True)
    for ev in ("created", "unblocked", "assigned"):
        e.rec(sid, ev, *([f"design_ref:{DESIGN[0]}@{e.base}"] if ev == "unblocked" else []))
    e.rec(sid, "result_accepted", "result_file:" + rr)
    e.rec(T, "code_review_changes_required", "result_file:" + rr)
    res["review1"] = rr

    # correction attempt 2: attempt and evidence_dir change, the contract core does not
    bump(e, T)
    c = load(e, T)
    e.rec(T, "dispatched", session="sess-example-2")
    h2 = e.commit("test/unit/core/config/clamp.test.ts", "// negative clamp test\n", "clamp", c["branch"])
    r2 = e.result(c, tests=passed(TESTS), summary="Clamping and negative test added (CR-DT0001-01).")
    e.run("check-result", r2, cp, ok=True)
    e.rec(T, "implementation_completed", "result_file:" + r2, head=h2)
    e.rec(T, "tests_passed", "test_run:" + e.write("g2-attempt2.json", {"rerun_by": "principal-orchestrator", "head": h2}), head=h2)

    r2id = e.review(T, h2, suffix="r2", branch=c["branch"], tests=TESTS)
    e.rec(T, "code_review_passed", f"subtask:{r2id}")
    s1 = e.review(T, h2, "security_review", "mdev-security-engineer", "s1", branch=c["branch"], tests=TESTS)
    e.rec(T, "security_review_passed", f"subtask:{s1}")
    iid = f"{T}-i1"
    ic = e.contract(iid, kind="integration", agent="mdev-integration-release-engineer", merc=None, covers_tasks=[T],
                    reviewers=[], allowed=[], branch="dev/dt-0001-int-w1-1")
    sh(f"git branch -f dev/dt-0001-int-w1-1 {h2}", e.repo)
    ir = e.result(ic, recommendation="accept", tests=passed(TESTS),
                  integrated_heads=[f"{T}@{h2}"], summary="DT-0001 integrated alone on the base; full suite passes.")
    e.run("check-result", ir, os.path.join(e.home, "tasks", iid + ".json"), ok=True)
    for ev in ("created", "unblocked", "assigned"):
        e.rec(iid, ev, *([f"design_ref:{DESIGN[0]}@{e.base}"] if ev == "unblocked" else []))
    e.rec(iid, "result_accepted", "result_file:" + ir)
    e.rec(T, "integration_verified", f"subtask:{iid}")
    e.rec(T, "pr_prepared", "pr:https://github.com/OWNER/REPO/pull/1",
          "ci_run:" + e.write("ci-run.json", {"workflow": "ci", "head": h2, "conclusion": "success"}), head=h2)
    e.rec(T, "human_merged", "github_merge:merged_by=<repository owner>", head=h2)
    e.rec(T, "closed")
    e.run("verify-ledger", ok=True)
    res.update(impl2=r2, integration=ir)
    return res


def main():
    check = sys.argv[1:] == ["--check"]
    e = Env()
    try:
        res = scenario(e)
        st = e.run("status", ok=True).stdout
        if check:
            # SHAs and times differ per run; the event/state/gate sequence must equal the committed examples
            drift = []
            for tid in TASKS:
                new = [(r["event"], r["to_state"], r.get("gate")) for r in map(json.loads, open(os.path.join(e.home, "ledger", tid + ".jsonl")))]
                old = [(r["event"], r["to_state"], r.get("gate")) for r in map(json.loads, open(os.path.join(OUT, "home", "ledger", tid + ".jsonl")))]
                if new != old:
                    drift.append(tid)
            print(st)
            if drift:
                print("examples DRIFTED from the tool for:", drift, "(run without --check to regenerate)")
                sys.exit(1)
            print("scenario OK; committed examples match the tool")
            return
        for f in os.listdir(OUT):
            if f.endswith((".json", ".jsonl")) and f != "result-escalation.json":
                os.remove(os.path.join(OUT, f))
        for tid, name in (("DT-0001", "contract-implementation.json"), ("DT-0001-r1", "contract-code-review.json"),
                          ("DT-0001-i1", "contract-integration.json")):
            shutil.copy(os.path.join(e.home, "tasks", tid + ".json"), os.path.join(OUT, name))
        for k, name in (("impl2", "result-implementation.json"), ("review1", "result-review-changes-required.json"),
                        ("integration", "result-integration.json")):
            shutil.copy(res[k], os.path.join(OUT, name))
        for tid in TASKS:
            shutil.copy(os.path.join(e.home, "ledger", tid + ".jsonl"), os.path.join(OUT, f"ledger-{tid}.jsonl"))
        # the whole ledger home (contracts, ledgers, hashed evidence copies) so the examples can be re-verified:
        #   DEVORCH_TEST_MODE=1 DEVORCH_HOME=docs/mercury/development-orchestration/examples/home devorch.py verify-ledger
        shutil.rmtree(os.path.join(OUT, "home"), ignore_errors=True)
        shutil.copytree(e.home, os.path.join(OUT, "home"), ignore=shutil.ignore_patterns(".git"))
        open(os.path.join(OUT, "status.txt"), "w").write(st)
        print(st)
        print("examples written to", os.path.normpath(OUT))
    finally:
        e.cleanup()


if __name__ == "__main__":
    main()
