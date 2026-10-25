#!/bin/sh
# tool: any command, piped
# needs: sh
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
build() { for i in $(seq 1 20); do echo "[$i/20] compiling module_$i"; sleep 0.1; done; }
# >>> readme
set -o pipefail   # so $? is the tool's exit code, not pbar's
build 2>&1 | pbar pipe; pbar end $?
# <<< readme
