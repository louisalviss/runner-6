#!/usr/bin/env bash
set -euo pipefail

SEARCH="${1:-}"
if [ -z "$SEARCH" ]; then
  echo 'usage: dsh-download-audio-search.sh <search-query-or-ytsearch-url>' >&2
  exit 2
fi

case "$SEARCH" in
  ytsearch*:*) URL="$SEARCH" ;;
  *) URL="ytsearch1:$SEARCH" ;;
esac

mkdir -p dsh-handoff/downloads
YTDLP="$HOME/.local/bin/yt-dlp"
if [ ! -x "$YTDLP" ]; then
  bash scripts/setup-dsh-media-tools.sh
fi
[ -x "$YTDLP" ] || { echo 'yt-dlp setup failed' >&2; exit 3; }

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
FORMAT='bestaudio[ext=m4a]/bestaudio'

run_once() {
  local out code
  set +e
  out="$(timeout --signal=TERM --kill-after=5s 120s "$YTDLP" "${COMMON[@]}" "$@" -f "$FORMAT" "$URL")"
  code=$?
  set -e
  if [ "$code" -eq 0 ]; then
    local candidate
    candidate="$(printf '%s\n' "$out" | sed '/^[[:space:]]*$/d' | tail -n 1)"
    if [ -n "$candidate" ] && [ -s "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  return 1
}

FINAL=''
if FINAL="$(run_once)"; then
  echo 'DSH audio search resolved on direct egress.' >&2
else
  echo 'Direct audio search blocked; switching DSH media egress through Cloudflare WARP.' >&2
  WARP_CONNECTED=0
  set +e
  bash scripts/setup-cloudflare-warp.sh >&2
  WARP_CODE=$?
  set -e
  if [ "$WARP_CODE" -eq 0 ]; then
    WARP_CONNECTED=1
    if FINAL="$(run_once)"; then
      :
    elif FINAL="$(run_once --extractor-args 'youtube:player_client=web_safari')"; then
      :
    else
      FINAL=''
    fi
  fi
  if [ "$WARP_CONNECTED" -eq 1 ]; then
    warp-cli --accept-tos disconnect >/dev/null 2>&1 || true
  fi
fi

if [ -z "$FINAL" ] || [ ! -s "$FINAL" ]; then
  echo 'WARP audio search still blocked; trying isolated VPNGate relay worker.' >&2
  set +e
  FINAL="$(YTDLP_BIN="$YTDLP" DSH_MEDIA_MODE=audio bash scripts/dsh-ytdlp-vpngate.sh "$URL" 720)"
  CODE=$?
  set -e
  if [ "$CODE" -ne 0 ]; then
    echo "DSH audio search failed with exit code $CODE" >&2
    exit "$CODE"
  fi
fi

if [ -z "$FINAL" ] || [ ! -f "$FINAL" ] || [ ! -s "$FINAL" ]; then
  echo 'audio search returned success but no non-empty final file was found' >&2
  exit 4
fi
if ! ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate -of json "$FINAL" >/dev/null 2>&1; then
  echo 'audio search returned a non-audio payload' >&2
  exit 4
fi

ABS="$(realpath "$FINAL")"
ROOT="$(realpath "$PWD")"
case "$ABS" in
  "$ROOT"/*) REL="${ABS#"$ROOT"/}" ;;
  *) echo 'downloaded file escaped the workspace' >&2; exit 5 ;;
esac
BYTES="$(stat -c '%s' "$ABS")"
python - "$SEARCH" "$REL" "$BYTES" <<'PY'
import json, sys
from pathlib import Path
source, rel, size = sys.argv[1], sys.argv[2], int(sys.argv[3])
Path('dsh-handoff/handoff.json').write_text(json.dumps({
    'source_url': source,
    'relative_path': rel,
    'bytes': size,
    'max_height': 720,
    'media_type': 'audio',
    'resolver': 'dsh-search-direct-warp-vpngate'
}, ensure_ascii=False, indent=2), encoding='utf-8')
PY
printf 'Source search: %s\n' "$SEARCH"
printf 'Resolved input: %s\n' "$URL"
printf 'Saved: %s\n' "$REL"
printf 'Bytes: %s\n' "$BYTES"
printf 'Media type: audio\n'
