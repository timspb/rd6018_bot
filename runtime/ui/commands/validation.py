"""Command validation without runtime or actuator dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Dict, Optional

from runtime.diagnostics import DiagnosticAuthority
from runtime.safety.variables import MAX_STAGE_CURRENT_A

from .models import (
    CommandResult, CommandStatus, ConfirmSafetyCommand, SelectProfileCommand,
    StartChargeCommand, StopChargeCommand, UpdateChargeSettingsCommand, UserCommand,
)


MAX_STAGE_CURRENT = float(MAX_STAGE_CURRENT_A.default)


def _parse_off_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит команду off с явными условиями:
    V>=16.4 / V<=13.2 — по напряжению (достигнет ≥ или снизится до ≤);
    I<=1.23 / I>=2 — по току (достигнет ≤ или достигнет ≥);
    2:23 — таймер.
    Без префикса: число 12–18 В → V>=, 0.1–12 А → I<= (как раньше).
    """
    t = (text or "").strip().replace(",", ".")
    if not t.lower().startswith("off "):
        return None
    rest = t[4:].strip().replace("\u2265", ">=").replace("\u2264", "<=")  # ≥ ≤
    if not rest:
        return None
    tokens = rest.lower().split()
    voltage_ge: Optional[float] = None
    voltage_le: Optional[float] = None
    current_le: Optional[float] = None
    current_ge: Optional[float] = None
    time_sec: Optional[float] = None
    parts: list = []

    for tok in tokens:
        if ":" in tok:
            try:
                comp = tok.split(":")
                if len(comp) == 2:
                    h, m = int(comp[0].strip()), int(comp[1].strip())
                    sec = h * 3600 + m * 60
                elif len(comp) == 3:
                    h, m, s = int(comp[0].strip()), int(comp[1].strip()), int(comp[2].strip())
                    sec = h * 3600 + m * 60 + s
                else:
                    continue
                if sec <= 0:
                    continue
                time_sec = (time_sec or 0) + sec
                parts.append(f"таймер {tok}")
            except (ValueError, IndexError):
                continue
        elif tok.startswith("v>="):
            try:
                voltage_ge = float(tok[3:].strip())
                if 0 <= voltage_ge <= 20:
                    parts.append(f"V≥{voltage_ge:.1f} В")
            except ValueError:
                continue
        elif tok.startswith("v<="):
            try:
                voltage_le = float(tok[3:].strip())
                if 0 <= voltage_le <= 20:
                    parts.append(f"V≤{voltage_le:.1f} В")
            except ValueError:
                continue
        elif tok.startswith("i>="):
            try:
                current_ge = float(tok[3:].strip())
                if 0 < current_ge <= MAX_STAGE_CURRENT:
                    parts.append(f"I≥{current_ge:.2f} А")
            except ValueError:
                continue
        elif tok.startswith("i<="):
            try:
                current_le = float(tok[3:].strip())
                if 0 < current_le <= MAX_STAGE_CURRENT:
                    parts.append(f"I≤{current_le:.2f} А")
            except ValueError:
                continue
        else:
            try:
                val = float(tok)
                if 12.0 <= val <= 18.0:
                    voltage_ge = val
                    parts.append(f"{val:.1f} В (V≥)")
                elif 0.1 <= val <= MAX_STAGE_CURRENT:
                    current_le = val
                    parts.append(f"{val:.2f} А (I≤)")
                else:
                    continue
            except ValueError:
                continue

    if voltage_ge is None and voltage_le is None and current_le is None and current_ge is None and time_sec is None:
        return None
    return {
        "voltage_ge": voltage_ge,
        "voltage_le": voltage_le,
        "current_le": current_le,
        "current_ge": current_ge,
        "time_sec": time_sec,
        "start_time": time.time(),
        "parts": parts,
    }



