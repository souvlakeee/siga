"""siga: live progress bars that keep filling after they are printed.

  siga set <0..1 | NN% | N/M>   running, at that fraction
  siga busy                     running, no known fraction
  siga done | fail              final state; every bar freezes on it
  siga end <exit-code>          done if 0, else fail; exits with that code
  siga clear                    empty bars
  siga bar                      print the bar string for this terminal
  siga refresh                  re-push the last state (new windows, restarts)
  siga status                   print the last state
  siga demo [seconds]           fill a bar from 0 to 100% (default 4 s), to check it draws;
                                in Claude Code it fills under Claude's next message
  siga run [--pty] [--shim] -- <cmd...>
                                run cmd, track its output, end with its exit code;
                                --pty for tools that only draw progress on a terminal
                                (output is cleaned to plain lines), --shim to read
                                tqdm/rich/click/cli-progress values directly
  siga pipe [-k KEY]            copy stdin to stdout, tracking progress
  --step RX [--steps N]         (run, pipe) for custom scripts: a line matching RX starts
                                the next step; N is learned from the last run if omitted
  --slot N                      (any verb) act on bar slot N; normally a ⟦bar⟧ token picks
                                the slot and the command that follows binds it
  siga selftest [name] [--network] [--capture] | --snippets | --readme
                                run examples/ under a recorder and check every bar
  siga setup [--plan|--apply|--remove]
                                install the font and the Ghostty/Kitty config (shows the diff first)
  siga off | on                 pause / resume the Claude Code hooks (no wrapping, no bar swap)
  siga hook <event>             (internal) Claude Code hooks: pretooluse, posttoolfailure,
                                messagedisplay, sessionstart
  siga animate                  (internal) kitty frame loop

A few independent bar slots per window: each ⟦bar⟧ gets its own, so a finished bar freezes
while the next job's fills (jobs run one at a time; a ring of slots recycles). Progress
comes from N/M counts, NN% or ffmpeg time= in the output; without them, from how long the
same command (KEY) took before, or a busy sweep the first time.
"""
import os
import sys
import time
from pathlib import Path

from siga import core


def fd_reader(fd):
    import select

    def read(timeout):
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return None
        return os.read(fd, 65536)
    return read


_reader_gone = False


def stdout_writer(chunk):
    # a reader like `head -1` may close early; keep consuming and tracking quietly
    global _reader_gone
    if chunk and not _reader_gone:
        try:
            os.write(sys.stdout.fileno(), chunk)
        except BrokenPipeError:
            _reader_gone = True


def _slot_arg(args):
    """Pull `--slot N` out of args; returns (N or None, remaining args)."""
    args = list(args)
    if "--slot" in args:
        i = args.index("--slot")
        try:
            return int(args[i + 1]), args[:i] + args[i + 2:]
        except (IndexError, ValueError):
            pass
    return None, args


def parse_opts(args):
    opts = {"pty": False, "shim": False, "key": None, "step": None, "steps": None, "rest": []}
    args = list(args)
    while args and args[0].startswith("-") and args[0] != "--":
        flag = args.pop(0)
        if flag == "--pty":
            opts["pty"] = True
        elif flag == "--shim":
            opts["shim"] = True
        elif flag in ("-k", "--key", "--step", "--steps") and args:
            name = {"-k": "key", "--key": "key"}.get(flag, flag[2:])
            opts[name] = args.pop(0)
        else:
            print(f"siga: unknown option {flag}", file=sys.stderr)
            return None
    if args and args[0] == "--":
        args = args[1:]
    opts["rest"] = args
    return opts


