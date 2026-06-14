# modelmatch-gitops

> **ACTIVE repo.** The GitOps source of truth for ModelMatch's cluster state (Helm umbrella + ArgoCD
> app-of-apps). Part of the [ModelMatch portfolio build](../CLAUDE.md); spec in
> [`../docs/planning/architecture.md`](../docs/planning/architecture.md) §12–§13 and
> `../docs/instructions/lesson-03`. See [`CLAUDE.md`](CLAUDE.md) for the chart layout + hard rules.

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
| **Ingress**    | F5 NGINX Ingress Controller (OSS) — one ELB; **host-based** (app./api. sslip.io) |
| **TLS**        | cert-manager + Let's Encrypt (HTTP-01); sslip.io host (no domain to register) |
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

## Ingress host recompute (P15 runbook)

The app is reachable over HTTPS at a **sslip.io** host derived from the single ingress ELB's public IP.
That IP has **no static allocation** — every platform rebuild gives a new one — so the host is a
**recompute, not a stable name**. One field drives everything: `global.sslipIp` in
[`charts/modelmatch/values.yaml`](charts/modelmatch/values.yaml). The Ingress, the FE `API_BASE_URL`,
and the BE `PUBLIC_BASE_URL`/`CORS_ALLOW_ORIGINS` all derive from it in-template:

```
global.sslipIp = <ELB public IP>
   ├── app.<ip>.sslip.io  → frontend Service (the SPA)
   └── api.<ip>.sslip.io  → backend  Service (FastAPI, at root)
```

**After each cluster rebuild** (or whenever the ELB IP changes), run the helper — it does **read-only
cluster discovery + a one-field local edit only** (never commits, pushes, or `kubectl apply`s):

```bash
./scripts/recompute-host.sh        # digs the ELB IP, writes global.sslipIp, prints next steps
git diff charts/modelmatch/values.yaml
git commit -am "chore(ingress): recompute sslip.io host -> <ip>"
git push                            # ArgoCD auto-syncs; cert-manager (re)issues the cert
```

**TLS — staging → prod.** `ingress.clusterIssuer` starts on `letsencrypt-staging` (validates HTTP-01
without burning prod rate limits; the cert is **untrusted** — browser warning, `curl -k`). Once the
staging cert goes `Ready`, flip it to `letsencrypt-prod`, **delete the old `app/modelmatch-tls` Secret**
so cert-manager re-issues against prod, and verify a trusted chain (no `-k`):

```bash
kubectl -n app get ingress,certificate,order,challenge
curl -kI https://app.<ip>.sslip.io/          # FE
curl -k  https://api.<ip>.sslip.io/healthz   # BE
```

> Both ClusterIssuers (staging + prod) live in [`charts/cluster-issuers`](charts/cluster-issuers) as
> their own ArgoCD child app. The HTTP-01 challenge is served over **port 80** through the same one ELB.

## Contact

Steve Levit — stevelevit230@gmail.com
