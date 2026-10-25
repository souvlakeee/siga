"""siga shim for Python: report tqdm / rich / click progress to siga, unchanged apps.

`siga run --shim -- python app.py` puts this directory on PYTHONPATH. Python then
imports this file at startup; it patches the progress libraries as they get
imported and sends `siga set` (at most 4 times a second). Any error disables it
quietly: the app must never notice.
"""
import builtins
import os
import subprocess
import sys
import time

_PY = os.environ.get("SIGA_PY")
_SRC = os.environ.get("SIGA_SRC", "")
_last = [0.0, None]
_patched = set()


def _report(value):
    try:
        value = max(0.0, min(1.0, float(value)))
        now = time.time()
        if value < 1.0 and (now - _last[0] < 0.25 or value == _last[1]):
            return
        _last[:] = [now, value]
        # the last report waits, so 100% lands before the app exits and `siga end` runs
        run = subprocess.run if value >= 1.0 else subprocess.Popen
        run([_PY, "-m", "siga", "set", "%.4f" % value], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "SIGA_ORIGIN": "shim", "PYTHONPATH": _SRC})
    except Exception:
        pass


def _after(cls, name, compute):
    orig = getattr(cls, name, None)
    if orig is None or getattr(orig, "_siga", False):
        return

    def wrapper(self, *a, **kw):
        result = orig(self, *a, **kw)
        try:
            v = compute(self)
            if v is not None:
                _report(v)
        except Exception:
            pass
        return result
    wrapper._siga = True
    setattr(cls, name, wrapper)


def _tqdm(mod):
    cls = mod.tqdm
    frac = lambda s: s.n / s.total if s.total else None
    _after(cls, "update", frac)
    _after(cls, "close", frac)


def _rich(mod):
    def frac(p):
        tasks = [t for t in p.tasks if t.total]
        total = sum(t.total for t in tasks)
        return sum(t.completed for t in tasks) / total if total else None
    for name in ("update", "advance"):
        _after(mod.Progress, name, frac)


def _click(mod):
    frac = lambda b: b.pos / b.length if getattr(b, "length", None) else None
    for name in ("update", "make_step"):
        _after(mod.ProgressBar, name, frac)


_TARGETS = {"tqdm.std": _tqdm, "rich.progress": _rich, "click._termui_impl": _click}
_orig_import = builtins.__import__


def _import(name, *args, **kwargs):
    module = _orig_import(name, *args, **kwargs)
    if len(_patched) < len(_TARGETS):
        for target, patch in _TARGETS.items():
            if target not in _patched and target in sys.modules:
                # a module can show up here half-initialized (an import inside it
                # just returned), so only a patch that went through counts
                try:
                    patch(sys.modules[target])
                    _patched.add(target)
                except Exception:
                    pass
    return module


if _PY and os.environ.get("SIGA_SHIM") == "1":
    builtins.__import__ = _import
