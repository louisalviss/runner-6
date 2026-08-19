#!/usr/bin/env bash
set -euo pipefail

URL="${1:-}"
LABEL="${2:-}"

if [ -z "$URL" ]; then
  echo 'usage: dsh-request-audio.sh <url> [label]' >&2
  exit 2
fi
case "$URL" in
  http://*|https://*) ;;
  *) echo 'only http/https URLs are accepted' >&2; exit 2 ;;
esac

# Reuse the existing worker request schema. The internal fragment is stripped by
# dsh-download-media.sh before yt-dlp sees the URL and switches the worker to
# bestaudio-only mode without changing the production workflow contract.
AUDIO_URL="${URL}#dsh-audio"
python - "$AUDIO_URL" "$LABEL" <<'PY'
import json, sys
from pathlib import Path
url, label = sys.argv[1], sys.argv[2]
req = {
    'v': 1,
    'action': 'download_media',
    'url': url,
    'max_height': 720,
    'label': label[:200],
}
Path('.dsh-download-request.json').write_text(
    json.dumps(req, ensure_ascii=False, separators=(',', ':')),
    encoding='utf-8'
)
PY

printf 'Audio download queued: %s\n' "$URL"
printf 'Runner handoff request: .dsh-download-request.json\n'
