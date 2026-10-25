# Changelog

## 0.1.9 (2026-10-25)

- Live bars inside herdr 0.9.5+. siga finds the real terminal from the herdr client.
  - Kitty: herdr re-places the bar image itself, and the animator runs at 8 fps there.
  - Ghostty: the palette value goes straight to the client's tty, because herdr swallows
    OSC 4.
- `siga setup` and the session context say "Kitty (through herdr)".

## 0.1.8 (2026-10-25)

- The welcome bar also shows right after a fresh Ghostty install: open windows pick up
  the new font after the config reload, so no new window is needed.
- `siga setup --apply` no longer repeats the terminal line from `--plan`.
- `siga demo --help` prints usage instead of crashing.

## 0.1.7 (2026-10-25)

- Terminals without live bars (herdr, tmux, Terminal.app) get one line that names them,
  from both `siga setup` and `siga demo`; no more Ghostty advice from Kitty or herdr.
- Inside Claude Code, `siga demo` puts its bar under Claude's next message, so it shows
  even when Claude doesn't write the token.

## 0.1.6 (2026-10-25)

- The SessionStart context names the terminal ("This window is Kitty."), so Claude stops
  guessing.
- README: `/reload-plugins` after install; no restart needed.

## 0.1.5 (2026-10-25)

- The welcome bar no longer depends on Claude: `siga setup` arms it, and the MessageDisplay
  hook adds `welcome ⟦bar⟧` under Claude's next message and fills it right then.
- `siga setup` touches only the terminal it runs in. In Kitty there is nothing to apply
  and nothing to ask; Ghostty steps appear only in a Ghostty window.
- `/siga:setup` is shorter: Claude never restates output or claims a bar filled.
- The siga:siga skill is hidden from the `/` menu (`user-invocable: false`).

## 0.1.4 (2026-10-25)

- `siga demo [seconds]` fills a bar from 0 to 100% (default 4 s).
- `/siga:setup` ends with a welcome run: Claude writes `⟦bar⟧` and runs `siga demo`, so
  the bar fills on screen right after setup. After a fresh Ghostty font install it asks
  for a new window first.
- The `done: append to …` line no longer ends in a colon.

## 0.1.3 (2026-10-25)

- `siga setup` names the terminal you're in. Kitty is told it needs nothing; the Ghostty
  steps appear only when Ghostty is installed. "Ghostty reloaded" prints only when a
  Ghostty process was signalled.
- `/siga:setup` relays siga's own words instead of always talking about Ghostty.
- README: the install takes `/plugin marketplace add` and then `/plugin install`.

## 0.1.2 (2026-10-25)

- The SessionStart rule now tells Claude to use `siga run` for commands the hook doesn't
  wrap, and to load the siga:siga skill.
- Path-prefixed tools such as `.venv/bin/pip` and `./node_modules/.bin/vite` are wrapped
  automatically.
- Shorter README.

## 0.1.1 (2026-10-25)

- `/siga:setup` no longer crashes Ghostty on macOS. The config reload sent signal 12,
  which is SIGUSR2 on Linux but SIGSYS on macOS; it now sends `signal.SIGUSR2`.

## 0.1.0 (2026-10-25)

First release.

- Live progress bars inside already-printed text: Ghostty 1.3+ (Siga font and a custom
  shader) and Kitty 0.49+ (Unicode placeholders). Other terminals get a static bar.
- Claude Code plugin: the `⟦bar⟧` token, automatic wrapping of build-like Bash commands,
  failed commands turn the bar red, and a one-bar-per-job rule for Claude.
- `/siga:setup`: shows every change, asks, then installs the font, the shader and the
  Ghostty config block, with backups. `siga setup --remove` undoes it.
- `siga run`, `siga pipe`, `siga set` / `done` / `fail`, with `--pty`, `--shim`,
  `--step` and learned durations.
- Reads OSC 9;4, curl, wget, git, rsync, pv, ffmpeg, yt-dlp, docker, cargo, make, pytest,
  tqdm, rich, click, alive-progress, cli-progress, progress, mpb, pb,
  schollz/progressbar and indicatif: 30 tested examples.
- `siga off` / `siga on` pause and resume the hooks.
