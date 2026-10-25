"""siga setup must never send Ghostty a signal that kills it."""
import signal
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from siga import setup  # noqa: E402


class Reload(unittest.TestCase):
    def test_sends_sigusr2_to_ghostty_only(self):
        ps = mock.Mock(stdout="  101 /Applications/Ghostty.app/Contents/MacOS/ghostty\n  202 /bin/zsh\n")
        with mock.patch.object(setup.subprocess, "run", return_value=ps), \
             mock.patch.object(setup.os, "kill") as kill:
            setup.reload_terminals()
        kill.assert_called_once_with(101, signal.SIGUSR2)


if __name__ == "__main__":
    unittest.main()
