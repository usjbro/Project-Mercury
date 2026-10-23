#!/usr/bin/env python3
"""Tests for platform/db/roles.sql + schema.sql against a REAL PostgreSQL 16 server (psql via subprocess; no psycopg).

Self-contained inside platform/ (R6 A-04): the devorch rule expectation is the vendored platform/db/devorch_v2_rules.json,
the role catalogue is platform/agents/execution-profiles.yaml. An optional cross-check against tools/devorch runs only
when that directory exists.

Server selection:
  1. DEVPLAT_PG_HOST / DEVPLAT_PG_PORT / DEVPLAT_PG_USER (a superuser) if set, else the Amendment-001 scratch server
     (socket dir <scratchpad>/pg, port 55432, user devplat).
  2. If that server does not answer, PostgreSQL 16 binaries are present and we run as root, an EPHEMERAL private instance
     is started as `nobody` in a fresh mkdtemp directory and stopped and deleted at the end (DEVPLAT_PG_NO_EPHEMERAL=1
     disables this).
Each run creates database devplat_test_<random> (owned by a LOGIN migrator role) and roles dpt_<random>_*, and drops
them at the end. The schema is applied AS THE MIGRATOR (R6 D9), not as a superuser.

Run:  python3 platform/db/test_schema.py   (not `-m unittest platform...`: `platform` shadows the stdlib module)
"""
import hashlib, json, os, secrets, shutil, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(PLATFORM, ".."))
SCHEMA = os.environ.get("DEVPLAT_SCHEMA", os.path.join(HERE, "schema.sql"))   # override: mutation checks
ROLES_SQL = os.path.join(HERE, "roles.sql")
RULES = json.load(open(os.path.join(HERE, "devorch_v2_rules.json")))
CATALOGUE = os.path.join(PLATFORM, "agents", "execution-profiles.yaml")
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(PLATFORM, "controller"))
import jobspec as JOBSPEC  # noqa: E402
DEFAULT_SOCK = "/tmp/claude-0/-home-user-Project-Mercury/16854e63-26a2-5af1-9adb-3e58b440561e/scratchpad/pg"
PGBIN = "/usr/lib/postgresql/16/bin"

SUFFIX = secrets.token_hex(4)
DB = f"devplat_test_{SUFFIX}"
R = {k: f"dpt_{SUFFIX}_{k}" for k in ("owner", "migrator", "ctl", "api", "ro", "mg", "ag")}
EXTRA_ROLES = []
CONN = {}
EPHEMERAL = {}
ISSUER = "https://idp.example.test"
OPERATOR = "operator-jb"
HOLDER = "ctrl-0"
HARD = ["DOD-02", "DOD-13"]          # this test project's config value of review_gates.hard_preconditions


class PgError(Exception):
    pass


def _psql_args(db, user=None):
    return ["psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-h", CONN["host"], "-p", str(CONN["port"]),
            "-U", user or CONN["user"], "-d", db]


def psql(sql, role=None, db=None, check=True, user=None):
    """Run SQL in a fresh session (optionally `SET ROLE role` first). Returns stdout; raises PgError on error."""
    text = (f'SET ROLE "{role}";\n' if role else "") + sql
    r = subprocess.run(_psql_args(db or DB, user), input=text, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise PgError(r.stderr.strip())
    return r.stdout.strip()


def server_up(host, port, user):
    r = subprocess.run(["psql", "-X", "-At", "-h", host, "-p", str(port), "-U", user, "-d", "postgres", "-c", "select 1"],
                       capture_output=True, text=True)
    return r.returncode == 0


def start_ephemeral():
    d = tempfile.mkdtemp(prefix="devplat-pgtest-", dir="/tmp")
    shutil.chown(d, "nobody", "nogroup")
    os.chmod(d, 0o700)
    run = lambda *a: subprocess.run(["runuser", "-u", "nobody", "--", *a], capture_output=True, text=True, check=True)
    run(f"{PGBIN}/initdb", "-D", f"{d}/data", "-U", "devplat", "--auth=trust", "-E", "UTF8", "--no-locale")
    port = 55400 + secrets.randbelow(90)
    run(f"{PGBIN}/pg_ctl", "-D", f"{d}/data", "-l", f"{d}/log", "-w", "-o", f"-k {d} -p {port} -c listen_addresses=", "start")
    EPHEMERAL.update(dir=d, port=port)
    return d, port


def stop_ephemeral():
    if EPHEMERAL:
        subprocess.run(["runuser", "-u", "nobody", "--", f"{PGBIN}/pg_ctl", "-D", f"{EPHEMERAL['dir']}/data", "-w",
                        "-m", "fast", "stop"], capture_output=True, text=True)
        shutil.rmtree(EPHEMERAL["dir"], ignore_errors=True)


def role_vars():
    out = []
    for var, key in (("role_owner", "owner"), ("role_migrator", "migrator"), ("role_controller", "ctl"), ("role_api", "api"),
                     ("role_readonly", "ro"), ("role_model_gateway", "mg"), ("role_artifact_gateway", "ag")):
        out += ["-v", f"{var}={R[key]}"]
    return out


def load_catalogue():
    import yaml
    raw = open(CATALOGUE, "rb").read()
    profiles = yaml.safe_load(raw)["profiles"]
    return profiles, hashlib.sha256(raw).hexdigest()


def setUpModule():
    host = os.environ.get("DEVPLAT_PG_HOST", DEFAULT_SOCK)
    port = int(os.environ.get("DEVPLAT_PG_PORT", "55432"))
    user = os.environ.get("DEVPLAT_PG_USER", "devplat")
    if server_up(host, port, user):
        CONN.update(host=host, port=port, user=user, mode=f"server at {host}:{port}")
    elif os.environ.get("DEVPLAT_PG_NO_EPHEMERAL") != "1" and os.path.exists(f"{PGBIN}/initdb") and os.geteuid() == 0:
        d, p = start_ephemeral()
        CONN.update(host=d, port=p, user="devplat", mode=f"EPHEMERAL instance (configured server {host}:{port} not reachable)")
    else:
        raise unittest.SkipTest(f"no PostgreSQL server at {host}:{port}")
    # cluster bootstrap (administrator): migrator login = database owner (CNPG initdb.owner), then roles.sql
    psql(f'CREATE ROLE "{R["migrator"]}" LOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB', db="postgres")
    r = subprocess.run(_psql_args("postgres") + role_vars() + ["-f", ROLES_SQL], capture_output=True, text=True)
    if r.returncode != 0:
        tearDownModule()
        raise RuntimeError("roles.sql failed:\n" + r.stderr)
    psql(f'CREATE DATABASE "{DB}" OWNER "{R["migrator"]}"', db="postgres")
    # migration AS THE MIGRATOR LOGIN (falls back to SET ROLE only if the server refuses the login)
    args = _psql_args(DB, R["migrator"])
    pre = []
    if not server_up_as(R["migrator"]):
        args, pre = _psql_args(DB), ["-c", f'SET ROLE "{R["migrator"]}"']
        CONN["mode"] += "; schema applied via SET ROLE migrator (login refused)"
    else:
        CONN["mode"] += "; schema applied by the migrator login"
    r = subprocess.run(args + role_vars() + pre + ["-f", SCHEMA], capture_output=True, text=True)
    if r.returncode != 0:
        tearDownModule()
        raise RuntimeError("schema.sql failed to load:\n" + r.stderr)
    profiles, digest = load_catalogue()
    psql(f"SELECT devplat.load_role_catalogue('test-{digest[:12]}', {lit(digest)}, {lit(profiles)})", role=R["migrator"])
    psql(f"SELECT devplat.set_mandatory_hard_preconditions({arr(HARD)})", role=R["migrator"])
    psql(f"SELECT devplat.set_operator_identities({lit(ISSUER)}, 'devplat-api', {lit([{'subject': OPERATOR}])})",
         role=R["migrator"])
    print(f"\n[test_schema] PostgreSQL: {CONN['mode']}; database {DB}", file=sys.stderr)


def server_up_as(user):
    r = subprocess.run(_psql_args(DB, user) + ["-c", "select 1"], capture_output=True, text=True)
    return r.returncode == 0


def tearDownModule():
    try:
        if CONN:
            psql(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)', db="postgres", check=False)
            for role in EXTRA_ROLES + [R[k] for k in ("ctl", "api", "ro", "mg", "ag", "owner", "migrator")]:
                psql(f'DROP ROLE IF EXISTS "{role}"', db="postgres", check=False)
    finally:
        stop_ephemeral()


# ------------------------------------------------------------------------------------------------- helpers
def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v).replace("'", "''") + "'::jsonb"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def arr(xs):
    return "ARRAY[" + ",".join(lit(x) for x in xs) + "]::text[]" if xs else "NULL::text[]"


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def head(n):
    return hashlib.sha1(f"head-{n}".encode()).hexdigest()


ROLE_FOR = {"implementation": "mdev-backend-engineer", "test": "mdev-test-automation-engineer",
            "design": "mdev-lead-architect", "code_review": "mdev-code-reviewer", "design_review": "mdev-lead-architect",
            "reliability_review": "mdev-reliability-engineer", "security_review": "mdev-security-engineer",
            "integration": "mdev-integration-release-engineer", "planning": "mdev-tpm", "mac_validation": None,
            "operator_action": None, "plan_proposal": "planner"}
# Kinds devplat adds to the ported devorch vocabulary (SHORT, read-only); everything else must equal devorch.
DEVPLAT_SHORT_RO_KINDS = ["plan_proposal"]
READ_ONLY = set(RULES["read_only_kinds"]) | set(DEVPLAT_SHORT_RO_KINDS)
TOKENS = {}


