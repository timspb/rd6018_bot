import unittest

from runtime.application import RuntimeContext, RuntimeOrchestrator
from runtime.journal import InMemoryJournalRecorder
from runtime.replay import (
    ReplayComparator, ReplayRunner, ReplayScenario, ReplayTelemetryProvider,
    TelemetryReplayRecord, load_replay_jsonl,
)


class _Service:
    def update_state(self, state, telemetry):
        return {"stage": "MAIN", "phase": "CV"}

    def evaluate(self, state, telemetry):
        return {"intent": {"stage": state["stage"]}}


class _Diagnostics:
    def evaluate(self, telemetry, state): return {"authority": "allow"}


class _Safety:
    def evaluate(self, intent, telemetry, state, diagnostics): return {"allowed": True}


class _Execution:
    def evaluate(self, intent, safety): return {"allowed": True}


class V3ReplayTests(unittest.TestCase):
    def _orchestrator(self, records):
        journal = InMemoryJournalRecorder()
        return RuntimeOrchestrator(RuntimeContext(
            ReplayTelemetryProvider(records), _Service(), _Diagnostics(), _Safety(), _Execution(), journal,
            lambda values: values,
        ))

    def test_loader_and_deterministic_trace(self):
        records = load_replay_jsonl('{"timestamp": 1, "voltage": 14.4}\n{"timestamp": 2, "voltage": 14.5}')
        scenario = ReplayScenario("main", None, None, records)
        first = ReplayRunner(self._orchestrator(records))
        first.orchestrator.start()
        second = ReplayRunner(self._orchestrator(records))
        second.orchestrator.start()
        trace_a = first.run(scenario)
        trace_b = second.run(scenario)
        self.assertEqual(trace_a, trace_b)
        self.assertEqual(trace_a[0].stage, "MAIN")

    def test_comparison_and_invalid_scenario(self):
        result = ReplayComparator.compare({"stage": "MAIN"}, {"stage": "MIX"})
        self.assertEqual(result.status, "MISMATCH")
        self.assertEqual(ReplayComparator.compare({}, {"stage": "MAIN"}).status, "INCONCLUSIVE")
        with self.assertRaises(ValueError):
            ReplayScenario("", None, None, ())


if __name__ == "__main__":
    unittest.main()
