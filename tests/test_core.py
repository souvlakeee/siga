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
            mock.patch.dict(core.os.environ, {"SIGA_TTY": "/dev/ttysTEST"}),
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


if __name__ == "__main__":
    unittest.main()
