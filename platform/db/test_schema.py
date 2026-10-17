#!/usr/bin/env python3
"""Tests for platform/db/schema.sql against a REAL PostgreSQL 16 server (no mocks, no psycopg: psql via subprocess).

Server selection:
  1. DEVPLAT_PG_HOST / DEVPLAT_PG_PORT / DEVPLAT_PG_USER if set, else the Amendment-001 scratch server
     (socket dir <scratchpad>/pg, port 55432, user devplat).
  2. If that server does not answer and PostgreSQL 16 binaries are present and we run as root, an EPHEMERAL private
     instance is started as `nobody` in a fresh mkdtemp directory and stopped and deleted at the end
     (DEVPLAT_PG_NO_EPHEMERAL=1 disables this).
Each run creates database devplat_test_<random> and roles dpt_<random>_{owner,ctl,api,ro,...}, and drops them at the end.

Run:  python3 platform/db/test_schema.py   (not `-m unittest platform...`: `platform` shadows the stdlib module)
"""
import hashlib, json, os, secrets, shutil, subprocess, sys, tempfile, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SCHEMA = os.environ.get("DEVPLAT_SCHEMA", os.path.join(HERE, "schema.sql"))   # override: mutation checks
DEFAULT_SOCK = "/tmp/claude-0/-home-user-Project-Mercury/16854e63-26a2-5af1-9adb-3e58b440561e/scratchpad/pg"
PGBIN = "/usr/lib/postgresql/16/bin"

SUFFIX = secrets.token_hex(4)
DB = f"devplat_test_{SUFFIX}"
R = {k: f"dpt_{SUFFIX}_{k}" for k in ("owner", "ctl", "api", "ro")}
EXTRA_ROLES = []                     # per-test roles created by tests (dropped at the end)
CONN = {}
EPHEMERAL = {}
ISSUER = "https://idp.example.test"
HOLDER = "ctrl-0"


class PgError(Exception):
    pass


def _psql_args(db):
    return ["psql", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", "-h", CONN["host"], "-p", str(CONN["port"]),
            "-U", CONN["user"], "-d", db]


def psql(sql, role=None, db=None, check=True):
    """Run SQL in a fresh session (optionally `SET ROLE role` first). Returns stdout; raises PgError on error."""
    text = (f'SET ROLE "{role}";\n' if role else "") + sql
    r = subprocess.run(_psql_args(db or DB), input=text, capture_output=True, text=True)
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
    print(f"\n[test_schema] PostgreSQL: {CONN['mode']}; database {DB}", file=sys.stderr)
    psql(f'CREATE DATABASE "{DB}"', db="postgres")
    r = subprocess.run(_psql_args(DB) + ["-v", f"role_owner={R['owner']}", "-v", f"role_controller={R['ctl']}",
                                         "-v", f"role_api={R['api']}", "-v", f"role_readonly={R['ro']}", "-f", SCHEMA],
                       capture_output=True, text=True)
    if r.returncode != 0:
        tearDownModule()
        raise RuntimeError("schema.sql failed to load:\n" + r.stderr)
    # platform admin configuration (migration-time, not a controller or api action)
    psql(f"INSERT INTO devplat.oidc_issuers (issuer, audience) VALUES ('{ISSUER}', 'devplat-api')")


def tearDownModule():
    try:
        if CONN:
            psql(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)', db="postgres", check=False)
            for role in EXTRA_ROLES + list(R.values()):
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
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def head(n):
    return hashlib.sha1(f"head-{n}".encode()).hexdigest()


TOKENS = {}


