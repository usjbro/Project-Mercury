{{- define "proj.labels" -}}
app.kubernetes.io/part-of: devplat
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
devplat.io/project: {{ .Values.project.id }}
{{- end -}}

{{- define "proj.ns" -}}
{{ .Values.project.namespacePrefix }}-{{ .role }}
{{- end -}}

{{/* PSA labels pinned to v1.33 (doc 18 I-9): upgrades never silently change the rules. */}}
{{- define "proj.psa" -}}
pod-security.kubernetes.io/enforce: {{ .enforce }}
pod-security.kubernetes.io/enforce-version: v1.33
pod-security.kubernetes.io/audit: restricted
pod-security.kubernetes.io/audit-version: v1.33
pod-security.kubernetes.io/warn: restricted
pod-security.kubernetes.io/warn-version: v1.33
{{- end -}}

{{- define "proj.quota" -}}
hard:
  {{- range $k, $v := . }}
  {{ $k }}: {{ $v | quote }}
  {{- end }}
  services: "0"
  services.loadbalancers: "0"
  services.nodeports: "0"
{{- end -}}

{{- define "proj.limits" -}}
limits:
  - type: Container
    max:
      {{- toYaml .max | nindent 6 }}
    min:
      {{- toYaml .min | nindent 6 }}
    default:
      {{- toYaml .default | nindent 6 }}
    defaultRequest:
      {{- toYaml .defaultRequest | nindent 6 }}
  - type: PersistentVolumeClaim
    max:
      storage: {{ .pvcMaxStorage }}
{{- end -}}

{{- define "proj.assert" -}}
{{- if ne .Values.project.namespacePrefix (printf "proj-%s" .Values.project.id) -}}
{{- fail "project.namespacePrefix must equal proj-<project.id>" -}}
{{- end -}}
{{- end -}}

{{/* Egress rules for DNS (devplat-dns only; never kube-dns, doc 18 section 9.4). */}}
{{- define "proj.dnsEgress" -}}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.platformNamespace }}
      podSelector:
        matchLabels:
          app.kubernetes.io/name: devplat-dns
  ports:
    - {protocol: UDP, port: 1053}
    - {protocol: TCP, port: 1053}
{{- end -}}

{{- define "proj.artifactsEgress" -}}
{{- if .Values.artifacts.inCluster.enabled }}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: devplat-artifacts
      podSelector:
        matchLabels:
          app.kubernetes.io/name: devplat-artifacts
  ports:
    - {protocol: TCP, port: 9000}
{{- end }}
{{- with .Values.artifacts.externalCidrs }}
- to:
    {{- range . }}
    - ipBlock:
        cidr: {{ . }}
    {{- end }}
  ports:
    - {protocol: TCP, port: 443}
{{- end }}
{{- end -}}
