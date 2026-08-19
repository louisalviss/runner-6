#!/usr/bin/env bash
set -euo pipefail

URL="${1:-}"
HEIGHT="${2:-720}"
MODE="${DSH_MEDIA_MODE:-video}"
if [ -z "$URL" ]; then
  echo 'usage: dsh-ytdlp-vpngate.sh <url> [max-height]' >&2
  exit 2
fi
case "$MODE" in video|audio) ;; *) echo 'invalid DSH_MEDIA_MODE' >&2; exit 2 ;; esac

YTDLP="${YTDLP_BIN:-$HOME/.local/bin/yt-dlp}"
NODE_BIN="$(command -v node || true)"
TIMEOUT_BIN="$(command -v timeout || true)"
if [ ! -x "$YTDLP" ] || [ -z "$NODE_BIN" ] || [ -z "$TIMEOUT_BIN" ]; then
  echo 'yt-dlp, node or timeout is missing before VPN fallback' >&2
  exit 3
fi

# Only the media subprocess is routed through a public relay namespace.
# DSH/OpenRouter/GitHub credential steps have already finished and no secrets
# are passed to this script. Package setup is also hard-bounded.
if ! command -v openvpn >/dev/null 2>&1; then
  echo 'Installing bounded OpenVPN dependency...' >&2
  sudo "$TIMEOUT_BIN" --signal=TERM --kill-after=5s 45s apt-get update -qq || true
  sudo "$TIMEOUT_BIN" --signal=TERM --kill-after=5s 75s apt-get install -y -qq openvpn >/dev/null
fi
command -v openvpn >/dev/null 2>&1 || { echo 'OpenVPN unavailable after bounded setup' >&2; exit 4; }
command -v ip >/dev/null 2>&1 || { echo 'iproute2 unavailable' >&2; exit 4; }
command -v iptables >/dev/null 2>&1 || { echo 'iptables unavailable' >&2; exit 4; }
command -v curl >/dev/null 2>&1 || { echo 'curl unavailable' >&2; exit 4; }

ROOT=/tmp/dsh-vpngate
POOL="$ROOT/pool"
rm -rf "$ROOT"
mkdir -p "$POOL"
curl -fsSL --connect-timeout 10 --max-time 30 'https://www.vpngate.net/api/iphone/' -o "$ROOT/vpngate.csv"

python3 - "$ROOT" <<'PY'
import base64,csv,io,pathlib,sys
root=pathlib.Path(sys.argv[1]); pool=root/'pool'
pref=['JP','KR','SG','US','CA','TH','MY','TW','VN','AU']
raw=(root/'vpngate.csv').read_text(encoding='utf-8-sig',errors='replace')
rows=list(csv.DictReader(io.StringIO('\n'.join(x for x in raw.splitlines() if x and not x.startswith('*')))))
(root/'auth').write_text('vpn\nvpn\n')
out=[]
for country in pref:
    rs=[r for r in rows if (r.get('CountryShort') or '').upper()==country and (r.get('OpenVPN_ConfigData_Base64') or '').strip()]
    rs.sort(key=lambda r:int(r.get('Speed') or 0),reverse=True)
    for r in rs[:1]:
        try: cfg=base64.b64decode(r['OpenVPN_ConfigData_Base64']).decode(errors='replace')
        except Exception: continue
        cfg='\n'.join('auth-user-pass '+str(root/'auth') if x.strip().startswith('auth-user-pass') else x for x in cfg.splitlines())+'\n'
        p=pool/f'{len(out):02d}-{country}.ovpn'; p.write_text(cfg)
        out.append((str(p),country,r.get('IP','')))
        if len(out)>=5: break
    if len(out)>=5: break
if not out: raise SystemExit('No VPNGate relays available')
(root/'relays.tsv').write_text('\n'.join('\t'.join(x for x in row) for row in out)+'\n')
print('RELAYS',len(out))
PY

IFACE="$(ip route show default | awk '{print $5; exit}')"
sudo ip netns del dshvpn 2>/dev/null || true
sudo ip netns add dshvpn
sudo ip link add dshvh type veth peer name dshvn
sudo ip link set dshvn netns dshvpn
sudo ip addr add 10.237.0.1/24 dev dshvh
sudo ip link set dshvh up
sudo ip netns exec dshvpn ip addr add 10.237.0.2/24 dev dshvn
sudo ip netns exec dshvpn ip link set lo up
sudo ip netns exec dshvpn ip link set dshvn up
sudo ip netns exec dshvpn ip route add default via 10.237.0.1
sudo sysctl -w net.ipv4.ip_forward=1 >/dev/null
sudo iptables -t nat -A POSTROUTING -s 10.237.0.0/24 -o "$IFACE" -j MASQUERADE
sudo iptables -A FORWARD -i dshvh -o "$IFACE" -j ACCEPT
sudo iptables -A FORWARD -i "$IFACE" -o dshvh -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo mkdir -p /etc/netns/dshvpn
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' | sudo tee /etc/netns/dshvpn/resolv.conf >/dev/null

mkdir -p dsh-handoff/downloads
if [ "$MODE" = audio ]; then
  FORMAT='bestaudio[ext=m4a]/bestaudio'
  HLS_FORMAT="$FORMAT"
