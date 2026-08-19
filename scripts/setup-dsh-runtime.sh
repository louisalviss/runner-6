#!/usr/bin/env bash
set -euo pipefail

DSH_VER="${DSH_VERSION:-0.1.0-rc.7}"
PW_VER="${PLAYWRIGHT_MCP_VERSION:-0.0.78}"
ROOT="${DSH_RUNTIME_ROOT:-$HOME/.cache/runner6-dsh-runtime/rc7-pwmcp078}"
STAMP="$ROOT/.versions"
WANT="dsh=$DSH_VER playwright-mcp=$PW_VER"

if [ ! -x "$ROOT/node_modules/.bin/dsh" ] || [ ! -f "$ROOT/node_modules/@playwright/mcp/cli.js" ] || [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$WANT" ]; then
  rm -rf "$ROOT"
  mkdir -p "$ROOT"
  npm install --prefix "$ROOT" --no-audit --no-fund \
    "@deepseek-ai/dsh@$DSH_VER" \
    "@playwright/mcp@$PW_VER"
  printf '%s' "$WANT" > "$STAMP"
fi

test -x "$ROOT/node_modules/.bin/dsh"
test -f "$ROOT/node_modules/@playwright/mcp/cli.js"

echo "DSH_BIN=$ROOT/node_modules/.bin/dsh" >> "$GITHUB_ENV"
echo "PLAYWRIGHT_MCP_CLI=$ROOT/node_modules/@playwright/mcp/cli.js" >> "$GITHUB_ENV"
echo "DSH_RUNTIME_ROOT=$ROOT" >> "$GITHUB_ENV"
printf 'DSH runtime ready: %s\n' "$WANT"
