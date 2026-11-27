"""P7 D061 HMI composition stays app-aware without global builder patches."""
import types
import unittest
from unittest.mock import patch

import operator_hmi
import rd_managed_adoption
from application.operator_actions import OperatorActionsView
from runtime.ui.components.hmi_state import OperatorHmiState, HmiAuthority, HmiProcessState, project_managed_live_adoption_state
from runtime.ui.components.hmi_action_keyboard import _managed_adoption_keyboard, _keyboard_from_actions
from application.operator_button_rules import actions_for_hmi


class FakeRouter:
    def __init__(self):
        self.routes = []

    def callback_query(self, _filter):
        def register(fn):
            self.routes.append(fn)
            return fn
        return register


class FakeCoordinator:
    def __init__(self, app, manager):
        self.app = app
        self.active = False
        self.off_pending = False


class ReassemblyHmiTests(unittest.TestCase):
    def _app(self):
        return types.SimpleNamespace(
            router=FakeRouter(),
            rd_control_mode_manager=types.SimpleNamespace(hands_off=True),
            manual_session_manager=types.SimpleNamespace(
                is_active=False, state="active", active_elapsed_s=0,
                request=types.SimpleNamespace(operation_mode_label="MANUAL"),
            ),
        )

    @staticmethod
    def _state(process_state, authority, output_on=True):
        return OperatorHmiState(
            process_state=process_state, authority=authority,
            title="original", output_on=output_on, regulator="",
            battery_label="", battery_voltage_v=None, current_a=None,
            power_w=None, battery_temp_c=None, psu_temp_c=None,
            target_voltage_v=None, current_limit_a=None,
            progress="original", safety="",
        )

    @staticmethod
    def _callbacks(markup):
        return [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        ]

    @staticmethod
    def _ui_keyboard(app, state):
        # Test the explicit D061 HMI owner: other production installers may
        # wrap the global operator_hmi builder during pytest collection.
        return _managed_adoption_keyboard(app, state, _keyboard_from_actions(actions_for_hmi(state)))

    def test_two_apps_project_their_own_d061_state_and_keyboard(self):
        with patch.object(rd_managed_adoption, "ManagedLiveAdoptionCoordinator", FakeCoordinator):
            first, second = self._app(), self._app()
            first_coordinator = rd_managed_adoption.install_managed_live_adoption(first, object())
            second_coordinator = rd_managed_adoption.install_managed_live_adoption(second, object())

            self.assertEqual(len(first.router.routes), 5)
            self.assertEqual(len(second.router.routes), 5)
            self.assertIs(rd_managed_adoption.install_managed_live_adoption(second, object()), second_coordinator)
            self.assertEqual(len(second.router.routes), 5)

            # Feed the existing action selector an already-built HANDS_OFF
            # projection with Output ON, as the app-aware keyboard caller does.
            hands_off = self._state(HmiProcessState.HANDS_OFF, HmiAuthority.EXTERNAL)
            keyboard = self._ui_keyboard(first, hands_off)
            self.assertEqual(
                [(button.text, button.callback_data) for button in keyboard.inline_keyboard[1]],
                [("🔒 Забрать под Pb-контроль", "rd_managed_adopt")],
            )
            self.assertEqual(
                self._callbacks(keyboard),
                ["rd_live_mix", "rd_managed_adopt", "rd_hands_off_output_off", "operator_refresh"],
            )

            first_coordinator.off_pending = True
            self.assertNotIn("rd_managed_adopt", self._callbacks(self._ui_keyboard(first, hands_off)))
            first_coordinator.off_pending = False
            first_coordinator.active = True
            self.assertNotIn("rd_managed_adopt", self._callbacks(self._ui_keyboard(first, hands_off)))
            self.assertIn("rd_managed_adopt", self._callbacks(self._ui_keyboard(second, hands_off)))

            # Supplying actions keeps the pre-existing bypass semantics.
            supplied = operator_hmi.build_operator_keyboard(first, hands_off, actions=OperatorActionsView())
            self.assertNotIn("rd_managed_adopt", self._callbacks(supplied))

    def test_active_manual_state_projection_is_per_app(self):
        with patch.object(rd_managed_adoption, "ManagedLiveAdoptionCoordinator", FakeCoordinator):
            first, second = self._app(), self._app()
            first.rd_control_mode_manager.hands_off = False
            second.rd_control_mode_manager.hands_off = False
            first.manual_session_manager.is_active = True
            second.manual_session_manager.is_active = True
            first_coordinator = rd_managed_adoption.install_managed_live_adoption(first, object())
            second_coordinator = rd_managed_adoption.install_managed_live_adoption(second, object())

            first_coordinator.active = True
            manual = self._state(HmiProcessState.RUNNING, HmiAuthority.MANUAL)
            # Exercise the installed HMI composition, not the transport
            # freshness gate (covered independently by telemetry tests).
            first_state = project_managed_live_adoption_state(first, manual)
            second_state = project_managed_live_adoption_state(second, manual)
            self.assertEqual(first_state.title, "RD6018 · MANUAL ПОДХВАЧЕН")
            self.assertEqual(first_state.progress, "Live adoption · исходные уставки — максимум, authority только вниз")
            self.assertNotEqual(second_state.title, "RD6018 · MANUAL ПОДХВАЧЕН")

            second_coordinator.active = True
            self.assertEqual(
                project_managed_live_adoption_state(second, manual).title,
                "RD6018 · MANUAL ПОДХВАЧЕН",
            )

    def test_no_global_hmi_builder_patch_or_process_flag(self):
        import inspect

        source = inspect.getsource(rd_managed_adoption.install_managed_live_adoption)
        self.assertNotIn("operator_hmi.build_operator_keyboard =", source)
        self.assertNotIn("operator_hmi.build_operator_hmi_state =", source)
        self.assertNotIn("_rd_managed_adoption_keyboard_wrapped", source)
        self.assertFalse(hasattr(operator_hmi, "_rd_managed_adoption_keyboard_wrapped"))


if __name__ == "__main__":
    unittest.main()
