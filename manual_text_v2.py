from __future__ import annotations

import html
import math
from pathlib import Path
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

import v2_sg_ui
from charge_logic import MAX_STAGE_CURRENT
from config import MAX_MANUAL_VOLTAGE
from manual_mode import ManualChargeRequest, ManualStopConditions
from manual_runtime_v2 import ProductionManualSessionManager
from runtime.charge.profiles.manual import ManualChargeProfile, ManualStageProfile, load_manual_profile, save_manual_profile

MANUAL_PROFILE_PATH = Path(__file__).resolve().parent / "config" / "charge" / "manual.yaml"


@dataclass(frozen=True)
class ParsedManualCommand:
    request: ManualChargeRequest
    reach_voltage_v: Optional[float] = None
    reach_current_a: Optional[float] = None


def _float(text: str) -> float:
    value = float(str(text).strip().replace(",", "."))
    if not math.isfinite(value):
        raise ValueError("значение должно быть конечным числом")
    return value


def _duration_seconds(text: str) -> float:
    raw = str(text).strip()
    parts = raw.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("таймер задаётся как H:MM или H:MM:SS")
    try:
        numbers = [int(part) for part in parts]
    except ValueError as exc:
        raise ValueError("таймер задаётся как H:MM или H:MM:SS") from exc
    if any(number < 0 for number in numbers):
        raise ValueError("таймер не может быть отрицательным")
    if len(numbers) == 2:
        hours, minutes = numbers
        seconds = 0
    else:
        hours, minutes, seconds = numbers
    if minutes >= 60 or seconds >= 60:
        raise ValueError("минуты и секунды таймера должны быть < 60")
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise ValueError("таймер должен быть больше нуля")
    return float(total)


def _profile_number(value: str, *, duration: bool = False) -> float:
    return _duration_seconds(value) if duration and ":" in value else _float(value.rstrip("АAaAvV"))


def _parse_profile_stage(line: str, *, main: bool, base: ManualStageProfile) -> ManualStageProfile:
    body = line.split(":", 1)[1] if ":" in line else line.split(None, 1)[1]
    values: dict[str, str] = {}
    for token in body.replace(",", ".").split():
        if "=" not in token:
            raise ValueError("поля режима задаются как ключ=значение")
        key, value = token.split("=", 1)
        values[key.strip().lower()] = value.strip()

    def take(*names: str, duration: bool = False) -> float:
        for name in names:
            if name in values:
                return _profile_number(values[name], duration=duration)
        raise ValueError(f"не заполнено поле {names[0]}")

    common = {
        "voltage_v": take("u", "v", "voltage", "voltage_v"),
        "current_a": take("i", "current", "current_a"),
        "hold_seconds": take("hold", "hold_s", "hold_seconds", duration=True),
    }
    if main:
        return replace(base, **common, minimum_current_a=take("imin", "minimum", "minimum_current_a"))
    return replace(
        base,
        **common,
        delta_voltage_v=take("dv", "deltav", "delta_voltage_v"),
        delta_current_a=take("di", "deltai", "delta_current_a"),
    )


