#!/bin/sh
# tool: click.progressbar (--pty)
# needs: py:click
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/python"
# >>> readme
siga run --pty -- python click_demo.py
# <<< readme
