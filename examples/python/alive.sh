#!/bin/sh
# tool: alive-progress (--pty)
# needs: py:alive_progress
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/python"
# >>> readme
siga run --pty -- python alive_demo.py
# <<< readme
