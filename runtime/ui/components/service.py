"""Framework-neutral formatter for operator service details."""

from __future__ import annotations

import html
from typing import Optional

from application.operator_views import ServiceDetailsView


def _value(value: Optional[float], digits: int, suffix: str) -> str:
    return "—" if value is None else f"{value:.{digits}f} {suffix}"


def render_service_details_body(view: ServiceDetailsView) -> str:
    return "\n".join(
        [
            f"Authority: <code>{html.escape(view.authority)}</code>",
            f"Output: <code>{'ON' if view.output_on else 'OFF'}</code>",
            f"Режим: <code>{html.escape(view.regulator or '—')}</code>",
            f"Этап: <code>{html.escape(view.stage)}</code>",
            f"V2 analysis: <code>{html.escape(view.v2_analysis)}</code>",
            f"Decision: <code>{html.escape(view.decision)}</code>",
            f"OVP/OCP: <code>{_value(view.ovp_v, 2, 'V')} / {_value(view.ocp_a, 2, 'A')}</code>",
            f"Protection/Regulation: <code>{html.escape(view.protection)} / {html.escape(view.regulation)}</code>",
            f"Heartbeat: <code>{html.escape(view.heartbeat)}</code>",
            "Lease/Modbus details доступны в диагностическом экране.",
        ]
    )


__all__ = ["render_service_details_body"]
