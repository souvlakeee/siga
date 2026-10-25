#!/bin/sh
# tool: docker build (BuildKit)
# needs: docker docker-daemon
# expect: updates>=4 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$WORK"; printf 'FROM busybox\nRUN sleep 1 && echo %s\nRUN sleep 1\nRUN sleep 1\nRUN sleep 1\nRUN sleep 1\n' "$(date +%s%N)" > Dockerfile
# >>> readme
pbar run -- docker build --progress=plain --no-cache -t pbar-demo .
# <<< readme
