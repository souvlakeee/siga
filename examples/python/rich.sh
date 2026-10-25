#!/bin/sh
# tool: rich (draws only on a terminal: --pty)
# needs: py:rich
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/python"
# >>> readme
siga run --pty -- python rich_demo.py
# <<< readme
