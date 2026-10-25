# Base manifest generators

`networkpolicies.yaml` and `quotas.yaml` in `platform/deploy/base/` are generated. Edit the generator, never the output.

    python3 platform/tools/base/gen_netpol.py platform/deploy/base/networkpolicies.yaml
    python3 platform/tools/base/gen_quotas.py platform/deploy/base/quotas.yaml

`validate_all.sh` regenerates both into a temporary file and fails if the result differs from the committed manifests.
