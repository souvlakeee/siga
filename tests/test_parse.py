"""Progress parsing against real captured output (tests/fixtures, from `siga selftest --capture`)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from siga.parse import Cleaner, Phases, Progress, Stream  # noqa: E402

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


PLAN = ["deploy:bump", "deploy:sync", "deploy:build", "deploy:restart", "deploy:verify"]
# a real five-phase deploy's medians, in seconds (21.0 s in all)
WEIGHTS = {"deploy:bump": 0.02, "deploy:sync": 7.4, "deploy:build": 8.8,
           "deploy:restart": 1.1, "deploy:verify": 3.6}


def header(name):
    return f"[{name}] $ run {name}"


class PhaseBar(unittest.TestCase):
    """A multi-step mise task moves phase by phase, weighted by each phase's median."""

    def phases(self):
        return Phases(parent="deploy", plan=PLAN, weights=WEIGHTS)

    def test_a_phase_start_places_the_bar_by_the_weight_already_passed(self):
        ph = self.phases()
        ph.feed(header("deploy"), 0)  # the parent's own header is not a phase
        self.assertIsNone(ph.value(0))  # no step yet: the time estimate keeps the bar
        ph.feed(header("deploy:bump"), 0)
        ph.feed(header("deploy:sync"), 0.1)
        ph.feed(header("deploy:build"), 7.5)
        self.assertAlmostEqual(ph.value(7.5), (0.02 + 7.4) / 20.92, places=3)  # 35%

    def test_time_fills_the_phase_between_starts(self):
        ph = self.phases()
        ph.feed(header("deploy:sync"), 0)
        self.assertAlmostEqual(ph.value(3.7), (0.02 + 3.7) / 20.92, places=3)

    def test_a_slow_phase_holds_at_its_own_boundary(self):
        ph = self.phases()
        ph.feed(header("deploy:sync"), 0)
        held = (0.02 + 0.9 * 7.4) / 20.92  # 90% of the phase, never into build's span
        self.assertAlmostEqual(ph.value(60), held, places=3)
        self.assertAlmostEqual(ph.value(900), held, places=3)

    def test_the_whole_bar_never_reads_done_before_the_exit(self):
        ph = self.phases()
        ph.feed(header("deploy:verify"), 0)
        self.assertLessEqual(ph.value(1000), Phases.BAR_CAP)

    def test_a_skipped_phase_jumps_forward(self):
        ph = self.phases()
        ph.feed(header("deploy:bump"), 0)
        ph.feed(header("deploy:restart"), 1)
        self.assertAlmostEqual(ph.value(1), (0.02 + 7.4 + 8.8) / 20.92, places=3)

    def test_a_header_outside_the_plan_holds_the_bar(self):
        ph = self.phases()
        ph.feed(header("deploy:sync"), 0)
        before = ph.value(2)
        ph.feed(header("deploy:new-step"), 2)
        self.assertEqual(ph.value(2), before)
        ph.feed(header("deploy:bump"), 2)  # an earlier phase showing up late changes nothing
        self.assertEqual(ph.value(2), before)

    def test_a_count_fills_only_its_own_phase(self):
        ph = self.phases()
        ph.feed(header("deploy:build"), 0)
        for line in ("transforming (1/3)", "transforming (2/3)", "transforming (3/3)"):
            ph.feed(line, 0)
        # 3/3 inside build is the end of build (held at 90%), not the end of the deploy
        self.assertAlmostEqual(ph.value(0), (0.02 + 7.4 + 0.9 * 8.8) / 20.92, places=3)
        ph.feed(header("deploy:restart"), 1)  # the next phase starts from its own clock
        self.assertAlmostEqual(ph.value(1), (0.02 + 7.4 + 8.8) / 20.92, places=3)

    def test_no_plan_or_one_phase_or_a_missing_weight_is_inactive(self):
        for plan, weights in ([], WEIGHTS), (["deploy:sync"], WEIGHTS), (PLAN, {"deploy:sync": 7.4}):
            ph = Phases(parent="deploy", plan=plan, weights=weights)
            ph.feed(header("deploy:sync"), 0)
            self.assertIsNone(ph.value(1), plan)

    def test_phases_that_ran_side_by_side_are_inactive(self):
        # measured on a real mise project: parallel `depends` steps start together, so the
        # plan's own run recorded 0.01 s gaps for steps whose medians are 1-2 s
        medians = {"a": 1.017, "b": 2.018, "c": 1.017}
        par = Phases(parent="par", plan=["a", "b", "c"], weights=medians,
                     measured={"a": 0.01, "b": 0.01, "c": 2.0})
        par.feed(header("c"), 0)
        self.assertIsNone(par.value(1))
        # positive control: the same steps run in turn recorded their full length
        seq = Phases(parent="seq", plan=["a", "b", "c"], weights=medians,
                     measured={"a": 1.03, "b": 2.04, "c": 1.03})
        seq.feed(header("b"), 0)
        self.assertIsNotNone(seq.value(1))

    def test_a_step_measured_at_zero_still_gets_a_weight(self):
        ph = Phases(parent="deploy")
        ph.feed(header("deploy:bump"), 5)
        ph.feed(header("deploy:sync"), 5)
        self.assertEqual(ph.observed(9)[0], ["deploy:bump", 0.01])

    def test_observed_records_each_phase_once_with_its_duration(self):
        ph = Phases(parent="deploy")
        for name, t in [("deploy", 0), ("deploy:bump", 0), ("deploy:sync", 0.5), ("deploy:sync", 3),
                        ("deploy:build", 8)]:
            ph.feed(header(name), t)
        self.assertEqual(ph.observed(17), [["deploy:bump", 0.5], ["deploy:sync", 7.5], ["deploy:build", 9]])

    def test_a_real_shaped_deploy_rises_in_five_steps(self):
        text = (FIXTURES / "phases" / "deploy.txt").read_text()
        clock = iter(range(1000)).__next__  # one second per line
        ph = self.phases()
        stream = Stream(Progress(), phases=ph, clock=clock)
        starts = []
        for line in text.splitlines(keepends=True):
            before = ph.current
            stream.feed(line)
            if ph.current != before:
                starts.append(ph.current)
        stream.close()
        self.assertEqual(starts, PLAN)
        self.assertEqual([n for n, _ in ph.observed(20)], PLAN)


if __name__ == "__main__":
    unittest.main()
