import inspect
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from charge_controller_v2 import ChargeControllerV2
from charge_logic import ChargeController
from production_controller import ProductionChargeControllerV2
from runtime.charge.strategy import mix as mix_strategy
from runtime.charge.strategy.final_safe_wait import (
    FinalSafeWaitContinuation,
    decide_final_safe_wait,
    validate_final_continuation,
)
from runtime.charge.strategy.mix_variables import (
    AGM_MIX_MAX_ACTIVE_HOURS,
    AGM_MIX_VOLTAGE_V,
    CA_MIX_MAX_ACTIVE_HOURS,
    CA_MIX_VOLTAGE_V,
    EFB_MIX_MAX_ACTIVE_HOURS,
    EFB_MIX_VOLTAGE_V,
    MIX_CURRENT_C_RATE,
    MIX_FINISH_HOLD_HOURS,
    MIX_MIN_CURRENT_A,
)
from runtime.charge.strategy.storage import (
    STORAGE_CURRENT_A,
    STORAGE_VOLTAGE_V,
)


class DummyHass:
    pass


class V3MixAuthorityMigrationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _controller(stage: str) -> ChargeControllerV2:
        controller = ChargeControllerV2(DummyHass(), authoritative=True)
        controller.battery_type = controller.PROFILE_AGM
        controller.ah_capacity = 90
        controller.current_stage = stage
        controller.stage_start_time = 1000.0
        controller.total_start_time = 500.0
        controller._stage_start_ah = 10.0
        controller._v2_trace_session_id = "session-final"
        controller._v2_trace_started_at = 500.0
        controller._last_known_output_on = stage != controller.STAGE_SAFE_WAIT
        return controller

    @staticmethod
    def _final_continuation(
        controller: ChargeControllerV2,
        *,
        generation: float | None = None,
    ) -> FinalSafeWaitContinuation:
        return FinalSafeWaitContinuation(
            source_stage=controller.STAGE_MIX,
            next_stage=controller.STAGE_DONE,
            target_voltage_v=13.8,
            target_current_a=1.0,
            started_at=1050.0,
            session_id=controller._v2_trace_session_id,
            completion_reason="confirmed_delta_finish_hold_complete",
            session_generation=(
                controller._v2_trace_started_at
                if generation is None
                else generation
            ),
        )

    def test_modular_mix_strategy_has_no_historical_controller_dependency(self):
        source = inspect.getsource(mix_strategy)
        self.assertNotIn("charge_logic", source)
        self.assertNotIn("ChargeController", source)

    def test_mix_and_storage_variable_metadata_is_explicit_and_single_owner(self):
        mix_specs = (
            AGM_MIX_MAX_ACTIVE_HOURS,
            AGM_MIX_VOLTAGE_V,
            CA_MIX_MAX_ACTIVE_HOURS,
            CA_MIX_VOLTAGE_V,
            EFB_MIX_MAX_ACTIVE_HOURS,
            EFB_MIX_VOLTAGE_V,
            MIX_CURRENT_C_RATE,
            MIX_FINISH_HOLD_HOURS,
            MIX_MIN_CURRENT_A,
        )
        for spec in mix_specs:
            self.assertEqual(spec.owner, "runtime.charge.strategy.mix")
            self.assertTrue(spec.key)
            self.assertTrue(spec.unit)
            self.assertTrue(spec.description)
            self.assertTrue(spec.provenance)
        for spec in (STORAGE_CURRENT_A, STORAGE_VOLTAGE_V):
            self.assertEqual(spec.owner, "runtime.charge.strategy.storage")
            self.assertTrue(spec.key)
            self.assertTrue(spec.unit)
            self.assertTrue(spec.provenance)

    async def test_authoritative_mix_never_enters_historical_tick(self):
        controller = self._controller(ChargeControllerV2.STAGE_MIX)
        with patch.object(
            ChargeController,
            "tick",
            new=AsyncMock(side_effect=AssertionError("historical tick reached")),
        ), patch("charge_controller_v2.time.time", return_value=1100.0):
            actions = await controller._run_stage_scaffold_tick(
                stage_before=controller.STAGE_MIX,
                voltage=16.3,
                current=0.5,
                temp_ext=25.0,
                is_cv=True,
                ah=12.0,
                output_is_on=True,
                manual_off_active=False,
                is_cc=False,
                manual_active=False,
            )
        self.assertIsInstance(actions, dict)
        self.assertEqual(controller.current_stage, controller.STAGE_MIX)

    async def test_final_safe_wait_never_enters_historical_tick(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        controller._final_safe_wait = self._final_continuation(controller)
        controller._safe_wait_next_stage = controller.STAGE_DONE
        with patch.object(
            ChargeController,
            "tick",
            new=AsyncMock(side_effect=AssertionError("historical tick reached")),
        ), patch("charge_controller_v2.time.time", return_value=1100.0):
            actions = await controller._run_stage_scaffold_tick(
                stage_before=controller.STAGE_SAFE_WAIT,
                voltage=13.5,
                current=0.0,
                temp_ext=25.0,
                is_cv=False,
                ah=12.0,
                output_is_on=False,
                manual_off_active=False,
                is_cc=False,
                manual_active=False,
            )
        self.assertIsInstance(actions, dict)
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)

    def test_stale_session_generation_cannot_authorize_final_continuation(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        continuation = self._final_continuation(
            controller,
            generation=controller._v2_trace_started_at - 1.0,
        )
        self.assertFalse(
            validate_final_continuation(
                continuation,
                session_id=controller._v2_trace_session_id,
                session_generation=controller._v2_trace_started_at,
                expected_next_stage=controller.STAGE_DONE,
                allowed_source_stages={controller.STAGE_MAIN, controller.STAGE_MIX},
            )
        )

    def test_persisted_final_continuation_alone_cannot_authorize_storage_enable(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        continuation = self._final_continuation(controller)
        decision = decide_final_safe_wait(
            continuation,
            now_s=10_000.0,
            voltage_v=13.0,
            output_is_off=False,
        )
        self.assertEqual(decision.reason, "fresh_output_off_required")
        self.assertEqual(decision.action.value, "wait")

    def test_stale_final_continuation_fails_closed_instead_of_falling_back(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        controller._safe_wait_next_stage = controller.STAGE_DONE
        controller._final_safe_wait = self._final_continuation(
            controller,
            generation=controller._v2_trace_started_at - 1.0,
        )
        actions = {}
        with patch.object(controller, "_save_session"):
            decision = controller._apply_final_safe_wait_authority(
                now=1100.0,
                voltage=13.0,
                current=0.0,
                temp=25.0,
                ah=12.0,
                actions=actions,
                output_is_on=False,
            )
        self.assertEqual(decision.action.value, "stop_and_diagnose")
        self.assertEqual(controller.current_stage, controller.STAGE_DONE)
        self.assertTrue(actions.get("turn_off"))
        self.assertNotIn("turn_on", actions)
        self.assertIsNone(controller._final_safe_wait)

    def test_storage_enable_request_does_not_commit_or_duplicate_while_output_is_on(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        controller._safe_wait_next_stage = controller.STAGE_DONE
        controller._final_safe_wait = self._final_continuation(controller)

        first = {}
        controller._apply_final_safe_wait_authority(
            now=1100.0,
            voltage=13.0,
            current=0.0,
            temp=25.0,
            ah=12.0,
            actions=first,
            output_is_on=False,
        )
        self.assertTrue(first.get("turn_on"))
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)

        second = {}
        controller._apply_final_safe_wait_authority(
            now=1101.0,
            voltage=13.0,
            current=0.0,
            temp=25.0,
            ah=12.0,
            actions=second,
            output_is_on=True,
        )
        self.assertNotIn("turn_on", second)
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertIsNotNone(controller._final_safe_wait)

    def test_stale_verified_storage_generation_cannot_commit_done(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        controller._safe_wait_next_stage = controller.STAGE_DONE
        controller._final_safe_wait = self._final_continuation(controller)
        actions = {}
        controller._apply_final_safe_wait_authority(
            now=1100.0,
            voltage=13.0,
            current=0.0,
            temp=25.0,
            ah=12.0,
            actions=actions,
            output_is_on=False,
        )
        token = dict(actions["verified_enable_transition"])
        token["session_generation"] = controller._v2_trace_started_at - 1.0
        with patch.object(controller, "_save_session"):
            committed = controller.commit_verified_enable_transition(
                token,
                now=1102.0,
                voltage=13.0,
                current=0.0,
                ah=12.0,
            )
        self.assertIsNone(committed)
        self.assertEqual(controller.current_stage, controller.STAGE_SAFE_WAIT)
        self.assertIsNotNone(controller._final_safe_wait)

    def test_final_safe_wait_identity_and_generation_survive_restart(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            now = 200_000.0
            controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            controller.start(controller.PROFILE_AGM, 90)
            controller.current_stage = controller.STAGE_MIX
            controller._enter_safe_wait_done(
                actions={},
                now=now,
                voltage=16.2,
                current=0.5,
                temp=25.0,
                ah=10.0,
                reason="confirmed_delta_finish_hold_complete",
            )
            expected_id = controller._v2_trace_session_id
            expected_generation = controller._v2_trace_started_at

            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=now + 30.0
            ), patch("charge_controller_v2.time.time", return_value=now + 30.0), patch(
                "production_controller.time.time", return_value=now + 30.0
            ):
                controller._save_session(15.0, 0.0, 10.0)
                restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
                ok, _ = restored.try_restore_session(
                    15.0,
                    0.0,
                    10.0,
                    output_is_on=False,
                    is_cv=False,
                    is_cc=False,
                )

            self.assertTrue(ok)
            self.assertEqual(restored.current_stage, restored.STAGE_SAFE_WAIT)
            self.assertIsNotNone(restored._final_safe_wait)
            self.assertEqual(restored._final_safe_wait.session_id, expected_id)
            self.assertAlmostEqual(
                float(restored._final_safe_wait.session_generation),
                float(expected_generation),
            )


if __name__ == "__main__":
    unittest.main()