class Base(unittest.TestCase):
    project = None

    @classmethod
    def setUpClass(cls):
        cls.project = cls.project or ("p" + secrets.token_hex(3))
        p = cls.project
        psql(f"SELECT devplat.upsert_project({lit(p)}, 'Test {p}', 'owner/{p}', NULL, 'projects/{p}.yaml@abc', "
             f"{lit('devplat-' + p)}, '{{}}'::jsonb)", role=R["ctl"])
        for key in ("DOD-02", "DOD-03"):
            cls.fact(key, {"status": "satisfied"})

    # --- operator facts through the api role
    @classmethod
    def fact(cls, key, value, task=None, subject="operator-jb", auth_age_s=5, project="__cls__"):
        project = cls.project if project == "__cls__" else project
        jti = secrets.token_hex(8)
        return int(psql(f"SELECT devplat.record_operator_fact({lit(project)}, {lit(key)}, {lit(value)}, {lit(task)}, "
                        f"'statement', {lit(subject)}, {lit(ISSUER)}, 'op@example.test', "
                        f"now() - interval '{auth_age_s} seconds', {lit(jti)}, NULL)", role=R["api"]))

    def artifact(self, content, kind="result"):
        h = sha(content)
        psql(f"SELECT * FROM devplat.register_artifact({lit(self.project)}, {lit(h)}, {lit('devplat-' + self.project)}, "
             f"{len(content)}, 'application/json', {lit(kind)}, NULL, NULL, NULL, 'evidence')", role=R["ctl"])
        return h

    def fev(self, kind, content=None):
        h = self.artifact(content or f"{kind}-{secrets.token_hex(6)}")
        return {"kind": kind, "ref": f"sha256/{h}", "sha256": h}

    def new_task(self, tid, kind, parent=None, covers=None, body=None, max_attempts=3, version=1):
        tok = int(psql(f"SELECT devplat.create_task({lit(self.project)}, {lit(tid)}, {lit(kind)}, {lit(parent)}, "
                       f"{('ARRAY[' + ','.join(lit(c) for c in covers) + ']::text[]') if covers else 'NULL'}, NULL, "
                       f"{lit(HOLDER)}, 3600)", role=R["ctl"]))
        TOKENS[tid] = tok
        self.contract(tid, version, body or {"kind": kind, "task_id": tid}, max_attempts)
        self.ev(tid, "created", [{"kind": "ledger", "ref": "created"}], version=version)
        return tok

    def contract(self, tid, version, body, max_attempts=3):
        body = dict(body, contract_version=version)
        core = sha(json.dumps(body, sort_keys=True, separators=(",", ":")))
        psql(f"SELECT devplat.register_contract({lit(tid)}, {version}, {lit(core)}, {lit(body)}, {max_attempts}, "
             f"{lit(HOLDER)}, {TOKENS[tid]})", role=R["ctl"])
        return core

    def ev(self, tid, event, evidence, head_commit=None, payload=None, attempt=1, version=1, holder=HOLDER, token=None,
           key=None, outbox=None):
        out = psql(f"SELECT r_seq, r_from_state, r_to_state, coalesce(r_gate,''), r_replayed FROM devplat.record_event("
                   f"{lit(tid)}, {lit(event)}, {version}, {attempt}, {lit(holder)}, "
                   f"{token if token is not None else TOKENS[tid]}, {lit(evidence)}, {lit(head_commit)}, "
                   f"{lit(payload or {})}, {lit(key)}, {lit(outbox or [])})", role=R["ctl"])
        seq, frm, to, gate, replayed = out.split("|")
        return {"seq": int(seq), "from": frm, "to": to, "gate": gate, "replayed": replayed == "t"}

    def refused(self, fn, *needles):
        with self.assertRaises(PgError) as cm:
            fn()
        for n in needles:
            self.assertIn(n, str(cm.exception))
        return str(cm.exception)

    def task(self, tid):
        out = psql(f"SELECT state, array_to_string(gates, ','), counts::text, coalesce(head_commit,''), attempt "
                   f"FROM devplat.tasks WHERE task_id = {lit(tid)}")
        st, gates, counts, h, att = out.split("|")
        return {"state": st, "gates": [g for g in gates.split(",") if g], "counts": json.loads(counts), "head": h,
                "attempt": int(att) if att else None}

    def chain_problems(self, tid=None):
        return psql(f"SELECT v_task_id || ':' || coalesce(v_seq::text, '-') || ':' || v_problem FROM devplat.verify_chain({lit(tid)})")

    # --- flows
    DR = {"kind": "design_ref", "ref": "docs/design.md§1@" + "a" * 40}

    def to_running(self, tid):
        self.ev(tid, "unblocked", [self.DR])
        self.ev(tid, "assigned", [{"kind": "ledger", "ref": "assigned"}])
        self.ev(tid, "dispatched", [{"kind": "job", "ref": f"dp-{tid.lower()}-a1"}])

    def implement_and_test(self, tid, h, attempt=1):
        self.ev(tid, "implementation_completed", [self.fev("result_file")], head_commit=h, attempt=attempt)
        return self.ev(tid, "tests_passed", [self.fev("test_run")], head_commit=h, attempt=attempt)

    def subtask(self, sid, kind, parent=None, covers=None, result=None, review_head=None):
        body = {"kind": kind, "task_id": sid}
        if review_head:
            body["review_target"] = {"implementation_task_id": parent, "head_commit": review_head}
        self.new_task(sid, kind, parent=parent, covers=covers, body=body)
        self.to_running(sid)
        return self.ev(sid, "result_accepted", [self.fev("result_file")], payload={"result": result})

    def full_to_review(self, tid, body=None):
        self.new_task(tid, "implementation", body=body or {"kind": "implementation", "task_id": tid,
                                                          "required_reviewers": ["mdev-code-reviewer", "mdev-security-engineer"]})
        self.to_running(tid)
        self.implement_and_test(tid, head(tid))
        return head(tid)

    def accept_review(self, h):
        return {"recommendation": "accept", "reviewed_head_commit": h, "blocking_findings": 0}


