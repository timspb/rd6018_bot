"""Application use case for applying an operator pause or resume."""

from __future__ import annotations

import asyncio
from typing import Any

from rd6018_telemetry import as_bool


async def toggle_operator_pause(host: Any) -> str:
    """Serialize the complete pause/resume transaction on the app owner lock."""
    port = host._runtime_execution_port()
    lock = getattr(port, "_guard_owner_lock", None)
    if lock is None:
        raise RuntimeError("Operator Pause requires the canonical execution owner lock")
    async with lock:
        return await _toggle_operator_pause_locked(host, port)


async def _toggle_operator_pause_locked(host: Any, port: Any) -> str:
    """Apply pause/resume while the shared app execution lock is held."""
    try:
        live = await port.read_live()
    except asyncio.CancelledError:
        raise
    output_off = _is_output_off(live)

    if not host._operator_pause_active():
        if not host.charge_controller.is_active:
            return "Активной сессии заряда нет"
        off_requested = not output_off
        if off_requested:
            try:
                off = await port.request_verified_off()
            except asyncio.CancelledError:
                after = await _shield_emergency_off_readback(port)
                if _is_output_off(after):
                    try:
                        _commit_pause(host, after)
                    except Exception:
                        pass
                raise
        try:
            after = await port.read_live()
        except asyncio.CancelledError:
            if off_requested:
                after = await _shield_emergency_off_readback(port)
                if _is_output_off(after):
                    try:
                        _commit_pause(host, after)
                    except Exception:
                        pass
            raise
        if not _is_output_off(after):
            return "Пауза не включена: Output не подтверждён OFF"
        if not _commit_pause(host, after):
            return "Пауза не включена: состояние не сохранено"
        return "Пауза включена · Output OFF подтверждён"

    if not output_off:
        try:
            off = await port.request_verified_off()
        except asyncio.CancelledError:
            await _shield_emergency_off_readback(port)
            raise
        try:
            after = await port.read_live()
        except asyncio.CancelledError:
            await _shield_emergency_off_readback(port)
            raise
        if not _is_output_off(after):
            return "Продолжение заблокировано: Output не подтверждён OFF"
        live = after
        output_off = True

    temp_ext = host._safe_float(live.get("temp_ext"))
    input_voltage = host._safe_float(live.get("input_voltage"), 0.0)
    if temp_ext < host.MIN_START_TEMP:
        return f"Продолжение заблокировано: температура АКБ {temp_ext:.1f}°C"
    if input_voltage < host.MIN_INPUT_VOLTAGE:
        return f"Продолжение заблокировано: вход БП {input_voltage:.0f}V"

    if not host.charge_controller.is_active:
        if not host.paused_done_resume_is_authorized(
            host,
            host.charge_controller,
        ):
            return (
                "Продолжение заблокировано: сохранённый Done не имеет "
                "подтверждённого Storage Output ON intent"
            )
        ok, _ = host.charge_controller.try_restore_session(
            host._safe_float(live.get("battery_voltage")),
            host._safe_float(live.get("current")),
            host._safe_float(live.get("ah")),
            output_is_on=not output_off,
            is_cv=host._canonical_bool(live, "is_cv"),
            is_cc=host._canonical_bool(live, "is_cc"),
        )
        if not ok:
            return "Продолжение заблокировано: сессия не восстановлена"

    pause_seconds = max(
        0.0, host.time.time() - float(host._operator_pause_state.started_at or host.time.time())
    )
    stage = host.charge_controller.current_stage
    if stage == host.charge_controller.STAGE_SAFE_WAIT:
        try:
            cleared = host._clear_operator_pause()
            if cleared is False:
                raise OSError("operator pause state clear failed")
        except OSError:
            return "Продолжение заблокировано: пауза не удалена"
        host.charge_controller.shift_active_clocks(pause_seconds)
        return "Пауза снята · ожидание продолжает контролироваться"

    uv, ui = host.charge_controller._get_target_v_i(temp_ext)
    try:
        voltage_ok = await port.program_voltage(uv)
        current_ok = await port.program_current(host._cap_current(ui))
    except asyncio.CancelledError:
        raise
    if voltage_ok is not True or current_ok is not True:
        return "Продолжение заблокировано: уставки напряжения/тока не применены"
    try:
        enabled = await port.request_verified_on()
    except asyncio.CancelledError:
        await _shield_emergency_off_readback(port)
        raise
    if not enabled:
        return "Продолжение заблокировано: безопасное включение не подтверждено"

    try:
        cleared = host._clear_operator_pause()
        if cleared is False:
            raise OSError("operator pause state clear failed")
    except OSError:
        await _shield_emergency_off_readback(port)
        return "Продолжение заблокировано: пауза не удалена"
    host.charge_controller.shift_active_clocks(pause_seconds)
    host.log_event(
        host.charge_controller.current_stage,
        host._safe_float(live.get("battery_voltage")),
        host._safe_float(live.get("current")),
        temp_ext,
        host._safe_float(live.get("ah")),
        "OPERATOR_PAUSE_OFF",
    )
    return "Пауза снята · заряд продолжен"


async def _shield_emergency_off_readback(port: Any) -> dict[str, Any] | None:
    """Finish preemptive OFF and a fresh readback despite caller cancellation."""
    async def contain() -> dict[str, Any] | None:
        try:
            await port.request_emergency_off()
        except Exception:
            pass
        try:
            return await port.read_live()
        except Exception:
            return None

    cleanup = asyncio.create_task(contain())
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            continue
    try:
        return cleanup.result()
    except Exception:
        return None


def _is_output_off(live: dict[str, Any] | None) -> bool:
    return live is not None and as_bool(live.get("switch")) is False


def _commit_pause(host: Any, live: dict[str, Any]) -> bool:
    """Synchronously save the existing session and durable pause timestamp."""
    host.charge_controller._save_session(
        host._safe_float(live.get("battery_voltage")),
        host._safe_float(live.get("current")),
        host._safe_float(live.get("ah")),
    )
    prior_pause = host._operator_pause_state.started_at
    host._operator_pause_state.started_at = host.time.time()
    try:
        saved = host._save_operator_pause_state()
        if saved is False:
            raise OSError("operator pause state save failed")
    except OSError:
        host._operator_pause_state.started_at = prior_pause
        return False
    host.log_event(
        host.charge_controller.current_stage,
        host._safe_float(live.get("battery_voltage")),
        host._safe_float(live.get("current")),
        host._safe_float(live.get("temp_ext")),
        host._safe_float(live.get("ah")),
        "OPERATOR_PAUSE_ON",
    )
    return True
