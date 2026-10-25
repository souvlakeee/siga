#!/bin/sh
# tool: git clone
# needs: git
# expect: updates>=2 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$WORK"; git init -q --bare origin.git
git init -q seed && (cd seed && for i in $(seq 1 400); do head -c 20000 /dev/urandom > "f$i"; done \
  && git add . && git -c user.email=a@b -c user.name=pbar commit -qm seed && git push -q ../origin.git HEAD:main)
# >>> readme
pbar run -- git clone --progress "file://$WORK/origin.git" copy
# <<< readme
