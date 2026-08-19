#!/usr/bin/env bash
set -euo pipefail

URL="${1:-}"
HEIGHT="${2:-720}"
LABEL="${3:-}"

if [ -z "$URL" ]; then
  echo 'usage: dsh-request-download.sh <url> [max-height] [label]' >&2
  exit 2
fi
if ! [[ "$HEIGHT" =~ ^[0-9]{3,4}$ ]]; then
  echo 'max-height must be a number such as 360 or 720' >&2
  exit 2
fi
case "$URL" in
  http://*|https://*) ;;
  *) echo 'only http/https URLs are accepted' >&2; exit 2 ;;
esac

python - "$URL" "$HEIGHT" "$LABEL" <<'PY'
import json, sys
from pathlib import Path
url, height, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
req = {
    'v': 1,
    'action': 'download_media',
    'url': url,
    'max_height': height,
    'label': label[:200],
}
Path('.dsh-download-request.json').write_text(
    json.dumps(req, ensure_ascii=False, separators=(',', ':')),
    encoding='utf-8'
)
PY

printf 'Download queued: %s\n' "$URL"
printf 'Runner handoff request: .dsh-download-request.json\n'
