import asyncio
import types
import unittest
from unittest import mock

from runtime.startup_recovery import StartupRecovery


class _Managed:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    async def recover_startup(self):
        self.calls += 1
        return self.result


class StartupRecoveryTests(unittest.TestCase):
    def test_recovery_order_is_managed_mix_then_live_then_observer(self):
        events = []

        class Managed:
            def __init__(self, name):
                self.name = name

            async def recover_startup(self):
                events.append(self.name)
                return True

        app = types.SimpleNamespace()
        coordinator = StartupRecovery(
            app,
            Managed("mix"),
            Managed("live"),
            Managed("observer"),
        )
        with mock.patch(
            "runtime.startup_recovery.recover_diagnostic_persistence",
            new=mock.AsyncMock(),
        ) as recover_diagnostics:
            self.assertTrue(asyncio.run(coordinator.recover_managed_startup_authority()))
            recover_diagnostics.assert_awaited_once_with(app)
        self.assertEqual(events, ["mix", "live", "observer"])

    def test_failed_ownership_recovery_short_circuits(self):
        mix = _Managed(False)
        live = _Managed(True)
        coordinator = StartupRecovery(types.SimpleNamespace(), mix, live)

        self.assertFalse(asyncio.run(coordinator.recover_managed_startup_authority()))
        self.assertEqual(mix.calls, 1)
        self.assertEqual(live.calls, 0)


if __name__ == "__main__":
    unittest.main()
