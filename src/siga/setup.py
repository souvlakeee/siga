"""`siga setup`: install what the terminal needs to draw the bars.

  siga setup            same as --plan
  siga setup --plan     print every change it would make, and change nothing
  siga setup --apply    make them: font, shader copy, Ghostty config block (with a backup)
  siga setup --remove   undo them
  siga setup --check    exit 1 if anything is missing (used by the SessionStart hook)

Only what this machine needs is installed: Ghostty needs the Siga font and the shader. The shader is copied to a stable path,
because Ghostty's config takes an absolute path and a Claude Code plugin's own
directory changes on every update. Kitty needs nothing: its bars are images.
Older pbar installs (the project's former name) are cleaned up on --apply.
"""
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from siga import core

BEGIN = "# >>> siga: live progress bars (https://github.com/souvlakeee/siga)"
END = "# <<< siga"
LEGACY_MARK = "# pbar: live progress bars"
HOME = Path.home()
SHADER = HOME / ".config" / "siga" / "siga.glsl"


def font_dest():
    if sys.platform == "darwin":
        return HOME / "Library" / "Fonts" / "Siga.ttf"
    return HOME / ".local" / "share" / "fonts" / "Siga.ttf"


def ghostty_config():
    """The config file Ghostty reads: an existing one, else the XDG path it would create."""
    candidates = [Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "ghostty" / "config"]
    if sys.platform == "darwin":
        candidates.append(HOME / "Library" / "Application Support" / "com.mitchellh.ghostty" / "config")
    for c in candidates:
        if c.exists() and c.read_text().strip():
            return c
    return candidates[0]


def ghostty_present():
    """Ghostty is on this machine: the app, the binary, its config, or we run inside it."""
    apps = [Path("/Applications/Ghostty.app"), HOME / "Applications" / "Ghostty.app"]
    return (core.detect_backend() == "ghostty" or any(a.exists() for a in apps)
            or shutil.which("ghostty") is not None or ghostty_config().exists())


def ghostty_block():
    return [
        BEGIN,
        "font-codepoint-map = U+10FB00-U+10FB13=Siga",
        f"custom-shader = {SHADER}",
        "custom-shader-animation = true",
        END,
    ]


def _same(a, b):
    try:
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _legacy_lines(text):
    """Lines a pbar install added: its marker line and the settings right after it."""
    lines, drop, out = text.splitlines(), set(), []
    for i, line in enumerate(lines):
        if line.startswith(LEGACY_MARK):
            drop.add(i)
            j = i + 1
            while j < len(lines) and ("Pbar" in lines[j] or "pbar" in lines[j] or "custom-shader-animation" in lines[j]):
                drop.add(j)
                j += 1
    for i in sorted(drop):
        out.append(lines[i])
    return drop, out


def plan():
    """[(description, apply_fn)] for everything not yet in place."""
    steps = []
    font = font_dest()
    if ghostty_present():
        if not _same(core.DATA / "Siga.ttf", font):
            steps.append((f"copy font  {font}", lambda: _copy(core.DATA / "Siga.ttf", font)))
        if not _same(core.DATA / "siga.glsl", SHADER):
            steps.append((f"copy shader  {SHADER}", lambda: _copy(core.DATA / "siga.glsl", SHADER)))
        cfg = ghostty_config()
        text = cfg.read_text() if cfg.exists() else ""
        if BEGIN not in text:
            block = "\n".join("    + " + l for l in ghostty_block())
            steps.append((f"append to {cfg} (backup kept):\n{block}", lambda: _append(cfg, ghostty_block())))

    for path in [p for p in (ghostty_config(), HOME / ".config" / "kitty" / "kitty.conf") if p.exists()]:
        drop, lines = _legacy_lines(path.read_text())
        if drop:
            shown = "\n".join("    - " + l for l in lines)
            steps.append((f"remove old pbar lines from {path} (backup kept):\n{shown}",
                          lambda p=path: _drop_legacy(p)))
    old_font = font.with_name("Pbar.ttf")
    if old_font.exists():
        steps.append((f"remove old font  {old_font}", old_font.unlink))
    return steps


