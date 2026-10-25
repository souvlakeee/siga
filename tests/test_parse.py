"""Progress parsing against real captured output (tests/fixtures, from `siga selftest --capture`)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from siga.parse import Cleaner, Progress, Stream  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
NO_PROGRESS = {"build__make_eta"}  # prints nothing to read; siga uses the learned ETA


def replay(data, chunk=97):
    """Feed raw bytes in odd-sized chunks, as a pipe delivers them; return the values seen."""
    prog = Progress()
    stream = Stream(prog)
    seen = []
    text = data.decode("utf-8", "replace")
    for i in range(0, len(text), chunk):
        stream.feed(text[i:i + chunk])
        if prog.trusted and (not seen or seen[-1] != prog.value):
            seen.append(prog.value)
    stream.close()
    if prog.trusted and (not seen or seen[-1] != prog.value):
        seen.append(prog.value)
    return seen


class Fixtures(unittest.TestCase):
    def test_every_tool_fixture_rises_to_the_end(self):
        # shim examples report values from inside the app, not in their text
        fixtures = sorted(p for p in FIXTURES.glob("*.txt")
                          if not p.name.startswith("negative__") and "_shim" not in p.name)
        self.assertGreater(len(fixtures), 20)
        for path in fixtures:
            with self.subTest(path.stem):
                seen = replay(path.read_bytes())
                if path.stem in NO_PROGRESS:
                    self.assertEqual(seen, [])
                    continue
                self.assertGreaterEqual(len(seen), 2, "too few values")
                self.assertGreaterEqual(max(seen), 0.9)
                drops = sum(1 for a, b in zip(seen, seen[1:]) if b < a - 0.3)
                self.assertLessEqual(drops, 1, f"bar jumps back: {seen}")

    def test_negative_fixtures_give_no_progress(self):
        for path in FIXTURES.glob("negative__*.txt"):
            with self.subTest(path.stem):
                self.assertEqual(replay(path.read_bytes()), [])


class FalsePositives(unittest.TestCase):
    def lines(self, *lines):
        return replay("\n".join(lines).encode() + b"\n")

    def test_dates_times_and_paths(self):
        self.assertEqual(self.lines(
            "2026/10/25 13:28:05 [build] output: server",
            "13:28:06 [assets] Copying fonts (18 files)...",
            "GET /api/v1/users 200 12ms",
            "commit 3f2a1b0 on 2026-10-25",
        ), [])

    def test_one_stray_ratio_is_not_trusted(self):
        self.assertEqual(self.lines("resolved 3/4 peers", "done"), [])

    def test_osc_wins_over_text(self):
        seen = replay(b"\x1b]9;4;1;40\x07 step 9/10 \n\x1b]9;4;1;60\x07\n")
        self.assertEqual(seen[-1], 0.6)

    def test_column_redraws(self):
        seen = replay(b"\x1b[1Gdl [=--] 10%\x1b[0K\x1b[1Gdl [==-] 50%\x1b[0K\x1b[1Gdl [===] 100%\x1b[0K\n")
        self.assertEqual(seen[-1], 1.0)


class Cleaning(unittest.TestCase):
    def test_trailing_progress_line_is_dropped(self):
        c = Cleaner()
        out = c.feed("error: boom\r\n   Building [==>  ] 3/9\r   Building [===> ] 4/9") + c.close()
        self.assertEqual(out, "error: boom\n")

    def test_redraws_collapse_to_final_line(self):
        c = Cleaner()
        out = c.feed("a 10%\ra 50%\ra 100%\r\nnext line\r\n\x1b[32mgreen\x1b[0m\r\n") + c.close()
        self.assertEqual(out, "a 100%\nnext line\ngreen\n")


if __name__ == "__main__":
    unittest.main()
