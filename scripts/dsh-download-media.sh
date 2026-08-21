#!/usr/bin/env bash
set -euo pipefail

URL="${1:-}"
HEIGHT="${2:-720}"
if [ -z "$URL" ]; then
  echo 'usage: dsh-download-media.sh <url> [max-height]' >&2
  exit 2
fi
if ! [[ "$HEIGHT" =~ ^[0-9]{3,4}$ ]]; then
  echo 'max-height must be a number such as 360 or 720' >&2
  exit 2
fi

MODE=video
AUDIO_MARKER='#dsh-audio'
if [[ "$URL" == *"$AUDIO_MARKER" ]]; then
  MODE=audio
  URL="${URL%%$AUDIO_MARKER*}"
fi

mkdir -p dsh-handoff/downloads

write_handoff() {
  local source="$1" final="$2" mode="$3"
  local abs root rel bytes
  abs="$(realpath "$final")"
  root="$(realpath "$PWD")"
  case "$abs" in
    "$root"/*) rel="${abs#"$root"/}" ;;
    *) echo 'downloaded file escaped the workspace' >&2; exit 5 ;;
  esac
  bytes="$(stat -c '%s' "$abs")"
  python - "$source" "$rel" "$bytes" "$HEIGHT" "$mode" <<'PY'
import json, sys
from pathlib import Path
url, rel, size, height, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
p = Path('dsh-handoff/handoff.json')
p.write_text(json.dumps({'source_url':url,'relative_path':rel,'bytes':size,'max_height':height,'media_type':mode}, ensure_ascii=False, indent=2), encoding='utf-8')
PY
  printf 'Source: %s\n' "$source"
  printf 'Saved: %s\n' "$rel"
  printf 'Bytes: %s\n' "$bytes"
  printf 'Media type: %s\n' "$mode"
}

# TikTok/TikWM: resolve the current media URL through TikWM's JSON API first.
# Static /video/media/... guesses can expire or return 400/403 on hosted runners.
if [ "$MODE" = video ] && [[ "$URL" == *tiktok.com* || "$URL" == *tikwm.com/video/* ]]; then
  SOURCE="$URL"
  if [[ "$SOURCE" == *tikwm.com/video/* ]]; then
    ID="$(printf '%s' "$SOURCE" | sed -nE 's#.*?/video/([0-9]+).*#\1#p')"
    [ -n "$ID" ] && SOURCE="$ID"
  fi
  API_JSON="$(mktemp)"
  UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/136 Safari/537.36'
  tikwm_api() {
    curl -fsS --retry 2 --retry-delay 1 --max-time 45 \
      -A "$UA" -H 'Accept: application/json, text/plain, */*' \
      -X POST -d "url=$SOURCE" -d 'hd=1' \
      'https://www.tikwm.com/api/' -o "$API_JSON"
  }
  set +e
  tikwm_api
  API_CODE=$?
  set -e
  WARP_CONNECTED=0
  if [ "$API_CODE" -ne 0 ]; then
    echo 'TikWM API direct request blocked; retrying through Cloudflare WARP.' >&2
    set +e
    bash scripts/setup-cloudflare-warp.sh >&2
    WARP_CODE=$?
    set -e
    if [ "$WARP_CODE" -eq 0 ]; then
      WARP_CONNECTED=1
      set +e
      tikwm_api
      API_CODE=$?
      set -e
    fi
  fi
  if [ "$API_CODE" -ne 0 ]; then
    [ "$WARP_CONNECTED" -eq 1 ] && warp-cli --accept-tos disconnect >/dev/null 2>&1 || true
    echo 'TikWM API resolution failed.' >&2
    exit "$API_CODE"
  fi
  MEDIA_URL="$(python - "$API_JSON" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
if p.get('code') != 0 or not p.get('data'):
    raise SystemExit(2)
d=p['data']
u=d.get('hdplay') or d.get('play')
if not u:
    raise SystemExit(3)
if u.startswith('/'):
    u='https://www.tikwm.com'+u
