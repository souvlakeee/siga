<p align="center"><img src=".claude-plugin/icon.png" width="96" alt=""></p>

<h1 align="center">siga</h1>

<p align="center"><b>Progress bars that keep filling after they are printed.</b><br>
<i>Siga-siga</i> means "slowly-slowly" in Cyprus. Your build can take its time; the bar keeps up.</p>

| Claude Code today | With siga |
|---|---|
| <a href="docs/media/before.mp4"><img src="docs/media/before.gif" alt="Without siga: every wait prints another progress line"></a> | <a href="docs/media/after.mp4"><img src="docs/media/after.gif" alt="With siga: one bar fills in place"></a> |
| Every wait prints another progress line. | One bar, written once, fills in place. |

Claude writes the token `⟦bar⟧` once, in the message that starts a long job. siga turns it
into a live bar on screen and keeps it moving while the build, download or render runs,
inside text that was already printed. The terminal does the drawing: a GPU shader in
Ghostty, an image placeholder in Kitty.

## Install

In Claude Code (2.1.275 or later):

```
/plugin install siga --marketplace souvlakeee/siga
/siga:setup
```

`/siga:setup` shows exactly what it will change (a font, a shader, a marked block in your
Ghostty config, with backups) and asks before applying. Kitty needs nothing. siga runs on
Python 3.9+ from the standard library only; with [uv](https://docs.astral.sh/uv/)
installed it picks a fast uv-managed Python by itself.

## Where it works

| Terminal ↓ / Harness → | Claude Code | OpenCode | Codex |
|---|---|---|---|
| **Ghostty** 1.3+ | ✅ live bar (font + shader) | TBD | TBD |
| **Kitty** 0.49+ | ✅ live bar (image placeholder) | TBD | TBD |

In other terminals the token becomes a static `▰▰▰▱▱▱` bar. The `siga` CLI itself works
anywhere.

## How the bar gets its progress

Inside Claude Code nothing extra is needed: build-like commands (npm, pnpm, bun, cargo, go,
make, docker build, pytest, pip, uv, curl -o, wget, rsync, git clone, ffmpeg, yt-dlp, …)
are wrapped automatically, and their output and exit code pass through unchanged. Add
your own patterns to `~/.config/siga/wrap.txt`.

### Keep your progress library

siga doesn't replace your progress bar, it reads it. Every row below is a tested script
in [`examples/`](examples/) (`bin/siga selftest` runs all of them, offline):

<!-- examples:start -->
| Family | Tool | Command | Example |
|---|---|---|---|
| Shell tools | curl | `siga run -- curl --limit-rate 8M -o big.bin "$URL"` | [curl.sh](examples/shell/curl.sh) |
| Shell tools | curl -# | `siga run -- curl -# --limit-rate 8M -o big.bin "$URL"` | [curl_bar.sh](examples/shell/curl_bar.sh) |
| Shell tools | ffmpeg | `siga run -- ffmpeg -y -re -i in.mp4 -c:v libx264 -preset ultrafast out.mp4` | [ffmpeg.sh](examples/shell/ffmpeg.sh) |
| Shell tools | git clone | `siga run -- git clone --progress "file://$WORK/origin.git" copy` | [git.sh](examples/shell/git.sh) |
| Shell tools | any command, piped | `build 2>&1 \| siga pipe; siga end $?` | [pipe_anything.sh](examples/shell/pipe_anything.sh) |
| Shell tools | a failing piped command ends red, with its own exit code | `build 2>&1 \| siga pipe; siga end $?` | [pipe_fail.sh](examples/shell/pipe_fail.sh) |
| Shell tools | pv | `siga run -- sh -c 'pv -f -i 0.5 -L 8m f1.bin > copy.bin'` | [pv.sh](examples/shell/pv.sh) |
| Shell tools | rsync | `siga run -- rsync -a --info=progress2 --bwlimit=8m src/ dst/` | [rsync.sh](examples/shell/rsync.sh) |
| Shell tools | a custom script with named steps | `siga run --step '^==> ' --steps 5 -- ./deploy.sh` | [steps.sh](examples/shell/steps.sh) |
| Shell tools | wget | `siga run -- wget --limit-rate=8m --progress=bar:force -O big.bin "$URL"` | [wget.sh](examples/shell/wget.sh) |
| Shell tools | yt-dlp | `siga run -- yt-dlp --newline --limit-rate 8M -o video.bin "$URL"` | [yt-dlp.sh](examples/shell/yt-dlp.sh) |
| Build tools | cargo build | `siga run --pty -- cargo build` | [cargo.sh](examples/build/cargo.sh) |
| Build tools | docker build | `siga run -- docker build --progress=plain --no-cache -t siga-demo .` | [docker.sh](examples/build/docker.sh) |
| Build tools | make | `siga run -- make` | [make_eta.sh](examples/build/make_eta.sh) |
| Build tools | pytest -v | `siga run -- pytest -v` | [pytest.sh](examples/build/pytest.sh) |
| Python libraries | alive-progress | `siga run --pty -- python alive_demo.py` | [alive.sh](examples/python/alive.sh) |
| Python libraries | click.progressbar | `siga run --pty -- python click_demo.py` | [click.sh](examples/python/click.sh) |
| Python libraries | rich | `siga run --pty -- python rich_demo.py` | [rich.sh](examples/python/rich.sh) |
| Python libraries | rich, exact values via --shim | `siga run --shim -- python rich_demo.py` | [rich_shim.sh](examples/python/rich_shim.sh) |
| Python libraries | tqdm | `siga run -- python tqdm_demo.py` | [tqdm.sh](examples/python/tqdm.sh) |
| Node libraries | cli-progress | `siga run --pty -- node cli_progress_demo.js` | [cli_progress.sh](examples/node/cli_progress.sh) |
| Node libraries | cli-progress, exact values via --shim | `siga run --pty --shim -- node cli_progress_demo.js` | [cli_progress_shim.sh](examples/node/cli_progress_shim.sh) |
| Node libraries | progress | `siga run --pty -- node progress_demo.js` | [progress.sh](examples/node/progress.sh) |
| Go libraries | vbauerster/mpb | `siga run --pty -- ./demo` | [mpb.sh](examples/go/mpb.sh) |
| Go libraries | cheggaaa/pb | `siga run --pty -- ./demo` | [pb.sh](examples/go/pb.sh) |
| Go libraries | schollz/progressbar | `siga run --pty -- ./demo` | [schollz.sh](examples/go/schollz.sh) |
| Rust libraries | indicatif | `siga run --pty -- ./target/debug/indicatif-demo` | [indicatif.sh](examples/rust/indicatif.sh) |
| OSC 9;4 emitters | cargo's own OSC 9;4 | `CARGO_TERM_PROGRESS_TERM_INTEGRATION=true siga run --pty -- cargo build` | [cargo.sh](examples/osc/cargo.sh) |
| OSC 9;4 emitters | OSC 9;4 from Python | `siga run -- python3 job.py` | [python.sh](examples/osc/python.sh) |
| OSC 9;4 emitters | OSC 9;4 from a shell script | `work \| siga pipe; siga end $?` | [shell.sh](examples/osc/shell.sh) |
<!-- examples:end -->

Some libraries only draw on a terminal (cargo, rich, the Node, Go and Rust libraries):
`--pty` runs them on a pseudo-terminal and hands back clean, plain output. `--shim` reads
exact values from inside tqdm, rich, click, cli-progress and progress, with no change to
the app.

### Your own scripts and builders

| Your command… | Use |
|---|---|
| prints counts or percentages (`[12/40]`, `45%`) | `siga run -- ./build.sh` |
| prints named steps | `siga run --step '^==> ' -- ./deploy.sh` (the step count is learned from the last run, or pass `--steps 5`) |
| prints nothing useful | `siga run -- make`: a busy sweep the first time, then it fills by the duration it learned |
| is yours and knows exact values | call `siga set 3/10` (or `30%`) between steps and `siga done` / `siga fail` at the end, or print the standard `\e]9;4;1;30\e\\` (OSC 9;4) |
| uses tqdm, rich, click or cli-progress | `siga run --shim -- python train.py` |
| has to stay in a pipe | `set -o pipefail; tool 2>&1 \| siga pipe; siga end $?` (pipefail keeps the tool's exit code) |

`siga --help` lists every command.

### Without Claude Code

```
git clone https://github.com/souvlakeee/siga && cd siga
bin/siga setup --apply          # or --plan to see the changes first
bin/siga run -- cargo build
```

Print the bar yourself with `bin/siga bar`; it keeps filling while `siga run` works.

## How it works

- **Ghostty:** the bar is 20 private-use glyphs from a tiny font, each painted in a "key"
  color that encodes its position. A custom shader finds those pixels on every frame and
  repaints them from the current value, which siga sends as an OSC 4 palette color.
- **Kitty:** the bar is a Kitty image placeholder in plain text; siga re-uploads the
  image, and every copy on screen updates at once.
- **Claude Code:** a `MessageDisplay` hook swaps `⟦bar⟧` for the right characters on screen
  only (the transcript keeps the token), a `PreToolUse` hook wraps build-like commands, and
  a `SessionStart` hook tells Claude the one-bar-per-job rule.

The details, and the terminal quirks that shaped them, are in
[docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Limitations

- One bar value per terminal window: two jobs running at once in one window share a bar.
- Ghostty 1.3+ and Kitty 0.49+, tested on macOS. Linux should work but is untested.
- Each hook call costs about 25 ms (Python startup).
- `siga off` pauses the hooks, `siga on` resumes them, `siga setup --remove` uninstalls
  the terminal pieces.

## Prior art and thanks

- [ghostty-blackhole](https://github.com/s0xDk/ghostty-blackhole) showed that a program can
  feed a value to a Ghostty shader through a color escape.
- Kitty's [Unicode placeholders](https://sw.kovidgoyal.net/kitty/graphics-protocol/#unicode-placeholders)
  make images part of the text.
- [Fira Code](https://github.com/tonsky/FiraCode) shipped the first progress-bar glyphs
  in a font.

## License

MIT
