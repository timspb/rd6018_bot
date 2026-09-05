import unittest
from unittest.mock import AsyncMock, patch

from charge_controller_v2 import ChargeControllerV2
from production_controller import ProductionChargeControllerV2


class DummyHass:
    pass


class V2NotificationIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_managed_profile_refreshes_legacy_hourly_clock_before_scaffold_tick(self):
        controller = ProductionChargeControllerV2(DummyHass())
        controller.battery_type = controller.PROFILE_CA
        controller.current_stage = controller.STAGE_MAIN
        controller._last_hourly_report = 0.0

        with patch.object(ChargeControllerV2, "tick", new=AsyncMock(return_value={})) as parent_tick:
            result = await controller.tick(
                14.7,
                0.1,
                23.0,
                True,
                1.0,
                output_is_on=True,
                is_cc=False,
            )

        self.assertEqual(result, {})
        self.assertGreater(controller._last_hourly_report, 0.0)
        parent_tick.assert_awaited_once()

    async def test_custom_profile_retains_legacy_hourly_reporting_contract(self):
        controller = ProductionChargeControllerV2(DummyHass())
        controller.battery_type = controller.PROFILE_CUSTOM
        controller.current_stage = controller.STAGE_MAIN
        controller._last_hourly_report = 0.0

        with patch.object(ChargeControllerV2, "tick", new=AsyncMock(return_value={})):
            await controller.tick(
                14.4,
                1.0,
                23.0,
                True,
                1.0,
                output_is_on=True,
                is_cc=False,
            )

        self.assertEqual(controller._last_hourly_report, 0.0)


if __name__ == "__main__":
    unittest.main()
