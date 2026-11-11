"""Manual and unmanaged HMI projections have no charger authority."""
import unittest
from types import SimpleNamespace as NS
from runtime.ui.components.hmi_manual_states import manual_hmi_state
from runtime.ui.components.hmi_unmanaged_states import unmanaged_hmi_state
from runtime.ui.components.hmi_state import HmiAuthority, HmiProcessState

COMMON=dict(
    output_on=False, regulator="CV", battery_v=12.7,
    current=0.0, power=0.0, temp_ext=24.0, temp_int=30.0,
    set_v=14.7, set_i=7.2, safety="ok", attention="normal",
)

class ManualAndUnmanagedProjectionTests(unittest.TestCase):
    def test_manual_none_defers_to_other_owner(self):
        self.assertIsNone(manual_hmi_state(NS(manual_session_manager=None), {},
                                           **COMMON, now_s=lambda:100.))

    def test_interrupted_manual_has_no_start_authority(self):
        manual=NS(is_active=False, state=NS(value="interrupted"), battery_id="Test")
        state=manual_hmi_state(NS(manual_session_manager=manual), {},
                               **COMMON, now_s=lambda:100.)
        self.assertIs(state.process_state,HmiProcessState.IDLE)
        self.assertIs(state.authority,HmiAuthority.NONE)
        self.assertTrue(state.manual_interrupted)
        self.assertEqual(state.attention,"warning")
        self.assertFalse(manual.is_active)

    def test_hands_off_is_distinct_from_unknown_output(self):
        for output in (False,True):
            data=dict(COMMON,output_on=output)
            state=unmanaged_hmi_state(hands_off=True,**data)
            self.assertIs(state.process_state,HmiProcessState.HANDS_OFF)
            self.assertIs(state.authority,HmiAuthority.EXTERNAL)
            self.assertIs(state.output_on,output)

    def test_unowned_output_on_is_containment(self):
        state=unmanaged_hmi_state(hands_off=False,**dict(COMMON,output_on=True))
        self.assertIs(state.process_state,HmiProcessState.CONTAINMENT)
        self.assertIs(state.authority,HmiAuthority.CONTAINMENT)
        self.assertEqual(state.attention,"alarm")

    def test_no_owner_output_off_is_idle(self):
        state=unmanaged_hmi_state(hands_off=False,**COMMON)
        self.assertIs(state.process_state,HmiProcessState.IDLE)
        self.assertIs(state.authority,HmiAuthority.NONE)
        self.assertFalse(state.manual_interrupted)