class Base(unittest.TestCase):
    project = None
    status = "active"

    @classmethod
    def setUpClass(cls):
        cls.project = cls.project or ("p" + secrets.token_hex(3))
        cls.make_project(cls.project, cls.status)

    @classmethod
    def make_project(cls, p, status="active", hard=HARD, cost=100, linear_fact=None):
        profiles, _ = load_catalogue()
        roles = {x["role"]: x["kinds"] for x in profiles}
        up = lambda st: psql(
            f"SELECT devplat.upsert_project({lit(p)}, 'Test {p}', 'owner/{p}', NULL, 'cfg-1', 'projects/{p}.yaml@abc', "
            f"{lit(st)}, 'standard', {arr(hard)}, {lit(roles)}, {lit(cost)}, NULL, '{{}}'::jsonb)", role=R["ctl"])
        up("onboarding" if status in ("active", "onboarding") else status)
        if status == "active":
            for key in hard:
                cls.fact(key, "verified", project=p)
            up("active")

    @classmethod
    def fact(cls, key, status="verified", value=None, task=None, subject=OPERATOR, auth_age_s=5, project="__cls__"):
        project = cls.project if project == "__cls__" else project
        jti = secrets.token_hex(8)
        return int(psql(f"SELECT devplat.record_operator_fact({lit(project)}, {lit(key)}, {lit(status)}, {lit(value or {})}, "
                        f"{lit(task)}, 'statement', {lit(subject)}, {lit(ISSUER)}, 'op@example.test', "
                        f"now() - interval '{auth_age_s} seconds', {lit(jti)}, NULL)", role=R["api"]))

    def artifact(self, content, kind="result", project=None):
        h = sha(content)
        psql(f"SELECT * FROM devplat.register_artifact({lit(project or self.project)}, {lit(h)}, {len(content)}, 'application/json', "
             f"{lit(kind)}, NULL, NULL, NULL, 'evidence')", role=R["ctl"])
        return h

    def fev(self, kind, content=None, project=None):
        h = self.artifact(content or f"{kind}-{secrets.token_hex(6)}", "log" if kind in ("log", "test_run", "ci_run") else "result",
                          project=project)
        return {"kind": kind, "ref": f"sha256/{h}", "sha256": h}

    def body(self, tid, kind, **kw):
        b = {"kind": kind, "task_id": tid, "assigned_agent": ROLE_FOR[kind],
             "allowed_paths": [] if kind in READ_ONLY else [f"src/{tid.lower()}/**"],
             "restricted_paths": ["docs/**", ".github/**"], "required_tests": [], "required_reviewers": []}
        if kind == "implementation":
            b["required_tests"] = [{"id": "unit", "command": "npm test"}]
            b["required_reviewers"] = ["mdev-code-reviewer", "mdev-security-engineer"]
        b.update(kw)
        return b

    def new_task(self, tid, kind, parent=None, covers=None, body=None, max_attempts=3, version=1, origin="controller",
                 project=None):
        p = project or self.project
        tok = int(psql(f"SELECT devplat.create_task({lit(p)}, {lit(tid)}, {lit(kind)}, {lit(parent)}, {arr(covers)}, NULL, "
                       f"{lit(HOLDER)}, 3600)", role=R["ctl"]))
        TOKENS[(p, tid)] = tok
        self.contract(tid, version, body or self.body(tid, kind), max_attempts, origin=origin, project=p)
        self.ev(tid, "created", [{"kind": "ledger", "ref": "created"}], version=version, project=p)
        return tok

    def contract(self, tid, version, body, max_attempts=3, origin="controller", project=None):
        p = project or self.project
        body = dict(body, contract_version=version)
        core = sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
        psql(f"SELECT devplat.register_contract({lit(p)}, {lit(tid)}, {version}, {lit(core)}, {lit(body)}, {max_attempts}, "
             f"{lit(origin)}, {lit(HOLDER)}, {TOKENS[(p, tid)]})", role=R["ctl"])
        return core

    def ev(self, tid, event, evidence, head_commit=None, payload=None, attempt=1, version=1, holder=HOLDER, token=None,
           key=None, outbox=None, project=None):
        p = project or self.project
        out = psql(f"SELECT r_seq, r_from_state, r_to_state, coalesce(r_gate,''), r_replayed FROM devplat.record_event("
                   f"{lit(p)}, {lit(tid)}, {lit(event)}, {version}, {attempt}, {lit(holder)}, "
                   f"{token if token is not None else TOKENS[(p, tid)]}, {lit(evidence)}, {lit(head_commit)}, "
                   f"{lit(payload or {})}, {lit(key)}, {lit(outbox or [])})", role=R["ctl"])
        seq, frm, to, gate, replayed = out.split("|")
        return {"seq": int(seq), "from": frm, "to": to, "gate": gate, "replayed": replayed == "t"}

    def refused(self, fn, *needles):
        with self.assertRaises(PgError) as cm:
            fn()
        for n in needles:
            self.assertIn(n, str(cm.exception))
        return str(cm.exception)

    def task(self, tid, project=None):
        out = psql(f"SELECT state, array_to_string(gates, ','), counts::text, coalesce(head_commit,''), attempt "
                   f"FROM devplat.tasks WHERE project_id = {lit(project or self.project)} AND task_id = {lit(tid)}")
        st, gates, counts, h, att = out.split("|")
        return {"state": st, "gates": [g for g in gates.split(",") if g], "counts": json.loads(counts), "head": h,
                "attempt": int(att) if att else None}

    def chain_problems(self, tid=None):
        return psql(f"SELECT v_task_id || ':' || coalesce(v_seq::text, '-') || ':' || v_problem "
                    f"FROM devplat.verify_chain({lit(self.project)}, {lit(tid)})")

    def result(self, tid, kind, attempt=1, version=1, **kw):
        r = {"task_id": tid, "contract_version": version, "attempt": attempt, "agent": ROLE_FOR[kind], "status": "completed",
             "tests": [], "findings": []}
        r.update(kw)
        return r

    # --- flows
    DR = {"kind": "design_ref", "ref": "docs/design.md§1@" + "a" * 40}

    def to_running(self, tid, project=None):
        self.ev(tid, "unblocked", [self.DR], project=project)
        self.ev(tid, "assigned", [{"kind": "ledger", "ref": "assigned"}], project=project)
        self.ev(tid, "dispatched", [{"kind": "job", "ref": f"dp-{tid.lower()}-a1"}], project=project)

    def admit(self, tid, role, attempt=1, project=None):
        p = project or self.project
        return int(psql(f"SELECT devplat.record_admission({lit(p)}, {lit(tid)}, {attempt}, {lit(role)}, 'admit', 'admitted', "
                        f"NULL, {lit(HOLDER)}, {TOKENS[(p, tid)]})", role=R["ctl"]))

    def dispatch(self, tid, role, attempt=1, dispatch_no=None, key=None, project=None):
        p = project or self.project
        if dispatch_no is None:   # next ordinal for (task, attempt, role): e.g. a second verifier run
            dispatch_no = int(psql(f"SELECT coalesce(max(dispatch_no), 0) + 1 FROM devplat.job_runs WHERE project_id = {lit(p)} "
                                   f"AND task_id = {lit(tid)} AND attempt = {attempt} AND role = {lit(role)}"))
        adm = self.admit(tid, role, attempt, project=p)
        # the controller's own formulas (platform/controller/jobspec.py), so a name or key collision between the
        # roles of one attempt (e.g. implementer and verifier, R6 re-check RA-1) fails here as it would in production
        core = psql(f"SELECT c.core_sha256 FROM devplat.task_contracts c JOIN devplat.tasks t USING (project_id, task_id) "
                    f"WHERE t.project_id = {lit(p)} AND t.task_id = {lit(tid)} AND c.contract_version = t.contract_version")
        key = key or JOBSPEC.idempotency_key(p, tid, core, attempt, role, dispatch_no)
        name = JOBSPEC.job_name(p, tid, attempt, role, dispatch_no)
        out = psql(f"SELECT r_job_id FROM devplat.dispatch_job({lit(p)}, {lit(tid)}, {attempt}, {lit(role)}, {dispatch_no}, "
                   f"{adm}, {lit(key)}, NULL, 'proj-{p}-exec', {lit(name)}, {lit(HOLDER)}, {TOKENS[(p, tid)]})", role=R["ctl"])
        return int(out)

    def verify_tests(self, tid, h, attempt=1, tests=("unit",), outcome="passed"):
        jid = self.dispatch(tid, "verifier", attempt)
        for t in tests:
            psql(f"SELECT devplat.record_test_run({jid}, {lit(h)}, {lit(t)}, {lit(outcome)}, {0 if outcome == 'passed' else 1}, "
                 f"NULL, {lit(HOLDER)}, {TOKENS[(self.project, tid)]})", role=R["ctl"])

    def implement_and_test(self, tid, h, attempt=1, tests=("unit",)):
        res = self.result(tid, "implementation", attempt=attempt, head_commit=h,
                          tests=[{"id": t, "exit_code": 0, "outcome": "passed"} for t in tests])
        self.ev(tid, "implementation_completed", [self.fev("result_file")], head_commit=h, attempt=attempt, payload={"result": res})
        self.verify_tests(tid, h, attempt, tests)
        return self.ev(tid, "tests_passed", [self.fev("test_run")], head_commit=h, attempt=attempt)

    def subtask(self, sid, kind, parent=None, covers=None, result=None, review_head=None):
        extra = {}
        if review_head:
            extra = {"parent_task_id": parent, "review_target": {"implementation_task_id": parent, "head_commit": review_head}}
        if covers:
            extra["covers_tasks"] = covers
        self.new_task(sid, kind, parent=parent, covers=covers, body=self.body(sid, kind, **extra))
        self.to_running(sid)
        return self.ev(sid, "result_accepted", [self.fev("result_file")], payload={"result": self.result(sid, kind, **(result or {}))})

    def full_to_review(self, tid, **body):
        self.new_task(tid, "implementation", body=self.body(tid, "implementation", **body))
        self.to_running(tid)
        self.implement_and_test(tid, head(tid))
        return head(tid)

    def accept_review(self, h, **kw):
        return dict({"recommendation": "accept", "reviewed_head_commit": h, "findings": []}, **kw)


# ------------------------------------------------------------------------------------------------- tests
class T01RulesPorted(Base):
    def test_transitions_table_matches_vendored_devorch_rules(self):
        want = {(r[0], r[1], r[2], r[3], r[4] or "") for r in RULES["transitions"]}
        got = {tuple(l.split("|")) for l in psql(
            "SELECT lifecycle, from_state, event, to_state, coalesce(gate,'') FROM devplat.transitions").splitlines()}
        self.assertEqual(len(want), 86)
        self.assertEqual(got, want)
        req = {}
        for l in psql("SELECT to_state, gate FROM devplat.gate_prerequisites").splitlines():
            s, g = l.split("|")
            req.setdefault(s, set()).add(g)
        self.assertEqual(req, {k: set(v) for k, v in RULES["required_before"].items()})
        lim = dict(l.split("|") for l in psql("SELECT counter, coalesce(max_count::text,'') FROM devplat.loop_counters").splitlines())
        self.assertEqual({k: (int(v) if v else None) for k, v in lim.items()}, RULES["limits"])
        kinds = dict(l.split("|") for l in psql("SELECT kind, lifecycle FROM devplat.task_kinds").splitlines())
        self.assertEqual(sorted(k for k, v in kinds.items() if v == "SHORT"), sorted(RULES["short_kinds"] + DEVPLAT_SHORT_RO_KINDS))
        self.assertEqual(sorted(k for k, v in kinds.items() if v == "FULL"), RULES["full_kinds"])
        ro = psql("SELECT string_agg(kind, ',' ORDER BY kind) FROM devplat.task_kinds WHERE read_only").split(",")
        self.assertEqual(ro, sorted(RULES["read_only_kinds"] + DEVPLAT_SHORT_RO_KINDS))
        # every catalogue kind run by a Job is a DB kind with the same lifecycle, read-only flag and suffix
        import yaml
        cat = {k["kind"]: k for k in yaml.safe_load(open(CATALOGUE))["kind_catalogue"]}
        db = {l.split("|")[0]: l.split("|")[1:] for l in
              psql("SELECT kind, lifecycle, read_only, coalesce(subtask_suffix, '') FROM devplat.task_kinds").splitlines()}
        self.assertEqual(set(cat), set(db))
        for k, c in cat.items():
            self.assertEqual(db[k], [c["lifecycle"].upper(), "t" if c["read_only"] else "f", c.get("subtask_suffix", "")], k)

    @unittest.skipUnless(os.path.isdir(os.path.join(REPO, "tools", "devorch")), "tools/devorch not present (optional cross-check)")
    def test_vendored_rules_still_equal_devorch_source(self):
        sys.dont_write_bytecode = True
        sys.path.insert(0, os.path.join(REPO, "tools", "devorch"))
        import devorch as d
        rows = []
        for name, T in (("FULL", d.T_FULL), ("SHORT", d.T_SHORT)):
            for (f, e), t in sorted(T.items()):
                rows.append([name, f, e, t, d.GATE_OF.get(e) if (name == "FULL" or e == "unblocked") else None])
        self.assertEqual(rows, RULES["transitions"])
        self.assertEqual(d.REQUIRED_BEFORE, RULES["required_before"])
        self.assertEqual(d.LIMITS, RULES["limits"])

    def test_no_project_or_role_literals_seeded(self):
        text = open(SCHEMA).read()
        code = "\n".join(l.split("--")[0] for l in text.splitlines())
        for lit_ in ("mdev-", "DOD-", "mercury", "jupiter", "MERC-", "G-S"):
            self.assertNotIn(lit_, code, f"seeded literal {lit_} in schema.sql")
        profiles, _ = load_catalogue()
        got = dict(l.split("|") for l in psql("SELECT role, array_to_string(kinds, ',') FROM devplat.roles").splitlines())
        self.assertEqual(got, {p["role"]: ",".join(p["kinds"]) for p in profiles})
        self.assertEqual(psql("SELECT string_agg(DISTINCT network_class, ',' ORDER BY network_class) FROM devplat.roles"),
                         ",".join(sorted({p["network_class"] for p in profiles})))


