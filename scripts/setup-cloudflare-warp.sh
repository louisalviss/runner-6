#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

if ! command -v warp-cli >/dev/null 2>&1; then
  curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg \
    | sudo gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
  . /etc/os-release
  echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ ${VERSION_CODENAME} main" \
    | sudo tee /etc/apt/sources.list.d/cloudflare-client.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq cloudflare-warp
fi

sudo systemctl start warp-svc || true

# GitHub-hosted jobs may call this helper multiple times in the same VM.
# Always clear a previous disconnected consumer registration before creating
# the next ephemeral one; otherwise warp-cli exits with "Old registration is
# still around" on the second media download.
warp-cli --accept-tos disconnect >/dev/null 2>&1 || true
warp-cli --accept-tos registration delete >/dev/null 2>&1 || true
sleep 1

set +e
warp-cli --accept-tos registration new >/tmp/warp-register.log 2>&1
REG=$?
set -e
if [ "$REG" -ne 0 ]; then
  cat /tmp/warp-register.log >&2
  exit "$REG"
fi
rm -f /tmp/warp-register.log

warp-cli --accept-tos mode warp >/dev/null 2>&1 || true
warp-cli --accept-tos connect >/dev/null

for _ in $(seq 1 20); do
  TRACE="$(curl -fsS --max-time 5 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null || true)"
  if printf '%s\n' "$TRACE" | grep -q '^warp=on$'; then
    printf '%s\n' "$TRACE" | grep -E '^(ip|colo|warp)='
    exit 0
  fi
  sleep 1
done

echo 'WARP failed to reach warp=on' >&2
warp-cli --accept-tos status >&2 || true
exit 1