# ------------------------------------------------------------------------------------------------- tests
class T01RulesPortedFromDevorch(Base):
    def test_transitions_table_matches_devorch(self):
        sys.dont_write_bytecode = True
        sys.path.insert(0, os.path.join(REPO, "tools", "devorch"))
        import devorch as d
        want = set()
        for name, T in (("FULL", d.T_FULL), ("SHORT", d.T_SHORT)):
            for (f, e), t in T.items():
                g = d.GATE_OF.get(e) if (name == "FULL" or e == "unblocked") else None
                want.add((name, f, e, t, g or ""))
        got = {tuple(l.split("|")) for l in psql(
            "SELECT lifecycle, from_state, event, to_state, coalesce(gate,'') FROM devplat.transitions").splitlines()}
        self.assertEqual(got, want)
        req = {}
        for l in psql("SELECT to_state, gate FROM devplat.gate_prerequisites").splitlines():
            s, g = l.split("|")
            req.setdefault(s, set()).add(g)
        self.assertEqual(req, {k: set(v) for k, v in d.REQUIRED_BEFORE.items()})
        lim = dict(l.split("|") for l in psql("SELECT counter, coalesce(max_count::text,'') FROM devplat.loop_counters").splitlines())
        self.assertEqual({k: (int(v) if v else None) for k, v in lim.items()}, d.LIMITS)
        kinds = dict(l.split("|") for l in psql("SELECT kind, lifecycle FROM devplat.task_kinds").splitlines())
        self.assertEqual({k for k, v in kinds.items() if v == "SHORT"}, d.SHORT_KINDS)
        self.assertEqual({k for k, v in kinds.items() if v == "FULL"}, d.FULL_KINDS)


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
                     result={"status": "completed", "recommendation": "accept", "integrated_heads": [f"{t}@{h}"]})
        self.assertEqual(self.ev(t, "integration_verified", [{"kind": "subtask", "ref": f"{t}-i1"}])["gate"], "G5")
        r = self.ev(t, "pr_prepared", [{"kind": "pr", "ref": "owner/repo#1"}, self.fev("ci_run")], head_commit=h)
        self.assertEqual((r["to"], r["gate"]), ("AWAITING_HUMAN", "G6"))
        r = self.ev(t, "human_merged", [{"kind": "github_merge", "ref": "owner/repo#1 merged_by operator"}], head_commit=h)
        self.assertEqual((r["to"], r["gate"]), ("COMPLETED", "G7"))
        self.ev(t, "closed", [{"kind": "ledger", "ref": "closed"}])
        st = self.task(t)
        self.assertEqual(st["state"], "COMPLETED")
        self.assertEqual(st["gates"], ["G1", "G2", "G3", "G4", "G5", "G6", "G7"])
        for x in (t, f"{t}-r1", f"{t}-s1", f"{t}-i1"):
            self.assertEqual(self.chain_problems(x), "", x)
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.task_events WHERE task_id = {lit(t)}"), "12")


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

    def test_g1_requires_design_ref_and_operator_facts(self):
        t = "G1-0001"
        self.new_task(t, "implementation")
        self.refused(lambda: self.ev(t, "unblocked", [{"kind": "ledger", "ref": "x"}]), "G1 needs design_ref")
        self.fact("DOD-03", {"status": "revoked"})          # a newer fact revokes the precondition
        try:
            self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "hard precondition DOD-03")
        finally:
            self.fact("DOD-03", {"status": "satisfied"})
        self.assertEqual(self.ev(t, "unblocked", [self.DR])["gate"], "G1")

    def test_g2_requires_checked_implementation_at_that_head(self):
        t = "G2-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        self.refused(lambda: self.ev(t, "tests_passed", [self.fev("test_run")], head_commit=head(2)),
                     "not the head of a checked implementation_completed")
        self.refused(lambda: self.ev(t, "implementation_completed", [{"kind": "result_file", "ref": "x", "sha256": "0" * 64}],
                                     head_commit=head(2)), "not a registered artifact")

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
        self.refused(lambda: self.ev(t, "unblocked", [self.DR]), "illegal transition")

    def test_review_bound_to_tested_head(self):
        t = "RB-0001"
        h = self.full_to_review(t)
        stale = head("stale")
        self.subtask(f"{t}-r1", "code_review", parent=t, result=self.accept_review(stale), review_head=stale)
        self.refused(lambda: self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r1"}]),
                     f"not bound to the current tested head {h}")
        # required_reviewers: a design review alone does not satisfy mdev-code-reviewer
        self.subtask(f"{t}-r2", "design_review", parent=t, result=self.accept_review(h), review_head=h)
        self.refused(lambda: self.ev(t, "code_review_passed", [{"kind": "subtask", "ref": f"{t}-r2"}]),
                     "G3 requires a passed code_review")
        # a review subtask id must follow <parent>-rN
        self.refused(lambda: psql(f"SELECT devplat.create_task({lit(self.project)}, 'RB-0001-x9', 'code_review', "
                                  f"'RB-0001', NULL, NULL, {lit(HOLDER)}, 60)", role=R["ctl"]), "subtask id must be RB-0001-rN")