class T02HappyPath(Base):
    def test_legal_happy_path_to_completed(self):
        t = "HP-0001"
        h = self.full_to_review(t)
        self.assertEqual(self.task(t)["state"], "AWAITING_REVIEW")
        self.subtask(f"{t}-r1", "code_review", parent=t, result=self.accept_review(h), review_head=h)
        self.subtask(f"{t}-s1", "security_review", parent=t, result=self.accept_review(h), review_head=h)
        r = self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r1"}])
        self.assertEqual((r["to"], r["gate"]), ("AWAITING_REVIEW", "G3"))
        r = self.ev(t, "security_review_passed", [{"kind": "subtask", "ref": f"{t}-s1"}])
        self.assertEqual((r["to"], r["gate"]), ("AWAITING_INTEGRATION", "G4"))
        self.subtask(f"{t}-i1", "integration", covers=[t],
                     result={"recommendation": "accept", "integrated_heads": [f"{t}@{h}"]})
        self.assertEqual(self.ev(t, "integration_verified", [{"kind": "subtask", "ref": f"{t}-i1"}])["gate"], "G5")
        r = self.ev(t, "pr_prepared", [{"kind": "pr", "ref": "owner/repo#1"}, self.fev("ci_run")], head_commit=h,
                    outbox=[{"target": "github", "operation": "open_draft_pr", "dedup_key": f"gh:{self.project}:{t}:pr"}])
        self.assertEqual((r["to"], r["gate"]), ("AWAITING_HUMAN", "G6"))
        r = self.ev(t, "human_merged", [{"kind": "github_merge", "ref": "owner/repo#1 merged_by operator"}], head_commit=h)
        self.assertEqual((r["to"], r["gate"]), ("COMPLETED", "G7"))
        self.ev(t, "closed", [{"kind": "ledger", "ref": "closed"}])
        st = self.task(t)
        self.assertEqual(st["state"], "COMPLETED")
        self.assertEqual(st["gates"], ["G1", "G2", "G3", "G4", "G5", "G6", "G7"])
        for x in (t, f"{t}-r1", f"{t}-s1", f"{t}-i1"):
            self.assertEqual(self.chain_problems(x), "", x)
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.task_events WHERE project_id = {lit(self.project)} AND task_id = {lit(t)}"), "12")
        self.assertEqual(psql(f"SELECT DISTINCT config_version || '/' || assurance_mode FROM devplat.task_events "
                              f"WHERE project_id = {lit(self.project)}"), "cfg-1/standard")


class T03Refusals(Base):
    def test_illegal_transition_refused(self):
        t = "IL-0001"
        self.new_task(t, "implementation")
        self.refused(lambda: self.ev(t, "assigned", [{"kind": "ledger", "ref": "x"}]),
                     "illegal transition for kind implementation: BLOCKED --assigned-->")
        self.ev(t, "unblocked", [self.DR])
        self.refused(lambda: self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=head(1)),
                     "illegal transition", "READY --tests_passed-->")
        self.refused(lambda: self.ev(t, "human_merged", [{"kind": "github_merge", "ref": "x"}], head_commit=head(1)),
                     "illegal transition")
        self.assertEqual(self.task(t)["state"], "READY")
        self.assertEqual(self.chain_problems(t), "")

    def test_g1_hard_preconditions_are_project_scoped(self):
        t = "G1-0001"
        self.new_task(t, "implementation")
        self.refused(lambda: self.ev(t, "unblocked", [{"kind": "ledger", "ref": "x"}]), "G1 needs design_ref")
        self.fact("DOD-13", "revoked")                    # the latest project fact decides (D1)
        try:
            self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "fact DOD-13")
            # a platform-wide fact never satisfies a project precondition (S-5)
            psql(f"SELECT devplat.set_operator_identities({lit(ISSUER)}, 'devplat-api', "
                 f"{lit([{'subject': OPERATOR}])})", role=R["migrator"])
            self.fact("DOD-13", "verified", project=None)
            self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "fact DOD-13")
        finally:
            self.fact("DOD-13", "verified")
        self.assertEqual(self.ev(t, "unblocked", [self.DR])["gate"], "G1")

    def test_g2_requires_checked_implementation_and_verifier_run_at_that_head(self):
        t = "G2-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        self.refused(lambda: self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=head(2)),
                     "not the head of a checked implementation_completed")
        self.refused(lambda: self.ev(t, "implementation_completed", [{"kind": "result_file", "ref": "x", "sha256": "0" * 64}],
                                     head_commit=head(2)), "not a registered artifact")
        res = self.result(t, "implementation", head_commit=head(2), tests=[{"id": "unit", "exit_code": 0, "outcome": "passed"}])
        self.ev(t, "implementation_completed", [self.fev("result_file")], head_commit=head(2), payload={"result": res})
        self.refused(lambda: self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=head(2)),
                     "G2 needs a passed verifier test run at this head for {unit}")
        self.verify_tests(t, head(2), outcome="failed")
        self.refused(lambda: self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=head(2)), "verifier test run")
        self.verify_tests(t, head(2))
        self.assertEqual(self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=head(2))["gate"], "G2")

    def test_g4_cannot_be_skipped(self):
        t = "G4-0001"
        h = self.full_to_review(t)
        self.subtask(f"{t}-r1", "code_review", parent=t, result=self.accept_review(h), review_head=h)
        self.assertEqual(self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r1"}])["to"], "AWAITING_REVIEW")
        self.refused(lambda: self.ev(t, "integration_verified", [{"kind": "subtask", "ref": f"{t}-r1"}]),
                     "illegal transition", "AWAITING_REVIEW --integration_verified-->")
        self.refused(lambda: self.ev(t, "pr_prepared", [{"kind": "pr", "ref": "o/r#2"}, self.fev("ci_run")], head_commit=h),
                     "illegal transition")
        self.refused(lambda: self.ev(t, "security_review_passed", [{"kind": "subtask", "ref": f"{t}-r1"}]),
                     "kind code_review cannot provide security_review_passed")
        st = self.task(t)
        self.assertEqual((st["state"], st["gates"]), ("AWAITING_REVIEW", ["G1", "G2", "G3"]))

    def test_duplicate_gate_refused(self):
        t = "DG-0001"
        h = self.full_to_review(t)
        self.subtask(f"{t}-r1", "code_review", parent=t, result=self.accept_review(h), review_head=h)
        self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r1"}])
        self.refused(lambda: self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r1"}]),
                     "gate G3 already recorded since the last correction")

    def test_review_bound_to_tested_head(self):
        t = "RB-0001"
        h = self.full_to_review(t)
        stale = head("stale")
        self.subtask(f"{t}-r1", "code_review", parent=t, result=self.accept_review(stale), review_head=stale)
        self.refused(lambda: self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r1"}]),
                     f"not bound to the current tested head {h}")
        self.subtask(f"{t}-r2", "design_review", parent=t, result=self.accept_review(h), review_head=h)
        self.refused(lambda: self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r2"}]),
                     "G3 requires a passed code_review")
        self.refused(lambda: psql(f"SELECT devplat.create_task({lit(self.project)}, 'RB-0001-x9', 'code_review', "
                                  f"'RB-0001', NULL, NULL, {lit(HOLDER)}, 60)", role=R["ctl"]), "subtask id must be RB-0001-rN")


class T04BudgetsAndRevisions(Base):
    def test_review_budget_enforced(self):
        t = "RV-0001"
        self.full_to_review(t)
        for i in range(1, 4):
            r = self.ev(t, "code_review_changes_required", [self.fev("review_file")], attempt=i)
            self.assertEqual(r["to"], "RUNNING")
            self.refused(lambda: self.ev(t, "dispatched", [{"kind": "job", "ref": "j"}], attempt=i),
                         f"a correction must be dispatched as attempt {i + 1}")
            self.ev(t, "dispatched", [{"kind": "job", "ref": f"j{i + 1}"}], attempt=i + 1)
            self.implement_and_test(t, head(f"{t}-{i}"), attempt=i + 1)
        self.assertEqual(self.task(t)["counts"]["review"], 3)
        self.refused(lambda: self.ev(t, "code_review_changes_required", [self.fev("review_file")], attempt=4),
                     "review loop budget 3 exhausted")
        self.assertEqual(self.ev(t, "escalated", [{"kind": "ledger", "ref": "budget"}], attempt=4)["to"], "BLOCKED")

    def test_attempt_budget_enforced(self):
        t = "AB-0001"
        self.new_task(t, "implementation", max_attempts=2)
        self.to_running(t)
        self.ev(t, "attempt_failed", [self.fev("log")])
        self.ev(t, "dispatched", [{"kind": "job", "ref": "j2"}], attempt=2)
        self.refused(lambda: self.ev(t, "attempt_failed", [self.fev("log")], attempt=2), "attempt budget 2 exhausted")
        self.assertEqual(self.ev(t, "failed", [self.fev("log")], attempt=2)["to"], "FAILED")

    def test_contract_core_continuity(self):
        t = "CC-0001"
        self.new_task(t, "implementation")
        self.contract(t, 2, self.body(t, "implementation", allowed_paths=["src/cc-0001/x/**"]))
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], version=2), "contract changed without a contract_revised")
        r = self.ev(t, "contract_revised", [{"kind": "ledger", "ref": "rev"}], version=2)
        self.assertEqual(r["to"], "BLOCKED")
        self.refused(lambda: self.ev(t, "contract_revised", [{"kind": "ledger", "ref": "rev"}], version=2),
                     "contract_revised needs a higher contract_version")
        self.refused(lambda: self.contract(t, 1, self.body(t, "implementation", objective="other")),
                     "contract version already registered")

    def test_revision_needs_operator_approval_before_ready(self):
        t = "AP-0001"
        self.new_task(t, "implementation")
        core2 = self.contract(t, 2, self.body(t, "implementation", objective="revised"))
        self.ev(t, "contract_revised", [{"kind": "ledger", "ref": "rev"}], version=2)
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], version=2), "needs an operator contract-approval before READY")
        self.fact("contract-approval", "approved", {"contract_version": 2, "core_sha256": sha("wrong")}, task=t)
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], version=2), "contract-approval")
        self.fact("contract-approval", "approved", {"contract_version": 2, "core_sha256": core2}, task=t)
        self.assertEqual(self.ev(t, "unblocked", [self.DR], version=2)["to"], "READY")

    def test_planner_contract_needs_operator_approval(self):
        t = "PL-0001"
        self.new_task(t, "planning", origin="planner")
        self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "needs an operator contract-approval before READY")
        core = psql(f"SELECT core_sha256 FROM devplat.task_contracts WHERE project_id = {lit(self.project)} AND task_id = '{t}'")
        self.fact("contract-approval", "approved", {"contract_version": 1, "core_sha256": core}, task=t)
        self.assertEqual(self.ev(t, "unblocked", [self.DR])["to"], "READY")

    def test_revision_limit_three_until_operator_reset(self):
        t = "RL-0001"
        self.new_task(t, "planning")
        for v in range(2, 5):
            self.contract(t, v, self.body(t, "planning", objective=f"v{v}"))
            self.ev(t, "contract_revised", [{"kind": "ledger", "ref": f"rev{v}"}], version=v)
        self.contract(t, 5, self.body(t, "planning", objective="v5"))
        self.refused(lambda: self.ev(t, "contract_revised", [{"kind": "ledger", "ref": "rev5"}], version=5),
                     "revision limit 3 reached")
        self.fact("revision-reset", "approved", task=t)
        self.assertEqual(self.ev(t, "contract_revised", [{"kind": "ledger", "ref": "rev5"}], version=5)["to"], "BLOCKED")
        self.assertEqual(psql(f"SELECT revisions_since_reset FROM devplat.tasks WHERE project_id = {lit(self.project)} "
                              f"AND task_id = '{t}'"), "1")


