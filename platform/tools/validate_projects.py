#!/usr/bin/env python3
"""Validate devplat project configurations (devplat.project.v1).

Usage:
  python3 platform/tools/validate_projects.py [FILE ...]      # default: platform/projects/*.yaml
  python3 platform/tools/validate_projects.py --self-test     # negative cases: each mutation must be rejected

Checks (doc 26-project-configuration.md §1.5):
  1. JSON Schema Draft 2020-12 (platform/schemas/project-config.schema.json), with format checking.
  2. Status rules: draft = anything may be unresolved; onboarding = the security core is resolved;
     active = nothing anywhere is unresolved, every secret is provisioned, governance is applied and verified,
     the design is approved and no Kubernetes test level is only 'planned'.
  3. Cross-field rules: file name = project_id; namespace_prefix = proj-<project_id>; bucket = devplat-<project_id>;
     test levels point at declared environments; read-only roles have no path scopes; no role scope inside
     restricted_paths (same rule as devorch check-contract); reviewers are enabled roles; unique ids across the registry.
  4. Role catalogue (R6 D6): every role is a role of the platform catalogue (platform/agents/execution-profiles.yaml),
     its task_kinds are kinds the catalogue gives it, a role whose kinds are all read-only cannot write, reviewers are
     roles of a gated review kind; the catalogue itself is consistent with the profiles.
  5. Hard preconditions and assurance (R6 D1, D16): hard-precondition keys are not duplicated as external gates;
     runtime_class 'default' requires security.reduced_assurance, which forbids build environments and needs a
     sandbox repository different from the source repository.
  6. No secret values: strings that look like keys or tokens are refused.
Exit status 0 = all files valid, 1 = at least one violation, 2 = usage or environment error.
Dependencies: Python standard library, PyYAML, jsonschema (tested with 4.26.0). No project literal in this file.
"""
import copy, glob, json, os, re, sys

try:
    import yaml
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError as e:  # pragma: no cover
    print(f"ERROR: missing dependency: {e} (pip install pyyaml jsonschema==4.26.0)", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = os.path.dirname(HERE)
SCHEMA_PATH = os.path.join(PLATFORM, "schemas", "project-config.schema.json")
PROFILES_PATH = os.path.join(PLATFORM, "agents", "execution-profiles.yaml")
PROFILES_SCHEMA_PATH = os.path.join(PLATFORM, "schemas", "execution-profiles.schema.json")
NON_JOB_ACTORS = {"operator", "mac-validation-queue"}
DEFAULT_GLOB = os.path.join(PLATFORM, "projects", "*.yaml")

# Fields that must be resolved before a project leaves 'draft' (the security core).
SECURITY_CORE = [
    ("source_repository", "url"), ("source_repository", "default_branch"), ("source_repository", "owner_kind"),
    ("security",), ("review_gates",), ("github_policy", "pr_mode"), ("github_policy", "branch_prefix"),
    ("github_policy", "base_branch"), ("github_policy", "merge_by"), ("github_policy", "agent_may"),
    ("execution_target",), ("identities", "github_app"), ("network", "model_providers"), ("network", "classes_allowed"),
]

SECRET_PATTERNS = [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "PEM private key"),
    (r"\bsk-ant-[A-Za-z0-9_-]{10,}", "Anthropic API key"),
    (r"\bsk-(proj-)?[A-Za-z0-9]{20,}", "OpenAI-style API key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{20,}", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}", "GitHub fine-grained token"),
    (r"\bxox[abprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS access key id"),
    (r"\blin_(api|oauth)_[A-Za-z0-9]{20,}", "Linear key"),
]


def glob_re(pat):
    """Same semantics as devorch: '**/' = zero or more dirs, '**' = anything, '*' and '?' never match '/'."""
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


def inside(scope, restricted):
    probe = scope.replace("**", "x").replace("*", "x")
    return any(glob_re(r).match(probe) for r in restricted)


def is_unresolved(v):
    return isinstance(v, dict) and "unresolved" in v