class T04Budgets(Base):
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
        self.contract(t, 2, {"kind": "implementation", "task_id": t, "allowed_paths": ["src/**"]})
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], version=2), "contract changed without a contract_revised")
        r = self.ev(t, "contract_revised", [{"kind": "ledger", "ref": "rev"}], version=2)
        self.assertEqual(r["to"], "BLOCKED")
        self.refused(lambda: self.ev(t, "contract_revised", [{"kind": "ledger", "ref": "rev"}], version=2),
                     "contract_revised needs a higher contract_version")
        self.refused(lambda: self.contract(t, 1, {"kind": "implementation", "task_id": t, "x": 1}),
                     "contract version already registered")


class T05AuditTrail(Base):
    def test_task_events_update_delete_refused(self):
        t = "AU-0001"
        self.new_task(t, "implementation")
        for sql in (                    f"UPDATE devplat.task_events SET head_commit = NULL WHERE task_id = '{t}'",
                    f"DELETE FROM devplat.task_events WHERE task_id = '{t}'",
                    f"INSERT INTO devplat.task_events (project_id) VALUES ('x')",
                    f"UPDATE devplat.tasks SET state = 'COMPLETED' WHERE task_id = '{t}'"):
            self.refused(lambda: psql(sql, role=R["ctl"]))         # no table privileges at all
        self.refused(lambda: psql(f"UPDATE devplat.task_events SET head_commit = NULL WHERE task_id = '{t}'"),
                     "task_events is append-only (UPDATE forbidden)")   # even the superuser, triggers on
        self.refused(lambda: psql(f"DELETE FROM devplat.task_events WHERE task_id = '{t}'"),
                     "task_events is append-only (DELETE forbidden)")
        self.refused(lambda: psql("TRUNCATE devplat.task_events CASCADE"), "append-only (TRUNCATE forbidden)")
        self.refused(lambda: psql(f"UPDATE devplat.tasks SET state = 'COMPLETED' WHERE task_id = '{t}'"),
                     "task state changes only through record_event()")
        self.refused(lambda: psql(f"SELECT * FROM devplat.record_event('{t}', 'unblocked', 1, 1, 'x', 1)", role=R["api"]),
                     "permission denied")
        self.assertEqual(self.chain_problems(t), "")

    def test_hash_chain_detects_superuser_tamper(self):
        t, u = "TP-0001", "TP-0002"
        for x in (t, u):
            self.new_task(x, "implementation")
            self.to_running(x)
        self.assertEqual(self.chain_problems(t), "")
        # 1) in-place edit with triggers bypassed (superuser only)
        psql(f"SET session_replication_role = replica; UPDATE devplat.task_events SET evidence = "
             f"'[{{\"kind\":\"design_ref\",\"ref\":\"forged\"}}]' WHERE task_id = '{t}' AND seq = 2")
        self.assertIn(f"{t}:2:hash mismatch (row altered)", self.chain_problems(t))
        # 2) deleting the tail is detected against the tasks row
        psql(f"SET session_replication_role = replica; DELETE FROM devplat.task_events WHERE task_id = '{t}' AND seq = 4")
        self.assertIn("does not match the chain tail", self.chain_problems(t))
        # 3) honest limit: a CONSISTENT rewrite (rehash the rest of the chain and the tasks row) passes verify_chain;
        #    only a checkpoint exported before the rewrite reveals it
        digest_before = psql("SELECT r_digest FROM devplat.chain_digest()")
        psql(f"""SET session_replication_role = replica;
DO $$ DECLARE e devplat.task_events; prev text; BEGIN
  UPDATE devplat.task_events SET payload = '{{"forged": true}}' WHERE task_id = '{u}' AND seq = 3;
  SELECT hash INTO prev FROM devplat.task_events WHERE task_id = '{u}' AND seq = 2;
  FOR e IN SELECT * FROM devplat.task_events WHERE task_id = '{u}' AND seq >= 3 ORDER BY seq LOOP
    e.prev_hash := prev; e.hash := devplat.event_hash(e);
    UPDATE devplat.task_events SET prev_hash = e.prev_hash, hash = e.hash WHERE task_id = '{u}' AND seq = e.seq;
    prev := e.hash;
  END LOOP;
  UPDATE devplat.tasks SET last_hash = prev WHERE task_id = '{u}';
END $$;""")
        self.assertEqual(self.chain_problems(u), "", "a consistent superuser rewrite is NOT detectable in-database")
        self.assertNotEqual(psql("SELECT r_digest FROM devplat.chain_digest()"), digest_before,
                            "but the checkpoint digest changes")

    def test_record_event_idempotency_key_replay(self):
        t = "IK-0001"
        self.new_task(t, "implementation")
        a = self.ev(t, "unblocked", [self.DR], key="k-unblock-1")
        b = self.ev(t, "unblocked", [self.DR], key="k-unblock-1")
        self.assertEqual((a["seq"], a["replayed"], b["seq"], b["replayed"]), (2, False, 2, True))
        self.refused(lambda: self.ev(t, "assigned", [{"kind": "ledger", "ref": "x"}], key="k-unblock-1"),
                     "already used for a different record")
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.task_events WHERE task_id = '{t}'"), "2")


