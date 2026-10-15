#!/usr/bin/env python3
"""devorch — durable task ledger and verifier for the temporary MERCURY
*development* orchestration system (docs/mercury/development-orchestration/).

This is development tooling, not part of the production MERCURY coordinator.
Standard library only; uses `jsonschema` for full schema validation when it is
installed, otherwise falls back to required-field checks and says so.

State lives in DEVORCH_HOME (default: ../mercury-devorch next to the repo),
a separate git worktree on branch `devorch/state`:

    DEVORCH_HOME/
      tasks/<task_id>.json          current contract (versioned)
      ledger/<task_id>.jsonl        append-only, hash-chained handoff records
      evidence/<task_id>/attempt-N/ results, logs, review reports
      dag.json                      generated from planning/issue-breakdown.md
      reports/                      TPM reports

Commands (all read-only except `record`, `init-task`, `dag`):
    dag            parse issue-breakdown.md -> dag.json; detect cycles
    ready          list tasks whose dependencies and gates are satisfied
    status         current state of every task (derived from the ledger)
    check-contract validate a contract file
    check-result   validate a result against its contract and the git repo
    record         append a ledger record after validating the transition
    verify-ledger  verify every task's hash chain
"""
import argparse, datetime, fnmatch, hashlib, json, os, re, subprocess, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DOC = os.path.join(REPO, "docs", "mercury", "development-orchestration")
SCHEMAS = os.path.join(DOC, "schemas")
BREAKDOWN = os.path.join(REPO, "docs", "mercury", "planning", "issue-breakdown.md")
HOME = os.environ.get("DEVORCH_HOME", os.path.abspath(os.path.join(REPO, "..", "mercury-devorch")))

# Development orchestration state machine (01-development-architecture.md §5).
# (from_state, event) -> (to_state, required_gate or None)
TRANSITIONS = {
    ("NEW", "created"): ("BLOCKED", None),
    ("BLOCKED", "unblocked"): ("READY", None),
    ("READY", "assigned"): ("RUNNING", None),
    ("RUNNING", "started"): ("RUNNING", None),
    ("RUNNING", "attempt_failed"): ("RUNNING", None),
    ("RUNNING", "implementation_completed"): ("RUNNING", None),
    ("RUNNING", "tests_failed"): ("RUNNING", None),
    ("RUNNING", "tests_passed"): ("AWAITING_REVIEW", "G2"),
    ("RUNNING", "interface_frozen"): ("AWAITING_REVIEW", "G1"),
    ("AWAITING_REVIEW", "code_review_changes_required"): ("RUNNING", None),
    ("AWAITING_REVIEW", "security_review_blocked"): ("RUNNING", None),
    # review gate events: to-state is resolved in review_target_state() — AWAITING_INTEGRATION once
    # G3 and (if the contract is security_sensitive) G4 are both recorded, else stay AWAITING_REVIEW
    ("AWAITING_REVIEW", "code_review_passed"): ("AWAITING_REVIEW|AWAITING_INTEGRATION", "G3"),
    ("AWAITING_REVIEW", "security_review_passed"): ("AWAITING_REVIEW|AWAITING_INTEGRATION", "G4"),
    ("AWAITING_INTEGRATION", "integration_failed"): ("RUNNING", None),
    ("AWAITING_INTEGRATION", "integration_verified"): ("AWAITING_INTEGRATION", "G5"),
    ("AWAITING_INTEGRATION", "pr_prepared"): ("AWAITING_HUMAN", "G6"),
    ("AWAITING_HUMAN", "human_changes_requested"): ("RUNNING", None),
    ("AWAITING_HUMAN", "human_merged"): ("COMPLETED", "G7"),
    ("COMPLETED", "closed"): ("COMPLETED", None),
}
NON_TERMINAL = {"BLOCKED", "READY", "RUNNING", "AWAITING_REVIEW", "AWAITING_INTEGRATION", "AWAITING_HUMAN"}
for s in NON_TERMINAL:
    TRANSITIONS[(s, "escalated")] = ("BLOCKED", None)
    TRANSITIONS[(s, "cancelled")] = ("CANCELLED", None)
    TRANSITIONS[(s, "contract_revised")] = ("BLOCKED", None)
