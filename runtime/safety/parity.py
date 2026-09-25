"""Decision-only comparator for V1/V2 and V3 safety outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SafetyParityResult:
    status: str
    fields: tuple[str, ...]
    v1_v2_snapshot: Mapping[str, Any]
    v3_snapshot: Mapping[str, Any]
    reason: str = ""


class SafetyParityComparator:
    @staticmethod
    def compare(v1_v2: Mapping[str, Any], v3: Mapping[str, Any]) -> SafetyParityResult:
        fields = tuple(sorted(key for key in set(v1_v2) | set(v3) if v1_v2.get(key) != v3.get(key)))
        return SafetyParityResult(
            status="MATCH" if not fields else "MISMATCH",
            fields=fields,
            v1_v2_snapshot=dict(v1_v2),
            v3_snapshot=dict(v3),
            reason="decision_fields_equal" if not fields else "decision_fields_differ",
        )
