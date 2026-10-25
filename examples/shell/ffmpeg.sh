#!/bin/sh
# tool: ffmpeg
# needs: ffmpeg
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$WORK"; ffmpeg -v error -f lavfi -i testsrc=duration=6:size=640x360:rate=30 -pix_fmt yuv420p in.mp4
# >>> readme
pbar run -- ffmpeg -y -re -i in.mp4 -c:v libx264 -preset ultrafast out.mp4
# <<< readme
