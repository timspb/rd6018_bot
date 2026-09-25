import unittest

from runtime.bench.live import LiveSmokeRunner
from runtime.config import load_config
from runtime.output.bridge import HardwareSnapshot
from runtime.physical.transports import PhysicalSnapshotComparator


class V3LiveSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_with_mocked_factory(self):
        config = load_config("config")
        runner = LiveSmokeRunner(config)
        class FakeTransport:
            config = type("Profile", (), {"name": "fake", "entities": {"v": "v"}})()
            async def discover(self): return ("v",)
            async def get_snapshot(self): return HardwareSnapshot(1, "connected", False, 12, 1)
            async def get_capabilities(self): return None
            async def health_check(self): return {"connected": True}
            async def close(self): pass
        class FakeFactory:
            def create(self, name): return FakeTransport()
        import runtime.bench.live.runner as module
        original = module.PhysicalTransportFactory
        module.PhysicalTransportFactory = lambda config: FakeFactory()
        try:
            evidence = await runner.run("test")
        finally:
            module.PhysicalTransportFactory = original
        self.assertEqual(len(evidence.runs), 2)
        self.assertEqual(evidence.comparison.status, "MATCH")

    def test_evidence_and_tolerance(self):
        a = HardwareSnapshot(100, "connected", False, 14.4, 2)
        b = HardwareSnapshot(105, "connected", False, 14.44, 2.04)
        self.assertEqual(PhysicalSnapshotComparator.compare(a, b, .06, 10, .06).status, "MATCH")
        self.assertEqual(PhysicalSnapshotComparator.compare(a, b, .01, 1, .01).status, "MISMATCH")
