"""Read-only charge-screen completeness checks."""

from __future__ import annotations

from .models import ChargeView


REQUIRED_SCREEN_FIELDS = ("stage", "program", "targets", "active_limits", "waiting_for", "conditions")


def missing_charge_screen_fields(view: ChargeView) -> tuple[str, ...]:
    missing = []
    for field in REQUIRED_SCREEN_FIELDS:
        value = getattr(view, field)
        if field in {"stage", "program"} and not str(value).strip():
            missing.append(field)
        elif field in {"targets", "active_limits", "conditions"} and not value:
            missing.append(field)
        elif field == "waiting_for" and not value:
            missing.append(field)
    return tuple(missing)
