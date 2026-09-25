import unittest

from runtime.application import RuntimeContext, RuntimeLifecycleState, RuntimeOrchestrator
from runtime.journal import InMemoryJournalRecorder
from runtime.ui.commands import CommandContext, SelectProfileCommand, UserCommandAdapter


class _Telemetry:
    def read(self):
        return {"voltage": 14.4, "current": 2.0}


class _Charge:
    def update_state(self, state, telemetry):
        return {"stage": "MAIN", "telemetry": telemetry}

    def evaluate(self, state, telemetry):
        return {"intent": {"target_voltage": 14.4, "target_current": 2.0}}


class _Diagnostics:
    def evaluate(self, telemetry, state):
        return {"authority": "allow"}


class _Safety:
    def evaluate(self, intent, telemetry, state, diagnostics):
        return {"allowed": True, "intent": intent}


class _Execution:
    def evaluate(self, intent, safety):
        return {"allowed": True, "intent": intent}


class V3RuntimeOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.journal = InMemoryJournalRecorder()
        self.orchestrator = RuntimeOrchestrator(RuntimeContext(
            _Telemetry(), _Charge(), _Diagnostics(), _Safety(), _Execution(), self.journal,
            lambda values: {"view": values["state"]["stage"]},
        ))

    def test_lifecycle_and_pipeline(self):
        self.assertEqual(self.orchestrator.lifecycle.state, RuntimeLifecycleState.CREATED)
        self.orchestrator.start()
        result = self.orchestrator.tick()
        self.assertEqual(result["snapshot"]["view"], "MAIN")
        self.assertTrue(result["execution"]["allowed"])
        self.orchestrator.stop()
        self.assertEqual(self.orchestrator.lifecycle.state, RuntimeLifecycleState.STOPPED)

    def test_telemetry_failure_is_contained(self):
        context = RuntimeContext(lambda: (_ for _ in ()).throw(RuntimeError("offline")), _Charge(), _Diagnostics(), _Safety(), _Execution(), self.journal, lambda values: values)
        orchestrator = RuntimeOrchestrator(context)
        orchestrator.start()
        result = orchestrator.tick()
        self.assertIsNone(result["telemetry"])
        self.assertTrue(self.journal.tail())

    def test_no_physical_path_is_injected(self):
        self.assertFalse(hasattr(self.orchestrator.context, "output"))
        self.assertFalse(hasattr(self.orchestrator.context, "controller"))

    def test_command_flow_ends_at_domain_intent(self):
        command = SelectProfileCommand("id", 1.0, "test", "operator", profile="agm")
        result = self.orchestrator.process_command(command, UserCommandAdapter(), context=CommandContext())
        self.assertEqual(result.intent.kind, "select_profile")
        self.assertFalse(hasattr(result.intent, "action"))


if __name__ == "__main__":
    unittest.main()