def _parse_three_values(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит строку из трёх частей: V I и третья — таймер H:MM, ток X.XXA/А, или напряжение X.XV/В.
    Возвращает dict с v, i и одним из: time_sec, off_current, off_voltage; иначе None.
    """
    parts = (text or "").strip().replace(",", ".").split()
    if len(parts) != 3:
        return None
    try:
        v = float(parts[0])
        i = float(parts[1])
        third = parts[2].strip().upper().rstrip("AАВV")
        if not third:
            return None
        # Таймер: 2:35 или 2:35:00
        if ":" in parts[2]:
            comp = parts[2].split(":")
            if len(comp) == 2:
                h, m = int(comp[0].strip()), int(comp[1].strip())
                time_sec = h * 3600 + m * 60
            elif len(comp) == 3:
                h, m, s = int(comp[0].strip()), int(comp[1].strip()), int(comp[2].strip())
                time_sec = h * 3600 + m * 60 + s
            else:
                return None
            if time_sec <= 0:
                return None
            return {"v": v, "i": i, "time_sec": time_sec}
        # Ток: 2.35A / 2.35А (латиница или кириллица) — выкл по достижении тока
        raw3 = parts[2].strip().replace(",", ".")
        last_char = (raw3[-1].upper() if len(raw3) > 1 else "")
        if last_char in ("A", "А"):  # A (Latin) или А (Cyrillic)
            val = float(third)
            if 0.1 <= val <= MAX_STAGE_CURRENT:
                return {"v": v, "i": i, "off_current": val}
            return None
        # Напряжение: 15V / 15В (латиница или кириллица) — выкл по достижении напряжения
        if last_char in ("V", "В"):  # V (Latin) или В (Cyrillic)
            val = float(third)
            if 0 <= val <= 20.0:
                return {"v": v, "i": i, "off_voltage": val}
            return None
    except (ValueError, IndexError):
        pass
    return None


def _parse_two_numbers(text: str) -> Optional[tuple]:
    """Парсит строку вида '16.50 1.4' (напряжение и ток). Возвращает (v, i) или None."""
    parts = (text or "").strip().replace(",", ".").split()
    if len(parts) != 2:
        return None
    try:
        v = float(parts[0])
        i = float(parts[1])
        return (v, i)
    except ValueError:
        return None


@dataclass(frozen=True)
class CommandContext:
    runtime_active: bool = False
    telemetry_available: bool = True
    authority: DiagnosticAuthority = DiagnosticAuthority.ALLOW
    selected_profile: str | None = None


class CommandValidator:
    def validate(self, command: UserCommand, context: CommandContext) -> CommandResult:
        if context.authority is DiagnosticAuthority.HARD_STOP:
            return CommandResult(CommandStatus.BLOCKED_BY_SAFETY, "hard_stop")
        if isinstance(command, StartChargeCommand):
            if context.runtime_active:
                return CommandResult(CommandStatus.REJECTED, "runtime_already_active")
            if not command.profile and not context.selected_profile:
                return CommandResult(CommandStatus.REJECTED, "profile_required")
            if not context.telemetry_available:
                return CommandResult(CommandStatus.REJECTED, "telemetry_required")
            if not command.confirmed:
                return CommandResult(CommandStatus.REQUIRES_CONFIRMATION, "start_confirmation_required")
        elif isinstance(command, StopChargeCommand):
            if not command.reason.strip():
                return CommandResult(CommandStatus.REJECTED, "stop_reason_required")
            if not command.confirmed:
                return CommandResult(CommandStatus.REQUIRES_CONFIRMATION, "stop_confirmation_required")
        elif isinstance(command, SelectProfileCommand):
            if not command.profile.strip():
                return CommandResult(CommandStatus.REJECTED, "profile_required")
        elif isinstance(command, UpdateChargeSettingsCommand):
            if not command.requested_settings:
                return CommandResult(CommandStatus.REJECTED, "settings_required")
            if context.runtime_active:
                return CommandResult(CommandStatus.REJECTED, "settings_change_requires_idle")
        elif isinstance(command, ConfirmSafetyCommand):
            if not command.acknowledgement.strip() or not command.confirmed:
                return CommandResult(CommandStatus.REQUIRES_CONFIRMATION, "safety_acknowledgement_required")
        return CommandResult(CommandStatus.ACCEPTED, "command_valid")


def parse_decimal_number(text: str) -> float:
    """Parse one user-entered decimal number, accepting comma or dot."""
    value = str(text).strip().replace(",", ".")
    if not value:
        raise ValueError("empty numeric input")
    return float(value)


def allow_operator_action(
    deadlines: dict[str, float],
    user_id: int,
    action: str,
    *,
    cooldown_sec: float = 1.2,
    now_s: float,
) -> bool:
    """Rate-limit duplicate UI intents with the caller-owned in-memory map.

    This function has no physical authority and does not own a separate clock,
    queue, lock, storage or runtime lifecycle. Preserve strict boundary semantics.
    """
    key = f"{user_id}:{action}"
    until = deadlines.get(key, 0.0)
    if now_s < until:
        return False
    deadlines[key] = now_s + cooldown_sec
    return True
