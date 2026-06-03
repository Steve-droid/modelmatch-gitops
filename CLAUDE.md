# CLAUDE.md — modelmatch-gitops

**Status: SHELL (inactive).** Placeholder; activates when the GitOps stories begin (after infra +
images exist).

> **When work starts here:** flip status to **ACTIVE** and fill in real guidance (Helm umbrella
> structure, subcharts, ArgoCD Application manifests, environments/values). Until then this is a stub.

## What it will be

The **GitOps** repo: a **Helm umbrella chart** with **FE / BE / in-cluster Postgres** subcharts (the DB
deploys *with* the app, on a **PVC** — per the build module), plus **ArgoCD app-of-apps** managing the
platform applications (Nginx ingress, cert-manager TLS, monitoring stack, logging stack). Proper sync
policies + health checks; dedicated namespaces; resource requests/limits; liveness/readiness probes
wired to `/healthz` + `/readyz`. DB migrations run as their own **Job/Helm hook**, not on backend startup.

The **proactive advisor is a separable subchart** toggled in one place (a `FEATURE_PROACTIVE_ADVISOR`
values flag, not a code change) — droppable by demo time with no core impact.

See the umbrella `../CLAUDE.md` and `../docs/planning/architecture.md` §12–§13 + `../instructions/lesson-03`.
