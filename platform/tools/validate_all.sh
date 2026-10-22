#!/usr/bin/env bash
# Run every offline check of the devplat package. Optional tools are used when given:
#   GO=/path/to/go (admission CEL checks), HELM=/path/to/helm and KUBECONFORM=/path/to/kubeconform (charts),
#   PG_BINDIR (PostgreSQL 16 server binaries for platform/db tests; default /usr/lib/postgresql/16/bin).
# Nothing here touches a cluster, GitHub or Linear.
set -uo pipefail
# --strict: a skipped optional check counts as a failure (use for release evidence).
ROOT=$(cd "$(dirname "$0")/../.." && pwd); cd "$ROOT"; FAIL=0; SKIPPED=0; STRICT=0
[ "${1:-}" = "--strict" ] && STRICT=1
skip() { echo "== $1 SKIPPED ($2)"; SKIPPED=$((SKIPPED+1)); }
run() { echo "== $1"; shift; if "$@"; then echo "   PASS"; else echo "   FAIL"; FAIL=1; fi; }
run "devorch v1 regression tests"          python3 tools/devorch/test_devorch.py
run "devorch examples drift check"         python3 tools/devorch/gen_examples.py --check
run "job spec generator (== doc 16, strict v1.33)" python3 platform/controller/test_jobspec.py
run "project configs (schema + rules)"     python3 platform/tools/validate_projects.py
run "project config validator self-test"   python3 platform/tools/validate_projects.py --self-test
run "execution profiles schema"            python3 -c "import json,yaml,jsonschema;jsonschema.Draft202012Validator(json.load(open('platform/schemas/execution-profiles.schema.json'))).validate(yaml.safe_load(open('platform/agents/execution-profiles.yaml')))"
run "task contract v2 example"             python3 -c "import json,jsonschema;jsonschema.Draft202012Validator(json.load(open('platform/schemas/task-contract.v2.schema.json'))).validate(json.load(open('platform/schemas/example-contract-v2.json')))"
run "base manifests (strict v1.33)"        python3 platform/tools/validate_k8s.py platform/deploy/base
run "role ConfigMap generator output"      bash -c 'python3 platform/tools/gen_role_configmap.py --project mercury --namespace proj-mercury-exec --commit HEAD > /tmp/devplat-roles.yaml && python3 platform/tools/validate_k8s.py /tmp/devplat-roles.yaml'
run "PostgreSQL state schema (real PG16)"  python3 platform/db/test_schema.py
if [ -n "${GO:-}" ]; then run "admission policies (CEL compile + behavioural cases)" bash -c "GO=$GO platform/tools/admission/run.sh | tail -2 | grep -q '0 mismatches'"; else skip "admission CEL checks" "set GO"; fi
if [ -n "${HELM:-}" ] && [ -n "${KUBECONFORM:-}" ]; then
  D=$(printf 'sha256:%064d' 0)   # test-only digest: no real image exists yet
  SET=controller.image.digest=$D,api.image.digest=$D,gitbroker.image.digest=$D,gitbrokerFetch.image.digest=$D,modelGateway.image.digest=$D,dns.image.digest=$D
  KC="'$KUBECONFORM' -strict -summary -kubernetes-version 1.33.0 -schema-location default -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'"
  # a check passes only if helm rendered something AND kubeconform reports no invalid/error AND >0 valid
  chk() { out=$(bash -o pipefail -c "$1 | $KC" 2>&1) || { echo "$out" | tail -3; return 1; }
          echo "$out" | tail -1; echo "$out" | grep -Eq 'Valid: [1-9][0-9]*, Invalid: 0, Errors: 0'; }
  run "helm lint devplat"            "$HELM" lint platform/deploy/charts/devplat -n devplat-system --kube-version 1.33.0 --set "$SET"
  run "helm lint devplat-project"    "$HELM" lint platform/deploy/charts/devplat-project --kube-version 1.33.0
  run "devplat render | kubeconform strict"         chk "'$HELM' template t platform/deploy/charts/devplat -n devplat-system --kube-version 1.33.0 --set $SET"
  run "devplat-project render | kubeconform strict" chk "'$HELM' template m platform/deploy/charts/devplat-project --kube-version 1.33.0"
  run "devplat refuses to render without image digests" bash -c "! '$HELM' template t platform/deploy/charts/devplat -n devplat-system --kube-version 1.33.0 >/dev/null 2>&1"
else skip "chart lint/render" "set HELM and KUBECONFORM"; fi
echo
if [ $FAIL != 0 ]; then echo "SOME CHECKS FAILED"; exit 1; fi
if [ $SKIPPED != 0 ]; then
  echo "REQUIRED CHECKS PASSED; $SKIPPED OPTIONAL CHECK GROUP(S) SKIPPED — not a complete validation"
  [ $STRICT = 1 ] && exit 2; exit 0
fi
echo "ALL CHECKS PASSED (nothing skipped)"
