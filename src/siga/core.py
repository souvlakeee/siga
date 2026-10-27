"""siga core: a few independent progress slots per terminal window, pushed to whichever
terminal draws the bars.

Each caller finds the tty of the window it runs in (walking up its parent processes)
and keeps its own state file, so sessions in different windows don't overwrite each
other. Without a tty in the ancestry, every window of the terminal app is updated.

A ⟦bar⟧ token is handed one of SLOTS slots (a recycling ring), so a finished bar keeps
its own value and freezes while the next job's bar moves. On ghostty each slot owns a
palette entry; the SLOTS+ "scratch" slot is tracked but drawn by nothing.

Backends:
  ghostty  palette entries BASE..BASE+SLOTS-1 (OSC 4) read by data/siga.glsl, bar = Siga
           font PUA glyphs (one family per slot)
  kitty    a PNG re-uploaded under one image id, bar = kitty Unicode placeholders (one
           shared bar per window; slots not yet distinguished)
  text     nothing live; the bar is a static ▰▱ string of the value at that moment

Inside herdr the backend is the terminal the herdr client runs in. herdr turns kitty
placeholders into its own image placements, so kitty frames go to the pane as usual;
it swallows OSC 4, so ghostty's palette value goes straight to the client's tty.
"""
import json
import math
import os
import sys
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
SLOTS = 4  # independent bar slots per window; a slot index >= SLOTS is scratch (renders nothing)
STATES = {"clear": 0, "run": 1, "busy": 2, "done": 3, "fail": 4}
LIVE = ("run", "busy")


# ---------------------------------------------------------------- state

def _host_key():
    """A per-pane id from the inherited env, so the ps-derived window resolution can be
    shared across this pane's short-lived hook/command processes without another ps."""
    raw = os.environ.get("HERDR_PANE_ID") or os.environ.get("KITTY_WINDOW_ID")
    return "".join(c if c.isalnum() else "_" for c in raw) if raw else None


def _host_get():
    """The disk-cached {tty, herdr_backend, herdr_ttys} for this pane, or {} if absent,
    unkeyed, or stale (a tty it names is gone, or herdr's socket vanished)."""
    key = _host_key()
    if not key:
        return {}
    try:
        d = json.loads((CACHE / f"host-{key}.json").read_text())
    except (OSError, ValueError):
        return {}
    ttys = ([d["tty"]] if d.get("tty") else []) + d.get("herdr_ttys", [])
    sock = os.environ.get("HERDR_SOCKET_PATH")
    if any(not Path(t).exists() for t in ttys) or (sock and not Path(sock).exists()):
        return {}
    return d


def _host_set(**fields):
    key = _host_key()
    if not key:
        return
    f = CACHE / f"host-{key}.json"
    try:
        d = json.loads(f.read_text())
    except (OSError, ValueError):
        d = {}
    d.update(fields)
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(f)
    except OSError:
        pass


def own_tty():
    """The tty of the window this process runs in, or None. Cached in SIGA_TTY for this
    process's children, and on disk per pane so sibling processes skip the ps."""
    if "SIGA_TTY" in os.environ:
        return os.environ["SIGA_TTY"] or None
    cached = _host_get().get("tty")
    if cached is not None:
        os.environ["SIGA_TTY"] = cached
        return cached or None
    import subprocess
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
    if tty:  # never persist a miss: "" names no device, so it would never invalidate
        _host_set(tty=tty)
    return tty


def _scoped(name):
    return _scoped_to(own_tty(), name)


def _scoped_to(tty, name):
    if not tty:
        return CACHE / name
    stem, _, ext = name.partition(".")
    return CACHE / f"{stem}-{tty.rsplit('/', 1)[-1]}.{ext}"


GHOSTTY_APP = "/Applications/Ghostty.app/Contents/MacOS/ghostty"


def window_tty():
    """The tty a bar's palette/image lands on — the scope a Ghostty palette is shared within.
    For Ghostty+herdr it's the one client tty behind every pane; otherwise it's own_tty(), so
    the window/pane split below collapses to one pane and nothing changes off that path."""
    if detect_backend() == "ghostty":
        t = target_ttys(GHOSTTY_APP)
        return t[0] if t else own_tty()
    return own_tty()


