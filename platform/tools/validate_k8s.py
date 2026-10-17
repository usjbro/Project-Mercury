#!/usr/bin/env python3
"""Validate Kubernetes manifests against the strict JSON schemas of one Kubernetes API version.

No cluster, kubectl or kubeconform is needed. The standalone-strict schemas published by
github.com/yannh/kubernetes-json-schema (generated from the upstream OpenAPI spec) are fetched once
into a local cache and treated as data. Strict = unknown fields are errors.

    python3 platform/tools/validate_k8s.py [--k8s v1.33.0] FILE_OR_DIR...

Exit 0 only if every document validates. Custom resources (kinds without an upstream schema, e.g. the
CloudNativePG `Cluster`) are reported as SKIPPED, never as valid. Helm templates (`templates/`) are skipped:
they must be rendered first (`helm template`, not available in the authoring environment).
"""
import json, os, sys, urllib.request

import yaml
from jsonschema import Draft7Validator

BASE = "https://raw.githubusercontent.com/yannh/kubernetes-json-schema/master/{ver}-standalone-strict/{name}.json"
CACHE = os.environ.get("K8S_SCHEMA_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "devplat-k8s-schemas"))


def schema_name(api_version, kind):
    group, _, version = api_version.rpartition("/")
    group = group.split(".")[0] if group else ""
    return f"{kind.lower()}-{group + '-' if group else ''}{version}"


def load_schema(ver, name):
    path = os.path.join(CACHE, ver, name + ".json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with urllib.request.urlopen(BASE.format(ver=ver, name=name), timeout=30) as r:
                data = r.read()
        except Exception as e:  # 404 = no upstream schema (custom resource)
            return None, str(e)
        open(path, "wb").write(data)
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
    ver = "v1.33.0"
    if argv[:1] == ["--k8s"]:
        ver, argv = argv[1], argv[2:]
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
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
