#!/usr/bin/env python3
"""Validate Kubernetes manifests against the strict JSON schemas of one Kubernetes API version.

No cluster, kubectl or kubeconform is needed. The standalone-strict schemas published by
github.com/yannh/kubernetes-json-schema (generated from the upstream OpenAPI spec) are fetched once, at
a pinned commit, into a local cache and treated as data. Strict = unknown fields are errors.

    python3 platform/tools/validate_k8s.py [--k8s v1.33.0] [--allow-unknown-kinds] FILE_OR_DIR...
    python3 platform/tools/validate_k8s.py [--k8s v1.33.0] --print-cache-dir

Exit 0 only if every document validates. A kind without an upstream schema (HTTP 404, e.g. a custom resource
such as the CloudNativePG `Cluster`) is reported as SKIPPED and fails the run unless --allow-unknown-kinds is
given; any other fetch error (network, rate limit, 5xx) fails the run (R6 CI review CI-2). Helm templates
(`templates/`) are skipped: they must be rendered first (`helm template`; platform/tools/charts/run.sh).
"""
import json, os, sys, urllib.error, urllib.request

import yaml
from jsonschema import Draft7Validator

# Pinned commit of yannh/kubernetes-json-schema (2026-10-25; the 15 schemas the package uses are byte-identical to
# the earlier `master` fetches). Changing it is a reviewed change; the cache directory is keyed by it.
SCHEMA_COMMIT = "f7d855e49c34b039c9ef2196444910275e31e09e"
BASE = "https://raw.githubusercontent.com/yannh/kubernetes-json-schema/" + SCHEMA_COMMIT + "/{ver}-standalone-strict/{name}.json"
CACHE = os.environ.get("K8S_SCHEMA_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "devplat-k8s-schemas"))


def cache_dir(ver):
    return os.path.join(CACHE, f"{ver}@{SCHEMA_COMMIT[:12]}")


def schema_name(api_version, kind):
    group, _, version = api_version.rpartition("/")
    group = group.split(".")[0] if group else ""
    return f"{kind.lower()}-{group + '-' if group else ''}{version}"


def load_schema(ver, name):
    path = os.path.join(cache_dir(ver), name + ".json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with urllib.request.urlopen(BASE.format(ver=ver, name=name), timeout=30) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:          # no upstream schema (custom resource); any other error is fatal
                return None, str(e)
            raise
        tmp = path + ".part"
        open(tmp, "wb").write(data)
        os.replace(tmp, path)
    with open(path) as f:
        return json.load(f), None


def files(args):
    for a in args:
        if os.path.isdir(a):
            for root, dirs, fs in os.walk(a):
                dirs[:] = [d for d in dirs if d != "templates"]
                for f in sorted(fs):
                    if f.endswith((".yaml", ".yml")) and f not in ("Chart.yaml", "values.yaml"):
                        yield os.path.join(root, f)
        else:
            yield a


def main(argv):
    ver, allow_unknown = "v1.33.0", False
    if argv[:1] == ["--k8s"]:
        ver, argv = argv[1], argv[2:]
    if argv == ["--print-cache-dir"]:
        print(cache_dir(ver)); return 0
    if argv[:1] == ["--allow-unknown-kinds"]:
        allow_unknown, argv = True, argv[1:]
    bad = ok = skipped = 0
    for f in files(argv):
        for i, doc in enumerate(yaml.safe_load_all(open(f))):
            if not doc:
                continue
            kind, av = doc.get("kind"), doc.get("apiVersion")
            label = f"{f}#{i} {kind} {doc.get('metadata', {}).get('name')}"
            if not kind or not av:
                print(f"INVALID {label}: missing kind/apiVersion"); bad += 1; continue
            sch, err = load_schema(ver, schema_name(av, kind))
            if sch is None:
                print(f"SKIPPED {label}: no upstream schema for {av}/{kind} (custom resource?)"); skipped += 1; continue
            errs = sorted(Draft7Validator(sch).iter_errors(doc), key=lambda e: list(e.path))
            if errs:
                bad += 1
                for e in errs[:5]:
                    print(f"INVALID {label}: {'/'.join(map(str, e.path))}: {e.message[:200]}")
            else:
                ok += 1
    print(f"k8s {ver}: {ok} valid, {bad} invalid, {skipped} skipped (custom resources)")
    return 1 if bad or (skipped and not allow_unknown) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