def state_file():  # the pre-0.4 single per-pane doc, read once to migrate into win/pane docs
    return _scoped("state.json")


def win_file():
    return _scoped_to(window_tty(), "win.json")


def pane_file():
    return _scoped_to(own_tty(), "pane.json")


def _blank():
    return {"value": 0.0, "state": "clear", "time": 0}


def _legacy():
    """The pre-0.4 single per-pane doc, read once to seed the split docs below."""
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}


def _atomic_write(path, doc):
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc))
    tmp.replace(path)


def _win_read(path=None):
    """The window's shared bars + recycle cursor — one palette per window (see window_tty).
    Every pane of the window reads and writes this, so two panes never claim the same slot
    (hence the glyph of pane A's bar and pane B's bar point at different palette entries)."""
    try:
        doc = json.loads((path or win_file()).read_text())
    except (OSError, ValueError):
        old = _legacy()  # migrate slots/cursor (or a flat record) from the old per-pane doc
        doc = {"slots": old.get("slots") or ([dict(old)] if old.get("state") else []),
               "cursor": old.get("cursor", 0)}
    doc.setdefault("slots", [])
    while len(doc["slots"]) < SLOTS:
        doc["slots"].append(_blank())
    doc.setdefault("cursor", 0)
    return doc


def _win_update(fn):
    """Read-modify-write the window doc under an flock: several panes write it at once, so an
    unlocked cycle would let two allocate()s read one cursor and claim the same slot."""
    import fcntl
    CACHE.mkdir(parents=True, exist_ok=True)
    path = win_file()  # resolve the window once; save() runs this up to ~4x/s while tracking
    with open(path.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        doc = _win_read(path)
        out = fn(doc)
        _atomic_write(path, doc)
        return out


def _pane_read():
    """Per-pane binding: the ⟦bar⟧ tokens awaiting a command, the last slot this pane touched,
    and its scratch bar. Pane-local (one writer), and `pending` must stay so or one pane's
    command could pop another pane's queued token."""
    try:
        doc = json.loads(pane_file().read_text())
    except (OSError, ValueError):
        old = _legacy()
        doc = {"pending": old.get("pending", []), "last": old.get("last", 0),
               "scratch": old.get("scratch", _blank())}
    doc.setdefault("pending", [])
    doc.setdefault("last", 0)
    doc.setdefault("scratch", _blank())
    return doc


def _pane_write(doc):
    _atomic_write(pane_file(), doc)


def save(value, state, slot=None):
    rec = {"value": value, "state": state, "time": time.time()}
    if os.environ.get("SIGA_ORIGIN"):  # "shim": the value came from inside the app
        rec["src"] = os.environ["SIGA_ORIGIN"]
    if slot is None:
        slot = _pane_read().get("last", 0)
    if slot >= SLOTS:
        pane = _pane_read()
        pane["scratch"] = rec
        _pane_write(pane)
    else:
        rec["pane"] = own_tty() or ""  # ownership: only this pane may fail/end this window slot
        _win_update(lambda win: win["slots"].__setitem__(slot, rec))
        pane = _pane_read()
        pane["last"] = slot
        _pane_write(pane)


def load(slot=None):
    if slot is None:
        slot = _pane_read().get("last", 0)
    if slot >= SLOTS:
        return _pane_read().get("scratch", _blank())
    return _win_read()["slots"][slot]


def allocate():
    """Hand a ⟦bar⟧ token a window slot and queue it for the command that follows. Scans from
    the cursor for a slot that is not live (a frozen or clear one is reclaimable — the accepted
    recycle-clobber); only if all four are live does it take the oldest, so a token never blanks
    another pane's running bar in the shared window."""
    now = time.time()

    def held(rec):  # live, or reserved by a token still awaiting its command (pending TTL)
        return rec.get("state") in LIVE or now - rec.get("reserved", 0) < 300

    def claim(win):
        order = [(win["cursor"] + i) % SLOTS for i in range(SLOTS)]
        free = [i for i in order if not held(win["slots"][i])]
        slot = free[0] if free else min(order, key=lambda i: win["slots"][i].get("time", 0))
        # reserve it so another pane doesn't reclaim the clear slot before the command pushes
        win["slots"][slot] = {"value": 0.0, "state": "clear", "time": now,
                              "pane": own_tty() or "", "reserved": now}
        win["cursor"] = (slot + 1) % SLOTS
        return slot
    slot = _win_update(claim)
    pane = _pane_read()
    pane["pending"] = pane.get("pending", []) + [[slot, time.time()]]
    pane["last"] = slot
    _pane_write(pane)
    return slot


def resolve_slot(explicit=None, default="last", ttl=300):
    """The slot a `siga` verb acts on: explicit --slot, else the oldest queued token, else a
    fallback — the last-touched slot, a scratch slot (nothing renders it), or the one bar still
    live and owned by this pane (for `siga end`, whose token the pipe already consumed)."""
    if explicit is None and os.environ.get("SIGA_SLOT"):
        explicit = os.environ["SIGA_SLOT"]  # a shimmed child drives its parent's slot
    if explicit is not None:
        return int(explicit)
    pane = _pane_read()
    pend = [e for e in pane.get("pending", []) if time.time() - e[1] < ttl]
    slot = pend.pop(0)[0] if pend else None
    pane["pending"] = pend
    _pane_write(pane)
    if slot is not None:
        return slot
    if default == "scratch":
        return SLOTS
    if default == "live":
        me = own_tty() or ""
        for i, rec in enumerate(_win_read()["slots"]):
            if rec.get("state") in LIVE and rec.get("pane", me) == me:  # absent = legacy, ours
                return i
        if pane.get("scratch", {}).get("state") in LIVE:
            return SLOTS
    return pane.get("last", 0)


def fail_live():
    """Fail this pane's live bars (a wrapped command died before `siga end`). The `pane` stamp
    keeps it from touching another pane's running bar in the same window."""
    me = own_tty() or ""
    for i, rec in enumerate(_win_read()["slots"]):
        if rec.get("state") in LIVE and rec.get("pane", me) == me:  # absent = legacy, ours
            push(float(rec.get("value", 0.0)), "fail", slot=i)
    scratch = _pane_read().get("scratch", _blank())
    if scratch.get("state") in LIVE:
        push(float(scratch.get("value", 0.0)), "fail", slot=SLOTS)


def detect_backend(env=os.environ):
    if env.get("SIGA_BACKEND"):
        return env["SIGA_BACKEND"]
    if env.get("TERM_PROGRAM") == "herdr":
        return herdr_host(env)[0] or "text"
    if env.get("TERM_PROGRAM") == "ghostty":
        return "ghostty"
    if env.get("KITTY_WINDOW_ID") or env.get("TERM") == "xterm-kitty":
        return "kitty"
    return "text"


def child_ttys(app_suffix):
    """ttys of the login shells a terminal app spawned (one per window/tab)."""
    import subprocess
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,tty=,comm="],
                         capture_output=True, text=True, check=True).stdout
    procs = [line.split(None, 3) for line in out.splitlines()]
    apps = {p[0] for p in procs if len(p) == 4 and p[3].endswith(app_suffix)}
    return sorted({"/dev/" + p[2] for p in procs
                   if len(p) == 4 and p[1] in apps and p[2] != "??"})