def shim_env(slot=None):
    """Env that loads the progress-library shims into Python and Node children."""
    root = Path(__file__).resolve().parent / "shims"
    py = str(root / "python")
    node = f"--require {root / 'node' / 'siga.cjs'}"
    return {
        "PYTHONPATH": os.pathsep.join(filter(None, [py, os.environ.get("PYTHONPATH")])),
        "NODE_OPTIONS": " ".join(filter(None, [node, os.environ.get("NODE_OPTIONS")])),
        "SIGA_SHIM": "1",
        # shims report back with `<SIGA_PY> -m siga set <value>`, onto this run's slot
        "SIGA_PY": sys.executable,
        "SIGA_SRC": str(core.SRC),
        "SIGA_TTY": core.own_tty() or "",
        "SIGA_SLOT": "" if slot is None else str(slot),
    }


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]
    slot_opt, args = _slot_arg(args)
    if cmd == "set":
        if len(args) != 1:
            print("usage: siga set [--slot N] <0..1 | NN% | N/M>", file=sys.stderr)
            return 2
        core.push(core.parse_value(args[0]), "run", slot=core.resolve_slot(slot_opt))
    elif cmd == "busy":
        core.push(0.0, "busy", slot=core.resolve_slot(slot_opt))
    elif cmd == "done":
        core.push(1.0, "done", slot=core.resolve_slot(slot_opt))
    elif cmd == "fail":
        slot = core.resolve_slot(slot_opt)
        core.push(float(core.load(slot).get("value", 0.0)), "fail", slot=slot)
    elif cmd == "end":
        rc = int(args[0]) if args else 0
        slot = core.resolve_slot(slot_opt, default="live")
        if rc == 0:
            core.push(1.0, "done", slot=slot)
        else:
            core.push(float(core.load(slot).get("value", 0.0)), "fail", slot=slot)
        return rc
    elif cmd == "clear":
        core.push(0.0, "clear", slot=core.resolve_slot(slot_opt))
    elif cmd == "refresh":
        for slot in range(core.SLOTS):  # a new window needs every slot's palette entry back
            core.reapply(slot)
    elif cmd == "bar":
        print(core.bar_string())
    elif cmd == "demo":
        now = "--now" in args
        args = [a for a in args if a != "--now"]
        try:
            seconds = float(args[0]) if args else 4.0
        except ValueError:
            print("usage: siga demo [seconds]   fill a bar from 0 to 100% (default 4 s)")
            return 0 if args[0] in ("-h", "--help") else 2
        if core.detect_backend() == "text":
            name = os.environ.get("TERM_PROGRAM") or "this terminal"
            print(f"siga demo: {name} can't show a live bar. "
                  "Run Claude Code directly in Kitty or Ghostty to see one.")
            return 0
        if os.environ.get("CLAUDECODE") and not now:
            core.arm_welcome("demo")
            print("siga demo: a bar fills for 4 s under Claude's next message.")
            return 0
        slot = core.resolve_slot(slot_opt)  # --now binds the welcome token's slot (clears its pending)
        if sys.stdout.isatty():
            print("  siga " + core.bar_string(slot=slot), flush=True)
        for i in range(21):
            core.push(i / 20, "run", slot=slot)
            time.sleep(seconds / 20)
        core.push(1.0, "done", slot=slot)
        print(f"siga demo: filled a bar in {seconds:g} s ({core.detect_backend()})")
    elif cmd == "status":
        last = core.load()
        print(f"{last.get('state')} {round(100 * float(last.get('value', 0)))}% ({core.detect_backend()})")
    elif cmd == "pipe":
        opts = parse_opts(args)
        if opts is None:
            return 2
        slot = core.resolve_slot(slot_opt, default="scratch")
        core.track(fd_reader(sys.stdin.fileno()), stdout_writer, opts["key"],
                   step=opts["step"], steps=opts["steps"], slot=slot)
    elif cmd == "run":
        opts = parse_opts(args)
        if opts is None:
            return 2
        args = opts["rest"]
        if not args:
            print("usage: siga run [--pty] [--shim] [--step RX [--steps N]] [-k KEY] -- <cmd...>",
                  file=sys.stderr)
            return 2
        slot = core.resolve_slot(slot_opt, default="scratch")
        env = shim_env(slot) if opts["shim"] else None
        read, wait = core.spawn(args, use_pty=opts["pty"], env=env)
        core.track(read, stdout_writer, opts["key"] or core.command_key(" ".join(args)),
                   clean=opts["pty"], step=opts["step"], steps=opts["steps"], slot=slot)
        return main(["end", str(wait()), "--slot", str(slot)])
    elif cmd == "selftest":
        from siga import selftest
        if "--snippets" in args:
            print(selftest.snippets())
            return 0
        if "--readme" in args:
            return 0 if selftest.readme_ok() else 1
        rest = [a for a in args if not a.startswith("--")]
        return selftest.run(rest[0] if rest else None, allow_network="--network" in args,
                                 capture="--capture" in args)
    elif cmd in ("off", "on"):
        from siga import hooks
        if cmd == "off":
            hooks.OFF_FILE.parent.mkdir(parents=True, exist_ok=True)
            hooks.OFF_FILE.touch()
        else:
            hooks.OFF_FILE.unlink(missing_ok=True)
        print(f"siga hooks {cmd}")
    elif cmd == "hook":
        from siga import hooks
        return hooks.run(args[0] if args else "")
    elif cmd == "setup":
        from siga import setup
        return setup.main(args)
    elif cmd == "animate":
        core.animate()
    else:
        print(f"siga: unknown command {cmd!r}", file=sys.stderr)
        return 2
    return 0


def entry():
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    entry()
