"""siga core: one progress state per terminal window, pushed to whichever terminal draws the bars.

Each caller finds the tty of the window it runs in (walking up its parent processes)
and keeps its own state file, so sessions in different windows don't overwrite each
other. Without a tty in the ancestry, every window of the terminal app is updated.

Backends:
  ghostty  palette entry 254 (OSC 4) read by data/siga.glsl, bar = Siga font PUA glyphs
  kitty    a PNG re-uploaded under one image id, bar = kitty Unicode placeholders
  text     nothing live; the bar is a static ▰▱ string of the value at that moment
"""
import base64
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PKG = Path(__file__).resolve().parent
DATA = PKG / "data"
SRC = PKG.parent  # what PYTHONPATH needs for `python -m siga`
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "siga"
WELCOME = CACHE / "welcome"  # armed by `siga setup` / `siga demo`, shown under Claude's next message


def arm_welcome(label="welcome"):
    CACHE.mkdir(parents=True, exist_ok=True)
    WELCOME.write_text(f"{time.time()} {label}")
HISTORY_FILE = CACHE / "history.json"

CELLS = 20
STATES = {"clear": 0, "run": 1, "busy": 2, "done": 3, "fail": 4}
LIVE = ("run", "busy")


# ---------------------------------------------------------------- state

def own_tty():
    """The tty of the window this process runs in, or None (cached in SIGA_TTY for children)."""
    if "SIGA_TTY" in os.environ:
        return os.environ["SIGA_TTY"] or None
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,tty="],
                         capture_output=True, text=True, check=True).stdout
    procs = {}
    for line in out.split("\n"):
        f = line.split()
        if len(f) == 3:
            procs[f[0]] = (f[1], f[2])
    pid, tty = str(os.getpid()), None
    for _ in range(64):
        if pid not in procs:
            break
        ppid, t = procs[pid]
        if t != "??":
            tty = "/dev/" + t
            break
        pid = ppid
    os.environ["SIGA_TTY"] = tty or ""
    return tty


def _scoped(name):
    tty = own_tty()
    if not tty:
        return CACHE / name
    stem, _, ext = name.partition(".")
    return CACHE / f"{stem}-{tty.rsplit('/', 1)[-1]}.{ext}"


def state_file():
    return _scoped("state.json")


def save(value, state):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = state_file()
    tmp = path.with_suffix(".tmp")
    rec = {"value": value, "state": state, "time": time.time()}
    if os.environ.get("SIGA_ORIGIN"):  # "shim": the value came from inside the app
        rec["src"] = os.environ["SIGA_ORIGIN"]
    tmp.write_text(json.dumps(rec))
    tmp.replace(path)


def load():
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {"value": 0.0, "state": "clear", "time": 0}


def detect_backend(env=os.environ):
    if env.get("SIGA_BACKEND"):
        return env["SIGA_BACKEND"]
    if env.get("TERM_PROGRAM") == "ghostty":
        return "ghostty"
    if env.get("KITTY_WINDOW_ID") or env.get("TERM") == "xterm-kitty":
        return "kitty"
    return "text"


def child_ttys(app_suffix):
    """ttys of the login shells a terminal app spawned (one per window/tab)."""
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,tty=,comm="],
                         capture_output=True, text=True, check=True).stdout
    procs = [line.split(None, 3) for line in out.splitlines()]
    apps = {p[0] for p in procs if len(p) == 4 and p[3].endswith(app_suffix)}
    return sorted({"/dev/" + p[2] for p in procs
                   if len(p) == 4 and p[1] in apps and p[2] != "??"})


def target_ttys(app_suffix):
    tty = own_tty()
    return [tty] if tty else child_ttys(app_suffix)


