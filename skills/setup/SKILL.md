---
name: setup
description: Install what the terminal needs to draw siga's live progress bars (the Siga font, the Ghostty shader and config block). Shows every change and asks before applying.
disable-model-invocation: true
---

# /siga:setup

1. Run `siga setup --plan` and show its output to the user exactly as printed.
2. If it says siga is already set up, tell the user and stop.
3. Otherwise ask with AskUserQuestion: "Apply these changes?", with the options
   "Apply" (recommended) and "Not now".
4. On "Apply", run `siga setup --apply` and report each `done:` line in one short list.
   Every edited config file keeps a timestamped backup next to it.
5. Tell the user: Ghostty reloads its config now; a newly installed font is picked up
   by new Ghostty windows (open one, or restart Ghostty). Kitty needs nothing.
6. To undo later: `siga setup --remove`.