else
  FORMAT="best[height<=${HEIGHT}][ext=mp4]/best[height<=${HEIGHT}]/best"
  HLS_FORMAT="best[height<=${HEIGHT}][protocol^=m3u8]/best[height<=${HEIGHT}]/best"
fi
: > "$ROOT/attempts.tsv"

run_in_vpn() {
  sudo ip netns exec dshvpn sudo -u "$USER" env HOME="$HOME" PATH="$PATH" "$@"
}

try_download() {
  local label="$1"; shift
  local fmt="$1"; shift
  local err="$ROOT/ytdlp-${label}.err"
  : > "$err"
  rm -f dsh-handoff/downloads/*.part dsh-handoff/downloads/*.ytdl 2>/dev/null || true
  set +e
  local out
  out="$(run_in_vpn "$TIMEOUT_BIN" --signal=TERM --kill-after=5s 75s \
    "$YTDLP" --js-runtimes "node:$NODE_BIN" --no-playlist --restrict-filenames \
    --socket-timeout 15 --retries 1 --fragment-retries 1 --max-filesize 250M \
    -P dsh-handoff/downloads -o '%(title).100s_[%(id)s].%(ext)s' \
    --print 'after_move:filepath' "$@" -f "$fmt" "$URL" 2>"$err")"
  local code=$?
  set -e
  printf '%s\t%s\n' "$label" "$code" >> "$ROOT/client-attempts.tsv"
  if [ "$code" -eq 0 ]; then
    local candidate
    candidate="$(printf '%s\n' "$out" | sed '/^[[:space:]]*$/d' | tail -n 1)"
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  tail -n 3 "$err" >&2 || true
  return 1
}

success=0
final=''
while IFS=$'\t' read -r cfg country relay; do
  echo "VPN_TRY country=$country relay=$relay mode=$MODE" >&2
  sudo ip netns exec dshvpn pkill openvpn 2>/dev/null || true
  sleep 1
  sudo rm -f "$ROOT/openvpn.log"
  sudo touch "$ROOT/openvpn.log" && sudo chmod 644 "$ROOT/openvpn.log"
  sudo ip netns exec dshvpn openvpn --config "$cfg" --daemon --log "$ROOT/openvpn.log" || true
  ready=0
  for _ in {1..10}; do
    sleep 1
    grep -q 'Initialization Sequence Completed' "$ROOT/openvpn.log" 2>/dev/null && { ready=1; break; }
    grep -Eq 'AUTH_FAILED|TLS Error|Connection timed out|Connection refused|fatal error' "$ROOT/openvpn.log" 2>/dev/null && break || true
  done
  if [ "$ready" != 1 ]; then
    printf '%s\t%s\tVPN_FAIL\n' "$country" "$relay" >> "$ROOT/attempts.tsv"
    continue
  fi

  exitip="$(sudo ip netns exec dshvpn curl -fsS --connect-timeout 5 --max-time 8 https://api.ipify.org || true)"
  ERR="$ROOT/ytdlp-probe.err"; : > "$ERR"

  set +e
  run_in_vpn "$TIMEOUT_BIN" --signal=TERM --kill-after=3s 25s \
    "$YTDLP" --js-runtimes "node:$NODE_BIN" --no-playlist --socket-timeout 10 \
    --retries 0 --simulate --print id "$URL" \
    >"$ROOT/probe.out" 2>"$ERR"
  probe=$?
  set -e
  if [ "$probe" -ne 0 ]; then
    printf '%s\t%s\t%s\tPROBE_%s\n' "$country" "$relay" "$exitip" "$probe" >> "$ROOT/attempts.tsv"
    tail -n 2 "$ERR" >&2 || true
    continue
  fi

  echo "VPN_PROBE_OK country=$country exit_ip=$exitip mode=$MODE" >&2
  : > "$ROOT/client-attempts.tsv"

  if final="$(try_download default "$FORMAT")"; then
    success=1
  elif final="$(try_download safari "$HLS_FORMAT" --extractor-args 'youtube:player_client=web_safari')"; then
    success=1
  elif final="$(try_download embedded "$FORMAT" --extractor-args 'youtube:player_client=web_embedded')"; then
    success=1
  fi

  if [ "$success" = 1 ]; then
    printf '%s\t%s\t%s\tDOWNLOAD_OK\n' "$country" "$relay" "$exitip" >> "$ROOT/attempts.tsv"
    echo "VPN_OK country=$country exit_ip=$exitip mode=$MODE" >&2
    break
  fi

  summary="$(tr '\n' ',' < "$ROOT/client-attempts.tsv" | sed 's/,$//')"
  printf '%s\t%s\t%s\tCLIENTS_%s\n' "$country" "$relay" "$exitip" "$summary" >> "$ROOT/attempts.tsv"
done < "$ROOT/relays.tsv"

sudo ip netns exec dshvpn pkill openvpn 2>/dev/null || true

if [ "$success" != 1 ]; then
  echo 'VPNGate downloader exhausted bounded relay/client pool' >&2
  cat "$ROOT/attempts.tsv" >&2
  exit 1
fi

printf '%s\n' "$final"
