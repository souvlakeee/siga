#!/bin/sh
# tool: OSC 9;4 from Python (two lines in any app)
# needs: python3
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cat > "$WORK/job.py" <<'PY'
import sys, time
for i in range(0, 101, 5):
    sys.stderr.write(f"\033]9;4;1;{i}\033\\"); sys.stderr.flush()
    time.sleep(0.2)
PY
cd "$WORK"
# >>> readme
pbar run -- python3 job.py
# <<< readme
