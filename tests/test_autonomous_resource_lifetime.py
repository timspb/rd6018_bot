"""Bound the composed autonomous tests' complete event-loop lifetime."""

import os
from pathlib import Path
import subprocess
import sys
import unittest


class AutonomousResourceLifetimeTests(unittest.TestCase):
    def test_composed_autonomous_cases_exit_after_runner_teardown(self):
        # IsolatedAsyncioTestCase prints "ok" before Runner.close(). A child
        # process ensures the assertion includes executor/session/task teardown,
        # and a leak cannot hang the parent suite indefinitely.
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env.update(
            TG_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            TELEGRAM_BOT_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            HA_URL="http://127.0.0.1:8123",
            HA_LOCAL_URL="http://127.0.0.1:8123",
            HA_TOKEN="ci-test-token",
            HA_PREFER_LOCAL="0",
            ESPHOME_API_HOST="127.0.0.1",
            ESPHOME_API_PORT="6053",
            ESPHOME_API_KEY="ci-test-key",
            ALLOWED_CHAT_IDS="1",
            ALLOW_ALL_CHATS="0",
            DEEPSEEK_BASE_URL="http://127.0.0.1:9",
        )
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_autonomous_runtime_composition.py", "-v"],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("Ran 2 tests", result.stdout)
        self.assertIn("\nOK", result.stdout)


if __name__ == "__main__":
    unittest.main()
