"""Manual bench scenario planner/executor boundary."""

from __future__ import annotations

from typing import Any

from .evidence import BenchEvidenceRecorder
from .models import BenchRunResult, BenchScenario


class BenchRunner:
    """Run only an explicitly supplied scenario; never creates a transport."""

    def __init__(self, evidence: BenchEvidenceRecorder | None = None):
        self.evidence = evidence or BenchEvidenceRecorder()

    def run(self, scenario: BenchScenario, *, executor: Any = None, preflight: dict[str, bool] | None = None) -> BenchRunResult:
        checks = preflight or {}
        missing = tuple(name for name in scenario.safety_requirements if not checks.get(name, False))
        if missing:
            record = self.evidence.add(scenario.scenario_id, scenario.operator, "preflight", "PASS", "FAIL", passed=False, notes=";".join(missing))
            return BenchRunResult(scenario, (record,), False)
        records = []
        for step in scenario.expected_steps:
            if executor is not None and step.command is not None:
                result = executor(step.command)
                passed = bool(result.get("passed", False)) if isinstance(result, dict) else bool(result)
                observed = "PASS" if passed else "FAIL"
                readback = result.get("readback") if isinstance(result, dict) else None
            else:
                passed, observed, readback = True, "PLANNED", None
            records.append(self.evidence.add(scenario.scenario_id, scenario.operator, step.name, "PASS", observed, readback=readback, passed=passed, notes="manual_gate_required" if executor is None else ""))
        return BenchRunResult(scenario, tuple(records), all(record.passed for record in records))

