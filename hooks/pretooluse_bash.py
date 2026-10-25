#!/usr/bin/env python3
"""PreToolUse(Bash): wrap build-like commands so pbar tracks their output.

Patterns (hooks/wrap.default.txt, plus ~/.config/pbar/wrap.txt) match where a command
starts: the line start or after ; && || | ( $( `, past env assignments and prefixes
like sudo or time. A "pipe" match keeps the command in Claude's own shell and pipes
it through `pbar pipe`; a "pty" match runs it on a pseudo-terminal via `pbar run
--pty`, for tools that only draw progress there. Either way the exit code is kept.
Prints nothing for commands it leaves alone.
"""
import json
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pbar_core as core  # noqa: E402

SKIP = re.compile(r"\bpbar\b|job\.sh|\bjob:|<<")
FILTERS = {"tail", "head", "grep", "egrep", "rg", "sed", "awk", "wc", "cut", "sort", "uniq", "tee", "less"}
PREFIXES = {"sudo", "time", "nice", "nohup", "env", "command", "exec", "caffeinate"}
ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*")


def patterns():
    rules = []
    for f in (ROOT / "hooks" / "wrap.default.txt", Path.home() / ".config" / "pbar" / "wrap.txt"):
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            mode, _, rx = line.partition(" ")
            if mode not in ("pipe", "pty"):
                mode, rx = "pipe", line
            rules.append((mode, re.compile(rx.strip())))
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
        return "set -o pipefail; pbar run --pty -k %s -- sh -c %s%s" % (key, shlex.quote(body), tail)
    return "set -o pipefail; { %s\n} 2>&1 | pbar pipe -k %s%s; pbar end $?" % (body, key, tail)


def decide(command):
    if not command or SKIP.search(command) or command.rstrip().endswith("&"):
        return None
    heads = segment_heads(command)
    modes = [mode for mode, rx in patterns() if any(rx.search(h) for h in heads)]
    if not modes:
        return None
    return "pty" if "pty" in modes else "pipe"


def main():
    event = json.load(sys.stdin)
    tool_input = event.get("tool_input") or {}
    command = tool_input.get("command", "")
    mode = decide(command)
    if not mode:
        return
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {**tool_input, "command": wrap(command, mode)},
            "additionalContext": "pbar is tracking this command with a live progress bar; "
                                 "its output and exit code pass through unchanged.",
        },
    }
    print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a broken hook must never change what Claude Code does
        pass
