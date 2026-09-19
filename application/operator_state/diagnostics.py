"""Neutral operator diagnostics view contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorDiagnosticsView:
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    stale_sources: tuple[str, ...]
    ambiguities: tuple[str, ...]
