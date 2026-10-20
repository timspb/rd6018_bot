import unittest
from auto_strategy import AutoStrategyProductionChargeController


class DummyHass:
    pass


class AutoStrategyScaffoldTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_has_no_stage_router_compatibility_entry(self):
        controller = AutoStrategyProductionChargeController(DummyHass())
        self.assertFalse(hasattr(controller, "_run_stage_scaffold_tick"))

    def test_production_mix_limits_are_20_24_10(self):
        controller = AutoStrategyProductionChargeController(DummyHass())
        for profile, hours in (("Ca/Ca", 20.0), ("EFB", 24.0), ("AGM", 10.0)):
            controller.battery_type = profile
            controller.current_stage = controller.STAGE_MIX
            controller.finish_timer_start = None
            self.assertEqual(controller._get_stage_max_hours(), hours)


if __name__ == "__main__":
    unittest.main()
