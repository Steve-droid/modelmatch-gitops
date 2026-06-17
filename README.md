# modelmatch-gitops

> **ACTIVE** (since P9). The GitOps source of truth for everything that runs **inside** the EKS cluster —
> a Helm umbrella + an ArgoCD **App-of-Apps**. Part of the [ModelMatch portfolio build](../CLAUDE.md);
> spec in [`../docs/planning/architecture.md`](../docs/planning/architecture.md) §12–§13 and
> `../docs/instructions/lesson-03`. See [`CLAUDE.md`](CLAUDE.md) for the chart layout + hard rules.

## Table of Contents

- [Overview](#overview)
- [The deploy boundary](#the-deploy-boundary)
- [Technology Stack](#technology-stack)
- [Repository Structure](#repository-structure)
- [ArgoCD App-of-Apps](#argocd-app-of-apps)
- [Getting Started / verification](#getting-started--verification)
- [Ingress host recompute (P15 runbook)](#ingress-host-recompute-p15-runbook)
- [Conventions](#conventions)
- [Contact](#contact)

## Overview

The GitOps repo holds the desired state of the cluster. Two layers:

1. **The ModelMatch product chart** — `charts/modelmatch/`, a Helm **umbrella** with **frontend** +
   **backend** local subcharts plus the host-based `Ingress` templates. One release boundary for the app.
2. **Platform charts + ArgoCD App-of-Apps** — a Terraform-seeded **root Application** (in
   `modelmatch-infra/platform/argocd.tf`) watches `argocd/apps/` and fans out to one child `Application`
   per platform component (ingress controller, cert-manager, ESO, CNPG, monitoring, logging, cluster
   issuers, app secrets) **and** the product chart.

**Kubernetes hygiene** is enforced everywhere: dedicated namespaces, **resource requests/limits on every
container**, liveness/readiness probes wired to `/healthz` + `/readyz`. The in-cluster Postgres runs on an
**EBS-CSI-backed PVC** (no container-disk state). DB migrations run as a **PostSync Job/hook**, never on
backend startup.

> The proactive advisor was scoped as a **separable, feature-flagged** subchart
> (`FEATURE_PROACTIVE_ADVISOR`) — droppable by demo time with no core impact. It is **not** part of the
> shipped chart.

## The deploy boundary

**CI builds images, pushes to ECR, and commits an image-tag bump here; ArgoCD is the only thing that ever
applies to the cluster.** Humans author chart structure; the Jenkins **Deploy** stage edits the
per-subchart `image.tag` in `charts/modelmatch/values.yaml`; ArgoCD syncs. **Never `helm install` /
`kubectl apply` app resources by hand** — that breaks the GitOps invariant.

```
Jenkins (FE/BE repos)                    this repo (git)                 EKS
  build → ECR → commit "image.tag bump" ───────────►  ArgoCD auto-sync ───────► cluster
```

## Technology Stack

| Category       | Technologies   |
| -------------- | -------------- |
| **Packaging**  | Helm (umbrella `modelmatch` + FE/BE subcharts; in-repo platform charts) |
| **GitOps**     | ArgoCD (App-of-Apps; `prune` + `selfHeal` auto-sync) |
| **Ingress**    | F5 NGINX Ingress Controller (OSS) — one ELB; **host-based** (`app.`/`api.` sslip.io) |
| **TLS**        | cert-manager + Let's Encrypt (HTTP-01); sslip.io host (no domain to register) |
| **Database**   | PostgreSQL 16 — in-cluster via CloudNativePG, EBS-CSI PVC |
| **Secrets**    | External Secrets Operator → AWS Secrets Manager (IRSA role B) |
| **Observability** | kube-prometheus-stack (Grafana dashboards) · ECK Elasticsearch/Kibana + Fluent Bit (EFK) |

## Repository Structure

```
modelmatch-gitops/
├── charts/
│   ├── modelmatch/            # umbrella = the product chart (release boundary)
│   │   ├── Chart.yaml         # deps: backend, frontend (local, condition <name>.enabled)
│   │   ├── values.yaml        # global.imageRegistry + global.sslipIp + backend:/frontend: + ingress:
│   │   ├── templates/         # host-based Ingress (F5 master/minion) + NOTES.txt
│   │   └── charts/{backend,frontend}/   # FastAPI + nginx subcharts (Deployment+Service+ConfigMap, probes)
│   ├── modelmatch-postgres/   # CNPG Cluster + gp3 StorageClass + migrate Job (P13)
│   ├── app-secrets/           # ESO SecretStore + ExternalSecret (P12)
│   ├── cluster-issuers/       # Let's Encrypt staging + prod ClusterIssuers, HTTP-01 (P15)
│   ├── monitoring/            # kube-prometheus-stack values + Grafana dashboards (P20–P22)
│   └── logging/               # ECK Elasticsearch/Kibana + Fluent Bit (EFK) (P23)
├── argocd/
│   ├── README.md              # the root App-of-Apps explained
│   └── apps/                  # one ArgoCD Application per child app (see below)
├── scripts/recompute-host.sh  # re-derive the sslip.io host after an ELB IP change
├── docs/diagrams/
├── README.md · CLAUDE.md · .gitignore
```

## ArgoCD App-of-Apps

The Terraform-seeded root Application watches [`argocd/apps/`](argocd/apps/); each `Application` manifest
there points either at a pinned upstream chart (thin app + inline `helm.values`) or at an in-repo `path:`.
All auto-sync (`prune` + `selfHeal`), ordered by **sync-waves** where dependencies require it (e.g. the
CNPG operator before the Postgres cluster; cert-manager before its ClusterIssuers).

| Child app | Source | Namespace | Slice |
|---|---|---|---|
| `nginx-ingress` | F5 NGINX Ingress Controller (OSS) — the single ingress LB | `nginx-ingress` | P11 |
| `cert-manager` | `jetstack/cert-manager` | `cert-manager` | P11 |
| `external-secrets` | `external-secrets` (IRSA role B) | `external-secrets` | P11 |
| `app-secrets` | in-repo `charts/app-secrets` | `app` | P12 |
| `cnpg-operator` | `cloudnative-pg` | `cnpg-system` | P13 |
| `modelmatch-postgres` | in-repo `charts/modelmatch-postgres` | `app` | P13 |
| `modelmatch` | in-repo `charts/modelmatch` (FE + BE + Ingress) | `app` | P14/P15 |
| `cluster-issuers` | in-repo `charts/cluster-issuers` | (cluster-scoped) | P15 |
| `monitoring` + `monitoring-dashboards` | kube-prometheus-stack + Grafana dashboards | `monitoring` | P20–P22 |
| `logging` + `logging-operator` + `logging-fluent-bit` | ECK ES/Kibana + Fluent Bit (EFK) | `logging` | P23 |

See [`argocd/apps/README.md`](argocd/apps/README.md) for the per-app sync-wave reasoning and the
ingress-LB teardown gotcha.

> **Why F5, not community `ingress-nginx`:** the community project was archived 2026-03-24 (end-of-life),
> so the maintained **F5 NGINX Ingress Controller (OSS)** is used instead — same architecture (one NGINX
> controller, one `LoadBalancer` Service, standard `Ingress`).

## Getting Started / verification

This repo is **never** applied by hand — ArgoCD reconciles it. Local work is **author + render-check
only**:

```bash
helm lint charts/modelmatch
helm template modelmatch charts/modelmatch        # renders clean (sslipIp may be the 0.0.0.0 sentinel)
git diff charts/modelmatch/values.yaml
```

Push to `main`; ArgoCD auto-syncs. **No `helm install` / `kubectl apply`.**

## Ingress host recompute (P15 runbook)

The app is reachable over HTTPS at a **sslip.io** host derived from the single ingress ELB's public IP.
That IP has **no static allocation** — every platform rebuild gives a new one — so the host is a
**recompute, not a stable name**. One field drives everything: `global.sslipIp` in
[`charts/modelmatch/values.yaml`](charts/modelmatch/values.yaml). The Ingress, the FE `API_BASE_URL`, and
the BE `PUBLIC_BASE_URL`/`CORS_ALLOW_ORIGINS` all derive from it in-template:

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

**TLS — staging → prod.** `ingress.clusterIssuer` validates HTTP-01 on `letsencrypt-staging` first
(untrusted cert; `curl -k`), then flips to `letsencrypt-prod` (current). On a fresh rebuild, if a stale
staging cert lingers, **delete the `app/modelmatch-app-tls` and `app/modelmatch-api-tls` Secrets** so
cert-manager re-issues against prod, then verify a trusted chain (no `-k`):

```bash
kubectl -n app get ingress,certificate,order,challenge
curl -kI https://app.<ip>.sslip.io/          # FE
curl -k  https://api.<ip>.sslip.io/healthz   # BE
```

**Why the Ingress is split (F5 mergeable master/minion).** F5 NGINX, unlike community ingress-nginx,
won't merge a second Ingress onto a host the app already owns — and cert-manager's HTTP-01 solver *is* a
second Ingress on that host. So per host the umbrella renders a **master** (host + TLS + cert-manager
annotation, no paths) + a **minion** (the route), and the ClusterIssuer annotates the solver as another
minion so F5 merges the challenge path in. `ssl-redirect` is forced **off** (F5 otherwise 301s
HTTP→HTTPS, breaking the plain-HTTP:80 challenge and the 60-day renewals). Each host owns its own
single-SAN cert (`modelmatch-app-tls` / `modelmatch-api-tls`).

## Conventions

- Humans commit chart structure; the CI Deploy stage commits image-tag bumps; ArgoCD syncs.
- **NO secrets in values/ConfigMap — ever.** `JWT_SECRET`, the DB password, and the chat read-only DB
  password arrive via **ESO → AWS Secrets Manager**. ConfigMaps hold non-secret knobs only.
- Resource requests/limits on **every** container; backend capped at **1Gi** (the ingestion-OOM gotcha).
- Branching: `feature/<story-id>-<desc>` → PR (self-review) → merge `--no-ff` → `main`. Conventional
  Commits; SemVer tags. Verification = `helm lint` + `helm template`, never `helm install`.

## Contact

Steve Levit — stevelevit230@gmail.com
</content>
