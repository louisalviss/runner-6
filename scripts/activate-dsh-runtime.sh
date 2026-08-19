#!/usr/bin/env bash
set -euo pipefail

OLD_ROOT="$HOME/.cache/runner6-dsh-runtime/rc7-pwmcp078"
NEW_ROOT="$HOME/.cache/runner6-dsh-runtime/rc7-pwmcp078-pnpm"

activate_root() {
  local root="$1"
  test -x "$root/node_modules/.bin/dsh"
  test -f "$root/node_modules/@playwright/mcp/cli.js"
  echo "DSH_BIN=$root/node_modules/.bin/dsh" >> "$GITHUB_ENV"
  echo "PLAYWRIGHT_MCP_CLI=$root/node_modules/@playwright/mcp/cli.js" >> "$GITHUB_ENV"
  echo "DSH_RUNTIME_ROOT=$root" >> "$GITHUB_ENV"
  printf 'Activated cached DSH runtime: %s\n' "$root"
}

if [ -x "$OLD_ROOT/node_modules/.bin/dsh" ] && [ -f "$OLD_ROOT/node_modules/@playwright/mcp/cli.js" ]; then
  activate_root "$OLD_ROOT"
elif [ -x "$NEW_ROOT/node_modules/.bin/dsh" ] && [ -f "$NEW_ROOT/node_modules/@playwright/mcp/cli.js" ]; then
  activate_root "$NEW_ROOT"
else
  echo 'No complete primed runtime found; using pnpm fallback.'
  bash "$(dirname "$0")/setup-dsh-runtime.sh"
fi
