#!/bin/sh
# tool: cli-progress, exact values via --shim
# needs: node
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/node"
# >>> readme
pbar run --shim -- node cli_progress_demo.js
# <<< readme
