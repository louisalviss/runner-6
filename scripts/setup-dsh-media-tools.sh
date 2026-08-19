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

if ! command -v ffmpeg >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq ffmpeg >/dev/null
fi
command -v ffmpeg >/dev/null 2>&1 || { echo 'ffmpeg setup failed' >&2; exit 3; }

"$BIN" --version
ffmpeg -version | head -n 1
node --version
