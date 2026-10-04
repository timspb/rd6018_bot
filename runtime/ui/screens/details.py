"""Canonical read-only operator-details screen."""

from __future__ import annotations

from application.operator_views import OperatorDetailsView
from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.components.details import render_operator_details_body
from runtime.ui.screen import ScreenId, ScreenSpec


def operator_details_button_spec() -> ButtonSpec:
    return ButtonSpec(
        button_id="operator.details",
        label="🔎 Подробнее",
        action=UIAction.OPEN_DIAGNOSTICS,
        target_screen=ScreenId.DIAGNOSTICS.value,
    )


def build_operator_details_screen(view: OperatorDetailsView) -> ScreenSpec:
    back = ButtonSpec(
        button_id="operator.details.back_home",
        label="⬅ К панели",
        action=UIAction.OPEN_HOME,
        target_screen=ScreenId.HOME.value,
    )
    return ScreenSpec(
        screen_id=ScreenId.DIAGNOSTICS,
        title="📋 Информация для оператора",
        body=render_operator_details_body(view),
        buttons=((back,),),
    )


__all__ = ["build_operator_details_screen", "operator_details_button_spec"]
