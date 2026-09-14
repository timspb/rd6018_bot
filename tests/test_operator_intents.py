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
        result = await IntentDispatcher().dispatch(self.intent(OperatorIntentKind.STOP_CHARGE))
        self.assertEqual(result.status, CommandStatus.REJECTED)
        self.assertEqual(result.reason, "execution_intent_not_migrated")

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
