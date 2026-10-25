#!/bin/sh
# tool: cheggaaa/pb (Go, --pty)
# needs: go
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/go/pb"; [ -x demo ] || go build -o demo .
# >>> readme
siga run --pty -- ./demo
# <<< readme
