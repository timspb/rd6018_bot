"""Data-only composition-root contract for Phase 6.0.

This describes the assembly shape; it does not construct or start the
application and is intentionally not imported by the production entrypoint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationComposition:
    """The one future composition boundary for the application graph."""

    domain: object
    application: object
    infrastructure: object
    ui: object
    persistence: object


__all__ = ["ApplicationComposition"]
