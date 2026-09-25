from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class VerificationResult:
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PreActionVerificationResult:
    requested_state: Any
    observed_state: Any
    differences: tuple[str, ...]
    timestamp: float
    transport: str
    result: str


@dataclass(frozen=True)
class PostActionVerificationResult:
    action: str
    expected_state: Any
    observed_state: Any
    differences: tuple[str, ...]
    timestamp: float
    result: str
