---
name: setup
description: Install what this machine's terminals need to draw siga's live progress bars (Kitty needs nothing; Ghostty gets the Siga font, a shader and a config block). Shows every change and asks before applying.
disable-model-invocation: true
---

# /siga:setup

1. Run `siga setup --plan` and show its output to the user exactly as printed. Its first
   line names the terminal the user is in; never say a different terminal than that line.
2. If it says "Nothing to set up" or "siga is set up", tell the user in one line and stop.
3. Otherwise ask with AskUserQuestion: "Apply these changes?", with the options
   "Apply" (recommended) and "Not now".
4. On "Apply", run `siga setup --apply` and report each `done:` line in one short list.
   Every edited config file keeps a timestamped backup next to it.
5. Relay the last line `--apply` prints (for example "Ghostty reloaded…") as is. Mention
   opening a new Ghostty window only if the font was installed.
6. To undo later: `siga setup --remove`.
