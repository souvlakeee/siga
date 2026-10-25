#!/bin/sh
# tool: progress (draws only on a terminal: --pty)
# needs: node
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/node"
# >>> readme
pbar run --pty -- node progress_demo.js
# <<< readme
