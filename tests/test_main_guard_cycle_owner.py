from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from application import main_guard_runtime


class MainGuardCycleOwnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.controller = SimpleNamespace(
            current_stage="Main Charge", STAGE_MAIN="Main Charge",
            battery_type="EFB", _main_current_guard=None,
        )
        self.shadow = Mock()
        self.admission = SimpleNamespace(
            session_id="session-1", battery_id="battery-1", capacity_ah=100.0,
            recipe_initial_current_a=10.0, guard_revision=7,
        )
        self.live = {
            "_meta": {"source": "esp_native_api"},
            "output_state_code_v2": 1,
            "current": 4.0,
        }

    def _common_patches(self, admitted=True):
        admission = self.admission if admitted else None
        return (
            patch.object(main_guard_runtime, "read_canonical_session", return_value={"canonical": True}),
            patch.object(main_guard_runtime, "admit_main_guard_shadow", return_value=admission),
            patch.object(main_guard_runtime, "telemetry_freshness", return_value=SimpleNamespace(valid=True)),
            patch.object(main_guard_runtime, "finite_float", side_effect=lambda value: value),
        )

    async def test_fresh_native_observation_reaches_existing_executor(self):
        execute = AsyncMock(return_value="executed")
        patches = self._common_patches()
        with patches[0], patches[1], patches[2], patches[3], patch.object(
            main_guard_runtime, "execute_due_main_guard", execute
        ), patch.object(main_guard_runtime.time, "monotonic", return_value=12.0):
            self.shadow.observe.return_value = "proposal"
            result = await main_guard_runtime.run_main_guard_cycle(
                app=object(), port=object(), controller=self.controller,
                shadow=self.shadow, live=self.live, session_path="session.json",
                now_epoch_s=1000.0, manual_active=False,
                manual_off_condition=False,
            )
        self.assertEqual(result, "executed")
        self.assertEqual(self.shadow.observe.call_args.kwargs["output_on"], True)
        self.assertEqual(self.shadow.observe.call_args.kwargs["output_current_a"], 4.0)
        self.assertTrue(self.shadow.observe.call_args.kwargs["fresh"])
        execute.assert_awaited_once()

    async def test_unknown_native_output_is_fail_closed(self):
        execute = AsyncMock()
        patches = self._common_patches()
        with patches[0], patches[1], patch.object(
            main_guard_runtime, "telemetry_freshness", return_value=SimpleNamespace(valid=False)
        ), patches[3], patch.object(main_guard_runtime, "execute_due_main_guard", execute):
            self.shadow.observe.return_value = None
            result = await main_guard_runtime.run_main_guard_cycle(
                app=object(), port=object(), controller=self.controller,
                shadow=self.shadow, live=self.live, session_path="session.json",
                now_epoch_s=1000.0, manual_active=False,
                manual_off_condition=False,
            )
        self.assertIsNone(result)
        self.assertIsNone(self.shadow.observe.call_args.kwargs["output_on"])
        self.assertIsNone(self.shadow.observe.call_args.kwargs["output_current_a"])
        self.assertFalse(self.shadow.observe.call_args.kwargs["fresh"])
        execute.assert_not_awaited()

    async def test_manual_and_operator_off_conditions_suppress_execution(self):
        execute = AsyncMock()
        patches = self._common_patches()
        with patches[0], patches[1], patches[2], patches[3], patch.object(
            main_guard_runtime, "execute_due_main_guard", execute
        ):
            self.shadow.observe.return_value = "proposal"
            await main_guard_runtime.run_main_guard_cycle(
                app=object(), port=object(), controller=self.controller,
                shadow=self.shadow, live=self.live, session_path="session.json",
                now_epoch_s=1000.0, manual_active=True,
                manual_off_condition=False,
            )
            await main_guard_runtime.run_main_guard_cycle(
                app=object(), port=object(), controller=self.controller,
                shadow=self.shadow, live=self.live, session_path="session.json",
                now_epoch_s=1000.0, manual_active=False,
                manual_off_condition=True,
            )
        execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
