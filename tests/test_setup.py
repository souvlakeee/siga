"""siga setup must never send Ghostty a signal that kills it."""
import contextlib
import io
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
        with mock.patch.object(setup, "_same", return_value=False), \
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
        cases = [("kitty", "Try it"), ("ghostty", "Try it"), ("text", "in Ghostty or Kitty")]
        with mock.patch.dict(setup.os.environ, {"CLAUDECODE": ""}):
            for backend, expect in cases:
                with mock.patch.object(setup.core, "detect_backend", return_value=backend):
                    self.assertIn(expect, setup.welcome(), backend)
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
        self.assertIn(["demo", "--now"], [c.args[0] for c in spawn.call_args_list])
    def test_demo_in_claude_arms_a_labelled_bar(self):
        from siga import cli
        with mock.patch.dict(setup.os.environ, {"CLAUDECODE": "1"}), \
             mock.patch.object(cli.core, "detect_backend", return_value="kitty"), \
             mock.patch.object(hook.core, "spawn_detached"):
            cli.main(["demo"])
            shown = hook.messagedisplay({"message_id": "m", "delta": "Here.", "final": True})
        self.assertIn("demo", shown["hookSpecificOutput"]["displayContent"])

    def test_demo_in_static_terminal_names_it(self):
        from siga import cli
        out = io.StringIO()
        with mock.patch.dict(setup.os.environ, {"TERM_PROGRAM": "herdr", "CLAUDECODE": "1"}), \
             mock.patch.object(cli.core, "detect_backend", return_value="text"), \
             contextlib.redirect_stdout(out):
            cli.main(["demo"])
        self.assertIn("herdr can't show a live bar", out.getvalue())
        self.assertFalse(setup.core.WELCOME.exists())

    def test_demo_help_does_not_crash(self):
        from siga import cli
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(["demo", "--help"]), 0)
        self.assertIn("usage", out.getvalue())


class Output(unittest.TestCase):
    def run_plan(self, env):
        out = io.StringIO()
        with mock.patch.dict(setup.os.environ, env, clear=False), \
             mock.patch.object(setup, "plan", return_value=[]), \
             mock.patch.object(setup, "welcome", return_value="WELCOME"), \
             contextlib.redirect_stdout(out):
            setup.main(["--plan"])
        return out.getvalue().strip().splitlines()

    def test_herdr_gets_one_line_naming_it(self):
        with mock.patch.object(setup.core, "detect_backend", return_value="text"):
            lines = self.run_plan({"TERM_PROGRAM": "herdr"})
        self.assertEqual(len(lines), 1)
        self.assertIn("herdr", lines[0])

    def test_herdr_on_kitty_names_both(self):
        with mock.patch.object(setup.core, "detect_backend", return_value="kitty"), \
             mock.patch.dict(setup.os.environ, {"TERM_PROGRAM": "herdr"}):
            self.assertIn("Kitty (through herdr)", setup.where())

    def test_kitty_never_mentions_ghostty(self):
        with mock.patch.object(setup.core, "detect_backend", return_value="kitty"):
            lines = self.run_plan({})
        self.assertNotIn("Ghostty", " ".join(lines))
        self.assertEqual(lines[-1], "WELCOME")

    def test_apply_does_not_repeat_the_terminal_line(self):
        out = io.StringIO()
        with mock.patch.object(setup.core, "detect_backend", return_value="ghostty"), \
             mock.patch.object(setup, "plan", return_value=[("copy font  /x", lambda: None)]), \
             mock.patch.object(setup, "reload_terminals", return_value=1), \
             mock.patch.object(setup, "welcome", return_value="WELCOME"), \
             contextlib.redirect_stdout(out):
            setup.main(["--apply"])
        self.assertNotIn("You're in", out.getvalue())
        self.assertEqual(out.getvalue().splitlines()[-1], "WELCOME")


if __name__ == "__main__":
    unittest.main()
