#!/usr/bin/env bash
#
# P15 two-phase recompute — phase 2.
#
# The single F5 nginx ingress ELB (P11) has no static IP; every platform rebuild gives
# a new one. The public host is therefore a RECOMPUTE, not a stable name:
#   app.<ip>.sslip.io  -> frontend   |   api.<ip>.sslip.io -> backend
# Both derive from one field, global.sslipIp, in charts/modelmatch/values.yaml.
#
# This script ONLY discovers (read-only on the cluster) and edits ONE local file. It
# NEVER commits, pushes, or `kubectl apply`s — that stays a manual, reviewable step
# (ArgoCD owns the actual deploy). Run it after each rebuild, review the diff, commit.
#
# Usage:   ./scripts/recompute-host.sh
# Env overrides (defaults match P11): INGRESS_NAMESPACE, INGRESS_SERVICE
# Requires: kubectl (pointed at the cluster), dig.

set -euo pipefail

NS="${INGRESS_NAMESPACE:-nginx-ingress}"
SVC="${INGRESS_SERVICE:-nginx-ingress-controller}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALUES="${REPO_ROOT}/charts/modelmatch/values.yaml"

command -v kubectl >/dev/null || { echo "ERROR: kubectl not found in PATH"; exit 1; }
command -v dig     >/dev/null || { echo "ERROR: dig not found in PATH"; exit 1; }
[ -f "$VALUES" ] || { echo "ERROR: values file not found: $VALUES"; exit 1; }

echo "==> [read-only] ingress ELB hostname from svc/${SVC} in ns/${NS}"
ELB_DNS="$(kubectl -n "$NS" get svc "$SVC" \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
[ -n "$ELB_DNS" ] || {
  echo "ERROR: no LoadBalancer hostname on svc/${SVC} — is the ELB provisioned yet?"
  echo "       check: kubectl -n ${NS} get svc ${SVC}"
  exit 1
}
echo "    ELB DNS : $ELB_DNS"

echo "==> [read-only] resolving its current public IP (dig)"
# The NLB publishes one static A record per AZ (2 here); pin the first (any is a valid
# entry point to the LB). NLB IPs are stable for the life of the LB, but a platform
# rebuild creates a brand-new LB with new IPs, so re-run this on each rebuild.
IP="$(dig +short "$ELB_DNS" A | grep -E '^[0-9]+(\.[0-9]+){3}$' | sort | head -n1 || true)"
[ -n "$IP" ] || { echo "ERROR: could not resolve an A record for $ELB_DNS (DNS not propagated yet?)"; exit 1; }
echo "    IP      : $IP"

APP_HOST="app.${IP}.sslip.io"
API_HOST="api.${IP}.sslip.io"
echo "==> computed hosts:"
echo "    FE  : https://${APP_HOST}"
echo "    API : https://${API_HOST}"

echo "==> rewriting global.sslipIp in charts/modelmatch/values.yaml"
grep -qE '^[[:space:]]*sslipIp:' "$VALUES" || { echo "ERROR: no 'sslipIp:' key in $VALUES"; exit 1; }
# Portable in-place edit (works with both BSD/macOS and GNU sed): write to a temp file,
# then move it back. Matches only the single source-of-truth line under global.
tmp="$(mktemp)"
sed -E "s|^([[:space:]]*sslipIp:[[:space:]]*).*$|\1\"${IP}\"|" "$VALUES" > "$tmp"
mv "$tmp" "$VALUES"
echo "    set global.sslipIp = \"$IP\""

cat <<EOF

==> Done — only the local file changed. Next (manual, reviewable):
  1. Review:  git -C "${REPO_ROOT}" diff charts/modelmatch/values.yaml
  2. Commit:  git -C "${REPO_ROOT}" commit -am "chore(ingress): recompute sslip.io host -> ${IP}"
  3. Push:    git -C "${REPO_ROOT}" push        # ArgoCD auto-syncs the modelmatch app
  4. Watch the cert issue:
       kubectl -n app get ingress,certificate,order,challenge
  5. Verify HTTPS (-k while on the LE STAGING issuer; drop -k once on prod):
       curl -kI https://${APP_HOST}/          # frontend
       curl -k  https://${API_HOST}/healthz   # backend
EOF
