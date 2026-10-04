"""Canonical read-only service-details screen."""

from __future__ import annotations

from application.operator_views import ServiceDetailsView
from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.components.service import render_service_details_body
from runtime.ui.screen import ScreenId, ScreenSpec


def build_service_details_screen(view: ServiceDetailsView) -> ScreenSpec:
    back = ButtonSpec(
        button_id="service.back_home",
        label="⬅ К панели",
        action=UIAction.OPEN_HOME,
        target_screen=ScreenId.HOME.value,
    )
    return ScreenSpec(
        screen_id=ScreenId.SERVICE,
        title="🛠 Сервисная информация",
        body=render_service_details_body(view),
        buttons=((back,),),
    )


__all__ = ["build_service_details_screen"]
