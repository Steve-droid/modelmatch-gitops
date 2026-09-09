# P38o ingress and public-demo rollout

Implementation is local, awaiting review/release. Existing image pins, public DNS, the NLB,
EKS API allowlist and infrastructure resources are unchanged.

## Configuration

- `charts/modelmatch/values.yaml` explicitly configures 700 accounts, operator-only chat via
  the backend entitlement, the shared auth token bucket, and bounded DB pools. Set
  `MAX_REGISTERED_USERS=0` to close signup without blocking returning users; keep the auth limiter
  enabled. The role grant is a reviewed backend CLI operation, not a public signup field.
- `ingress.protection` enables F5 per-IP rate limits: API 10 r/s + burst 20; frontend 60 r/s +
  burst 100; `/auth` 30 r/m + burst 10. Excess is rejected immediately with 429. Auth bodies are
  limited to 32k; ordinary routes retain a 1m bound. Proxy connect/send/read waits are bounded.
- These are per-ingress, per-controller zones. Branded and legacy API hosts each get the `/auth`
  minion; the backend's shared bucket prevents switching hostnames from bypassing the aggregate
  auth ceiling. Shared-office/carrier IPs share the ingress allowance; tune deliberately if
  legitimate users are throttled. Re-evaluate limits before increasing controller replicas.
- The NLB preserves source IP with `externalTrafficPolicy: Local`; the controller does not trust
  arbitrary X-Forwarded-For for its limit key. The backend's aggregate limiter is independent of
  client IP headers. A distributed attack can still deny service; these are not volumetric DDoS
  protection or a guaranteed AWS billing cap.
- The controller ConfigMap's central `http-snippets` defines a map of **actual `$scheme:$uri`**.
  `server-snippets` issues 308 to HTTPS except `/.well-known/acme-challenge/`. Keep the app's
  `sslRedirect=false`: F5's unconditional server redirect would preempt the HTTP-01 exception.
  Both request-header and body timeouts are explicit NGINX directives in the central HTTP snippet;
  F5 5.5.0 does not accept the guessed `client-header-timeout`/`client-body-timeout` ConfigMap keys.
  Arbitrary Ingress snippets remain disabled; no new CRDs/NGINX Plus/WAF/CloudFront are required.
- Grafana's app dashboard adds registration/auth rejections and backend 403/429 rates. Existing
  HTTP latency/errors, DB query timing, pod resources and LLM token panels remain available.

## Verified locally

Helm lint/render + existing chart tests; actual F5 OSS **5.5.0**, chart **2.6.0**, in an isolated
`kind-p38o` cluster using `/tmp/p38o-kubeconfig`, never the live context. Synthetic app/API upstreams
and an HTTP-01 solver minion exercise the rendered real Ingress resources. Four HTTP redirects,
four HTTPS routes, solver HTTP 200, auth body 413, and per-IP 429 under changing forged
X-Forwarded-For all pass. `nginx -T` confirms rate zones and both 10-second client timeouts.
The fixture certificate is self-signed; this is a routing check, not a live certificate proof.

`tests/local_ingress_smoke.py` runs the black-box checks against local port-forwards 18080/18443.
It asserts the isolated context and sends only loopback requests. To recreate the fixture:
use kind with that explicit kubeconfig; install the pinned controller using the Helm values from
`argocd/apps/nginx-ingress.yaml` with only the Service changed to ClusterIP; render the app chart
with namespace `app`, apply only its Ingress resources plus synthetic backend/frontend Services,
replace master TLS refs with a test certificate, and add an exact solver minion at
`/.well-known/acme-challenge/p38o` for `api.modicum.cloud`. The synthetic upstream returns the
literal `synthetic-upstream`. The companion umbrella review retains test results and screenshots.

## Live release still required

Review first. Release the DB migration/backend controls before frontend visibility and ingress
changes; explicitly grant only Steve's verified existing account. Use the migration-only Job
with seeds disabled. No role grant, live schema change, image bump or ArgoCD sync happened here.
After approval, verify exact release/image digests and generated NGINX configuration, both old
and new hosts, HTTPS and real HTTP-01 renewal compatibility. Keep rollback of the UI independent
from security controls; do not restore unrestricted paid endpoints. Reverting only the central
redirect snippets temporarily restores plain HTTP, so avoid that except for a reviewed incident.

Steve selected a temporary demo on 2026-09-09. Existing teardown/data deletion remains intentional
and the frontend now discloses it. No backup/restore cost is introduced in P38o.
