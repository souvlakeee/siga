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
        with mock.patch.object(core.subprocess, "run", return_value=ps(*rows)):
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
        with mock.patch.object(core.subprocess, "run", return_value=ps(SERVER, PANE)):
            self.assertEqual(core.detect_backend({"TERM_PROGRAM": "herdr"}), "text")

    def test_two_clients(self):
        rows = [SERVER, ("200", "1", "??", GHOSTTY),
                ("230", "200", "ttys004", "herdr"), ("240", "200", "ttys006", "herdr")]
        self.assertEqual(self.host(*rows), ("ghostty", ["/dev/ttys004", "/dev/ttys006"]))

    def test_outside_herdr_does_nothing(self):
        with mock.patch.object(core.subprocess, "run") as run:
            self.assertEqual(core.herdr_host({"TERM_PROGRAM": "kitty"}), (None, []))
        run.assert_not_called()


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
