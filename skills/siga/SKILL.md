---
name: siga
user-invocable: false
description: Show a live progress bar for long-running work (builds, tests, downloads, renders, deploys, data jobs) in Ghostty or Kitty. Use before starting any command or job that will take more than a few seconds, and when wiring progress into scripts with siga run, siga pipe, --pty, --shim, --step or siga set.
---

# siga: one live bar per job

siga draws a progress bar that keeps filling after it is printed. You write a token
once; the terminal animates it while the job runs.

## Rules for you, Claude

1. **One bar per job, written once.** In the message that starts a long job, put the
   token on its own indented line with a short label:

       build ⟦bar⟧

   It fills by itself. Never write it again for the same job.
2. **No progress chatter.** Don't post "still running…", percentages, or a new message
   per poll. Wait in one foreground command, or in chained waits that print nothing new.
3. **Never paste bar glyphs or placeholder characters yourself.** Only the token `⟦bar⟧`.
4. **Report the result once** when the job ends: done, or the failure with its error.
   Don't add a second bar for the same job.
5. **Several jobs in a row** get one token each, at the start of each job.

The token works in Ghostty and Kitty with siga set up; elsewhere it shows a static bar.

## How the bar gets its progress

Inside Claude Code, build-like commands (npm/pnpm/bun builds and tests, cargo, go,
make, docker build, pytest, curl -o, wget, rsync, git clone, ffmpeg, yt-dlp, pip/uv…)
are wrapped automatically: their output and exit code pass through unchanged. Add
your own patterns under `[wrap]` in `~/.config/siga/config.toml`, or a repo-local
`siga.toml` (`pipe = ['<regex>']` / `pty = ['<regex>']`, anchored at the start of a command).

For anything else, pick the matching form:

| The command… | Use |
|---|---|
| prints `12/40`, `45%`, ffmpeg `time=` | `siga run -- <cmd>` |
| only draws its bar on a terminal (cargo, rich, Node, Go, Rust libraries) | `siga run --pty -- <cmd>` |
| uses tqdm, rich, click, cli-progress (exact values) | `siga run --shim -- <cmd>` (add `--pty` for cli-progress) |
| prints named steps | `siga run --step '<regex for a step line>' [--steps N] -- <cmd>` |
| prints nothing useful | `siga run -- <cmd>`: busy the first time, then the learned duration |
| is your own script | call `siga set 3/10` (or `30%`) between steps, then `siga done` / `siga fail`; or print `\e]9;4;1;30\e\\` (OSC 9;4) |
| must stay in a pipeline | `set -o pipefail; cmd 2>&1 \| siga pipe; siga end $?` |

`siga --help` lists every command. Each `⟦bar⟧` gets its own bar, and a finished one
freezes at its result, so a row of jobs each keep their own state. Only one bar is live at
a time, so run long jobs one after another, not in parallel.
