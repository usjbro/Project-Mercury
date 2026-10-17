#!/usr/bin/env python3
"""Generate the immutable role ConfigMap for one project (16-agent-execution-and-job-lifecycle.md §9.1).

    python3 platform/tools/gen_role_configmap.py --project mercury --namespace proj-mercury-exec [--commit SHA] > roles.yaml

Reads `.claude/agents/mdev-*.md` (the repository files are never edited) and
`platform/agents/execution-profiles.yaml`, and emits a ConfigMap `devplat-roles-<project>-<hash8>`:
  * key `<file>.md`: the definition, byte-identical except one recorded transform: the guard-hook path
    `$CLAUDE_PROJECT_DIR/tools/devorch/hooks/specialist_guard.py` becomes `/opt/devplat/hooks/specialist_guard.py`
    (baked into the image; the workspace copy would be agent-writable);
  * key `managed-settings.<role>.json`: the deny rules of `.claude/settings.json`, plus allow rules for the role's
    frontmatter `tools` (headless runs cannot answer permission prompts), plus the profile's
    `extra_disallowed_tools`. The Job mounts it as `/etc/claude-code/managed-settings.json`;
  * annotations: source commit and per-file sha256 before and after the transform.
hash8 = first 8 hex of sha256 over the sorted keys and values, so any content change yields a new name and a running
Job never sees its role definition change (immutable: true).
"""
import argparse, hashlib, json, os, subprocess, sys

import yaml

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
HOOK_FROM = '$CLAUDE_PROJECT_DIR/tools/devorch/hooks/specialist_guard.py'
HOOK_TO = '/opt/devplat/hooks/specialist_guard.py'


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def frontmatter(text):
    return yaml.safe_load(text.split("---")[1])


def read_at(commit, rel):
    """Read a repository file at the pinned commit (provenance must match the annotation; R6 F28)."""
    r = subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=ROOT, capture_output=True)
    if r.returncode != 0:
        raise SystemExit(f"cannot read {rel} at {commit}: {r.stderr.decode().strip()}")
    return r.stdout.decode("utf-8")


def build(project, namespace, commit):
    profiles = yaml.safe_load(read_at(commit, "platform/agents/execution-profiles.yaml"))["profiles"]
    deny = json.loads(read_at(commit, ".claude/settings.json"))["permissions"]["deny"]
    data, ann = {}, {"devplat.io/source-commit": commit}
    for p in profiles:
        path = p["agent_definition"]
        raw = read_at(commit, path)
        out = raw.replace(HOOK_FROM, HOOK_TO)
        key = os.path.basename(path)
        data[key] = out
        ann[f"devplat.io/sha256-src.{key}"] = sha(raw)
        ann[f"devplat.io/sha256-out.{key}"] = sha(out)
        fm = frontmatter(raw)
        tools = [t.strip() for t in str(fm.get("tools", "")).split(",") if t.strip() and not t.strip().startswith("Agent")]
        extra = list(p.get("extra_disallowed_tools", []))
        data[f"managed-settings.{p['role']}.json"] = json.dumps(
            {"permissions": {"allow": sorted(set(tools) - set(extra)), "deny": deny + sorted(extra)}},
            indent=2, sort_keys=True) + "\n"
    digest = sha("".join(f"{k}\0{data[k]}\0" for k in sorted(data)))[:8]
    return {"apiVersion": "v1", "kind": "ConfigMap", "immutable": True,
            "metadata": {"name": f"devplat-roles-{project}-{digest}", "namespace": namespace,
                         "labels": {"app.kubernetes.io/managed-by": "devplat-controller", "devplat.io/project": project,
                                    "devplat.io/component": "roles"},
                         "annotations": ann},
            "data": data}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--commit")
    a = ap.parse_args()
    commit = subprocess.run(["git", "rev-parse", a.commit or "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    yaml.safe_dump(build(a.project, a.namespace, commit), sys.stdout, sort_keys=False, width=1000)


if __name__ == "__main__":
    main()
