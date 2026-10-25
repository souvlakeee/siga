#!/bin/sh
# tool: make (no progress output: learned ETA from the previous run)
# needs: make
# expect: updates>=5 final=done max>=0.75
. "$(dirname "$0")/../_lib.sh"
cd "$WORK"; printf 'all:\n\t@sleep 3\n\t@echo built\n' > Makefile
pbar run -- make >/dev/null   # first run: busy sweep, pbar learns how long `make` takes here
# >>> readme
pbar run -- make   # every later run fills by that learned duration
# <<< readme
