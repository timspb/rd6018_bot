import unittest
from unittest.mock import AsyncMock, patch

from application.charge_session_tick import run_charge_session_tick
from production_controller import create_production_charge_host


class DummyHass:
    pass


class V2NotificationIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_managed_profile_refreshes_legacy_hourly_clock_before_scaffold_tick(self):
        controller = create_production_charge_host(DummyHass())
        controller.battery_type = controller.PROFILE_CA
        controller.current_stage = controller.STAGE_MAIN
        controller._last_hourly_report = 0.0

        with patch(
            "application.charge_session_tick._run_charge_session_tick_body",
            new=AsyncMock(return_value={}),
        ) as session_body:
            result = await run_charge_session_tick(controller,
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
        session_body.assert_awaited_once()

    async def test_custom_profile_retains_legacy_hourly_reporting_contract(self):
        controller = create_production_charge_host(DummyHass())
        controller.battery_type = controller.PROFILE_CUSTOM
        controller.current_stage = controller.STAGE_MAIN
        controller._last_hourly_report = 0.0

        with patch(
            "application.charge_session_tick._run_charge_session_tick_body",
            new=AsyncMock(return_value={}),
        ):
            await run_charge_session_tick(controller,
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
