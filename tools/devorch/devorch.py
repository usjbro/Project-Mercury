#!/usr/bin/env python3
"""devorch v2 — durable task ledger, gate enforcement and result verification for the temporary
MERCURY *development* orchestration system (docs/mercury/development-orchestration/).

Development tooling only; NOT part of production MERCURY. Python 3.9+ standard library; full JSON
Schema validation when `jsonschema` (tested: 4.26.0) is installed, else structural checks (reported).

Layout (all paths absolute):
  REPO            the main checkout that contains this script (never a task worktree)
  DEVORCH_HOME    required; a git worktree of branch `devorch/state` (ledger, contracts, imported evidence)
      tasks/<task>.json  ledger/<task>.jsonl  evidence/<task>/attempt-N/  dag.json  facts.jsonl
      LOCK  ESCALATIONS.md  baseline.json  reports/
  DEVORCH_EVIDENCE  agent-writable evidence root, OUTSIDE DEVORCH_HOME (default: <parent of REPO>/mercury-evidence)

Writers: only the Principal Orchestrator (and the operator) run `record`, `fact`, `import-evidence`,
`push`. Specialists are blocked from running this tool by tools/devorch/hooks/specialist_guard.py
(a tripwire, not a security boundary — see 08-quality-gates-and-security.md §4).

Ledger records are canonical JSON (json.dumps sort_keys, separators (',',':'), ensure_ascii=False),
hash-chained per task (sha256 over the record without "hash"); not RFC 8785.
"""
import argparse, datetime, fnmatch, hashlib, json, os, re, shutil, subprocess, sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
DOC = os.path.join(REPO, "docs", "mercury", "development-orchestration")
SCHEMAS = os.path.join(DOC, "schemas")
BREAKDOWN = os.path.join(REPO, "docs", "mercury", "planning", "issue-breakdown.md")
ASSIGN = os.path.join(REPO, "tools", "devorch", "assignments.json")
HOME = os.environ.get("DEVORCH_HOME", "")
EVIDENCE_ROOT = os.environ.get("DEVORCH_EVIDENCE", os.path.join(os.path.dirname(REPO), "mercury-evidence"))
TEST_MODE = os.environ.get("DEVORCH_TEST_MODE") == "1"   # scratch tests only: skips the devorch/state branch check

FULL_KINDS = {"implementation", "test", "reliability", "design", "release"}
SUB_KINDS = {"code_review", "security_review", "design_review", "reliability_review", "integration"}
SHORT_KINDS = SUB_KINDS | {"planning", "mac_validation", "operator_action"}
READ_ONLY_KINDS = {"code_review", "security_review", "design_review", "reliability_review", "planning",
                   "mac_validation", "operator_action"}
KIND_AGENT = {"code_review": {"mdev-code-reviewer"}, "security_review": {"mdev-security-engineer"},
              "design_review": {"mdev-lead-architect"}, "reliability_review": {"mdev-reliability-engineer"},
              "integration": {"mdev-integration-release-engineer"}, "planning": {"mdev-tpm"},
              "mac_validation": {"mac-validation-queue"}, "operator_action": {"operator"},
              "release": {"mdev-integration-release-engineer", "mdev-devops-engineer"}}
REVIEW_GATE = {"code_review": "G3", "design_review": "G3", "reliability_review": "G3", "security_review": "G4"}
REVIEWER_KIND = {"mdev-code-reviewer": "code_review", "mdev-lead-architect": "design_review",
                 "mdev-reliability-engineer": "reliability_review", "mdev-security-engineer": "security_review"}
ACTORS = {"principal-orchestrator", "operator"}
HARD_PRECONDITIONS = ["DOD-02", "DOD-03"]   # operator facts: ruleset on main verified; development bot identity
LIMITS = {"attempt": None, "review": 3, "security": 2, "integration": 2, "env": 5}  # attempt: contract budget
NON_TERMINAL = {"BLOCKED", "READY", "RUNNING", "AWAITING_REVIEW", "AWAITING_INTEGRATION", "AWAITING_HUMAN"}

# (from_state, event) -> to_state.  "*" entries are expanded below.  FULL lifecycle unless noted.
T_FULL = {
    ("NEW", "created"): "BLOCKED",
    ("BLOCKED", "unblocked"): "READY",          # G1 recorded here (design refs approved, DoR met)
    ("READY", "assigned"): "RUNNING",
    ("RUNNING", "started"): "RUNNING",
    ("RUNNING", "dispatched"): "RUNNING",       # (re)dispatch of an agent, with session id
    ("RUNNING", "env_retry"): "RUNNING",        # environmental failure; not charged to attempts
    ("RUNNING", "attempt_failed"): "RUNNING",   # charged; next attempt needs contract attempt+1
    ("RUNNING", "implementation_completed"): "RUNNING",
    ("RUNNING", "tests_failed"): "RUNNING",
    ("RUNNING", "tests_passed"): "AWAITING_REVIEW",                  # G2, records head_commit
    ("AWAITING_REVIEW", "code_review_changes_required"): "RUNNING",
    ("AWAITING_REVIEW", "security_review_blocked"): "RUNNING",
    ("AWAITING_REVIEW", "code_review_passed"): "AWAITING_REVIEW",    # G3 (resolved below)
    ("AWAITING_REVIEW", "security_review_passed"): "AWAITING_REVIEW",  # G4 (resolved below)
    ("AWAITING_INTEGRATION", "integration_failed"): "RUNNING",
    ("AWAITING_INTEGRATION", "integration_verified"): "AWAITING_INTEGRATION",  # G5
    ("AWAITING_INTEGRATION", "pr_prepared"): "AWAITING_HUMAN",       # G6
    ("AWAITING_HUMAN", "human_changes_requested"): "RUNNING",
    ("AWAITING_HUMAN", "human_merged"): "COMPLETED",                 # G7
    ("COMPLETED", "closed"): "COMPLETED",
    ("RUNNING", "reclaimed"): "READY",
    ("BLOCKED", "resumed"): "READY",
}
T_SHORT = {
    ("NEW", "created"): "BLOCKED",
    ("BLOCKED", "unblocked"): "READY",
    ("READY", "assigned"): "RUNNING",
    ("RUNNING", "dispatched"): "RUNNING",
    ("RUNNING", "env_retry"): "RUNNING",
    ("RUNNING", "attempt_failed"): "RUNNING",
    ("RUNNING", "result_accepted"): "COMPLETED",   # valid result (or operator evidence) accepted
    ("RUNNING", "reclaimed"): "READY",
    ("BLOCKED", "resumed"): "READY",
    ("COMPLETED", "closed"): "COMPLETED",
}
for T in (T_FULL, T_SHORT):
    for s in NON_TERMINAL:
        T[(s, "escalated")] = "BLOCKED"
        T[(s, "cancelled")] = "CANCELLED"
        if s != "BLOCKED":
            T[(s, "contract_revised")] = "BLOCKED"
        if s in ("RUNNING", "AWAITING_REVIEW", "AWAITING_INTEGRATION"):
            T[(s, "failed")] = "FAILED"
            T[(s, "stale_detected")] = s
    T[("BLOCKED", "contract_revised")] = "BLOCKED"
    T[("FAILED", "contract_revised")] = "BLOCKED"   # RB-D7: revise and retry
    T[("FAILED", "cancelled")] = "CANCELLED"
T_FULL[("COMPLETED", "interface_frozen")] = "COMPLETED"    # freeze only after G7 (merged) ...
T_FULL[("AWAITING_HUMAN", "interface_frozen")] = "AWAITING_HUMAN"  # ... or after G1-G6 (stack base)

GATE_OF = {"unblocked": "G1", "tests_passed": "G2", "code_review_passed": "G3", "security_review_passed": "G4",
           "integration_verified": "G5", "pr_prepared": "G6", "human_merged": "G7"}
REQUIRED_BEFORE = {"RUNNING": ["G1"], "AWAITING_INTEGRATION": ["G1", "G2", "G3", "G4"],
                   "AWAITING_HUMAN": ["G1", "G2", "G3", "G4", "G5", "G6"], "COMPLETED": ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]}
