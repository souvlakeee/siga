#!/bin/sh
# tool: pv
# needs: pv
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
make_tree "$WORK" 1 40; cd "$WORK"
# >>> readme
pbar run -- sh -c 'pv -f -i 0.5 -L 8m f1.bin > copy.bin'
# <<< readme
