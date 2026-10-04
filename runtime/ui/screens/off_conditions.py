"""Canonical operator OFF-condition screen."""

from __future__ import annotations

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.screen import ScreenId, ScreenSpec


def off_conditions_button_spec() -> ButtonSpec:
    return ButtonSpec(
        button_id="off_conditions.open",
        label="⏹ Off по условию",
        action=UIAction.OPEN_OFF_CONDITIONS,
        target_screen=ScreenId.OFF_CONDITIONS.value,
    )


def _preset(button_id: str, label: str, preset: str) -> ButtonSpec:
    return ButtonSpec(
        button_id=button_id,
        label=label,
        action=UIAction.SET_OFF_PRESET,
        payload=(("preset", preset),),
    )


def build_off_conditions_screen(status_line: str = "") -> ScreenSpec:
    status = str(status_line or "").strip()
    if status:
        body = (
            "<b>⏹ Принудительное выключение активно</b>\n\n"
            f"{status}\n\n"
        )
    else:
        body = "Сейчас условие выключения не задано.\n\n"
    body += (
        "<b>Быстрые пресеты:</b> кнопки ниже.\n\n"
        "<b>Расширенный ввод в чат:</b>\n"
        "• <code>off I&lt;=1.23</code> или <code>off 1.23</code>\n"
        "• <code>off I&gt;=2</code>\n"
        "• <code>off V&gt;=16.4</code> или <code>off 16.4</code>\n"
        "• <code>off V&lt;=13.2</code>\n"
        "• <code>off 2:23</code>\n"
        "• <code>off I&gt;=2 V&lt;=13.5 2:00</code>\n"
        "• <code>off</code> — сброс\n\n"
        "Защиты не сбрасываются; температура и входное напряжение могут "
        "выключить выход раньше."
    )
    back = ButtonSpec(
        button_id="off_conditions.back_home",
        label="⬅ К панели",
        action=UIAction.OPEN_HOME,
        target_screen=ScreenId.HOME.value,
    )
    return ScreenSpec(
        screen_id=ScreenId.OFF_CONDITIONS,
        title="⏹ Off по условию",
        body=body,
        buttons=(
            (
                _preset("off_conditions.time_2h", "⏱ 2ч", "time_2h"),
                _preset("off_conditions.i_le_030", "🔋 I≤0.30A", "i_le_030"),
            ),
            (
                _preset("off_conditions.v_ge_162", "⚡ V≥16.2V", "v_ge_162"),
                _preset("off_conditions.clear", "🧹 Сброс", "clear"),
            ),
            (back,),
        ),
    )


__all__ = ["build_off_conditions_screen", "off_conditions_button_spec"]
