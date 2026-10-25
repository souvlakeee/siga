#!/bin/sh
# tool: cargo's own OSC 9;4 (term integration)
# needs: cargo
# expect: updates>=3 final=done max>=0.9
. "$(dirname "$0")/../_lib.sh"
cd "$WORK"; printf '[workspace]\nmembers = [' > Cargo.toml
for i in $(seq 1 24); do
    printf '"c%s",' "$i" >> Cargo.toml; mkdir -p "c$i/src"
    dep=""; [ "$i" -gt 1 ] && dep="c$((i - 1)) = { path = \"../c$((i - 1))\" }"
    printf '[package]\nname = "c%s"\nversion = "0.1.0"\nedition = "2021"\n[dependencies]\n%s\n' "$i" "$dep" > "c$i/Cargo.toml"
    seq 1 400 | awk -v c="$i" '{ printf "pub fn f%d(x: u64) -> u64 { let v: Vec<u64> = (0..x).map(|y| y.wrapping_mul(%d) ^ %d).collect(); v.iter().sum() }\n", $1, $1 + c, c }' > "c$i/src/lib.rs"
done; printf ']\nresolver = "2"\n[profile.dev]\nopt-level = 1\n' >> Cargo.toml
# >>> readme
CARGO_TERM_PROGRESS_TERM_INTEGRATION=true siga run --pty -- cargo build
# <<< readme
