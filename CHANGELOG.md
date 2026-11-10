# Changelog

## 0.7.0 (2026-11-10)

- **Zero-config bars for mise.** Any `mise run <task>` whose median in mise's own history
  is 20 s or more gets a bar with no `[wrap]` pattern. Set `[mise] auto_wrap = <seconds>`
  in your config or a repo-local `siga.toml`; `0` turns it off. The hook only looks when the
  command contains `mise`, and caches each project's medians for 5 minutes.
- **The bar's colour says how siga knows the value.** Bright cyan-blue is an exact count
  the job printed. A calmer blue is a time estimate (mise's median, siga's record, a step's
  elapsed time). Amber, breathing slowly, means the estimate ran out and the job is still
  working (a step at its cap, or the whole bar at its 90% hold). A short white flash marks
  the start of each step of a mise task. Ghostty and Kitty both draw them.
- They use the three free state codes (5-7) of the existing colour encoding, so nothing
  else changes. The shader now carries a `siga-shader: 2` line; until the session-start
  hook has installed it, siga sends an older shader the plain running colour.

## 0.6.1 (2026-11-10)

- A piped job's bar now always finishes. `siga end` could not tell which bar its
  `siga pipe` had driven, so it finished the first live bar in slot order. When an
  interrupted command had left an older bar running, `end` finished that one, and the real
  job's bar froze short of done (seen on a deploy that stopped at 95%). `siga pipe` now
  hands its slot to the `siga end` that follows it. With no hand-over, `end` takes this
  pane's most recently pushed live bar instead of the lowest slot number.

## 0.6.0 (2026-11-10)

- A mise task that runs other tasks moves phase by phase. mise prints a `[task] $ cmd`
  header as each step starts; siga remembers the order of those steps from the task's last
  successful run and weights each one by its mise median. The bar stands at the weight of
  the steps already done plus the current step's share, so it follows the real work, not
  the clock. A slow step holds at its own boundary (90% of its share) instead of drifting
  toward the end, and the whole bar stays under 95% until the exit. A count printed inside
  a step fills only that step's share, so one step's `3/3` no longer reads as the whole
  task done.
- A failed run never replaces the learned steps: `siga pipe` parks them and `siga end 0`
  keeps them; `siga run` does the same through its own exit code.
- Steps that ran side by side (parallel `depends`) are recognised and left to the time
  estimate: they start together, so the learned run records each one far shorter than its
  median. A run that prints no step header (`--output summary`, `task.quiet`) also keeps
  the 0.5 behaviour, and a passed run with no steps forgets the old plan.
- The bar never steps back when the first step header arrives after the time estimate.
- One `mise tasks history` call now serves the task and all its steps.

## 0.5.1 (2026-11-10)

- The mise timing now works the way agents write commands. 0.5.0 only recognised a
  command that started with `mise run`, so `cd /repo && mise run deploy` fell back to the
  busy sweep. siga now finds the first `mise run <task>` after any `&&`, `;` or `||`, and
  reads mise's history in the directory of the last `cd` before it, because mise keeps a
  separate history per project. The hook passes it as `--mise-cwd <dir>`.

## 0.5.0 (2026-11-10)

- A `mise run <task>` is timed from mise's own run history. mise 2026.11.3+ records the
  duration of every task run, so siga reads the task's median
  (`mise tasks history --summary --json`) and fills the bar against it, ahead of its own
  last-5-runs record. The history is per project and shared by every terminal and session,
  so a task's first run in a new pane already has a real bar. The hook passes the task as
  `--mise <task>` to `siga pipe` / `siga run`; `siga run -- mise run <task>` finds it in the
  command. No mise, an older mise, or a task with no runs falls back to siga's record, then
  to the busy sweep. The lookup takes about 16 ms and is capped at 2 s.
- Docs: a "Best with mise" section in the README; HOW_IT_WORKS said a timed bar stops at
  99%, the code holds it at 90%.

## 0.4.0 (2026-10-27)

- Independent bars across herdr panes (issue #4). Under Ghostty + herdr the panes of one
  window share a single palette, so every pane's bar used to show the last value any pane
  pushed. The four slots are now a window-wide pool claimed across panes (each bar's glyph
  already encodes which palette entry it reads), so two panes get distinct entries instead of
  overwriting one. Cap: four distinct bars per Ghostty window; a fifth live across all panes
  recycles the oldest. Each slot records its owning pane, so a failed command reddens only its
  own bar. Single-pane Ghostty, direct Ghostty, Kitty and text are unchanged.
- State is split into a per-window doc (the shared bars + cursor, `win-<tty>.json`, written
  under an flock) and a per-pane doc (token binding + scratch, `pane-<tty>.json`), migrated
  from the old `state-<tty>.json`. Pure Python — effective on the next plugin load, no setup
  step and no Ghostty reload.

## 0.3.0 (2026-10-27)

- Bars are now independent. Each `⟦bar⟧` gets its own slot (a ring of four), so a finished
  bar freezes at its own result while the next job's bar fills, instead of every bar on
  screen following one shared value. Jobs still run one at a time; a fifth bar recycles the
  oldest slot, and a wrapped command with no token of its own drives a scratch slot that
  nothing draws. Ghostty only; on Kitty all bars still share one image.
- Ghostty: the Siga font now has four glyph families (U+10FB00–U+10FB4F), each slot keyed a
  distinct green and reading its own palette entry (252–255); the shader decodes the slot
  per pixel. `siga <verb> --slot N` acts on a specific slot.
- The bar now draws one rounded box per cell with the gap at the cell boundaries, so it no
  longer starts and ends with a half box (the gap used to fall inside each cell, pairing
  segments across the joins). Both the Ghostty shader and the Kitty image.
- Faster hooks. The `ps` that finds the window's tty is now cached on disk per terminal
  pane, not just per process, so a wrapped command no longer pays the ~90–180 ms `ps` before
  its bar appears — the first process in the pane resolves it, the rest read the cache. The
  launcher also starts Python with `-S` and the hooks import `tomllib`/`subprocess`/`shlex`
  only when a path needs them, trimming ~4–7 ms off every tool-call and message hook. No
  setup step; it takes effect on the next plugin load.
- **Reaching the bar changes needs `siga setup --apply` and a Ghostty config reload** (the
  glyph range grew). A new session refreshes the installed font, shader and config block for
  users who already opted in, then reloads Ghostty; SessionStart flags an out-of-date block.

## 0.2.1 (2026-10-27)

- A time-estimated bar now holds at 90%, not 99%, while the job is still running.
  A near-full bar read as "done"; the last tenth fills only on the real exit, so
  overrunning the estimate looks like "almost there", not finished. A trusted N/M
  count is still exact and uncapped.

## 0.2.0 (2026-10-27)

- Config is TOML. Wrap patterns live under `[wrap]` (`pipe = [...]`, `pty = [...]`) in
  `~/.config/siga/config.toml`, the bundled `data/wrap.default.toml`, and a new repo-local
  `siga.toml` (nearest one walking up from the working directory, or `$SIGA_PROJECT_CONFIG`)
  so a project can commit its own patterns. Replaces the line-based `wrap.txt`.
- Requires Python 3.11+ (for stdlib `tomllib`). Still zero third-party dependencies.
- A backgrounded command (a top-level `&`, told apart from `&&` and redirections) is no
  longer auto-wrapped, so the bar can't paint `done` while the detached job runs (#1).

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
