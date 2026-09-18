"""Test-only parity oracle for execution-policy requirements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from runtime.output.intent import OutputAction, SafeOutputIntent


@dataclass(frozen=True)
class ExecutionParityResult:
    status: str
    fields: tuple[str, ...]
    v2_requirements: Mapping[str, Any]
    v3_requirements: Mapping[str, Any]
    reason: str = ""


def legacy_requirements(intent: SafeOutputIntent) -> dict[str, Any]:
    requirements = {"action": intent.action.value}
    if intent.action is OutputAction.ENABLE:
        requirements.update({"telemetry_fresh": True, "programming_readback": True, "authority": True})
    elif intent.action in {OutputAction.SET_VOLTAGE, OutputAction.SET_CURRENT}:
        requirements.update({"telemetry_fresh": True, "recipe_limits": True, "authority": True})
    elif intent.action is OutputAction.RESET_PROTECTION:
        requirements.update({"reason": bool(intent.source), "source_phase": bool(intent.source)})
    else:
        requirements["fail_closed"] = True
    return requirements


def compare_requirements(v2_requirements: Mapping[str, Any], v3_requirements: Mapping[str, Any]) -> ExecutionParityResult:
    fields = tuple(sorted(key for key in set(v2_requirements) | set(v3_requirements) if v2_requirements.get(key) != v3_requirements.get(key)))
    return ExecutionParityResult(
        "MATCH" if not fields else "MISMATCH",
        fields,
        dict(v2_requirements),
        dict(v3_requirements),
        "requirements_equal" if not fields else "requirements_differ",
    )
