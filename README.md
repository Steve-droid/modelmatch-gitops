# modelmatch-gitops

> **SHELL repo (inactive).** Activates when the GitOps stories begin (after infra + images exist).
> This README describes the intended shape. Part of the [ModelMatch portfolio build](../CLAUDE.md);
> spec in [`../docs/planning/architecture.md`](../docs/planning/architecture.md) §12–§13 and
> `../instructions/lesson-03`.

## Overview

The GitOps source of truth for ModelMatch's cluster state.

What it will hold:

- **Helm umbrella chart** — FE / BE / **in-cluster PostgreSQL** subcharts; the database deploys *with*
  the app on a **PVC** (no data on the container disk). DB migrations run as their own **Job / Helm
  hook**, never on backend startup.
- **ArgoCD app-of-apps** — manages the platform applications (Nginx ingress controller, cert-manager
  TLS, monitoring stack, logging stack) with proper sync policies + health checks.
- **Kubernetes hygiene** — dedicated namespaces (app / argocd / monitoring / logging), resource
  requests/limits on every container, liveness/readiness probes wired to `/healthz` + `/readyz`.
- **Separable proactive advisor** — its own subchart, toggled in one place via a
  `FEATURE_PROACTIVE_ADVISOR` values flag (not a code change) — droppable by demo time with no core
  impact.

The CI "Deploy" stage commits image-tag bumps here; ArgoCD syncs from this repo.

## Technology Stack

| Category       | Technologies   |
| -------------- | -------------- |
| **Packaging**  | Helm (umbrella + FE/BE/DB subcharts) |
| **GitOps**     | ArgoCD (App-of-Apps) |
| **Ingress**    | Nginx ingress controller (single, path-based) |
| **TLS**        | cert-manager |
| **Database**   | PostgreSQL 16 — in-cluster, PVC-backed |

## Repository Structure (planned)

```
modelmatch-gitops/
├── charts/
│   └── modelmatch/         # umbrella chart
│       ├── Chart.yaml
│       ├── values.yaml     # FEATURE_PROACTIVE_ADVISOR toggle lives here
│       └── charts/         # frontend / backend / postgres / advisor subcharts
├── apps/                   # ArgoCD Application + app-of-apps manifests
├── .gitignore
├── README.md
└── CLAUDE.md
```

## Conventions

- Humans commit chart structure; the CI Deploy stage commits image-tag bumps; ArgoCD syncs.
- Never commit rendered secrets (use the chosen secrets mechanism: Secrets Manager + ESO, or Sealed
  Secrets).
- Branching: `feature/<story-id>-<desc>` → PR → `main` (protected).

## Contact

Steve Levit — stevelevit230@gmail.com