def herdr_host(env=os.environ):
    """(backend, client ttys) of the terminal herdr is attached in, or (None, []).

    A pane descends from the detached herdr server, not from the client, so the host
    comes from the client processes: a `herdr` with a tty, under a kitty or ghostty app.
    """
    if env.get("TERM_PROGRAM") != "herdr":
        return None, []
    if "SIGA_HERDR_HOST" in env:
        backend, _, ttys = env["SIGA_HERDR_HOST"].partition(":")
        return backend or None, [t for t in ttys.split(",") if t]
    if env is os.environ:
        d = _host_get()
        if "herdr_backend" in d:
            backend = d["herdr_backend"] or None
            ttys = d.get("herdr_ttys", [])
            os.environ["SIGA_HERDR_HOST"] = f"{backend or ''}:{','.join(ttys)}"
            return backend, ttys
    import subprocess
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,tty=,comm="],
                         capture_output=True, text=True).stdout
    procs = {}
    for line in out.splitlines():
        f = line.split(None, 3)
        if len(f) == 4:
            procs[f[0]] = (f[1], f[2], f[3].strip().rsplit("/", 1)[-1])
    found = {}
    for ppid, tty, name in procs.values():
        if name != "herdr" or tty == "??":
            continue
        for _ in range(32):
            if ppid not in procs:
                break
            ppid, _, parent = procs[ppid]
            if parent in ("kitty", "ghostty"):
                found.setdefault(parent, []).append("/dev/" + tty)
                break
    backend = "kitty" if "kitty" in found else "ghostty" if "ghostty" in found else None
    ttys = sorted(found.get(backend, []))
    if env is os.environ:
        os.environ["SIGA_HERDR_HOST"] = f"{backend or ''}:{','.join(ttys)}"
        if backend:  # don't persist a miss (see own_tty)
            _host_set(herdr_backend=backend, herdr_ttys=ttys)
    return backend, ttys


