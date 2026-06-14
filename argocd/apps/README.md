# `argocd/apps/` — child Application manifests

The Terraform-seeded **root App-of-Apps** (see `../README.md`) watches this directory and auto-syncs
everything in it. Drop **one ArgoCD `Application` manifest per app** here and ArgoCD picks it up — no
`kubectl apply`.

## State: full E12 stack — controllers + secrets + Postgres + app + ingress/TLS (through P15, E12 complete)

| File | Child app | Chart (pinned) | Namespace | Slice |
|---|---|---|---|---|
| `nginx-ingress.yaml` | `nginx-ingress` | **F5 NGINX Ingress Controller (OSS)** `nginx-ingress` **2.6.0** (controller 5.5.0) | `nginx-ingress` | P11 |
| `cert-manager.yaml` | `cert-manager` | `jetstack/cert-manager` **v1.20.2** | `cert-manager` | P11 |
| `external-secrets.yaml` | `external-secrets` | `external-secrets` **2.6.0** | `external-secrets` | P11 |
| `app-secrets.yaml` | `app-secrets` | _in-repo_ `charts/app-secrets` (SecretStore + ExternalSecret) | `app` | P12 |
| `cnpg-operator.yaml` | `cnpg-operator` | `cloudnative-pg` **0.28.3** (operator v1.29.1) | `cnpg-system` | P13 |
| `modelmatch-postgres.yaml` | `modelmatch-postgres` | _in-repo_ `charts/modelmatch-postgres` (CNPG `Cluster` + gp3 SC + migrate Job) | `app` | P13 |
| `modelmatch.yaml` | `modelmatch` | _in-repo_ `charts/modelmatch` (umbrella: **FE + BE**; + the P15 `Ingress`) | `app` | P14 |
| `cluster-issuers.yaml` | `cluster-issuers` | _in-repo_ `charts/cluster-issuers` (LE staging+prod `ClusterIssuer`s, HTTP-01) | `cert-manager`¹ | P15 |

¹ destination namespace is nominal — `ClusterIssuer`s are **cluster-scoped** (carry no namespace).

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
  **P15** added the actual routing: a single host-based `Ingress` (in the `modelmatch` umbrella) sending
  `app.<ip>.sslip.io` → FE and `api.<ip>.sslip.io` → BE through this same one LB (no second LB).
- **cert-manager** installed its CRDs at P11; **P15** added the `cluster-issuers` app (LE staging+prod
  `ClusterIssuer`s, HTTP-01 over the `nginx` class). The umbrella `Ingress`'s `cert-manager.io/cluster-issuer`
  annotation drives the `Certificate` → the `modelmatch-tls` Secret it serves on :443.
- **external-secrets** runs with its main controller SA `external-secrets` annotated with IRSA **role B**
  (`modelmatch-eso-irsa`). The `SecretStore`/`ExternalSecret` that pull secrets from AWS Secrets Manager
  are **P12**.

> **ingress LB is a day-end orphan risk** — the LB is created by the in-cluster cloud-controller-manager,
> *not* tracked by Terraform. Before a platform `terraform destroy`, delete the `nginx-ingress` app/Service
> first so the CCM releases the LB (else it orphans). Keep it to **one** LB (cert-manager/ESO create none).

**P15 ordering (sync-wave):** `cluster-issuers` is wave **`1`** so it applies after `cert-manager` (default
wave `0`) — its `ClusterIssuer`s need the cert-manager CRDs. cert-manager's CRD install is async across
child apps, so on a fresh rebuild an early apply just retries under auto-sync until the CRD registers
(eventually consistent). The `Ingress` ships inside the `modelmatch` umbrella (wave `2`), so by the time it
requests a cert the issuers already exist.

## What gets added here next

**E12 is complete** — no more child apps until **E13 (observability)**: `kube-prometheus-stack` (P20) and
the EFK/logging stack (P23) will each land here as their own `Application`. E11 (Jenkins CI/CD) adds no
child apps — its Deploy stage only **bumps image tags** in `charts/modelmatch/values.yaml`, which ArgoCD
then reconciles.

> _Auto-sync verified 2026-06-14 (P10): a commit to this path is reconciled by ArgoCD with no manual
> action (no webhook yet — that's P16; ArgoCD polls the repo)._
