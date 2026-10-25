#!/bin/sh
# tool: cli-progress, exact values via --shim (with --pty: it only counts on a terminal)
# needs: node
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/node"; [ -d node_modules ] || npm install --silent --no-audit --no-fund >/dev/null 2>&1
# >>> readme
siga run --pty --shim -- node cli_progress_demo.js   # cli-progress only counts on a terminal
# <<< readme