RETURN_EVENTS = {"code_review_changes_required", "security_review_blocked", "integration_failed", "human_changes_requested"}
FILE_EVIDENCE = {"result_file", "review_file", "test_run", "log", "operator_statement", "ci_run"}


class Refused(Exception):
    pass


def die(msg, code=2):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def load(path):
    with open(path) as f:
        return json.load(f)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


GIT_SAFE = ["-c", "core.hooksPath=/dev/null", "-c", "core.quotePath=false", "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false", "-c", "protocol.ext.allow=never"]


def git(args, cwd, check=False, user_config=False):
    """Run git with hooks and fsmonitor disabled. System and global config are ignored (R5 N-02) unless
    user_config=True (only `push` and `fetch`, which need the operator's credential setup; that config is
    covered by the git baseline)."""
    env = dict(os.environ)
    if not user_config:
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    r = subprocess.run(["git", *GIT_SAFE, *args], cwd=cwd, capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def common_dir(repo):
    c = git(["rev-parse", "--git-common-dir"], repo, check=True).stdout.strip()
    return os.path.realpath(c if os.path.isabs(c) else os.path.join(repo, c))


def worktree_git(wt, common=None):
    """Return explicit --git-dir/--work-tree args for a task worktree after checking that its `.git`
    pointer is the one git created (R5 N-02: a specialist could point `.git` at a forged git dir whose
    config runs commands or whose refs lie). The main checkout itself is accepted only in test mode."""
    wt = os.path.realpath(wt)
    dotgit = os.path.join(wt, ".git")
    if os.path.isdir(dotgit) and not os.path.islink(dotgit):
        if TEST_MODE or wt == os.path.realpath(REPO):
            return [f"--git-dir={dotgit}", f"--work-tree={wt}"]
        raise Refused(f"{wt} is not a linked worktree of the main checkout")
    if os.path.islink(dotgit) or not os.path.isfile(dotgit):
        raise Refused(f"{dotgit} is not a worktree pointer file")
    txt = open(dotgit, encoding="utf-8").read().strip()
    if not txt.startswith("gitdir: "):
        raise Refused(f"{dotgit} is not a worktree pointer file")
    gd = os.path.realpath(txt[len("gitdir: "):])
    common = os.path.realpath(common or common_dir(REPO))
    if os.path.dirname(gd) != os.path.join(common, "worktrees"):
        raise Refused(f"{dotgit} points outside {common}/worktrees")
    back = os.path.join(gd, "gitdir")
    if not os.path.isfile(back) or os.path.realpath(open(back).read().strip()) != dotgit:
        raise Refused(f"{gd} does not point back to {dotgit}")
    return [f"--git-dir={gd}", f"--work-tree={wt}"]


def hidden_index_entries(gargs, cwd):
    """Files hidden from `git status` by skip-worktree or assume-unchanged (R5 N-03)."""
    out = git([*gargs, "ls-files", "-v", "-z"], cwd, check=True).stdout
    return [e[2:] for e in out.split("\0") if e and (e[0] == "S" or e[0].islower())]


def require_home():
    if "/mercury-wt/" in REPO + "/":
        die("devorch must be run from the main checkout, not from a task worktree")
    if not HOME:
        die("DEVORCH_HOME is not set")
    if not os.path.isdir(HOME):
        die(f"DEVORCH_HOME {HOME} does not exist (see 13-runbook.md RB-D1)")
    if not TEST_MODE:
        br = git(["rev-parse", "--abbrev-ref", "HEAD"], HOME).stdout.strip()
        if br != "devorch/state":
            die(f"DEVORCH_HOME must be a worktree of branch devorch/state (found '{br}')")


def hpath(*p):
    return os.path.join(HOME, *p)


# ---------------------------------------------------------------- schema validation
def parse_dt(s):
    try:
        datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def validate(obj, schema_name):
    schema = load(os.path.join(SCHEMAS, schema_name + ".schema.json"))
    errs = []
    try:
        import jsonschema
        v = jsonschema.Draft202012Validator(schema)
        errs = [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in v.iter_errors(obj)]
        mode = "full"
    except ImportError:
        mode = "structural-only (install jsonschema==4.26.0 for full validation)"
        errs += [f"missing field {k}" for k in schema.get("required", []) if k not in obj]
        errs += [f"unknown field {k}" for k in obj if k not in schema.get("properties", {})]
        if obj.get("schema") != schema["properties"]["schema"]["const"]:
            errs.append("wrong schema id")
    for f in ("created_at", "at"):
        if f in obj and not parse_dt(str(obj[f])):
            errs.append(f"{f}: not an RFC 3339 date-time")
    return errs, mode


# ---------------------------------------------------------------- glob semantics (git-like)
def glob_re(pat):
    """'**/' = zero or more directories, '**' = anything, '*' and '?' never match '/'."""
    i, out = 0, ""
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"; i += 3
        elif pat.startswith("**", i):
            out += ".*"; i += 2
        elif pat[i] == "*":
            out += "[^/]*"; i += 1
        elif pat[i] == "?":
            out += "[^/]"; i += 1
        else:
            out += re.escape(pat[i]); i += 1
    return re.compile("^" + out + "$")


def matches(path, patterns):
    return any(glob_re(p).match(path) for p in patterns)


def literal_prefix(p):
    m = re.search(r"[*?\[]", p)
    return p if not m else p[:m.start()]


def overlap(a_patterns, b_patterns):
    """Conservative: two pattern sets overlap if any literal prefixes are prefix-related."""
    for a in a_patterns:
        for b in b_patterns:
            pa, pb = literal_prefix(a), literal_prefix(b)
            if pa.startswith(pb) or pb.startswith(pa):
                return True
    return False


# ---------------------------------------------------------------- dag
def parse_breakdown(path=BREAKDOWN):
    issues, cur, epic = {}, None, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r"### (E\w+) — ", line)
        if m:
            epic = m.group(1)
            continue
        m = re.match(r"#### (MERC-\w+) — (.*)", line)
        if m:
            cur = m.group(1)
            conditional = "*(conditional)*" in m.group(2)
            issues[cur] = {"id": cur, "title": m.group(2).replace("*(conditional)*", "").strip(), "epic": epic,
                           "deps": [], "p50": None, "p90": None, "env": "", "gates": "", "security": False,
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
        i["p0_refs"] = sorted(set(re.findall(r"P0-\d+", i["gates"])))
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
    lp, down = {}, {}

    def LP(k):
        if k not in lp:
            lp[k] = base[k]["p50"] + max([LP(c) for c in succ[k]] + [0])
        return lp[k]

    def D(k):
        if k not in down:
            s = set()
            for c in succ[k]:
                s |= {c} | D(c)
            down[k] = s
        return down[k]

    for k in base:
        LP(k); D(k)
    roots = [k for k in base if not [d for d in base[k]["deps"] if d in base]]
    cur, path = max(roots, key=lambda k: lp[k]), []
    while cur:
        path.append(cur)
        cur = max(succ[cur], key=lambda k: lp[k]) if succ[cur] else None
    return path, lp, {k: len(v) for k, v in down.items()}


def cmd_dag(a):
    issues = parse_breakdown(a.breakdown)
    cycles = find_cycles(issues)
    path, lp, down = critical_path(issues)
    out = {"source": os.path.relpath(a.breakdown, REPO), "issue_count": len(issues),
           "base_count": sum(1 for i in issues.values() if not i["conditional"]),
           "conditional": sorted(k for k, i in issues.items() if i["conditional"]), "cycles": cycles,
           "critical_path": path, "critical_path_p50": round(lp[path[0]], 1),
           "counting_note": "downstream and longest-path figures exclude conditional issues",
           "issues": {k: {**v, "longest_path_p50": round(lp.get(k, 0), 1), "downstream": down.get(k, 0)}
                      for k, v in issues.items()}}
    dest = a.out or hpath("dag.json")
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"issues={out['issue_count']} base={out['base_count']} conditional={len(out['conditional'])} "
          f"cycles={len(cycles)} critical_path_p50={out['critical_path_p50']}d -> {dest}")
    return 1 if cycles else 0


