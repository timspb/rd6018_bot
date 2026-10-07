import unittest
from types import SimpleNamespace

from runtime.replay import (
    ReplayComparator,
    ReplayRunner,
    ReplayScenario,
    ReplayTelemetryProvider,
    load_replay_jsonl,
)


class _Journal:
    def __init__(self):
        self.events = []

    def append(self, event):
        self.events.append(event)

    def tail(self, count=1):
        return tuple(self.events[-count:])


class _ReplayOrchestrator:
    """Minimal injected orchestrator contract for ReplayRunner tests."""

    def __init__(self, records):
        self.context = SimpleNamespace(
            telemetry_provider=ReplayTelemetryProvider(records),
            journal_recorder=_Journal(),
        )

    def start(self):
        return None

    def tick(self):
        telemetry = self.context.telemetry_provider()
        state = {"stage": "MAIN", "phase": "CV"}
        charge = {"intent": {"stage": "MAIN"}}
        safety = {"allowed": True}
        execution = {"allowed": True}
        self.context.journal_recorder.append({"stage": "MAIN"})
        return {
            "telemetry": telemetry,
            "state": state,
            "charge": charge,
            "safety": safety,
            "execution": execution,
        }


class V3ReplayTests(unittest.TestCase):
    def _orchestrator(self, records):
        return _ReplayOrchestrator(records)

    def test_loader_and_deterministic_trace(self):
        records = load_replay_jsonl(
            '{"timestamp": 1, "voltage": 14.4}\n'
            '{"timestamp": 2, "voltage": 14.5}'
        )
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
        self.assertEqual(
            ReplayComparator.compare({}, {"stage": "MAIN"}).status,
            "INCONCLUSIVE",
        )
        with self.assertRaises(ValueError):
            ReplayScenario("", None, None, ())


if __name__ == "__main__":
    unittest.main()
