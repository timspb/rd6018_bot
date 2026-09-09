import types
import unittest
from unittest.mock import patch

from battery_fault_engine import DiagnosticAuthority
from diagnostic_controller import DiagnosticProductionChargeControllerV2
from pb_domain import ChargeIntent
from production_controller import ProductionChargeControllerV2
from production_guardrails_v2 import install_production_guardrails
from v2_authority import AuthorityAction, AuthorityDecision


class DummyHass:
    pass


class DiagnosticControllerTests(unittest.TestCase):
    def _controller(self, *, profile="EFB"):
        controller = DiagnosticProductionChargeControllerV2(DummyHass(), authoritative=True)
        controller.battery_type = profile
        controller.ah_capacity = 70
        controller._v2_intent = ChargeIntent.RECOVERY
        return controller

    def test_initial_sg_imbalance_does_not_veto_recovery(self):
        controller = self._controller()
        controller.update_diagnostic_context()
        self.assertEqual(controller.battery_fault_assessment.authority, DiagnosticAuthority.ALLOW)
        decision = AuthorityDecision(AuthorityAction.ENTER_DESULFATION, "fixture")
        self.assertIsNone(controller._diagnostic_hv_veto(decision))

    def test_confirmed_failed_cell_vetoes_new_recovery_hv(self):
        controller = self._controller()
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        veto = controller._diagnostic_hv_veto(
            AuthorityDecision(AuthorityAction.ENTER_DESULFATION, "fixture")
        )
        self.assertIsNotNone(veto)
        assert veto is not None
        self.assertIn("diagnostic_hv_block", veto.reason)

    def test_agm_intermediate_main_step_is_not_misclassified_as_hv(self):
        controller = self._controller(profile="AGM")
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        self.assertIsNone(
            controller._diagnostic_hv_veto(
                AuthorityDecision(AuthorityAction.ADVANCE_AGM_STEP, "fixture")
            )
        )

    def test_agm_final_tail_mix_is_hv_candidate_and_can_be_vetoed(self):
        controller = self._controller(profile="AGM")
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        veto = controller._diagnostic_hv_veto(
            AuthorityDecision(AuthorityAction.ENTER_MIX, "fixture")
        )
        self.assertIsNotNone(veto)

    def test_normal_hv_is_also_subject_to_diagnostic_veto(self):
        controller = self._controller()
        controller._v2_intent = ChargeIntent.NORMAL
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        veto = controller._diagnostic_hv_veto(
            AuthorityDecision(AuthorityAction.ENTER_DESULFATION, "fixture")
        )
        self.assertIsNotNone(veto)

    def test_restore_contract_propagates_through_mix_and_cooling_wrappers(self):
        controller = self._controller()
        received = []

        def production_restore(_controller, *args, **kwargs):
            received.append((args, kwargs))
            return False, None

        app = types.SimpleNamespace(
            charge_controller=controller,
            MIN_INPUT_VOLTAGE=60.0,
        )
        with patch.object(
            ProductionChargeControllerV2,
            "try_restore_session",
            production_restore,
        ):
            install_production_guardrails(app)
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
