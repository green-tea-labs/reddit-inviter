import ast
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINTS = (
    "daily_inviter/reddit_inviter.py",
    "daily_inviter/lan_status_server.py",
    "daily_poster/daily_puzzle_reddit_poster.py",
    "daily_poster/daily_challenge_reddit_poster.py",
    "daily_poster/midday_quiz_reddit_poster.py",
    "switch_reddit_account.py",
    "discover_ui.py",
    "debug_reddit_feed.py",
    "benchmark_inviter.py",
)


class RunLoggingTests(unittest.TestCase):
    def run_child(self, directory, body):
        source = (
            "import sys, logging\n"
            "from console_output import start_run_logging, run_with_logging\n"
            f"log_root = {str(directory)!r}\n"
            + body
        )
        return subprocess.run(
            [sys.executable, "-X", "utf8", "-c", source],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )

    def only_log(self, directory):
        paths = list(Path(directory).rglob("*.txt"))
        self.assertEqual(len(paths), 1)
        return paths[0].read_text(encoding="utf-8")

    def test_stdout_stderr_debug_unicode_and_success_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_child(directory, '''
def main():
    print('progress 🍍', flush=True)
    print('diagnostic error', file=sys.stderr)
    logging.getLogger('bot.test').debug('detailed library event')
run_with_logging('example_bot.py', main, log_root=log_root)
''')
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = self.only_log(directory)
            for text in ("progress 🍍", "[stdout]", "diagnostic error", "[stderr]", "DEBUG bot.test", "detailed library event", "success (exit code 0)", "runtime=", "Python:", "Working directory:", "Dependencies:"):
                self.assertIn(text, saved)
            self.assertIn("progress 🍍", result.stdout)
            self.assertIn("diagnostic error", result.stderr)
            self.assertNotIn("detailed library event", result.stdout + result.stderr)

    def test_uncaught_traceback_and_failure_are_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_child(directory, '''
def main():
    print('last action before crash')
    raise RuntimeError('simulated Android failure')
run_with_logging('crashing_bot.py', main, log_root=log_root)
''')
            self.assertEqual(result.returncode, 1)
            saved = self.only_log(directory)
            self.assertIn("last action before crash", saved)
            self.assertIn("Traceback (most recent call last)", saved)
            self.assertIn("RuntimeError: simulated Android failure", saved)
            self.assertIn("End: failed: RuntimeError", saved)

    def test_dependency_import_failure_is_saved_before_main(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_child(directory, '''
start_run_logging('missing_dependency_bot.py', log_root=log_root)
import deliberately_missing_bot_dependency
''')
            self.assertEqual(result.returncode, 1)
            saved = self.only_log(directory)
            self.assertIn("ModuleNotFoundError", saved)
            self.assertIn("End: failed: ModuleNotFoundError", saved)

    def test_reinitialization_shares_one_log_and_nonzero_exit_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_child(directory, '''
first = start_run_logging('scheduled_poster.py', log_root=log_root)
assert first == start_run_logging('shared_helper.py', log_root=log_root)
def main():
    raise SystemExit(2)
run_with_logging('scheduled_poster.py', main, log_root=log_root)
''')
            self.assertEqual(result.returncode, 2)
            saved = self.only_log(directory)
            self.assertIn("exit code 2", saved)
            self.assertEqual(saved.count("Run started:"), 1)

    def test_separate_processes_keep_separate_run_files(self):
        with tempfile.TemporaryDirectory() as directory:
            body = "run_with_logging('same_bot.py', lambda: print('completed'), log_root=log_root)\n"
            for _ in range(2):
                result = self.run_child(directory, body)
                self.assertEqual(result.returncode, 0, result.stderr)
            paths = list(Path(directory).rglob("*.txt"))
            self.assertEqual(len(paths), 2)
            self.assertTrue(all("success (exit code 0)" in path.read_text(encoding="utf-8") for path in paths))

    def test_every_entry_point_bootstraps_and_wraps_execution(self):
        for relative_path in ENTRY_POINTS:
            with self.subTest(script=relative_path):
                tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
                calls = [node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
                self.assertIn("start_run_logging", calls)
                self.assertIn("run_with_logging", calls)


if __name__ == "__main__":
    unittest.main()
