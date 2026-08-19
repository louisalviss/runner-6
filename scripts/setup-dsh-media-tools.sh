#!/usr/bin/env bash
set -euo pipefail

CACHE_DIR="$HOME/.cache/runner6-media-tools"
BIN="$CACHE_DIR/yt-dlp"
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$CACHE_DIR" "$LOCAL_BIN"

if [ ! -x "$BIN" ]; then
  TMP="$BIN.tmp.$$"
  curl -fL --retry 3 --retry-delay 2 \
    https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o "$TMP"
  chmod 755 "$TMP"
  mv "$TMP" "$BIN"
fi

ln -sf "$BIN" "$LOCAL_BIN/yt-dlp"
printf '%s\n' "$LOCAL_BIN" >> "$GITHUB_PATH"
printf 'YTDLP_BIN=%s\n' "$LOCAL_BIN/yt-dlp" >> "$GITHUB_ENV"

"$BIN" --version
node --version
