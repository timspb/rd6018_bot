import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import database
from charge_controller_v2 import ChargeControllerV2
from recovery_trace_store import export_replay_document, list_trace_sessions


class DummyHass:
    pass


class RecoveryTraceCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await database.close_db()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(self.tempdir.name, "capture.db")

    async def asyncTearDown(self):
        await database.close_db()
        database.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    @staticmethod
    def _controller() -> ChargeControllerV2:
        controller = ChargeControllerV2(DummyHass())
        controller.current_stage = controller.STAGE_MAIN
        controller.battery_type = controller.PROFILE_EFB
        controller.ah_capacity = 70
        controller.stage_start_time = 900.0
        controller.total_start_time = 900.0
        controller._v2_target_voltage_v = 14.8
        controller._last_known_output_on = True
        return controller

    async def _tick(self, controller: ChargeControllerV2):
        with patch("charge_logic.time.time", return_value=1000.0):
            return await controller.tick(
                voltage=14.75,
                current=0.70,
                temp_ext=25.0,
                is_cv=True,
                ah=5.0,
                output_is_on=True,
                is_cc=False,
            )

    async def test_controller_is_side_effect_free_before_production_db_init(self):
        controller = self._controller()
        actions = await self._tick(controller)

        self.assertFalse(database.TRACE_CAPTURE_READY)
        self.assertNotIn("persistence", actions["recovery_shadow"])
        self.assertFalse(os.path.exists(database.DB_PATH))

    async def test_init_db_enables_live_trace_capture_and_replay_export(self):
        await database.init_db()
        controller = self._controller()
        actions = await self._tick(controller)

        self.assertTrue(database.TRACE_CAPTURE_READY)
        self.assertEqual(actions["recovery_shadow"]["persistence"], "stored")

        sessions = await list_trace_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["sample_count"], 1)
        self.assertEqual(sessions[0]["battery_type"], "EFB")
        self.assertAlmostEqual(sessions[0]["capacity_ah"], 70.0)

        document = await export_replay_document(sessions[0]["session_id"])
        trace = document["cycles"][0]["trace"]
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["stage"], controller.STAGE_MAIN)
        self.assertAlmostEqual(trace[0]["target_voltage_v"], 14.8)
        self.assertTrue(trace[0]["is_cv"])

    async def test_trace_persistence_failure_does_not_invalidate_legacy_actions(self):
        await database.init_db()
        controller = self._controller()

        with patch.object(
            controller,
            "_persist_shadow_trace_if_ready",
            new=AsyncMock(side_effect=RuntimeError("synthetic storage failure")),
        ):
            actions = await self._tick(controller)

        shadow = actions["recovery_shadow"]
        self.assertEqual(shadow["status"], "ok")
        self.assertEqual(shadow["persistence"], "error")
        self.assertEqual(shadow["persistence_error_type"], "RuntimeError")
        self.assertNotIn("emergency_stop", actions)
        self.assertEqual(controller.current_stage, controller.STAGE_MAIN)


if __name__ == "__main__":
    unittest.main()
