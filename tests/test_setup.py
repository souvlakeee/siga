"""siga setup must never send Ghostty a signal that kills it."""
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from siga import hooks as hook  # noqa: E402
from siga import setup  # noqa: E402


class Reload(unittest.TestCase):
    def test_sends_sigusr2_to_ghostty_only(self):
        ps = mock.Mock(stdout="  101 /Applications/Ghostty.app/Contents/MacOS/ghostty\n  202 /bin/zsh\n")
        with mock.patch.object(setup.subprocess, "run", return_value=ps), \
             mock.patch.object(setup.os, "kill") as kill:
            setup.reload_terminals()
        kill.assert_called_once_with(101, signal.SIGUSR2)


class Plan(unittest.TestCase):
    def test_kitty_never_gets_ghostty_steps(self):
        with mock.patch.object(setup, "ghostty_present", return_value=True), \
             mock.patch.object(setup, "_same", return_value=False), \
             mock.patch.object(setup.core, "detect_backend", return_value="kitty"):
            self.assertFalse([d for d, _ in setup.plan() if "font" in d or "shader" in d or "append" in d])
            self.assertIn("Kitty", setup.where())

    def test_ghostty_gets_font_shader_and_block(self):
        with mock.patch.object(setup.core, "detect_backend", return_value="ghostty"), \
             mock.patch.object(setup, "_same", return_value=False), \
             mock.patch.object(setup, "ghostty_config", return_value=Path("/nonexistent/ghostty/config")):
            descs = " ".join(d for d, _ in setup.plan())
        for word in ("font", "shader", "append"):
            self.assertIn(word, descs)


class Welcome(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cache = Path(self.tmp.name)
        self.patches = [mock.patch.object(setup.core, "CACHE", cache),
                        mock.patch.object(setup.core, "WELCOME", cache / "welcome")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_line_per_terminal(self):
        cases = [("kitty", False, "Try it"), ("ghostty", False, "Try it"),
                 ("ghostty", True, "new Ghostty window"), ("text", False, "in Ghostty or Kitty")]
        with mock.patch.dict(setup.os.environ, {"CLAUDECODE": ""}):
            for backend, font_new, expect in cases:
                with mock.patch.object(setup.core, "detect_backend", return_value=backend):
                    self.assertIn(expect, setup.welcome(font_new), backend)
        self.assertFalse(setup.core.WELCOME.exists())

    def test_claude_session_gets_the_bar_once(self):
        with mock.patch.dict(setup.os.environ, {"CLAUDECODE": "1"}), \
             mock.patch.object(setup.core, "detect_backend", return_value="kitty"), \
             mock.patch.object(hook.core, "spawn_detached") as spawn:
            self.assertIn("welcome bar", setup.welcome())
            first = hook.messagedisplay({"message_id": "m1", "delta": "Done.", "final": True})
            second = hook.messagedisplay({"message_id": "m2", "delta": "Next.", "final": True})
        shown = first["hookSpecificOutput"]["displayContent"]
        self.assertIn("welcome", shown)
        self.assertNotIn("⟦bar⟧", shown)
        self.assertIsNone(second)
        self.assertIn(["demo"], [c.args[0] for c in spawn.call_args_list])

if __name__ == "__main__":
    unittest.main()