class T06Execution(Base):
    def test_idempotent_dispatch_concurrent(self):
        t = "ID-0001"
        self.new_task(t, "implementation")
        self.to_running(t)
        key = sha(f"{self.project}|core|1")
        sql = (f'SET ROLE "{R["ctl"]}"; BEGIN; SELECT r_job_id, r_created FROM devplat.dispatch_job({lit(t)}, 1, '
               f"'mdev-backend-engineer', 1, {lit(key)}, NULL, 'proj-{self.project}-exec', 'dp-{self.project}-id-0001-a1', "
               f"{lit(HOLDER)}, {TOKENS[t]}); SELECT pg_sleep(1.5); COMMIT;")
        t0 = time.time()
        procs = [subprocess.Popen(_psql_args(DB), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for _ in range(2)]
        for p in procs:
            p.stdin.write(sql); p.stdin.close()
        outs = []
        for p in procs:
            so, se = p.communicate()
            outs.append((p.returncode, so.strip(), se.strip()))
        elapsed = time.time() - t0
        self.assertEqual([o[0] for o in outs], [0, 0], outs)
        rows = sorted(o[1].splitlines()[0] for o in outs)
        ids = {r.split("|")[0] for r in rows}
        self.assertEqual(len(ids), 1, rows)
        self.assertEqual(sorted(r.split("|")[1] for r in rows), ["f", "t"])
        self.assertGreater(elapsed, 2.5, "second session must have waited for the first (true concurrency)")
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.job_runs WHERE task_id = '{t}'"), "1")
        # a different key for the same (task, attempt, role, dispatch_no) is a duplicate execution: refused
        self.refused(lambda: psql(f"SELECT * FROM devplat.dispatch_job({lit(t)}, 1, 'mdev-backend-engineer', 1, "
                                  f"{lit(sha('other'))}, NULL, 'proj-x-exec', 'dp-other-a1', {lit(HOLDER)}, {TOKENS[t]})",
                                  role=R["ctl"]), "already belongs to another idempotency key")
        # Job uid change (deleted and recreated Job object) is flagged
        jid = ids.pop()
        uid1, uid2 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
        psql(f"SELECT devplat.update_job_phase({jid}, 'created', '{uid1}', NULL, NULL, {lit(HOLDER)}, {TOKENS[t]})", role=R["ctl"])
        self.assertEqual(psql(f"SELECT devplat.job_heartbeat({jid}, '{uid1}')", role=R["ctl"]), "t")
        self.refused(lambda: psql(f"SELECT devplat.update_job_phase({jid}, 'running', '{uid2}', NULL, NULL, {lit(HOLDER)}, "
                                  f"{TOKENS[t]})", role=R["ctl"]), "duplicate execution")
        self.refused(lambda: psql(f"SELECT devplat.update_job_phase({jid}, 'planned', NULL, NULL, NULL, {lit(HOLDER)}, "
                                  f"{TOKENS[t]})", role=R["ctl"]), "illegal job phase change created -> planned")

    def test_task_lease_fencing(self):
        t = "LF-0001"
        tok_a = int(psql(f"SELECT devplat.create_task({lit(self.project)}, {lit(t)}, 'implementation', NULL, NULL, NULL, "
                         f"'ctrl-a', 2)", role=R["ctl"]))
        TOKENS[t] = tok_a
        psql(f"SELECT devplat.register_contract({lit(t)}, 1, {lit(sha(t))}, '{{}}'::jsonb, 3, 'ctrl-a', {tok_a})", role=R["ctl"])
        self.ev(t, "created", [{"kind": "ledger", "ref": "c"}], holder="ctrl-a", token=tok_a)
        self.assertEqual(psql(f"SELECT devplat.acquire_task_lease({lit(t)}, 'ctrl-b', 60)", role=R["ctl"]), "",
                         "B cannot take an unexpired lease")
        time.sleep(2.5)
        # an expired lease is lost even if nobody took it over: the old holder's write with its own token is refused
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], holder="ctrl-a", token=tok_a), "stale or missing task lease")
        tok_b = int(psql(f"SELECT devplat.acquire_task_lease({lit(t)}, 'ctrl-b', 60)", role=R["ctl"]))
        self.assertEqual(tok_b, tok_a + 1)
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], holder="ctrl-a", token=tok_a), "stale or missing task lease")
        self.assertEqual(psql(f"SELECT devplat.acquire_task_lease({lit(t)}, 'ctrl-a', 60)", role=R["ctl"]), "")
        self.refused(lambda: self.ev(t, "unblocked", [self.DR], holder="ctrl-b", token=tok_a), "stale or missing task lease")
        self.assertEqual(self.ev(t, "unblocked", [self.DR], holder="ctrl-b", token=tok_b)["to"], "READY")
        self.assertEqual(psql(f"SELECT controller_id || '/' || lease_token FROM devplat.task_events WHERE task_id = '{t}' "
                              f"ORDER BY seq"), f"ctrl-a/{tok_a}\nctrl-b/{tok_b}")