for s in ("RUNNING", "AWAITING_REVIEW", "AWAITING_INTEGRATION"):
    TRANSITIONS[(s, "failed")] = ("FAILED", None)
    TRANSITIONS[(s, "stale_detected")] = (s, None)
TRANSITIONS[("RUNNING", "reclaimed")] = ("READY", None)
TRANSITIONS[("BLOCKED", "resumed")] = ("READY", None)
# Gates that must already be recorded before entering a state.
REQUIRED_BEFORE = {
    "AWAITING_INTEGRATION": ["G2", "G3"],
    "AWAITING_HUMAN": ["G2", "G3", "G5", "G6"],
    "COMPLETED": ["G7"],
}


def die(msg, code=2):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def load(path):
    with open(path) as f:
        return json.load(f)


def validate(obj, schema_name):
    schema = load(os.path.join(SCHEMAS, schema_name + ".schema.json"))
    try:
        import jsonschema  # optional
    except ImportError:
        missing = [k for k in schema.get("required", []) if k not in obj]
        extra = [k for k in obj if k not in schema.get("properties", {})]
        errs = [f"missing field {k}" for k in missing] + [f"unknown field {k}" for k in extra]
        if obj.get("schema") != schema["properties"]["schema"]["const"]:
            errs.append("wrong schema id")
        return errs, "structural-only (install jsonschema for full validation)"
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(obj)], "full"


def git(args, cwd):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd,
                          capture_output=True, text=True)


# ---------------------------------------------------------------- dag
def parse_breakdown(path=BREAKDOWN):
    issues, cur, epic = {}, None, None
    for line in open(path):
        line = line.rstrip("\n")
        m = re.match(r"### (E\w+) — ", line)
        if m:
            epic = m.group(1)
            continue
        m = re.match(r"#### (MERC-\w+) — (.*)", line)
        if m:
            cur = m.group(1)
            conditional = "*(conditional)*" in m.group(2)
            title = m.group(2).replace("*(conditional)*", "").strip()
            issues[cur] = {"id": cur, "title": title, "epic": epic, "deps": [], "p50": None, "p90": None,
                           "env": "", "gates": "", "security": False,
                           "conditional": conditional}
            continue
        if not cur:
            continue
        i = issues[cur]
        if line.startswith("- **Blocked by:**"):
            i["deps"] = re.findall(r"MERC-\w+", line)
        elif line.startswith("- **Estimate"):
            m = re.search(r"P50 ([\d.]+) / P90 ([\d.]+)", line)
            if m:
                i["p50"], i["p90"] = float(m.group(1)), float(m.group(2))
        elif line.startswith("- **DoR fields:**"):
            e = re.search(r"Env ([^·]+)", line)
            g = re.search(r"Gates ([^·]+)", line)
            i["env"] = e.group(1).strip() if e else ""
            i["gates"] = g.group(1).strip() if g else ""
            i["security"] = "Security label yes" in line
    for i in issues.values():
        env = i["env"]
        i["needs_mac_or_operator"] = any(t in env for t in ("T4", "T5", "ⓗ", "ROOT")) or i["id"] in ("MERC-004", "MERC-005", "MERC-020")
        i["root"] = "ROOT" in env
    return issues


def find_cycles(issues):
    color, cycles = {}, []

    def dfs(u, stack):
        color[u] = 1
        stack.append(u)
        for d in issues[u]["deps"]:
            if d not in issues:
                cycles.append([u, d, "<missing>"])
            elif color.get(d) == 1:
                cycles.append(stack[stack.index(d):] + [d])
            elif not color.get(d):
                dfs(d, stack)
        stack.pop()
        color[u] = 2

    for k in issues:
        if not color.get(k):
            dfs(k, [])
    return cycles