class T05AuditTrail(Base):
    def test_task_events_update_delete_refused(self):
        t = "AU-0001"
        self.new_task(t, "implementation")
        w = f"project_id = {lit(self.project)} AND task_id = '{t}'"
        for sql in (f"UPDATE devplat.task_events SET head_commit = NULL WHERE {w}",
                    f"DELETE FROM devplat.task_events WHERE {w}",
                    "INSERT INTO devplat.task_events (project_id) VALUES ('x')",
                    f"UPDATE devplat.tasks SET state = 'COMPLETED' WHERE {w}"):
            self.refused(lambda: psql(sql, role=R["ctl"]), "permission denied")
        self.refused(lambda: psql(f"UPDATE devplat.task_events SET head_commit = NULL WHERE {w}"),
                     "task_events is append-only (UPDATE forbidden)")
        self.refused(lambda: psql(f"DELETE FROM devplat.task_events WHERE {w}"), "task_events is append-only (DELETE forbidden)")
        self.refused(lambda: psql("TRUNCATE devplat.task_events CASCADE"), "append-only (TRUNCATE forbidden)")
        self.refused(lambda: psql(f"UPDATE devplat.tasks SET state = 'COMPLETED' WHERE {w}"),
                     "task state changes only through record_event()")
        for role in ("api", "mg", "ag", "ro"):
            self.refused(lambda: psql(f"SELECT * FROM devplat.record_event({lit(self.project)}, '{t}', 'unblocked', 1, 1, 'x', 1)",
                                      role=R[role]), "permission denied")
        self.assertEqual(self.chain_problems(t), "")

    def test_hash_chain_detects_superuser_tamper(self):
        t, u = "TP-0001", "TP-0002"
        for x in (t, u):
            self.new_task(x, "implementation")
            self.to_running(x)
        self.assertEqual(self.chain_problems(t), "")
        p = lit(self.project)
        psql(f"SET session_replication_role = replica; UPDATE devplat.task_events SET evidence = "
             f"'[{{\"kind\":\"design_ref\",\"ref\":\"forged\"}}]' WHERE project_id = {p} AND task_id = '{t}' AND seq = 2")
        self.assertIn(f"{t}:2:hash mismatch (row altered)", self.chain_problems(t))
        psql(f"SET session_replication_role = replica; DELETE FROM devplat.task_events WHERE project_id = {p} AND task_id = '{t}' AND seq = 4")
        self.assertIn("does not match the chain tail", self.chain_problems(t))
        digest_before = psql("SELECT r_digest FROM devplat.chain_digest()")
        psql(f"""SET session_replication_role = replica;
DO $$ DECLARE e devplat.task_events; prev text; BEGIN
  UPDATE devplat.task_events SET payload = '{{"forged": true}}' WHERE project_id = {p} AND task_id = '{u}' AND seq = 3;
  SELECT hash INTO prev FROM devplat.task_events WHERE project_id = {p} AND task_id = '{u}' AND seq = 2;
  FOR e IN SELECT * FROM devplat.task_events WHERE project_id = {p} AND task_id = '{u}' AND seq >= 3 ORDER BY seq LOOP
    e.prev_hash := prev; e.hash := devplat.event_hash(e);
    UPDATE devplat.task_events SET prev_hash = e.prev_hash, hash = e.hash WHERE project_id = {p} AND task_id = '{u}' AND seq = e.seq;
    prev := e.hash;
  END LOOP;
  UPDATE devplat.tasks SET last_hash = prev WHERE project_id = {p} AND task_id = '{u}';
END $$;""")
        self.assertEqual(self.chain_problems(u), "", "a consistent superuser rewrite is NOT detectable in-database")
        self.assertNotEqual(psql("SELECT r_digest FROM devplat.chain_digest()"), digest_before, "but the checkpoint digest changes")

    def test_record_event_idempotency_key_replay(self):
        t = "IK-0001"
        self.new_task(t, "implementation")
        a = self.ev(t, "unblocked", [self.DR], key="k-unblock-1")
        b = self.ev(t, "unblocked", [self.DR], key="k-unblock-1")
        self.assertEqual((a["seq"], a["replayed"], b["seq"], b["replayed"]), (2, False, 2, True))
        self.refused(lambda: self.ev(t, "assigned", [{"kind": "ledger", "ref": "x"}], key="k-unblock-1"),
                     "already used for a different record")


