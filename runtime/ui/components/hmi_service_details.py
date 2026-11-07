"""Read-only technical service details (live and immutable DTO)."""
from __future__ import annotations
import html
from typing import Any, Mapping
from application.operator_views import ServiceDetailsView
from .hmi_state import OperatorHmiState
from .hmi_values import _finite, _value

def render_operator_service_details(app: Any, state: OperatorHmiState, live: Mapping[str, Any]) -> str:
    """Technical read-only details kept outside the operator screen."""
    lines = ["<b>🛠 Сервисная информация</b>", ""]
    lines.append(f"Authority: <code>{html.escape(state.authority.value)}</code>")
    lines.append(f"Output: <code>{'ON' if state.output_on else 'OFF'}</code>")
    lines.append(f"Режим: <code>{html.escape(state.regulator or '—')}</code>")
    controller = getattr(app, "charge_controller", None)
    if controller is not None:
        try:
            snapshot = controller.ui_support_snapshot()
        except Exception:
            snapshot = {}
        lines.append(f"Этап: <code>{html.escape(str(getattr(controller, 'current_stage', '—')))}</code>")
        lines.append(f"V2 analysis: <code>{'available' if snapshot.get('runtime_analysis_available') else 'unavailable'}</code>")
        lines.append(f"Decision: <code>{html.escape(str(snapshot.get('decision') or '—'))}</code>")
    ovp = _finite(live.get("ovp"))
    ocp = _finite(live.get("ocp"))
    protection = html.escape(str(live.get("protection_code") or "—"))
    regulation = html.escape(str(live.get("regulation_code") or "—"))
    lines.extend(
        [
            f"OVP/OCP: <code>{_value(ovp, 2, 'V')} / {_value(ocp, 2, 'A')}</code>",
            f"Protection/Regulation: <code>{protection} / {regulation}</code>",
            f"Heartbeat: <code>{html.escape(str(live.get('last_reported') or live.get('last_updated') or '—'))}</code>",
            "Lease/Modbus details доступны в диагностическом экране.",
        ]
    )
    return "\n".join(lines)


def render_operator_service_details_view(view: ServiceDetailsView) -> str:
    lines = ["<b>🛠 Сервисная информация</b>", ""]
    lines.extend([
        f"Authority: <code>{html.escape(view.authority)}</code>",
        f"Output: <code>{'ON' if view.output_on else 'OFF'}</code>",
        f"Режим: <code>{html.escape(view.regulator or '—')}</code>",
        f"Этап: <code>{html.escape(view.stage)}</code>",
        f"V2 analysis: <code>{view.v2_analysis}</code>",
        f"Decision: <code>{html.escape(view.decision)}</code>",
        f"OVP/OCP: <code>{_value(view.ovp_v, 2, 'V')} / {_value(view.ocp_a, 2, 'A')}</code>",
        f"Protection/Regulation: <code>{html.escape(view.protection)} / {html.escape(view.regulation)}</code>",
        f"Heartbeat: <code>{html.escape(view.heartbeat)}</code>",
        "Lease/Modbus details доступны в диагностическом экране.",
    ])
    return "\n".join(lines)
