#!/bin/sh
# tool: rich, exact values via --shim
# needs: py:rich
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/python"
# >>> readme
pbar run --shim -- python rich_demo.py
# <<< readme
