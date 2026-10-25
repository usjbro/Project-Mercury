{{/*
devplat control-plane helpers. Proposed (Amendment 001, R6 fix round). Rendered and validated offline only
(platform/tools/charts/run.sh); never installed.
*/}}

{{- define "devplat.chart" -}}
{{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "devplat.labels" -}}
app.kubernetes.io/part-of: devplat
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
helm.sh/chart: {{ include "devplat.chart" .root }}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/component: {{ .name }}
{{- end -}}

{{- define "devplat.selectorLabels" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/name: {{ .name }}
{{- end -}}

{{/* Image by digest only: <imageRegistry>/<devplat|mirror>/...@sha256:... (D15). Fails while no image exists. */}}
{{- define "devplat.image" -}}
{{- $d := required (printf "%s.image.digest is empty: no image %s has been published/mirrored yet; supply sha256:<64 hex>" .key .image.name) .image.digest -}}
{{ .root.Values.imageRegistry }}/{{ .image.name }}@{{ $d }}
{{- end -}}

{{- define "devplat.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 65532
runAsGroup: 65532
fsGroup: 65532
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "devplat.containerSecurityContext" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
privileged: false
capabilities:
  drop: ["ALL"]
{{- end -}}

{{- define "devplat.placement" -}}
{{- with .Values.placement.control.nodeSelector }}
nodeSelector:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.placement.control.tolerations }}
tolerations:
{{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{- define "devplat.pgHost" -}}
{{- if eq .Values.postgres.mode "cnpg" -}}
devplat-pg-rw.{{ .Release.Namespace }}.svc
{{- else -}}
{{ required "postgres.external.host is required when postgres.mode=external" .Values.postgres.external.host }}
{{- end -}}
{{- end -}}

{{/* DB credential Secret for a component role (basic-auth Secret created by the operator). */}}
{{/* DB role credentials: fixed Secret names (doc 18 section 8.1), kubernetes.io/basic-auth. */}}
{{- define "devplat.dbEnv" -}}
- name: DEVPLAT_DB_HOST
  value: {{ include "devplat.pgHost" .root | quote }}
- name: DEVPLAT_DB_PORT
  value: {{ ternary "5432" (toString .root.Values.postgres.external.port) (eq .root.Values.postgres.mode "cnpg") | quote }}
- name: DEVPLAT_DB_NAME
  value: {{ ternary "devplat" .root.Values.postgres.external.database (eq .root.Values.postgres.mode "cnpg") | quote }}
- name: DEVPLAT_DB_SSLMODE
  value: {{ ternary "verify-full" .root.Values.postgres.external.sslmode (eq .root.Values.postgres.mode "cnpg") | quote }}
- name: DEVPLAT_DB_USER
  valueFrom:
    secretKeyRef:
      name: devplat-db-{{ .role }}
      key: username
- name: DEVPLAT_DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: devplat-db-{{ .role }}
      key: password
{{- end -}}

{{/* S3 credentials per component: fixed Secret names devplat-artifacts-<component> (doc 18 section 8.1). */}}
{{- define "devplat.artifactsEnv" -}}
- name: DEVPLAT_ARTIFACTS_ENDPOINT
  value: {{ .root.Values.artifacts.endpoint | quote }}
- name: DEVPLAT_ARTIFACTS_REGION
  value: {{ .root.Values.artifacts.region | quote }}
- name: DEVPLAT_ARTIFACTS_BUCKET_PREFIX
  value: {{ .root.Values.artifacts.bucketPrefix | quote }}
- name: AWS_ACCESS_KEY_ID
  valueFrom:
    secretKeyRef:
      name: devplat-artifacts-{{ .component }}
      key: access-key-id
- name: AWS_SECRET_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: devplat-artifacts-{{ .component }}
      key: secret-access-key
{{- end -}}

{{- define "devplat.commonEnv" -}}
- name: DEVPLAT_CLUSTER_REF
  value: {{ .Values.platform.clusterRef | quote }}
- name: DEVPLAT_ASSURANCE_MODE
  value: {{ .Values.platform.assuranceMode | quote }}
- name: DEVPLAT_NAMESPACE
  valueFrom:
    fieldRef:
      fieldPath: metadata.namespace
{{- end -}}

{{/* Guards. NetworkPolicies are not rendered by this chart (owned by platform/deploy/base). */}}
{{- define "devplat.assert" -}}
{{- if and .Values.ingress.enabled (eq .Values.api.oidc.issuerUrl "") -}}
{{- fail "ingress.enabled=true requires api.oidc.issuerUrl: the API is never exposed without operator authentication" -}}
{{- end -}}
{{- if ne .Release.Namespace "devplat-system" -}}
{{- fail "install into namespace devplat-system: base RBAC, NetworkPolicies and Secret pinning are bound to it" -}}
{{- end -}}
{{- if eq (len .Values.api.oidc.allowedSubjects) 0 -}}
{{- fail "api.oidc.allowedSubjects is empty: at least one operator identity {issuer, subject, project} is required (D2)" -}}
{{- end -}}
{{- /* S-24: no two components may share the same (non-empty) ServiceAccount annotations, e.g. one cloud identity. */ -}}
{{- $seen := dict -}}
{{- range $k := list "controller" "migrator" "api" "gitbroker" "gitbrokerFetch" "artifactGateway" "modelGateway" -}}
{{- $a := (index $.Values $k).serviceAccountAnnotations -}}
{{- if $a -}}
{{- $j := toJson $a -}}
{{- if hasKey $seen $j -}}
{{- fail (printf "serviceAccountAnnotations of %s and %s are identical: every component needs its own workload identity (S-24)" (get $seen $j) $k) -}}
{{- end -}}
{{- $_ := set $seen $j $k -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "devplat.saAnnotations" -}}
{{- with .annotations }}
annotations:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}
