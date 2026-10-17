{{/*
Shared Deployment + Service shape for the four control-plane components.
Input dict: root, name, key (values key), comp (values block), port (int), env (rendered YAML list or ""),
automount (bool), volumes / volumeMounts (rendered YAML or "").
*/}}
{{- define "devplat.workload" -}}
{{- $root := .root -}}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .name }}
  namespace: {{ $root.Release.Namespace }}
  labels:
    {{- include "devplat.labels" (dict "root" $root "name" .name) | nindent 4 }}
spec:
  replicas: {{ .comp.replicas }}
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      {{- include "devplat.selectorLabels" (dict "root" $root "name" .name) | nindent 6 }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  template:
    metadata:
      labels:
        {{- include "devplat.labels" (dict "root" $root "name" .name) | nindent 8 }}
    spec:
      serviceAccountName: {{ .name }}
      automountServiceAccountToken: {{ .automount }}
      enableServiceLinks: false
      securityContext:
        {{- include "devplat.podSecurityContext" $root | nindent 8 }}
      {{- include "devplat.placement" $root | nindent 6 }}
      {{- with $root.Values.image.pullSecrets }}
      imagePullSecrets:
        {{- range . }}
        - name: {{ . }}
        {{- end }}
      {{- end }}
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              {{- include "devplat.selectorLabels" (dict "root" $root "name" .name) | nindent 14 }}
      containers:
        - name: {{ .name }}
          image: {{ include "devplat.image" (dict "image" .comp.image "key" .key "name" (trimPrefix "devplat-" .name)) }}
          imagePullPolicy: {{ $root.Values.image.pullPolicy }}
          securityContext:
            {{- include "devplat.containerSecurityContext" $root | nindent 12 }}
          ports:
            - name: http
              containerPort: {{ .port }}
              protocol: TCP
          env:
            {{- include "devplat.commonEnv" $root | nindent 12 }}
            {{- with .env }}
            {{- . | nindent 12 }}
            {{- end }}
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 20
            failureThreshold: 3
          resources:
            {{- toYaml .comp.resources | nindent 12 }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            {{- with .volumeMounts }}
            {{- . | nindent 12 }}
            {{- end }}
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 64Mi
        {{- with .volumes }}
        {{- . | nindent 8 }}
        {{- end }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ .name }}
  namespace: {{ $root.Release.Namespace }}
  labels:
    {{- include "devplat.labels" (dict "root" $root "name" .name) | nindent 4 }}
spec:
  type: ClusterIP
  selector:
    {{- include "devplat.selectorLabels" (dict "root" $root "name" .name) | nindent 4 }}
  ports:
    - name: http
      port: {{ .port }}
      targetPort: http
      protocol: TCP
{{- if gt (int .comp.replicas) 1 }}
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ .name }}
  namespace: {{ $root.Release.Namespace }}
  labels:
    {{- include "devplat.labels" (dict "root" $root "name" .name) | nindent 4 }}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      {{- include "devplat.selectorLabels" (dict "root" $root "name" .name) | nindent 6 }}
{{- end }}
{{- end -}}
