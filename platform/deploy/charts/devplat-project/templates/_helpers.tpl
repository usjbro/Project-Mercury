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

{{- define "proj.quota" -}}
hard:
  pods: {{ .pods | quote }}
  requests.cpu: {{ .requestsCpu | quote }}
  requests.memory: {{ .requestsMemory | quote }}
  limits.cpu: {{ .limitsCpu | quote }}
  limits.memory: {{ .limitsMemory | quote }}
  requests.ephemeral-storage: {{ .requestsEphemeralStorage | quote }}
  limits.ephemeral-storage: {{ .limitsEphemeralStorage | quote }}
  persistentvolumeclaims: "0"
  services: "0"
  services.loadbalancers: "0"
  services.nodeports: "0"
  secrets: "0"
{{- end -}}

{{- define "proj.assert" -}}
{{- if ne .Values.project.namespacePrefix (printf "proj-%s" .Values.project.id) -}}
{{- fail "project.namespacePrefix must equal proj-<project.id>" -}}
{{- end -}}
{{- end -}}

{{/* Egress rules shared by exec and build namespaces: DNS, gitbroker (fetch), artifact store. */}}
{{- define "proj.baseEgress" -}}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
      podSelector:
        matchLabels:
          k8s-app: kube-dns
  ports:
    - {protocol: UDP, port: 53}
    - {protocol: TCP, port: 53}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.platformNamespace }}
      podSelector:
        matchLabels:
          app.kubernetes.io/name: devplat-gitbroker
  ports:
    - {protocol: TCP, port: 8080}
{{- if .Values.artifacts.egressCidrs }}
- to:
    {{- range .Values.artifacts.egressCidrs }}
    - ipBlock:
        cidr: {{ . }}
    {{- end }}
  ports:
    - {protocol: TCP, port: 443}
{{- else }}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.artifacts.inClusterNamespace }}
  ports:
    - {protocol: TCP, port: {{ .Values.artifacts.inClusterPort }}}
{{- end }}
{{- end -}}

{{- define "proj.registryEgress" -}}
{{- if .Values.registryProxy.enabled }}
- to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: {{ .Values.registryProxy.namespace }}
      podSelector:
        matchLabels:
          {{- toYaml .Values.registryProxy.podLabels | nindent 10 }}
  ports:
    - {protocol: TCP, port: {{ .Values.registryProxy.port }}}
{{- end }}
{{- end -}}
