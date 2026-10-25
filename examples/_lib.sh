# Shared setup for the examples. Everything is local: no network, temp dirs only.
# Sourced by examples/*/*.sh; the README shows only the lines between the markers.
set -eu
EXAMPLES=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d "${TMPDIR:-/tmp}/pbar-example.XXXXXX")
_PIDS=""
cleanup() { for p in $_PIDS; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

# serve_file MB -> prints a URL to a MB-sized file on a local HTTP server
serve_file() {
    mkdir -p "$WORK/www"
    dd if=/dev/urandom of="$WORK/www/big.bin" bs=1048576 count="$1" 2>/dev/null
    port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')
    (cd "$WORK/www" && exec python3 -m http.server "$port" --bind 127.0.0.1 >/dev/null 2>&1) &
    _PIDS="$_PIDS $!"
    for _ in $(seq 1 50); do curl -s -o /dev/null "http://127.0.0.1:$port/" && break; sleep 0.1; done
    echo "http://127.0.0.1:$port/big.bin"
}

# make_tree DIR FILES MB_EACH -> a directory of random files (rsync, cp, tar demos)
make_tree() {
    mkdir -p "$1"
    i=1; while [ "$i" -le "$2" ]; do
        dd if=/dev/urandom of="$1/f$i.bin" bs=1048576 count="$3" 2>/dev/null; i=$((i + 1))
    done
}

# skip REASON -> selftest reports SKIP instead of FAIL (exit 77, as in automake)
skip() { echo "SKIP: $*" >&2; exit 77; }
