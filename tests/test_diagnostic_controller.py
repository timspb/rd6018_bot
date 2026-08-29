import unittest

from battery_fault_engine import DiagnosticAuthority
from diagnostic_controller import DiagnosticProductionChargeControllerV2
from first_stage_evidence import FirstStageAssessment, FirstStageState
from pb_domain import ChargeIntent


class DummyHass:
    pass


def stage_assessment(state: FirstStageState) -> FirstStageAssessment:
    return FirstStageAssessment(
        state=state,
        current_c_rate=0.01,
        tail_threshold_a=0.3,
        tail_threshold_c=0.004,
        near_target=True,
        reason=state.value,
    )


class DiagnosticControllerTests(unittest.TestCase):
    def _controller(self, *, profile="EFB"):
        controller = DiagnosticProductionChargeControllerV2(DummyHass(), authoritative=True)
        controller.battery_type = profile
        controller.ah_capacity = 70
        controller._v2_intent = ChargeIntent.RECOVERY
        return controller

    def test_initial_sg_imbalance_does_not_veto_recovery(self):
        controller = self._controller()
        # A first SG imbalance belongs to the stratification/equalization hypothesis,
        # not to confirmed cell-fault authority.
        controller.update_diagnostic_context()
        self.assertEqual(
            controller.battery_fault_assessment.authority,
            DiagnosticAuthority.ALLOW,
        )
        self.assertIsNone(
            controller._diagnostic_hv_veto(stage_assessment(FirstStageState.STUCK_PLATEAU))
        )

    def test_confirmed_failed_cell_vetoes_new_recovery_hv(self):
        controller = self._controller()
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        veto = controller._diagnostic_hv_veto(
            stage_assessment(FirstStageState.STUCK_PLATEAU)
        )
        self.assertIsNotNone(veto)
        assert veto is not None
        self.assertIn("diagnostic_hv_block", veto.reason)

    def test_agm_intermediate_main_step_is_not_misclassified_as_hv(self):
        controller = self._controller(profile="AGM")
        controller._agm_stage_idx = 0
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        self.assertIsNone(
            controller._diagnostic_hv_veto(stage_assessment(FirstStageState.TAIL_READY))
        )

    def test_agm_final_tail_is_hv_candidate_and_can_be_vetoed(self):
        controller = self._controller(profile="AGM")
        controller._agm_stage_idx = 3
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        veto = controller._diagnostic_hv_veto(
            stage_assessment(FirstStageState.TAIL_READY)
        )
        self.assertIsNotNone(veto)

    def test_normal_intent_has_no_diagnostic_hv_veto_because_no_hv_is_authorized(self):
        controller = self._controller()
        controller._v2_intent = ChargeIntent.NORMAL
        controller.update_diagnostic_context(external_failed_cell_confirmed=True)
        self.assertIsNone(
            controller._diagnostic_hv_veto(stage_assessment(FirstStageState.STUCK_PLATEAU))
        )


if __name__ == "__main__":
    unittest.main()
