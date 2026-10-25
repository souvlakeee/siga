#!/bin/sh
# tool: schollz/progressbar (Go, --pty)
# needs: go
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/go/schollz"; [ -x demo ] || go build -o demo .
# >>> readme
pbar run --pty -- ./demo
# <<< readme
