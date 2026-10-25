#!/bin/sh
# tool: OSC 9;4 from a shell script (the standard progress escape)
# needs: sh
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
# >>> readme
work() {
    for i in $(seq 0 5 100); do
        printf '\033]9;4;1;%d\033\\' "$i"   # ESC ] 9;4;1;<percent> ST
        sleep 0.2
    done
    printf '\033]9;4;0\033\\'               # clear
}
set -o pipefail
work | pbar pipe; pbar end $?
# <<< readme
