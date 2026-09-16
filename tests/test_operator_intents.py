from __future__ import annotations

import unittest

from application.intents import IntentDispatcher, OperatorIntent, OperatorIntentKind
from runtime.ui.commands.models import CommandStatus


class OperatorIntentBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def intent(self, kind):
        return OperatorIntent(kind=kind, source="telegram", user="42")

    async def test_read_only_intent_routes_to_injected_handler(self):
        seen = []

        async def route(intent):
            seen.append(intent.kind)
            from runtime.ui.commands.models import CommandResult
            return CommandResult(CommandStatus.ACCEPTED, "handled")

        dispatcher = IntentDispatcher({OperatorIntentKind.SHOW_GRAPH: route})
        result = await dispatcher.dispatch(self.intent(OperatorIntentKind.SHOW_GRAPH))
        self.assertEqual(result.status, CommandStatus.ACCEPTED)
        self.assertEqual(seen, [OperatorIntentKind.SHOW_GRAPH])

    async def test_unwired_read_only_intent_is_routed_to_preserved_callback(self):
        result = await IntentDispatcher().dispatch(self.intent(OperatorIntentKind.REFRESH_PANEL))
        self.assertEqual(result.status, CommandStatus.ACCEPTED)
        self.assertEqual(result.reason, "routed_to_preserved_callback")

    async def test_execution_intent_is_rejected(self):
        result = await IntentDispatcher().dispatch(self.intent(OperatorIntentKind.START_CHARGE))
        self.assertEqual(result.status, CommandStatus.REJECTED)
        self.assertEqual(result.reason, "execution_intent_not_migrated")

    async def test_stop_requires_and_uses_stop_route(self):
        from application.stop_command import StopCommandHandler

        result = await IntentDispatcher(stop_handler=StopCommandHandler().route).dispatch(
            self.intent(OperatorIntentKind.STOP_CHARGE)
        )
        self.assertEqual(result.status, CommandStatus.ACCEPTED)
        self.assertEqual(result.reason, "routed_to_managed_stop_handler")

        rejected = await IntentDispatcher().dispatch(self.intent(OperatorIntentKind.STOP_CHARGE))
        self.assertEqual(rejected.status, CommandStatus.REJECTED)
        self.assertEqual(rejected.reason, "stop_charge_route_not_wired")

    async def test_pause_requires_and_uses_pause_route(self):
        from application.pause_command import PauseCommandHandler

        dispatcher = IntentDispatcher(
            routes={
                OperatorIntentKind.PAUSE_CHARGE: PauseCommandHandler().route,
                OperatorIntentKind.RESUME_CHARGE: PauseCommandHandler().route,
            }
        )
        paused = await dispatcher.dispatch(self.intent(OperatorIntentKind.PAUSE_CHARGE))
        resumed = await dispatcher.dispatch(self.intent(OperatorIntentKind.RESUME_CHARGE))
        self.assertEqual(paused.reason, "routed_to_preserved_pause_handler")
        self.assertEqual(resumed.reason, "routed_to_preserved_pause_handler")

    async def test_profile_selection_requires_and_uses_profile_route(self):
        from application.profile_command import ProfileCommandHandler

        dispatcher = IntentDispatcher(
            routes={OperatorIntentKind.SELECT_CHARGE_PROFILE: ProfileCommandHandler().route}
        )
        selected = await dispatcher.dispatch(
            OperatorIntent(
                OperatorIntentKind.SELECT_CHARGE_PROFILE,
                "telegram",
                "42",
                {"profile": "AGM"},
            )
        )
        invalid = await dispatcher.dispatch(
            OperatorIntent(
                OperatorIntentKind.SELECT_CHARGE_PROFILE,
                "telegram",
                "42",
                {"profile": "LiFePO4"},
            )
        )
        self.assertEqual(selected.status, CommandStatus.ACCEPTED)
        self.assertEqual(selected.reason, "routed_to_preserved_profile_handler")
        self.assertEqual(invalid.status, CommandStatus.REJECTED)
        self.assertEqual(invalid.reason, "unsupported_charge_profile")

    async def test_legacy_read_names_normalize(self):
        result = await IntentDispatcher().dispatch(self.intent(OperatorIntentKind.SHOW_JOURNAL))
        self.assertEqual(result.status, CommandStatus.ACCEPTED)
        self.assertEqual(result.intent.kind, OperatorIntentKind.SHOW_LOG.value)

    async def test_invalid_input_is_rejected(self):
        result = await IntentDispatcher().dispatch(object())
        self.assertEqual(result.status, CommandStatus.REJECTED)
        self.assertEqual(result.reason, "invalid_operator_intent")


if __name__ == "__main__":
    unittest.main()
