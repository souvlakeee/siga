"""Which commands the PreToolUse hook wraps, and how."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from siga import hooks as hook  # noqa: E402


class Decide(unittest.TestCase):
    def test_wrapped(self):
        for cmd, mode in [
            ("npm run build", "pipe"),
            ("cd app && npm run build 2>&1 | tail -20", "pipe"),
            ("CI=1 cargo build --release", "pty"),
            ("sudo docker build -t x .", "pipe"),
            ("curl -L -o file.zip https://x/y.zip", "pipe"),
            ("git clone https://x/repo.git", "pipe"),
            ("pip install -r requirements.txt", "pty"),
            ("make -j8 | grep -E \"error|warn\"", "pipe"),
            (".venv/bin/pip install --no-cache-dir .", "pty"),
            ("cd web && ./node_modules/.bin/vite build", "pipe"),
            ("/opt/homebrew/bin/cargo build --release", "pty"),
        ]:
            self.assertEqual(hook.decide(cmd), mode, cmd)

    def test_left_alone(self):
        for cmd in [
            "ls -la",
            'for t in pv ffmpeg curl; do command -v $t; done',
            "echo 'npm run build'",
            "curl -s https://api.example.com/health",
            "grep -rn cargo src/",
            "npm run dev &",
            "npm run build & echo started",
            "nohup npm run build & echo started",
            "cat <<EOF | make\nx\nEOF",
            "siga status",
            "curl -s -o /dev/null -w '%{http_code}' https://example.com",
            "curl -s --output /dev/null https://example.com",
            "mise run job:wait -- x.log",
        ]:
            self.assertIsNone(hook.decide(cmd), cmd)

    def test_background_detection(self):
        # a top-level `&` backgrounds the job (issue #1), so it is not wrapped
        self.assertTrue(hook.backgrounds("npm run build & echo x"))
        self.assertTrue(hook.backgrounds("nohup npm run build > log 2>&1 &"))
        self.assertTrue(hook.backgrounds("npm run build &"))
        # `&&`, redirections and quoted `&` are NOT backgrounding
        self.assertFalse(hook.backgrounds("cd app && npm run build 2>&1 | tail -20"))
        self.assertFalse(hook.backgrounds("npm run build > out 2>&1"))
        self.assertFalse(hook.backgrounds("npm run build &> out"))
        self.assertFalse(hook.backgrounds("echo 'a & b'"))
        self.assertFalse(hook.backgrounds("make -j8 | grep -E 'error|warn'"))


class ProjectConfig(unittest.TestCase):
    def test_project_pattern_loads(self):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("[wrap]\npipe = ['^frobnicate']\n")
            path = f.name
        os.environ["SIGA_PROJECT_CONFIG"] = path
        try:
            # a token no default pattern matches — wrapping proves the repo-local siga.toml was read
            self.assertEqual(hook.decide("frobnicate the gizmo"), "pipe")
        finally:
            os.environ.pop("SIGA_PROJECT_CONFIG", None)
            os.unlink(path)


class Wrap(unittest.TestCase):
    def test_filter_moves_after_siga(self):
        out = hook.wrap('make -j8 | grep -E "error|warn"', "pipe")
        self.assertIn('make -j8\n} 2>&1 | siga pipe', out)
        self.assertTrue(out.endswith('| grep -E "error|warn"; siga end $?'))

    def test_filter_not_last_segment(self):
        body, tail = hook.split_filter("brew info x 2>&1 | head -1; gh api user")
        self.assertEqual(tail, "")

    def test_pty_form(self):
        out = hook.wrap("cargo build 2>&1 | tail -5", "pty")
        self.assertIn("siga run --pty -k", out)
        self.assertIn("-- sh -c 'cargo build' | tail -5", out)

    def test_git_progress(self):
        self.assertIn("git clone --progress https://x", hook.wrap("git clone https://x", "pipe"))
        self.assertIn("git pull --progress", hook.wrap("git pull --progress", "pipe").replace("--progress --progress", "X"))


class MessageDisplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            mock.patch.object(hook.core, "CACHE", Path(self.tmp.name)),
            mock.patch.object(hook.core, "WELCOME", Path(self.tmp.name) / "welcome"),
            mock.patch.dict(hook.os.environ, {"SIGA_TTY": "/dev/ttysTEST", "SIGA_BACKEND": "ghostty"}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_two_tokens_get_two_slots(self):
        with mock.patch.object(hook.core, "detect_backend", return_value="ghostty"):
            out = hook.messagedisplay({"message_id": "m", "delta": "a ⟦bar⟧\nb ⟦bar⟧", "final": True})
        shown = out["hookSpecificOutput"]["displayContent"]
        self.assertNotIn(hook.TOKEN, shown)
        self.assertIn(chr(0x10FB00), shown)       # family 0 (slot 0)
        self.assertIn(chr(0x10FB00 + 20), shown)  # family 1 (slot 1): a distinct bar


if __name__ == "__main__":
    unittest.main()
