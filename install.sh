#!/bin/sh
# Build and install the Pbar font, link `pbar`, wire Ghostty, Kitty and the Claude Code hooks.
set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)
GHOSTTY=${GHOSTTY_CONFIG:-$HOME/.config/ghostty/config}
KITTY=${KITTY_CONFIG:-$HOME/.config/kitty/kitty.conf}
CLAUDE=${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}
MARK="# pbar: live progress bars ($ROOT)"
STAMP=$(date +%Y%m%d-%H%M%S)

python3 "$ROOT/font/build_font.py" >/dev/null
cp "$ROOT/font/Pbar.ttf" "$HOME/Library/Fonts/Pbar.ttf"

mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/pbar" "$HOME/.local/bin/pbar"

if [ -f "$GHOSTTY" ] && ! grep -qF "$MARK" "$GHOSTTY"; then
    cp "$GHOSTTY" "$GHOSTTY.bak-pbar-$STAMP"
    {
        echo
        echo "$MARK"
        echo "font-codepoint-map = U+10FB00-U+10FB13=Pbar"
        echo "custom-shader = $ROOT/shader/pbar.glsl"
        echo "custom-shader-animation = true"
    } >> "$GHOSTTY"
fi

# kitty draws the bars as images; the symbol_map only keeps stray Pbar glyphs from tofu
if [ -f "$KITTY" ] && ! grep -q 'symbol_map U+10FB00-U+10FB13' "$KITTY"; then
    cp "$KITTY" "$KITTY.bak-pbar-$STAMP"
    printf '\n%s\nsymbol_map U+10FB00-U+10FB13 Pbar\n' "$MARK" >> "$KITTY"
fi

# Claude Code hooks: merged into settings.json, existing hooks kept, re-runs are no-ops
python3 - "$CLAUDE" "$ROOT" "$STAMP" <<'EOF'
import json, shutil, sys
from pathlib import Path
path, root, stamp = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
settings = json.loads(path.read_text()) if path.exists() else {}
wanted = {
    "PreToolUse": ("Bash", "hooks/pretooluse_bash.py", 5),
    "PostToolUseFailure": ("Bash", "hooks/posttooluse_bash.py", 5),
    "MessageDisplay": (None, "hooks/messagedisplay.py", 3),
}
hooks = settings.setdefault("hooks", {})
changed = False
for event, (matcher, script, timeout) in wanted.items():
    command = f"python3 {root}/{script}"
    groups = hooks.setdefault(event, [])
    if any(h.get("command") == command for g in groups for h in g.get("hooks", [])):
        continue
    group = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
    if matcher:
        group["matcher"] = matcher
    groups.append(group)
    changed = True
if changed:
    if path.exists():
        shutil.copy(path, f"{path}.bak-pbar-{stamp}")
    path.write_text(json.dumps(settings, indent=2) + "\n")
print("claude hooks:", "added" if changed else "already present")
EOF

# reload running terminals (pkill -f can't see app processes on some macOS setups)
signal_app() { ps -axo pid=,comm= | awk -v app="$2" '$2 ~ app {print $1}' | xargs kill "-$1" 2>/dev/null || true; }
signal_app USR2 'Ghostty.app/Contents/MacOS/ghostty$'
signal_app USR1 'kitty.app/Contents/MacOS/kitty$'
echo "installed: font, $HOME/.local/bin/pbar, ghostty, kitty, $CLAUDE"
