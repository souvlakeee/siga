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
  siga selftest [name] [--network] [--capture] | --snippets | --readme
                                run examples/ under a recorder and check every bar
  siga setup [--plan|--apply|--remove]
                                install the font and the Ghostty/Kitty config (shows the diff first)
  siga off | on                 pause / resume the Claude Code hooks (no wrapping, no bar swap)
  siga hook <event>             (internal) Claude Code hooks: pretooluse, posttoolfailure,
                                messagedisplay, sessionstart
  siga animate                  (internal) kitty frame loop

One value per terminal window: every bar in that window shows the same state. Progress comes from
N/M counts, NN% or ffmpeg time= in the output; without them, from how long the
same command (KEY) took before, or a busy sweep the first time.
"""
import os
import select
import subprocess
import sys
import time
from pathlib import Path

from siga import core


def fd_reader(fd):
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


def shim_env():
    """Env that loads the progress-library shims into Python and Node children."""
    root = Path(__file__).resolve().parent / "shims"
    py = str(root / "python")
    node = f"--require {root / 'node' / 'siga.cjs'}"
    return {
        "PYTHONPATH": os.pathsep.join(filter(None, [py, os.environ.get("PYTHONPATH")])),
        "NODE_OPTIONS": " ".join(filter(None, [node, os.environ.get("NODE_OPTIONS")])),
        "SIGA_SHIM": "1",
        # shims report back with `<SIGA_PY> -m siga set <value>`
        "SIGA_PY": sys.executable,
        "SIGA_SRC": str(core.SRC),
        "SIGA_TTY": core.own_tty() or "",
    }


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip())
        return 0
    cmd, args = argv[0], argv[1:]
    last = core.load()
    if cmd == "set":
        if len(args) != 1:
            print("usage: siga set <0..1 | NN% | N/M>", file=sys.stderr)
            return 2
        core.push(core.parse_value(args[0]), "run")
    elif cmd == "busy":
        core.push(0.0, "busy")
    elif cmd == "done":
        core.push(1.0, "done")
    elif cmd == "fail":
        core.push(float(last.get("value", 0.0)), "fail")
    elif cmd == "end":
        rc = int(args[0]) if args else 0
        if rc == 0:
            core.push(1.0, "done")
        else:
            core.push(float(last.get("value", 0.0)), "fail")
        return rc
    elif cmd == "clear":
        core.push(0.0, "clear")
    elif cmd == "refresh":
        core.push(float(last.get("value", 0.0)), last.get("state", "clear"))
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
        if sys.stdout.isatty():
            print("  siga " + core.bar_string(), flush=True)
        for i in range(21):
            core.push(i / 20, "run")
            time.sleep(seconds / 20)
        core.push(1.0, "done")
        print(f"siga demo: filled a bar in {seconds:g} s ({core.detect_backend()})")
    elif cmd == "status":
        print(f"{last.get('state')} {round(100 * float(last.get('value', 0)))}% ({core.detect_backend()})")
    elif cmd == "pipe":
        opts = parse_opts(args)
        if opts is None:
            return 2
        core.track(fd_reader(sys.stdin.fileno()), stdout_writer, opts["key"],
                   step=opts["step"], steps=opts["steps"])
    elif cmd == "run":
        opts = parse_opts(args)
        if opts is None:
            return 2
        args = opts["rest"]
        if not args:
            print("usage: siga run [--pty] [--shim] [--step RX [--steps N]] [-k KEY] -- <cmd...>",
                  file=sys.stderr)
            return 2
        env = shim_env() if opts["shim"] else None
        read, wait = core.spawn(args, use_pty=opts["pty"], env=env)
        core.track(read, stdout_writer, opts["key"] or core.command_key(" ".join(args)),
                   clean=opts["pty"], step=opts["step"], steps=opts["steps"])
        return main(["end", str(wait())])
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