def critical_path(issues):
    base = {k: v for k, v in issues.items() if not v["conditional"]}
    succ = {k: [] for k in base}
    for k, v in base.items():
        for d in v["deps"]:
            if d in succ:
                succ[d].append(k)
    lp = {}

    def LP(k):
        if k not in lp:
            lp[k] = base[k]["p50"] + max([LP(c) for c in succ[k]] + [0])
        return lp[k]

    for k in base:
        LP(k)
    roots = [k for k in base if not [d for d in base[k]["deps"] if d in base]]
    cur, path = max(roots, key=lambda k: lp[k]), []
    while cur:
        path.append(cur)
        cur = max(succ[cur], key=lambda k: lp[k]) if succ[cur] else None
    down = {}

    def D(k):
        if k not in down:
            s = set()
            for c in succ[k]:
                s |= {c} | D(c)
            down[k] = s
        return down[k]

    for k in base:
        D(k)
    return path, lp, {k: len(v) for k, v in down.items()}


def cmd_dag(a):
    issues = parse_breakdown(a.breakdown)
    cycles = find_cycles(issues)
    path, lp, down = critical_path(issues)
    out = {"source": os.path.relpath(a.breakdown, REPO), "generated_at": now(), "issue_count": len(issues),
           "base_count": sum(1 for i in issues.values() if not i["conditional"]),
           "conditional": sorted(k for k, i in issues.items() if i["conditional"]),
           "cycles": cycles, "critical_path": path, "critical_path_p50": round(lp[path[0]], 1),
           "issues": {k: {**v, "longest_path_p50": round(lp.get(k, 0), 1), "downstream": down.get(k, 0)}
                      for k, v in issues.items()}}
    dest = a.out or os.path.join(HOME, "dag.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    json.dump(out, open(dest, "w"), indent=1, ensure_ascii=False)
    print(f"issues={out['issue_count']} base={out['base_count']} conditional={len(out['conditional'])} "
          f"cycles={len(cycles)} critical_path_p50={out['critical_path_p50']}d -> {dest}")
    return 1 if cycles else 0


# ---------------------------------------------------------------- ledger
def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canon(rec):
    return json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def ledger_path(task_id):
    return os.path.join(HOME, "ledger", task_id + ".jsonl")


def read_ledger(task_id):
    p = ledger_path(task_id)
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def state_of(records):
    return records[-1]["to_state"] if records else "NEW"


def gates_of(records):
    # gates recorded since the last return to RUNNING (a correction invalidates later gates)
    gates = []
    for r in records:
        if r["to_state"] == "RUNNING" and r["from_state"] != "RUNNING":
            gates = []
        if r.get("gate"):
            gates.append(r["gate"])
    return gates


def review_gates_needed(contract):
    need = ["G3"]
    if contract and (contract.get("security_sensitive") or "G4" in contract.get("required_gates", [])):
        need.append("G4")
    return need


def resolve_to(to, have, contract):
    if "|" not in to:
        return to
    return "AWAITING_INTEGRATION" if all(g in have for g in review_gates_needed(contract)) else "AWAITING_REVIEW"


def load_contract(task_id):
    p = os.path.join(HOME, "tasks", task_id + ".json")
    return load(p) if os.path.exists(p) else None


def cmd_record(a):
    recs = read_ledger(a.task)
    frm = state_of(recs)
    key = (frm, a.event)
    if key not in TRANSITIONS:
        die(f"illegal transition: {frm} --{a.event}-->")
    to, gate = TRANSITIONS[key]
    contract = load_contract(a.task)
    if a.event in ("assigned", "contract_revised", "created") or frm != "NEW":
        if contract is None and a.event != "created":
            die(f"no contract at {HOME}/tasks/{a.task}.json")
    if contract is not None:
        errs, _ = validate(contract, "task-contract")
        if errs:
            die("contract invalid, refusing to record: " + "; ".join(errs))
    have = gates_of(recs) + ([gate] if gate else [])
    to = resolve_to(to, have, contract)
    need = [g for g in REQUIRED_BEFORE.get(to, []) if g not in have]
    if to in ("AWAITING_INTEGRATION", "AWAITING_HUMAN", "COMPLETED"):
        need += [g for g in review_gates_needed(contract) if g not in have and g not in need]
    if need:
        die(f"cannot enter {to}: missing gate evidence {need}")
    if not a.evidence:
        die("at least one --evidence kind:ref is required")
    ev = []
    for e in a.evidence:
        kind, _, ref = e.partition(":")
        item = {"kind": kind, "ref": ref}
        if os.path.isfile(ref):
            item["sha256"] = hashlib.sha256(open(ref, "rb").read()).hexdigest()
        ev.append(item)
    rec = {"schema": "devorch.handoff.v1", "seq": len(recs) + 1, "task_id": a.task, "at": now(),
           "event": a.event, "from_state": frm, "to_state": to, "actor": a.actor, "evidence": ev,
           "prev_hash": recs[-1]["hash"] if recs else "GENESIS"}
    if gate:
        rec["gate"] = gate
    if contract:
        rec["contract_version"], rec["attempt"] = contract["contract_version"], contract["attempt"]
    if a.note:
        rec["note"] = a.note
    rec["hash"] = hashlib.sha256(canon(rec).encode()).hexdigest()
    errs, mode = validate(rec, "handoff-record")
    if errs:
        die("record invalid: " + "; ".join(errs))
    os.makedirs(os.path.dirname(ledger_path(a.task)), exist_ok=True)
    with open(ledger_path(a.task), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"{a.task}: {frm} -> {to} ({a.event}{', ' + gate if gate else ''}) seq={rec['seq']}")


def cmd_verify_ledger(a):
    bad = 0
    d = os.path.join(HOME, "ledger")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        recs = [json.loads(l) for l in open(os.path.join(d, fn)) if l.strip()]
        prev, state = "GENESIS", "NEW"
        for i, r in enumerate(recs, 1):
            problems = []
            if r["seq"] != i: problems.append("seq")
            if r["prev_hash"] != prev: problems.append("prev_hash")
            if hashlib.sha256(canon(r).encode()).hexdigest() != r["hash"]: problems.append("hash")
            exp = TRANSITIONS.get((state, r["event"]), ("<illegal>",))[0]
            if r["from_state"] != state or r["to_state"] not in exp.split("|"):
                problems.append("transition")
            if problems:
                bad += 1
                print(f"{fn} seq {i}: {', '.join(problems)}")
            prev, state = r["hash"], r["to_state"]
    print("ledger OK" if not bad else f"{bad} bad records")
    return 1 if bad else 0


def cmd_status(a):
    d = os.path.join(HOME, "ledger")
    rows = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        recs = read_ledger(fn[:-6])
        rows.append((fn[:-6], state_of(recs), ",".join(gates_of(recs)) or "-", recs[-1]["at"] if recs else ""))
    for r in rows:
        print("%-16s %-22s gates=%-20s last=%s" % r)
    if not rows:
        print("(no tasks in ledger at %s)" % HOME)


def cmd_ready(a):
    dag = load(a.dag or os.path.join(HOME, "dag.json"))
    tasks_dir = os.path.join(HOME, "tasks")
    by_merc = {}
    for fn in os.listdir(tasks_dir) if os.path.isdir(tasks_dir) else []:
        c = load(os.path.join(tasks_dir, fn))
        if c.get("merc_issue"):
            by_merc[c["merc_issue"]] = (c["task_id"], state_of(read_ledger(c["task_id"])))
    satisfied_gates = set(a.gate or [])
    out = []
    for k, i in dag["issues"].items():
        if i["conditional"] and k not in (a.include_conditional or []):
            continue
        if k in by_merc and by_merc[k][1] not in ("NEW", "BLOCKED", "READY"):
            continue
        deps_ok = all(d in by_merc and by_merc[d][1] == "COMPLETED" for d in i["deps"])
        gate_refs = re.findall(r"G-S\d", i.get("gates", ""))
        gates_ok = all(g in satisfied_gates for g in gate_refs)
        if deps_ok and gates_ok:
            out.append((k, i["longest_path_p50"], i["downstream"], i["needs_mac_or_operator"], i["title"], i.get("gates", "")))
    out.sort(key=lambda r: (-r[1], -r[2]))
    for k, lp, dn, mac, t, g in out:
        pre = f"  [check prerequisites: {g}]" if g and g not in ("—", "-") else ""
        print(f"{k:10} lp={lp:5} downstream={dn:3} {'MAC/OPERATOR' if mac else 'agent':12} {t}{pre}")
    if not out:
        print("(nothing READY)")


# ---------------------------------------------------------------- checks
def cmd_check_contract(a):
    c = load(a.contract)
    errs, mode = validate(c, "task-contract")
    if c.get("worktree") and not os.path.isabs(c["worktree"]):
        errs.append("worktree must be an absolute path")
    if c.get("kind") == "code_review" and c.get("assigned_agent") != "mdev-code-reviewer":
        errs.append("code_review tasks must be assigned to mdev-code-reviewer")
    if c.get("kind") in ("code_review", "security_review") and "review_target" not in c:
        errs.append("review tasks need review_target")
    report(errs, mode)


def cmd_check_result(a):
    r, c = load(a.result), load(a.contract)
    errs, mode = validate(r, "task-result")
    for k in ("task_id", "contract_version", "attempt"):
        if r.get(k) != c.get(k):
            errs.append(f"{k} mismatch (result {r.get(k)} vs contract {c.get(k)})")
    if r.get("agent") != c.get("assigned_agent"):
        errs.append("result agent is not the assigned agent")
    wt = a.repo or c["worktree"]
    if c["kind"] in ("implementation", "test", "reliability", "design", "integration", "release") and r.get("commits"):
        head = r.get("head_commit")
        if not head:
            errs.append("commits listed but head_commit missing")
        else:
            if git(["merge-base", "--is-ancestor", c["base_commit"], head], wt).returncode != 0:
                errs.append("base_commit is not an ancestor of head_commit")
            br = git(["rev-parse", c["branch"]], wt).stdout.strip()
            if br != head:
                errs.append(f"branch {c['branch']} does not point at head_commit")
            for sha in r["commits"]:
                if git(["cat-file", "-e", sha + "^{commit}"], wt).returncode != 0:
                    errs.append(f"commit {sha} does not exist")
            changed = [l for l in git(["diff", "--name-only", c["base_commit"], head], wt).stdout.split("\n") if l]
            for f in changed:
                if not any(fnmatch.fnmatch(f, p) for p in c["allowed_paths"]):
                    errs.append(f"changed file outside allowed_paths: {f}")
                if any(fnmatch.fnmatch(f, p) for p in c.get("restricted_paths", [])):
                    errs.append(f"changed restricted path: {f}")
            if sorted(set(changed)) != sorted(set(r.get("modified_files", []))):
                errs.append("modified_files does not equal git diff --name-only base..head")
    if r.get("status") == "completed":
        required = {t["id"] for t in c.get("required_tests", [])}
        passed = {t["id"] for t in r.get("tests", []) if t["outcome"] == "passed" and t["exit_code"] == 0}
        if required - passed:
            errs.append(f"required tests not passed: {sorted(required - passed)}")
        if any(f.get("blocking") for f in r.get("findings", [])) and r.get("recommendation") == "accept":
            errs.append("recommendation accept with blocking findings")
    if r.get("status") == "escalated" and "escalation" not in r:
        errs.append("escalated without escalation object")
    report(errs, mode)


def report(errs, mode):
    print(f"validation mode: {mode}")
    if errs:
        for e in errs:
            print(" - " + e)
        print("RESULT: INVALID — must not advance task state")
        sys.exit(1)
    print("RESULT: VALID (claims still require gate re-verification by the orchestrator)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("dag"); s.add_argument("--breakdown", default=BREAKDOWN); s.add_argument("--out")
    s = sp.add_parser("ready"); s.add_argument("--dag"); s.add_argument("--gate", action="append",
        help="TDD security gate already satisfied, e.g. --gate G-S1"); s.add_argument("--include-conditional", action="append")
    sp.add_parser("status")
    s = sp.add_parser("check-contract"); s.add_argument("contract")
    s = sp.add_parser("check-result"); s.add_argument("result"); s.add_argument("contract"); s.add_argument("--repo")
    s = sp.add_parser("record"); s.add_argument("--task", required=True); s.add_argument("--event", required=True)
    s.add_argument("--actor", default="principal-orchestrator"); s.add_argument("--evidence", action="append")
    s.add_argument("--note")
    sp.add_parser("verify-ledger")
    a = p.parse_args()
    fn = {"dag": cmd_dag, "ready": cmd_ready, "status": cmd_status, "check-contract": cmd_check_contract,
          "check-result": cmd_check_result, "record": cmd_record, "verify-ledger": cmd_verify_ledger}[a.cmd]
    sys.exit(fn(a) or 0)


if __name__ == "__main__":
    main()
