from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ha_history import HomeAssistantHistoryError, HomeAssistantHistoryReader, MixHistoryEvidence
from pb_domain import BatteryChemistry
from rd6018_telemetry import RegulationMode, finite_float, resolve_regulation
from signal_analyzer import SignalAnalyzer, SignalEvent, SignalSample
from v2_battery_catalog import list_batteries
from v2_ui import battery_button_label


MIX_HARD_LIMIT_HOURS = {
    BatteryChemistry.CA_CA: 20.0,
    BatteryChemistry.FLOODED: 20.0,
    BatteryChemistry.EFB: 24.0,
    BatteryChemistry.AGM: 10.0,
}
MIX_FINISH_HOLD_S = 2 * 3600.0
OBSERVER_POLL_S = 30.0
SETPOINT_CHANGE_TOLERANCE = 0.08


class LiveMixObserverMode(str, Enum):
    OBSERVE_ONLY = "observe_only"
    DELTA_THEN_OFF = "delta_then_off"


class LiveMixObserverState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    OFF_PENDING = "off_pending"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class LiveMixFingerprint:
    set_voltage_v: float
    set_current_a: float
    ovp_v: float
    ocp_a: float


@dataclass(frozen=True)
class LiveMixPreview:
    battery_id: str
    chemistry: BatteryChemistry
    capacity_ah: float
    fingerprint: LiveMixFingerprint
    history: Optional[MixHistoryEvidence]
    history_error: str = ""


