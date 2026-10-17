{{/*
devplat control-plane helpers. Proposed (Amendment 001); not rendered with helm in the authoring environment.
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

{{/* Image by digest only. Fails while no image exists (placeholder digests are empty). */}}
{{- define "devplat.image" -}}
{{- $d := required (printf "%s.image.digest is empty: no devplat-%s image has been published yet; supply sha256:<64 hex>" .key .name) .image.digest -}}
{{ .image.repository }}@{{ $d }}
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
{{- define "devplat.pgSecret" -}}
{{- if eq .root.Values.postgres.mode "cnpg" -}}
devplat-pg-{{ .role }}
{{- else -}}
{{ required "postgres.external.credentialsSecretRef is required" .root.Values.postgres.external.credentialsSecretRef }}-{{ .role }}
{{- end -}}
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

{{/* Guard: NetworkPolicy off is only allowed in reduced assurance mode. */}}
{{- define "devplat.assertAssurance" -}}
{{- if and (not .Values.networkPolicy.enabled) (eq .Values.platform.assuranceMode "standard") -}}
{{- fail "networkPolicy.enabled=false requires platform.assuranceMode=reduced (25-deployment-profiles.md)" -}}
{{- end -}}
{{- if and .Values.ingress.enabled (eq .Values.api.oidc.issuerUrl "") -}}
{{- fail "ingress.enabled=true requires api.oidc.issuerUrl: the API is never exposed without operator authentication" -}}
{{- end -}}
{{- end -}}