class T06Execution(Base):
    def test_admission_required_and_consumed_once(self):
        t = "AD-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        p = self.project
        hold = int(psql(f"SELECT devplat.record_admission({lit(p)}, '{t}', 1, 'mdev-backend-engineer', 'hold', 'project_limit', "
                        f"'{{\"running\": 2}}'::jsonb, {lit(HOLDER)}, {TOKENS[(p, t)]})", role=R["ctl"]))
        call = lambda adm, key: psql(
            f"SELECT r_job_id FROM devplat.dispatch_job({lit(p)}, '{t}', 1, 'mdev-backend-engineer', 1, {adm}, {lit(key)}, NULL, "
            f"'proj-{p}-exec', 'dp-{p}-ad-0001-a1', {lit(HOLDER)}, {TOKENS[(p, t)]})", role=R["ctl"])
        self.refused(lambda: call(hold, sha("k1")), "needs a fresh admit decision")
        adm = self.admit(t, "mdev-backend-engineer")
        call(adm, sha("k1"))
        self.refused(lambda: call(adm, sha("k2")), "duplicate key")      # an admit is consumed by one Job
        self.refused(lambda: psql(f"SELECT devplat.record_admission({lit(p)}, '{t}', 1, 'x', 'admit', 'budget', NULL, "
                                  f"{lit(HOLDER)}, {TOKENS[(p, t)]})", role=R["ctl"]), "admission_decisions_check")
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.admission_decisions WHERE project_id = {lit(p)} AND task_id = '{t}' "
                              f"AND decision = 'hold' AND reason = 'project_limit'"), "1")

    def test_assigned_role_and_verifier_jobs_of_one_attempt(self):
        # R6 re-check RA-1: the implementer's Job and the verifier's Job of the same attempt and dispatch ordinal are
        # two job_runs rows; with role-less jobspec names/keys the second dispatch_job() hit an idempotency collision
        t = "AD-0003"
        self.new_task(t, "implementation")
        self.to_running(t)
        a = self.dispatch(t, "mdev-backend-engineer", dispatch_no=1)
        h = head(t)
        res = self.result(t, "implementation", head_commit=h, tests=[{"id": "unit", "exit_code": 0, "outcome": "passed"}])
        self.ev(t, "implementation_completed", [self.fev("result_file")], head_commit=h, payload={"result": res})
        self.verify_tests(t, h)                                   # verifier, dispatch_no 1 of its own role
        self.assertEqual(self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=h)["gate"], "G2")
        rows = psql(f"SELECT count(DISTINCT idempotency_key) || ',' || count(DISTINCT k8s_job_name) || ',' || count(*) "
                    f"FROM devplat.job_runs WHERE project_id = {lit(self.project)} AND task_id = '{t}' AND attempt = 1")
        self.assertEqual(rows, "2,2,2")
        self.assertNotEqual(a, 0)

    def test_admission_older_than_ten_minutes_is_refused(self):
        # 16-... step 6, 17-... §2 rule 5: dispatch_job() needs an admit decision at most 10 minutes old
        if psql("SELECT rolsuper FROM pg_roles WHERE rolname = current_user") != "t":
            self.skipTest("backdating an append-only admission row needs a superuser connection")
        t = "AD-0002"
        self.new_task(t, "implementation")
        self.to_running(t)
        p = self.project
        call = lambda adm, key: psql(
            f"SELECT r_job_id FROM devplat.dispatch_job({lit(p)}, '{t}', 1, 'mdev-backend-engineer', 1, {adm}, {lit(key)}, NULL, "
            f"'proj-{p}-exec', 'dp-{p}-ad-0002-a1', {lit(HOLDER)}, {TOKENS[(p, t)]})", role=R["ctl"])
        stale = self.admit(t, "mdev-backend-engineer")
        psql(f"SET session_replication_role = replica; UPDATE devplat.admission_decisions "
             f"SET decided_at = clock_timestamp() - interval '10 minutes 1 second' WHERE decision_id = {stale}")
        self.refused(lambda: call(stale, sha("k-stale")), "needs a fresh admit decision")
        call(self.admit(t, "mdev-backend-engineer"), sha("k-fresh"))

    def test_idempotent_dispatch_concurrent(self):
        t = "ID-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        p = self.project
        adm = self.admit(t, "mdev-backend-engineer")
        key = sha(f"{p}|core|1")
        sql = (f'SET ROLE "{R["ctl"]}"; BEGIN; SELECT r_job_id, r_created FROM devplat.dispatch_job({lit(p)}, {lit(t)}, 1, '
               f"'mdev-backend-engineer', 1, {adm}, {lit(key)}, NULL, 'proj-{p}-exec', 'dp-{p}-id-0001-a1', "
               f"{lit(HOLDER)}, {TOKENS[(p, t)]}); SELECT pg_sleep(1.5); COMMIT;")
        t0 = time.time()
        procs = [subprocess.Popen(_psql_args(DB), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for _ in range(2)]
        for pr in procs:
            pr.stdin.write(sql); pr.stdin.close()
        outs = []
        for pr in procs:
            so, se = pr.communicate()
            outs.append((pr.returncode, so.strip(), se.strip()))
        elapsed = time.time() - t0
        self.assertEqual([o[0] for o in outs], [0, 0], outs)
        rows = sorted(o[1].splitlines()[0] for o in outs)
        ids = {r.split("|")[0] for r in rows}
        self.assertEqual(len(ids), 1, rows)
        self.assertEqual(sorted(r.split("|")[1] for r in rows), ["f", "t"])
        self.assertGreater(elapsed, 2.5, "second session must have waited for the first (true concurrency)")
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.job_runs WHERE project_id = {lit(p)} AND task_id = '{t}'"), "1")
        adm2 = self.admit(t, "mdev-backend-engineer")
        self.refused(lambda: psql(f"SELECT * FROM devplat.dispatch_job({lit(p)}, {lit(t)}, 1, 'mdev-backend-engineer', 1, {adm2}, "
                                  f"{lit(sha('other'))}, NULL, 'proj-x-exec', 'dp-other-a1', {lit(HOLDER)}, {TOKENS[(p, t)]})",
                                  role=R["ctl"]), "duplicate key")
        jid = ids.pop()
        uid1, uid2 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
        upd = lambda ph, uid, fc="NULL", det="NULL": psql(
            f"SELECT devplat.update_job_phase({jid}, '{ph}', {uid}, {fc}, {det}, {lit(HOLDER)}, {TOKENS[(p, t)]})", role=R["ctl"])
        upd("created", f"'{uid1}'")
        self.assertEqual(psql(f"SELECT devplat.job_heartbeat({jid}, '{uid1}')", role=R["ctl"]), "t")
        self.refused(lambda: upd("running", f"'{uid2}'"), "duplicate execution")
        self.refused(lambda: upd("planned", "NULL"), "illegal job phase change created -> planned")

    def test_env_classification_only_from_platform_signals(self):
        t = "EV-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        p = self.project
        jid = self.dispatch(t, "mdev-backend-engineer")
        upd = lambda ph, fc, det: psql(
            f"SELECT devplat.update_job_phase({jid}, '{ph}', NULL, {lit(fc)}, {lit(det)}, {lit(HOLDER)}, {TOKENS[(p, t)]})", role=R["ctl"])
        upd("created", None, {})
        self.refused(lambda: upd("failed", "environmental", {"signal": "runner_exit_75"}),
                     "environmental classification needs a platform signal (got runner_exit_75)")
        self.refused(lambda: self.ev(t, "env_retry", [self.fev("log")], payload={"signal": "partial_result", "job_id": jid}),
                     "agent-reported failures are charged attempts")
        upd("failed", "environmental", {"signal": "gateway_429"})
        self.refused(lambda: self.ev(t, "env_retry", [self.fev("log")], payload={"signal": "node_failure", "job_id": jid}),
                     "classified environmental with the same signal")
        r = self.ev(t, "env_retry", [self.fev("log")], payload={"signal": "gateway_429", "job_id": jid})
        self.assertEqual((r["to"], self.task(t)["counts"]["env"]), ("RUNNING", 1))

    def test_fence_transfer_on_leader_election(self):
        t = "FT-0001"
        tok_a = self.new_task(t, "implementation")
        p = self.project
        self.assertEqual(psql("SELECT devplat.acquire_lease('controller-leader', 'ctrl-a', 1)", role=R["ctl"]), "1")
        self.refused(lambda: psql("SELECT devplat.fence_transfer_task_leases('ctrl-b', 1, 120)", role=R["ctl"]),
                     "needs the current controller-leader lease")
        time.sleep(1.5)
        lt = int(psql("SELECT devplat.acquire_lease('controller-leader', 'ctrl-b', 15)", role=R["ctl"]))
        self.assertEqual(lt, 2)
        n = int(psql(f"SELECT devplat.fence_transfer_task_leases('ctrl-b', {lt}, 120)", role=R["ctl"]))
        self.assertGreaterEqual(n, 1)
        new = int(psql(f"SELECT lease_token FROM devplat.tasks WHERE project_id = {lit(p)} AND task_id = '{t}'"))
        self.assertEqual(new, tok_a + 1)
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], holder=HOLDER, token=tok_a), "stale or missing task lease")
        self.assertEqual(self.ev(t, "unblocked", [self.DR], holder="ctrl-b", token=new)["to"], "READY")

    def test_task_lease_fencing(self):
        t, p = "LF-0001", self.project
        tok_a = int(psql(f"SELECT devplat.create_task({lit(p)}, {lit(t)}, 'implementation', NULL, NULL, NULL, 'ctrl-a', 2)", role=R["ctl"]))
        TOKENS[(p, t)] = tok_a
        body = dict(self.body(t, "implementation"), contract_version=1)
        psql(f"SELECT devplat.register_contract({lit(p)}, {lit(t)}, 1, {lit(sha(t))}, {lit(body)}, 3, 'controller', 'ctrl-a', {tok_a})",
             role=R["ctl"])
        self.ev(t, "created", [{"kind": "ledger", "ref": "c"}], holder="ctrl-a", token=tok_a)
        self.assertEqual(psql(f"SELECT devplat.acquire_task_lease({lit(p)}, {lit(t)}, 'ctrl-b', 60)", role=R["ctl"]), "")
        time.sleep(2.5)
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], holder="ctrl-a", token=tok_a), "stale or missing task lease")
        tok_b = int(psql(f"SELECT devplat.acquire_task_lease({lit(p)}, {lit(t)}, 'ctrl-b', 60)", role=R["ctl"]))
        self.assertEqual(tok_b, tok_a + 1)
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], holder="ctrl-a", token=tok_a), "stale or missing task lease")
        self.assertEqual(psql(f"SELECT devplat.acquire_task_lease({lit(p)}, {lit(t)}, 'ctrl-a', 60)", role=R["ctl"]), "")
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], holder="ctrl-b", token=tok_a), "stale or missing task lease")
        self.assertEqual(self.ev(t, "unblocked", [self.DR], holder="ctrl-b", token=tok_b)["to"], "READY")


class T07SideEffects(Base):
    def test_outbox_dedup_and_allowed_operations(self):
        p = self.project
        q = (f"SELECT r_outbox_id || '|' || r_created FROM devplat.enqueue_outbox({lit(p)}, 'github', 'comment_pr', "
             f"'gh:{p}:OB-0001:c1', '{{\"body\": \"x\"}}'::jsonb)")
        a, b = psql(q, role=R["ctl"]).split("|"), psql(q, role=R["ctl"]).split("|")
        self.assertEqual((a[0] == b[0], a[1], b[1]), (True, "true", "false"))
        self.refused(lambda: psql(f"SELECT * FROM devplat.enqueue_outbox({lit(p)}, 'github', 'merge_pr', 'gh:{p}:merge', "
                                  f"'{{}}'::jsonb)", role=R["ctl"]), "not an allowed outbox operation")
        self.refused(lambda: psql(f"SELECT * FROM devplat.enqueue_outbox({lit(p)}, 'linear', 'comment_issue', 'ln:{p}:1', "
                                  f"'{{}}'::jsonb)", role=R["ctl"]), "Linear writes are not enabled")
        t = "OB-0001"
        self.new_task(t, "implementation")
        self.ev(t, "unblocked", [self.DR], outbox=[{"target": "github", "operation": "comment_pr",
                                                   "dedup_key": f"gh:{p}:OB-0001:c1", "payload": {}}])
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.outbox WHERE dedup_key = 'gh:{p}:OB-0001:c1'"), "1")
        oid = psql(f"SELECT outbox_id FROM devplat.claim_outbox('disp-1', 50) WHERE dedup_key = 'gh:{p}:OB-0001:c1'", role=R["ctl"])
        self.assertTrue(oid)
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.claim_outbox('disp-2', 50) WHERE outbox_id = {oid}", role=R["ctl"]), "0")
        self.assertEqual(psql(f"SELECT devplat.fail_outbox({oid}, 'disp-1', '403 rate limited', true, 60)", role=R["ctl"]), "pending")
        self.assertEqual(psql(f"SELECT next_attempt_at > now() + interval '50 seconds' FROM devplat.outbox WHERE outbox_id = {oid}"), "t")
        psql(f"UPDATE devplat.outbox SET next_attempt_at = now() WHERE outbox_id = {oid}")   # test shortcut (superuser)
        psql("SELECT 1 FROM devplat.claim_outbox('disp-2', 50)", role=R["ctl"])
        self.assertEqual(psql(f"SELECT devplat.complete_outbox({oid}, 'disp-1', 'c#7')", role=R["ctl"]), "f")
        self.assertEqual(psql(f"SELECT devplat.complete_outbox({oid}, 'disp-2', 'c#7')", role=R["ctl"]), "t")
        self.assertEqual(psql(f"SELECT status || '|' || attempts FROM devplat.outbox WHERE outbox_id = {oid}"), "done|2")

    def test_push_needs_active_project_with_hard_preconditions(self):
        p = self.project
        push = lambda k: psql(f"SELECT r_created FROM devplat.enqueue_outbox({lit(p)}, 'github', 'push_dev_branch', "
                              f"{lit(k)}, '{{}}'::jsonb)", role=R["ctl"])
        self.assertEqual(push(f"gh:{p}:push:1"), "t")
        self.fact("DOD-02", "revoked")
        try:
            self.refused(lambda: push(f"gh:{p}:push:2"), "push refused: hard preconditions {DOD-02}")
        finally:
            self.fact("DOD-02", "verified")
        q = "q" + secrets.token_hex(3)
        self.make_project(q, "onboarding")
        self.refused(lambda: psql(f"SELECT * FROM devplat.enqueue_outbox({lit(q)}, 'github', 'open_draft_pr', 'gh:{q}:pr', "
                                  f"'{{}}'::jsonb)", role=R["ctl"]), f"project {q} is onboarding")

    def test_controller_cannot_drop_mandatory_hard_preconditions(self):
        # R6 re-check RS-5: a compromised controller activating a project with a list of its choosing
        q = "m" + secrets.token_hex(3)
        self.make_project(q, "onboarding")
        self.fact("note", "verified", project=q)
        up = lambda hard, st="onboarding", wf=None: psql(
            f"SELECT devplat.upsert_project({lit(q)}, 'M', NULL, NULL, 'cfg-2', 'r@2', {lit(st)}, 'standard', {arr(hard)}, "
            f"'{{}}'::jsonb, 5, NULL, '{{}}'::jsonb, {lit(wf)})", role=R["ctl"])
        self.refused(lambda: up(["note"], "active"), "must include the platform's mandatory keys {DOD-02,DOD-13}")
        self.refused(lambda: up(["DOD-02", "note"]), "mandatory keys {DOD-13}")
        self.refused(lambda: up(HARD, wf="DOD-02"), "Linear writes need their own fact")
        self.refused(lambda: up(HARD, wf="REDUCED-ASSURANCE"), "reserved key")
        self.refused(lambda: up(HARD + ["X-1"], wf="X-1"), "Linear writes need their own fact")
        up(HARD + ["X-1"], wf="LINEAR-WRITE")
        self.refused(lambda: psql("SELECT devplat.set_mandatory_hard_preconditions(ARRAY['note'])", role=R["ctl"]),
                     "permission denied")
        self.refused(lambda: psql("INSERT INTO devplat.mandatory_hard_preconditions VALUES ('x')", role=R["ctl"]),
                     "permission denied")

    def test_linear_writes_need_configured_project_fact(self):
        q = "l" + secrets.token_hex(3)
        self.make_project(q, "onboarding")
        psql(f"SELECT devplat.upsert_project({lit(q)}, 'L', NULL, 'TEAM', 'cfg-2', 'r@2', 'onboarding', 'standard', {arr(HARD)}, "
             f"'{{}}'::jsonb, NULL, NULL, '{{}}'::jsonb, 'LIN-WRITE')", role=R["ctl"])
        enq = lambda k: psql(f"SELECT r_created FROM devplat.enqueue_outbox({lit(q)}, 'linear', 'comment_issue', {lit(k)}, "
                             f"'{{}}'::jsonb)", role=R["ctl"])
        self.refused(lambda: enq(f"ln:{q}:1"), "Linear writes are not enabled")
        self.fact("LIN-WRITE", "verified", project=q)
        self.assertEqual(enq(f"ln:{q}:1"), "t")


