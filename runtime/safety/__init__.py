"""Pure V3 safety package with cycle-safe lazy public exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "SafetyContext": (".engine", "SafetyContext"),
    "SafetyDecision": (".engine", "SafetyDecision"),
    "SafetyEngine": (".engine", "SafetyEngine"),
    "SafetyLimits": (".engine", "SafetyLimits"),
    "SafetyViolation": (".engine", "SafetyViolation"),
    "SafetyParityComparator": (".parity", "SafetyParityComparator"),
    "SafetyParityResult": (".parity", "SafetyParityResult"),
    "SafeOutputIntent": ("runtime.output.intent", "SafeOutputIntent"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(module_name, __name__) if module_name.startswith(".") else import_module(module_name)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
