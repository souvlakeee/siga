---
name: setup
description: Install what this machine's terminals need to draw siga's live progress bars (Kitty needs nothing; Ghostty gets the Siga font, a shader and a config block). Shows every change and asks before applying.
disable-model-invocation: true
---

# /siga:setup

1. Run `siga setup --plan` and show its output to the user exactly as printed. Its first
   line names the terminal the user is in; never say a different terminal than that line.
2. If it says "Nothing to set up" or "siga is set up", tell the user in one line and go
   to step 6.
3. Otherwise ask with AskUserQuestion: "Apply these changes?", with the options
   "Apply" (recommended) and "Not now". On "Not now", stop.
4. On "Apply", run `siga setup --apply` and report each `done:` line in one short list.
   Every edited config file keeps a timestamped backup next to it.
5. Relay the "Ghostty reloaded…" line, if printed, as is.
6. Welcome run. If the last line siga printed starts with "Try it", show the bar now: in
   one message, write the token on its own indented line,

       welcome ⟦bar⟧

   and run `siga demo` in that same message. It fills for 4 seconds; then say in one line
   that the bar should have filled, and that if it stayed empty the user should tell you.
   If the last line says to open a new Ghostty window, relay it as is and skip the demo.
7. To undo later: `siga setup --remove`.