class T08OperatorFacts(Base):
    def test_operator_fact_not_writable_by_controller(self):
        p = self.project
        call = (f"SELECT devplat.record_operator_fact({lit(p)}, 'DOD-02', 'verified', '{{}}'::jsonb, NULL, 's', "
                f"{lit(OPERATOR)}, {lit(ISSUER)}, NULL, now(), {lit(secrets.token_hex(8))}, NULL)")
        self.refused(lambda: psql(call, role=R["ctl"]), "permission denied for function record_operator_fact")
        self.refused(lambda: psql(f"INSERT INTO devplat.operator_facts (fact_key, status, value, subject, issuer, auth_time, "
                                  f"token_jti, recorded_via) VALUES ('DOD-02', 'verified', '{{}}', 'x', {lit(ISSUER)}, now(), 'j', 'x')",
                                  role=R["ctl"]), "permission denied for table operator_facts")
        for role in ("ro", "mg", "ag"):
            self.refused(lambda: psql(call, role=R[role]), "permission denied")
        self.refused(lambda: self.fact("DOD-02", subject="system:serviceaccount:proj-x-exec:agent"), "is not a human operator identity")
        self.refused(lambda: self.fact("DOD-02", auth_age_s=3600), "not fresh")
        jti = secrets.token_hex(8)
        once = (f"SELECT devplat.record_operator_fact({lit(p)}, 'note', 'recorded', '{{}}'::jsonb, NULL, 's', {lit(OPERATOR)}, "
                f"{lit(ISSUER)}, NULL, now(), {lit(jti)}, NULL)")
        psql(once, role=R["api"])
        self.refused(lambda: psql(once, role=R["api"]), "duplicate key")
        self.refused(lambda: psql(once.replace(ISSUER, "https://evil.test").replace(jti, "j2"), role=R["api"]),
                     "not an enabled operator identity provider")
        self.refused(lambda: psql("UPDATE devplat.operator_facts SET subject = 'x'"), "operator_facts is append-only")

    def test_operator_subject_must_be_allowlisted(self):
        self.refused(lambda: self.fact("note", "recorded", subject="someone-else"), "is not an allowed operator for project")
        self.refused(lambda: psql(f"SELECT devplat.set_operator_identities({lit(ISSUER)}, 'devplat-api', '[]'::jsonb)",
                                  role=R["migrator"]), "at least one allowed operator subject")
        q = "o" + secrets.token_hex(3)
        self.make_project(q, "onboarding")
        psql(f"SELECT devplat.set_operator_identities({lit(ISSUER)}, 'devplat-api', "
             f"{lit([{'subject': OPERATOR}, {'subject': 'proj-only', 'project_id': self.project}])})", role=R["migrator"])
        self.fact("note", "recorded", subject="proj-only")
        self.refused(lambda: self.fact("note", "recorded", subject="proj-only", project=q), f"not an allowed operator for project {q}")
        self.refused(lambda: self.fact("note", "recorded", subject="proj-only", project=None), "(platform)")
        self.refused(lambda: psql(f"SELECT devplat.set_operator_identities({lit(ISSUER)}, 'devplat-api', "
                                  f"{lit([{'subject': 'x'}])})", role=R["ctl"]), "permission denied")

    def test_operator_task_completion_needs_authenticated_fact(self):
        t = "MV-0001"
        self.new_task(t, "mac_validation")
        self.to_running(t)
        self.refused(lambda: self.ev(t, "result_accepted", [self.fev("operator_statement")]),
                     "needs an authenticated operator fact for this task")
        fid = self.fact("task_result", "accepted", {"outcome": "passed"}, task=t)
        r = self.ev(t, "result_accepted", [{"kind": "operator_fact", "ref": str(fid)}])
        self.assertEqual(r["to"], "COMPLETED")
        self.assertEqual(psql(f"SELECT on_behalf_of FROM devplat.task_events WHERE project_id = {lit(self.project)} "
                              f"AND task_id = '{t}' AND seq = {r['seq']}"), f"{ISSUER}#{OPERATOR}")


