#!/bin/sh
# tool: rsync (3.1+, for --info=progress2; macOS ships openrsync: brew install rsync)
# needs: rsync
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
rsync --info=progress2 --version >/dev/null 2>&1 || skip "rsync without --info=progress2 (openrsync)"
make_tree "$WORK/src" 10 4; cd "$WORK"
# >>> readme
pbar run -- rsync -a --info=progress2 --bwlimit=8m src/ dst/
# <<< readme
