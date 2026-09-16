"""Pure renderer: snapshot in, text and declarative actions out."""

from __future__ import annotations

from dataclasses import dataclass

from application.operator_snapshot import OperatorSnapshot
from .panel_layout import PanelLayout, layout_for


@dataclass(frozen=True)
class RenderedPanel:
    text: str
    layout: PanelLayout


def render_panel(snapshot: OperatorSnapshot) -> RenderedPanel:
    layout = layout_for(snapshot)
    return RenderedPanel("\n".join(layout.rows), layout)
