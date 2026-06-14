# `argocd/apps/` — child Application manifests

The Terraform-seeded **root App-of-Apps** (see `../README.md`) watches this directory and auto-syncs
everything in it. Drop **one ArgoCD `Application` manifest per app** here and ArgoCD picks it up — no
`kubectl apply`.

## State: platform controllers + secrets + in-cluster Postgres (through P13)

| File | Child app | Chart (pinned) | Namespace | Slice |
|---|---|---|---|---|
| `nginx-ingress.yaml` | `nginx-ingress` | **F5 NGINX Ingress Controller (OSS)** `nginx-ingress` **2.6.0** (controller 5.5.0) | `nginx-ingress` | P11 |
| `cert-manager.yaml` | `cert-manager` | `jetstack/cert-manager` **v1.20.2** | `cert-manager` | P11 |
| `external-secrets.yaml` | `external-secrets` | `external-secrets` **2.6.0** | `external-secrets` | P11 |
| `app-secrets.yaml` | `app-secrets` | _in-repo_ `charts/app-secrets` (SecretStore + ExternalSecret) | `app` | P12 |
| `cnpg-operator.yaml` | `cnpg-operator` | `cloudnative-pg` **0.28.3** (operator v1.29.1) | `cnpg-system` | P13 |
| `modelmatch-postgres.yaml` | `modelmatch-postgres` | _in-repo_ `charts/modelmatch-postgres` (CNPG `Cluster` + gp3 SC + migrate Job) | `app` | P13 |

The **upstream-chart** apps (nginx-ingress, cert-manager, external-secrets, cnpg-operator) are thin
`Application`s → a pinned chart + inline `helm.values`. The **in-repo-chart** apps (app-secrets,
modelmatch-postgres) point at this repo's `path:`. All auto-sync (`prune`+`selfHeal`). The platform
controllers use **`CreateNamespace=true`** (ArgoCD owns their namespaces); the **`app`** namespace is
Terraform-owned (P10), so the apps landing there do **not** create it. cert-manager, external-secrets, and
cnpg-operator set **`ServerSideApply=true`** because their CRDs exceed the client-side-apply
annotation-size limit.

**P13 ordering (sync-waves):** `cnpg-operator` is wave **`-1`** (installs the `postgresql.cnpg.io` CRDs +
controller first); `modelmatch-postgres` is wave **`1`** — after the operator **and** after `app-secrets`
(default wave `0`), since its owner-credential ExternalSecret needs the P12 `SecretStore` and its migrate
Job needs the `modelmatch-app-secrets` Secret (avoids a fresh-rebuild race). Its `Cluster` CR also carries
`SkipDryRunOnMissingResource=true` for the brief window before the CRD registers. The migrate Job is a
**PostSync hook** that waits on `modelmatch-postgres-rw:5432` before `alembic upgrade head`.

> **Why F5, not `kubernetes/ingress-nginx`:** the community `kubernetes/ingress-nginx` project was
> **archived 2026-03-24** and is end-of-life (no further releases/security fixes), so it can't ship in a
> new install. We use the maintained **F5 NGINX Ingress Controller (OSS)** instead — same architecture
> (one NGINX controller, one `LoadBalancer` Service, standard Kubernetes `Ingress`; no Gateway API).
> [Retirement post](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/) ·
> [F5 repo](https://github.com/nginx/kubernetes-ingress).

**Scope of P11 = install only.** The things that *use* these controllers come later, and are deliberately
**not** here yet:

- **nginx-ingress** provisions the cluster's **single ingress LB** (controller `Service type=LoadBalancer`).
  It runs **standard-Ingress-only** (`enableCustomResources: false` + `skipCrds: true`) — we use plain
  Kubernetes `Ingress`, not F5's VirtualServer/TransportServer CRDs, so the chart's 12 CRDs are skipped.
  Actual `Ingress` routing + TLS (`ClusterIssuer`, sslip.io host) is **P15**.
- **cert-manager** installs its CRDs; no `ClusterIssuer`/`Certificate` yet (**P15**).
- **external-secrets** runs with its main controller SA `external-secrets` annotated with IRSA **role B**
  (`modelmatch-eso-irsa`). The `SecretStore`/`ExternalSecret` that pull secrets from AWS Secrets Manager
  are **P12**.

> **ingress LB is a day-end orphan risk** — the LB is created by the in-cluster cloud-controller-manager,
> *not* tracked by Terraform. Before a platform `terraform destroy`, delete the `nginx-ingress` app/Service
> first so the CCM releases the LB (else it orphans). Keep it to **one** LB (cert-manager/ESO create none).

## What gets added here next

| Slice | Child Application(s) |
|---|---|
| **P14** | `modelmatch` — the product umbrella (`charts/modelmatch/`: **FE + BE only**; Postgres is delivered separately by the `modelmatch-postgres` app above, P13). Annotates the backend SA with IRSA role A; backend reaches Ready (DB + secrets + migrations already present). Backend `DATABASE_URL` host = **`modelmatch-postgres-rw`**. |

> _Auto-sync verified 2026-06-14 (P10): a commit to this path is reconciled by ArgoCD with no manual
> action (no webhook yet — that's P16; ArgoCD polls the repo)._
