"""Canonical charge-program selection screen."""

from __future__ import annotations

from runtime.ui.actions import UIAction
from runtime.ui.buttons import ButtonSpec
from runtime.ui.screen import ScreenId, ScreenSpec


def charge_button_spec() -> ButtonSpec:
    return ButtonSpec(
        button_id="charge.open",
        label="▶️ Новая программа",
        action=UIAction.OPEN_CHARGE,
        target_screen=ScreenId.CHARGE.value,
    )


def _profile(button_id: str, label: str, profile: str) -> ButtonSpec:
    return ButtonSpec(
        button_id=button_id,
        label=label,
        action=UIAction.SELECT_PROFILE,
        payload=(("profile", profile),),
    )


def build_charge_program_screen(*, manual_interrupted: bool = False) -> ScreenSpec:
    body = (
        "Сначала выберите химию или сохранённую физическую батарею, затем <b>intent</b>.\n\n"
        "⚡ Normal — полный штатный AUTO; Recovery/Mix включаются только по критериям V2.\n"
        "🛠 Recovery — восстановительный intent с HV только в разрешённом recipe/diagnostic envelope.\n"
        "🔄 Conditioning — сервисный режим в recipe envelope.\n"
        "🔬 Diagnostic — без автоматической HV-эскалации.\n\n"
        "В CV финиш оценивается по <b>Imin→ΔI</b>, в CC — по <b>Vmax→ΔV</b>."
    )
    rows: list[tuple[ButtonSpec, ...]] = [
        (
            _profile("charge.profile.caca", "🟦 Ca/Ca", "Ca/Ca"),
            _profile("charge.profile.efb", "🟧 EFB", "EFB"),
            _profile("charge.profile.agm", "🟥 AGM", "AGM"),
        ),
        (
            ButtonSpec(
                button_id="charge.batteries",
                label="🔋 Мои АКБ",
                action=UIAction.OPEN_BATTERIES,
                target_screen=ScreenId.BATTERIES.value,
            ),
            ButtonSpec(
                button_id="charge.battery_add",
                label="➕ АКБ",
                action=UIAction.OPEN_BATTERY_ADD,
                target_screen=ScreenId.BATTERIES.value,
            ),
        ),
        (
            ButtonSpec(
                button_id="charge.manual",
                label="🛠 Ручной MAIN → MIX",
                action=UIAction.OPEN_MANUAL,
                target_screen=ScreenId.MANUAL.value,
            ),
            ButtonSpec(
                button_id="charge.off_conditions",
                label="⏹ Off по условию",
                action=UIAction.OPEN_OFF_CONDITIONS,
                target_screen=ScreenId.OFF_CONDITIONS.value,
            ),
        ),
    ]
    if manual_interrupted:
        rows.append(
            (
                ButtonSpec(
                    button_id="charge.manual_interrupted",
                    label="↻ Прерванный Manual",
                    action=UIAction.OPEN_INTERRUPTED_MANUAL,
                    target_screen=ScreenId.MANUAL.value,
                ),
            )
        )
    rows.append(
        (
            ButtonSpec(
                button_id="charge.back_home",
                label="⬅ К панели",
                action=UIAction.OPEN_HOME,
                target_screen=ScreenId.HOME.value,
            ),
        )
    )
    return ScreenSpec(
        screen_id=ScreenId.CHARGE,
        title="🧭 V2 · программа заряда",
        body=body,
        buttons=tuple(rows),
    )


__all__ = ["build_charge_program_screen", "charge_button_spec"]
