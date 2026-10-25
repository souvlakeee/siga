#!/bin/sh
# tool: tqdm
# needs: py:tqdm
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/python"
# >>> readme
siga run -- python tqdm_demo.py
# <<< readme
