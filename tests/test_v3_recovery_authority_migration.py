import inspect
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from charge_controller_v2 import ChargeControllerV2
from charge_logic import ChargeController
from production_controller import ProductionChargeControllerV2
from runtime.charge.strategy import desulfation as desulfation_strategy
from runtime.charge.strategy.desulfation_variables import (
    DESULFATION_BASE_VOLTAGE_V,
    DESULFATION_CURRENT_C_RATE,
    DESULFATION_DURATION_HOURS,
    DESULFATION_MIN_CURRENT_A,
    DESULFATION_OCP_MARGIN_A,
)
from runtime.charge.strategy.recovery_safe_wait import (
    RecoverySafeWaitContinuation,
    decide_recovery_safe_wait,
    validate_recovery_continuation,
)
from runtime.charge.strategy.safe_wait_variables import (
    SAFE_WAIT_MAX_HOURS,
    SAFE_WAIT_TARGET_MARGIN_V,
)


class DummyHass:
    pass


class V3RecoveryAuthorityMigrationTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _controller(stage: str) -> ChargeControllerV2:
        controller = ChargeControllerV2(DummyHass(), authoritative=True)
        controller.battery_type = controller.PROFILE_AGM
        controller.ah_capacity = 90
        controller.current_stage = stage
        controller.stage_start_time = 1000.0
        controller.total_start_time = 500.0
        controller._stage_start_ah = 10.0
        controller._agm_stage_idx = 2
        controller.antisulfate_count = 2
        controller._v2_trace_session_id = "session-recovery"
        controller._v2_trace_started_at = 500.0
        controller._last_known_output_on = stage != controller.STAGE_SAFE_WAIT
        return controller

    def test_modular_recovery_strategy_has_no_historical_controller_dependency(self):
        source = inspect.getsource(desulfation_strategy)
        self.assertNotIn("charge_logic", source)
        self.assertNotIn("ChargeController", source)

    def test_recovery_variable_metadata_is_explicit_and_single_owner(self):
        desulf_specs = (
            DESULFATION_BASE_VOLTAGE_V,
            DESULFATION_CURRENT_C_RATE,
            DESULFATION_DURATION_HOURS,
            DESULFATION_MIN_CURRENT_A,
            DESULFATION_OCP_MARGIN_A,
        )
        for spec in desulf_specs:
            self.assertEqual(spec.owner, "runtime.charge.strategy.desulfation")
            self.assertTrue(spec.key)
            self.assertTrue(spec.unit)
            self.assertTrue(spec.description)
            self.assertTrue(spec.provenance)
        for spec in (SAFE_WAIT_MAX_HOURS, SAFE_WAIT_TARGET_MARGIN_V):
            self.assertEqual(spec.owner, "runtime.charge.strategy.safe_wait")
            self.assertTrue(spec.key)
            self.assertTrue(spec.provenance)

    async def test_authoritative_desulfation_never_enters_historical_tick(self):
        controller = self._controller(ChargeControllerV2.STAGE_DESULFATION)
        with patch.object(
            ChargeController,
            "tick",
            new=AsyncMock(side_effect=AssertionError("historical tick reached")),
        ), patch("charge_controller_v2.time.time", return_value=1100.0):
            actions = await controller._run_stage_scaffold_tick(
                stage_before=controller.STAGE_DESULFATION,
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
        self.assertEqual(controller.current_stage, controller.STAGE_DESULFATION)

    async def test_recovery_safe_wait_never_enters_historical_tick(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        controller._recovery_safe_wait = RecoverySafeWaitContinuation(
            source_stage=controller.STAGE_DESULFATION,
            next_stage=controller.STAGE_MAIN,
            target_voltage_v=14.8,
            target_current_a=9.0,
            started_at=1050.0,
            session_id=controller._v2_trace_session_id,
            recovery_attempt=controller.antisulfate_count,
            agm_stage_idx=controller._agm_stage_idx,
            session_generation=controller._v2_trace_started_at,
        )
        controller._safe_wait_next_stage = controller.STAGE_MAIN
        with patch.object(
            ChargeController,
            "tick",
            new=AsyncMock(side_effect=AssertionError("historical tick reached")),
        ), patch("charge_controller_v2.time.time", return_value=1100.0):
            actions = await controller._run_stage_scaffold_tick(
                stage_before=controller.STAGE_SAFE_WAIT,
                voltage=14.5,
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

    def test_stale_session_generation_cannot_authorize_recovery_continuation(self):
        continuation = RecoverySafeWaitContinuation(
            source_stage=ChargeControllerV2.STAGE_DESULFATION,
            next_stage=ChargeControllerV2.STAGE_MAIN,
            target_voltage_v=14.8,
            target_current_a=9.0,
            started_at=1100.0,
            session_id="session-recovery",
            recovery_attempt=2,
            agm_stage_idx=2,
            session_generation=499.0,
        )
        self.assertFalse(
            validate_recovery_continuation(
                continuation,
                session_id="session-recovery",
                session_generation=500.0,
                expected_source_stage=ChargeControllerV2.STAGE_DESULFATION,
                expected_next_stage=ChargeControllerV2.STAGE_MAIN,
            )
        )

    def test_persisted_continuation_alone_cannot_authorize_output_enable(self):
        continuation = RecoverySafeWaitContinuation(
            source_stage=ChargeControllerV2.STAGE_DESULFATION,
            next_stage=ChargeControllerV2.STAGE_MAIN,
            target_voltage_v=14.8,
            target_current_a=9.0,
            started_at=1000.0,
            session_id="session-recovery",
            recovery_attempt=2,
            agm_stage_idx=2,
            session_generation=500.0,
        )
        decision = decide_recovery_safe_wait(
            continuation,
            now_s=10_000.0,
            voltage_v=13.0,
            output_is_off=False,
        )
        self.assertEqual(decision.reason, "fresh_output_off_required")
        self.assertEqual(decision.action.value, "wait")

    def test_stale_recovery_continuation_fails_closed_instead_of_falling_back(self):
        controller = self._controller(ChargeControllerV2.STAGE_SAFE_WAIT)
        controller._safe_wait_next_stage = controller.STAGE_MAIN
        controller._recovery_safe_wait = RecoverySafeWaitContinuation(
            source_stage=controller.STAGE_DESULFATION,
            next_stage=controller.STAGE_MAIN,
            target_voltage_v=14.8,
            target_current_a=9.0,
            started_at=1050.0,
            session_id=controller._v2_trace_session_id,
            recovery_attempt=controller.antisulfate_count,
            agm_stage_idx=controller._agm_stage_idx,
            session_generation=controller._v2_trace_started_at - 1.0,
        )
        actions = {}
        with patch.object(controller, "_save_session"):
            decision = controller._apply_recovery_safe_wait_authority(
                now=1100.0,
                voltage=14.0,
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
        self.assertIsNone(controller._recovery_safe_wait)

    def test_desulfation_stage_and_recovery_counters_survive_restart(self):
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = os.path.join(tempdir, "charge_session.json")
            now = 20_000.0
            controller = ProductionChargeControllerV2(DummyHass(), authoritative=True)
            controller.start(controller.PROFILE_AGM, 90)
            controller.current_stage = controller.STAGE_DESULFATION
            controller.stage_start_time = now - 1800.0
            controller._stage_start_ah = 10.0
            controller.antisulfate_count = 3
            controller._agm_stage_idx = 2
            controller._v2_trace_session_id = "session-restart"
            controller._v2_trace_started_at = now - 5000.0
            with patch("charge_logic.SESSION_FILE", session_file), patch(
                "charge_controller_v2.SESSION_FILE", session_file
            ), patch("production_controller.SESSION_FILE", session_file), patch(
                "charge_logic.time.time", return_value=now
            ), patch("charge_controller_v2.time.time", return_value=now), patch(
                "production_controller.time.time", return_value=now
            ):
                controller._save_session(16.3, 0.5, 12.0)
                restored = ProductionChargeControllerV2(DummyHass(), authoritative=True)
                ok, _ = restored.try_restore_session(
                    16.3,
                    0.5,
                    12.0,
                    output_is_on=True,
                    is_cv=True,
                    is_cc=False,
                )

            self.assertTrue(ok)
            self.assertEqual(restored.current_stage, restored.STAGE_DESULFATION)
            self.assertEqual(restored.antisulfate_count, 3)
            self.assertEqual(restored._agm_stage_idx, 2)
            self.assertAlmostEqual(restored.stage_start_time, now - 1800.0)


if __name__ == "__main__":
    unittest.main()
