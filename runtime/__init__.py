"""Isolated V3 runtime boundaries.

Package import must stay side-effect free: importing one leaf module must not
compose RuntimeApp or pull the historical controller graph into memory.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORTS = {
    "RuntimeApp": (".app", "RuntimeApp"),
    "RuntimeDependencies": (".dependencies", "RuntimeDependencies"),
    "LifecycleManager": (".lifecycle", "LifecycleManager"),
    "LifecycleState": (".lifecycle", "LifecycleState"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, symbol = target
    value = getattr(import_module(module_name, __name__), symbol)
    globals()[name] = value
    return value