def missing():
    """Short reasons the bars can't draw yet, for the SessionStart hook."""
    out = []
    backend = core.detect_backend()
    if backend == "ghostty":
        if not font_dest().exists():
            out.append("the Siga font is not installed")
        text = ghostty_config().read_text() if ghostty_config().exists() else ""
        if BEGIN not in text:
            out.append("Ghostty is not configured for siga")
    return out


def refresh_installed():
    """After a plugin update, keep the installed shader and font in step with this version."""
    if SHADER.exists() and not _same(core.DATA / "siga.glsl", SHADER):
        _copy(core.DATA / "siga.glsl", SHADER)
        reload_terminals()
    font = font_dest()
    if font.exists() and not _same(core.DATA / "Siga.ttf", font):
        _copy(core.DATA / "Siga.ttf", font)


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def _backup(path):
    if path.exists():
        shutil.copyfile(path, path.with_name(path.name + time.strftime(".bak-siga-%Y%m%d-%H%M%S")))


def _append(path, lines):
    _backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text() if path.exists() else ""
    sep = "" if not text or text.endswith("\n") else "\n"
    path.write_text(text + sep + "\n" + "\n".join(lines) + "\n")


def _drop_legacy(path):
    _backup(path)
    text = path.read_text()
    drop, _ = _legacy_lines(text)
    path.write_text("\n".join(l for i, l in enumerate(text.splitlines()) if i not in drop) + "\n")


def _remove_block(path):
    text = path.read_text()
    if BEGIN not in text:
        return False
    _backup(path)
    out, inside = [], False
    for line in text.splitlines():
        if line == BEGIN:
            inside = True
        elif inside and line == END:
            inside = False
        elif not inside:
            out.append(line)
    path.write_text("\n".join(out).rstrip("\n") + "\n")
    return True


def reload_terminals():
    """Ask running Ghostty instances to reload their config (pkill -f can't see app processes)."""
    out = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True).stdout
    reloaded = 0
    for line in out.splitlines():
        pid, _, comm = line.strip().partition(" ")
        if comm.endswith("Ghostty.app/Contents/MacOS/ghostty") or comm.endswith("/ghostty"):
            try:
                os.kill(int(pid), signal.SIGUSR2)  # reload config; 12 is SIGSYS on macOS and kills Ghostty
                reloaded += 1
            except (OSError, ValueError):
                pass
    return reloaded


def where():
    """One line naming the terminal we run in, and what it needs."""
    backend = core.detect_backend()
    if backend == "kitty":
        return "You're in Kitty: it draws siga's bars as images and needs nothing."
    if backend == "ghostty":
        return "You're in Ghostty: it needs the Siga font, the shader and a config block."
    return "This terminal shows a static bar; live bars need Ghostty 1.3+ or Kitty 0.49+."


def main(args):
    if "--remove" in args:
        changed = [str(p) for p in (font_dest(), SHADER) if p.exists()]
        for p in (font_dest(), SHADER):
            p.unlink(missing_ok=True)
        if ghostty_config().exists() and _remove_block(ghostty_config()):
            changed.append(str(ghostty_config()))
        reload_terminals()
        print("removed: " + (", ".join(changed) if changed else "nothing was installed"))
        return 0
    steps = plan()
    if "--check" in args:
        return 1 if steps else 0
    print(where())
    if not steps:
        print("Nothing to set up." if not ghostty_present()
              else "siga is set up: the font, shader and Ghostty config are in place.")
        return 0
    if "--apply" not in args:
        lead = "siga setup would:" if core.detect_backend() == "ghostty" \
            else "Ghostty is also installed. For live bars there, siga setup would:"
        print(lead + "\n" + "\n".join(f"  {i + 1}. {d}" for i, (d, _) in enumerate(steps)))
        print("\nRun `siga setup --apply` to make these changes.")
        return 0
    for desc, fn in steps:
        fn()
        print("done: " + desc.splitlines()[0])
    if reload_terminals():
        print("Ghostty reloaded. A newly installed font is picked up by new Ghostty windows.")
    return 0
