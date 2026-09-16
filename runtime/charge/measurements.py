"""Immutable measurement snapshot for pure charge evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Measurements:
    """One observation; no history and no transport ownership."""

    voltage: Optional[float] = None
    current: Optional[float] = None
    temperature: Optional[float] = None
    time: Optional[float] = None
