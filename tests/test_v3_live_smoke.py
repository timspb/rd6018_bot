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
            async def get_snapshot(self):
                return HardwareSnapshot(1, "connected", False, 12, 0, 12.5, 0.1, 13.0, 0.2, 25, 12)
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
        self.assertEqual([item.quality for item in evidence.runs], ["VALID", "VALID"])
        self.assertEqual(evidence.comparison.status, "MATCH")

    async def test_connected_but_incomplete_snapshot_is_invalid(self):
        config = load_config("config")
        runner = LiveSmokeRunner(config)

        class FakeTransport:
            async def discover(self): return ()
            async def get_snapshot(self): return HardwareSnapshot(1, "connected")
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
        self.assertEqual([item.quality for item in evidence.runs], ["INVALID", "INVALID"])
        self.assertTrue(all("missing_fields:" in item.errors[0] for item in evidence.runs))

    def test_evidence_and_tolerance(self):
        a = HardwareSnapshot(100, "connected", False, 14.4, 2)
        b = HardwareSnapshot(105, "connected", False, 14.44, 2.04)
        self.assertEqual(PhysicalSnapshotComparator.compare(a, b, .06, 10, .06).status, "MATCH")
        self.assertEqual(PhysicalSnapshotComparator.compare(a, b, .01, 1, .01).status, "MISMATCH")
