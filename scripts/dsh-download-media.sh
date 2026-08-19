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

YTDLP="$HOME/.local/bin/yt-dlp"
if [ ! -x "$YTDLP" ] || { [ "$MODE" = audio ] && ! command -v ffmpeg >/dev/null 2>&1; }; then
  bash scripts/setup-dsh-media-tools.sh
fi
if [ ! -x "$YTDLP" ]; then
  echo 'yt-dlp setup failed' >&2
  exit 3
fi
if [ "$MODE" = audio ] && ! command -v ffmpeg >/dev/null 2>&1; then
  echo 'ffmpeg is required for MP3 audio mode' >&2
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
AUDIO_FORMAT="bestaudio/best"

run_ytdlp() {
  timeout --signal=TERM --kill-after=5s 120s "$YTDLP" "${COMMON[@]}" "$@" "$URL"
}

run_mode_download() {
  local format="$1"; shift
  if [ "$MODE" = audio ]; then
    run_ytdlp --extract-audio --audio-format mp3 --audio-quality 0 "$@" -f "$format"
  else
    run_ytdlp "$@" -f "$format"
  fi
}

try_public_clients() {
  local out code
  local format="$VIDEO_FORMAT"
  [ "$MODE" = audio ] && format="$AUDIO_FORMAT"

  set +e
  out="$(run_mode_download "$format")"
  code=$?
  set -e

  if [ "$code" -ne 0 ] && [[ "$URL" == *youtube.com* || "$URL" == *youtu.be* ]]; then
    set +e
    out="$(run_mode_download "$format" --extractor-args 'youtube:player_client=web_embedded,default')"
    code=$?
    set -e
  fi

  if [ "$code" -ne 0 ] && [[ "$URL" == *youtube.com* || "$URL" == *youtu.be* ]]; then
    set +e
    out="$(run_mode_download "$format" --extractor-args 'youtube:player_client=web_safari')"
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

# GitHub-hosted Azure egress is often challenged by YouTube. For YouTube only,
# retry the same bounded public-client chain after switching the runner egress
# through Cloudflare WARP. WARP is connected only after the DSH/OpenRouter brain
# step has finished; disconnect immediately after the media attempt.
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

# Final fallback: isolated VPNGate rotation pattern from runner-7. Only the
# media subprocess enters the public relay namespace; no model/GitHub secrets
# are passed to it.
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
if [ "$MODE" = audio ] && [[ "${FINAL,,}" != *.mp3 ]]; then
  echo "audio mode returned non-MP3 output: $FINAL" >&2
  exit 4
fi

ABS="$(realpath "$FINAL")"
ROOT="$(realpath "$PWD")"
case "$ABS" in
  "$ROOT"/*) REL="${ABS#"$ROOT"/}" ;;
  *) echo 'downloaded file escaped the workspace' >&2; exit 5 ;;
esac
BYTES="$(stat -c '%s' "$ABS")"

python - "$URL" "$REL" "$BYTES" "$HEIGHT" "$MODE" <<'PY'
import json, sys
from pathlib import Path
url, rel, size, height, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
p = Path('dsh-handoff/handoff.json')
data = {
    'source_url': url,
    'relative_path': rel,
    'bytes': size,
    'max_height': height,
    'media_type': mode,
    'output_format': 'mp3' if mode == 'audio' else Path(rel).suffix.lower().lstrip('.'),
}
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
PY

printf 'Source: %s\n' "$URL"
printf 'Saved: %s\n' "$REL"
printf 'Bytes: %s\n' "$BYTES"
printf 'Media type: %s\n' "$MODE"
