---
name: setup
description: Install what this terminal needs to draw siga's live progress bars (Kitty needs nothing; Ghostty gets the Siga font, a shader and a config block). Shows every change and asks before applying.
disable-model-invocation: true
---

# /siga:setup

Keep this short: the user sees every command's output, so never restate it.

1. Run `siga setup --plan`. Its first line names the terminal the user is in; talk only
   about that terminal.
2. If it lists no numbered steps, there is nothing to apply. Reply with one short line
   and stop.
3. Otherwise ask with AskUserQuestion: "Apply these changes?", with the options
   "Apply" (recommended) and "Not now". On "Not now", stop.
4. Run `siga setup --apply`. Reply in one or two lines: what was installed (each edited
   config keeps a timestamped backup), and siga's last line as printed.

siga adds a welcome bar under your final line by itself. Never write ⟦bar⟧ here and
never say a bar filled: you can't see it. To undo later: `siga setup --remove`.
