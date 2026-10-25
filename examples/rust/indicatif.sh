#!/bin/sh
# tool: indicatif (Rust, --pty)
# needs: cargo
# expect: updates>=5 final=done max>=0.95
. "$(dirname "$0")/../_lib.sh"
cd "$EXAMPLES/rust/indicatif"; cargo build -q
# >>> readme
siga run --pty -- ./target/debug/indicatif-demo
# <<< readme
