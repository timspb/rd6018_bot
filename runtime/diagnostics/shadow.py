"""Read-only adapter from existing diagnostic assessments to V3 evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import DiagnosticAuthority, DiagnosticDecision


def _read(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class LegacyDiagnosticAdapter:
    """Convert a V1/V2 assessment object; never runs the assessment itself."""

    @staticmethod
    def to_decision(assessment: Any) -> DiagnosticDecision:
        raw_authority = _read(assessment, "authority", DiagnosticAuthority.ALLOW)
        raw_value = getattr(raw_authority, "value", raw_authority)
        try:
            authority = DiagnosticAuthority(str(raw_value))
        except ValueError:
            authority = DiagnosticAuthority.VERIFY_BEFORE_HV

        reasons = tuple(_read(assessment, "authority_reasons", ()) or ())
        classes = tuple(sorted(_read(assessment, "independent_cell_fault_classes", ()) or ()))
        return DiagnosticDecision(
            authority=authority,
            reasons=reasons + (("cell_fault_classes:" + ",".join(classes),) if classes else ()),
            hypothesis="cell_fault" if classes else None,
        )
