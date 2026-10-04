"""Historical import-compatibility facade for the retired V2 runtime name.

Production composition imports :mod:`runtime.production_runtime` directly.
This module intentionally provides read-only attribute compatibility only.
"""

from __future__ import annotations

from . import production_runtime as _runtime


def __getattr__(name: str):
    try:
        return getattr(_runtime, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_runtime)))


__all__: tuple[str, ...] = ()
