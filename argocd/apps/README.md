# `argocd/apps/` — child Application manifests

The Terraform-seeded **root App-of-Apps** (see `../README.md`) watches this directory and auto-syncs
everything in it. Drop **one ArgoCD `Application` manifest per app** here and ArgoCD picks it up — no
`kubectl apply`.

## State: platform controllers landed (P11)

| File | Child app | Upstream chart (pinned) | Namespace |
|---|---|---|---|
| `nginx-ingress.yaml` | `nginx-ingress` | **F5 NGINX Ingress Controller (OSS)** `nginx-ingress` **2.6.0** (controller 5.5.0) | `nginx-ingress` |
| `cert-manager.yaml` | `cert-manager` | `jetstack/cert-manager` **v1.20.2** | `cert-manager` |
| `external-secrets.yaml` | `external-secrets` | `external-secrets` **2.6.0** | `external-secrets` |

Each is a thin `Application` → an **upstream Helm chart** (pinned `targetRevision` + inline `helm.values`),
auto-sync (`prune`+`selfHeal`), and **`CreateNamespace=true`** — ArgoCD owns the namespace lifecycle, so
P11 is **gitops-only** (no Terraform namespaces). cert-manager + external-secrets also set
**`ServerSideApply=true`** because their CRDs exceed the client-side-apply annotation-size limit.

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
| **P14** | `modelmatch` — the product umbrella (`charts/modelmatch/`: FE + BE + Postgres) |

> _Auto-sync verified 2026-06-14 (P10): a commit to this path is reconciled by ArgoCD with no manual
> action (no webhook yet — that's P16; ArgoCD polls the repo)._
