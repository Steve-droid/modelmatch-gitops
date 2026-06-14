# `argocd/apps/` — child Application manifests

The Terraform-seeded **root App-of-Apps** (see `../README.md`) watches this directory and auto-syncs
everything in it. Drop **one ArgoCD `Application` manifest per app** here and ArgoCD picks it up — no
`kubectl apply`.

## State: empty skeleton (P10)

At P10 this dir is intentionally empty (only `.gitkeep` + this README). With zero child manifests the
root app is **Synced / Healthy** with no managed resources — exactly the skeleton P10 asks for.

## What gets added here

| Slice | Child Application(s) |
|---|---|
| **P11** | `nginx-ingress`, `cert-manager`, `external-secrets` (platform controllers) |
| **P14** | `modelmatch` — the product umbrella (`charts/modelmatch/`: FE + BE + Postgres) |

Each child Application will set its own `source` (this repo + a chart path, or an upstream chart),
`destination` namespace (`app` / `monitoring` / `logging` — all pre-created), and inherit auto-sync.
