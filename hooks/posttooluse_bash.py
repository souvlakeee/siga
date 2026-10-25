#!/usr/bin/env python3
"""PostToolUseFailure(Bash): backstop for wrapped commands that never reached `pbar end`.

An interrupted or killed command leaves the bars live; mark them failed.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pbar_core as core  # noqa: E402


def main():
    event = json.load(sys.stdin)
    command = (event.get("tool_input") or {}).get("command", "")
    if "pbar pipe" not in command:
        return
    st = core.load()
    if st.get("state") in core.LIVE:
        core.push(float(st.get("value", 0.0)), "fail")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a broken hook must never change what Claude Code does
        pass
