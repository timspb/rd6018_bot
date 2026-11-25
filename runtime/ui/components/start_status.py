"""Pure operator feedback for the transactional START use case."""

from __future__ import annotations

import html


_START_INTENT_LABELS = {
    "normal": "Обычный заряд",
    "recovery": "Восстановление",
    "conditioning": "Кондиционирование",
    "diagnostic": "Диагностика",
}


def format_start_intent_label(intent: object) -> str:
    value = str(getattr(intent, "value", intent))
    return _START_INTENT_LABELS.get(value, value)


def format_start_success(
    profile: str,
    capacity_ah: float,
    intent: object,
    battery_id: str,
    *,
    battery_voltage_v: float,
    initial_threshold_v: float,
    prep_skipped: bool,
    recipe_target_voltage_v: float | None = None,
    recipe_target_current_a: float | None = None,
) -> str:
    """Build the established HTML START reply from transaction result data."""
    if recipe_target_voltage_v is not None and recipe_target_current_a is not None:
        first_line = (
            f"\nПервый SET рецепта: {recipe_target_voltage_v:.2f} В / "
            f"{recipe_target_current_a:.2f} А."
        )
    elif prep_skipped:
        first_line = (
            f"\nPREP пропущен: Uакб={battery_voltage_v:.2f} V ≥ "
            f"{initial_threshold_v:.1f} V."
        )
    else:
        first_line = f"\nPREP: мягкий ток до Uакб ≥ {initial_threshold_v:.1f} V."
    return (
        "✅ <b>Заряд запущен</b>\n"
        f"{html.escape(profile)} {capacity_ah:g} Ah · "
        f"{html.escape(format_start_intent_label(intent))}\n"
        f"АКБ: <code>{html.escape(battery_id)}</code>{first_line}"
    )


def format_start_html_error(prefix: str, detail: str) -> str:
    """Build an HTML-safe validation error while the caller selects its cause."""
    return prefix + html.escape(detail)


def format_start_pre_enable_failure(detail: str) -> str:
    return format_start_html_error("START отменён до включения: ", detail)


def format_start_enable_failure(exception_name: str, *, off_confirmed: bool) -> str:
    suffix = (
        " Выход подтверждён OFF."
        if off_confirmed
        else (
            " 🚨 <b>Output OFF НЕ подтверждён.</b> Автовключение заблокировано; "
            "проверьте RD6018/HA и при необходимости отключите выход или питание вручную."
        )
    )
    return (
        "❌ Запуск отменён: ошибка безопасного включения "
        f"({html.escape(exception_name)}).{suffix}"
    )


def format_start_unverified_failure(reason: str | None, *, off_confirmed: bool) -> str:
    state_text = (
        "Выход подтверждён OFF."
        if off_confirmed
        else (
            "🚨 <b>Output OFF НЕ подтверждён.</b> Контроллер оставлен активным и заблокированным "
            "для контроля безопасности; проверьте RD6018/HA."
        )
    )
    detail = html.escape(reason or "RD6018 не подтвердил безопасное включение")
    return f"❌ <b>Запуск отменён.</b> {state_text}\n<code>{detail}</code>"


def format_start_persistence_failure(
    exception_name: str, *, off_confirmed: bool,
) -> str:
    off_text = (
        "Output OFF подтверждён."
        if off_confirmed
        else "🚨 Output OFF не подтверждён; проверьте RD6018 вручную."
    )
    return (
        "❌ Сохранение начального состояния рецепта не удалось "
        f"({html.escape(exception_name)}). {off_text}"
    )


__all__ = [
    "format_start_enable_failure",
    "format_start_html_error",
    "format_start_intent_label",
    "format_start_persistence_failure",
    "format_start_pre_enable_failure",
    "format_start_success",
    "format_start_unverified_failure",
]
