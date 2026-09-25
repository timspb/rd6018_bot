import os
import subprocess
import sys
import unittest


class GraphingLazyImportTests(unittest.TestCase):
    def test_runtime_import_does_not_load_graphing_stack(self):
        code = (
            "import sys; import runtime.v2_runtime; "
            "assert not any(name == 'graphing' or name == 'matplotlib' or "
            "name == 'numpy' or name.startswith('matplotlib.') or "
            "name.startswith('numpy.') for name in sys.modules)"
        )
        env = os.environ.copy()
        env["TG_TOKEN"] = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"
        env.pop("TELEGRAM_BOT_TOKEN", None)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_chart_generation_still_loads_graphing_stack(self):
        from graphing import generate_chart

        chart = generate_chart(
            ["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"],
            [12.6, 12.7],
            [0.1, 0.2],
            [25.0, 25.1],
        )
        self.assertGreater(len(chart.getvalue()), 100)


if __name__ == "__main__":
    unittest.main()
