"""Which commands the PreToolUse hook wraps, and how."""
import sys
import unittest
from pathlib import Path

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
            "cat <<EOF | make\nx\nEOF",
            "siga status",
            "curl -s -o /dev/null -w '%{http_code}' https://example.com",
            "curl -s --output /dev/null https://example.com",
            "mise run job:wait -- x.log",
        ]:
            self.assertIsNone(hook.decide(cmd), cmd)


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


if __name__ == "__main__":
    unittest.main()
