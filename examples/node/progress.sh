#!/bin/sh
# tool: progress (draws only on a terminal: --pty)
# needs: node
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/node"; [ -d node_modules ] || npm install --silent --no-audit --no-fund >/dev/null 2>&1
# >>> readme
siga run --pty -- node progress_demo.js
# <<< readme
