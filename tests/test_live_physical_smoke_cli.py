import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from runtime.output.bridge import HardwareSnapshot
from runtime.physical.transports.comparator import PhysicalSnapshotComparison
from runtime.bench.live.models import LiveSnapshotRun, PhysicalSnapshotEvidence


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "live_physical_smoke.py"
spec = importlib.util.spec_from_file_location("live_physical_smoke", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class LivePhysicalSmokeCliTests(unittest.IsolatedAsyncioTestCase):
    def _evidence(self, status="MATCH", qualities=("VALID", "VALID")):
        ha = HardwareSnapshot(1, "connected", False, 13.2, 0.0, 13.7, 0.1, 14.2, 0.2, 25.0, 13.2)
        esp = HardwareSnapshot(2, "connected", False, 13.2, 0.0, 13.7, 0.1, 14.2, 0.2, 25.0, 13.2)
        return PhysicalSnapshotEvidence(
            3, "test", ha, esp,
            PhysicalSnapshotComparison(status, (), "equal" if status == "MATCH" else "x"),
            (
                LiveSnapshotRun(1, "ha102", "ha102", ha, qualities[0]),
                LiveSnapshotRun(2, "esp128", "esp128", esp, qualities[1]),
            ),
        )

    def test_payload_pass_is_sanitized(self):
        payload = module._payload(self._evidence())
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["comparison"]["status"], "MATCH")
        self.assertNotIn("timestamp", payload["ha102"])
        self.assertNotIn("token", json.dumps(payload).lower())
        self.assertNotIn("key", json.dumps(payload).lower())

    def test_payload_blocks_on_inconclusive_or_invalid_transport(self):
        self.assertEqual(module._payload(self._evidence("INCONCLUSIVE"))["status"], "BLOCKED")
        self.assertEqual(module._payload(self._evidence(qualities=("VALID", "ERROR")))["status"], "BLOCKED")

    async def test_run_fails_closed_on_config_error(self):
        with patch.object(module, "load_config", side_effect=ValueError("missing host")):
            with patch("builtins.print") as output:
                code = await module._run("test", "config")
        self.assertEqual(code, 2)
        payload = json.loads(output.call_args.args[0])
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertIn("missing host", payload["error"])


if __name__ == "__main__":
    unittest.main()
