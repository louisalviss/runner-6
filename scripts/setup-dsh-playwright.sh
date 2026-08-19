#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-$PWD}"
PW_VERSION="${PLAYWRIGHT_MCP_VERSION:-0.0.78}"
PW_ROOT="$RUNNER_TEMP/playwright-mcp"

mkdir -p "$PW_ROOT" "$DSH_HOME/profiles/headless" "$WORKSPACE/dsh-handoff/browser"

npm install --prefix "$PW_ROOT" --no-audit --no-fund "@playwright/mcp@$PW_VERSION"
node "$PW_ROOT/node_modules/playwright/cli.js" install-deps chromium
node "$PW_ROOT/node_modules/playwright/cli.js" install chromium

test -f "$PW_ROOT/node_modules/@playwright/mcp/cli.js"
PLAYWRIGHT_MCP_CLI="$PW_ROOT/node_modules/@playwright/mcp/cli.js"
echo "PLAYWRIGHT_MCP_CLI=$PLAYWRIGHT_MCP_CLI" >> "$GITHUB_ENV"

cat > "$DSH_HOME/profiles/headless/cordis.patch.yml" <<'YAML'
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
          - chromium
          - --no-sandbox
          - --output-dir
          - !!js process.getBuiltinModule('node:path').join(process.cwd(), 'dsh-handoff', 'browser')
        cwd: !!js process.cwd()
        env: {}
        toolCallTimeoutMs: 90000
        failOnStartupError: true
YAML

printf 'Playwright MCP %s configured for DSH headless profile.\n' "$PW_VERSION"