class T07SideEffects(Base):
    def test_outbox_dedup(self):
        p = self.project
        q = (f"SELECT r_outbox_id || '|' || r_created FROM devplat.enqueue_outbox({lit(p)}, 'github', 'open_draft_pr', "
             f"'gh:{p}:OB-0001:pr', '{{\"head\": \"x\"}}'::jsonb)")
        a, b = psql(q, role=R["ctl"]).split("|"), psql(q, role=R["ctl"]).split("|")
        self.assertEqual((a[0] == b[0], a[1], b[1]), (True, "true", "false"))
        self.refused(lambda: psql(f"SELECT * FROM devplat.enqueue_outbox({lit(p)}, 'github', 'merge_pr', 'gh:{p}:merge', "
                                  f"'{{}}'::jsonb)", role=R["ctl"]), "not an allowed outbox operation")
        self.refused(lambda: psql(f"SELECT * FROM devplat.enqueue_outbox({lit(p)}, 'linear', 'comment_issue', 'ln:{p}:1', "
                                  f"'{{}}'::jsonb)", role=R["ctl"]), "Linear writes need operator fact DOD-05")
        # transactional enqueue from record_event with the same dedup key does not duplicate
        t = "OB-0001"
        self.new_task(t, "implementation")
        self.ev(t, "unblocked", [self.DR], outbox=[{"target": "github", "operation": "open_draft_pr",
                                                   "dedup_key": f"gh:{p}:OB-0001:pr", "payload": {}}])
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.outbox WHERE dedup_key = 'gh:{p}:OB-0001:pr'"), "1")
        # claim / fenced completion / backoff
        oid = psql(f"SELECT outbox_id FROM devplat.claim_outbox('disp-1', 10) WHERE dedup_key = 'gh:{p}:OB-0001:pr'", role=R["ctl"])
        self.assertTrue(oid)
        self.assertEqual(psql(f"SELECT count(*) FROM devplat.claim_outbox('disp-2', 10) WHERE outbox_id = {oid}", role=R["ctl"]), "0")
        self.assertEqual(psql(f"SELECT devplat.fail_outbox({oid}, 'disp-1', '403 rate limited', true, 60)", role=R["ctl"]), "pending")
        self.assertEqual(psql(f"SELECT next_attempt_at > now() + interval '50 seconds' FROM devplat.outbox WHERE outbox_id = {oid}"), "t")
        psql(f"UPDATE devplat.outbox SET next_attempt_at = now() WHERE outbox_id = {oid}")   # test shortcut (superuser)
        psql(f"SELECT 1 FROM devplat.claim_outbox('disp-2', 10)", role=R["ctl"])
        self.assertEqual(psql(f"SELECT devplat.complete_outbox({oid}, 'disp-1', 'PR#7')", role=R["ctl"]), "f",
                         "stale claimer cannot complete")
        self.assertEqual(psql(f"SELECT devplat.complete_outbox({oid}, 'disp-2', 'PR#7')", role=R["ctl"]), "t")
        self.assertEqual(psql(f"SELECT status || '|' || attempts FROM devplat.outbox WHERE outbox_id = {oid}"), "done|2")
        self.fact("DOD-05", {"status": "satisfied"})
        self.assertEqual(psql(f"SELECT r_created FROM devplat.enqueue_outbox({lit(p)}, 'linear', 'comment_issue', "
                              f"'ln:{p}:1', '{{}}'::jsonb)", role=R["ctl"]), "t")


