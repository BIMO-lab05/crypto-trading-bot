{{/*
Expand the name of the chart.
*/}}
{{- define "crypto-trading-bot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "crypto-trading-bot.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "crypto-trading-bot.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "crypto-trading-bot.labels" -}}
helm.sh/chart: {{ include "crypto-trading-bot.chart" . }}
{{ include "crypto-trading-bot.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: crypto-trading-bot
environment: {{ .Values.global.environment }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "crypto-trading-bot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "crypto-trading-bot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "crypto-trading-bot.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "crypto-trading-bot.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Generate full image name with registry
*/}}
{{- define "crypto-trading-bot.image" -}}
{{- $registry := .Values.global.imageRegistry -}}
{{- $repository := .Values.image.repository -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry $repository $tag }}
{{- else }}
{{- printf "%s:%s" $repository $tag }}
{{- end }}
{{- end }}

{{/*
Generate PostgreSQL connection string
*/}}
{{- define "crypto-trading-bot.postgresql.url" -}}
{{- printf "postgresql://%s:$(POSTGRES_PASSWORD)@%s:%d/%s" .Values.global.postgresql.username .Values.global.postgresql.host (.Values.global.postgresql.port | int) .Values.global.postgresql.database }}
{{- end }}

{{/*
Generate TimescaleDB connection string
*/}}
{{- define "crypto-trading-bot.timescaledb.url" -}}
{{- printf "postgresql://%s:$(TIMESCALE_PASSWORD)@%s:%d/%s" .Values.global.timescaledb.username .Values.global.timescaledb.host (.Values.global.timescaledb.port | int) .Values.global.timescaledb.database }}
{{- end }}

{{/*
Generate Redis connection string
*/}}
{{- define "crypto-trading-bot.redis.url" -}}
{{- if .Values.global.redis.existingSecret }}
{{- printf "redis://:%s@%s:%d/%d" "$(REDIS_PASSWORD)" .Values.global.redis.host (.Values.global.redis.port | int) (.Values.global.redis.database | int) }}
{{- else }}
{{- printf "redis://%s:%d/%d" .Values.global.redis.host (.Values.global.redis.port | int) (.Values.global.redis.database | int) }}
{{- end }}
{{- end }}

{{/*
Generate RabbitMQ connection string
*/}}
{{- define "crypto-trading-bot.rabbitmq.url" -}}
{{- printf "amqp://%s:$(RABBITMQ_PASSWORD)@%s:%d/" .Values.global.rabbitmq.username .Values.global.rabbitmq.host (.Values.global.rabbitmq.port | int) }}
{{- end }}

{{/*
Common environment variables for all services
*/}}
{{- define "crypto-trading-bot.commonEnv" -}}
- name: ENVIRONMENT
  value: {{ .Values.global.environment | quote }}
- name: LOG_LEVEL
  value: {{ .Values.global.logging.level | quote }}
- name: LOG_FORMAT
  value: {{ .Values.global.logging.format | quote }}
- name: POSTGRES_HOST
  value: {{ .Values.global.postgresql.host | quote }}
- name: POSTGRES_PORT
  value: {{ .Values.global.postgresql.port | quote }}
- name: POSTGRES_DB
  value: {{ .Values.global.postgresql.database | quote }}
- name: POSTGRES_USER
  value: {{ .Values.global.postgresql.username | quote }}
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.global.postgresql.existingSecret }}
      key: {{ .Values.global.postgresql.existingSecretPasswordKey }}
- name: TIMESCALE_HOST
  value: {{ .Values.global.timescaledb.host | quote }}
- name: TIMESCALE_PORT
  value: {{ .Values.global.timescaledb.port | quote }}
- name: TIMESCALE_DB
  value: {{ .Values.global.timescaledb.database | quote }}
- name: TIMESCALE_USER
  value: {{ .Values.global.timescaledb.username | quote }}
- name: TIMESCALE_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.global.timescaledb.existingSecret }}
      key: {{ .Values.global.timescaledb.existingSecretPasswordKey }}
- name: REDIS_HOST
  value: {{ .Values.global.redis.host | quote }}
- name: REDIS_PORT
  value: {{ .Values.global.redis.port | quote }}
- name: REDIS_DB
  value: {{ .Values.global.redis.database | quote }}
{{- if .Values.global.redis.existingSecret }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.global.redis.existingSecret }}
      key: {{ .Values.global.redis.existingSecretPasswordKey }}
{{- end }}
- name: RABBITMQ_HOST
  value: {{ .Values.global.rabbitmq.host | quote }}
- name: RABBITMQ_PORT
  value: {{ .Values.global.rabbitmq.port | quote }}
- name: RABBITMQ_USER
  value: {{ .Values.global.rabbitmq.username | quote }}
- name: RABBITMQ_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .Values.global.rabbitmq.existingSecret }}
      key: {{ .Values.global.rabbitmq.existingSecretPasswordKey }}
{{- end }}

{{/*
Bybit API environment variables
*/}}
{{- define "crypto-trading-bot.bybitEnv" -}}
- name: BYBIT_API_URL
  value: {{ .Values.global.bybit.apiUrl | quote }}
