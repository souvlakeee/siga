#!/bin/sh
# tool: curl -# (progress bar style)
# needs: curl
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
URL=$(serve_file 40); cd "$WORK"
# >>> readme
siga run -- curl -# --limit-rate 8M -o big.bin "$URL"
# <<< readme
