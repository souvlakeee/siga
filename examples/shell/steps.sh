#!/bin/sh
# tool: a custom script with named steps (--step)
# needs: sh
# expect: updates>=3 final=done max>=0.7
. "$(dirname "$0")/../_lib.sh"
cat > "$WORK/deploy.sh" <<'SH'
#!/bin/sh
for s in bump sync build restart verify; do echo "==> $s"; sleep 0.6; echo "    ok"; done
SH
chmod +x "$WORK/deploy.sh"; cd "$WORK"
# >>> readme
pbar run --step '^==> ' --steps 5 -- ./deploy.sh
# <<< readme
