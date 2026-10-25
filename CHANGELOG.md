# Changelog

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