def find(obj, pred, path=""):
    """Yield (json-path, value) for every node where pred(value) holds."""
    if pred(obj):
        yield path or "/", obj
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from find(v, pred, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from find(v, pred, f"{path}/{i}")


def get(doc, keys):
    cur = doc
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def catalogue_errors(cat):
    """Consistency of the platform role catalogue with the execution profiles (R6 D6)."""
    errs = []
    kinds = {k["kind"]: k for k in cat["kind_catalogue"]}
    if len(kinds) != len(cat["kind_catalogue"]):
        errs.append("catalogue: duplicate kind")
    roles = {p["role"]: p for p in cat["profiles"]}
    if len(roles) != len(cat["profiles"]):
        errs.append("catalogue: duplicate profile role")
    for k in cat["kind_catalogue"]:
        for ex in k["executors"]:
            if k["job"] and ex not in roles:
                errs.append(f"catalogue: kind {k['kind']} executor '{ex}' has no execution profile")
            if not k["job"] and ex not in NON_JOB_ACTORS:
                errs.append(f"catalogue: non-Job kind {k['kind']} names '{ex}', not a non-Job actor")
        if k.get("gate") and not k["read_only"]:
            errs.append(f"catalogue: review kind {k['kind']} must be read_only")
    for r, p in roles.items():
        given = {k["kind"] for k in cat["kind_catalogue"] if r in k["executors"]}
        if set(p["kinds"]) != given:
            errs.append(f"catalogue: profile {r} kinds {sorted(p['kinds'])} != catalogue {sorted(given)}")
        if given and all(kinds[k]["read_only"] for k in given if k in kinds) and p["writes_allowed"]:
            errs.append(f"catalogue: profile {r} only has read-only kinds but writes_allowed is true")
    return errs


def load_catalogue(path=None):
    cat = yaml.safe_load(open(path or PROFILES_PATH))
    sch = json.load(open(PROFILES_SCHEMA_PATH))
    Draft202012Validator.check_schema(sch)
    errs = [f"profiles schema {'/'.join(map(str, e.absolute_path))}: {e.message[:200]}"
            for e in Draft202012Validator(sch).iter_errors(cat)]
    return cat, errs or catalogue_errors(cat)


CATALOGUE = None


def catalogue():
    global CATALOGUE
    if CATALOGUE is None:
        CATALOGUE, errs = load_catalogue()
        if errs:
            raise SystemExit("ERROR: role catalogue invalid: " + "; ".join(errs))
    return CATALOGUE


def check(doc, file_stem, validator, cat=None):
    errs = []
    for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        loc = "/" + "/".join(str(p) for p in e.absolute_path)
        errs.append(f"schema {loc}: {e.message[:300]}")
    if errs:
        return errs  # cross-field rules assume a schema-valid document

    for s in strings(doc):
        for pat, what in SECRET_PATTERNS:
            if re.search(pat, s):
                errs.append(f"secret value detected ({what}); only secret NAMES may appear")

    pid, status = doc["project_id"], doc["status"]
    if file_stem != pid:
        errs.append(f"file name '{file_stem}' does not match project_id '{pid}'")
    if doc["execution_target"]["namespace_prefix"] != f"proj-{pid}":
        errs.append(f"execution_target.namespace_prefix must be 'proj-{pid}'")
    if doc["artifacts"]["bucket"] != f"devplat-{pid}":
        errs.append(f"artifacts.bucket must be 'devplat-{pid}' (per-project bucket, artifact layout R6 D11)")

    env_ids = [e["id"] for e in doc["environments"]]
    if len(env_ids) != len(set(env_ids)):
        errs.append("duplicate environment id")
    if isinstance(doc["test_levels"], list):
        ids = [t["id"] for t in doc["test_levels"]]
        if len(ids) != len(set(ids)):
            errs.append("duplicate test level id")
        for t in doc["test_levels"]:
            if t["environment"] not in env_ids:
                errs.append(f"test level {t['id']}: unknown environment '{t['environment']}'")

    cat = cat or catalogue()
    cat_roles = {p["role"]: p for p in cat["profiles"]}
    cat_kinds = {k["kind"]: k for k in cat["kind_catalogue"]}
    restricted = doc["security"]["restricted_paths"]
    roles = doc["agent_permissions"]["roles"]
    for name, r in roles.items():
        if name not in cat_roles:
            errs.append(f"role {name}: not a role of the platform catalogue")
            continue
        given = set(cat_roles[name]["kinds"])
        for k in r.get("task_kinds", []):
            if k not in given:
                errs.append(f"role {name}: task kind '{k}' is not given to this role by the catalogue")
        if r["writes"] and all(cat_kinds[k]["read_only"] for k in given):
            errs.append(f"role {name}: catalogue kinds are all read-only, so writes must be false")
        scopes = r["path_scopes"]
        if not r["writes"] and scopes != []:
            errs.append(f"role {name}: read-only role must have path_scopes []")
        if isinstance(scopes, list) and isinstance(restricted, list):
            for sc in scopes:
                if inside(sc, restricted):
                    errs.append(f"role {name}: path scope '{sc}' falls inside restricted_paths")
    rr = doc["review_gates"]["required_reviewers"]
    for kind, lst in rr.items():
        if kind == "root_artefacts":
            continue
        for rv in lst:
            if rv in cat_roles and not any(cat_kinds[k].get("gate") for k in cat_roles[rv]["kinds"]):
                errs.append(f"required_reviewers.{kind}: '{rv}' has no review kind with a gate in the catalogue")
            if rv not in roles:
                errs.append(f"required_reviewers.{kind}: '{rv}' is not a declared role")
            elif status != "draft" and not roles[rv]["enabled"]:
                errs.append(f"required_reviewers.{kind}: '{rv}' is not enabled")
    hp = set(doc["review_gates"]["hard_preconditions"])
    for g in doc["review_gates"].get("external_gates", []):
        if g["id"] in hp:
            errs.append(f"external_gates: '{g['id']}' is a hard precondition; list it only in review_gates.hard_preconditions")
    wf = doc["issue_tracker"].get("write_fact") if isinstance(doc["issue_tracker"], dict) else None
    if wf in hp:
        errs.append(f"issue_tracker.write_fact: '{wf}' is a hard precondition; Linear writes need their own fact (DOD-05)")
    ra = doc["security"].get("reduced_assurance")
    if doc["security"]["runtime_class"] == "default" and not ra:
        errs.append("security.runtime_class 'default' requires security.reduced_assurance (R6 D16)")
    if ra:
        for e in doc["environments"]:
            if e["kind"] == "kubernetes_build":
                errs.append(f"reduced_assurance: build environment '{e['id']}' not allowed (builds disabled, R6 D16)")
        if ra["sandbox_repository"] == doc["source_repository"]["url"]:
            errs.append("reduced_assurance: sandbox_repository must not be the project's source repository")
    if "deps" in doc["network"]["classes_allowed"] and not doc["network"]["model_providers"] and status != "draft":
        errs.append("network: deps class without any model provider is not a valid agent configuration")

    if status in ("onboarding", "active", "paused", "archived"):
        for keys in SECURITY_CORE:
            node = get(doc, keys)
            for p, _ in find(node, is_unresolved, "/" + "/".join(keys)):
                errs.append(f"status {status}: security-core field {p} is unresolved")
        for name, r in roles.items():
            if r["enabled"] and is_unresolved(r["path_scopes"]):
                errs.append(f"status {status}: enabled role {name} has unresolved path_scopes")
        if not any(r["enabled"] for r in roles.values()):
            errs.append(f"status {status}: no role is enabled")
    if status == "active":
        for p, _ in find(doc, is_unresolved):
            errs.append(f"status active: {p} is unresolved")
        for s in [doc["identities"]["github_app"]] + doc["identities"]["secrets"]:
            if s["provisioning"] != "provisioned":
                errs.append(f"status active: secret '{s['name']}' is {s['provisioning']}")
        for k in ("ruleset", "codeowners"):
            v = doc["github_policy"][k]
            if isinstance(v, dict) and v.get("state") != "applied_verified":
                errs.append(f"status active: github_policy.{k} is {v.get('state')}")
        da = doc["documentation"].get("design_approval")
        if not (isinstance(da, dict) and da.get("state") == "approved"):
            errs.append("status active: documentation.design_approval must be 'approved'")
        kenv = {e["id"] for e in doc["environments"] if e["kind"].startswith("kubernetes")}
        for t in doc["test_levels"]:
            if t["environment"] in kenv:
                for c, v in t["commands"].items():
                    if isinstance(v, dict) and "planned" in v:
                        errs.append(f"status active: test level {t['id']} command {c} is only planned")
    return errs


def load_schema():
    with open(SCHEMA_PATH) as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def stem(path):
    return os.path.basename(path).split(".")[0]


def validate_files(paths, validator, quiet=False):
    bad, seen_ids, seen_ns = 0, {}, {}
    for p in paths:
        with open(p) as f:
            doc = yaml.safe_load(f)
        errs = check(doc, stem(p), validator)
        if isinstance(doc, dict) and not errs:
            pid, ns = doc["project_id"], doc["execution_target"]["namespace_prefix"]
            if pid in seen_ids:
                errs.append(f"project_id '{pid}' also in {seen_ids[pid]}")
            if ns in seen_ns:
                errs.append(f"namespace_prefix '{ns}' also in {seen_ns[ns]}")
            seen_ids[pid], seen_ns[ns] = p, p
        rel = os.path.relpath(p)
        if errs:
            bad += 1
            print(f"INVALID {rel}")
            for e in errs:
                print(f"  - {e}")
        elif not quiet:
            unresolved = list(find(doc, is_unresolved))
            planned = list(find(doc, lambda v: isinstance(v, dict) and "planned" in v))
            core = sum(1 for keys in SECURITY_CORE for _ in find(get(doc, keys), is_unresolved))
            deps_note = ""
            if "deps" in doc["network"]["classes_allowed"] and is_unresolved(doc["network"]["registries_allowlist"]):
                deps_note = "; deps egress effectively DENIED (registries_allowlist unresolved)"
            print(f"VALID   {rel}  project={doc['project_id']} status={doc['status']} "
                  f"unresolved={len(unresolved)} (security-core={core}) planned={len(planned)}{deps_note}")
    return bad


def self_test(validator):
    """Each mutation of the first valid non-draft config must be rejected; the unmutated one must pass."""
    base_path = next((p for p in sorted(glob.glob(DEFAULT_GLOB))
                      if yaml.safe_load(open(p)).get("status") in ("onboarding", "active")), None)
    if not base_path:
        print("self-test: no onboarding/active config found"); return 1
    base = yaml.safe_load(open(base_path))
    pid, st = base["project_id"], stem(base_path)
    U = {"unresolved": "self-test placeholder question"}

    def m(fn):
        d = copy.deepcopy(base); fn(d); return d

    first_role = next(n for n, r in base["agent_permissions"]["roles"].items() if r["writes"])
    first_ro = next(n for n, r in base["agent_permissions"]["roles"].items() if not r["writes"])
    restricted0 = base["security"]["restricted_paths"][0]
    _cat = catalogue()
    _gated = {k["kind"] for k in _cat["kind_catalogue"] if k.get("gate")}
    ungated = next(n for n in base["agent_permissions"]["roles"]
                   if n in {p["role"] for p in _cat["profiles"]}
                   and not _gated & set(next(p for p in _cat["profiles"] if p["role"] == n)["kinds"]))
    cases = [
        ("status active with unresolved values", "status active", m(lambda d: d.update(status="active"))),
        ("unresolved runtime_class at onboarding", "runtime_class", m(lambda d: d["security"].update(runtime_class=U))),
        ("unresolved restricted_paths at onboarding", "restricted_paths is unresolved", m(lambda d: d["security"].update(restricted_paths=U))),
        ("unresolved human approvers at onboarding", "human_approvers is unresolved", m(lambda d: d["review_gates"].update(human_approvers=U))),
        ("non-draft PR mode", "pr_mode", m(lambda d: d["github_policy"].update(pr_mode="ready"))),
        ("agent allowed to merge", "agent_may", m(lambda d: d["github_policy"].update(agent_may=["push_branch_prefix", "merge"]))),
        ("merge by agent", "merge_by", m(lambda d: d["github_policy"].update(merge_by="agent"))),
        ("G7 not required", "G7", m(lambda d: d["review_gates"]["gates"]["G7"].update(required=False))),
        ("approver rule changed", "human_approver_rule", m(lambda d: d["review_gates"].update(human_approver_rule="any_maintainer"))),
        ("image pinned by tag", "container_images", m(lambda d: d["container_images"][0].update(image="node:24"))),
        ("role scope inside restricted path", "falls inside restricted_paths", m(lambda d: d["agent_permissions"]["roles"][first_role]["path_scopes"].append(restricted0.rstrip("*") + "x/**" if restricted0.endswith("**") else restricted0))),
        ("read-only role with a path scope", "read-only role", m(lambda d: d["agent_permissions"]["roles"][first_ro].update(path_scopes=["src/**"]))),
        ("secret value in config", "GitHub token", m(lambda d: d["notes"].append("token ghp_" + "A" * 36))),
        ("private key in config", "PEM private key", m(lambda d: d["notes"].append("-----BEGIN RSA PRIVATE KEY-----"))),
        ("secret value field", "'value' was unexpected", m(lambda d: d["identities"]["secrets"].append({"name": "x-key", "purpose": "p", "holder": "devplat-gitbroker", "provisioning": "provisioned", "value": "hunter2"}))),
        ("secret mounted by an agent", "holder", m(lambda d: d["identities"]["secrets"].append({"name": "x-key", "purpose": "p", "holder": "agent-job", "provisioning": "provisioned"}))),
        ("wrong namespace prefix", "namespace_prefix must be", m(lambda d: d["execution_target"].update(namespace_prefix="proj-other"))),
        ("unknown test environment", "unknown environment", m(lambda d: d["test_levels"][0].update(environment="nowhere"))),
        ("automated production deployment", "deployment_targets", m(lambda d: d["deployment_targets"].append({"id": "prod", "purpose": "deployment_validation", "production": True, "automated": True, "approval": "x"}))),
        ("unknown top-level field", "bypass_review", m(lambda d: d.update(bypass_review=True))),
        ("wrong schema id", "/schema", m(lambda d: d.update(schema="devplat.project.v2"))),
        ("pod security relaxed", "pod_security", m(lambda d: d["security"].update(pod_security="baseline"))),
        ("extra egress", "extra_egress", m(lambda d: d["network"].update(extra_egress=["example.com"]))),
        # R6 fix round
        ("old bucket naming", "artifacts.bucket must be", m(lambda d: d["artifacts"].update(bucket=f"devplat-proj-{pid}"))),
        ("project id longer than 24", "/project_id", m(lambda d: d.update(project_id="p" * 25))),
        ("unknown network class", "classes_allowed", m(lambda d: d["network"].update(classes_allowed=["none", "integration"]))),
        ("unknown project status", "/status", m(lambda d: d.update(status="suspended"))),
        ("paused with unresolved security core", "status paused", m(lambda d: (d.update(status="paused"), d["review_gates"].update(human_approvers=U)))),
        ("hard preconditions without DOD-13", "hard_preconditions", m(lambda d: d["review_gates"].update(hard_preconditions=["DOD-02", "DOD-01"]))),
        ("hard preconditions missing", "hard_preconditions", m(lambda d: d["review_gates"].pop("hard_preconditions"))),
        ("hard precondition duplicated as external gate", "is a hard precondition", m(lambda d: d["review_gates"]["external_gates"].append({"id": "DOD-02", "satisfied_by": "operator_fact", "ref": "x"}))),
        # minor 2: per-project Linear write fact
        ("Linear writes without a write fact", "/issue_tracker", m(lambda d: d.update(issue_tracker={"kind": "linear", "team": "T", "project": "P", "write_mode": "comments"}))),
        ("write fact with read-only Linear", "/issue_tracker", m(lambda d: d.update(issue_tracker={"kind": "linear", "team": "T", "project": "P", "write_mode": "read_only", "write_fact": "LINEAR-WRITE"}))),
        ("write fact reuses a hard precondition", "Linear writes need their own fact", m(lambda d: d.update(issue_tracker={"kind": "linear", "team": "T", "project": "P", "write_mode": "comments", "write_fact": d["review_gates"]["hard_preconditions"][0]}))),
        ("role not in the catalogue", "not a role of the platform catalogue", m(lambda d: d["agent_permissions"]["roles"].update({"mdev-rogue": {"enabled": False, "writes": False, "path_scopes": []}}))),
        ("task kind not given by the catalogue", "is not given to this role", m(lambda d: d["agent_permissions"]["roles"][first_role].update(task_kinds=["security_review"]))),
        ("read-only catalogue role made writable", "all read-only", m(lambda d: d["agent_permissions"]["roles"][first_ro].update(writes=True, path_scopes=[]))),
        ("reviewer without a gated kind", "no review kind with a gate", m(lambda d: d["review_gates"]["required_reviewers"]["default"].append(ungated))),
        ("no sandbox runtime without reduced assurance", "requires security.reduced_assurance", m(lambda d: d["security"].update(runtime_class="default"))),
        ("reduced assurance with builds", "builds disabled", m(lambda d: (d["security"].update(runtime_class="default", reduced_assurance={"fact_key": "REDUCED-ASSURANCE", "sandbox_repository": "https://github.com/example/sandbox", "llm_key_secret": "devplat-llm-key-sandbox", "builds": "disabled"}), d["environments"].append({"id": "k8s-build", "kind": "kubernetes_build", "purpose": "self-test", "task_kinds": ["build"], "ref": "self-test"})))),
        ("reduced assurance on the real repository", "must not be the project's source repository", m(lambda d: (d["security"].update(runtime_class="default", reduced_assurance={"fact_key": "REDUCED-ASSURANCE", "sandbox_repository": d["source_repository"]["url"], "llm_key_secret": "devplat-llm-key-sandbox", "builds": "disabled"}), d.update(environments=[e for e in d["environments"] if e["kind"] != "kubernetes_build"])))),
        ("reduced assurance with builds enabled", "/security/reduced_assurance/builds", m(lambda d: d["security"].update(reduced_assurance={"fact_key": "REDUCED-ASSURANCE", "sandbox_repository": "https://github.com/example/sandbox", "llm_key_secret": "devplat-llm-key-sandbox", "builds": "enabled"}))),
    ]
    fails = 0
    ok = check(base, st, validator)
    print(f"self-test baseline {os.path.relpath(base_path)}: {'PASS (valid)' if not ok else 'FAIL ' + str(ok)}")
    fails += bool(ok)
    for name, expect, d in cases:
        errs = check(d, st, validator)
        hit = [e for e in errs if expect in e]
        if hit:
            verdict = "PASS (rejected for the expected reason)"
        elif errs:
            verdict = f"FAIL (rejected, but not for '{expect}')"
        else:
            verdict = "FAIL (accepted)"
        fails += not hit
        print(f"self-test {name}: {verdict}" + (f" — {(hit or errs)[0][:110]}" if errs else ""))
    # catalogue consistency (R6 D6): each mutation of the platform catalogue must be rejected
    cat0 = catalogue()
    prof = lambda c, r: next(p for p in c["profiles"] if p["role"] == r)
    def cm(fn):
        c = copy.deepcopy(cat0); fn(c); return c
    ccases = [
        ("profile kind missing from catalogue", "!= catalogue", cm(lambda c: prof(c, first_role)["kinds"].append("security_review"))),
        ("catalogue executor without profile", "has no execution profile", cm(lambda c: c["kind_catalogue"][0]["executors"].append("mdev-ghost"))),
        ("writable profile with only read-only kinds", "writes_allowed is true", cm(lambda c: prof(c, first_ro).update(writes_allowed=True))),
        ("review kind not read-only", "must be read_only", cm(lambda c: next(k for k in c["kind_catalogue"] if k.get("gate")).update(read_only=False))),
        ("non-Job kind with a Job role", "not a non-Job actor", cm(lambda c: next(k for k in c["kind_catalogue"] if not k["job"])["executors"].append(first_role))),
    ]
    base_cat_errs = catalogue_errors(cat0)
    print(f"self-test catalogue baseline: {'PASS (valid)' if not base_cat_errs else 'FAIL ' + str(base_cat_errs)}")
    fails += bool(base_cat_errs)
    for name, expect, c in ccases:
        errs = catalogue_errors(c)
        hit = [e for e in errs if expect in e]
        fails += not hit
        print(f"self-test {name}: {'PASS (rejected for the expected reason)' if hit else 'FAIL ' + str(errs[:1])}")
    total = len(cases) + 1 + len(ccases) + 1
    print(f"self-test: {total - fails}/{total} passed")
    return 1 if fails else 0


def main(argv):
    try:
        validator = load_schema()
    except Exception as e:
        print(f"ERROR: schema {SCHEMA_PATH}: {e}", file=sys.stderr); return 2
    if argv[:1] == ["--self-test"]:
        return self_test(validator)
    paths = argv or sorted(glob.glob(DEFAULT_GLOB))
    if not paths:
        print("ERROR: no project files", file=sys.stderr); return 2
    print(f"schema {os.path.relpath(SCHEMA_PATH)} (Draft 2020-12, metaschema OK); jsonschema {jsonschema_version()}")
    bad = validate_files(paths, validator)
    print(f"{len(paths) - bad}/{len(paths)} valid")
    return 1 if bad else 0


def jsonschema_version():
    try:
        from importlib.metadata import version
        return version("jsonschema")
    except Exception:
        return "unknown"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
