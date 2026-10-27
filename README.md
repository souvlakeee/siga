<img src="docs/media/siga-siga.jpg" align="left" width="250" alt="An old Cypriot man resting in the shade by a blue shutter, a coffee on the table and a cat asleep at his feet">

# siga

**Progress bars that keep filling after they are printed.**

*Σιγά-σιγά* (siga-siga) is Cypriot for "slowly, slowly". Claude writes one bar, once, and it fills in place while the job runs — no stream of "still building… 40%… 70%…". It keeps filling even after that line scrolls up.

<br clear="left">

<a href="docs/media/after.mp4"><img src="docs/media/after.gif" width="900" alt="With siga: a bar under Claude's message fills while cargo compiles, then turns green"></a>

## Install

In Claude Code 2.1.275+:

```
/plugin marketplace add souvlakeee/siga
/plugin install siga@siga
/reload-plugins
/siga:setup
```

`/siga:setup` installs a font and a Ghostty shader (shown first, backed up). Kitty needs nothing. Python 3.11+, standard library only.

## How it works

A terminal never redraws text it has already printed. siga changes one thing anyway: in **Ghostty** the bar is a row of glyphs that a small **GPU shader repaints every frame** from a value siga sends as an OSC 4 palette color; in **Kitty** the bar is an image siga re-uploads in place. So the bar is a live region inside a line that was printed once. In Claude Code a hook swaps the `⟦bar⟧` token for the bar on screen and wraps build commands so siga can read their progress.

## Config

Wrap patterns are TOML, under `[wrap]`. Three files merge, in order: the bundled defaults, your `~/.config/siga/config.toml` (all projects), and a repo-local `siga.toml` committed with one project.

```toml
# siga.toml
[wrap]
# piped through `siga pipe` (the default)
pipe = [
  '^mise\s+run\s+(deploy|build|test)',
  '^make\b',
  '^docker\s+build\b',
]
# run on a pseudo-terminal, for tools that only draw a bar on a terminal
pty = [
  '^cargo\s+(build|test)',
  '^(npm|bun)\s+install\b',
]
```

Build-like commands (npm, cargo, go, make, docker, pytest, curl -o, rsync, git clone, ffmpeg, …) are wrapped out of the box, their output and exit code unchanged. A command that prints `12/40`, `45%` or ffmpeg `time=` fills exactly.

**A command that prints no progress at all still gets a bar:** siga remembers how long it took (the median of its last 5 runs) and fills by that, holding at 90% until it exits — so the second run of your build or deploy has a real bar.

For one-off commands:

| Your command… | Use |
|---|---|
| prints `12/40` or `45%` | `siga run -- ./build.sh` |
| draws its bar only on a terminal | `siga run --pty -- cargo build` |
| uses tqdm, rich, click, cli-progress | `siga run --shim -- python train.py` |
| prints nothing useful | `siga run -- make` (learns the duration) |
| is your own script | `siga set 3/10`, then `siga done` / `siga fail` |
| must stay in a pipe | `tool 2>&1 \| siga pipe; siga end $?` |

<details>
<summary>30 tested examples: shell tools, build tools, Python, Node, Go, Rust, OSC 9;4</summary>

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

`bin/siga selftest` runs all of them offline.
</details>

Works in Ghostty 1.3+ and Kitty 0.49+, including through [herdr](https://herdr.dev). Tested on macOS; Linux should work, Windows is TBD. Full mechanism: [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

Without Claude Code: `git clone https://github.com/souvlakeee/siga && cd siga`, then `bin/siga setup --apply` and `bin/siga run -- cargo build`.

## Limitations

- One bar per terminal window; parallel jobs share it.
- `siga off` / `siga on` pause the hooks; `siga setup --remove` uninstalls.

## Thanks

[ghostty-blackhole](https://github.com/s0xDk/ghostty-blackhole) (shader input via a color escape), Kitty's [Unicode placeholders](https://sw.kovidgoyal.net/kitty/graphics-protocol/#unicode-placeholders), [Fira Code](https://github.com/tonsky/FiraCode) (the first progress glyphs in a font).

## License

MIT