class T08OperatorFacts(Base):
    def test_operator_fact_not_writable_by_controller(self):
        p = self.project
        call = (f"SELECT devplat.record_operator_fact({lit(p)}, 'DOD-02', '{{\"status\":\"satisfied\"}}'::jsonb, NULL, 's', "
                f"'operator-jb', {lit(ISSUER)}, NULL, now(), {lit(secrets.token_hex(8))}, NULL)")
        self.refused(lambda: psql(call, role=R["ctl"]), "permission denied for function record_operator_fact")
        self.refused(lambda: psql(f"INSERT INTO devplat.operator_facts (fact_key, value, subject, issuer, auth_time, token_jti, "
                                  f"recorded_via) VALUES ('DOD-02', '{{}}', 'x', {lit(ISSUER)}, now(), 'j', 'x')", role=R["ctl"]),
                     "permission denied for table operator_facts")
        self.refused(lambda: psql(call, role=R["ro"]), "permission denied")
        # api: workload identities, stale authentication, replayed token and unknown issuers are refused
        self.refused(lambda: self.fact("DOD-02", {"status": "satisfied"}, subject="system:serviceaccount:proj-x-exec:agent"),
                     "is not a human operator identity")
        self.refused(lambda: self.fact("DOD-02", {"status": "satisfied"}, auth_age_s=3600), "not fresh")
        jti = secrets.token_hex(8)
        once = (f"SELECT devplat.record_operator_fact({lit(p)}, 'note', '{{}}'::jsonb, NULL, 's', 'operator-jb', {lit(ISSUER)}, "
                f"NULL, now(), {lit(jti)}, NULL)")
        psql(once, role=R["api"])
        self.refused(lambda: psql(once, role=R["api"]), "duplicate key")
        self.refused(lambda: psql(once.replace(ISSUER, "https://evil.test").replace(jti, "j2"), role=R["api"]),
                     "not an enabled operator identity provider")
        self.refused(lambda: psql(f"UPDATE devplat.operator_facts SET subject = 'x'"), "operator_facts is append-only")

    def test_operator_task_completion_needs_authenticated_fact(self):
        t = "MV-0001"
        self.new_task(t, "mac_validation")
        self.to_running(t)
        self.refused(lambda: self.ev(t, "result_accepted", [self.fev("operator_statement")]),
                     "needs an authenticated operator fact for this task")
        fid = self.fact("task_result", {"status": "passed"}, task=t)
        r = self.ev(t, "result_accepted", [{"kind": "operator_fact", "ref": str(fid)}])
        self.assertEqual(r["to"], "COMPLETED")
        self.assertEqual(psql(f"SELECT on_behalf_of FROM devplat.task_events WHERE task_id = '{t}' AND seq = {r['seq']}"),
                         f"{ISSUER}#operator-jb")


