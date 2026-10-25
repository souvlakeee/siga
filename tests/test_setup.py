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


class Plan(unittest.TestCase):
    def test_kitty_without_ghostty_needs_nothing(self):
        with mock.patch.object(setup, "ghostty_present", return_value=False), \
             mock.patch.object(setup.core, "detect_backend", return_value="kitty"):
            self.assertFalse([d for d, _ in setup.plan() if "font" in d or "shader" in d or "append" in d])
            self.assertIn("Kitty", setup.where())

    def test_ghostty_gets_font_shader_and_block(self):
        with mock.patch.object(setup, "ghostty_present", return_value=True), \
             mock.patch.object(setup, "_same", return_value=False), \
             mock.patch.object(setup, "ghostty_config", return_value=Path("/nonexistent/ghostty/config")):
            descs = " ".join(d for d, _ in setup.plan())
        for word in ("font", "shader", "append"):
            self.assertIn(word, descs)


if __name__ == "__main__":
    unittest.main()
