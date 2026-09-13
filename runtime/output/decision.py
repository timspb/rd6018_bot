"""Result of a fake/contract adapter operation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputDecision:
    accepted: bool
    reason: str
