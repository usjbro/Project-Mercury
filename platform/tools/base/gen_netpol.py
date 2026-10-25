# Generates platform/deploy/base/networkpolicies.yaml (deterministic). Kept in scratchpad; output is the artifact.
import yaml, sys
PUBLIC = [{"ipBlock": {"cidr": "0.0.0.0/0", "except": ["10.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16"]}},
          {"ipBlock": {"cidr": "::/0", "except": ["fc00::/7", "fe80::/10"]}}]
APISERVER = [{"ipBlock": {"cidr": "192.0.2.10/32"}}]  # PLACEHOLDER (TEST-NET-1): overlay sets the real endpoint IPs
DNS_TO = [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
           "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}}}]
def tcp(*ps): return [{"protocol": "TCP", "port": p} for p in ps]
def app(n): return {"matchLabels": {"app.kubernetes.io/name": n}}
def ns(n): return {"matchLabels": {"kubernetes.io/metadata.name": n}}
PG = {"matchLabels": {"cnpg.io/cluster": "devplat-pg"}}  # S-22: CNPG Cluster name in charts/devplat is devplat-pg
EXT_PG = [{"ipBlock": {"cidr": "203.0.113.10/32"}}]  # PLACEHOLDER (TEST-NET-3): managed PostgreSQL endpoint, external-PG profiles only
ARTIFACTS = [{"namespaceSelector": ns("devplat-artifacts"), "podSelector": app("devplat-artifacts")}]
# Default artifact store = EXTERNAL S3-compatible endpoint (MinIO community edition reported archived; doc 22 / ADR-027).
# PLACEHOLDER 198.51.100.10/32 (TEST-NET-2): overlay sets the endpoint's IPs (or a VPC endpoint / egress gateway).
S3_EXT = [{"ipBlock": {"cidr": "198.51.100.10/32"}}]
ART = [{"to": ARTIFACTS, "ports": [{"protocol": "TCP", "port": 9000}]}, {"to": S3_EXT, "ports": [{"protocol": "TCP", "port": 443}]}]
PROM = [{"namespaceSelector": ns("devplat-observability"), "podSelector": app("devplat-prometheus")}]
docs = []
def np(name, namespace, pod_selector, types, ingress=None, egress=None, comment=None):
    d = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
         "metadata": {"name": name, "namespace": namespace},
         "spec": {"podSelector": pod_selector, "policyTypes": types}}
    if comment: d["metadata"]["annotations"] = {"devplat.io/purpose": comment}
    if ingress is not None: d["spec"]["ingress"] = ingress
    if egress is not None: d["spec"]["egress"] = egress
    docs.append(d)
def default_deny(n):
    np("default-deny-all", n, {}, ["Ingress", "Egress"], comment="Deny all ingress and egress; every flow below is an explicit exception.")
