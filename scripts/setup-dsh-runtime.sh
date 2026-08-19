#!/usr/bin/env bash
set -euo pipefail

DSH_VER="${DSH_VERSION:-0.1.0-rc.7}"
PW_VER="${PLAYWRIGHT_MCP_VERSION:-0.0.78}"
PNPM_VER="${PNPM_VERSION:-11.7.0}"
ROOT="${DSH_RUNTIME_ROOT:-$HOME/.cache/runner6-dsh-runtime/rc7-pwmcp078-pnpm}"
STORE="${PNPM_STORE_DIR:-$HOME/.cache/runner6-pnpm-store}"
STAMP="$ROOT/.versions"
WANT="dsh=$DSH_VER playwright-mcp=$PW_VER pnpm=$PNPM_VER"

export COREPACK_HOME="${COREPACK_HOME:-$HOME/.cache/corepack}"
corepack enable
corepack prepare "pnpm@$PNPM_VER" --activate
pnpm --version

if [ ! -x "$ROOT/node_modules/.bin/dsh" ] || [ ! -f "$ROOT/node_modules/@playwright/mcp/cli.js" ] || [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$WANT" ]; then
  rm -rf "$ROOT"
  mkdir -p "$ROOT" "$STORE"
  cat > "$ROOT/package.json" <<'JSON'
{
  "private": true,
  "name": "runner6-dsh-runtime",
  "version": "1.0.0",
  "pnpm": {
    "onlyBuiltDependencies": [
      "@deepseek-ai/dsh-subprocess-local",
      "@google/genai",
      "koffi",
      "node-pty",
      "protobufjs"
    ]
  }
}
JSON
  pnpm --dir "$ROOT" --store-dir "$STORE" add --prod \
    "@deepseek-ai/dsh@$DSH_VER" \
    "@playwright/mcp@$PW_VER"
  printf '%s' "$WANT" > "$STAMP"
fi

test -x "$ROOT/node_modules/.bin/dsh"
test -f "$ROOT/node_modules/@playwright/mcp/cli.js"

echo "DSH_BIN=$ROOT/node_modules/.bin/dsh" >> "$GITHUB_ENV"
echo "PLAYWRIGHT_MCP_CLI=$ROOT/node_modules/@playwright/mcp/cli.js" >> "$GITHUB_ENV"
echo "DSH_RUNTIME_ROOT=$ROOT" >> "$GITHUB_ENV"
echo "PNPM_STORE_DIR=$STORE" >> "$GITHUB_ENV"
printf 'DSH runtime ready: %s\n' "$WANT"
