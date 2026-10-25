#!/bin/sh
# tool: vbauerster/mpb (Go, --pty)
# needs: go
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/go/mpb"; [ -x demo ] || go build -o demo .
# >>> readme
siga run --pty -- ./demo
# <<< readme
