#!/usr/bin/env bash
# Build the pinned CI tools from source into BINDIR (devplat-ci.yml; 23-ci-cd-integration.md §5.2).
#   platform/tools/ci/install_tools.sh BINDIR helm kubeconform actionlint
# Sources come through the Go module proxy; every module is verified against sum.golang.org (GONOSUMDB and
# GOFLAGS=-insecure are never set), so a version pins content, not just a tag. Needs Go 1.24 (GOTOOLCHAIN=local:
# no other toolchain is downloaded).
set -euo pipefail
BINDIR=${1:?usage: install_tools.sh BINDIR tool...}; shift
declare -A MOD=(
  [helm]=helm.sh/helm/v3/cmd/helm@v3.17.3
  [kubeconform]=github.com/yannh/kubeconform/cmd/kubeconform@v0.6.7
  [actionlint]=github.com/rhysd/actionlint/cmd/actionlint@v1.7.11
)
mkdir -p "$BINDIR"
export GOBIN BINDIR GOTOOLCHAIN=local GOFLAGS=-trimpath
GOBIN=$(cd "$BINDIR" && pwd)
for t in "$@"; do
  [ -n "${MOD[$t]:-}" ] || { echo "unknown tool $t" >&2; exit 2; }
  go install "${MOD[$t]}"
  echo "$t ${MOD[$t]##*@} -> $GOBIN/$t"
done
