"""`siga selftest`: run every example under the recorder backend and check its bar.

Each example script carries a header:
    # tool: curl
    # needs: curl            (commands that must exist; "docker-daemon", "network" are special)
    # expect: updates>=5 final=done max>=0.95
and marks the lines the README shows with `# >>> readme` / `# <<< readme`.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root (src/siga/selftest.py)
EXAMPLES = ROOT / "examples"
FIXTURES = ROOT / "tests" / "fixtures"


def header(path):
    meta = {"needs": [], "expect": {}}
    for line in path.read_text().splitlines()[:20]:
        m = re.match(r"#\s*(\w+):\s*(.*)", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if k == "needs":
            meta["needs"] = v.split()
        elif k == "expect":
            for part in v.split():
                key, op, val = re.match(r"(\w+)(>=|=)(.+)", part).groups()
                meta["expect"][key] = (op, val)
        else:
            meta[k] = v
    return meta


def readme_block(path):
    text = path.read_text()
    m = re.search(r"# >>> readme\n(.*?)# <<< readme", text, re.S)
    return m.group(1).rstrip() if m else None


def missing(needs, allow_network):
    out = []
    for n in needs:
        if n == "network":
            if not allow_network:
                out.append("network (use --network)")
        elif n == "docker-daemon":
            if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
                out.append("docker daemon")
        elif n.startswith("py:"):
            py = str(ROOT / ".venv" / "bin" / "python")
            if subprocess.run([py, "-c", f"import {n[3:]}"], capture_output=True).returncode != 0:
                out.append(n)
        elif not shutil.which(n):
            out.append(n)
    return out


def judge(records, expect):
    values = [r["value"] for r in records if r["state"] == "run"]
    distinct = len(set(values))
    final = records[-1]["state"] if records else "none"
    top = max(values) if values else 0.0
    problems = []
    for key, (op, want) in expect.items():
        got = {"updates": distinct, "final": final, "max": top}[key]
        ok = got == want if op == "=" else float(got) >= float(want)
        if not ok:
            problems.append(f"{key}={got} (want {op}{want})")
    return distinct, final, top, problems


def run(pattern=None, allow_network=False, capture=False, timeout=180):
    scripts = sorted(p for p in EXAMPLES.glob("*/*") if p.suffix == ".sh" and not p.name.startswith("_"))
    if pattern:
        scripts = [p for p in scripts if pattern in str(p.relative_to(EXAMPLES))]
    env = {**os.environ, "PATH": f"{ROOT / 'bin'}:{ROOT / '.venv' / 'bin'}:/opt/homebrew/bin:{os.environ['PATH']}",
           "SIGA_BACKEND": "record", "SIGA_TTY": "", "PYTHONDONTWRITEBYTECODE": "1"}
    rows, failed = [], 0
    for path in scripts:
        name = str(path.relative_to(EXAMPLES))
        meta = header(path)
        lack = missing(meta["needs"], allow_network)
        if lack:
            rows.append((name, "SKIP", "missing " + ", ".join(lack)))
            continue
        rec = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False).name
        run_env = {**env, "SIGA_RECORD": rec}
        if capture:
            FIXTURES.mkdir(parents=True, exist_ok=True)
            tee = FIXTURES / (name.replace("/", "__").rsplit(".", 1)[0] + ".txt")
            if tee.exists():
                tee.unlink()
            run_env["SIGA_TEE"] = str(tee)
        t0 = time.time()
        try:
            proc = subprocess.run([str(path)], env=run_env, capture_output=True, timeout=timeout)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        records = [json.loads(l) for l in Path(rec).read_text().splitlines() if l.strip()]
        os.unlink(rec)
        if rc == 77:
            reason = proc.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["skipped"]
            rows.append((name, "SKIP", reason[0].replace("SKIP: ", "")))
            continue
        distinct, final, top, problems = judge(records, meta["expect"])
        if rc not in (0,) and meta["expect"].get("final", ("=", "done"))[1] == "done":
            problems.insert(0, f"exit {rc}")
        status = "FAIL" if problems else "PASS"
        failed += bool(problems)
        detail = f"{distinct} updates, max {top:.2f}, {final}, {time.time() - t0:.1f}s"
        rows.append((name, status, detail + ("  <- " + "; ".join(problems) if problems else "")))
    width = max((len(r[0]) for r in rows), default=10)
    for name, status, detail in rows:
        print(f"{status:4}  {name:<{width}}  {detail}")
    return 1 if failed else 0


FAMILIES = {"shell": "Shell tools", "build": "Build tools", "python": "Python libraries",
            "node": "Node libraries", "go": "Go libraries", "rust": "Rust libraries",
            "osc": "OSC 9;4 emitters"}
README = ROOT / "README.md"
TABLE_BEGIN, TABLE_END = "<!-- examples:start -->", "<!-- examples:end -->"


def _command(block):
    """The README-worthy line of an example: its siga call, without setup or comments."""
    lines = [l.split("   #")[0].strip() for l in block.splitlines() if "siga " in l and not l.lstrip().startswith("#")]
    return lines[-1] if lines else block.splitlines()[-1].strip()


def table(prefix="examples/"):
    """The examples table, generated from examples/*/*.sh (family order as in FAMILIES)."""
    rows = ["| Family | Tool | Command | Example |", "|---|---|---|---|"]
    for family in FAMILIES:
        for path in sorted((EXAMPLES / family).glob("*.sh")):
            meta, block = header(path), readme_block(path)
            if not block:
                continue
            tool = meta.get("tool", path.stem).split(" (")[0]
            cmd = _command(block).replace("|", "\\|")
            rel = path.relative_to(EXAMPLES)
            rows.append(f"| {FAMILIES[family]} | {tool} | `{cmd}` | [{rel.name}]({prefix}{rel}) |")
    return "\n".join(rows)


def snippets(out=EXAMPLES / "README-snippets.md"):
    """Write examples/README-snippets.md and refresh the table in README.md."""
    blocks = []
    for family in FAMILIES:
        for path in sorted((EXAMPLES / family).glob("*.sh")):
            block = readme_block(path)
            if block:
                blocks.append(f"### {header(path).get('tool', path.stem)}\n\n```sh\n{block}\n```\n")
    out.write_text("<!-- generated by `siga selftest --snippets`; edit examples/*/*.sh instead -->\n\n"
                   + table(prefix="") + "\n\n" + "\n".join(blocks))
    if README.exists() and TABLE_BEGIN in README.read_text():
        text = README.read_text()
        head, rest = text.split(TABLE_BEGIN, 1)
        _, tail = rest.split(TABLE_END, 1)
        README.write_text(f"{head}{TABLE_BEGIN}\n{table()}\n{TABLE_END}{tail}")
    return out


def readme_ok():
    """True when README.md's examples table matches the scripts."""
    text = README.read_text() if README.exists() else ""
    if TABLE_BEGIN not in text:
        print("README.md has no examples table markers")
        return False
    current = text.split(TABLE_BEGIN, 1)[1].split(TABLE_END, 1)[0].strip()
    if current != table().strip():
        print("README.md examples table is out of date: run `siga selftest --snippets`")
        return False
    print("README.md examples table matches examples/")
    return True