# ---------------------------------------------------------------- ledger primitives
def canon(rec):
    return json.dumps({k: v for k, v in rec.items() if k != "hash"}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


CONTRACT_MUTABLE = ("status", "attempt", "evidence_dir")  # per-attempt fields; everything else is scope


def contract_core_sha(c):
    core = {k: v for k, v in c.items() if k not in CONTRACT_MUTABLE}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def ledger_files():
    d = hpath("ledger")
    return sorted(f for f in os.listdir(d) if f.endswith(".jsonl")) if os.path.isdir(d) else []


def read_ledger(task_id, repair=False):
    p = hpath("ledger", task_id + ".jsonl")
    if not os.path.exists(p):
        return []
    raw = open(p, encoding="utf-8").read()
    if raw and not raw.endswith("\n"):
        if not repair:
            raise Refused(f"{task_id}: incomplete final ledger line (crash during append?). "
                          f"Run verify-ledger --repair-tail after checking git history.")
        raw = raw[: raw.rfind("\n") + 1] if "\n" in raw else ""
        with open(p, "w", encoding="utf-8") as f:
            f.write(raw)
    return [json.loads(l) for l in raw.split("\n") if l.strip()]


def load_contract(task_id):
    p = hpath("tasks", task_id + ".json")
    return load(p) if os.path.exists(p) else None


def snapshot_path(task_id, core_sha):
    return hpath("contracts", task_id, core_sha + ".json")


def snapshot_contract(task_id, contract):
    """Keep the contract a record was judged by, addressed by its core hash. Replay applies each record's own
    contract, not the latest one, so a revision cannot reinterpret the records it supersedes (Codex review on PR #5)."""
    p = snapshot_path(task_id, contract_core_sha(contract))
    if os.path.exists(p):
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(contract, f, sort_keys=True, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def contract_of_record(task_id, rec, current):
    core = rec.get("contract_core_sha256")
    if current is None or not core:
        return current   # check_transition refuses both
    p = snapshot_path(task_id, core)
    if os.path.exists(p):
        c = load(p)
        if contract_core_sha(c) != core:
            raise Refused(f"contract snapshot {core[:12]} was edited")
        return c
    if contract_core_sha(current) == core:
        return current   # written before snapshots existed and never revised: the file is that contract
    raise Refused(f"contract snapshot {core[:12]} is missing (deleted, or the ledger predates snapshots and was revised)")


def lifecycle(contract):
    return T_SHORT if contract and contract["kind"] in SHORT_KINDS else T_FULL


def dag_issue(merc):
    p = hpath("dag.json")
    if merc and os.path.exists(p):
        return load(p)["issues"].get(merc)
    return None


def needs_g4(contract):
    if contract["kind"] not in FULL_KINDS:
        return False
    return True  # TDD DoD D6: security review for every issue (light for non-sensitive changes)


def resolve_home_ref(ref):
    """Evidence recorded in the ledger lives in DEVORCH_HOME (copied there by `record`)."""
    p = os.path.realpath(os.path.join(HOME, ref))
    return p if p.startswith(os.path.realpath(HOME) + os.sep) and os.path.isfile(p) else None


def resolve_ref(ref):
    for base in (HOME, REPO, ""):
        p = os.path.join(base, ref) if base else ref
        if os.path.isfile(p):
            return p
    return None


# ---------------------------------------------------------------- the transition validator (shared)
class Ctx:
    """Replayable state of one task ledger."""

    def __init__(self, task_id):
        self.task_id = task_id
        self.state = "NEW"
        self.gates = []          # gates since the last return to RUNNING (G1 survives)
        self.head = None
        self.attempt = None
        self.core_sha = None
        self.counts = {"attempt": 0, "review": 0, "security": 0, "integration": 0, "env": 0}
        self.prev = "GENESIS"
        self.seq = 0
        self.frozen = {}
        self.pr_head = None
        self.impl_head = None    # head_commit of the last checked implementation_completed (R5 N1)
        self.need_bump = False   # a correction is pending: the next dispatch must carry attempt + 1
        self.contract_version = None


def check_transition(ctx, rec, contract, live):
    """Raise Refused if `rec` is not a legal next record for ctx. `live` = also verify external facts
    (subtask ledgers, git, files) — done at record time; replay re-checks what is stable."""
    ev, actor = rec["event"], rec["actor"]
    if actor not in ACTORS:
        raise Refused(f"actor must be one of {sorted(ACTORS)} (agents never write the ledger)")
    if contract is None:
        raise Refused("no contract for task")
    T = lifecycle(contract)
    key = (ctx.state, ev)
    if key not in T:
        raise Refused(f"illegal transition for kind {contract['kind']}: {ctx.state} --{ev}-->")
    to = T[key]
    gate = GATE_OF.get(ev) if T is T_FULL or ev == "unblocked" else None
    # contract integrity: core may change only via contract_revised (which needs a higher version)
    core = rec.get("contract_core_sha256")
    if not core:
        raise Refused("record lacks contract_core_sha256")
    if ctx.core_sha and core != ctx.core_sha and ev != "contract_revised":
        raise Refused("contract changed without a contract_revised record")
    if ev == "contract_revised" and ctx.core_sha and core == ctx.core_sha:
        raise Refused("contract_revised but the contract core did not change")
    # attempt discipline
    att = rec.get("attempt")
    if ctx.state in ("AWAITING_REVIEW", "AWAITING_INTEGRATION", "AWAITING_HUMAN") and to == "RUNNING":
        pass  # the correction's attempt bump is checked at the next 'dispatched'
    if ev == "dispatched" and ctx.attempt is not None and att is not None:
        if att < ctx.attempt:
            raise Refused("attempt number went backwards")
        if ctx.need_bump and att != ctx.attempt + 1:
            raise Refused(f"a correction must be dispatched as attempt {ctx.attempt + 1}")
    if ev == "contract_revised" and ctx.contract_version is not None and rec["contract_version"] <= ctx.contract_version:
        raise Refused("contract_revised needs a higher contract_version")
    if ev == "implementation_completed" and not rec.get("head_commit") and contract["kind"] in FULL_KINDS:
        raise Refused("implementation_completed must record head_commit (the result's head)")
    # budgets
    if ev in ("attempt_failed", "tests_failed"):
        if ctx.counts["attempt"] + 1 >= contract["budget"]["max_attempts"]:
            raise Refused(f"attempt budget {contract['budget']['max_attempts']} exhausted: record 'failed' or 'escalated'")
    lim = {"code_review_changes_required": "review", "security_review_blocked": "security",
           "integration_failed": "integration", "env_retry": "env"}.get(ev)
    if lim and ctx.counts[lim] + 1 > LIMITS[lim]:
        raise Refused(f"{lim} loop budget {LIMITS[lim]} exhausted: record 'failed' or 'escalated'")
    # duplicate gates
    if gate and gate in ctx.gates:
        raise Refused(f"gate {gate} already recorded since the last correction")
    have = ctx.gates + ([gate] if gate else [])
    # gate-specific evidence
    kinds = {e["kind"] for e in rec["evidence"]}
    if ev == "unblocked" and "design_ref" not in kinds:
        raise Refused("G1 needs design_ref evidence (operator-approved design commit)")
    if ev == "tests_passed":
        if not rec.get("head_commit"):
            raise Refused("tests_passed must record head_commit (the tested tip)")
        if "test_run" not in kinds:
            raise Refused("tests_passed needs test_run evidence from the orchestrator's own re-run")
        if ctx.impl_head != rec["head_commit"]:
            raise Refused("tests_passed head is not the head of a checked implementation_completed in this attempt")
    if ev in ("code_review_passed", "security_review_passed", "integration_verified"):
        subs = [e["ref"] for e in rec["evidence"] if e["kind"] == "subtask"]
        if not subs:
            raise Refused(f"{ev} needs subtask evidence (a COMPLETED review/integration task)")
        if live:
            for s in subs:
                verify_subtask(s, ev, ctx, contract)
    if ev == "code_review_passed" and live:
        for r in contract.get("required_reviewers", []):
            k = REVIEWER_KIND.get(r)
            if k and k != "security_review" and not any(subtask_kind(s) == k for s in
                                                         [e["ref"] for e in rec["evidence"] if e["kind"] == "subtask"]):
                raise Refused(f"G3 requires a passed {k} by {r} (required_reviewers)")
    if ev == "pr_prepared":
        if "pr" not in kinds or "ci_run" not in kinds or not rec.get("head_commit"):
            raise Refused("pr_prepared needs pr and ci_run evidence and head_commit")
        if rec["head_commit"] != ctx.head:
            raise Refused("pushed head differs from the tested and reviewed head")
    if ev == "human_merged":
        if "github_merge" not in kinds or rec.get("head_commit") != ctx.pr_head:
            raise Refused("human_merged needs github_merge evidence and head_commit equal to the G6 head")
    if ev == "result_accepted":
        if contract["kind"] in ("mac_validation", "operator_action"):
            if actor != "operator" or not ({"operator_statement", "result_file", "log"} & kinds):
                raise Refused("operator/Mac task completion is recorded by the operator with a hashed evidence file")
        elif "result_file" not in kinds:
            raise Refused("result_accepted needs a validated result_file")
    if ev == "interface_frozen":
        if not rec.get("frozen_files"):
            raise Refused("interface_frozen needs frozen_files {path: sha256}")
    # resolve review-gate target state
    if ev in ("code_review_passed", "security_review_passed"):
        to = "AWAITING_INTEGRATION" if all(g in have for g in ["G3"] + (["G4"] if needs_g4(contract) else [])) else "AWAITING_REVIEW"
    need = [g for g in REQUIRED_BEFORE.get(to, []) if g not in have]
    if T is T_FULL and to != ctx.state and need:
        if not (to == "AWAITING_INTEGRATION" and need == ["G4"] and not needs_g4(contract)):
            raise Refused(f"cannot enter {to}: missing gates {need}")
    if T is T_SHORT and to == "RUNNING" and "G1" not in have:
        raise Refused("cannot enter RUNNING without G1")
    return to, gate


def apply(ctx, rec, to, gate):
    ev = rec["event"]
    if to == "RUNNING" and ctx.state != "RUNNING":
        ctx.gates = [g for g in ctx.gates if g == "G1"]
    if gate:
        ctx.gates.append(gate)
    if to == "RUNNING" and ctx.state != "RUNNING":
        ctx.impl_head = None
        if ctx.state in ("AWAITING_REVIEW", "AWAITING_INTEGRATION", "AWAITING_HUMAN"):
            ctx.need_bump = True
    if ev in ("attempt_failed", "tests_failed"):
        ctx.impl_head, ctx.need_bump = None, True
    if ev == "dispatched":
        ctx.need_bump = False
    if ev == "implementation_completed":
        ctx.impl_head = rec.get("head_commit")
    if ev == "tests_passed":
        ctx.head = rec["head_commit"]
    if ev == "pr_prepared":
        ctx.pr_head = rec["head_commit"]
    if ev == "interface_frozen":
        ctx.frozen.update(rec["frozen_files"])
    for e, k in (("attempt_failed", "attempt"), ("tests_failed", "attempt"), ("code_review_changes_required", "review"),
                 ("security_review_blocked", "security"), ("integration_failed", "integration"), ("env_retry", "env")):
        if ev == e:
            ctx.counts[k] += 1
    if ev == "contract_revised":
        ctx.counts = {k: 0 for k in ctx.counts}
        ctx.gates = [g for g in ctx.gates if g == "G1"]
        ctx.frozen, ctx.impl_head, ctx.need_bump = {}, None, False
    ctx.contract_version = rec.get("contract_version", ctx.contract_version)
    ctx.core_sha = rec["contract_core_sha256"]
    if rec.get("attempt") is not None:
        ctx.attempt = rec["attempt"]
    ctx.state, ctx.prev, ctx.seq = to, rec["hash"], rec["seq"]


def verify_file_evidence(rec):
    for e in rec["evidence"]:
        if e["kind"] in FILE_EVIDENCE:
            p = resolve_home_ref(e["ref"])
            if not p:
                raise Refused(f"evidence {e['ref']} missing from DEVORCH_HOME")
            if hashlib.sha256(open(p, "rb").read()).hexdigest() != e.get("sha256"):
                raise Refused(f"evidence {e['ref']} changed after it was recorded")


def replay(task_id, live=True, contract_file_check=True):
    """Re-apply every rule `record` applies (R5 N2/N-05): transitions, gates, subtask bindings,
    required reviewers, evidence file hashes, and the contract file against the last record. Each record is judged
    by the contract it was recorded under (`contracts/<task>/<core sha>.json`); only the last is compared with the file."""
    ctx = Ctx(task_id)
    contract = load_contract(task_id)
    for i, r in enumerate(read_ledger(task_id), 1):
        if r["seq"] != i or r["prev_hash"] != ctx.prev:
            raise Refused(f"{task_id} seq {i}: chain broken")
        if hashlib.sha256(canon(r).encode()).hexdigest() != r["hash"]:
            raise Refused(f"{task_id} seq {i}: hash mismatch")
        try:
            to, gate = check_transition(ctx, r, contract_of_record(task_id, r, contract), live)
            verify_file_evidence(r)
        except Refused as e:
            raise Refused(f"{task_id} seq {i} ({r['event']}): {e}")
        if to != r["to_state"] or r["from_state"] != ctx.state:
            raise Refused(f"{task_id} seq {i}: recorded {r['from_state']}->{r['to_state']}, rules give {ctx.state}->{to}")
        apply(ctx, r, to, gate)
    if live and contract_file_check and ctx.core_sha and contract and contract_core_sha(contract) != ctx.core_sha:
        raise Refused(f"{task_id}: contract file edited after the last record (record contract_revised)")
    return ctx


def subtask_kind(task_id):
    c = load_contract(task_id)
    return c["kind"] if c else None


def verify_subtask(sub_id, ev, parent_ctx, parent_contract):
    c = load_contract(sub_id)
    if not c:
        raise Refused(f"subtask {sub_id} has no contract")
    if c["kind"] != "integration" and c.get("parent_task_id") != parent_ctx.task_id:
        raise Refused(f"subtask {sub_id} does not belong to {parent_ctx.task_id}")
    sctx = replay(sub_id)
    if sctx.state != "COMPLETED":
        raise Refused(f"subtask {sub_id} is {sctx.state}, not COMPLETED")
    want = {"code_review_passed": {"code_review", "design_review", "reliability_review"},
            "security_review_passed": {"security_review"}, "integration_verified": {"integration"}}[ev]
    if c["kind"] not in want:
        raise Refused(f"subtask {sub_id} kind {c['kind']} cannot provide {ev}")
    res = accepted_result(sub_id)
    if c["kind"] in REVIEW_GATE:
        if res.get("recommendation") not in ("accept", "accept_with_conditions"):
            raise Refused(f"review {sub_id} did not accept")
        if any(f.get("blocking") for f in res.get("findings", [])):
            raise Refused(f"review {sub_id} has blocking findings")
        if res.get("reviewed_head_commit") != parent_ctx.head or c["review_target"]["head_commit"] != parent_ctx.head:
            raise Refused(f"review {sub_id} is not bound to the current tested head {parent_ctx.head}")
    if c["kind"] == "integration":
        if parent_ctx.task_id not in c.get("covers_tasks", []):
            raise Refused(f"integration {sub_id} does not cover {parent_ctx.task_id}")
        if res.get("status") != "completed" or res.get("recommendation") not in ("accept", "accept_with_conditions"):
            raise Refused(f"integration {sub_id} did not pass")
        heads = {x.split("@")[0]: x.split("@")[1] for x in res.get("integrated_heads", [])}
        if heads.get(parent_ctx.task_id) != parent_ctx.head:
            raise Refused(f"integration {sub_id} integrated a different head of {parent_ctx.task_id}")


def accepted_result(sub_id):
    recs = read_ledger(sub_id)
    acc = [r for r in recs if r["event"] == "result_accepted"]
    if not acc:
        raise Refused(f"{sub_id} has no accepted result")
    item = [e for e in acc[-1]["evidence"] if e["kind"] == "result_file"]
    p = resolve_home_ref(item[0]["ref"]) if item else None
    if not p:
        raise Refused(f"{sub_id} accepted result file not found in DEVORCH_HOME")
    data = open(p, "rb").read()
    if hashlib.sha256(data).hexdigest() != item[0].get("sha256"):
        raise Refused(f"{sub_id} accepted result changed after acceptance")
    return json.loads(data)


# ---------------------------------------------------------------- commands: record / verify / status
def cmd_record(a):
    require_home()
    contract = load_contract(a.task)
    if contract is None:
        die(f"no contract at {hpath('tasks', a.task + '.json')}")
    errs, _ = validate(contract, "task-contract")
    if not errs:
        # ownership again on `assigned`: two tasks created while both were inactive pass the creation check, and
        # only one of them may enter RUNNING with overlapping paths (Codex review on PR #2; devplat: 17-... §9 rule 4)
        errs = contract_errors(contract, ownership=a.event in ("created", "contract_revised", "assigned"))
    if errs:
        die("contract invalid, refusing to record: " + "; ".join(errs))
    try:
        ctx = replay(a.task, contract_file_check=False)   # the new record itself is checked against the file
    except Refused as e:
        die(f"ledger does not verify, refusing to append: {e}")
    if not a.evidence:
        die("at least one --evidence kind:ref is required")
    ev = []
    for e in a.evidence:
        kind, _, ref = e.partition(":")
        if not ref:
            die(f"evidence '{e}' has an empty ref")
        item = {"kind": kind, "ref": ref}
        if kind in FILE_EVIDENCE:
            p = resolve_ref(ref)
            if not p:
                die(f"evidence file not found (relative to DEVORCH_HOME or repo): {ref}")
            data = open(p, "rb").read()   # read once; the copy in HOME is what the ledger trusts (R5 N-04)
            item["sha256"] = hashlib.sha256(data).hexdigest()
            item["source"] = os.path.abspath(p)
            item["ref"] = os.path.join("evidence", a.task, "records",
                                       f"{ctx.seq + 1:04d}-{kind}-{item['sha256'][:12]}-{os.path.basename(p)}")
            item["_data"] = data
        ev.append(item)
    rec = {"schema": "devorch.handoff.v1", "seq": ctx.seq + 1, "task_id": a.task, "at": now(), "event": a.event,
           "from_state": ctx.state, "actor": a.actor, "evidence": ev, "prev_hash": ctx.prev,
           "contract_version": contract["contract_version"], "attempt": contract["attempt"],
           "contract_core_sha256": contract_core_sha(contract)}
    if a.head:
        rec["head_commit"] = a.head
    if a.session:
        rec["session"] = a.session
    if a.frozen:
        rec["frozen_files"] = dict(x.split("=", 1) for x in a.frozen)
    if a.note:
        rec["note"] = a.note
    try:
        to, gate = check_transition(ctx, {**rec, "to_state": "?", "hash": "?"}, contract, live=True)
    except Refused as e:
        die(str(e))
    if a.event in ("implementation_completed", "result_accepted") and contract["kind"] not in ("mac_validation", "operator_action"):
        items = [e for e in ev if e["kind"] == "result_file"]
        if not items:
            die(f"{a.event} needs a result_file")
        res = json.loads(items[0]["_data"])
        errs, _ = result_errors(contract, res, items[0]["source"], allow_copy=TEST_MODE and a.allow_copy)
        if res.get("status") != "completed":
            errs.append(f"result status is {res.get('status')}, not completed")
        if a.event == "implementation_completed" and res.get("head_commit") != a.head:
            errs.append("--head must equal the result's head_commit")
        if errs:
            die(f"{a.event} refused, result does not check: " + "; ".join(errs))
    if a.event == "unblocked":   # G1 means READY by the same rules as `ready` (R5 M2)
        if contract.get("merc_issue") and contract["kind"] not in SUB_KINDS:
            dagp = hpath("dag.json")
            if not os.path.exists(dagp):
                die("G1 needs $DEVORCH_HOME/dag.json (devorch.py dag --out) to check dependencies")
            issue = load(dagp)["issues"].get(contract["merc_issue"])
            if not issue:
                die(f"{contract['merc_issue']} is not in dag.json")
            by_merc, _ = primary_contracts()
            bl = issue_blockers(contract["merc_issue"], issue, by_merc, satisfied_facts(), load(ASSIGN).get("_tdd_gates", {}))
        else:
            bl = contract_dep_blockers(contract)
        if bl:
            die("not READY, refusing G1: " + "; ".join(bl))
    if a.event == "tests_passed":
        try:
            g = worktree_git(contract["worktree"])
            tip = git([*g, "rev-parse", f"refs/heads/{contract['branch']}"], contract["worktree"], check=True).stdout.strip()
        except Refused as e:
            die(str(e))
        if tip != a.head:
            die(f"tests_passed head {a.head} is not the branch tip {tip}")
    for e in ev:
        if "_data" in e:
            dst = hpath(e["ref"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(e.pop("_data"))
                f.flush(); os.fsync(f.fileno())
    rec["evidence"] = ev
    rec["to_state"] = to
    if gate:
        rec["gate"] = gate
    rec["hash"] = hashlib.sha256(canon(rec).encode()).hexdigest()
    errs, _ = validate(rec, "handoff-record")
    if errs:
        die("record invalid: " + "; ".join(errs))
    snapshot_contract(a.task, contract)   # before the append: a snapshot without a record is harmless, the reverse is not
    os.makedirs(hpath("ledger"), exist_ok=True)
    with open(hpath("ledger", a.task + ".jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    print(f"{a.task}: {ctx.state} -> {to} ({a.event}{', ' + gate if gate else ''}) seq={rec['seq']}")


def cmd_verify_ledger(a):
    require_home()
    bad = 0
    for fn in ledger_files():
        tid = fn[:-6]
        try:
            if a.repair_tail:
                read_ledger(tid, repair=True)
            replay(tid)
        except Refused as e:
            bad += 1
            print(str(e))
    if a.remote:
        remote_files = git(["ls-tree", "--name-only", f"{a.remote}:ledger"], HOME).stdout.split()
        for fn in sorted(set(f for f in remote_files if f.endswith(".jsonl")) - set(ledger_files())):
            bad += 1
            print(f"{fn}: present on {a.remote} but deleted locally")
        for fn in ledger_files():
            r = git(["show", f"{a.remote}:ledger/{fn}"], HOME)
            if r.returncode != 0:
                continue  # new local ledger, not yet pushed
            local = open(hpath("ledger", fn), encoding="utf-8").read()
            if not local.startswith(r.stdout):
                bad += 1
                print(f"{fn}: local ledger is not an extension of {a.remote} (truncated or rewritten)")
    print("ledger OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


def cmd_status(a):
    require_home()
    for fn in ledger_files():
        tid = fn[:-6]
        try:
            ctx = replay(tid)
            c = load_contract(tid) or {}
            print(f"{tid:16} {c.get('kind', '?'):16} {ctx.state:22} gates={','.join(ctx.gates) or '-':20} "
                  f"attempt={ctx.attempt} head={(ctx.head or '-')[:10]}")
        except Refused as e:
            print(f"{tid:16} INVALID: {e}")
    if not ledger_files():
        print(f"(no tasks in ledger at {HOME})")


# ---------------------------------------------------------------- facts (TDD gates, P0 checks, identity)
def read_facts():
    p = hpath("facts.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()] if os.path.exists(p) else []


def cmd_fact(a):
    require_home()
    if a.actor != "operator":
        die("facts (TDD gates G-S*, P0 checks, identity) are recorded by the operator only")
    if not a.evidence:
        die("evidence required")
    rec = {"at": now(), "kind": a.kind, "id": a.id, "status": a.status, "actor": a.actor, "evidence": a.evidence}
    with open(hpath("facts.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush(); os.fsync(f.fileno())
    print(f"fact {a.kind} {a.id} = {a.status}")


def satisfied_facts():
    s = set()
    for f in read_facts():
        if f["status"] in ("verified", "accepted", "recorded"):
            s.add(f["id"])
        elif f["status"] in ("revoked", "failed"):
            s.discard(f["id"])
    return s


# ---------------------------------------------------------------- ready
def primary_contracts():
    by_merc, problems = {}, []
    for fn in sorted(f for f in os.listdir(hpath("tasks")) if f.endswith(".json")) if os.path.isdir(hpath("tasks")) else []:
        c = load(hpath("tasks", fn))
        if c.get("parent_task_id") or c["kind"] in SUB_KINDS or not c.get("merc_issue"):
            continue
        st = replay(c["task_id"]).state
        if c["merc_issue"] in by_merc and by_merc[c["merc_issue"]][1] not in ("CANCELLED", "FAILED"):
            problems.append(f"duplicate primary tasks for {c['merc_issue']}: {by_merc[c['merc_issue']][0]}, {c['task_id']}")
        by_merc[c["merc_issue"]] = (c["task_id"], st, c)
    return by_merc, problems


def contract_dep_blockers(c):
    out = []
    for ic in c.get("interface_contracts", []):
        fctx = replay(ic["frozen_by"]) if load_contract(ic["frozen_by"]) else None
        if not fctx or fctx.frozen.get(ic["path"]) != ic["sha256"]:
            out.append(f"interface {ic['path']} not frozen at the contracted sha256 by {ic['frozen_by']}")
    for dep in c.get("dependencies", []):
        if not load_contract(dep["task_id"]):
            out.append(f"dependency {dep['task_id']} has no contract")
            continue
        dctx = replay(dep["task_id"])
        ok = {"INTERFACE_FROZEN": bool(dctx.frozen), "AWAITING_HUMAN": dctx.state in ("AWAITING_HUMAN", "COMPLETED")}.get(
            dep["required_state"], dctx.state == "COMPLETED")
        if not ok:
            out.append(f"dependency {dep['task_id']} not {dep['required_state']}")
    return out


def issue_blockers(k, i, by_merc, facts, gate_map):
    """Everything that keeps MERC issue k from READY (used by `ready` and by `record unblocked`)."""
    out = []
    c = by_merc[k][2] if k in by_merc else None
    relaxed = set()   # DAG deps whose required state a contract dependency relaxes (RA-D3 interface freeze)
    for dep in (c or {}).get("dependencies", []):
        dc = load_contract(dep["task_id"]) or {}
        if dep["required_state"] != "COMPLETED" and dc.get("merc_issue"):
            relaxed.add(dc["merc_issue"])
    out += [f"{d} not COMPLETED" for d in i["deps"] if d not in relaxed and not (d in by_merc and by_merc[d][1] == "COMPLETED")]
    if c:
        out += contract_dep_blockers(c)
    tdd = re.findall(r"G-S\d", i.get("gates", "")) + gate_map.get(k, [])
    out += [f"fact {g}" for g in tdd + i.get("p0_refs", []) if g not in facts]
    if c and c["kind"] in FULL_KINDS:
        out += [f"fact {f}" for f in HARD_PRECONDITIONS if f not in facts]
    return out


def cmd_ready(a):
    require_home()
    dag = load(a.dag or hpath("dag.json"))
    assign = load(ASSIGN)
    gate_map = assign.get("_tdd_gates", {})
    facts = satisfied_facts()
    by_merc, problems = primary_contracts()
    for p in problems:
        print("ERROR: " + p)
    out = []
    for k, i in dag["issues"].items():
        if i["conditional"] and k not in (a.include_conditional or []):
            continue
        if k in by_merc and by_merc[k][1] not in ("NEW", "BLOCKED", "READY"):
            continue
        blockers = issue_blockers(k, i, by_merc, facts, gate_map)
        if not blockers:
            out.append((k, i["longest_path_p50"], i["downstream"], i["needs_mac_or_operator"], i["title"]))
        elif a.verbose:
            print(f"{k:10} waiting for: {'; '.join(blockers)}")
    out.sort(key=lambda r: (-r[1], -r[2]))
    for k, lp, dn, mac, t in out:
        print(f"{k:10} lp={lp:5} downstream={dn:3} {'OPERATOR/MAC' if mac else 'agent':12} {t}")
    if not out:
        print("(nothing READY)")
    return 1 if problems else 0


# ---------------------------------------------------------------- contract / result checks
def active_primary_paths(exclude):
    res = []
    if not os.path.isdir(hpath("tasks")):
        return res
    for fn in os.listdir(hpath("tasks")):
        c = load(hpath("tasks", fn))
        if c["task_id"] == exclude or c["kind"] in READ_ONLY_KINDS or c.get("parent_task_id"):
            continue
        try:
            st = replay(c["task_id"]).state
        except Refused:
            st = "?"
        if st in ("RUNNING", "AWAITING_REVIEW", "AWAITING_INTEGRATION", "AWAITING_HUMAN"):
            res.append((c["task_id"], c["allowed_paths"]))
    return res


def cmd_check_contract(a):
    c = load(a.contract)
    errs, mode = validate(c, "task-contract")
    if not errs:
        errs = contract_errors(c)
    report(errs, mode)


def contract_errors(c, ownership=True):
    """Semantic contract rules. Run by check-contract and, on every record, by `record` (R5 M6)."""
    errs = []
    if True:
        if not os.path.isabs(c["worktree"]) or not os.path.isabs(c["evidence_dir"]):
            errs.append("worktree and evidence_dir must be absolute paths")
        if HOME and os.path.abspath(c["evidence_dir"]).startswith(os.path.abspath(HOME) + os.sep):
            errs.append("evidence_dir must be outside DEVORCH_HOME (agents never write the ledger worktree)")
        allowed = KIND_AGENT.get(c["kind"])
        if allowed and c["assigned_agent"] not in allowed:
            errs.append(f"kind {c['kind']} must be assigned to {sorted(allowed)}")
        if c["kind"] in SUB_KINDS:
            if c.get("merc_issue"):
                errs.append("review/integration subtasks must have merc_issue null")
            if c["kind"] == "integration" and not c.get("covers_tasks"):
                errs.append("integration tasks need covers_tasks")
            if c["kind"] != "integration" and not c.get("parent_task_id"):
                errs.append("review subtasks need parent_task_id")
            # id convention: reviews <parent>-rN/-sN, integration <first covered task>-iN
            owner = c.get("parent_task_id") if c["kind"] != "integration" else (c.get("covers_tasks") or [None])[0]
            suffix = "i" if c["kind"] == "integration" else ("s" if c["kind"] == "security_review" else "r")
            if owner and not re.fullmatch(re.escape(owner) + f"-{suffix}[0-9]+", c["task_id"]):
                errs.append(f"subtask id must be {owner}-{suffix}<n>")
        if c["kind"] in REVIEW_GATE and "review_target" not in c:
            errs.append("review tasks need review_target")
        if c["kind"] in READ_ONLY_KINDS and c["allowed_paths"] != []:
            errs.append("read-only kinds must have allowed_paths []")
        for p in c["allowed_paths"]:
            if matches(p.replace("**", "x").replace("*", "x"), c.get("restricted_paths", [])):
                errs.append(f"allowed path {p} falls inside restricted_paths")
        if ownership and HOME and c["allowed_paths"]:
            for tid, paths in active_primary_paths(c["task_id"]):
                if overlap(c["allowed_paths"], paths):
                    errs.append(f"path ownership conflict with active task {tid}")
    return errs


def changed_files(wt, base, tip, gargs=()):
    r = git([*gargs, "diff", "--no-renames", "--name-only", "-z", base, tip], wt, check=True)
    return sorted(f for f in r.stdout.split("\0") if f)


def cmd_check_result(a):
    c = load(a.contract)
    errs, mode = validate(c, "task-contract")
    if errs:
        report(["contract: " + e for e in errs], mode)
    r = load(a.result)
    errs, mode = result_errors(c, r, a.result, a.allow_copy, a.repo)
    report(errs, mode)


def result_errors(c, r, result_path, allow_copy=False, repo=None):
    """All mechanical checks of a result against its contract and git. Used by check-result and,
    live, by `record` for implementation_completed / result_accepted (R0: a result is never accepted
    without these checks)."""
    errs, mode = validate(r, "task-result")
    for k in ("task_id", "contract_version", "attempt"):
        if r.get(k) != c.get(k):
            errs.append(f"{k} mismatch (result {r.get(k)} vs contract {c.get(k)})")
    if r.get("agent") != c.get("assigned_agent"):
        errs.append("result agent is not the assigned agent")
    expected_path = os.path.join(c["evidence_dir"], "result.json")
    if os.path.abspath(result_path) != os.path.abspath(expected_path) and not allow_copy:
        errs.append(f"result must be read from {expected_path} (written by the agent before returning)")
    wt = repo or c["worktree"]
    try:
        g = worktree_git(wt)
        tip = git([*g, "rev-parse", "--verify", f"refs/heads/{c['branch']}"], wt, check=True).stdout.strip()
        if git([*g, "merge-base", "--is-ancestor", c["base_commit"], tip], wt).returncode != 0:
            errs.append("base_commit is not an ancestor of the branch tip")
        changed = changed_files(wt, c["base_commit"], tip, g)
        rev = [x for x in git([*g, "rev-list", "--reverse", f"{c['base_commit']}..{tip}"], wt, check=True).stdout.split() if x]
        dirty = git([*g, "status", "--porcelain", "--untracked-files=all"], wt, check=True).stdout.strip()
        wt_head = git([*g, "rev-parse", "HEAD"], wt, check=True).stdout.strip()
        hidden = hidden_index_entries(g, wt)
        if hidden:
            errs.append(f"index entries hidden from status (skip-worktree/assume-unchanged): {hidden[:5]}")
        if c["kind"] in READ_ONLY_KINDS:
            target = c.get("review_target", {}).get("head_commit")
            if r.get("commits") or (target and tip != target and c["kind"] in REVIEW_GATE):
                errs.append("read-only task: branch moved or commits reported")
            if dirty:
                errs.append("read-only task left the worktree modified")
        else:
            if dirty:
                errs.append("worktree has uncommitted or untracked changes")
            if wt_head != tip:
                errs.append("worktree HEAD is not the branch tip")
            if rev and r.get("head_commit") != tip:
                errs.append("head_commit is not the branch tip")
            if sorted(r.get("commits", [])) != sorted(rev):
                errs.append("commits must equal git rev-list base..tip")
            if sorted(set(r.get("modified_files", []))) != changed:
                errs.append("modified_files does not equal git diff --no-renames base..tip")
            allowed = list(c["allowed_paths"])
            restricted = list(c.get("restricted_paths", []))
            if c["kind"] == "integration":
                # an integration branch carries the covered tasks' reviewed heads: its scope is the union of
                # their scopes plus its own, and every integrated head must be the covered task's tested head
                heads = dict(x.split("@", 1) for x in r.get("integrated_heads", []))
                for t in c.get("covers_tasks", []):
                    tc = load_contract(t)
                    if not tc:
                        errs.append(f"covered task {t} has no contract")
                        continue
                    allowed += tc["allowed_paths"]
                    restricted += tc.get("restricted_paths", [])
                    h = heads.get(t)
                    if not h:
                        errs.append(f"integrated_heads lacks covered task {t}")
                    elif git([*g, "merge-base", "--is-ancestor", h, tip], wt).returncode != 0:
                        errs.append(f"integrated head of {t} is not contained in the integration tip")
                    elif replay(t).head != h:
                        errs.append(f"integrated head of {t} is not its tested head")
            for f in changed:
                if not matches(f, allowed):
                    errs.append(f"changed file outside allowed_paths: {f}")
                if matches(f, restricted):
                    errs.append(f"changed restricted path: {f}")
    except Refused as e:
        errs.append(str(e))
    if c["kind"] in REVIEW_GATE:
        tgt = c["review_target"]["head_commit"]
        if r.get("reviewed_head_commit") != tgt:
            errs.append("reviewed_head_commit must equal review_target.head_commit")
        rec = r.get("recommendation")
        if rec is None:
            errs.append("review result needs a recommendation")
        if rec in ("accept", "accept_with_conditions") and any(f.get("blocking") for f in r.get("findings", [])):
            errs.append("recommendation accept with blocking findings")
    required = {t["id"] for t in c.get("required_tests", [])}
    reported = {t["id"]: t for t in r.get("tests", [])}
    if r.get("status") == "completed":
        if c["kind"] in REVIEW_GATE:
            if required - set(reported):
                errs.append(f"review must report an outcome for every required test: {sorted(required - set(reported))}")
            if r.get("recommendation") in ("accept", "accept_with_conditions"):
                bad = [t for t in required if t in reported and (reported[t]["outcome"] != "passed" or reported[t]["exit_code"] != 0)]
                if bad:
                    errs.append(f"accept with failing required tests: {bad}")
        elif c["kind"] not in ("mac_validation", "operator_action", "planning"):
            missing = [t for t in required if t not in reported or reported[t]["outcome"] != "passed" or reported[t]["exit_code"] != 0]
            if missing:
                errs.append(f"required tests not passed: {sorted(missing)}")
    if r.get("status") == "escalated" and "escalation" not in r:
        errs.append("escalated without escalation object")
    return errs, mode


def report(errs, mode):
    print(f"validation mode: {mode}")
    if errs:
        for e in errs:
            print(" - " + e)
        print("RESULT: INVALID — must not advance task state")
        sys.exit(1)
    print("RESULT: VALID (claims still require gate re-verification by the orchestrator)")


# ---------------------------------------------------------------- evidence import, git baseline, push, lock
def cmd_import_evidence(a):
    require_home()
    c = load_contract(a.task)
    if not c:
        die("no contract")
    src = c["evidence_dir"]
    dst = hpath("evidence", a.task, f"attempt-{c['attempt']}")
    if not os.path.isdir(src):
        die(f"evidence_dir {src} missing")
    os.makedirs(dst, exist_ok=True)
    manifest = {}
    for root, _, files in os.walk(src):
        for fn in files:
            sp = os.path.join(root, fn)
            if os.path.islink(sp):
                continue
            rel = os.path.relpath(sp, src)
            dp = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            shutil.copyfile(sp, dp)
            manifest[rel] = hashlib.sha256(open(dp, "rb").read()).hexdigest()
    with open(os.path.join(dst, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
    print(f"imported {len(manifest)} files -> {os.path.relpath(dst, HOME)}")


BASELINE_PATHS = [".claude", "CLAUDE.md", "tools/devorch", ".gitignore"]
USER_BASELINE = ["~/.gitconfig", "~/.config/git/config", "~/.claude/settings.json", "~/.claude/settings.local.json"]


def baseline_snapshot():
    common = git(["rev-parse", "--git-common-dir"], REPO, check=True).stdout.strip()
    common = common if os.path.isabs(common) else os.path.join(REPO, common)
    snap = {"git_config": hashlib.sha256(open(os.path.join(common, "config"), "rb").read()).hexdigest()}
    hooks = os.path.join(common, "hooks")
    snap["git_hooks"] = {f: hashlib.sha256(open(os.path.join(hooks, f), "rb").read()).hexdigest()
                         for f in sorted(os.listdir(hooks)) if not f.endswith(".sample")
                         and os.path.isfile(os.path.join(hooks, f))} if os.path.isdir(hooks) else {}
    # user-level configuration that changes what git push/fetch or Claude Code do (R5 N-02)
    user = {}
    for p in USER_BASELINE:
        full = os.path.expanduser(p)
        user[p] = hashlib.sha256(open(full, "rb").read()).hexdigest() if os.path.isfile(full) else None
    snap["user_config"] = user
    files = {}
    for p in BASELINE_PATHS:
        full = os.path.join(REPO, p)
        targets = [full] if os.path.isfile(full) else [os.path.join(r, f) for r, _, fs in os.walk(full) for f in fs
                                                       if "__pycache__" not in r]
        for t in targets:
            files[os.path.relpath(t, REPO)] = hashlib.sha256(open(t, "rb").read()).hexdigest()
    snap["files"] = files
    return snap


def cmd_git_baseline(a):
    require_home()
    p = hpath("baseline.json")
    snap = baseline_snapshot()
    if a.action == "record":
        with open(p, "w") as f:
            json.dump(snap, f, indent=1, sort_keys=True)
        print("baseline recorded")
        return 0
    if not os.path.exists(p):
        die("no baseline recorded")
    old = load(p)
    diffs = []
    if old["git_config"] != snap["git_config"]:
        diffs.append(".git/config changed")
    if old["git_hooks"] != snap["git_hooks"]:
        diffs.append(f"git hooks changed: {snap['git_hooks']}")
    # user configuration is what push/fetch run with (git(..., user_config=True)); it was snapshotted but never
    # compared (Codex review on PR #2). A baseline recorded before this check exists must be re-recorded.
    if "user_config" not in old:
        diffs.append("baseline has no user configuration snapshot: the operator re-records it (git-baseline record)")
    else:
        for k in sorted(set(old["user_config"]) | set(snap["user_config"])):
            if old["user_config"].get(k) != snap["user_config"].get(k):
                diffs.append(f"user configuration changed: {k}")
    for k in sorted(set(old["files"]) | set(snap["files"])):
        if old["files"].get(k) != snap["files"].get(k):
            diffs.append(f"changed: {k}")
    for d in diffs:
        print(" - " + d)
    print("baseline OK" if not diffs else "BASELINE VIOLATION — stop and escalate (S-05)")
    return 1 if diffs else 0


def cmd_push(a):
    require_home()
    if cmd_git_baseline(argparse.Namespace(action="verify")) != 0:
        die("refusing to push: baseline violation")
    if a.ledger:
        ref, cwd = "devorch/state", HOME
    else:
        c = load_contract(a.task)
        try:
            ctx = replay(a.task)
        except Refused as e:
            die(f"refusing to push: ledger does not verify: {e}")
        ref, cwd = c["branch"], REPO
        if not re.match(r"^dev/[a-z0-9-]+$", ref) or c["kind"] not in FULL_KINDS or "-int-" in ref:
            die("only dev/* branches of full-lifecycle tasks may be pushed (integration branches stay local)")
        if ctx.state != "AWAITING_INTEGRATION":
            die(f"push only from AWAITING_INTEGRATION (task is {ctx.state})")
        missing = [f for f in HARD_PRECONDITIONS if f not in satisfied_facts()]
        if missing:
            die(f"refusing to push: operator facts missing {missing} (DOD-02 ruleset, DOD-03 development identity)")
        tip = git(["rev-parse", f"refs/heads/{ref}"], REPO, check=True).stdout.strip()
        if ctx.head != tip:
            die(f"branch tip {tip} is not the tested head {ctx.head}")
        if not all(g in ctx.gates for g in ("G1", "G2", "G3", "G4", "G5")):
            die(f"push needs G1-G5 (have {ctx.gates})")
    url = git(["config", "--get", "remote.origin.url"], cwd, check=True).stdout.strip()
    r = git(["push", url, f"refs/heads/{ref}:refs/heads/{ref}"], cwd, user_config=True)
    print(r.stdout + r.stderr)
    return r.returncode


def cmd_lock(a):
    require_home()
    p = hpath("LOCK")
    cur = load(p) if os.path.exists(p) else None
    if a.action in ("acquire", "refresh"):
        if cur and cur["session"] != a.session and not a.force:
            die(f"LOCK held by session {cur['session']} since {cur['at']}: confirm with the operator, then --force")
        with open(p, "w") as f:
            json.dump({"session": a.session, "at": now()}, f)
        print(f"lock {a.action}d by {a.session}")
    elif a.action == "release":
        if cur and cur["session"] == a.session:
            os.remove(p)
        print("lock released")
    else:
        print(json.dumps(cur) if cur else "(no lock)")


def cmd_preflight(a):
    """Run at the start of every tick: ledger verifies (also against the pushed branch), the ledger
    worktree has no foreign changes, the git baseline holds, the lock is ours."""
    require_home()
    ok = True
    # LOCK is rewritten by `lock acquire|refresh` and committed with the ledger at the end of the tick
    # (the pushed LOCK is what another machine sees), so it alone does not make HOME dirty
    dirty = "\n".join(l for l in git(["status", "--porcelain", "--untracked-files=all"], HOME).stdout.splitlines()
                      if l[3:].strip() != "LOCK").strip()
    if dirty:
        ok = False
        print("DEVORCH_HOME has uncommitted changes (only the orchestrator writes, then commits each tick):\n" + dirty)
    if git(["remote"], HOME).stdout.strip():
        f = git(["fetch", "origin", "devorch/state"], HOME, user_config=True)
        if f.returncode != 0 and git(["ls-remote", "--exit-code", "origin", "devorch/state"], HOME, user_config=True).returncode != 2:
            ok = False
            print("cannot fetch origin/devorch/state: the remote comparison would be stale")
    has_remote = git(["rev-parse", "--verify", "origin/devorch/state"], HOME).returncode == 0
    if cmd_verify_ledger(argparse.Namespace(repair_tail=False, remote="origin/devorch/state" if has_remote else None)):
        ok = False
    if cmd_git_baseline(argparse.Namespace(action="verify")):
        ok = False
    lk = load(hpath("LOCK")) if os.path.exists(hpath("LOCK")) else None
    if not lk or lk["session"] != a.session:
        ok = False
        print(f"LOCK not held by this session ({lk})")
    print("PREFLIGHT OK" if ok else "PREFLIGHT FAILED — do not dispatch")
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("dag"); s.add_argument("--breakdown", default=BREAKDOWN); s.add_argument("--out")
    s = sp.add_parser("ready"); s.add_argument("--dag"); s.add_argument("--include-conditional", action="append")
    s.add_argument("--verbose", action="store_true")
    sp.add_parser("status")
    s = sp.add_parser("check-contract"); s.add_argument("contract")
    s = sp.add_parser("check-result"); s.add_argument("result"); s.add_argument("contract"); s.add_argument("--repo")
    s.add_argument("--allow-copy", action="store_true", help="tests/examples only: result not at evidence_dir/result.json")
    s = sp.add_parser("record"); s.add_argument("--task", required=True); s.add_argument("--event", required=True)
    s.add_argument("--actor", default="principal-orchestrator"); s.add_argument("--evidence", action="append")
    s.add_argument("--head"); s.add_argument("--session"); s.add_argument("--frozen", action="append",
                   help="path=sha256 (interface_frozen)"); s.add_argument("--note")
    s.add_argument("--allow-copy", action="store_true", help="DEVORCH_TEST_MODE only: result not at evidence_dir/result.json")
    s = sp.add_parser("verify-ledger"); s.add_argument("--repair-tail", action="store_true"); s.add_argument("--remote")
    s = sp.add_parser("fact"); s.add_argument("--kind", required=True, choices=["tdd_gate", "p0_check", "identity", "decision"])
    s.add_argument("--id", required=True); s.add_argument("--status", required=True,
                   choices=["verified", "accepted", "recorded", "failed", "revoked"])
    s.add_argument("--actor", default="principal-orchestrator"); s.add_argument("--evidence", action="append")
    s = sp.add_parser("import-evidence"); s.add_argument("task")
    s = sp.add_parser("git-baseline"); s.add_argument("action", choices=["record", "verify"])
    s = sp.add_parser("push"); g = s.add_mutually_exclusive_group(required=True); g.add_argument("--task")
    g.add_argument("--ledger", action="store_true")
    s = sp.add_parser("lock"); s.add_argument("action", choices=["acquire", "refresh", "release", "show"])
    s.add_argument("--session", default=""); s.add_argument("--force", action="store_true")
    s = sp.add_parser("preflight"); s.add_argument("--session", required=True)
    a = p.parse_args()
    fn = {"dag": cmd_dag, "ready": cmd_ready, "status": cmd_status, "check-contract": cmd_check_contract,
          "check-result": cmd_check_result, "record": cmd_record, "verify-ledger": cmd_verify_ledger,
          "fact": cmd_fact, "import-evidence": cmd_import_evidence, "git-baseline": cmd_git_baseline,
          "push": cmd_push, "lock": cmd_lock, "preflight": cmd_preflight}[a.cmd]
    try:
        sys.exit(fn(a) or 0)
    except Refused as e:
        die(str(e))


if __name__ == "__main__":
    main()