class T09IsolationAndStatus(Base):
    def test_rls_project_isolation(self):
        other = "q" + secrets.token_hex(3)
        self.make_project(other, "onboarding")
        mine = "IS-0001"
        self.new_task(mine, "planning")
        role = f"dpt_{SUFFIX}_ro_{self.project}"
        EXTRA_ROLES.append(role)
        psql(f'CREATE ROLE "{role}" NOLOGIN IN ROLE "{R["ro"]}"', db="postgres")
        self.assertEqual(psql("SELECT count(*) FROM devplat.tasks", role=role), "0", "no grant, no rows")
        psql(f"INSERT INTO devplat.project_grants VALUES ({lit(self.project)}, {lit(role)}::regrole)")
        self.assertEqual(psql("SELECT DISTINCT project_id FROM devplat.tasks", role=role), self.project)
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.projects WHERE project_id = {lit(other)}", role=role), "0")
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.task_events WHERE task_id = '{mine}'", role=role), "1")
        self.assertEqual(psql(f"SELECT count(*) > 0 FROM devplat.projects WHERE project_id <> {lit(self.project)}", role=R["api"]), "t")
        self.refused(lambda: psql("SELECT * FROM devplat.leases", role=role), "permission denied")

    def test_plan_proposal_ids_and_onboarding_dispatch(self):
        # doc 16 §10: planner Jobs, kind plan_proposal; ids <task>-pN (task-bound) or PL-<nnnn> (project-level)
        o = "q" + secrets.token_hex(3)
        self.make_project(o, "onboarding")
        create = lambda tid, parent=None, covers=None: psql(
            f"SELECT devplat.create_task({lit(o)}, {lit(tid)}, 'plan_proposal', {lit(parent)}, {arr(covers)}, NULL, {lit(HOLDER)}, 60)",
            role=R["ctl"])
        self.refused(lambda: create("PLAN-1"), "project-level plan proposal id must be PL-<nnnn>")
        self.refused(lambda: create("PL-1"), "PL-<nnnn>")
        self.refused(lambda: create("PB-0001-p1", parent="PB-0001"), "needs a parent in the same project")
        self.new_task("PB-0001", "planning", project=o)
        self.refused(lambda: create("PB-0001-r1", parent="PB-0001"), "plan proposal id must be PB-0001-pN")
        self.refused(lambda: create("PL-0002", covers=["PB-0001"]), "no covers_tasks")
        self.new_task("PB-0001-p1", "plan_proposal", parent="PB-0001", project=o)
        self.new_task("PL-0001", "plan_proposal", project=o)
        self.to_running("PL-0001", project=o)          # SHORT read-only: dispatchable while onboarding
        self.dispatch("PL-0001", "planner", project=o)
        r = self.ev("PL-0001", "result_accepted", [self.fev("result_file", project=o)], project=o,
                    payload={"result": self.result("PL-0001", "plan_proposal")})
        self.assertEqual(r["to"], "COMPLETED")
        # the planner role cannot be assigned another kind (role vs kind map from the catalogue)
        self.refused(lambda: self.new_task("PL-0003", "plan_proposal", project=o,
                                           body=dict(self.body("PL-0003", "plan_proposal"), assigned_agent="mdev-tpm")))

    def test_task_identity_is_project_scoped(self):
        other = "s" + secrets.token_hex(3)
        self.make_project(other, "active")
        self.new_task("SAME-0001", "implementation")
        self.new_task("SAME-0001", "implementation", project=other)
        self.ev("SAME-0001", "unblocked", [self.DR], project=other)
        self.assertEqual(self.task("SAME-0001")["state"], "BLOCKED")
        self.assertEqual(self.task("SAME-0001", project=other)["state"], "READY")
        self.refused(lambda: self.ev("SAME-0001", "unblocked", [self.DR], project=other, token=TOKENS[(self.project, "SAME-0001")] + 5),
                     "stale or missing task lease")

    def test_project_status_gates_creation_and_dispatch(self):
        d = "d" + secrets.token_hex(3)
        self.make_project(d, "draft")
        self.refused(lambda: psql(f"SELECT devplat.create_task({lit(d)}, 'X-0001', 'planning', NULL, NULL, NULL, {lit(HOLDER)}, 60)",
                                  role=R["ctl"]), f"project {d} is draft")
        o = "n" + secrets.token_hex(3)
        self.make_project(o, "onboarding")
        self.new_task("ON-0001", "planning", project=o)
        self.to_running("ON-0001", project=o)          # SHORT read-only kinds may run in onboarding
        self.new_task("ON-0002", "implementation", project=o)
        self.refused(lambda: self.ev("ON-0002", "unblocked", [self.DR], project=o), "fact DOD-02")
        for key in HARD:
            self.fact(key, "verified", project=o)
        self.ev("ON-0002", "unblocked", [self.DR], project=o)
        self.refused(lambda: self.ev("ON-0002", "assigned", [{"kind": "ledger", "ref": "a"}], project=o),
                     f"dispatch of kind implementation refused: project {o} is onboarding")
        self.refused(lambda: psql(f"SELECT devplat.upsert_project({lit(o)}, 'x', NULL, NULL, 'cfg-1', 'r@1', 'active', 'standard', "
                                  f"{arr(HARD)}, '{{}}'::jsonb, NULL, NULL, '{{}}'::jsonb)", role=R["ctl"]),
                     "cannot be active without budgets.cost_usd_per_day")
        self.refused(lambda: psql(f"SELECT devplat.upsert_project({lit(o)}, 'x', NULL, NULL, 'cfg-1', 'r@1', 'onboarding', 'reduced', "
                                  f"{arr(HARD)}, '{{}}'::jsonb, 5, NULL, '{{}}'::jsonb)", role=R["ctl"]),
                     "reduced assurance needs the project fact REDUCED-ASSURANCE")
        self.refused(lambda: psql(f"SELECT devplat.upsert_project({lit(o)}, 'x', NULL, NULL, 'cfg-1', 'r@1', 'onboarding', 'standard', "
                                  f"'{{}}'::text[], '{{}}'::jsonb, 5, NULL, '{{}}'::jsonb)", role=R["ctl"]),
                     "hard_preconditions must list at least one")

    def test_identifiers_and_network_classes(self):
        bad = "x" * 25
        self.refused(lambda: psql(f"SELECT devplat.upsert_project({lit(bad)}, 'x', NULL, NULL, 'c', 'r', 'draft', 'standard', "
                                  f"{arr(HARD)}, '{{}}'::jsonb, NULL, NULL)", role=R["ctl"]), "projects_project_id_check")
        self.refused(lambda: psql(f"SELECT devplat.upsert_execution_target({lit(self.project)}, 'main', 'local', "
                                  f"'proj-{self.project}', 'gvisor', 'integration', 'standard', true)", role=R["ctl"]),
                     "execution_targets_network_class_check")
        psql(f"SELECT devplat.upsert_execution_target({lit(self.project)}, 'main', 'local', 'proj-{self.project}', 'gvisor', "
             f"'model-only', 'standard', true)", role=R["ctl"])

    def test_artifact_immutability_bucket_and_caps(self):
        h = self.artifact("immutable-content")
        self.assertEqual(psql(f"SELECT bucket || ' ' || object_key FROM devplat.artifacts WHERE sha256 = '{h}'"),
                         f"devplat-{self.project} sha256/{h}")
        self.refused(lambda: psql(f"UPDATE devplat.artifacts SET size_bytes = 1 WHERE sha256 = '{h}'"), "identity is immutable")
        self.refused(lambda: psql(f"DELETE FROM devplat.artifacts WHERE sha256 = '{h}'"), "artifact is retained")
        self.refused(lambda: psql(f"UPDATE devplat.artifacts SET bucket = 'other' WHERE sha256 = '{h}'"), "identity is immutable")
        self.refused(lambda: psql(f"INSERT INTO devplat.artifacts (project_id, sha256, bucket, object_key, size_bytes, media_type, "
                                  f"kind, retention_class, retain_until) VALUES ({lit(self.project)}, {lit(sha('b2'))}, 'other', "
                                  f"'sha256/' || {lit(sha('b2'))}, 1, 'x', 'log', 'standard', now())"), "artifacts_bucket_check")
        self.refused(lambda: psql(f"SELECT * FROM devplat.register_artifact({lit(self.project)}, {lit(sha('big'))}, 2000000, "
                                  f"'application/json', 'result', NULL, NULL, NULL, 'evidence')", role=R["ctl"]),
                     "result artifact over 1048576 bytes")
        self.refused(lambda: psql(f"SELECT * FROM devplat.register_artifact({lit(self.project)}, {lit(sha('m'))}, 10, "
                                  f"'application/json', 'result', NULL, NULL, NULL, 'evidence', 'manifests/T/1/1.json')",
                                  role=R["ctl"]), "artifacts_alias_check")
        psql(f"SELECT * FROM devplat.register_artifact({lit(self.project)}, {lit(sha('m'))}, 10, 'application/json', "
             f"'evidence_manifest', NULL, NULL, NULL, 'evidence', 'manifests/T-0001/1/1.json')", role=R["ctl"])
        self.assertEqual(psql("SELECT count(*) FROM devplat.expire_artifacts(100)", role=R["ctl"]), "0")


class T10DevorchRulesPorted(Base):
    """1:1 ports of the devorch G1 / result / contract rules lost in the first DB port (R6 A-02, A-03, D7)."""

    def test_g1_requires_ready_including_hard_preconditions(self):
        # devorch test_g1_requires_ready_including_hard_preconditions: no facts -> "fact DOD-02"
        q = "h" + secrets.token_hex(3)
        self.make_project(q, "onboarding")
        self.new_task("DT-0001", "implementation", project=q)
        self.refused(lambda: self.ev("DT-0001", "unblocked", [self.DR], project=q), "fact DOD-02")

    def test_g1_requires_task_required_facts(self):
        t = "RF-0001"
        self.new_task(t, "implementation", body=self.body(t, "implementation", required_facts=["G-S1", "P0-3"]))
        self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "fact G-S1, fact P0-3")
        self.fact("G-S1", "verified")
        self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "fact P0-3")
        self.fact("P0-3", "accepted")
        self.assertEqual(self.ev(t, "unblocked", [self.DR])["to"], "READY")

    def test_interface_contract_hash_must_equal_frozen_hash(self):
        f, t = "IF-0001", "IF-0002"
        self.new_task(f, "implementation")
        good = sha("ports-v1")
        self.new_task(t, "implementation", body=self.body(t, "implementation", interface_contracts=[
            {"path": "src/ports/a.ts", "sha256": good, "frozen_by": f}]))
        self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "interface src/ports/a.ts not frozen at the contracted sha256 by IF-0001")
        h = self.full_to_review_existing(f)
        self.subtask(f"{f}-r1", "code_review", parent=f, result=self.accept_review(h), review_head=h)
        self.subtask(f"{f}-s1", "security_review", parent=f, result=self.accept_review(h), review_head=h)
        self.ev(f, "code_review_passed", [{"kind": "subtask", "ref": f"{f}-r1"}])
        self.ev(f, "security_review_passed", [{"kind": "subtask", "ref": f"{f}-s1"}])
        self.subtask(f"{f}-i1", "integration", covers=[f], result={"recommendation": "accept", "integrated_heads": [f"{f}@{h}"]})
        self.ev(f, "integration_verified", [{"kind": "subtask", "ref": f"{f}-i1"}])
        self.ev(f, "pr_prepared", [{"kind": "pr", "ref": "o/r#9"}, self.fev("ci_run")], head_commit=h)
        self.ev(f, "interface_frozen", [{"kind": "ledger", "ref": "freeze"}], payload={"frozen_files": {"src/ports/a.ts": sha("ports-v0")}})
        self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "not frozen at the contracted sha256")
        self.ev(f, "interface_frozen", [{"kind": "ledger", "ref": "freeze2"}], payload={"frozen_files": {"src/ports/a.ts": good}})
        self.assertEqual(self.ev(t, "unblocked", [self.DR])["to"], "READY")

    def full_to_review_existing(self, tid):
        self.to_running(tid)
        self.implement_and_test(tid, head(tid))
        return head(tid)

    def test_dependency_required_states(self):
        a, b, c = "DS-0001", "DS-0002", "DS-0003"
        self.new_task(a, "implementation")
        self.new_task(b, "implementation", body=self.body(b, "implementation", dependencies=[
            {"task_id": a, "required_state": "AWAITING_HUMAN"}]))
        self.new_task(c, "implementation", body=self.body(c, "implementation", dependencies=[
            {"task_id": a, "required_state": "INTERFACE_FROZEN", "path": "src/ports/b.ts", "sha256": sha("b")}]))
        self.refused(lambda: self.ev(b, "unblocked", [self.DR]), f"dependency {a} not AWAITING_HUMAN")
        self.refused(lambda: self.ev(c, "unblocked", [self.DR]), f"dependency {a} not INTERFACE_FROZEN")
        self.refused(lambda: self.contract(b, 2, self.body(b, "implementation", dependencies=[
            {"task_id": a, "required_state": "INTERFACE_FROZEN"}])), "task_dependencies_check")

    def test_result_checks_status_head_and_blocking_findings(self):
        t = "RC-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        fe = lambda: [self.fev("result_file")]
        ok = dict(head_commit=head(5), tests=[{"id": "unit", "exit_code": 0, "outcome": "passed"}])
        self.refused(lambda: self.ev(t, "implementation_completed", fe(), head_commit=head(5)), "needs payload.result")
        self.refused(lambda: self.ev(t, "implementation_completed", fe(), head_commit=head(5),
                                     payload={"result": self.result(t, "implementation", **dict(ok, status="partial"))}),
                     "result status is partial, not completed")
        self.refused(lambda: self.ev(t, "implementation_completed", fe(), head_commit=head(5),
                                     payload={"result": self.result(t, "implementation", **dict(ok, head_commit=head(6)))}),
                     "head_commit must equal the result's head_commit")
        self.refused(lambda: self.ev(t, "implementation_completed", fe(), head_commit=head(5),
                                     payload={"result": self.result(t, "implementation", **dict(ok, tests=[]))}),
                     "required tests not passed: {unit}")
        self.refused(lambda: self.ev(t, "implementation_completed", fe(), head_commit=head(5),
                                     payload={"result": self.result(t, "implementation", **dict(ok, agent="mdev-tpm"))}),
                     "result agent is not the assigned agent")
        self.refused(lambda: self.ev(t, "implementation_completed", fe(), head_commit=head(5),
                                     payload={"result": self.result(t, "implementation", attempt=2, **ok)}),
                     "do not match the contract")
        self.ev(t, "implementation_completed", fe(), head_commit=head(5), payload={"result": self.result(t, "implementation", **ok)})
        self.verify_tests(t, head(5))
        self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=head(5))
        # review: accept with a blocking finding is refused at result_accepted (computed from findings[])
        s = f"{t}-r1"
        self.new_task(s, "code_review", parent=t, body=self.body(s, "code_review", parent_task_id=t,
                                                                review_target={"head_commit": head(5)}))
        self.to_running(s)
        bad = self.result(s, "code_review", **self.accept_review(head(5), findings=[{"id": "F1", "blocking": True}]))
        self.refused(lambda: self.ev(s, "result_accepted", [self.fev("result_file")], payload={"result": bad}),
                     "recommendation accept with blocking findings")

    def test_result_accepted_requires_checking_result(self):
        # devorch test_result_accepted_requires_checking_result: an integration result that does not check is refused
        t = "IR-0001"
        h = self.full_to_review(t)
        i = f"{t}-i1"
        self.new_task(i, "integration", covers=[t], body=self.body(i, "integration", covers_tasks=[t], allowed_paths=[]))
        self.to_running(i)
        self.refused(lambda: self.ev(i, "result_accepted", [self.fev("result_file")],
                                     payload={"result": self.result(i, "integration", recommendation="accept")}),
                     "integration result needs recommendation and integrated_heads")
        _ = h

    def test_contract_rules_role_scope_and_ownership(self):
        p = self.project
        t = "CR-0001"
        tok = int(psql(f"SELECT devplat.create_task({lit(p)}, {lit(t)}, 'implementation', NULL, NULL, NULL, {lit(HOLDER)}, 600)",
                       role=R["ctl"]))
        TOKENS[(p, t)] = tok
        self.refused(lambda: self.contract(t, 1, self.body(t, "implementation", assigned_agent="mdev-code-reviewer")),
                     "kind implementation must be assigned to an enabled role")
        self.refused(lambda: self.contract(t, 1, self.body(t, "implementation", allowed_paths=["docs/x/**"])),
                     "allowed path docs/x/** falls inside restricted_paths")
        self.refused(lambda: self.contract(t, 1, self.body(t, "implementation", required_reviewers=["operator"])),
                     "required reviewer operator is not an enabled reviewing role")
        r = "CR-0002"
        self.refused(lambda: self.new_task(r, "planning", body=self.body(r, "planning", allowed_paths=["src/**"])),
                     "read-only kinds must have allowed_paths []")

    def test_cross_project_dependency_refused(self):
        # R6 re-check RA-3: contract v2 allows dependencies[].project_id; the DB does not implement it yet
        other = "x" + secrets.token_hex(3)
        self.make_project(other, "active")
        self.new_task("XP-0001", "implementation", project=other)
        self.new_task("XP-0001", "implementation")           # same id in this project
        t = "XP-0002"
        dep = {"task_id": "XP-0001", "required_state": "COMPLETED", "project_id": other}
        self.refused(lambda: self.new_task(t, "implementation", body=self.body(t, "implementation", dependencies=[dep])),
                     f"cross-project dependency on {other}/XP-0001 is not implemented")
        self.refused(lambda: self.new_task("XP-0003", "implementation",
                                           body=self.body("XP-0003", "implementation", dependencies=[{"task_id": "XP-0999"}])),
                     "dependency XP-0999 is not a task of project")
        self.new_task("XP-0004", "implementation", body=self.body("XP-0004", "implementation",
                      dependencies=[{"task_id": "XP-0001", "required_state": "COMPLETED", "project_id": self.project}]))

    def test_path_ownership_conflict(self):
        # devorch test_path_ownership_conflict: an active owner of src/core/** blocks a contract for src/core/x/**
        self.new_task("PO-0001", "implementation", body=self.body("PO-0001", "implementation", allowed_paths=["src/core/**"]))
        self.ev("PO-0001", "unblocked", [self.DR])
        self.ev("PO-0001", "assigned", [{"kind": "ledger", "ref": "a"}])
        self.refused(lambda: self.new_task("PO-0003", "implementation",
                                           body=self.body("PO-0003", "implementation", allowed_paths=["src/core/x/**"])),
                     "ownership conflict")


