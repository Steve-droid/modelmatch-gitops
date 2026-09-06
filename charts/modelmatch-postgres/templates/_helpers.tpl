{{/*
Helpers for the modelmatch-postgres chart (namespaced `postgres.*`).
*/}}

{{/*
ECR registry host (P33b, Option B): derived from global.awsAccountId + global.awsRegion
so the account id lives in one place per chart. `migrate.image.registry` is an explicit
override (unset by default). `required` fails the render loudly if the globals are missing.
*/}}
{{- define "postgres.registry" -}}
{{- if .Values.migrate.image.registry -}}
{{- .Values.migrate.image.registry -}}
{{- else -}}
{{- $account := (required "global.awsAccountId is required" .Values.global.awsAccountId | toString) -}}
{{- $region := (required "global.awsRegion is required" .Values.global.awsRegion | toString) -}}
{{- printf "%s.dkr.ecr.%s.amazonaws.com" $account $region -}}
{{- end -}}
{{- end -}}

{{/* The backend image the migrate + seed Jobs (and the wait-for-db initContainer) run. */}}
{{- define "postgres.migrateImage" -}}
{{- printf "%s/%s:%s" (include "postgres.registry" .) .Values.migrate.image.repository (.Values.migrate.image.tag | toString) -}}
{{- end -}}
