"""Non-executable read-only compatibility facade pending final removal.

Production starts through :mod:`bot`. Direct execution is intentionally retired.
Residual characterization imports are forwarded to the canonical production runtime
without replacing module identity or mutating `sys.modules`.
"""

from __future__ import annotations

if __name__ == "__main__":
    raise SystemExit(
        "bot_legacy.py direct execution is retired; use the canonical production entrypoint"
    )

from runtime import production_runtime as _runtime


def __getattr__(name: str):
    try:
        return getattr(_runtime, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_runtime)))


__all__: tuple[str, ...] = ()
