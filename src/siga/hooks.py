"""Claude Code hooks for siga, one entry point: `siga hook <event>` reads the event on stdin.

pretooluse       wrap build-like Bash commands so siga tracks their output. Patterns
                 (data/wrap.default.toml, ~/.config/siga/config.toml, and a repo-local
                 siga.toml, all under [wrap]) match where a command starts: the line
                 start or after ; && || | ( $( `, past env
                 assignments and prefixes like sudo or time. "pipe" keeps the command in
                 Claude's own shell and pipes it through `siga pipe`; "pty" runs it on a
                 pseudo-terminal via `siga run --pty`. Either way the exit code is kept.
posttoolfailure  mark the bar failed when a wrapped command died before `siga end`
messagedisplay   show the live bar wherever Claude wrote the ⟦bar⟧ token (display only:
                 the transcript and what Claude reads keep the token)
sessionstart     tell Claude how to use the bar, keep the installed shader current, and
                 point at /siga:setup when the font or terminal config is missing

Every hook prints nothing when it has nothing to do, and never raises: a broken hook
must not change what Claude Code does. SIGA_DISABLE=1, or `siga off` (a file in
~/.config/siga), turns them all off.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from siga import core

SKIP = re.compile(r"\bsiga\b|job\.sh|\bjob:|<<")
FILTERS = {"tail", "head", "grep", "egrep", "rg", "sed", "awk", "wc", "cut", "sort", "uniq", "tee", "less"}
PREFIXES = {"sudo", "time", "nice", "nohup", "env", "command", "exec", "caffeinate"}
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*")
TOKEN = "⟦bar⟧"
RULE = (
    "siga draws live progress bars in this terminal. Before a long build, test, download or "
    "render, write the token ⟦bar⟧ once, on its own indented line with a label (`  build ⟦bar⟧`), "
    "in the message that starts the job; it fills by itself. Never write it twice for one job, "
    "never post progress updates or paste bar glyphs, and report the result once at the end. "
    "Commands the hook does not wrap: run them as `siga run -- <cmd>` (`--pty` if the tool only "
    "draws a bar on a terminal). Load the siga:siga skill before any long job for the full table."
)


def project_config():
    """A repo's own siga.toml, so wrap patterns live with the code they describe.
    `$SIGA_PROJECT_CONFIG` names it outright; otherwise it is the nearest siga.toml
    walking up from the working directory."""
    env = os.environ.get("SIGA_PROJECT_CONFIG")
    if env:
        return Path(env)
    try:
        here = Path.cwd()
    except OSError:
        return None
    for d in (here, *here.parents):
        f = d / "siga.toml"
        if f.is_file():
            return f
    return None


def patterns():
    rules = []
    files = [core.DATA / "wrap.default.toml", Path.home() / ".config" / "siga" / "config.toml"]
    proj = project_config()
    if proj:
        files.append(proj)
    for f in files:
        try:
            conf = tomllib.loads(f.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            continue  # a missing or malformed config must never break wrapping
        wrap = conf.get("wrap", {})
        for mode in ("pipe", "pty"):
            for rx in wrap.get(mode, []):
                if not isinstance(rx, str):
                    continue
                try:
                    rules.append((mode, re.compile(rx)))
                except re.error:
                    continue
    return rules


def scan(command):
    """Top-level segment starts, `|` positions and list separators (; && || &), ignoring quotes."""
    starts, pipes, seps = [0], [], []
    i, quote, n = 0, None, len(command)
    while i < n:
        c = command[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "\\":
            i += 2
            continue
        elif command.startswith(("&&", "||", "$("), i):
            if command[i] != "$":
                seps.append(i)
            starts.append(i + 2)
            i += 2
            continue
        elif c in ";&|(\n`":
            if c == "|":
                pipes.append(i)
            elif c in ";&\n":
                seps.append(i)
            starts.append(i + 1)
        i += 1
    return starts, pipes, seps


def segment_heads(command):
    """Each segment with leading env assignments and prefixes like sudo/time removed."""
    starts, _, _ = scan(command)
    heads = []
    for s in starts:
        words = command[s:].lstrip().split()
        while words and (ASSIGN.fullmatch(words[0]) or words[0] in PREFIXES):
            words.pop(0)
        if words:
            words[0] = words[0].rsplit("/", 1)[-1]  # .venv/bin/pip matches the pip rule
            heads.append(" ".join(words))
    return heads


def split_filter(command):
    """(body, " | filter ...") when the command ends in an output filter, else (command, "")."""
    _, pipes, seps = scan(command)
    if not pipes:
        return command, ""
    last = pipes[-1]
    if any(s > last for s in seps):  # `a | head -1; b`: the filter belongs to a, not to the end
        return command, ""
    try:
        first = shlex.split(command[last + 1:])[0]
    except (ValueError, IndexError):
        return command, ""
    if first not in FILTERS:
        return command, ""
    body = re.sub(r"\s*2>&1\s*$", "", command[:last].rstrip())
    return body, " " + command[last:].strip()


def add_git_progress(command):
    # git only prints clone/fetch progress to a terminal unless asked
    return re.sub(r"\bgit\s+(clone|fetch|pull)\b(?![^;&|]*--progress)", r"git \1 --progress", command)


def wrap(command, mode):
    key = core.command_key(command)
    body, tail = split_filter(command)
    body = add_git_progress(body)
    if mode == "pty":
        return "set -o pipefail; siga run --pty -k %s -- sh -c %s%s" % (key, shlex.quote(body), tail)
    return "set -o pipefail; { %s\n} 2>&1 | siga pipe -k %s%s; siga end $?" % (body, key, tail)


def backgrounds(command):
    """True when a top-level `&` runs part of the command in the background.

    The launcher then returns before the detached work ends, so a wrapping
    `siga pipe`/`siga run` paints `done` the moment the launcher exits while the
    real job is still running (issue #1). A backgrounding `&` is a control
    operator, so it is told apart from `&&` and from redirections (`>&`, `&>`,
    `2>&1`), whose `&` is adjacent to `<`, `>` or another `&`. A job that
    detaches its OWN work (an inner `nohup`/daemon in a script we just invoke)
    cannot be seen from the command text — it drives the bar itself with
    `siga set`/`siga done`, the pattern the README documents.
    """
    _, _, seps = scan(command)
    for i in seps:
        if command[i] != "&":
            continue
        prev = command[i - 1] if i > 0 else ""
        nxt = command[i + 1] if i + 1 < len(command) else ""
        # tuple membership, not `in "<>&"`: an empty string (at a boundary) is a
        # substring of every string, so `"" in "<>&"` is True and would wrongly
        # treat a trailing `&` as a redirection.
        if prev in ("<", ">", "&") or nxt in ("<", ">", "&"):
            continue
        return True
    return False


def decide(command):
    if not command or SKIP.search(command) or backgrounds(command):
        return None
    heads = segment_heads(command)
    modes = [mode for mode, rx in patterns() if any(rx.search(h) for h in heads)]
    if not modes:
        return None
    return "pty" if "pty" in modes else "pipe"


def pretooluse(event):
    tool_input = event.get("tool_input") or {}
    command = tool_input.get("command", "")
    mode = decide(command)
    if not mode:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {**tool_input, "command": wrap(command, mode)},
            "additionalContext": "siga is tracking this command with a live progress bar; "
                                 "its output and exit code pass through unchanged.",
        },
    }


def posttoolfailure(event):
    command = (event.get("tool_input") or {}).get("command", "")
    if "siga pipe" in command or "siga run" in command:
        st = core.load()
        if st.get("state") in core.LIVE:
            core.push(float(st.get("value", 0.0)), "fail")
    return None


def messagedisplay(event):
    held_dir = core.CACHE / "md"
    held_file = held_dir / str(event.get("message_id", "none"))
    try:
        held = held_file.read_text()
        held_file.unlink()
    except OSError:
        held = ""
    text = held + event.get("delta", "")
    label = _take_welcome() if event.get("final") else None
    if label:
        # the bar fills from the moment it appears, not before
        text += f"\n\n  {label} {TOKEN}"
        core.spawn_detached(["demo", "--now"])
    if TOKEN[0] not in text:
        return _display(text) if held else None
    keep = ""
    if not event.get("final"):
        # a token split across two deltas waits for the next one
        for k in range(len(TOKEN) - 1, 0, -1):
            if text.endswith(TOKEN[:k]):
                text, keep = text[:-k], TOKEN[:k]
                break
    if keep:
        held_dir.mkdir(parents=True, exist_ok=True)
        held_file.write_text(keep)
    if TOKEN in text:
        backend = core.detect_backend()
        text = text.replace(TOKEN, core.bar_string(backend))
        if backend == "kitty":
            # a placeholder shows nothing until this window has the image
            core.spawn_detached(["refresh"])
    return _display(text)


def _take_welcome(max_age=300):
    """The bar's label, once, after `siga setup` or `siga demo` armed it (None if stale)."""
    try:
        armed, _, label = core.WELCOME.read_text().partition(" ")
        core.WELCOME.unlink()
        fresh = time.time() - float(armed) < max_age
    except (OSError, ValueError):
        return None
    return (label or "welcome") if fresh else None


def _display(text):
    return {"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": text}}


def sessionstart(event):
    from siga import setup
    where = {"kitty": "Kitty", "ghostty": "Ghostty"}.get(core.detect_backend())
    if where and os.environ.get("TERM_PROGRAM") == "herdr":
        where += " (through herdr)"
    other = os.environ.get("TERM_PROGRAM") or "a terminal siga can't animate"
    context = RULE + (f" This window is {where}." if where else
                      f" This window is {other}: bars here stay static.")
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    try:
        setup.refresh_installed()
        missing = setup.missing()
    except Exception:
        missing = []
    if missing:
        out["systemMessage"] = "siga: " + "; ".join(missing) + ". Run /siga:setup to finish installing."
    return out


HOOKS = {"pretooluse": pretooluse, "posttoolfailure": posttoolfailure,
         "messagedisplay": messagedisplay, "sessionstart": sessionstart}


OFF_FILE = Path.home() / ".config" / "siga" / "disabled"


def run(name):
    if os.environ.get("SIGA_DISABLE") == "1" or OFF_FILE.exists() or name not in HOOKS:
        return 0
    try:
        out = HOOKS[name](json.load(sys.stdin))
        if out:
            print(json.dumps(out))
    except Exception:
        pass
    return 0
