#!/usr/bin/env bash
# Offline chart checks (doc 24 section 10). Needs python3 + PyYAML + jsonschema, HELM and KUBECONFORM binaries,
# network access for the Kubernetes/CRD JSON schemas, and optionally GO (>= 1.24) for the CEL checks.
#   HELM=/path/helm KUBECONFORM=/path/kubeconform GO=/path/go platform/tools/charts/run.sh
# helm v3.17.3 and kubeconform v0.6.7 can be built from source:
#   GOBIN=$PWD/bin go install helm.sh/helm/v3/cmd/helm@v3.17.3
#   GOBIN=$PWD/bin go install github.com/yannh/kubeconform/cmd/kubeconform@v0.6.7
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
: "${HELM:?set HELM}" "${KUBECONFORM:?set KUBECONFORM}"
"$HELM" version --short 2>/dev/null | sed 's/^/helm /'; "$KUBECONFORM" -v 2>/dev/null | sed 's/^/kubeconform /'
exec python3 "$HERE/check_charts.py" "$@"
