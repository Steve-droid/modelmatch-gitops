{{/*
Helpers for the backend subchart. All define names are namespaced with `backend.`
so they never collide with the frontend subchart in the same umbrella render.
*/}}

{{- define "backend.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "backend.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "backend.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "backend.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: modelmatch
app.kubernetes.io/component: backend
{{- end -}}

{{/* Fully-qualified image ref from the shared registry + per-subchart repo/tag. */}}
{{- define "backend.image" -}}
{{- $registry := .Values.image.registry | default .Values.global.imageRegistry -}}
{{- printf "%s/%s:%s" $registry .Values.image.repository (.Values.image.tag | toString) -}}
{{- end -}}
