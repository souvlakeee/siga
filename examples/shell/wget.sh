#!/bin/sh
# tool: wget
# needs: wget
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
URL=$(serve_file 40); cd "$WORK"
# >>> readme
siga run -- wget --limit-rate=8m --progress=bar:force -O big.bin "$URL"
# <<< readme