print(u)
PY
  )"
  OUT="dsh-handoff/downloads/tiktok_$(date +%s%N).mp4"
  set +e
  curl -fL --retry 2 --retry-delay 1 --max-time 120 \
    -A "$UA" -e 'https://www.tikwm.com/' -H 'Accept: video/*,*/*;q=0.8' \
    "$MEDIA_URL" -o "$OUT"
  CODE=$?
  set -e
  [ "$WARP_CONNECTED" -eq 1 ] && warp-cli --accept-tos disconnect >/dev/null 2>&1 || true
  if [ "$CODE" -ne 0 ] || [ ! -s "$OUT" ]; then
    echo 'TikWM resolved media download failed.' >&2
    exit "${CODE:-1}"
  fi
  # Reject HTML/challenge bodies masquerading as media.
  if ! ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$OUT" >/dev/null 2>&1; then
    echo 'TikWM returned a non-video payload.' >&2
    exit 4
  fi
  write_handoff "$URL" "$OUT" video
  exit 0
fi

YTDLP="$HOME/.local/bin/yt-dlp"
if [ ! -x "$YTDLP" ]; then
  bash scripts/setup-dsh-media-tools.sh
fi
if [ ! -x "$YTDLP" ]; then
  echo 'yt-dlp setup failed' >&2
  exit 3
fi

COMMON=(
  --js-runtimes node
  --no-playlist
  --restrict-filenames
  --socket-timeout 20
  --retries 2
  --fragment-retries 2
  --max-filesize 250M
  -P dsh-handoff/downloads
  -o '%(title).100s_[%(id)s].%(ext)s'
  --print 'after_move:filepath'
)
VIDEO_FORMAT="best[height<=${HEIGHT}][ext=mp4]/best[height<=${HEIGHT}]/best"
AUDIO_FORMAT="bestaudio[ext=m4a]/bestaudio"

run_ytdlp() {
  timeout --signal=TERM --kill-after=5s 120s "$YTDLP" "${COMMON[@]}" "$@" "$URL"
}

try_public_clients() {
  local out code
  local format="$VIDEO_FORMAT"
  [ "$MODE" = audio ] && format="$AUDIO_FORMAT"
  set +e
  out="$(run_ytdlp -f "$format")"
  code=$?
  set -e
  if [ "$code" -ne 0 ] && [[ "$URL" == *youtube.com* || "$URL" == *youtu.be* ]]; then
    set +e
    out="$(run_ytdlp --extractor-args 'youtube:player_client=web_embedded,default' -f "$format")"
    code=$?
    set -e
  fi
  if [ "$code" -ne 0 ] && [[ "$URL" == *youtube.com* || "$URL" == *youtu.be* ]]; then
    set +e
    out="$(run_ytdlp --extractor-args 'youtube:player_client=web_safari' -f "$format")"
    code=$?
    set -e
  fi
  PUBLIC_OUT="$out"
  PUBLIC_CODE="$code"
}

PUBLIC_OUT=''
PUBLIC_CODE=1
try_public_clients
OUT="$PUBLIC_OUT"
CODE="$PUBLIC_CODE"

if [ "$CODE" -ne 0 ] && [[ "$URL" == *youtube.com* || "$URL" == *youtu.be* ]]; then
  echo 'Direct YouTube download blocked; switching media egress through Cloudflare WARP.' >&2
  WARP_CONNECTED=0
  set +e
  bash scripts/setup-cloudflare-warp.sh >&2
  WARP_CODE=$?
  set -e
  if [ "$WARP_CODE" -eq 0 ]; then
    WARP_CONNECTED=1
    try_public_clients
    OUT="$PUBLIC_OUT"
    CODE="$PUBLIC_CODE"
  fi
  if [ "$WARP_CONNECTED" -eq 1 ]; then
    warp-cli --accept-tos disconnect >/dev/null 2>&1 || true
  fi
fi

if [ "$CODE" -ne 0 ] && [[ "$URL" == *youtube.com* || "$URL" == *youtu.be* ]]; then
  echo 'WARP/public clients still blocked; trying isolated VPNGate relay worker.' >&2
  set +e
  OUT="$(YTDLP_BIN="$YTDLP" DSH_MEDIA_MODE="$MODE" bash scripts/dsh-ytdlp-vpngate.sh "$URL" "$HEIGHT")"
  CODE=$?
  set -e
fi

if [ "$CODE" -ne 0 ]; then
  echo "download failed with exit code $CODE" >&2
  exit "$CODE"
fi

FINAL="$(printf '%s\n' "$OUT" | sed '/^[[:space:]]*$/d' | tail -n 1)"
if [ -z "$FINAL" ] || [ ! -f "$FINAL" ] || [ ! -s "$FINAL" ]; then
  echo 'download command returned success but no non-empty final file was found' >&2
  exit 4
fi
write_handoff "$URL" "$FINAL" "$MODE"