class T09Isolation(Base):
    def test_rls_project_isolation(self):
        other = "q" + secrets.token_hex(3)
        psql(f"SELECT devplat.upsert_project({lit(other)}, 'Other', NULL, NULL, 'r@1', {lit('devplat-' + other)})", role=R["ctl"])
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
        self.assertEqual(psql(f"SELECT count(*) > 0 FROM devplat.tasks WHERE project_id <> {lit(self.project)}", role=R["api"]), "t")
        self.refused(lambda: psql("SELECT * FROM devplat.leases", role=role), "permission denied")

    def test_artifact_immutability_and_bucket(self):
        h = self.artifact("immutable-content")
        self.refused(lambda: psql(f"UPDATE devplat.artifacts SET size_bytes = 1 WHERE sha256 = '{h}'"), "identity is immutable")
        self.refused(lambda: psql(f"DELETE FROM devplat.artifacts WHERE sha256 = '{h}'"), "artifact is retained")
        self.refused(lambda: psql(f"SELECT * FROM devplat.register_artifact({lit(self.project)}, {lit(sha('z'))}, 'other-bucket', "
                                  f"1, 'text/plain', 'log', NULL, NULL, NULL, 'standard')", role=R["ctl"]),
                     "not the project's artifact bucket")
        self.refused(lambda: psql(f"SELECT * FROM devplat.register_artifact({lit(self.project)}, {lit(sha('big'))}, "
                                  f"{lit('devplat-' + self.project)}, 2000000, 'application/json', 'result', NULL, NULL, NULL, "
                                  f"'evidence')", role=R["ctl"]), "result artifact over 1048576 bytes")
        self.assertEqual(psql("SELECT count(*) FROM devplat.expire_artifacts(100)", role=R["ctl"]), "0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
