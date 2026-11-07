"""Button eligibility is shared by app provider and the HMI renderer."""
from types import SimpleNamespace as NS
import unittest

from application.operator_actions import OperatorAction as A
from application.operator_button_rules import actions_for_hmi, actions_for_snapshot
from operator_hmi import build_operator_keyboard, HmiAuthority, HmiProcessState


def hmi(process, authority=HmiAuthority.NONE, *, output_on=False, manual_interrupted=False):
    return NS(process_state=process, authority=authority, output_on=output_on,
              manual_interrupted=manual_interrupted)


def allowed(view):
    return tuple(item.action for item in view.available_actions)


class OneButtonPolicyTests(unittest.TestCase):
    def test_manual_interrupted_navigation_not_a_text_match(self):
        state=hmi(HmiProcessState.IDLE, manual_interrupted=True)
        actions=actions_for_hmi(state)
        self.assertEqual(allowed(actions), (A.REAUTHORIZE_MANUAL, A.DISCARD_MANUAL))
        rows=build_operator_keyboard(None,state,actions=actions).inline_keyboard
        self.assertEqual([b.callback_data for b in rows[0]],
                         ["v2_manual_reauthorize","v2_manual_discard"])

    def test_managed_running_and_pause(self):
        running=hmi(HmiProcessState.RUNNING,HmiAuthority.AUTO,output_on=True)
        self.assertIn(A.PAUSE_CHARGE,allowed(actions_for_hmi(running,paused=False)))
        self.assertIn(A.RESUME_CHARGE,allowed(actions_for_hmi(running,paused=True)))
        self.assertNotIn(A.START_CHARGE,allowed(actions_for_hmi(running)))

    def test_external_and_fault_fail_closed(self):
        on=hmi(HmiProcessState.HANDS_OFF,HmiAuthority.EXTERNAL,output_on=True)
        off=hmi(HmiProcessState.HANDS_OFF,HmiAuthority.EXTERNAL,output_on=False)
        self.assertEqual(allowed(actions_for_hmi(on)), (A.ADOPT_MIX,A.DISABLE_OUTPUT))
        self.assertEqual(allowed(actions_for_hmi(off)), (A.START_CHARGE,A.RETURN_PB_CONTROL))
        containment=hmi(HmiProcessState.CONTAINMENT,HmiAuthority.CONTAINMENT,output_on=True)
        self.assertNotIn(A.START_CHARGE,allowed(actions_for_hmi(containment)))
        interrupted=hmi(HmiProcessState.INTERRUPTED,HmiAuthority.ADOPTED_MIX)
        self.assertIn(A.ADOPT_MIX,allowed(actions_for_hmi(interrupted)))

    def test_snapshot_hands_off_reuses_external_rule(self):
        snapshot=NS(state="HANDS_OFF",snapshot=NS(output={"enabled":True},safety=NS(allowed=True)))
        self.assertEqual(allowed(actions_for_snapshot(snapshot)),
                         allowed(actions_for_hmi(hmi(HmiProcessState.HANDS_OFF,output_on=True))))
        snapshot.snapshot.output["enabled"]=False
        self.assertEqual(allowed(actions_for_snapshot(snapshot)),
                         allowed(actions_for_hmi(hmi(HmiProcessState.HANDS_OFF,output_on=False))))
