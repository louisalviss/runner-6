#!/usr/bin/env bash
set -euo pipefail

OLD_ROOT="$HOME/.cache/runner6-dsh-runtime/rc7-pwmcp078"
NEW_ROOT="$HOME/.cache/runner6-dsh-runtime/rc7-pwmcp078-pnpm"

install_cost_guard() {
  # OpenRouter bills every replayed prompt token. DSH's stock 0.8 compaction
  # threshold is far too late for million-token models, so compact before
  # tool loops grow into repeated 50k-150k prompts.
  if [ -n "${DSH_HOME:-}" ]; then
    mkdir -p "$DSH_HOME"
    cat > "$DSH_HOME/cordis.patch.yml" <<'YAML'
- id: compaction-basic
  disabled: false
  config:
    auto: true
    thresholdRatio: 0.06
    retainTokens: 12000
    maxTokens: 4096
    compactionRetries: 1
    maxOverflowRetries: 1
YAML
    chmod 600 "$DSH_HOME/cordis.patch.yml"
    echo 'Installed DSH cost guard: compact@6%, retain=12000, summary<=4096.'
  fi
}

activate_root() {
  local root="$1"
  test -x "$root/node_modules/.bin/dsh"
  test -f "$root/node_modules/@playwright/mcp/cli.js"
  echo "DSH_BIN=$root/node_modules/.bin/dsh" >> "$GITHUB_ENV"
  echo "PLAYWRIGHT_MCP_CLI=$root/node_modules/@playwright/mcp/cli.js" >> "$GITHUB_ENV"
  echo "DSH_RUNTIME_ROOT=$root" >> "$GITHUB_ENV"
  install_cost_guard
  printf 'Activated cached DSH runtime: %s\n' "$root"
}

if [ -x "$OLD_ROOT/node_modules/.bin/dsh" ] && [ -f "$OLD_ROOT/node_modules/@playwright/mcp/cli.js" ]; then
  activate_root "$OLD_ROOT"
elif [ -x "$NEW_ROOT/node_modules/.bin/dsh" ] && [ -f "$NEW_ROOT/node_modules/@playwright/mcp/cli.js" ]; then
  activate_root "$NEW_ROOT"
else
  echo 'No complete primed runtime found; using pnpm fallback.'
  bash "$(dirname "$0")/setup-dsh-runtime.sh"
  install_cost_guard
fi