class HandsOffMixObserver:
    """Observe an already-running external Mix without taking setpoint authority.

    This is the D063 non-autonomous fallback for a live RD6018 that cannot safely be
    converted to full managed authority in place. It deliberately remains in
    HANDS_OFF: it never writes V/I/OVP/OCP, never turns Output ON, and never treats HA
    history as finish evidence. Optional DELTA_THEN_OFF grants exactly one bounded
    actuator authority: after a *fresh post-activation* V2 Delta plus the normal 2 h
    hold, issue the existing explicit verified HANDS_OFF Output OFF.

    A normal process restart never resumes Delta/future-OFF authority. The one
    exception is a durable OFF_PENDING state: once final OFF has already become the
    required safety action, restart may only continue trying to prove OFF, never resume
    charging authority.
    """

    VERSION = 1

    def __init__(
        self,
        app: Any,
        manager: Any,
        *,
        state_file: str = "rd_live_mix_observer_v2.json",
        poll_s: float = OBSERVER_POLL_S,
    ) -> None:
        self.app = app
        self.manager = manager
        self.state_file = str(state_file)
        self.poll_s = max(1.0, float(poll_s))
        self.state = LiveMixObserverState.IDLE
        self.mode: Optional[LiveMixObserverMode] = None
        self.battery_id = ""
        self.chemistry: Optional[BatteryChemistry] = None
        self.capacity_ah = 0.0
        self.fingerprint: Optional[LiveMixFingerprint] = None
        self.started_at_s = 0.0
        self.finish_hold_started_at_s: Optional[float] = None
        self.last_source_timestamp_s: Optional[float] = None
        self.last_status = ""
        self._task: Optional[asyncio.Task] = None
        self.analyzer = SignalAnalyzer()
        self._restore_interrupted()

    @property
    def active(self) -> bool:
        return self.state is LiveMixObserverState.ACTIVE

    @property
    def off_pending(self) -> bool:
        return self.state is LiveMixObserverState.OFF_PENDING

    @property
    def actuator_authority(self) -> bool:
        return (
            self.active and self.mode is LiveMixObserverMode.DELTA_THEN_OFF
        ) or self.off_pending

    def _document(self) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "state": self.state.value,
            "mode": self.mode.value if self.mode is not None else None,
            "battery_id": self.battery_id,
            "chemistry": self.chemistry.value if self.chemistry is not None else None,
            "capacity_ah": self.capacity_ah,
            "fingerprint": (
                {
                    "set_voltage_v": self.fingerprint.set_voltage_v,
                    "set_current_a": self.fingerprint.set_current_a,
                    "ovp_v": self.fingerprint.ovp_v,
                    "ocp_a": self.fingerprint.ocp_a,
                }
                if self.fingerprint is not None
                else None
            ),
            "started_at_s": self.started_at_s,
            "finish_hold_started_at_s": self.finish_hold_started_at_s,
            "last_source_timestamp_s": self.last_source_timestamp_s,
            "last_status": self.last_status,
            "saved_at_s": time.time(),
        }

    def _persist(self) -> None:
        path = os.path.abspath(self.state_file)
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".rd-live-mix-observer-",
            suffix=".tmp",
            dir=directory,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._document(), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except OSError:
                pass

    def _restore_interrupted(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if not isinstance(raw, dict) or int(raw.get("version")) != self.VERSION:
                return
            previous = LiveMixObserverState(str(raw.get("state") or "idle"))
            self.battery_id = str(raw.get("battery_id") or "")
            chemistry_raw = raw.get("chemistry")
            self.chemistry = BatteryChemistry(str(chemistry_raw)) if chemistry_raw else None
            self.capacity_ah = float(raw.get("capacity_ah") or 0.0)
            mode_raw = raw.get("mode")
            self.mode = LiveMixObserverMode(str(mode_raw)) if mode_raw else None
            if previous is LiveMixObserverState.OFF_PENDING:
                # OFF containment is the only authority that survives restart.
                self.state = LiveMixObserverState.OFF_PENDING
                self.finish_hold_started_at_s = None
                self.last_source_timestamp_s = None
                self.last_status = "restart: verified Output OFF remains pending"
                self._persist()
            elif previous is LiveMixObserverState.ACTIVE:
                self.state = LiveMixObserverState.INTERRUPTED
                self.last_status = (
                    "process_restart: observer/future-OFF authority requires fresh operator authorization"
                )
                self.finish_hold_started_at_s = None
                self.last_source_timestamp_s = None
                self._persist()
            else:
                self.state = previous
                self.last_status = str(raw.get("last_status") or "")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.state = LiveMixObserverState.IDLE
            self.mode = None

    @staticmethod
    def fingerprint_from_live(live: dict[str, Any]) -> Optional[LiveMixFingerprint]:
        values = [
            finite_float(live.get("set_voltage")),
            finite_float(live.get("set_current")),
            finite_float(live.get("ovp")),
            finite_float(live.get("ocp")),
        ]
        if any(value is None for value in values):
            return None
        set_v, set_i, ovp, ocp = (float(value) for value in values if value is not None)
        if set_v <= 0 or set_i <= 0 or ovp <= 0 or ocp <= 0:
            return None
        return LiveMixFingerprint(set_v, set_i, ovp, ocp)

    @staticmethod
    def fingerprint_matches(
        expected: LiveMixFingerprint,
        actual: LiveMixFingerprint,
        *,
        tolerance: float = SETPOINT_CHANGE_TOLERANCE,
    ) -> bool:
        return all(
            abs(a - b) <= float(tolerance)
            for a, b in (
                (expected.set_voltage_v, actual.set_voltage_v),
                (expected.set_current_a, actual.set_current_a),
                (expected.ovp_v, actual.ovp_v),
                (expected.ocp_a, actual.ocp_a),
            )
        )

    @staticmethod
    def _source_timestamp(live: dict[str, Any]) -> Optional[float]:
        meta = live.get("_meta")
        if not isinstance(meta, dict):
            return None
        candidates: list[float] = []
        for key in (
            "current",
            "battery_voltage",
            "temp_ext_v2",
            "temp_ext",
            "regulation_code",
            "is_cv",
            "is_cc",
        ):
            item = meta.get(key)
            if not isinstance(item, dict):
                continue
            raw = item.get("last_reported") or item.get("last_updated")
            if not isinstance(raw, str) or not raw:
                continue
            text = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
            try:
                parsed = datetime.fromisoformat(text).timestamp()
            except (ValueError, OverflowError):
                continue
            if math.isfinite(parsed) and parsed > 0:
                candidates.append(parsed)
        # Use the oldest timestamp in the coherent U/I/T/mode observation. A newly
        # reported current must not lend freshness to an older temperature/mode value.
        return min(candidates) if candidates else None

    async def start(
        self,
        preview: LiveMixPreview,
        *,
        mode: LiveMixObserverMode,
    ) -> None:
        if self.active or self.off_pending:
            raise RuntimeError("live Mix observer already owns pending state")
        if not bool(getattr(self.manager, "hands_off", False)):
            raise RuntimeError("live Mix observer requires HANDS_OFF")

        live = await self.manager.guard._raw_live()
        if str(live.get("switch", "")).strip().lower() != "on":
            raise RuntimeError("live Mix observer requires current Output ON")
        fresh_fingerprint = self.fingerprint_from_live(live)
        if fresh_fingerprint is None:
            raise RuntimeError("live Mix setpoint/protection readback is incomplete")
        if not self.fingerprint_matches(preview.fingerprint, fresh_fingerprint):
            raise RuntimeError("live RD setpoints changed after preview; refresh adoption preview")

        self.mode = LiveMixObserverMode(mode)
        self.battery_id = preview.battery_id
        self.chemistry = preview.chemistry
        self.capacity_ah = float(preview.capacity_ah)
        self.fingerprint = fresh_fingerprint
        self.started_at_s = time.time()
        self.finish_hold_started_at_s = None
        # This is the fresh-evidence barrier. Recorder/live samples whose source
        # heartbeat predates operator confirmation can be displayed as history but can
        # never become the first Imin/Vmax of the new authority epoch.
        self.last_source_timestamp_s = self.started_at_s
        self.last_status = "fresh post-activation Delta epoch started; waiting for a new HA source report"
        self.analyzer.reset_stage(
            "Adopted Mix observer",
            target_voltage_v=fresh_fingerprint.set_voltage_v,
        )
        self.state = LiveMixObserverState.ACTIVE
        self._persist()
        self._task = asyncio.create_task(self._run(), name="rd6018-hands-off-mix-observer")

    async def cancel(self) -> None:
        if self.off_pending:
            raise RuntimeError("verified Output OFF is already pending and cannot be cancelled")
        task = self._task
        self._task = None
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.state = LiveMixObserverState.CANCELLED
        self.finish_hold_started_at_s = None
        self.last_status = "operator_cancelled_without_actuation"
        self._persist()

    def _notify(self, message: str) -> None:
        callback = getattr(self.app, "_charge_notify", None)
        if callable(callback):
            try:
                callback(message, critical=False)
            except TypeError:
                callback(message)
            except Exception:
                pass

    def _reset_evidence_for_new_setpoints(self, fingerprint: LiveMixFingerprint) -> None:
        self.fingerprint = fingerprint
        self.finish_hold_started_at_s = None
        # Do not accept the same HA report that revealed the setpoint change as a fresh
        # chemistry sample. Wait until all relevant sources report after this reset.
        self.last_source_timestamp_s = time.time()
        self.analyzer.reset_stage(
            "Adopted Mix observer",
            target_voltage_v=fingerprint.set_voltage_v,
        )
        self.last_status = "external setpoints changed; fresh Delta epoch restarted"
        self._persist()
        self._notify(
            "🧲 Mix-наблюдение: уставки RD изменились вручную. Старое Delta-доказательство сброшено; "
            "наблюдение продолжено с нового чистого epoch."
        )

    async def _finish_verified_off(self) -> bool:
        self.state = LiveMixObserverState.OFF_PENDING
        self.finish_hold_started_at_s = None
        self.last_status = "fresh Delta + 2h hold complete; verified Output OFF pending"
        # Persist OFF containment before the first actuation attempt. A crash may only
        # continue toward OFF, never reconstruct or resume the external Mix authority.
        self._persist()
        try:
            await self.manager.operator_output_off(self.app.ENTITY_MAP.get("switch"))
        except Exception as exc:
            self.last_status = f"verified Output OFF still pending: {type(exc).__name__}: {exc}"
            self._persist()
            return False

        self.state = LiveMixObserverState.COMPLETED
        self.last_status = "fresh Delta + 2h hold complete; Output verified OFF"
        self._persist()
        self._notify(
            "⏹ <b>Внешний Mix завершён:</b> свежая Delta + 2ч выдержка. Output подтверждён OFF. "
            "HANDS_OFF остаётся включён."
        )
        return True

    async def recover_startup(self) -> bool:
        """Resume only a previously committed OFF containment after process restart."""
        if not self.off_pending:
            return True
        if not bool(getattr(self.manager, "hands_off", False)):
            self.last_status = "OFF_PENDING recovery blocked: durable RD mode is not HANDS_OFF"
            self._persist()
            return False
        return await self._finish_verified_off()

    async def observe_once(self) -> None:
        if self.off_pending:
            await self._finish_verified_off()
            return
        if not self.active:
            return
        if not bool(getattr(self.manager, "hands_off", False)):
            self.state = LiveMixObserverState.FAILED
            self.last_status = "HANDS_OFF ownership was removed while observer was active"
            self._persist()
            return

        live = await self.manager.guard._raw_live()
        if str(live.get("switch", "")).strip().lower() != "on":
            self.state = LiveMixObserverState.COMPLETED
            self.last_status = "Output became OFF externally"
            self.finish_hold_started_at_s = None
            self._persist()
            return

        fingerprint = self.fingerprint_from_live(live)
        if fingerprint is None:
            self.last_status = "setpoint/protection readback unavailable; no evidence accepted"
            self._persist()
            return
        if self.fingerprint is None or not self.fingerprint_matches(self.fingerprint, fingerprint):
            self._reset_evidence_for_new_setpoints(fingerprint)

        source_timestamp = self._source_timestamp(live)
        if source_timestamp is None:
            self.last_status = "source timestamps unavailable; no Delta evidence accepted"
            self._persist()
            return
        if self.last_source_timestamp_s is not None and source_timestamp <= self.last_source_timestamp_s:
            return

        voltage = finite_float(live.get("battery_voltage"))
        current = finite_float(live.get("current"))
        temp = finite_float(live.get("temp_ext_v2"))
        if temp is None:
            temp = finite_float(live.get("temp_ext"))
        regulation = resolve_regulation(live)
        if (
            voltage is None
            or current is None
            or temp is None
            or regulation not in {RegulationMode.CV, RegulationMode.CC}
        ):
            self.last_source_timestamp_s = source_timestamp
            self.last_status = "incomplete U/I/T/regulation sample; no Delta evidence accepted"
            self._persist()
            return

        self.last_source_timestamp_s = source_timestamp
        analysis = self.analyzer.observe(
            SignalSample(
                timestamp_s=source_timestamp,
                voltage_v=float(voltage),
                current_a=float(current),
                temp_c=float(temp),
                is_cv=regulation is RegulationMode.CV,
                is_cc=regulation is RegulationMode.CC,
            )
        )
        metrics = analysis.metrics
        self.last_status = (
            f"{regulation.value}: Imin={metrics.current_min_a!r} "
            f"dI={metrics.delta_current_from_min_a!r} Vmax={metrics.voltage_max_v!r} "
            f"dV={metrics.delta_voltage_from_max_v!r}"
        )

        if SignalEvent.END_OF_CHARGE_LIKELY in analysis.events and self.finish_hold_started_at_s is None:
            self.finish_hold_started_at_s = time.time()
            evidence = (
                f"Imin={metrics.current_min_a:.3f}A ΔI={metrics.delta_current_from_min_a:.3f}A"
                if regulation is RegulationMode.CV
                and metrics.current_min_a is not None
                and metrics.delta_current_from_min_a is not None
                else (
                    f"Vmax={metrics.voltage_max_v:.3f}V ΔV={metrics.delta_voltage_from_max_v:.3f}V"
                    if metrics.voltage_max_v is not None
                    and metrics.delta_voltage_from_max_v is not None
                    else regulation.value
                )
            )
            self.last_status = f"fresh Delta accepted; 2h hold started ({evidence})"
            self._notify(
                f"🎯 <b>Текущая внешняя Mix: свежая Delta подтверждена.</b>\n{evidence}\n"
                "Начата 2-часовая выдержка. История HA в это доказательство не включалась."
            )

        if self.finish_hold_started_at_s is not None:
            held = max(0.0, time.time() - self.finish_hold_started_at_s)
            if held >= MIX_FINISH_HOLD_S:
                if self.mode is LiveMixObserverMode.DELTA_THEN_OFF:
                    await self._finish_verified_off()
                    return
                self.last_status = "fresh Delta + 2h hold complete; observe-only mode did not actuate"

        self._persist()

    async def _run(self) -> None:
        try:
            while self.active or self.off_pending:
                await self.observe_once()
                if not (self.active or self.off_pending):
                    break
                await asyncio.sleep(self.poll_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # OFF_PENDING is safety containment and must not be downgraded to FAILED.
            if self.off_pending:
                self.last_status = f"OFF_PENDING runtime error: {type(exc).__name__}: {exc}"
                self._persist()
            elif self.active:
                self.state = LiveMixObserverState.FAILED
                self.last_status = f"observer_runtime_error:{type(exc).__name__}:{exc}"
                self._persist()


def _hours(seconds: Optional[float]) -> str:
    if seconds is None:
        return "неизвестно"
    return f"{max(0.0, float(seconds)) / 3600.0:.1f} ч"


def _summary_line(label: str, summary: Any, suffix: str) -> Optional[str]:
    if summary is None or getattr(summary, "count", 0) <= 0:
        return None
    return (
        f"{label}: min {summary.minimum:.2f}, max {summary.maximum:.2f}, "
        f"сейчас {summary.latest:.2f}{suffix}"
    )


def format_live_mix_preview(preview: LiveMixPreview) -> str:
    history = preview.history
    lines = [
        "<b>🧲 Подхват текущего внешнего Mix</b>",
        f"АКБ: <code>{preview.battery_id}</code> · {preview.chemistry.value} · {preview.capacity_ah:g} Ah",
        (
            f"RD сейчас: {preview.fingerprint.set_voltage_v:.2f} V / "
            f"{preview.fingerprint.set_current_a:.2f} A · "
            f"OVP {preview.fingerprint.ovp_v:.2f} / OCP {preview.fingerprint.ocp_a:.2f}"
        ),
    ]
    hard_limit = MIX_HARD_LIMIT_HOURS.get(preview.chemistry)
    if history is not None:
        if history.output.reliable:
            lines.append(f"HA Recorder: непрерывный Output ON {_hours(history.output.elapsed_s)}")
            if (
                hard_limit is not None
                and history.output.elapsed_s is not None
                and history.output.elapsed_s >= hard_limit * 3600.0
            ):
                lines.append(
                    f"⚠️ HA-age уже >= стандартного chemistry Mix max {hard_limit:g} ч. "
                    "HANDS_OFF-наблюдение не продлевает и не выдаёт новый chemistry budget."
                )
        else:
            lines.append(f"HA Recorder: возраст Mix не доказан ({history.output.reason})")
        for line in (
            _summary_line("I history", history.current, " A"),
            _summary_line("Uout history", history.output_voltage, " V"),
            _summary_line("T history", history.external_temperature, " °C"),
        ):
            if line:
                lines.append(line)
    elif preview.history_error:
        lines.append(f"HA Recorder недоступен: {preview.history_error}")

    if hard_limit is not None:
        lines.append(f"Стандартный chemistry Mix max: {hard_limit:g} ч активного Mix.")
    lines.extend(
        [
            "",
            "<b>Важно:</b> история HA используется только как контекст/оценка возраста. "
            "Она не переносит старый Imin/Vmax в автоматическое решение.",
            "После подтверждения начинается новый Delta epoch. Режим остаётся HANDS_OFF: "
            "бот не меняет V/I/OVP/OCP и не включает Output.",
        ]
    )
    return "\n".join(lines)


def install_rd_live_adoption(app: Any, manager: Any) -> HandsOffMixObserver:
    existing = getattr(app, "rd_live_mix_observer", None)
    if isinstance(existing, HandsOffMixObserver):
        return existing

    observer = HandsOffMixObserver(app, manager)
    app.rd_live_mix_observer = observer
    reader = HomeAssistantHistoryReader(app.hass, app.ENTITY_MAP)
    pending: dict[int, dict[str, Any]] = {}

    original_dashboard = app._build_dashboard_keyboard

    def dashboard(
        is_on: bool,
        user_id: int,
        *,
        back_to_dashboard: bool = False,
    ) -> InlineKeyboardMarkup:
        markup = original_dashboard(is_on, user_id, back_to_dashboard=back_to_dashboard)
        if back_to_dashboard or not bool(getattr(manager, "hands_off", False)):
            return markup
        rows = [list(row) for row in markup.inline_keyboard]
        if is_on:
            rows.insert(
                1,
                [
                    InlineKeyboardButton(
                        text=(
                            "🧲 Mix-наблюдение"
                            if observer.active or observer.off_pending
                            else "🧲 Подхватить текущий Mix"
                        ),
                        callback_data=(
                            "rd_live_mix_status"
                            if observer.active or observer.off_pending
                            else "rd_live_mix"
                        ),
                    )
                ],
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)

    app._build_dashboard_keyboard = dashboard

    async def _require_preview(call: Any) -> Optional[dict[str, Any]]:
        user_id = call.from_user.id if call.from_user else 0
        item = pending.get(user_id)
        if item is None:
            await call.answer("Предпросмотр устарел — откройте подхват Mix заново", show_alert=True)
            return None
        return item

    @app.router.callback_query(F.data == "rd_live_mix")
    async def _live_mix_menu(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        if not manager.hands_off:
            await call.answer("Сначала включите Режим РД — не лезь", show_alert=True)
            return
        if observer.active or observer.off_pending:
            await call.answer("Mix-наблюдение уже активно", show_alert=True)
            return
        live = await manager.guard._raw_live()
        if str(live.get("switch", "")).strip().lower() != "on":
            await call.answer("Output сейчас не ON", show_alert=True)
            return
        fingerprint = observer.fingerprint_from_live(live)
        if fingerprint is None:
            await call.answer("Нет полного readback V/I/OVP/OCP", show_alert=True)
            return
        try:
            history = await reader.read_mix_evidence(live=live)
            history_error = ""
        except HomeAssistantHistoryError as exc:
            history = None
            history_error = str(exc)

        records = [
            record
            for record in await list_batteries(limit=30)
            if record.identity.chemistry in MIX_HARD_LIMIT_HOURS
        ]
        if not records:
            await call.answer("Нет сохранённой Pb АКБ подходящей химии", show_alert=True)
            return
        user_id = call.from_user.id if call.from_user else 0
        pending[user_id] = {
            "fingerprint": fingerprint,
            "history": history,
            "history_error": history_error,
            "records": records,
        }
        rows = [
            [
                InlineKeyboardButton(
                    text=battery_button_label(record),
                    callback_data=f"rd_live_mix_bat_{idx}",
                )
            ]
            for idx, record in enumerate(records)
        ]
        rows.append([InlineKeyboardButton(text="Отмена", callback_data="rd_live_mix_cancel")])
        await call.answer()
        await call.message.answer(
            "🧲 <b>Какую физическую АКБ сейчас держит RD6018?</b>\n"
            "История Home Assistant уже прочитана; выбор АКБ не меняет RD.",
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @app.router.callback_query(F.data.startswith("rd_live_mix_bat_"))
    async def _live_mix_battery(call: Any) -> None:
        item = await _require_preview(call)
        if item is None:
            return
        try:
            index = int(str(call.data).rsplit("_", 1)[-1])
            record = item["records"][index]
        except (ValueError, IndexError):
            await call.answer("Выбор АКБ устарел", show_alert=True)
            return
        preview = LiveMixPreview(
            battery_id=record.identity.battery_id,
            chemistry=record.identity.chemistry,
            capacity_ah=record.identity.nominal_capacity_ah,
            fingerprint=item["fingerprint"],
            history=item["history"],
            history_error=item["history_error"],
        )
        item["preview"] = preview
        await call.answer()
        await call.message.answer(
            format_live_mix_preview(preview),
            parse_mode=app.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👁 Только наблюдать",
                            callback_data="rd_live_mix_start_observe",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🎯 Свежая Delta + 2ч → OFF",
                            callback_data="rd_live_mix_start_delta_off",
                        )
                    ],
                    [InlineKeyboardButton(text="Отмена", callback_data="rd_live_mix_cancel")],
                ]
            ),
        )

    async def _start_from_pending(call: Any, mode: LiveMixObserverMode) -> None:
        if not await app._check_chat_and_respond(call):
            return
        item = await _require_preview(call)
        if item is None:
            return
        preview = item.get("preview")
        if not isinstance(preview, LiveMixPreview):
            await call.answer("Сначала выберите АКБ", show_alert=True)
            return
        try:
            await observer.start(preview, mode=mode)
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        pending.pop(call.from_user.id if call.from_user else 0, None)
        await call.answer("Mix-наблюдение запущено")
        action = (
            "только наблюдение; Output бот не выключит"
            if mode is LiveMixObserverMode.OBSERVE_ONLY
            else "после свежей Delta и 2ч выдержки бот выполнит только verified Output OFF"
        )
        await call.message.answer(
            "🧲 <b>Текущий Mix подхвачен в HANDS_OFF.</b>\n"
            f"{action}.\n"
            "История HA сохранена как контекст; Delta считается заново с первого нового "
            "source-report после этого подтверждения. V/I/OVP/OCP не изменялись.",
            parse_mode=app.ParseMode.HTML,
        )

    @app.router.callback_query(F.data == "rd_live_mix_start_observe")
    async def _start_observe(call: Any) -> None:
        await _start_from_pending(call, LiveMixObserverMode.OBSERVE_ONLY)

    @app.router.callback_query(F.data == "rd_live_mix_start_delta_off")
    async def _start_delta_off(call: Any) -> None:
        await _start_from_pending(call, LiveMixObserverMode.DELTA_THEN_OFF)

    @app.router.callback_query(F.data == "rd_live_mix_status")
    async def _status(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        hold = (
            _hours(time.time() - observer.finish_hold_started_at_s)
            if observer.finish_hold_started_at_s is not None
            else "не начата"
        )
        await call.answer()
        await call.message.answer(
            "🧲 <b>Mix-наблюдение</b>\n"
            f"Состояние: {observer.state.value}\n"
            f"Режим: {observer.mode.value if observer.mode else '-'}\n"
            f"АКБ: <code>{observer.battery_id}</code>\n"
            f"Delta hold: {hold}\n"
            f"Последнее: <code>{observer.last_status}</code>",
            parse_mode=app.ParseMode.HTML,
            reply_markup=(
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Снять наблюдение (без OFF)",
                                callback_data="rd_live_mix_stop_observer",
                            )
                        ]
                    ]
                )
                if observer.active
                else None
            ),
        )

    @app.router.callback_query(F.data == "rd_live_mix_stop_observer")
    async def _stop_observer(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        try:
            await observer.cancel()
        except Exception as exc:
            await call.answer(str(exc), show_alert=True)
            return
        await call.answer("Наблюдение снято; RD не изменён")

    @app.router.callback_query(F.data == "rd_live_mix_cancel")
    async def _cancel_preview(call: Any) -> None:
        if not await app._check_chat_and_respond(call):
            return
        pending.pop(call.from_user.id if call.from_user else 0, None)
        await call.answer("Отменено")

    return observer