- name: BYBIT_WS_URL
  value: {{ .Values.global.bybit.wsUrl | quote }}
- name: BYBIT_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.global.bybit.existingSecret }}
      key: {{ .Values.global.bybit.existingSecretApiKeyKey }}
- name: BYBIT_API_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Values.global.bybit.existingSecret }}
      key: {{ .Values.global.bybit.existingSecretApiSecretKey }}
{{- end }}

{{/*
Common security context
*/}}
{{- define "crypto-trading-bot.securityContext" -}}
runAsNonRoot: {{ .Values.global.securityContext.runAsNonRoot }}
runAsUser: {{ .Values.global.securityContext.runAsUser }}
runAsGroup: {{ .Values.global.securityContext.runAsGroup }}
fsGroup: {{ .Values.global.securityContext.fsGroup }}
{{- if .Values.global.securityContext.seccompProfile }}
seccompProfile:
  type: {{ .Values.global.securityContext.seccompProfile.type }}
{{- end }}
{{- end }}

{{/*
Container security context
*/}}
{{- define "crypto-trading-bot.containerSecurityContext" -}}
allowPrivilegeEscalation: {{ .Values.global.containerSecurityContext.allowPrivilegeEscalation }}
readOnlyRootFilesystem: {{ .Values.global.containerSecurityContext.readOnlyRootFilesystem }}
capabilities:
  drop:
  {{- range .Values.global.containerSecurityContext.capabilities.drop }}
  - {{ . }}
  {{- end }}
{{- end }}

{{/*
Resource limits and requests
*/}}
{{- define "crypto-trading-bot.resources" -}}
{{- if .Values.resources }}
limits:
  {{- if .Values.resources.limits }}
  {{- if .Values.resources.limits.cpu }}
  cpu: {{ .Values.resources.limits.cpu }}
  {{- end }}
  {{- if .Values.resources.limits.memory }}
  memory: {{ .Values.resources.limits.memory }}
  {{- end }}
  {{- end }}
requests:
  {{- if .Values.resources.requests }}
  {{- if .Values.resources.requests.cpu }}
  cpu: {{ .Values.resources.requests.cpu }}
  {{- end }}
  {{- if .Values.resources.requests.memory }}
  memory: {{ .Values.resources.requests.memory }}
  {{- end }}
  {{- end }}
{{- end }}
{{- end }}

{{/*
Metrics port annotation
*/}}
{{- define "crypto-trading-bot.metricsAnnotations" -}}
{{- if .Values.global.metrics.enabled }}
prometheus.io/scrape: "true"
prometheus.io/port: {{ .Values.global.metrics.port | quote }}
prometheus.io/path: {{ .Values.global.metrics.path | quote }}
{{- end }}
{{- end }}

{{/*
Storage class
*/}}
{{- define "crypto-trading-bot.storageClass" -}}
{{- if .Values.persistence.storageClass }}
{{- if (eq "-" .Values.persistence.storageClass) }}
storageClassName: ""
{{- else }}
storageClassName: {{ .Values.persistence.storageClass | quote }}
{{- end }}
{{- else }}
storageClassName: {{ .Values.global.storageClass | quote }}
{{- end }}
{{- end }}

{{/*
Pod annotations - merge global and service-specific
*/}}
{{- define "crypto-trading-bot.podAnnotations" -}}
{{- $globalAnnotations := include "crypto-trading-bot.metricsAnnotations" . | fromYaml -}}
{{- $serviceAnnotations := .Values.podAnnotations | default dict -}}
{{- toYaml (merge $serviceAnnotations $globalAnnotations) }}
{{- end }}

{{/*
Node selector
*/}}
{{- define "crypto-trading-bot.nodeSelector" -}}
{{- if .Values.nodeSelector }}
{{- toYaml .Values.nodeSelector }}
{{- end }}
{{- end }}

{{/*
Tolerations
*/}}
{{- define "crypto-trading-bot.tolerations" -}}
{{- if .Values.tolerations }}
{{- toYaml .Values.tolerations }}
{{- end }}
{{- end }}

{{/*
Affinity
*/}}
{{- define "crypto-trading-bot.affinity" -}}
{{- if .Values.affinity }}
{{- toYaml .Values.affinity }}
{{- end }}
{{- end }}

{{/*
Create service labels for a specific component
*/}}
{{- define "crypto-trading-bot.componentLabels" -}}
{{- $componentName := .componentName -}}
{{- $context := .context -}}
app: {{ $componentName }}
component: {{ $componentName }}
{{ include "crypto-trading-bot.labels" $context }}
{{- end }}

{{/*
Create selector labels for a specific component
*/}}
{{- define "crypto-trading-bot.componentSelectorLabels" -}}
{{- $componentName := .componentName -}}
{{- $context := .context -}}
app: {{ $componentName }}
app.kubernetes.io/name: {{ $componentName }}
app.kubernetes.io/instance: {{ $context.Release.Name }}
{{- end }}