def parse_manual_profile_input(text: str) -> ManualChargeProfile:
    """Parse the two-line operator form and return a validated profile."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if len(lines) != 2 or not lines[0].lower().startswith("main") or not lines[1].lower().startswith("mix"):
        raise ValueError("нужны две строки: MAIN ... и MIX ...")
    base = load_manual_profile(MANUAL_PROFILE_PATH)
    main = _parse_profile_stage(lines[0], main=True, base=base.main)
    mix = _parse_profile_stage(lines[1], main=False, base=base.mix)
    return ManualChargeProfile(main=main, mix=mix, profile_id=base.profile_id)


def _validate_stop_voltage(value: float) -> float:
    if value < 0 or value > float(MAX_MANUAL_VOLTAGE):
        raise ValueError(f"порог напряжения должен быть 0..{MAX_MANUAL_VOLTAGE:.1f} V")
    return value


def _validate_stop_current(value: float) -> float:
    if value < 0 or value > float(MAX_STAGE_CURRENT):
        raise ValueError(f"порог тока должен быть 0..{MAX_STAGE_CURRENT:.1f} A")
    return value


def parse_manual_command(text: str) -> Optional[ParsedManualCommand]:
    """Parse the production Manual one-line DSL.

    The first two numeric tokens preserve the historic quick command. Additional tokens
    are explicit operator stop conditions. Historic third-token ``15V`` / ``2.3A``
    means *reach that value* and therefore maps to a separate crossing detector rather
    than to a one-sided >= or <= predicate.
    """
    raw = str(text or "").strip()
    if not raw or raw.startswith("/"):
        return None
    if raw.lower() in {"manual", "ручной", "manual_main_mix"}:
        profile = load_manual_profile(MANUAL_PROFILE_PATH)
        return ParsedManualCommand(request=ManualChargeRequest.from_profile(profile))
    if "\n" in raw and raw.lower().lstrip().startswith("main"):
        profile = parse_manual_profile_input(raw)
        save_manual_profile(profile, MANUAL_PROFILE_PATH)
        return ParsedManualCommand(request=ManualChargeRequest.from_profile(profile))
    tokens = raw.replace("≥", ">=").replace("≤", "<=").split()
    if len(tokens) < 2:
        return None
    try:
        voltage = _float(tokens[0])
        current = _float(tokens[1])
    except ValueError:
        return None

    # Once the first two tokens are numeric this is unambiguously a Manual command;
    # invalid limits/conditions must be rejected instead of falling through to the LLM.
    request_base = ManualChargeRequest(voltage_v=voltage, current_a=current)
    _ = request_base

    fields: Dict[str, Optional[float]] = {
        "max_active_seconds": None,
        "voltage_ge_v": None,
        "voltage_le_v": None,
        "current_ge_a": None,
        "current_le_a": None,
        "delta": None,
    }
    reach_v: Optional[float] = None
    reach_i: Optional[float] = None

    def set_once(name: str, value: float) -> None:
        if fields[name] is not None:
            raise ValueError(f"условие {name} задано больше одного раза")
        fields[name] = value

    for token in tokens[2:]:
        original = token.strip()
        lower = original.lower().replace(",", ".")
        upper = original.upper().replace(",", ".")

        if ":" in original and "=" not in original:
            set_once("max_active_seconds", _duration_seconds(original))
            continue
        if lower.startswith("t=") or lower.startswith("time="):
            value = original.split("=", 1)[1]
            set_once("max_active_seconds", _duration_seconds(value))
            continue

        if upper.endswith(("A", "А")) and not any(op in original for op in (">", "<", "=")):
            if reach_i is not None:
                raise ValueError("точный ток остановки задан больше одного раза")
            reach_i = _validate_stop_current(_float(original[:-1]))
            continue
        if upper.endswith(("V", "В")) and not any(op in original for op in (">", "<", "=")):
            if reach_v is not None:
                raise ValueError("точное напряжение остановки задано больше одного раза")
            reach_v = _validate_stop_voltage(_float(original[:-1]))
            continue

        compact = lower.replace(" ", "")
        if compact.startswith("v>="):
            set_once("voltage_ge_v", _validate_stop_voltage(_float(compact[3:])))
        elif compact.startswith("v<="):
            set_once("voltage_le_v", _validate_stop_voltage(_float(compact[3:])))
        elif compact.startswith("v="):
            if reach_v is not None:
                raise ValueError("точное напряжение остановки задано больше одного раза")
            reach_v = _validate_stop_voltage(_float(compact[2:]))
        elif compact.startswith("i>="):
            set_once("current_ge_a", _validate_stop_current(_float(compact[3:])))
        elif compact.startswith("i<="):
            set_once("current_le_a", _validate_stop_current(_float(compact[3:])))
        elif compact.startswith("i="):
            if reach_i is not None:
                raise ValueError("точный ток остановки задан больше одного раза")
            reach_i = _validate_stop_current(_float(compact[2:]))
        elif compact.startswith("delta="):
            set_once("delta", _float(compact.split("=", 1)[1]))
        elif compact.startswith("d=") or compact.startswith("δ=") or compact.startswith("Δ="):
            set_once("delta", _float(compact.split("=", 1)[1]))
        else:
            raise ValueError(f"неизвестное условие ручного режима: {original}")

    stop = ManualStopConditions(**fields)
    request = ManualChargeRequest(
        voltage_v=voltage,
        current_a=current,
        stop=stop,
        notes="Telegram V2 Manual command",
    )
    return ParsedManualCommand(
        request=request,
        reach_voltage_v=reach_v,
        reach_current_a=reach_i,
    )


def manual_help_text() -> str:
    return (
        "<b>Ручной режим MAIN → MIX</b>\n"
        "Параметры задаются отдельно в <code>config/charge/manual.yaml</code>.\n"
        "MAIN: ток, напряжение, подтверждённый нижний порог, выдержка.\n"
        "Нижний порог MAIN: <code>I&lt;=0.30 A</code> подтверждается перед выдержкой.\n"
        "После подтверждения минимума и выдержки запускается MIX.\n"
        "MIX: ток, напряжение, ΔV, ΔI, выдержка.\n"
        "Для записи новых значений отправьте две строки:\n"
        "<code>MAIN: U=14.7 I=5.0 Imin=0.30 hold=600</code>\n"
        "<code>MIX: U=16.5 I=1.5 dV=0.03 dI=0.03 hold=7200</code>\n"
        "После записи профиль запускается командой <code>MANUAL</code>.\n"
        "Старый формат одной строки отключён.\n"
        f"Envelope: U &lt;= <b>{MAX_MANUAL_VOLTAGE:.1f} V</b>, I &lt;= <b>{MAX_STAGE_CURRENT:.1f} A</b>."
    )


def _legacy_numeric_manual(text: str) -> bool:
    parts = str(text or "").replace(",", ".").split()
    if len(parts) < 2:
        return False
    try:
        float(parts[0])
        float(parts[1])
    except ValueError:
        return False
    return True


def _format_start(parsed: ParsedManualCommand, *, replaced: bool) -> str:
    request = parsed.request
    stop = request.stop
    conditions: list[str] = []
    if stop.max_active_seconds is not None:
        conditions.append(f"T={stop.max_active_seconds / 3600.0:.2f} h active")
    if stop.voltage_ge_v is not None:
        conditions.append(f"V>={stop.voltage_ge_v:.2f}")
    if stop.voltage_le_v is not None:
        conditions.append(f"V<={stop.voltage_le_v:.2f}")
    if parsed.reach_voltage_v is not None:
        conditions.append(f"V={parsed.reach_voltage_v:.2f} reach")
    if stop.current_ge_a is not None:
        conditions.append(f"I>={stop.current_ge_a:.2f}")
    if stop.current_le_a is not None:
        conditions.append(f"I<={stop.current_le_a:.2f}")
    if parsed.reach_current_a is not None:
        conditions.append(f"I={parsed.reach_current_a:.2f} reach")
    if request.operation_mode == "mix" and stop.delta is not None:
        conditions.append(f"delta={stop.delta:.3f}")
    if request.operation_mode == "main":
        conditions.insert(0, "CV Imin по штатному порогу")
    elif stop.delta is not None:
        conditions.append("после Delta выдержка 2ч")
    suffix = ", ".join(conditions) if conditions else "только operator stop / hard safety"
    verb = "перенастроен" if replaced else "запущен"
    return (
        f"<b>🛠 {request.operation_mode_label} {verb.lower()}</b>\n"
        f"U={request.voltage_v:.2f} V · I={request.current_a:.2f} A\n"
        f"OVP={request.ovp_v:.2f} V · OCP={request.ocp_a:.2f} A\n"
        f"Stop: <code>{html.escape(suffix)}</code>\n"
        "Автоматическая химическая FSM не имеет authority в этом режиме."
    )


def _another_dialog_owns_text(app: Any, user_id: int) -> bool:
    """Keep structured V2/legacy dialog input ahead of the global quick Manual parser."""
    if user_id in getattr(app, "custom_mode_state", {}):
        return True
    if getattr(app, "awaiting_ah", {}).get(user_id):
        return True
    # SG input starts with six numeric values, so without explicit ownership the first
    # two can look exactly like a quick ``V I`` Manual command.
    if user_id in getattr(v2_sg_ui, "_pending_sg_battery", {}):
        return True
    return False


class ManualTextMiddleware(BaseMiddleware):
    def __init__(self, app: Any) -> None:
        self.app = app
        self.pending_users: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.text:
            return await handler(event, data)
        user_id = event.from_user.id if event.from_user else 0
        text = event.text.strip()
        if text.startswith("/"):
            return await handler(event, data)

        # Structured multi-step inputs own their next message before the global Manual
        # quick-command parser. The native Manual prompt itself needs no dialog FSM.
        if _another_dialog_owns_text(self.app, user_id):
            return await handler(event, data)

        if _legacy_numeric_manual(text):
            self.pending_users.discard(user_id)
            await event.answer(
                "❌ Старый формат Manual отключён. Используйте значения из конфигурации и отправьте "
                "<code>MANUAL</code>.\n" + manual_help_text()
            )
            return None

        try:
            parsed = parse_manual_command(text)
        except ValueError as exc:
            first_two_numeric = False
            parts = text.replace(",", ".").split()
            if len(parts) >= 2:
                try:
                    float(parts[0])
                    float(parts[1])
                    first_two_numeric = True
                except ValueError:
                    pass
            if user_id in self.pending_users or first_two_numeric:
                self.pending_users.discard(user_id)
                await event.answer(
                    f"❌ {html.escape(str(exc))}\n\n{manual_help_text()}",
                )
                return None
            return await handler(event, data)

        if parsed is None:
            if user_id in self.pending_users:
                self.pending_users.discard(user_id)
                await event.answer("❌ Не распознал параметры.\n\n" + manual_help_text())
                return None
            return await handler(event, data)

        self.pending_users.discard(user_id)
        if not await self.app._check_chat_and_respond(event):
            return None

        manager = getattr(self.app, "manual_session_manager", None)
        if not isinstance(manager, ProductionManualSessionManager):
            await event.answer("❌ V2 Manual runtime не инициализирован.")
            return None

        # Historic three-token commands replaced the old Manual-OFF condition. The new
        # reach/timer lives inside ManualSession; clear the legacy overlay only when a
        # direct command actually carries its own stop rule. Plain V I keeps any
        # independently configured persistent Manual-OFF condition intact.
        carries_stop = (
            parsed.reach_voltage_v is not None
            or parsed.reach_current_a is not None
            or any(
                value is not None
                for value in (
                    parsed.request.stop.max_active_seconds,
                    parsed.request.stop.voltage_ge_v,
                    parsed.request.stop.voltage_le_v,
                    parsed.request.stop.current_ge_a,
                    parsed.request.stop.current_le_a,
                    parsed.request.stop.delta,
                )
            )
        )
        if carries_stop:
            clear_overlay = getattr(self.app, "_clear_manual_off", None)
            if callable(clear_overlay):
                clear_overlay()

        replaced = manager.is_active
        try:
            if replaced:
                enabled = await manager.replace(
                    parsed.request,
                    reach_voltage_v=parsed.reach_voltage_v,
                    reach_current_a=parsed.reach_current_a,
                )
            else:
                enabled = await manager.start(
                    parsed.request,
                    reach_voltage_v=parsed.reach_voltage_v,
                    reach_current_a=parsed.reach_current_a,
                )
        except (RuntimeError, ValueError) as exc:
            await event.answer(f"❌ Manual не запущен: {html.escape(str(exc))}")
            return None

        if not enabled:
            await event.answer(
                "❌ Manual не запущен: безопасное программирование/включение RD6018 не подтверждено."
            )
            return None

        self.app.last_chat_id = event.chat.id
        self.app.last_user_id = user_id
        await event.answer(_format_start(parsed, replaced=replaced))
        schedule = getattr(self.app, "schedule_dashboard_after_60", None)
        if callable(schedule):
            schedule(event.chat.id, user_id)
        return None


def install_manual_text_v2(app: Any) -> ManualTextMiddleware:
    existing = getattr(app, "_v2_manual_text_middleware", None)
    if isinstance(existing, ManualTextMiddleware):
        return existing

    middleware = ManualTextMiddleware(app)
    # Outer middleware runs before the already-registered catch-all F.text handler, so
    # legacy direct setpoint writes cannot bypass managed Manual authority in V2.
    app.router.message.outer_middleware.register(middleware)
    app._v2_manual_text_middleware = middleware

    @app.router.callback_query(F.data == "v2_manual")
    async def v2_manual_handler(call: CallbackQuery) -> None:
        if not await app._check_chat_and_respond(call):
            return
        await call.answer()
        user_id = call.from_user.id if call.from_user else 0
        middleware.pending_users.add(user_id)
        await call.message.answer(
            manual_help_text(),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅ К программам", callback_data="charge_modes")]
                ]
            ),
        )

    return middleware