def write_tty(tty, data):
    try:
        fd = os.open(tty, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return
    try:
        os.write(fd, data)
    except OSError:
        pass
    finally:
        os.close(fd)


# ---------------------------------------------------------------- ghostty

class Ghostty:
    """Palette entry 254 carries value + state to the shader (see data/siga.glsl)."""
    PALETTE_INDEX = 254

    @staticmethod
    def bar(st):
        return "".join(chr(0x10FB00 + i) for i in range(CELLS))

    def apply(self, value, state):
        v = max(0, min(1023, round(value * 1023)))
        seq = "\033]4;%d;#%02x%02x%02x\a" % (
            self.PALETTE_INDEX, 0xE0 | (v >> 5), 0xE0 | (v & 31), 0xF0 | STATES[state])
        for tty in target_ttys("/Applications/Ghostty.app/Contents/MacOS/ghostty"):
            write_tty(tty, seq.encode())


# ---------------------------------------------------------------- kitty

_MASKS = {}


def _rounded_mask(w, h, r):
    """Alpha rows (bytes) of an anti-aliased rounded rectangle, cached by size."""
    if (w, h, r) not in _MASKS:
        rows = []
        for y in range(h):
            row = bytearray(w)
            for x in range(w):
                # distance outside the rounded rect, sampled at the pixel center
                dx = max(r - (x + 0.5), 0, (x + 0.5) - (w - r))
                dy = max(r - (y + 0.5), 0, (y + 0.5) - (h - r))
                d = math.hypot(dx, dy) - r if dx and dy else -0.5
                row[x] = int(255 * min(1.0, max(0.0, 0.5 - d)))
            rows.append(bytes(row))
        _MASKS[(w, h, r)] = rows
    return _MASKS[(w, h, r)]


def _png(w, h, raw):
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


class Kitty:
    """One image id shared by every placeholder; re-uploading it repaints them all.

    In default-colored text a placeholder's id has 0 in its low 24 bits (kitty takes
    them from the foreground color), so the high byte comes from the third diacritic.
    """
    MSB = 80
    IMAGE_ID = MSB << 24
    CELL_W, CELL_H = 40, 84
    SEGS = CELLS * 2

    @classmethod
    def bar(cls, st):
        diac = [int(x, 16) for x in (DATA / "kitty_diacritics.txt").read_text().split()]
        head = chr(0x10EEEE) + chr(diac[0]) + chr(diac[0]) + chr(diac[cls.MSB])
        return head + chr(0x10EEEE) * (CELLS - 1)

    @classmethod
    def colors(cls, value, state, t):
        """One RGB color per segment for this moment of the animation."""
        lit_n = value * cls.SEGS
        if state == "busy":
            ph = (t / 1.2) % 1.0
            head = (ph * 2 if ph < 0.5 else 2 - ph * 2) * (cls.SEGS + 6) - 3
        out = []
        for i in range(cls.SEGS):
            p = i / cls.SEGS
            base = (int(33 + p * 26), int(211 - p * 81), int(238 + p * 7))
            off = (34, 38, 46)
            if state == "done":
                wave = (t * 0.8 - p) % 1.0
                col = tuple(min(255, int(c * (1 + 0.25 * wave ** 12))) for c in (51, 204, 107))
            elif state == "fail":
                col = (245, 77, 77) if i < lit_n else (74, 32, 36)
            elif state == "busy":
                dist = head - i if ph < 0.5 else i - head
                k = math.exp(-dist * 0.55) if dist >= 0 else 0.0
                col = tuple(int(o + (b - o) * k) for o, b in zip(off, base))
            elif state == "run" and i < lit_n:
                wave = (t * 1.6 - p * 1.5) % 1.0
                boost = 1 + 0.45 * wave ** 10
                if i + 1 > lit_n:  # leading partial segment pulses
                    boost += 0.35 + 0.35 * math.sin(t * 12)
                col = tuple(min(255, int(c * boost)) for c in base)
            else:
                col = off
            out.append(col)
        return out

    @classmethod
    def frame(cls, value, state, t):
        """The bar as PNG bytes: rounded segments drawn with the stdlib (zlib) only."""
        w, h = CELLS * cls.CELL_W, cls.CELL_H
        sw = w // cls.SEGS
        mask = _rounded_mask(sw - 4, int(h * 0.56), 5)
        top = int(h * 0.22)
        rows = []
        cols = cls.colors(value, state, t)
        for y in range(h):
            row = bytearray(1 + w * 4)  # filter byte 0, then transparent pixels
            my = y - top
            if 0 <= my < len(mask):
                alphas = mask[my]
                for i, (r, g, b) in enumerate(cols):
                    x0 = 1 + (i * sw + 2) * 4
                    seg = bytearray(len(alphas) * 4)
                    seg[0::4], seg[1::4], seg[2::4] = bytes([r]) * len(alphas), bytes([g]) * len(alphas), bytes([b]) * len(alphas)
                    seg[3::4] = alphas
                    row[x0:x0 + len(seg)] = seg
            rows.append(bytes(row))
        return _png(w, h, b"".join(rows))

    @classmethod
    def push_frame(cls, value, state, t=0.0):
        png = cls.frame(value, state, t)
        for tty in target_ttys("/Applications/kitty.app/Contents/MacOS/kitty"):
            # t=t: kitty reads then deletes the file, so every tty gets its own copy
            fd, name = tempfile.mkstemp(prefix="tty-graphics-protocol-", suffix=".png")
            with os.fdopen(fd, "wb") as f:
                f.write(png)
            p64 = base64.b64encode(name.encode()).decode()
            seq = "\033_Ga=T,U=1,i=%d,f=100,t=t,c=%d,r=1,q=2;%s\033\\" % (cls.IMAGE_ID, CELLS, p64)
            write_tty(tty, seq.encode())

    def apply(self, value, state):
        self.push_frame(value, state)
        if state in LIVE:
            start_animator()


def start_animator():
    try:
        pid = int(_scoped("animate.pid").read_text())
        os.kill(pid, 0)
        return
    except (OSError, ValueError):
        pass
    spawn_detached(["animate"], {"SIGA_BACKEND": "kitty", "SIGA_TTY": own_tty() or ""})


def spawn_detached(args, env=None):
    """Run `python -m siga <args>` in the background, detached from this process."""
    subprocess.Popen([sys.executable, "-m", "siga", *args],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True,
                     env={**os.environ, "PYTHONPATH": str(SRC), **(env or {})})


def animate(fps=20, idle_timeout=600):
    """Re-push kitty frames while the state is live; ghostty animates in its shader."""
    CACHE.mkdir(parents=True, exist_ok=True)
    pidfile = _scoped("animate.pid")
    pidfile.write_text(str(os.getpid()))
    t0 = time.time()
    try:
        while True:
            st = load()
            if st["state"] not in LIVE or time.time() - st.get("time", 0) > idle_timeout:
                Kitty.push_frame(st["value"], st["state"], time.time() - t0)
                return
            Kitty.push_frame(st["value"], st["state"], time.time() - t0)
            time.sleep(1 / fps)
    finally:
        try:
            if pidfile.read_text() == str(os.getpid()):
                pidfile.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- text

class Text:
    @staticmethod
    def bar(st):
        n = round(float(st.get("value", 0)) * CELLS)
        if st.get("state") == "done":
            n = CELLS
        return "▰" * n + "▱" * (CELLS - n)

    def apply(self, value, state):
        pass


class Record:
    """Appends every push to $SIGA_RECORD (JSONL); used by tests and `siga selftest`."""
    bar = Text.bar

    def apply(self, value, state):
        path = os.environ.get("SIGA_RECORD")
        if path:
            with open(path, "a") as f:
                f.write(json.dumps({"t": round(time.time(), 3), "value": round(value, 4), "state": state}) + "\n")


BACKENDS = {"ghostty": Ghostty, "kitty": Kitty, "text": Text, "record": Record}


def push(value, state, backend=None):
    value = max(0.0, min(1.0, value))
    save(value, state)
    BACKENDS[backend or detect_backend()]().apply(value, state)


def bar_string(backend=None):
    return BACKENDS[backend or detect_backend()].bar(load())


def parse_value(arg):
    arg = arg.strip()
    if arg.endswith("%"):
        return float(arg[:-1]) / 100
    if "/" in arg:
        n, m = arg.split("/", 1)
        return float(n) / float(m) if float(m) else 0.0
    return float(arg)


# ---------------------------------------------------------------- ETA history

def command_key(command):
    import hashlib
    norm = " ".join(command.split())
    return hashlib.sha1(norm.encode()).hexdigest()[:10]


def history_get(key):
    try:
        runs = json.loads(HISTORY_FILE.read_text()).get(key, [])
    except (OSError, ValueError):
        return None
    if not runs:
        return None
    runs = sorted(runs)
    return runs[len(runs) // 2]


def history_add(key, seconds):
    try:
        data = json.loads(HISTORY_FILE.read_text())
    except (OSError, ValueError):
        data = {}
    data[key] = (data.get(key, []) + [round(seconds, 2)])[-5:]
    CACHE.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(data))


def shim_active(window=2.0):
    st = load()
    return st.get("src") == "shim" and time.time() - st.get("time", 0) < window


def track(read_chunk, write_chunk, key=None, clean=False, step=None, steps=None, min_interval=0.25):
    """Copy a byte stream through while pushing its progress to the bars.

    read_chunk(timeout) returns bytes, b"" at EOF, or None when nothing arrived.
    clean=True rewrites terminal-style output (pty runs) into plain final lines.
    step/steps: a regex counting a custom script's steps, and their total (learned
    from the previous run of the same command when not given).
    """
    from siga.parse import Cleaner, Progress, Stream
    if step and not steps and key:
        steps = history_get("steps:" + key)
    prog = Progress(step=step, steps=int(steps) if steps else None)
    stream = Stream(prog)
    cleaner = Cleaner() if clean else None
    eta = history_get(key) if key else None
    tee = open(os.environ["SIGA_TEE"], "ab") if os.environ.get("SIGA_TEE") else None
    t0 = time.time()
    last_push, last_val = 0.0, None
    push(0.0, "run") if eta else push(0.0, "busy")
    while True:
        chunk = read_chunk(min_interval)
        if chunk == b"":
            break
        if chunk:
            if tee:  # raw stream capture, for tests/fixtures
                tee.write(chunk)
            text = chunk.decode("utf-8", "replace")
            write_chunk(cleaner.feed(text).encode() if cleaner else chunk)
            stream.feed(text)
        now = time.time()
        if prog.state == "busy":
            val, state = 0.0, "busy"
        elif prog.trusted:
            val, state = prog.value, prog.state or "run"
        elif eta:
            val, state = min(0.99, (now - t0) / eta), "run"
        else:
            continue
        if shim_active():
            continue
        if now - last_push >= min_interval and (val, state) != last_val:
            push(val, state)
            last_push, last_val = now, (val, state)
    stream.close()
    if tee:
        tee.close()
    if cleaner:
        write_chunk(cleaner.close().encode())
    if prog.trusted and not shim_active() and (prog.value, prog.state or "run") != last_val:
        push(prog.value, prog.state or "run")
    if key:
        history_add(key, time.time() - t0)
        if step and prog.steps_seen:
            history_add("steps:" + key, prog.steps_seen)


# ---------------------------------------------------------------- running commands

def spawn(args, use_pty=False, env=None, columns=120):
    """Start args with stdout+stderr merged; returns (read_chunk, wait).

    use_pty runs it on a pseudo-terminal, for tools that only draw progress there.
    """
    import select
    env = {**os.environ, **(env or {})}
    if not use_pty:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=env)
        fd = child.stdout.fileno()
    else:
        import fcntl
        import struct
        import termios
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, columns, 0, 0))
        env.setdefault("TERM", "xterm-256color")
        env["COLUMNS"] = str(columns)
        child = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=slave, env=env,
                                 start_new_session=True)
        os.close(slave)
        fd = master

    def read_chunk(timeout):
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return None
        try:
            return os.read(fd, 65536)
        except OSError:  # a pty master reports EIO once the child side closes
            return b""

    def wait():
        rc = child.wait()
        if use_pty:
            os.close(fd)
        return rc

    return read_chunk, wait
