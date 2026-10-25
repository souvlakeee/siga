#!/usr/bin/env python3
"""MessageDisplay: show the live bar wherever Claude wrote the ⟦bar⟧ token.

Display only: the transcript and what Claude reads keep the token. A token split
across two deltas is held back until the next delta (or the final one) arrives.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pbar_core as core  # noqa: E402

TOKEN = "⟦bar⟧"
HELD = core.CACHE / "md"


def show(text):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": text}}))


def main():
    event = json.load(sys.stdin)
    delta = event.get("delta", "")
    held_file = HELD / str(event.get("message_id", "none"))
    try:
        held = held_file.read_text()
        held_file.unlink()
    except OSError:
        held = ""
    text = held + delta
    if TOKEN[0] not in text:
        if held:
            show(text)
        return

    keep = ""
    if not event.get("final"):
        for k in range(len(TOKEN) - 1, 0, -1):
            if text.endswith(TOKEN[:k]):
                text, keep = text[:-k], TOKEN[:k]
                break
    if keep:
        HELD.mkdir(parents=True, exist_ok=True)
        held_file.write_text(keep)

    if TOKEN in text:
        backend = core.detect_backend()
        text = text.replace(TOKEN, core.bar_string(backend))
        if backend == "kitty":
            # a placeholder shows nothing until this window has the image
            subprocess.Popen([sys.executable, str(ROOT / "pbar"), "refresh"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    show(text)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a broken hook must never change what Claude Code does
        pass
