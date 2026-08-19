#!/usr/bin/env bash
set -euo pipefail

URL="${1:-}"
HEIGHT="${2:-720}"
if [ -z "$URL" ]; then
  echo 'usage: dsh-ytdlp-vpngate.sh <url> [max-height]' >&2
  exit 2
fi

YTDLP="${YTDLP_BIN:-$HOME/.local/bin/yt-dlp}"
NODE_BIN="$(command -v node || true)"
if [ ! -x "$YTDLP" ] || [ -z "$NODE_BIN" ]; then
  echo 'yt-dlp or node is missing before VPN fallback' >&2
  exit 3
fi

# Only the media downloader is routed through the public relay namespace.
# No GitHub/OpenRouter credentials are passed to this script.
sudo apt-get update -qq
sudo apt-get install -y -qq openvpn iproute2 iptables curl >/dev/null

ROOT=/tmp/dsh-vpngate
POOL="$ROOT/pool"
mkdir -p "$POOL"
curl -fsSL --connect-timeout 10 --max-time 30 'https://www.vpngate.net/api/iphone/' -o "$ROOT/vpngate.csv"

python3 - "$ROOT" <<'PY'
import base64,csv,io,pathlib,sys
root=pathlib.Path(sys.argv[1]); pool=root/'pool'
pref=['JP','KR','SG','TH','MY','PH','ID','TW','VN','US','CA','AU','DE','NL','GB','FR']
raw=(root/'vpngate.csv').read_text(encoding='utf-8-sig',errors='replace')
rows=list(csv.DictReader(io.StringIO('\n'.join(x for x in raw.splitlines() if x and not x.startswith('*')))))
(root/'auth').write_text('vpn\nvpn\n')
out=[]
for country in pref:
    rs=[r for r in rows if (r.get('CountryShort') or '').upper()==country and (r.get('OpenVPN_ConfigData_Base64') or '').strip()]
    rs.sort(key=lambda r:int(r.get('Speed') or 0),reverse=True)
    for r in rs[:2]:
        try: cfg=base64.b64decode(r['OpenVPN_ConfigData_Base64']).decode(errors='replace')
        except Exception: continue
        cfg='\n'.join('auth-user-pass '+str(root/'auth') if x.strip().startswith('auth-user-pass') else x for x in cfg.splitlines())+'\n'
        p=pool/f'{len(out):02d}-{country}.ovpn'; p.write_text(cfg)
        out.append((str(p),country,r.get('IP','')))
        if len(out)>=12: break
    if len(out)>=12: break
if not out: raise SystemExit('No VPNGate relays available')
(root/'relays.tsv').write_text('\n'.join('\t'.join(x) for x in out)+'\n')
print(len(out))
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
FORMAT="best[height<=${HEIGHT}][ext=mp4]/best[height<=${HEIGHT}]/best"
: > "$ROOT/attempts.tsv"

success=0
final=''
while IFS=$'\t' read -r cfg country relay; do
  echo "VPN_TRY country=$country relay=$relay" >&2
  sudo ip netns exec dshvpn pkill openvpn 2>/dev/null || true
  sleep 1
  sudo rm -f "$ROOT/openvpn.log"
  sudo touch "$ROOT/openvpn.log" && sudo chmod 644 "$ROOT/openvpn.log"
  sudo ip netns exec dshvpn openvpn --config "$cfg" --daemon --log "$ROOT/openvpn.log" || true
  ready=0
  for _ in {1..12}; do
    sleep 1
    grep -q 'Initialization Sequence Completed' "$ROOT/openvpn.log" 2>/dev/null && { ready=1; break; }
    grep -Eq 'AUTH_FAILED|TLS Error|Connection timed out|Connection refused|fatal error' "$ROOT/openvpn.log" 2>/dev/null && break || true
  done
  if [ "$ready" != 1 ]; then
    printf '%s\t%s\tVPN_FAIL\n' "$country" "$relay" >> "$ROOT/attempts.tsv"
    continue
  fi

  exitip="$(sudo ip netns exec dshvpn curl -fsS --connect-timeout 7 --max-time 10 https://api.ipify.org || true)"
  rm -f dsh-handoff/downloads/*.part dsh-handoff/downloads/*.ytdl 2>/dev/null || true
  ERR="$ROOT/ytdlp.err"
  : > "$ERR"
  set +e
  OUT="$(sudo ip netns exec dshvpn sudo -u "$USER" env HOME="$HOME" PATH="$PATH" \
    "$YTDLP" --js-runtimes "node:$NODE_BIN" --no-playlist --restrict-filenames \
    --socket-timeout 15 --retries 1 --fragment-retries 1 --max-filesize 250M \
    -P dsh-handoff/downloads -o '%(title).100s_[%(id)s].%(ext)s' \
    --print 'after_move:filepath' -f "$FORMAT" "$URL" 2>"$ERR")"
  code=$?
  set -e
  printf '%s\t%s\t%s\t%s\n' "$country" "$relay" "$exitip" "$code" >> "$ROOT/attempts.tsv"
  if [ "$code" -eq 0 ]; then
    candidate="$(printf '%s\n' "$OUT" | sed '/^[[:space:]]*$/d' | tail -n 1)"
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      final="$candidate"; success=1
      echo "VPN_OK country=$country exit_ip=$exitip" >&2
      break
    fi
  fi
  tail -n 3 "$ERR" >&2 || true
done < "$ROOT/relays.tsv"

sudo ip netns exec dshvpn pkill openvpn 2>/dev/null || true

if [ "$success" != 1 ]; then
  echo 'VPNGate downloader exhausted relay pool' >&2
  cat "$ROOT/attempts.tsv" >&2
  exit 1
fi

printf '%s\n' "$final"
