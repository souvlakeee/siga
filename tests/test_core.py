"""herdr: finding the terminal a herdr client runs in, and where each backend writes."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from siga import core  # noqa: E402

KITTY = "/Applications/kitty.app/Contents/MacOS/kitty"
GHOSTTY = "/Applications/Ghostty.app/Contents/MacOS/ghostty"


def ps(*rows):
    return mock.Mock(stdout="".join(f"{p} {pp} {t} {c}\n" for p, pp, t, c in rows))


SERVER = ("4196", "1", "??", "/Users/u/.local/bin/herdr")
PANE = ("5000", "4196", "ttys009", "-fish")


class HerdrHost(unittest.TestCase):
    def host(self, *rows, env=None):
        with mock.patch("subprocess.run", return_value=ps(*rows)):
            return core.herdr_host(env or {"TERM_PROGRAM": "herdr"})

    def test_kitty_client(self):
        rows = [SERVER, PANE, ("100", "1", "??", KITTY), ("110", "100", "ttys003", "login"),
                ("120", "110", "ttys003", "-fish"), ("130", "120", "ttys003", "herdr")]
        self.assertEqual(self.host(*rows), ("kitty", ["/dev/ttys003"]))

    def test_ghostty_client(self):
        rows = [SERVER, PANE, ("200", "1", "??", GHOSTTY), ("210", "200", "ttys004", "/usr/bin/login"),
                ("220", "210", "ttys004", "-zsh"), ("230", "220", "ttys004", "herdr")]
        self.assertEqual(self.host(*rows), ("ghostty", ["/dev/ttys004"]))

    def test_no_client_is_text(self):
        self.assertEqual(self.host(SERVER, PANE), (None, []))
        with mock.patch("subprocess.run", return_value=ps(SERVER, PANE)):
            self.assertEqual(core.detect_backend({"TERM_PROGRAM": "herdr"}), "text")

    def test_two_clients(self):
        rows = [SERVER, ("200", "1", "??", GHOSTTY),
                ("230", "200", "ttys004", "herdr"), ("240", "200", "ttys006", "herdr")]
        self.assertEqual(self.host(*rows), ("ghostty", ["/dev/ttys004", "/dev/ttys006"]))

    def test_outside_herdr_does_nothing(self):
        with mock.patch("subprocess.run") as run:
            self.assertEqual(core.herdr_host({"TERM_PROGRAM": "kitty"}), (None, []))
        run.assert_not_called()


class Slots(unittest.TestCase):
    """Each ⟦bar⟧ gets its own slot; finished bars freeze while the next one fills."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(core, "CACHE", Path(self.tmp.name)),
            mock.patch.dict(core.os.environ, {"SIGA_TTY": "/dev/ttysTEST", "SIGA_BACKEND": "text"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_allocate_recycles_through_the_ring(self):
        got = [core.allocate() for _ in range(core.SLOTS + 2)]
        self.assertEqual(got, [0, 1, 2, 3, 0, 1])

    def test_pending_binds_fifo(self):
        a, b = core.allocate(), core.allocate()
        self.assertEqual(core.resolve_slot(), a)
        self.assertEqual(core.resolve_slot(), b)
        self.assertEqual(core.resolve_slot(default="scratch"), core.SLOTS)  # queue drained

    def test_finished_bar_freezes_when_the_next_fills(self):
        core.allocate(); a = core.resolve_slot()    # bar A: token then its command
        core.push(1.0, "done", slot=a)
        core.allocate(); b = core.resolve_slot()    # bar B
        core.push(0.4, "run", slot=b)
        self.assertEqual((a, b), (0, 1))
        self.assertEqual(core.load(a)["state"], "done")  # A kept its own state
        self.assertEqual(core.load(b)["state"], "run")

    def test_untokened_command_uses_scratch_not_a_visible_bar(self):
        core.allocate(); a = core.resolve_slot()
        core.push(1.0, "done", slot=a)              # a finished, visible bar
        scratch = core.resolve_slot(default="scratch")  # a wrapped command with no token
        self.assertEqual(scratch, core.SLOTS)
        core.push(0.5, "run", slot=scratch)
        self.assertEqual(core.load(a)["state"], "done")  # untouched

    def test_end_resolves_the_live_slot(self):
        s = core.allocate()
        core.resolve_slot(default="scratch")        # pipe consumes the token -> s
        core.push(0.3, "run", slot=s)
        self.assertEqual(core.resolve_slot(default="live"), s)  # end finds the live bar

    def test_fail_live_only_hits_live_bars(self):
        core.push(1.0, "done", slot=0)
        core.push(0.6, "run", slot=1)
        core.fail_live()
        self.assertEqual(core.load(0)["state"], "done")
        self.assertEqual(core.load(1)["state"], "fail")

    def test_migrates_an_old_flat_record(self):
        core.state_file().write_text('{"value": 0.5, "state": "run", "time": 1}')
        self.assertEqual(core.load(0), {"value": 0.5, "state": "run", "time": 1})

    def test_demo_now_drives_and_clears_the_welcome_token(self):
        from siga import cli
        s = core.allocate()  # the welcome ⟦bar⟧ token
        with mock.patch.dict(core.os.environ, {"SIGA_BACKEND": "record"}):
            cli.main(["demo", "--now", "0"])
        self.assertEqual(core.load(s)["state"], "done")  # demo filled the token's own slot
        self.assertEqual(core.resolve_slot(default="scratch"), core.SLOTS)  # no stale pending left


class GhosttyApply(unittest.TestCase):
    """The one path that actually changed in production: OSC 4 to BASE+slot."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(core, "CACHE", Path(self.tmp.name)),
            mock.patch.dict(core.os.environ, {"SIGA_TTY": "/dev/ttysTEST", "SIGA_BACKEND": "ghostty"}),
            mock.patch.object(core, "target_ttys", return_value=["/dev/x"]),
            mock.patch.object(core, "write_tty"),
        ]
        self.mocks = [p.start() for p in self.patches]

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_slot_picks_its_palette_entry(self):
        core.push(0.5, "run", backend="ghostty", slot=2)  # BASE(252)+2 = 254
        self.mocks[3].assert_called_once()
        self.assertTrue(self.mocks[3].call_args.args[1].startswith(b"\033]4;254;"))

    def test_scratch_slot_writes_nothing(self):
        core.push(0.5, "run", backend="ghostty", slot=core.SLOTS)
        self.mocks[3].assert_not_called()


class WindowSlots(unittest.TestCase):
    """Panes of one Ghostty window (herdr) share the palette, so they must claim distinct
    slots, never blank each other's live bar, and fail only their own (issue #4)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(core, "CACHE", Path(self.tmp.name)),
            mock.patch.dict(core.os.environ, {"SIGA_BACKEND": "record"}),
            mock.patch.object(core, "window_tty", return_value="/dev/win"),
            mock.patch.object(core, "own_tty", return_value="/dev/paneA"),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.own = self.mocks[3]
        for k in ("SIGA_TTY", "SIGA_SLOT"):
            core.os.environ.pop(k, None)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def pane(self, tty):
        self.own.return_value = tty

    def _run_a_bar(self, value):  # allocate a token, bind it, push it live; returns the slot
        core.allocate()
        slot = core.resolve_slot()
        core.push(value, "run", slot=slot)
        return slot

    def test_two_panes_claim_distinct_entries(self):
        self.pane("/dev/paneA"); a = self._run_a_bar(0.3)
        self.pane("/dev/paneB"); b = self._run_a_bar(0.6)
        self.assertNotEqual(a, b)
        win = core._win_read()["slots"]
        self.assertEqual(win[a]["pane"], "/dev/paneA")
        self.assertEqual(win[b]["pane"], "/dev/paneB")

    def test_allocate_skips_another_panes_live_slot(self):
        self.pane("/dev/paneA"); self._run_a_bar(0.3)          # A live on slot 0
        self.pane("/dev/paneB")
        got = [self._run_a_bar(0.5) for _ in range(3)]
        self.assertNotIn(0, got)                                # A's live bar is never reclaimed
        self.assertEqual(sorted(got), [1, 2, 3])

    def test_allocate_skips_another_panes_reserved_slot(self):
        self.pane("/dev/paneA"); core.allocate()               # reserves slot 0, command not run
        self.pane("/dev/paneB")
        got = [core.allocate() for _ in range(3)]
        self.assertNotIn(0, got)                                # A's reserved token isn't stolen
        self.assertEqual(sorted(got), [1, 2, 3])

    def test_fifth_bar_wraps_onto_the_oldest(self):
        self.pane("/dev/paneA"); self._run_a_bar(0.3)          # slot 0, oldest
        self.pane("/dev/paneB"); [self._run_a_bar(0.5) for _ in range(3)]  # 1,2,3
        core.allocate()                                         # all four live -> oldest
        self.assertEqual(core.resolve_slot(), 0)

    def test_fail_live_only_fails_this_pane(self):
        self.pane("/dev/paneA"); self._run_a_bar(0.3)          # A live, slot 0
        self.pane("/dev/paneB"); self._run_a_bar(0.6)          # B live, slot 1
        self.pane("/dev/paneA"); core.fail_live()              # A's command dies
        win = core._win_read()["slots"]
        self.assertEqual(win[0]["state"], "fail")              # A failed
        self.assertEqual(win[1]["state"], "run")               # B still running

    def test_migrates_a_legacy_doc(self):
        self.pane("/dev/paneA")
        core.state_file().write_text('{"value": 0.5, "state": "run", "time": 1}')
        self.assertEqual(core.load(0), {"value": 0.5, "state": "run", "time": 1})
        core.fail_live()  # a migrated live bar has no owner tag but is still failable by its pane
        self.assertEqual(core.load(0)["state"], "fail")


class WindowTty(unittest.TestCase):
    def test_degrades_to_the_pane_when_herdr_has_no_backend(self):
        with mock.patch.object(core, "detect_backend", return_value="ghostty"), \
             mock.patch.object(core, "target_ttys", return_value=[]), \
             mock.patch.object(core, "own_tty", return_value="/dev/paneX"):
            self.assertEqual(core.window_tty(), "/dev/paneX")


class HostCache(unittest.TestCase):
    """The ps-derived window resolution is cached on disk per pane, so the sibling
    hook/command processes in a pane don't each pay a ~90 ms ps."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(core, "CACHE", Path(self.tmp.name)),
            mock.patch.dict(core.os.environ,
                            {"HERDR_PANE_ID": "w47:p1Z", "TERM_PROGRAM": "herdr"}),
        ]
        for p in self.patches:
            p.start()
        for k in ("SIGA_TTY", "SIGA_HERDR_HOST", "HERDR_SOCKET_PATH", "KITTY_WINDOW_ID"):
            core.os.environ.pop(k, None)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _ps_self(self):  # a ps whose pid chain gives this process the tty /dev/null
        return mock.Mock(stdout=f"{core.os.getpid()} 1 null\n")

    GHOSTTY_ROWS = [SERVER, ("200", "1", "??", GHOSTTY),
                    ("210", "200", "null", "/usr/bin/login"),
                    ("220", "210", "null", "-zsh"), ("230", "220", "null", "herdr")]

    def test_own_tty_hits_ps_once_then_reads_disk(self):
        with mock.patch("subprocess.run", return_value=self._ps_self()) as run:
            self.assertEqual(core.own_tty(), "/dev/null")
            self.assertEqual(run.call_count, 1)
        core.os.environ.pop("SIGA_TTY", None)  # a fresh sibling process in the same pane
        with mock.patch("subprocess.run", side_effect=AssertionError("ps re-run")) as run:
            self.assertEqual(core.own_tty(), "/dev/null")
            run.assert_not_called()

    def test_herdr_host_hits_ps_once_then_reads_disk(self):
        with mock.patch("subprocess.run", return_value=ps(*self.GHOSTTY_ROWS)) as run:
            self.assertEqual(core.herdr_host(), ("ghostty", ["/dev/null"]))
            self.assertEqual(run.call_count, 1)
        core.os.environ.pop("SIGA_HERDR_HOST", None)
        with mock.patch("subprocess.run", side_effect=AssertionError("ps re-run")):
            self.assertEqual(core.herdr_host(), ("ghostty", ["/dev/null"]))

    def test_stale_entry_forces_re_resolve(self):
        (Path(self.tmp.name) / "host-w47_p1Z.json").write_text('{"tty": "/dev/ttysZZZ9"}')
        with mock.patch("subprocess.run", return_value=self._ps_self()) as run:
            self.assertEqual(core.own_tty(), "/dev/null")  # gone device → cache dropped
            self.assertEqual(run.call_count, 1)

    def test_a_miss_is_not_cached(self):
        # a transient resolve failure must not pin the whole pane to "no tty" for the session
        with mock.patch("subprocess.run",
                        return_value=mock.Mock(stdout=f"{core.os.getpid()} 1 ??\n")):
            self.assertIsNone(core.own_tty())
        self.assertFalse((Path(self.tmp.name) / "host-w47_p1Z.json").exists())
        core.os.environ.pop("SIGA_TTY", None)  # next process retries rather than inheriting it
        with mock.patch("subprocess.run", return_value=self._ps_self()) as run:
            self.assertEqual(core.own_tty(), "/dev/null")
            self.assertEqual(run.call_count, 1)

    def test_no_pane_key_means_no_disk_cache(self):
        core.os.environ.pop("HERDR_PANE_ID", None)
        self.assertIsNone(core._host_key())
        for _ in range(2):  # every process pays its own ps; nothing lands on disk
            core.os.environ.pop("SIGA_TTY", None)
            with mock.patch("subprocess.run", return_value=self._ps_self()) as run:
                self.assertEqual(core.own_tty(), "/dev/null")
                self.assertEqual(run.call_count, 1)


class Targets(unittest.TestCase):
    def test_ghostty_writes_to_the_client_tty(self):
        with mock.patch.object(core, "herdr_host", return_value=("ghostty", ["/dev/ttys004"])), \
             mock.patch.object(core, "own_tty", return_value="/dev/ttys009"):
            self.assertEqual(core.target_ttys(GHOSTTY), ["/dev/ttys004"])

    def test_kitty_writes_to_the_pane(self):
        with mock.patch.object(core, "herdr_host", return_value=("kitty", ["/dev/ttys003"])), \
             mock.patch.object(core, "own_tty", return_value="/dev/ttys009"):
            self.assertEqual(core.target_ttys(KITTY), ["/dev/ttys009"])


class MiseHistory(unittest.TestCase):
    """A `mise run X` is timed from mise's run history, ahead of siga's own record."""

    def history(self, payload):
        return mock.patch("subprocess.run", return_value=mock.Mock(stdout=payload))

    def test_task_name_from_a_command(self):
        for cmd, task in [
            ("mise run deploy", "deploy"),
            ("mise run test:acceptance:hurl -- tests/a.hurl", "test:acceptance:hurl"),
            ("REACT_COMPILER=1 mise run deploy", "deploy"),
            ("mise run --output summary lint:all", "lint:all"),
            ("mise r build", "build"),
            ("make", None),
            ("cd video && mise run render", "render"),  # how agents write it: cd first
            ("mise tasks history deploy; mise run deploy 2>&1 | tail -3", "deploy"),
            ("echo mise run deploy", None),  # an argument, not a command
            ("mise install", None),
        ]:
            self.assertEqual(core.mise_task(cmd), task, cmd)

    def test_the_cd_before_the_task_is_where_history_is_read(self):
        for cmd, cwd in [
            ("mise run deploy", None),
            ("cd /repo && mise run deploy", "/repo"),
            ("cd /a && make; cd '/b c' && mise run deploy", "/b c"),
            ("cd ~/proj && mise run deploy", str(Path("~/proj").expanduser())),
            ("mise run deploy && cd /later", None),  # a cd after the task does not apply
        ]:
            self.assertEqual(core.mise_run(cmd), ("deploy", cwd), cmd)

    def test_history_is_read_in_that_directory(self):
        with self.history('[{"task":"deploy","median_ms":2000}]') as run:
            core.mise_eta("deploy", "/repo")
        self.assertEqual(run.call_args.kwargs["cwd"], "/repo")

    def test_median_comes_back_in_seconds(self):
        with self.history('[{"task":"deploy","runs":4,"median_ms":41500},{"task":"build","median_ms":900}]'):
            self.assertEqual(core.mise_eta("deploy"), 41.5)

    def test_no_usable_history_is_none(self):
        for payload in ("", "not json", "[]", '[{"task":"deploy","median_ms":null}]',
                        '[{"task":"other","median_ms":5000}]', '{"task":"deploy"}'):
            with self.history(payload):
                self.assertIsNone(core.mise_eta("deploy"), payload)

    def test_a_missing_mise_is_none(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertIsNone(core.mise_eta("deploy"))

    def track(self, mise, mise_eta, own):
        """Run track() over a silent 0.3 s stream and return the values it pushed."""
        import time
        chunks = iter([None, None, None, b""])
        pushed = []

        def read(timeout):
            time.sleep(0.1)
            return next(chunks)

        medians = {mise: mise_eta} if mise and mise_eta else {}
        with mock.patch.object(core, "mise_history", return_value=medians) as asked, \
             mock.patch.object(core, "phase_plan_get", return_value=[]), \
             mock.patch.object(core, "history_get", return_value=own), \
             mock.patch.object(core, "history_add"), \
             mock.patch.object(core, "shim_active", return_value=False), \
             mock.patch.object(core, "push", side_effect=lambda v, s, slot=None: pushed.append((v, s))):
            core.track(read, lambda b: None, key="k", min_interval=0.0, mise=mise)
        return pushed, asked

    def test_mise_median_times_the_bar_ahead_of_siga_record(self):
        pushed, _ = self.track("deploy", mise_eta=1.0, own=100.0)
        # 0.3 s against mise's 1 s is ~30%; against siga's own 100 s it would be under 1%
        self.assertGreater(max(v for v, _ in pushed), 0.15)

    def test_no_mise_history_falls_back_to_siga_record(self):
        pushed, _ = self.track("deploy", mise_eta=None, own=1.0)
        self.assertEqual(pushed[0], (0.0, "run"))
        self.assertGreater(max(v for v, _ in pushed), 0.15)

    def test_a_plain_command_never_asks_mise(self):
        pushed, asked = self.track(None, mise_eta=1.0, own=None)
        asked.assert_not_called()
        self.assertEqual(pushed, [(0.0, "busy")])


class MisePhases(unittest.TestCase):
    """track() moves a multi-step mise task phase by phase, and keeps a plan only from a run that passed."""

    PLAN = [["deploy:sync", 7.4], ["deploy:build", 8.8], ["deploy:verify", 3.6]]

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        cache = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(core, "CACHE", cache),
            mock.patch.object(core, "HISTORY_FILE", cache / "history.json"),
            mock.patch.dict(core.os.environ, {"SIGA_TTY": "/dev/ttysTEST", "SIGA_BACKEND": "text"}),
            mock.patch.object(core, "mise_history", return_value={}),
            mock.patch.object(core, "shim_active", return_value=False),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def run_track(self, lines):
        """Feed lines one per read, return the values pushed."""
        chunks = iter([ln.encode() for ln in lines] + [b""])
        pushed = []
        with mock.patch.object(core, "push", side_effect=lambda v, s, slot=None: pushed.append((round(v, 3), s))):
            seen = core.track(lambda t: next(chunks), lambda b: None, key="k", min_interval=0.0,
                              mise="deploy", mise_cwd="/repo")
        return pushed, seen

    LINES = ["[deploy] $ bash deploy.sh\n", "[deploy:sync] $ rsync\n", "copying 1/2\n", "copying 2/2\n",
             "[deploy:build] $ build\n", "[deploy:verify] $ curl\n"]

    def test_a_stored_plan_steps_the_bar_at_each_phase(self):
        core.phase_plan_set("deploy", "/repo", self.PLAN)
        pushed, _ = self.run_track(self.LINES)
        values = [v for v, s in pushed if s == "run"]
        self.assertIn(round(7.4 / 19.8, 3), values)          # build started
        self.assertIn(round((7.4 + 8.8) / 19.8, 3), values)  # verify started
        self.assertLess(max(values), 0.96)                   # the last part waits for the exit

    def test_without_a_plan_the_whole_stream_count_drives_the_bar(self):
        # positive control: the same stream, no plan, reads the sync's 2/2 as the whole job
        pushed, _ = self.run_track(self.LINES)
        self.assertIn((1.0, "run"), pushed)

    def test_a_plan_with_no_header_in_the_output_leaves_the_count_in_charge(self):
        # `--output summary`, `task.quiet` or a renamed step: the plan must not pin the bar
        core.phase_plan_set("deploy", "/repo", self.PLAN)
        pushed, _ = self.run_track(["copying 1/2\n", "copying 2/2\n"])
        self.assertIn((1.0, "run"), pushed)

    def test_the_bar_never_steps_back_when_the_first_header_arrives(self):
        core.phase_plan_set("deploy", "/repo", self.PLAN)
        lines = ["copying 1/2\n", "copying 2/2\n", "[deploy:sync] $ rsync\n", "[deploy:build] $ build\n"]
        pushed, _ = self.run_track(lines)
        values = [v for v, s in pushed if s == "run"]
        self.assertEqual(values, sorted(values), values)

    def test_a_passed_run_without_steps_forgets_the_plan(self):
        core.phase_plan_set("deploy", "/repo", self.PLAN)
        core.phases_park("deploy", "/repo", [])
        core.phases_settle(0)
        self.assertEqual(core.phase_plan_get("deploy", "/repo"), [])

    def test_the_run_reports_its_phases(self):
        _, seen = self.run_track(self.LINES)
        self.assertEqual([n for n, _ in seen], ["deploy:sync", "deploy:build", "deploy:verify"])

    def test_a_passed_run_becomes_the_plan(self):
        core.phases_park("deploy", "/repo", self.PLAN)
        core.phases_settle(0)
        self.assertEqual(core.phase_plan_get("deploy", "/repo"), self.PLAN)

    def test_a_failed_run_keeps_the_old_plan(self):
        core.phase_plan_set("deploy", "/repo", self.PLAN)
        core.phases_park("deploy", "/repo", [["deploy:sync", 1.0], ["deploy:other", 1.0]])
        core.phases_settle(1)
        self.assertEqual(core.phase_plan_get("deploy", "/repo"), self.PLAN)
        core.phases_settle(0)  # nothing parked any more: nothing to save
        self.assertEqual(core.phase_plan_get("deploy", "/repo"), self.PLAN)

    def test_plans_are_per_project(self):
        core.phase_plan_set("deploy", "/repo", self.PLAN)
        self.assertEqual(core.phase_plan_get("deploy", "/other"), [])

    def test_one_phase_is_no_plan(self):
        core.phase_plan_set("deploy", "/repo", [["deploy:sync", 1.0]])
        self.assertEqual(core.phase_plan_get("deploy", "/repo"), [])

    def test_siga_end_settles_the_parked_plan(self):
        from siga import cli
        core.phases_park("deploy", "/repo", self.PLAN)
        with mock.patch.object(core, "push"):
            self.assertEqual(cli.main(["end", "0"]), 0)
        self.assertEqual(core.phase_plan_get("deploy", "/repo"), self.PLAN)


if __name__ == "__main__":
    unittest.main()
