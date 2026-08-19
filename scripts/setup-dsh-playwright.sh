#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-$PWD}"
PW_VERSION="${PLAYWRIGHT_MCP_VERSION:-0.0.78}"
PATCH_FILE="$DSH_HOME/cordis.patch.yml"

mkdir -p "$DSH_HOME" "$WORKSPACE/dsh-handoff/browser"

if [ -z "${PLAYWRIGHT_MCP_CLI:-}" ]; then
  PW_ROOT="$RUNNER_TEMP/playwright-mcp"
  mkdir -p "$PW_ROOT"
  npm install --prefix "$PW_ROOT" --no-audit --no-fund "@playwright/mcp@$PW_VERSION"
  PLAYWRIGHT_MCP_CLI="$PW_ROOT/node_modules/@playwright/mcp/cli.js"
  echo "PLAYWRIGHT_MCP_CLI=$PLAYWRIGHT_MCP_CLI" >> "$GITHUB_ENV"
fi

test -f "$PLAYWRIGHT_MCP_CLI"
command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1

cat > "$PATCH_FILE" <<'YAML'
- insert:
    - id: browser-playwright-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: browser
        transport: stdio
        command: node
        args:
          - !!js process.env.PLAYWRIGHT_MCP_CLI
          - --headless
          - --browser
          - chrome
          - --no-sandbox
          - --output-dir
          - !!js process.getBuiltinModule('node:path').join(process.cwd(), 'dsh-handoff', 'browser')
        cwd: !!js process.cwd()
        env: {}
        toolCallTimeoutMs: 90000
        failOnStartupError: true
YAML

printf 'Playwright MCP %s ready with preinstalled Chrome via %s\n' "$PW_VERSION" "$PATCH_FILE"
