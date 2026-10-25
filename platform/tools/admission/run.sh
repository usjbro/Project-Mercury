#!/usr/bin/env bash
# Offline validation of platform/deploy/base: strict v1.33 schemas, cross-references and invariants,
# CEL compilation of every ValidatingAdmissionPolicy expression (Kubernetes v0.33 CEL environment),
# and behavioural evaluation of the policies against sample admission requests (cases.py).
# Needs: python3 + jsonschema + PyYAML, Go >= 1.24 (GO=/path/to/go), network for Go modules and schemas.
# Limits: objects are untyped JSON without API defaulting; a real apiserver is still required (29-… AT-16).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$(cd "$HERE/../../.." && pwd)
GO=${GO:-go}; OUT=${OUT:-$(mktemp -d)}; VER=v1.33.0
SCHEMAS=$(python3 "$ROOT/platform/tools/validate_k8s.py" --k8s $VER --print-cache-dir)   # keyed by the pinned commit
python3 "$ROOT/platform/tools/validate_k8s.py" --k8s $VER "$ROOT/platform/deploy/base"   # also fills the schema cache
python3 "$HERE/extract_policies.py" "$ROOT/platform/deploy/base" "$SCHEMAS" "$OUT"
(cd "$HERE" && "$GO" build -o "$OUT/celcheck" .)
"$OUT/celcheck" "$OUT/cel-items.json"
python3 "$HERE/cases.py" "$OUT/pol-data.json" "$OUT/suite.json"
"$OUT/celcheck" eval "$OUT/suite.json" | tail -3
echo "outputs in $OUT"
