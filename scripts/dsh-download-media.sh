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

mkdir -p dsh-handoff/downloads

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
  --retries 3
  --fragment-retries 3
  --max-filesize 250M
  -P dsh-handoff/downloads
  -o '%(title).100s_[%(id)s].%(ext)s'
  --print 'after_move:filepath'
)
FORMAT="best[height<=${HEIGHT}][ext=mp4]/best[height<=${HEIGHT}]/best"

set +e
OUT="$(timeout --signal=TERM --kill-after=5s 150s "$YTDLP" "${COMMON[@]}" -f "$FORMAT" "$URL")"
CODE=$?
set -e

# YouTube can intermittently require a different public client because of
# GVS/PO-token enforcement. Retry once with web_safari, whose HLS path may
# remain available for public videos, then stop rather than looping.
if [ "$CODE" -ne 0 ] && [[ "$URL" == *youtube.com* || "$URL" == *youtu.be* ]]; then
  set +e
  OUT="$(timeout --signal=TERM --kill-after=5s 150s "$YTDLP" "${COMMON[@]}" \
    --extractor-args 'youtube:player_client=web_safari' \
    -f "best[height<=${HEIGHT}]/best" "$URL")"
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

REL="${FINAL#./}"
BYTES="$(stat -c '%s' "$FINAL")"

python - "$URL" "$REL" "$BYTES" "$HEIGHT" <<'PY'
import json, sys
from pathlib import Path
url, rel, size, height = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
p = Path('dsh-handoff/handoff.json')
data = {'source_url': url, 'relative_path': rel, 'bytes': size, 'max_height': height}
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
PY

printf 'Source: %s\n' "$URL"
printf 'Saved: %s\n' "$REL"
printf 'Bytes: %s\n' "$BYTES"
