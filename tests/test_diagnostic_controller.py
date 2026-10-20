import types
import unittest
from unittest.mock import AsyncMock
from types import SimpleNamespace
from unittest.mock import patch

from battery_fault_engine import DiagnosticAuthority
from application.charge_stage_tick import apply_charge_stage_authority
from application.charge_session_tick import refresh_pre_tick_diagnostics
from runtime.charge.diagnostics import diagnostic_hv_veto, update_diagnostic_context
from production_controller import create_production_charge_host
from pb_domain import ChargeIntent
from production_controller import create_production_charge_host
from runtime.charge.decisions import AuthorityAction, AuthorityDecision


class DummyHass:
    pass


class DiagnosticControllerTests(unittest.TestCase):
    def _controller(self, *, profile="EFB"):
        controller = create_production_charge_host(DummyHass())
        controller.battery_type = profile
        controller.ah_capacity = 70
        controller._v2_intent = ChargeIntent.RECOVERY
        return controller

    def test_initial_sg_imbalance_does_not_veto_recovery(self):
        controller = self._controller()
        update_diagnostic_context(controller)
        self.assertEqual(controller._diagnostic_assessment.authority, DiagnosticAuthority.ALLOW)
        decision = AuthorityDecision(AuthorityAction.ENTER_DESULFATION, "fixture")
        self.assertIsNone(diagnostic_hv_veto(controller, decision))

    def test_confirmed_failed_cell_vetoes_new_recovery_hv(self):
        controller = self._controller()
        update_diagnostic_context(controller, external_failed_cell_confirmed=True)
        veto = diagnostic_hv_veto(controller,
            AuthorityDecision(AuthorityAction.ENTER_DESULFATION, "fixture")
        )
        self.assertIsNotNone(veto)
        assert veto is not None
        self.assertIn("diagnostic_hv_block", veto.reason)

    def test_production_main_dispatch_enters_mix_or_fails_closed_on_diagnostic_veto(self):
        record = SimpleNamespace(
            decision=SimpleNamespace(decision="fixture-policy"),
            analysis=SimpleNamespace(metrics=SimpleNamespace(seconds_since_current_min=9999.0)),
        )
        enter_mix = AuthorityDecision(AuthorityAction.ENTER_MIX, "fixture-main-tail")
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                controller = self._controller(profile="Ca/Ca")
                controller.start("Ca/Ca", 70)
                controller.current_stage = controller.STAGE_MAIN
                controller.stage_start_time = 100.0
                if blocked:
                    update_diagnostic_context(controller, external_failed_cell_confirmed=True)
                actions = {}
                with patch("application.charge_stage_tick.update_live_diagnostic_evidence"), patch(
                    "runtime.charge.strategy.main_authority.decide_main_transition",
                    return_value=enter_mix,
                ):
                    result = apply_charge_stage_authority(controller,
                        record=record, first_stage=None, stage_before=controller.STAGE_MAIN,
                        timestamp_s=200.0, voltage=14.4, current=0.3, temp=24.0,
                        ah=2.0, is_cv=True, is_cc=False, actions=actions,
                    )
                if blocked:
                    self.assertEqual(result.action, AuthorityAction.STOP_AND_DIAGNOSE)
                    self.assertIn("diagnostic_hv_block", result.reason)
                    self.assertEqual(controller.current_stage, controller.STAGE_DONE)
                    self.assertTrue(actions.get("turn_off"))
                    self.assertNotIn("turn_on", actions)
                    self.assertNotIn("set_voltage", actions)
                else:
                    self.assertIs(result, enter_mix)
                    self.assertEqual(controller.current_stage, controller.STAGE_MIX)
                    self.assertIn("set_voltage", actions)
                    self.assertIn("battery_diagnostics", actions)

    def test_agm_intermediate_main_step_is_not_misclassified_as_hv(self):
        controller = self._controller(profile="AGM")
        update_diagnostic_context(controller, external_failed_cell_confirmed=True)
        self.assertIsNone(
            diagnostic_hv_veto(controller,
                AuthorityDecision(AuthorityAction.ADVANCE_AGM_STEP, "fixture")
            )
        )

    def test_agm_final_tail_mix_is_hv_candidate_and_can_be_vetoed(self):
        controller = self._controller(profile="AGM")
        update_diagnostic_context(controller, external_failed_cell_confirmed=True)
        veto = diagnostic_hv_veto(controller,
            AuthorityDecision(AuthorityAction.ENTER_MIX, "fixture")
        )
        self.assertIsNotNone(veto)

    def test_normal_hv_is_also_subject_to_diagnostic_veto(self):
        controller = self._controller()
        controller._v2_intent = ChargeIntent.NORMAL
        update_diagnostic_context(controller, external_failed_cell_confirmed=True)
        veto = diagnostic_hv_veto(controller,
            AuthorityDecision(AuthorityAction.ENTER_DESULFATION, "fixture")
        )
        self.assertIsNotNone(veto)

    def test_controller_has_no_tick_override(self):
        self.assertNotIn("tick", type(self._controller()).__dict__)

    def test_application_awaits_stored_diagnostic_refresh(self):
        async def scenario():
            controller = self._controller()
            with patch("application.charge_session_tick.refresh_stored_diagnostics", new=AsyncMock()) as refresh:
                await refresh_pre_tick_diagnostics(controller)
                refresh.assert_awaited_once_with(controller)

        import asyncio

        asyncio.run(scenario())

    def test_restore_contract_propagates_through_mix_and_cooling_wrappers(self):
        controller = self._controller()
        received = []

        def production_restore(_controller, *args, **kwargs):
            received.append((args, kwargs))
            return False, None

        with patch.object(
            type(controller),
            "try_restore_session",
            production_restore,
        ):
            controller.try_restore_session(
                14.2,
                0.3,
                70.0,
                output_is_on=True,
                is_cv=True,
                is_cc=False,
            )
            controller.try_restore_session(14.2, 0.3, 70.0)

        self.assertEqual(
            received,
            [
                (
                    (14.2, 0.3, 70.0),
                    {"output_is_on": True, "is_cv": True, "is_cc": False},
                ),
                ((14.2, 0.3, 70.0), {}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
