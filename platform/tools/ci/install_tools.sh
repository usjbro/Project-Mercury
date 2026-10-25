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
# Enforce what the header promises, whatever the caller's environment says (R6 CI review CI-7).
export GOTOOLCHAIN=local GOFLAGS=-trimpath GOPROXY=https://proxy.golang.org GOSUMDB=sum.golang.org \
       GONOSUMDB='' GONOSUMCHECK='' GOPRIVATE='' GOINSECURE='' GONOPROXY=''
case "$(go env GOVERSION)" in go1.24.*) ;; *) echo "install_tools.sh: need Go 1.24.x, have $(go env GOVERSION)" >&2; exit 2;; esac
GOBIN=$(cd "$BINDIR" && pwd); export GOBIN
for t in "$@"; do
  [ -n "${MOD[$t]:-}" ] || { echo "unknown tool $t" >&2; exit 2; }
  go install "${MOD[$t]}"
  echo "$t ${MOD[$t]##*@} -> $GOBIN/$t"
done
