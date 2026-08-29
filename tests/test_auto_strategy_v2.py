import unittest
from unittest.mock import patch

from auto_strategy_v2 import AutoStrategyProductionChargeControllerV2
from production_controller import ProductionChargeControllerV2


class DummyHass:
    pass


class AutoStrategyScaffoldTests(unittest.IsolatedAsyncioTestCase):
    async def test_authoritative_main_hides_elapsed_clock_from_legacy_scaffold_then_restores_it(self):
        controller = AutoStrategyProductionChargeControllerV2(DummyHass(), authoritative=True)
        controller.current_stage = controller.STAGE_MAIN
        real_start = 1000.0
        now = real_start + 80 * 3600
        controller.stage_start_time = real_start
        seen = []

        async def fake_parent(_self, **_kwargs):
            seen.append(_self.stage_start_time)
            return {"legacy": True}

        with patch.object(
            ProductionChargeControllerV2,
            "_run_legacy_scaffold_tick",
            new=fake_parent,
        ), patch("auto_strategy_v2.time.time", return_value=now):
            actions = await controller._run_legacy_scaffold_tick(
                stage_before=controller.STAGE_MAIN,
                voltage=14.8,
                current=0.5,
                temp_ext=25.0,
                is_cv=True,
                ah=20.0,
                output_is_on=True,
                manual_off_active=False,
                is_cc=False,
            )

        self.assertEqual(actions, {"legacy": True})
        self.assertEqual(seen, [now])
        self.assertEqual(controller.stage_start_time, real_start)

    def test_production_mix_limits_are_20_24_10(self):
        controller = AutoStrategyProductionChargeControllerV2(DummyHass(), authoritative=True)
        for profile, hours in (("Ca/Ca", 20.0), ("EFB", 24.0), ("AGM", 10.0)):
            controller.battery_type = profile
            controller.current_stage = controller.STAGE_MIX
            controller.finish_timer_start = None
            self.assertEqual(controller._get_stage_max_hours(), hours)


if __name__ == "__main__":
    unittest.main()