def kube_dns(n):
    np("allow-kube-dns-egress", n, {}, ["Egress"], egress=[{"to": DNS_TO, "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}],
       comment="Platform namespaces only. Project namespaces never reach kube-dns (it forwards to the internet).")
def metrics(n):
    np("allow-metrics-scrape", n, {}, ["Ingress"], ingress=[{"from": PROM, "ports": tcp(9090)}])
def role_ns(*roles):
    return {"matchExpressions": [{"key": "devplat.io/ns-role", "operator": "In", "values": list(roles)}]}
def wl(*w):
    return {"matchExpressions": [{"key": "devplat.io/workload", "operator": "In", "values": list(w)}]}
def nc(*c):
    return {"matchExpressions": [{"key": "devplat.io/network-class", "operator": "In", "values": list(c)}]}
S = "devplat-system"
def sys_peer(name): return {"namespaceSelector": ns(S), "podSelector": app(name)}
DEVPLAT_DNS = [{"to": [sys_peer("devplat-dns")], "ports": [{"protocol": "UDP", "port": 1053}, {"protocol": "TCP", "port": 1053}]}]

default_deny(S); kube_dns(S); metrics(S)
PROJECTS = ["mercury", "jupiter"]
DB_CLIENTS = ["devplat-controller", "devplat-api", "devplat-model-gateway", "devplat-migrator"]
np("controller", S, app("devplat-controller"), ["Egress"], egress=[
    {"to": [{"podSelector": PG}], "ports": tcp(5432)},
    {"to": [{"podSelector": app("devplat-gitbroker")}], "ports": tcp(8080)},
    {"to": [{"podSelector": app("devplat-model-gateway")}], "ports": tcp(9443)},
    {"to": [{"podSelector": app("devplat-namespacer")}], "ports": tcp(8083)},
    {"to": [{"podSelector": app("devplat-artifact-gateway")}], "ports": tcp(9444)},
    *ART,
    {"to": APISERVER, "ports": tcp(443, 6443)}],
    comment="Controller: DB, gitbroker internal API, model-gateway admin (budgets, Job tokens), namespacer API, artifact-gateway admin (Job upload tokens), object store, kube-apiserver. No internet.")
np("migrator", S, app("devplat-migrator"), ["Egress"], egress=[{"to": [{"podSelector": PG}], "ports": tcp(5432)}],
   comment="D9 migration hook Job: PostgreSQL only.")
np("external-postgres", S, {"matchExpressions": [{"key": "app.kubernetes.io/name", "operator": "In", "values": DB_CLIENTS}]}, ["Egress"],
   egress=[{"to": EXT_PG, "ports": tcp(5432)}],
   comment="OPTION for profiles with managed PostgreSQL (S-22): DB clients to the external endpoint. Overlay sets the CIDR, or deletes this policy when PostgreSQL runs in-cluster.")
np("namespacer", S, app("devplat-namespacer"), ["Ingress", "Egress"],
   ingress=[{"from": [{"podSelector": app("devplat-controller")}], "ports": tcp(8083)}],
   egress=[{"to": APISERVER, "ports": tcp(443, 6443)}],
   comment="D19 namespacer: called only by the controller with (project, runid, profile ref); writes only to the kube-apiserver.")
np("api", S, app("devplat-api"), ["Ingress", "Egress"],
   ingress=[{"from": [{"namespaceSelector": {"matchLabels": {"devplat.io/ingress-gateway": "true"}}}], "ports": tcp(8080)}],
   egress=[{"to": [{"podSelector": PG}], "ports": tcp(5432)},
           *ART,
           {"to": PUBLIC, "ports": tcp(443)}],
   comment="API/dashboard: operator traffic from the ingress gateway namespace; DB; evidence reads; public 443 for OIDC issuer and Linear (host allowlist enforced in-app).")
np("gitbroker", S, app("devplat-gitbroker"), ["Ingress", "Egress"],
   ingress=[{"from": [{"podSelector": app("devplat-controller")}], "ports": tcp(8080)}],
   egress=[*ART,
           {"to": PUBLIC, "ports": tcp(443)},
           {"to": APISERVER, "ports": tcp(443, 6443)}],
   comment="Git broker (GitHub App key): called only by the controller, never by project pods; the caller's audience-bound projected token is verified against the issuer JWKS from the kube-apiserver (S-23), not by network position; GitHub over public 443 (host allowlist in-app).")
np("gitbroker-fetch", S, app("devplat-gitbroker-fetch"), ["Ingress", "Egress"],
   ingress=[{"from": [{"namespaceSelector": role_ns("exec", "test"), "podSelector": wl("agent", "planner", "verifier", "test")}], "ports": tcp(8081)}],
   egress=[*ART],
   comment="One-time bundle endpoint without any GitHub credential: project pods' fetch init containers; reads prepared bundles src/<project>/<sha>.bundle from the object store.")
np("artifact-gateway", S, app("devplat-artifact-gateway"), ["Ingress", "Egress"],
   ingress=[{"from": [{"namespaceSelector": role_ns("exec", "build", "test")}], "ports": tcp(8082)},
            {"from": [{"podSelector": app("devplat-controller")}], "ports": tcp(9444)}],
   egress=[*ART],
   comment="D10 artifact gateway: the ONLY artifact path of agent/build/test pods (per-Job one-time token, size caps per D11); writes runs/<job-uid>/ with its own S3 credential. Controller mints/revokes tokens on 9444.")
np("model-gateway", S, app("devplat-model-gateway"), ["Ingress", "Egress"],
   ingress=[{"from": [{"namespaceSelector": role_ns("exec"), "podSelector": {"matchExpressions": wl("agent", "planner", "verifier")["matchExpressions"] + nc("model-only", "deps")["matchExpressions"]}}],
             "ports": tcp(8080)},
            {"from": [{"podSelector": app("devplat-controller")}], "ports": tcp(9443)}],
   egress=[{"to": PUBLIC, "ports": tcp(443)}, {"to": [{"podSelector": PG}], "ports": tcp(5432)}],
   comment="Model gateway (LLM keys): exec pods of network class model-only/deps; endpoint allowlist and server-tool rejection (D12); project bound to the per-Job token; providers over public 443; budget rows in PostgreSQL.")
for pr in PROJECTS:
    np(f"registry-proxy-{pr}", S, app(f"devplat-registry-proxy-{pr}"), ["Ingress", "Egress"],
       ingress=[{"from": [{"namespaceSelector": {"matchExpressions": role_ns("exec", "test")["matchExpressions"] + [{"key": "devplat.io/project", "operator": "In", "values": [pr]}]}, "podSelector": nc("deps")},
                          {"namespaceSelector": {"matchExpressions": role_ns("build")["matchExpressions"] + [{"key": "devplat.io/project", "operator": "In", "values": [pr]}]}, "podSelector": wl("build")}],
                 "ports": tcp(4873, 5000)}],
       egress=[{"to": PUBLIC, "ports": tcp(443)}],
       comment=f"D14 read-only proxy of project {pr} only (packages 4873, OCI pull-through 5000; publish/adduser disabled; upstreams = the project's registries_allowlist).")
np("devplat-dns", S, app("devplat-dns"), ["Ingress", "Egress"],
   ingress=[{"from": [{"namespaceSelector": role_ns("exec", "build", "test")}], "ports": [{"protocol": "UDP", "port": 1053}, {"protocol": "TCP", "port": 1053}]}],
   egress=[{"to": APISERVER, "ports": tcp(443, 6443)}],
   comment="Cluster-local resolver for project pods (CoreDNS kubernetes plugin only, no forward; listens on 1053, Service port 53). No internet egress, so DNS cannot tunnel data out.")
np("postgres", S, PG, ["Ingress", "Egress"],
   ingress=[{"from": [{"podSelector": app(n)} for n in DB_CLIENTS], "ports": tcp(5432)},
            {"from": [{"podSelector": PG}], "ports": tcp(5432, 8000)},
            {"from": [{"namespaceSelector": ns("cnpg-system")}], "ports": tcp(8000)}],
   egress=[{"to": [{"podSelector": PG}], "ports": tcp(5432, 8000)},
           *ART,
           {"to": APISERVER, "ports": tcp(443, 6443)}],
   comment="PostgreSQL (CloudNativePG Cluster devplat-pg): controller, api, model-gateway (budget role) and migrator; replication; operator status port; backups to the object store; instance manager to kube-apiserver.")

A = "devplat-artifacts"
default_deny(A); kube_dns(A); metrics(A)
np("artifact-store", A, app("devplat-artifacts"), ["Ingress"], ingress=[
    {"from": [{"namespaceSelector": ns(S), "podSelector": {"matchExpressions": [{"key": "app.kubernetes.io/name", "operator": "In",
              "values": ["devplat-controller", "devplat-api", "devplat-gitbroker", "devplat-gitbroker-fetch", "devplat-artifact-gateway"]}]}},
              {"namespaceSelector": ns(S), "podSelector": PG}],
     "ports": tcp(9000)}],
   comment="OPTIONAL in-cluster S3-compatible store (default is external S3): platform components only. Project pods never reach the object store (D10).")

O = "devplat-observability"
default_deny(O); kube_dns(O)
np("prometheus", O, app("devplat-prometheus"), ["Ingress", "Egress"],
   ingress=[{"from": [{"podSelector": app("devplat-grafana")}], "ports": tcp(9090)}],
   egress=[{"to": [{"namespaceSelector": ns(S)}, {"namespaceSelector": ns(A)}], "ports": tcp(9090)},
           {"to": APISERVER, "ports": tcp(443, 6443)}],
   comment="Prometheus scrapes platform metrics ports only; never project namespaces.")
np("grafana", O, app("devplat-grafana"), ["Ingress", "Egress"],
   ingress=[{"from": [{"namespaceSelector": {"matchLabels": {"devplat.io/ingress-gateway": "true"}}}], "ports": tcp(3000)}],
   egress=[{"to": [{"podSelector": app("devplat-prometheus")}], "ports": tcp(9090)}])

AGW = [{"to": [sys_peer("devplat-artifact-gateway")], "ports": tcp(8082)}]
for p in PROJECTS:
    E = f"proj-{p}-exec"; B = f"proj-{p}-build"
    default_deny(E)
    np("exec-base-egress", E, wl("agent", "planner", "verifier"), ["Egress"],
       egress=DEVPLAT_DNS + [{"to": [sys_peer("devplat-gitbroker-fetch")], "ports": tcp(8081)}] + AGW,
       comment="Every exec Job (class none and up): cluster-local DNS, one-time bundle fetch, artifact gateway (D10). No object store, internet, GitHub, Linear, kube-apiserver, DB or other project.")
    np("model-egress", E, {"matchExpressions": wl("agent", "planner", "verifier")["matchExpressions"] + nc("model-only", "deps")["matchExpressions"]}, ["Egress"],
       egress=[{"to": [sys_peer("devplat-model-gateway")], "ports": tcp(8080)}],
       comment="Network class model-only or deps: model gateway (per-Job token).")
    np("deps-egress", E, nc("deps"), ["Egress"],
       egress=[{"to": [sys_peer(f"devplat-registry-proxy-{p}")], "ports": tcp(4873)}],
       comment=f"Network class deps: this project's read-only package proxy only (D14).")
    default_deny(B)
    np("build-egress", B, wl("build"), ["Egress"],
       egress=DEVPLAT_DNS + [{"to": [sys_peer(f"devplat-registry-proxy-{p}")], "ports": tcp(4873, 5000)}] + AGW,
       comment="Build Jobs (disabled by default, D20): this project's proxy/mirror; outputs via the artifact gateway. No object store, internet, push credentials or model gateway.")

hdr = """# devplat base: NetworkPolicies (networking.k8s.io/v1). Status: Documented only / not deployed.
# Flows table: docs/mercury/development-orchestration/18-kubernetes-security-model.md §6.
# Every devplat namespace starts with default-deny-all (ingress+egress). Ephemeral test namespaces get the same
# default-deny plus the test flows (doc 18 §6.3) from the controller (as devplat-namespacer) at creation time.
# Selectors: namespaces by devplat.io/ns-role; project pods by devplat.io/workload and devplat.io/network-class
# (none | model-only | deps), both set by the controller from the execution profile, checked by admission.
# Requires a CNI that enforces NetworkPolicy (e.g. Cilium, Calico; verify the workstation CNI). Plain flannel does NOT: then
# every policy here is inert -> reduced-assurance mode (doc 18 §12).
# PLACEHOLDERS the overlay MUST replace: 192.0.2.10/32 (TEST-NET-1) = kube-apiserver endpoint IPs (post-DNAT);
# 198.51.100.10/32 (TEST-NET-2) = external S3-compatible object store (default; reached ONLY by platform
# components; the in-cluster devplat-artifacts store on :9000 is optional); 203.0.113.10/32 (TEST-NET-3) =
# managed PostgreSQL (policy external-postgres; delete it when PostgreSQL runs in-cluster);
# namespace label devplat.io/ingress-gateway=true = the operator's ingress controller namespace; cnpg-system.
# Port convention (aligned with charts/devplat values and doc 16): api, gitbroker, model-gateway 8080;
# gitbroker-fetch 8081; artifact-gateway 8082 (Job uploads) and 9444 (controller admin); namespacer 8083;
# model-gateway admin 9443; registry-proxy-<project> 4873 (packages) and 5000 (OCI pull-through);
# devplat-dns pod port 1053 (Service port 53); artifact store 9000; postgres 5432 (+8000 CNPG status);
# metrics 9090; grafana 3000. Policies match pod (target) ports, i.e. after Service translation.
"""
out = hdr + "".join("---\n" + yaml.safe_dump(d, sort_keys=False, default_flow_style=False) for d in docs)
open(sys.argv[1], "w").write(out)
print(len(docs), "documents")
