from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PhysicalVerificationEvidence:
    before_snapshot: Any
    requested_state: Any
    write_result: Any
    pre_readback: Any
    pre_comparison: Any
    action: str
    post_readback: Any
    post_comparison: Any
    final_result: str
