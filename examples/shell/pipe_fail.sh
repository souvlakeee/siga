#!/bin/sh
# tool: a failing piped command ends red, with its own exit code
# needs: sh
# expect: updates>=3 final=fail max>=0.4
. "$(dirname "$0")/../_lib.sh"
build() { for i in $(seq 1 10); do echo "[$i/20] compiling"; sleep 0.1; done; echo "error: boom" >&2; return 3; }
set +e   # _lib.sh runs with set -e; a README reader's shell does not
# >>> readme
set -o pipefail
build 2>&1 | siga pipe; siga end $?   # exits 3, bar ends red
# <<< readme
[ $? -eq 3 ]
