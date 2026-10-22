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
{{- if and (eq .Values.assurance.mode "reduced") .Values.build.enabled -}}
{{- fail "builds are disabled in reduced-assurance mode (D16)" -}}
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

{{/* Artifacts only through devplat-artifact-gateway :8082 (D10); no object-store egress from project pods. */}}
{{- define "proj.artifactsEgress" -}}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.platformNamespace }}
      podSelector:
        matchLabels:
          app.kubernetes.io/name: devplat-artifact-gateway
  ports:
    - {protocol: TCP, port: 8082}
{{- end -}}

{{/* This project's read-only registry proxy (D14). */}}
{{- define "proj.registryEgress" -}}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.platformNamespace }}
      podSelector:
        matchLabels:
          app.kubernetes.io/name: devplat-registry-proxy-{{ .Values.project.id }}
  ports:
    - {protocol: TCP, port: 4873}
{{- end -}}

{{/* Image prefixes admitted in this project's namespaces (D15). */}}
{{- define "proj.imagePrefixes" -}}
{{ .Values.imageRegistry }}/devplat/,{{ .Values.imageRegistry }}/projects/{{ .Values.project.id }}/,{{ .Values.imageRegistry }}/mirror/
{{- end -}}