class T11Gateways(Base):
    def job_with_tokens(self, tid, dispatch_no=1, deadline="now() + interval '1 hour'", uid=None):
        p = self.project
        jid = self.dispatch(tid, "mdev-backend-engineer", dispatch_no=dispatch_no)
        g, u = secrets.token_hex(16), secrets.token_hex(16)
        psql(f"SELECT devplat.set_job_tokens({jid}, {lit(sha(g))}, {lit(sha(u))}, {deadline}, {lit(HOLDER)}, {TOKENS[(p, tid)]})",
             role=R["ctl"])
        uid = uid or f"{secrets.token_hex(4)}-0000-4000-8000-{secrets.token_hex(6)}"
        psql(f"SELECT devplat.update_job_phase({jid}, 'created', '{uid}', NULL, NULL, {lit(HOLDER)}, {TOKENS[(p, tid)]})", role=R["ctl"])
        return jid, sha(g), sha(u), uid

    def test_budget_reservations_atomic_and_env_retries_charged(self):
        q = "b" + secrets.token_hex(3)
        self.make_project(q, "active", cost=10)
        old, type(self).project = self.project, q
        try:
            t = "BU-0001"
            self.new_task(t, "implementation", body=self.body(t, "implementation", budget={"max_cost_usd": 6}))
            self.to_running(t)
            j1, g1, _, _ = self.job_with_tokens(t)
            res = lambda g, rid, usd: psql(f"SELECT devplat.reserve_budget({lit(g)}, {lit(rid)}, {usd}, 1000)", role=R["mg"])
            r1 = res(g1, "req-1", 4)
            self.assertEqual(res(g1, "req-1", 4), r1, "same request id is idempotent")
            psql(f"SELECT devplat.settle_budget({r1}, 4.5, 1200)", role=R["mg"])
            # an environmental re-dispatch of the same attempt is a new Job but the SAME task budget (D17)
            j2, g2, _, _ = self.job_with_tokens(t, dispatch_no=2)
            self.refused(lambda: res(g2, "req-2", 2), "task cost budget 6 exhausted")
            self.assertTrue(res(g2, "req-3", 1))
            t2 = "BU-0002"
            self.new_task(t2, "implementation")
            self.to_running(t2)
            _, g3, _, _ = self.job_with_tokens(t2)
            self.refused(lambda: res(g3, "req-4", 5), f"daily cost budget of {q} exhausted")
            self.assertTrue(res(g3, "req-5", 4))
            self.refused(lambda: res(sha("forged"), "req-6", 1), "unknown, finished or expired gateway token")
            self.refused(lambda: psql(f"SELECT * FROM devplat.budget_days", role=R["mg"]), "permission denied")
            self.refused(lambda: psql(f"SELECT devplat.reserve_budget({lit(g3)}, 'x', 1, 1)", role=R["ctl"]), "permission denied")
            # two concurrent reservations of 0.4 against 0.5 left: exactly one succeeds
            sql = (f'SET ROLE "{R["mg"]}"; BEGIN; SELECT devplat.reserve_budget({lit(g3)}, ' + "'{rid}'" +
                   ", 0.4, 1); SELECT pg_sleep(1); COMMIT;")
            procs = [subprocess.Popen(_psql_args(DB), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True) for _ in range(2)]
            for i, pr in enumerate(procs):
                pr.stdin.write(sql.replace("{rid}", f"par-{i}")); pr.stdin.close()
            rcs = sorted(pr.wait() for pr in procs)
            for pr in procs:
                pr.communicate()
            self.assertEqual(rcs, [0, 3], "one reservation commits, the other is refused")
            self.assertEqual(psql(f"SELECT (reserved_usd + settled_usd)::text FROM devplat.budget_days WHERE project_id = {lit(q)}"),
                             "9.9000")
        finally:
            type(self).project = old

    def test_artifact_gateway_authorizes_layout_caps_once(self):
        t = "UP-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        _, _, u, uid = self.job_with_tokens(t)
        auth = lambda name, size, tok=u, juid=uid: psql(
            f"SELECT r_bucket || ' ' || r_key FROM devplat.authorize_upload({lit(tok)}, '{juid}', {lit(name)}, {size})", role=R["ag"])
        self.assertEqual(auth("result.json", 100), f"devplat-{self.project} runs/{uid}/result.json")
        self.refused(lambda: auth("result.json", 100), "already uploaded for this run (one-time)")
        self.refused(lambda: auth("result.bundle", 268435457), "result.bundle over its cap")
        self.refused(lambda: auth("secrets.txt", 1), "not part of the run layout")
        self.refused(lambda: auth("runner.json", 1, juid="33333333-3333-3333-3333-333333333333"), "foreign")
        self.assertTrue(auth("result.bundle", 268435456))
        self.assertEqual(psql(f"SELECT devplat.complete_upload({lit(u)}, '{uid}', 'result.json', {lit(sha('r'))}, 99)", role=R["ag"]), "t")
        self.assertEqual(psql(f"SELECT devplat.complete_upload({lit(u)}, '{uid}', 'result.json', {lit(sha('r'))}, 99)", role=R["ag"]), "f")
        _, _, u2, uid2 = self.job_with_tokens(t, dispatch_no=2, deadline="now() - interval '20 minutes'")
        self.refused(lambda: auth("result.json", 1, tok=u2, juid=uid2), "expired upload token")
        self.refused(lambda: psql(f"SELECT * FROM devplat.authorize_upload({lit(u)}, '{uid}', 'runner.json', 1)", role=R["ctl"]),
                     "permission denied")


class T12RolesAndMigration(Base):
    def test_owner_nologin_and_migrator_least_privilege(self):
        flags = psql(f"SELECT rolname || ':' || rolcanlogin || ':' || rolsuper FROM pg_roles WHERE rolname IN "
                     f"({lit(R['owner'])}, {lit(R['migrator'])}, {lit(R['ctl'])}) ORDER BY rolname", db="postgres").splitlines()
        self.assertIn(f"{R['owner']}:false:false", flags)
        self.assertIn(f"{R['migrator']}:true:false", flags)
        self.assertEqual(psql(f"SELECT pg_has_role({lit(R['ctl'])}, {lit(R['owner'])}, 'MEMBER')"), "f",
                         "the controller is never a member of the owner role")
        self.refused(lambda: psql("CREATE TABLE devplat.x (i int)", role=R["ctl"]), "permission denied")
        self.refused(lambda: psql("ALTER TABLE devplat.task_events DISABLE TRIGGER USER", role=R["ctl"]), "must be owner")
        self.refused(lambda: psql("SELECT devplat.load_role_catalogue('evil', repeat('0', 64), '[]'::jsonb)", role=R["ctl"]),
                     "permission denied")
        owner = psql("SELECT tableowner FROM pg_tables WHERE schemaname = 'devplat' GROUP BY tableowner")
        self.assertEqual(owner, R["owner"])
        self.assertIn("schema applied by the migrator login", CONN["mode"])

    def test_catalogue_reload_is_versioned(self):
        profiles, digest = load_catalogue()
        self.assertEqual(psql(f"SELECT devplat.load_role_catalogue('test-{digest[:12]}', {lit(digest)}, {lit(profiles)})",
                              role=R["migrator"]), "0")
        self.refused(lambda: psql(f"SELECT devplat.load_role_catalogue('test-{digest[:12]}', {lit(sha('x'))}, {lit(profiles)})",
                                  role=R["migrator"]), "already loaded with different content")


if __name__ == "__main__":
    unittest.main(verbosity=2)
