# How siga works

A terminal never redraws text it has already printed unless the program prints over it.
Claude Code's chat history is printed once. siga makes one part of that text change anyway:
the terminal keeps one bit of state (a palette color in Ghostty, an image in Kitty), and
siga changes that state instead of the text.

```
your build ──► siga run / pipe / hook ──► parser ──► state file (per tty)
                                                        │
                                   ┌────────────────────┴───────────────────┐
                                Ghostty                                    Kitty
                      OSC 4 palette entry 254                  PNG re-uploaded under one id
                      read by a custom shader                  shown by Unicode placeholders
```

## Ghostty: glyphs plus a shader

- **The font.** `Siga.ttf` has 20 glyphs at U+10FB00–U+10FB13, one per cell of the bar.
  They are color bitmaps (`sbix`), because Ghostty draws COLR glyphs in the text color,
  which would lose the key. Every pixel is a "key" color: red 0xFF, green 0x11, blue
  0x30 + 2·slot, with 4 slots per cell. The bitmaps carry a Display P3 ICC profile, so
  macOS doesn't shift the key colors on the way to the screen.
- **The config.** `font-codepoint-map = U+10FB00-U+10FB13=Siga` sends only those code points
  to the font. `custom-shader-animation = true` runs the shader every frame.
- **The shader** (`src/siga/data/siga.glsl`) checks each pixel. A pixel whose green/red
  and blue/red ratios match the key is part of the bar, and the ratio gives its slot,
  even after blending against the background. The shader then paints a segmented bar
  over the glyph's cell: 40 segments, rounded corners, a moving gradient while running,
  green when done, red when failed.
- **The value channel.** siga writes the value into palette entry 254 with OSC 4. The
  shader reads it from the palette uniform. Red and green carry 10 bits of progress,
  blue carries the state (clear, run, busy, done, fail). Every encoded color stays near
  the default entry, so a program that uses color 254 still looks right. The cursor
  color (OSC 12) would be the obvious channel, but Ghostty only refreshes shader
  uniforms when the screen is marked dirty, and OSC 12 doesn't mark it. OSC 4 does.
- **Glyph clipping.** Ghostty clips a glyph to its cell box (about 15×28 px in a 17×38 px
  cell at default size). The shader finds the real cell edges by scanning, and the design
  draws two segments per cell, so the gaps line up.

## Kitty: Unicode placeholders

- Kitty never draws private-use glyphs in color, so the font trick doesn't work there.
  Instead the bar is Kitty's
  [Unicode placeholder](https://sw.kovidgoyal.net/kitty/graphics-protocol/#unicode-placeholders):
  U+10EEEE repeated 20 times, where the first one carries row, column and ID diacritics.
- The image ID usually goes in the text's foreground color, but Claude's reply text has
  no color escapes. In default-colored text the low 24 bits of the ID read as 0, so siga
  uses an ID whose only set bits are the high byte, carried in the third diacritic.
- siga renders the bar as a PNG with a stdlib-only encoder and re-uploads it under the
  same ID (`a=T,U=1,q=2`). Every placeholder on screen shows the new image at once. A
  small animator process redraws at 20 fps while a bar is running, and exits when idle.

## Inside herdr

herdr is a multiplexer built on libghostty: it runs each pane's terminal itself and
redraws the result into the real terminal. A pane's processes descend from the detached
herdr server, so siga finds the real terminal from the herdr client processes instead: a
`herdr` with a tty, under a kitty or ghostty app.

- **Kitty:** herdr understands Kitty placeholders. When siga uploads the bar image to the
  pane, herdr stores it and re-places it on the real terminal over the placeholder cells
  (`a=p … c=20,r=1`). siga writes to the pane as usual. herdr re-sends every frame as raw
  RGBA, so the animator drops to 8 fps there.
- **Ghostty:** the bar glyphs pass through herdr as text, but herdr swallows OSC 4. siga
  writes the palette value straight to the herdr client's tty, where Ghostty's shader
  reads it.

## Other terminals

The token becomes `▰▰▰▱▱▱`, the value at the moment the message was shown.

## Where the progress comes from

`siga run -- cmd`, `cmd | siga pipe` and the Claude Code hook all feed output to one parser
(`src/siga/parse.py`):

1. **OSC 9;4** (`ESC ] 9 ; 4 ; state ; percent ST`), the progress escape that cargo,
   Windows Terminal, ConEmu and others use. Once a command sends it, siga trusts only it.
2. **Tool-specific rows**, priority 3: ffmpeg `time=` against `Duration:`, curl's meter,
   git's "Receiving objects", docker `#N [x/y]` steps, cargo's `[x/y]` header.
3. **Percentages**, priority 2.
4. **Ratios** (`12/40`, `12 of 40`), priority 1.

Inside one line the strongest source wins. Once a stronger source has appeared, weaker
ones are ignored for the rest of the run, so ffmpeg's closing `44.3%` stats line can't
undo its `time=` progress. A single stray ratio isn't trusted until it repeats.

Before parsing, terminal output is cleaned: CSI and OSC sequences are stripped,
`ESC[nG` counts as a carriage return and cursor-up as a new line, and an escape split
across two reads is held back until it is complete. With `--pty` the command runs on a
pseudo-terminal (for tools that only draw a bar on a terminal) and the cleaned lines are
what you see.

When nothing parses, the bar shows a busy sweep. siga remembers how long each command took,
so the next run fills by time and stops at 99% until the command exits. `--step REGEX`
counts named steps instead, and remembers how many there were.

`--shim` reads values from inside the program: a Python `sitecustomize` patches tqdm, rich
and click, and a Node `--require` patches cli-progress and progress. Each reports its
value with `siga set`.

## One state per window

Each window's bar is separate. siga finds the tty of the window it runs in by walking up
its parent processes, and keeps `~/.cache/siga/state-<tty>.json`. Two Claude Code sessions
in two windows don't overwrite each other's bars. Two jobs in one window share one bar.

## Claude Code hooks

The plugin (`hooks/hooks.json`) runs `bin/siga hook <event>`:

- **SessionStart** tells Claude the one-bar-per-job rule, refreshes the installed shader and
  font after a plugin update, and says if `/siga:setup` hasn't run yet.
- **PreToolUse (Bash)** rewrites build-like commands (patterns in
  `src/siga/data/wrap.default.txt`, plus `~/.config/siga/wrap.txt`) into
  `set -o pipefail; { cmd; } 2>&1 | siga pipe; siga end $?`, or `siga run --pty` for tools
  that need a terminal. A trailing filter such as `| tail -20` stays after siga, so the
  bar still sees everything. Commands that already call siga are left alone.
- **PostToolUseFailure (Bash)** leaves the bar red when a wrapped command fails, even if
  siga's own end step never ran (a timeout, an interrupt).
- **MessageDisplay** swaps `⟦bar⟧` for the terminal's bar characters on screen only. The
  transcript keeps the token. A token split
  across two streamed chunks is held back until it is complete.

`siga off` creates `~/.config/siga/disabled` and every hook passes through unchanged;
`siga on` removes it. `SIGA_DISABLE=1` does the same for one process.

## The launcher

`bin/siga` is a POSIX shell script. It finds Python once (a uv-managed Python if uv is
installed, else `python3` 3.9 or newer), caches the path, and runs `python -m siga` with
`src/` on `PYTHONPATH`. siga uses the standard library only, so there's nothing to install.
A hook call takes about 25 ms, almost all of it Python startup.
