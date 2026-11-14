{{- define "octop.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "octop.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "octop.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "octop.labels" -}}
helm.sh/chart: {{ include "octop.chart" . }}
app.kubernetes.io/name: {{ include "octop.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{- define "octop.selectorLabels" -}}
app.kubernetes.io/name: {{ include "octop.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: server
{{- end -}}

{{- define "octop.postgres.selectorLabels" -}}
app.kubernetes.io/name: {{ include "octop.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: postgres
{{- end -}}

{{- define "octop.image" -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{- define "octop.database.host" -}}
{{- if .Values.postgresql.enabled -}}
{{- printf "%s-pgvector" (include "octop.fullname" .) -}}
{{- else -}}
{{- required "database.host is required when postgresql.enabled is false" .Values.database.host -}}
{{- end -}}
{{- end -}}

{{- define "octop.corsOrigins" -}}
{{- if .Values.config.corsOrigins -}}
{{- .Values.config.corsOrigins -}}
{{- else -}}
{{- printf "https://%s" .Values.ingress.host -}}
{{- end -}}
{{- end -}}
