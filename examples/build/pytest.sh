#!/bin/sh
# tool: pytest -v
# needs: py:pytest
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$WORK"; for f in 1 2 3 4; do
    printf 'import time, pytest\n@pytest.mark.parametrize("i", range(10))\ndef test_slow(i):\n    time.sleep(0.1)\n' > "test_$f.py"
done
# >>> readme
pbar run -- pytest -v
# <<< readme
