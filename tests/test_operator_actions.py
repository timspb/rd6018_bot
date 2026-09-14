from __future__ import annotations

import unittest

from application.operator_actions import OperatorAction, OperatorActionSpec, OperatorActionsView
from operator_hmi import build_operator_keyboard


def _actions(view: OperatorActionsView) -> set[OperatorAction]:
    return {item.action for item in view.available_actions}


class OperatorActionMatrixTests(unittest.TestCase):
    def test_idle_offers_start_and_read_only_information(self):
        view = OperatorActionsView.for_state("IDLE", safety_allowed=True)
        self.assertTrue({OperatorAction.START_CHARGE, OperatorAction.SELECT_PROFILE,
                         OperatorAction.SHOW_LOG, OperatorAction.SHOW_DIAGNOSTICS} <= _actions(view))
        self.assertNotIn(OperatorAction.STOP_CHARGE, _actions(view))
        self.assertNotIn(OperatorAction.PAUSE_CHARGE, _actions(view))

    def test_charging_offers_stop_pause_and_observation(self):
        view = OperatorActionsView.for_state("CHARGING", safety_allowed=True, pause_allowed=True)
        self.assertTrue({OperatorAction.STOP_CHARGE, OperatorAction.PAUSE_CHARGE,
                         OperatorAction.SHOW_LOG, OperatorAction.SHOW_GRAPH} <= _actions(view))
        self.assertNotIn(OperatorAction.START_CHARGE, _actions(view))
        self.assertNotIn(OperatorAction.SELECT_PROFILE, _actions(view))

    def test_fault_is_fail_closed(self):
        view = OperatorActionsView.for_state("FAULT", safety_allowed=False)
        self.assertTrue({OperatorAction.SHOW_DIAGNOSTICS, OperatorAction.ACK} <= _actions(view))
        self.assertNotIn(OperatorAction.START_CHARGE, _actions(view))
        self.assertNotIn(OperatorAction.STOP_CHARGE, _actions(view))
        self.assertNotIn(OperatorAction.SELECT_PROFILE, _actions(view))

    def test_keyboard_renders_logical_actions_without_runtime_objects(self):
        view = OperatorActionsView(
            available_actions=(
                *[OperatorActionSpec(action) for action in (
                    OperatorAction.START_CHARGE,
                    OperatorAction.SHOW_LOG,
                    OperatorAction.SHOW_DIAGNOSTICS,
                )],
            )
        )
        keyboard = build_operator_keyboard(None, None, actions=view)  # type: ignore[arg-type]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        self.assertEqual(callbacks, ["charge_modes", "logs", "operator_details", "operator_refresh"])


if __name__ == "__main__":
    unittest.main()