def target_ttys(app_suffix):
    backend, host = herdr_host()
    if backend == "ghostty" and app_suffix.endswith("/ghostty"):
        return host
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
    """Each slot's value + state rides palette entry BASE+slot, read by data/siga.glsl.

    Slot identity is baked into the glyphs: font family j (U+10FB00 + j*CELLS ..) is keyed
    a distinct green, so the shader tells one bar's cells from another's and reads the
    matching entry. A finished bar keeps its own entry and freezes while others move.
    """
    BASE = 252

    @staticmethod
    def bar(st, slot=0):
        if slot is None or slot >= SLOTS:
            slot = 0
        first = 0x10FB00 + slot * CELLS
        return "".join(chr(first + i) for i in range(CELLS))

    def apply(self, value, state, slot=None):
        if slot is None or slot >= SLOTS:  # scratch bar: tracked but nothing renders it
            return
        v = max(0, min(1023, round(value * 1023)))
        seq = "\033]4;%d;#%02x%02x%02x\a" % (
            self.BASE + slot, 0xE0 | (v >> 5), 0xE0 | (v & 31), 0xF0 | STATES[state])
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
    def bar(cls, st, slot=0):  # kitty keeps one shared bar per window (slot ignored)
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
        """The bar as PNG bytes: one rounded box per cell, drawn with the stdlib (zlib) only."""
        w, h = CELLS * cls.CELL_W, cls.CELL_H
        bw = cls.CELL_W - 4  # box width; the 4 px gap lands at the cell boundary, ends full
        mask = _rounded_mask(bw, int(h * 0.56), 5)
        top = int(h * 0.22)
        cols = cls.colors(value, state, t)
        # Each cell box holds its two segment colors (left half, right half) for fill detail.
        boxes = []
        for cell in range(CELLS):
            lo, hi = cols[2 * cell], cols[2 * cell + 1]
            rgb = bytearray(bw * 3)
            for px in range(bw):
                rgb[px * 3:px * 3 + 3] = bytes(lo if px * 2 < bw else hi)
            boxes.append(rgb)
        rows = []
        for y in range(h):
            row = bytearray(1 + w * 4)  # filter byte 0, then transparent pixels
            my = y - top
            if 0 <= my < len(mask):
                alphas = mask[my]
                for cell in range(CELLS):
                    x0 = 1 + (cell * cls.CELL_W + 2) * 4
                    rgb = boxes[cell]
                    seg = bytearray(bw * 4)
                    seg[0::4], seg[1::4], seg[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
                    seg[3::4] = alphas
                    row[x0:x0 + len(seg)] = seg
            rows.append(bytes(row))
        return _png(w, h, b"".join(rows))

    @classmethod
    def push_frame(cls, value, state, t=0.0):
        import base64
        import tempfile
        png = cls.frame(value, state, t)
        for tty in target_ttys("/Applications/kitty.app/Contents/MacOS/kitty"):
            # t=t: kitty reads then deletes the file, so every tty gets its own copy
            fd, name = tempfile.mkstemp(prefix="tty-graphics-protocol-", suffix=".png")
            with os.fdopen(fd, "wb") as f:
                f.write(png)
            p64 = base64.b64encode(name.encode()).decode()
            seq = "\033_Ga=T,U=1,i=%d,f=100,t=t,c=%d,r=1,q=2;%s\033\\" % (cls.IMAGE_ID, CELLS, p64)
            write_tty(tty, seq.encode())

    def apply(self, value, state, slot=None):
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
    import subprocess
    subprocess.Popen([sys.executable, "-m", "siga", *args],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True,
                     env={**os.environ, "PYTHONPATH": str(SRC), **(env or {})})


def animate(fps=20, idle_timeout=600):
    """Re-push kitty frames while the state is live; ghostty animates in its shader."""
    if os.environ.get("TERM_PROGRAM") == "herdr":
        fps = 8  # herdr re-sends every frame to its client as raw RGBA
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
    def bar(st, slot=0):
        n = round(float(st.get("value", 0)) * CELLS)
        if st.get("state") == "done":
            n = CELLS
        return "▰" * n + "▱" * (CELLS - n)

    def apply(self, value, state, slot=None):
        pass


class Record:
    """Appends every push to $SIGA_RECORD (JSONL); used by tests and `siga selftest`."""
    bar = Text.bar

    def apply(self, value, state, slot=None):
        path = os.environ.get("SIGA_RECORD")
        if path:
            with open(path, "a") as f:
                rec = {"t": round(time.time(), 3), "value": round(value, 4), "state": state}
                if slot is not None:
                    rec["slot"] = slot
                f.write(json.dumps(rec) + "\n")


BACKENDS = {"ghostty": Ghostty, "kitty": Kitty, "text": Text, "record": Record}


def push(value, state, backend=None, slot=None):
    value = max(0.0, min(1.0, value))
    if slot is None:
        slot = _pane_read().get("last", 0)
    save(value, state, slot)
    BACKENDS[backend or detect_backend()]().apply(value, state, slot)


def reapply(slot, backend=None):
    """Repaint a slot from its saved state without re-saving it (new windows, restarts) — so
    refresh doesn't overwrite the window slot's `pane` owner with the refreshing pane's."""
    rec = load(slot)
    BACKENDS[backend or detect_backend()]().apply(
        float(rec.get("value", 0.0)), rec.get("state", "clear"), slot)


def bar_string(backend=None, slot=0):
    backend = backend or detect_backend()
    return BACKENDS[backend].bar(load(slot), slot)


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


def shim_active(slot=None, window=2.0):
    st = load(slot)
    return st.get("src") == "shim" and time.time() - st.get("time", 0) < window


def track(read_chunk, write_chunk, key=None, clean=False, step=None, steps=None, min_interval=0.25, slot=None):
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
    push(0.0, "run", slot=slot) if eta else push(0.0, "busy", slot=slot)
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
            # Hold a time-estimated bar at 90%, not 99%: a near-full bar reads as
            # "done" while the job is still running. The last tenth fills only on the
            # real exit (push below / `siga end`), so overrunning the estimate looks
            # like "almost there, still working", not finished. A trusted N/M count
            # is exact and uncapped — this ceiling is for the guess only.
            val, state = min(0.90, (now - t0) / eta), "run"
        else:
            continue
        if shim_active(slot):
            continue
        if now - last_push >= min_interval and (val, state) != last_val:
            push(val, state, slot=slot)
            last_push, last_val = now, (val, state)
    stream.close()
    if tee:
        tee.close()
    if cleaner:
        write_chunk(cleaner.close().encode())
    if prog.trusted and not shim_active(slot) and (prog.value, prog.state or "run") != last_val:
        push(prog.value, prog.state or "run", slot=slot)
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
    import subprocess
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
