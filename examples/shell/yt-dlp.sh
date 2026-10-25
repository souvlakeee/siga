#!/bin/sh
# tool: yt-dlp
# needs: yt-dlp
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
URL=$(serve_file 40); cd "$WORK"
# >>> readme
siga run -- yt-dlp --newline --limit-rate 8M -o video.bin "$URL"
# <<< readme
