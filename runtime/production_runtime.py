"""
bot.py — RD6018 Ultimate Telegram Controller (Async Edition).
Дашборд: один автообновляемый message с графиком, метриками и кнопками.
"""
import asyncio
import inspect
import json
import logging
import math
import os
import re
import sys
import time

from datetime import datetime, timedelta
from typing import Dict, Optional, Union, Any

from aiogram import Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.filters import Command
from telegram.runtime import configure_commands, create_telegram_runtime, run_polling
from runtime.production_lifecycle import ProductionRuntimeLifecycle
from runtime.operator.off_conditions import OperatorOffConditions
from runtime.operator.pause_state import OperatorPauseState
from runtime.ui.telegram.analysis import ANALYSIS_CALLBACK_DATA, handle_dialog_delivery
from runtime.ui.telegram.charge import CHARGE_CALLBACK_DATA, handle_capacity_input
from runtime.ui.telegram.details import DETAILS_CALLBACK_DATA, HOME_CALLBACK_DATA
from runtime.ui.telegram.journal import JOURNAL_CALLBACK_DATA
from runtime.ui.telegram.off_conditions import OFF_CALLBACK_DATA
from runtime.ui.telegram.ingress import install_text_message_handler
from operator_managed_stop import STOP_CONFIRM_CALLBACK

from runtime.charge.strategy.exit_variables import (
    MIX_CC_DELTA_V_EXIT_V,
    MIX_CV_DELTA_I_EXIT_A,
)
from runtime.charge.persistence import (
    SESSION_FILE,
    paused_done_resume_is_authorized,
    restore_allows_auto_enable,
)
from runtime.charge.controller_state import (
    mark_link_unavailable,
    set_last_known_output_on,
    set_observed_device_setpoints,
)
from runtime.charge.strategy.main_guard_shadow import MainGuardShadow
from application.main_guard_runtime import run_main_guard_cycle
from application.charge_session_tick import run_charge_session_tick
from runtime.safety.variables import (
    HIGH_V_FAST_TIMEOUT_S,
    HIGH_V_THRESHOLD_V,
    MAX_STAGE_CURRENT_A,
    WATCHDOG_TIMEOUT_S,
)
from runtime.safety.live_protection import evaluate_live_protection
from charging_log import clear_event_logs, get_recent_events, log_checkpoint, log_event, log_stage_end, rotate_if_needed, trim_log_older_than_days
from production_controller import create_production_charge_host
from config import (
    ALLOWED_CHAT_IDS,
    NOTIFY_CHAT_ID,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_API_KEY,
    ENTITY_MAP,
    MIN_INPUT_VOLTAGE,
    TEMP_INT_PRECRITICAL,
    TG_TOKEN,
)
from application.execution_port import get_or_create_execution_port
from application.controller_action_execution import execute_controller_action_batch
from application.session_recovery_service import (
    SessionRecoveryObservation,
    SessionRecoveryService,
)
from application.operator_pause_use_case import toggle_operator_pause
from application.link_outage_use_case import transition_link_outage
from runtime.safety.voltage_variables import PB_AUTOMATIC_TARGET_CEILING_V
from database import add_record, cleanup_old_records, get_graph_data_with_temp, get_logs_data, get_raw_history, init_db
from hass_api import HassClient
from rd6018_telemetry import as_bool
from runtime.charge.evidence.temperature_source_journal import TemperatureSourceJournalObserver
from runtime.charge.evidence.charge_cycle_journal import record_charge_cycle_journal
from runtime.telemetry.source import observe_data_logger_cycle
from time_utils import format_time_user_tz
import html
from runtime.ui.components.hmi_values import (
    _md_to_html,
    _sanitize_telegram_html,
    format_electrical_data,
    format_temperature_data,
    format_status_data,
    format_operator_off_conditions,
    safe_html_format,
)
from runtime.ui.commands.validation import (
    _parse_off_command,
    _parse_two_numbers,
    _parse_three_values,
)
from runtime.ui.components.journal_format import _collapse_noisy_events, _remove_duplicate_events
from application.intents import OperatorIntent, OperatorIntentKind
from pb_domain import BatteryCondition, ChargeIntent

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rd6018")
# Keep third-party libraries at INFO; capture detailed RD6018 diagnostics only.
logger.setLevel(logging.DEBUG)

# Production chemistry never grants or denies authority from PSU input voltage.
# Vin remains telemetry/health context only.  Keep the historical symbol because
# the runtime still contains compatibility-shaped comparisons, but make those
# comparisons statically inert instead of mutating the module at composition time.
MIN_INPUT_VOLTAGE = float("-inf")
_v2_vin_psu_health_only = True

# Stable module-level compatibility values; semantic ownership lives in V3 VariableSpec modules.
DELTA_I_EXIT = float(MIX_CV_DELTA_I_EXIT_A.default)
DELTA_V_EXIT = float(MIX_CC_DELTA_V_EXIT_V.default)
HIGH_V_FAST_TIMEOUT = float(HIGH_V_FAST_TIMEOUT_S.default)
HIGH_V_THRESHOLD = float(HIGH_V_THRESHOLD_V.default)
MAX_STAGE_CURRENT = float(MAX_STAGE_CURRENT_A.default)
WATCHDOG_TIMEOUT = float(WATCHDOG_TIMEOUT_S.default)


def _canonical_bool(live: Dict[str, Any], key: str) -> bool:
    """Consume a canonical telemetry boolean without string reinterpretation."""
    return as_bool(live.get(key)) is True


# Compatibility exports: physical transport owns outage classification.
from runtime.physical.transports.error_policy import (
    _is_physical_transport_error,
    _is_recoverable_link_boundary_error,
)


def generate_chart(*args: Any, **kwargs: Any) -> Any:
    """Load the charting stack only when a chart is actually requested."""
    from graphing import generate_chart as _generate_chart

    return _generate_chart(*args, **kwargs)


class _DeferredHassClient:
    """A non-connecting handle used while the application module is imported.

    The production client is bound explicitly by ``initialize_runtime``.  Keeping
    this small handle preserves the existing composed V2 module surface without
    constructing a connector, loading physical configuration, or touching the
    network during import.
    """

    _VALUE_ATTRIBUTES = frozenset(
        {
            "base_url",
            "token",
            "_disable_tls_verify",
            "_session",
            "_physical_backend",
        }
    )

    def __init__(self) -> None:
        object.__setattr__(self, "_client", None)
        object.__setattr__(self, "_initializer", None)

    @property
    def is_bound(self) -> bool:
        return object.__getattribute__(self, "_client") is not None

    def bind(self, client: HassClient) -> None:
        if self.is_bound and object.__getattribute__(self, "_client") is not client:
            raise RuntimeError("HassClient is already bound to another runtime client")
        object.__setattr__(self, "_client", client)
        # Production keeps HassClient as transport/read adapter. The explicit
        # RuntimeSafetyGuard is the ExecutionPort owner and must only rebind its
        # raw transport methods here; it must not monkeypatch the live client.
        guard = globals().get("runtime_safety_guard")
        if guard is None:
            guard = object.__getattribute__(self, "__dict__").get("_runtime_safety_guard")
        bind_adapter = getattr(guard, "bind_adapter", None)
        if callable(bind_adapter):
            bind_adapter(client)

    def set_initializer(self, initializer: Any) -> None:
        object.__setattr__(self, "_initializer", initializer)

    def _ensure_bound(self) -> HassClient:
        client = object.__getattribute__(self, "_client")
        if client is None:
            initializer = object.__getattribute__(self, "_initializer")
            if callable(initializer):
                initializer()
                client = object.__getattribute__(self, "_client")
        if client is None:
            raise RuntimeError("HassClient runtime is not initialized")
        return client

    def __getattr__(self, name: str) -> Any:
        client = object.__getattribute__(self, "_client")
        if client is not None:
            return getattr(client, name)
        if name in self._VALUE_ATTRIBUTES:
            return None
        # Private composition markers are intentionally local to this deferred
        # handle.  They must not turn an import into a runtime initialization.
        if name.startswith("_"):
            return None

        async def deferred_call(*args: Any, **kwargs: Any) -> Any:
            bound = self._ensure_bound()
            result = getattr(bound, name)(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result

        return deferred_call



if not TG_TOKEN:
    raise ValueError(
        "TG_TOKEN не задан. Укажите TG_TOKEN или TELEGRAM_BOT_TOKEN в .env"
    )

_telegram_runtime = create_telegram_runtime(TG_TOKEN)
bot = _telegram_runtime.bot
dp = _telegram_runtime.dispatcher
router = _telegram_runtime.router

hass = _DeferredHassClient()

# Executor для блокирующих операций (DeepSeek API)
def _charge_notify(msg: str, critical: bool = True) -> None:
    """Отправка уведомления в Telegram. critical=True — после него дашборд только по кнопке ОБНОВИТЬ; critical=False — сразу шлём дашборд последним сообщением."""
    global last_chat_id, last_notification_signature, last_notification_at
    if NOTIFY_CHAT_ID is not None:
        last_chat_id = NOTIFY_CHAT_ID
    elif last_chat_id is None and len(ALLOWED_CHAT_IDS) == 1 and ALLOWED_CHAT_IDS[0] > 0:
        last_chat_id = ALLOWED_CHAT_IDS[0]
    if last_chat_id and msg:
        enriched = msg
        if last_live_context and "📊 Факт:" not in msg:
            enriched = f"{msg}\r\n\r\n{last_live_context}"
        signature = msg.strip()
        now = time.time()
        if signature == last_notification_signature and now - last_notification_at < 5:
            return
        last_notification_signature = signature
        last_notification_at = now
        recipient_chat_id = last_chat_id
        recipient_user_id = last_user_id
        asyncio.create_task(
            _send_notify_safe(enriched, critical, recipient_chat_id, recipient_user_id)
        )


async def _send_notify_safe(
    msg: str, critical: bool = True, recipient_chat_id: Optional[int] = None,
    recipient_user_id: Optional[int] = None,
) -> None:
    # Legacy direct callers may omit the recipient. Scheduled notifications
    # always pass the ID captured before creating the background task.
    if recipient_chat_id is None:
        recipient_chat_id = last_chat_id
    try:
        safe_msg = msg
        if not any(tag in msg for tag in ['<b>', '<i>', '<code>']):
            safe_msg = html.escape(msg)
        safe_msg = safe_msg.replace('<hr>', '___________________').replace('<hr/>', '___________________').replace('<hr />', '___________________')
        safe_msg = safe_msg.replace('<br>', '\r\n').replace('<br/>', '\r\n').replace('<br />', '\r\n')
        await bot.send_message(recipient_chat_id, safe_msg, parse_mode=ParseMode.HTML)
        # The already installed PanelLast notification owner decides whether
        # and when to restore the one panel. Never publish a legacy text panel
        # from the notification transport.
    except Exception as ex:
        logger.error("charge notify failed: %s", ex)
        try:
            clean_msg = html.escape(msg).replace('<hr>', '---').replace('<hr/>', '---').replace('<hr />', '---')
            await bot.send_message(recipient_chat_id, clean_msg)
        except Exception as ex2:
            logger.error("fallback notify also failed: %s", ex2)


charge_controller = create_production_charge_host(hass, notify_cb=_charge_notify)
_main_guard_shadow = MainGuardShadow()


def initialize_runtime() -> None:
    """Bind the physical client at application startup, never at import time."""
    if hass.is_bound:
        return
    hass.bind(HassClient.from_physical_config())


hass.set_initializer(initialize_runtime)


def _restore_allows_auto_enable(controller: Any) -> bool:
    "Startup lifecycle compatibility; canonical policy stays in persistence."
    return restore_allows_auto_enable(controller)


def _is_chat_allowed(chat_id: int) -> bool:
    """Проверка доступа по ALLOWED_CHAT_IDS. Пустой список = доступ у всех."""
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS


async def _check_chat_and_respond(event: Union[Message, CallbackQuery]) -> bool:
    """
    Вернуть True, если чат разрешён. Иначе отправить «Доступ запрещён» и вернуть False.
    Вызывать в начале обработчиков.
    """
    chat_id = event.chat.id if isinstance(event, Message) else event.message.chat.id
    if _is_chat_allowed(chat_id):
        return True
    try:
        if isinstance(event, Message):
            await event.answer("Доступ запрещён.")
        else:
            await event.answer("Доступ запрещён.", show_alert=True)
    except Exception:
        pass
    return False


user_dashboard: Dict[int, int] = {}
chat_dashboard: Dict[int, int] = {}
user_chart_range: Dict[int, str] = {}
_action_debounce_until: Dict[str, float] = {}
last_chat_id: Optional[int] = None
last_user_id: Optional[int] = None
last_live_context: str = ""
last_notification_signature: str = ""
last_notification_at: float = 0.0
last_charge_alert_at: Optional[datetime] = None
last_idle_alert_at: Optional[datetime] = None
zero_current_since: Optional[datetime] = None
CHARGE_ALERT_COOLDOWN = timedelta(hours=1)
# В режиме хранения (V < 14В) алерт «заряд завершён» не чаще раза в час
STORAGE_ALERT_COOLDOWN = timedelta(hours=1)
IDLE_ALERT_COOLDOWN = timedelta(hours=1)
ZERO_CURRENT_THRESHOLD_MINUTES = 30
awaiting_ah: Dict[int, str] = {}
# FSM для ручного режима
last_ha_ok_time: float = 0.0
link_lost_alert_sent: bool = False  # флаг-блокировка однократного уведомления о потере связи
link_failure_streak: int = 0
LINK_FAILURE_NOTIFY_THRESHOLD = 3
soft_watchdog_outage_reported: bool = False
# Last-good telemetry can precede a detected disconnect by one 30s poll.
# Allow the full 300s loss window plus that observation margin; the
# independent 900s edge safety lease retains physical authority.
SOFT_WATCHDOG_TIMEOUT = 6 * 60
MIN_START_TEMP = 10.0  # °C — заряд не начинаем, если внешний датчик ниже
last_checkpoint_time: float = 0.0

MANUAL_OFF_FILE = "manual_off_state.json"
_operator_off_conditions = OperatorOffConditions()
OPERATOR_PAUSE_FILE = "operator_pause_state.json"
_operator_pause_state = OperatorPauseState()

CHART_RANGE_30M = "30m"
CHART_RANGE_2H = "2h"
CHART_RANGE_SESSION = "session"
CHART_RANGE_DEFAULT = CHART_RANGE_2H
CHART_RANGE_VALUES = {CHART_RANGE_30M, CHART_RANGE_2H, CHART_RANGE_SESSION}


def _operator_pause_active() -> bool:
    return _operator_pause_state.active()


def _save_operator_pause_state() -> bool:
    return _operator_pause_state.save(OPERATOR_PAUSE_FILE)


def _load_operator_pause_state() -> None:
    loaded = OperatorPauseState.load(OPERATOR_PAUSE_FILE)
    _operator_pause_state.started_at = loaded.started_at
    if _operator_pause_state.active():
        logger.info("Operator pause restored from %s", OPERATOR_PAUSE_FILE)


def _clear_operator_pause() -> bool:
    return _operator_pause_state.clear(OPERATOR_PAUSE_FILE)


def _save_manual_off_state() -> None:
    _operator_off_conditions.save(MANUAL_OFF_FILE)


def _load_manual_off_state() -> None:
    _operator_off_conditions.load(MANUAL_OFF_FILE)


def _clear_manual_off() -> None:
    _operator_off_conditions.clear(MANUAL_OFF_FILE)


def _has_manual_off_condition() -> bool:
    return _operator_off_conditions.has_condition()


def _format_manual_off_for_dashboard() -> str:
    """Строка для дашборда: статус принудительного выключения и остаток времени до выкл."""
    if not _has_manual_off_condition():
        return ""
    now_s = time.time() if _operator_off_conditions.time_sec is not None else 0.0
    return format_operator_off_conditions(_operator_off_conditions, now_s=now_s)


def _stage_label(raw_stage: str, short: bool = True) -> str:
    """Compatibility wrapper for the UI-owned stage label catalog."""
    from runtime.ui.components.hmi_values import stage_label

    return stage_label(raw_stage, short=short)


def _is_action_allowed(user_id: int, action: str, cooldown_sec: float = 1.2) -> bool:
    """Compatibility delegate for operator UI command debounce."""
    from runtime.ui.commands.validation import allow_operator_action

    return allow_operator_action(
        _action_debounce_until, user_id, action,
        cooldown_sec=cooldown_sec, now_s=time.time(),
    )


def _chart_range_for_user(user_id: int) -> str:
    from runtime.ui.components.hmi_navigation_keyboards import chart_range_for_user

    return chart_range_for_user(sys.modules[__name__], user_id)


def _chart_label(mode: str) -> str:
    from runtime.ui.components.hmi_navigation_keyboards import chart_label

    return chart_label(sys.modules[__name__], mode)


def _chart_query_params(user_id: int) -> tuple:
    from runtime.ui.components.hmi_navigation_keyboards import chart_query_params

    return chart_query_params(sys.modules[__name__], user_id)

def _build_dashboard_keyboard(
    is_on: bool, user_id: int, *, back_to_dashboard: bool = False,
) -> InlineKeyboardMarkup:
    """Compatibility wrapper for the canonical operator dashboard keyboard."""
    from ui_polish import build_operator_dashboard_keyboard

    return build_operator_dashboard_keyboard(
        sys.modules[__name__],
        is_on,
        user_id,
        back_to_dashboard=back_to_dashboard,
    )

def _apply_manual_off_preset(preset: str) -> str:
    """Apply one named operator OFF preset through the canonical state owner."""
    try:
        text = _operator_off_conditions.apply_preset(preset, now_s=time.time())
    except ValueError:
        _save_manual_off_state()
        raise
    _save_manual_off_state()
    return text


def _charge_modes_text() -> str:
    """Compatibility wrapper for the canonical production mode copy."""
    from production_bootstrap import _operator_modes_text

    return _operator_modes_text()


def _build_charge_modes_keyboard() -> InlineKeyboardMarkup:
    """Compatibility wrapper for the canonical production mode keyboard."""
    from production_bootstrap import _operator_modes_keyboard

    return _operator_modes_keyboard()

def _build_trend_summary(times: list, voltages: list, currents: list) -> str:
    from integrations.ai.runtime import trend
    return trend(times, voltages, currents)

def _safe_float(val, default: float = 0.0) -> float:
    if val is None or val in ("unknown", "unavailable", ""):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _cap_current(value: float) -> float:
    return min(MAX_STAGE_CURRENT, max(0.1, float(value)))


_temperature_source_observer = TemperatureSourceJournalObserver()


def _log_temperature_source_if_changed(live, *, stage, voltage, current, temperature, ah, session_id=None):
    """Observational, never a charging/safety decision."""
    _temperature_source_observer.record(
        live, stage=stage, voltage=voltage, current=current,
        temperature=temperature, ah=ah, session_id=session_id,
        log_event=log_event,
    )


def _runtime_execution_port():
    """Return the one app-scoped physical execution owner for this runtime module."""
    return get_or_create_execution_port(sys.modules[__name__])


async def _apply_controller_output_actions(
    actions: Dict[str, Any], live: Dict[str, Any], *, battery_v: float,
    current: float, temp: float, ah: float,
) -> Optional[bool]:
    """Execute V/I/Output actions through the canonical application owner."""
    return await execute_controller_action_batch(
        actions, live, execution_port=_runtime_execution_port(),
        controller=charge_controller, battery_v=battery_v, current=current,
        temp=temp, ah=ah, max_stage_current_a=MAX_STAGE_CURRENT,
        recipe_voltage_ceiling_v=float(PB_AUTOMATIC_TARGET_CEILING_V.default),
        notify=_charge_notify, log_event=log_event, logger=logger,
    )


async def _hard_stop_charge(clear_session: bool = True) -> None:
    """Finish AUTO after verified OFF."""
    if not await _runtime_execution_port().request_verified_off():
        raise RuntimeError("STOP refused: physical Output OFF not verified")
    charge_controller.stop(clear_session=clear_session)
    _clear_operator_pause()


from runtime.startup_recovery import (
    UPTIME_AS_CHARGE_TIMER_MAX_SEC,
    UPTIME_SYNC_MAX_DRIFT_SEC,
)


def _parse_uptime_to_elapsed_sec(uptime_raw) -> Optional[float]:
    from runtime.startup_recovery import parse_uptime_to_elapsed_sec

    return parse_uptime_to_elapsed_sec(uptime_raw, now_s=time.time())


def _sync_total_start_from_uptime(
    charge_controller,
    live: Optional[Dict],
    *,
    max_drift_sec: int = UPTIME_SYNC_MAX_DRIFT_SEC,
    allow_init: bool = False,
) -> bool:
    from runtime.startup_recovery import sync_total_start_from_uptime

    return sync_total_start_from_uptime(
        charge_controller,
        live,
        max_drift_sec=max_drift_sec,
        allow_init=allow_init,
        now_s=time.time(),
    )


def _apply_restore_time_corrections(charge_controller, live: Optional[Dict]) -> None:
    "Startup lifecycle compatibility; time correction stays in startup recovery."
    from runtime.startup_recovery import apply_restore_time_corrections

    apply_restore_time_corrections(charge_controller, live, now_s=time.time())


_last_restore_time: float = 0.0
_script_start_time: float = time.time()




def format_log_event(event_line: str) -> str:
    """Compatibility wrapper for the canonical UI journal formatter."""
    from runtime.ui.components.journal_format import format_journal_event

    return format_journal_event(event_line)

def _retire_graph_tracking_for_message(chat_id: int, user_id: int, message_id: int) -> None:
    """Compatibility delegate for legacy graph-to-log transitions."""
    from runtime.ui.telegram.panel_lifecycle import retire_graph_tracking_for_message

    retire_graph_tracking_for_message(sys.modules[__name__], chat_id, user_id, message_id)


async def _safe_output_on() -> bool:
    """Безопасно получить текущий статус выхода для построения клавиатуры."""
    try:
        live = await hass.get_all_live()
        return str(live.get("switch", "")).lower() == "on"
    except Exception:
        return False


async def _operator_pause_toggle(call: Any) -> str:
    """Pause/resume the active charge without converting it into a stop."""
    global last_chat_id, last_user_id

    user_id = call.from_user.id if call.from_user else 0
    if not _is_action_allowed(user_id, "operator_pause_toggle", cooldown_sec=1.5):
        return "Команда уже выполняется..."
    last_chat_id = call.message.chat.id
    last_user_id = user_id
    return await toggle_operator_pause(sys.modules[__name__])


async def _build_ai_analysis_text() -> str:
    from integrations.ai.runtime import analysis
    return await analysis(sys.modules[__name__])

def _build_dashboard_blocks(live: Dict[str, Any]) -> tuple:
    """Compatibility wrapper for extracted legacy dashboard projection."""
    from runtime.ui.components.hmi_values import build_legacy_dashboard_blocks

    return build_legacy_dashboard_blocks(
        charge_controller,
        live,
        canonical_bool=_canonical_bool,
        stage_label=_stage_label,
        progress_line=_format_stage_progress_line,
        delta_i_exit=DELTA_I_EXIT,
        delta_v_exit=DELTA_V_EXIT,
    )

def _strip_html_tags(text: str) -> str:
    """Убрать HTML-теги и нормализовать пробелы для компактного текста."""
    plain = re.sub(r"<[^>]+>", "", text or "")
    plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", plain).strip()


from runtime.ui.components.stage_duration import (
    format_eta_compact as _format_eta_compact,
    format_seconds_compact as _format_seconds_compact,
)


def _format_stage_progress_line(live: Dict[str, Any]) -> str:
    """Compatibility wrapper for the extracted read-only UI projection."""
    from runtime.ui.components.hmi_auto_stage_progress import (
        format_stage_progress_line,
    )

    return format_stage_progress_line(
        charge_controller,
        live,
        stage_snapshot=_safe_stage_snapshot,
    )

def _safe_stage_snapshot(temp_ext: Optional[float]) -> Dict[str, Any]:
    """Compatibility wrapper for the explicit read-only stage projection."""
    from application.operator_snapshot_provider import build_safe_stage_snapshot

    return build_safe_stage_snapshot(
        charge_controller,
        temp_ext,
        on_error=lambda exc: logger.warning(
            "safe stage snapshot fallback: %s", exc
        ),
    )

def _compact_dashboard_caption(
    live: Dict[str, Any], chart_mode: str, mode: str, idle_warning: str,
) -> str:
    """Compatibility fallback to the canonical operator panel renderer."""
    del chart_mode, mode, idle_warning
    from operator_hmi import build_operator_hmi_state
    from runtime.ui.components.hmi_panel_text import render_operator_panel

    return render_operator_panel(
        build_operator_hmi_state(sys.modules[__name__], live)
    )

async def charge_monitor() -> None:
    """Compatibility fallback to the managed-aware production monitor."""
    from production_bootstrap import _managed_aware_charge_monitor_poll

    while True:
        await asyncio.sleep(15 * 60)
        try:
            await _managed_aware_charge_monitor_poll(sys.modules[__name__])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("charge_monitor (network/error): %s", exc)
            await asyncio.sleep(60)

async def data_logger() -> None:
    """Фоновая задача: опрос HA каждые 30с, сохранение в DB, ChargeController tick, проверка безопасности."""
    global last_chat_id, last_ha_ok_time, last_checkpoint_time, link_lost_alert_sent, link_failure_streak, last_live_context, soft_watchdog_outage_reported
    last_cleanup_time = 0.0
    
    while True:
        # A dead command path cannot be made safer by sending the same STOP
        # repeatedly. Keep the charge session intact and let the independent
        # edge lease remain the blind-operation backstop until readback returns.
        try:
            safety_owner = globals().get("runtime_safety_guard")
            live = await (
                safety_owner.get_all_live()
                if safety_owner is not None
                else hass.get_all_live()
            )
        except Exception as ex:
            if _is_physical_transport_error(ex):
                transition = transition_link_outage(
                    category="initial_read",
                    recoverable_link_error=True,
                    failure_streak=link_failure_streak,
                    alert_sent=link_lost_alert_sent,
                    last_known_output_on=charge_controller._last_known_output_on,
                    session_active=charge_controller.is_active,
                    notification_threshold=LINK_FAILURE_NOTIFY_THRESHOLD,
                )
                link_failure_streak = transition.failure_streak
                if transition.mark_unavailable:
                    mark_link_unavailable(charge_controller, lost_at_s=time.time())
                if transition.notify_repeated_outage:
                    _charge_notify("🚨 Связь с RD6018 не восстановилась после "
                                   f"{link_failure_streak} попыток. Аппаратный lease остаётся последним рубежом.")
                link_lost_alert_sent = transition.alert_sent
                logger.warning(
                    "ESPHome transport outage #%d; no host STOP sent: %s",
                    link_failure_streak,
                    ex,
                )
            else:
                logger.error("data_logger read failed: %s", ex)
            await asyncio.sleep(30)
            continue

        if (
            "_native_link_outage_since" in live
            or live.get("_managed_telemetry_recovery_pending") is True
        ):
            # Reconnect or delayed ordinary/transition callback evidence.
            # Defer controller decisions without treating partial data as a
            # healthy heartbeat; the existing 300s guard owns the timeout.
            logger.info("Native link recovering; charge controller tick deferred")
            await asyncio.sleep(30)
            continue

        last_ha_ok_time = time.time()
        link_failure_streak = 0
        link_lost_alert_sent = False
        soft_watchdog_outage_reported = False
        try:
            manual_manager = globals().get("manual_session_manager")
            manual_request = getattr(manual_manager, "request", None)
            manual_active = bool(getattr(manual_manager, "is_active", False) and manual_request)
            observation = observe_data_logger_cycle(
                live,
                manual_active=manual_active,
                manual_mode_label=(
                    getattr(manual_request, "operation_mode_label", "Ручной")
                    if manual_active else None
                ),
            )
            battery_v = observation.battery_voltage_v
            output_v = observation.output_voltage_v
            i = observation.current_a
            p = observation.power_w
            temp_ext = observation.external_temperature_raw
            t = observation.external_temperature_c
            ah = observation.amp_hours
            try:
                _log_temperature_source_if_changed(
                    live, stage=charge_controller.current_stage,
                    voltage=battery_v, current=i, temperature=temp_ext, ah=ah,
                    session_id=getattr(charge_controller, "_v2_trace_session_id", None),
                )
            except Exception as exc:
                # Observability is best-effort. It must not interrupt the
                # established safety/charge control path.
                logger.warning("TEMP_SOURCE journal unavailable: %s", type(exc).__name__)
            is_cv = observation.is_cv
            is_cc = observation.is_cc
            output_switch = observation.output_switch
            output_on = observation.output_on
            input_voltage = observation.input_voltage_v
            temp_int = observation.internal_temperature_c
            last_live_context = observation.live_context
            
            # v2.5 Умный watchdog: обновляем последнее известное состояние выхода
            if output_switch is not None and str(output_switch).lower() not in ("unavailable", "unknown", ""):
                set_last_known_output_on(
                    charge_controller,
                    output_switch is True or str(output_switch).lower() == "on",
                )
            # Фактические уставки прибора — для сохранения в сессию (восстановление после перезапуска/потери связи)
            set_v = observation.set_voltage_v
            set_i = observation.set_current_a
            if set_v > 0 and set_i > 0:
                set_observed_device_setpoints(
                    charge_controller,
                    voltage_v=set_v,
                    current_a=set_i,
                )
            
            # Синхронизация с прибором только при малом расхождении (чтобы не затирать новую сессию)
            _sync_total_start_from_uptime(
                charge_controller,
                live,
                max_drift_sec=UPTIME_SYNC_MAX_DRIFT_SEC,
                allow_init=False,
            )
            
            # Protection policy owns the trip decision; this runtime only
            # dispatches the established journal, notification and OFF effects.
            protection_decision = evaluate_live_protection(
                live=live,
                charge_active=charge_controller.is_active,
                output_on=output_on,
                internal_temperature_c=temp_int,
                precritical_temperature_c=TEMP_INT_PRECRITICAL,
            )
            if "OPP_TRIGGERED" in protection_decision.triggers:
                log_event(
                    charge_controller.current_stage, battery_v, i, t, ah,
                    "OPP_TRIGGERED",
                )
                _charge_notify("🛑 Сработала аппаратная защита мощности. Выход выключен.")
            if "OPP_TRIGGERED" in protection_decision.triggers:
                await _hard_stop_charge()

            if "TEMP_INT_PRECRITICAL" in protection_decision.triggers:
                log_event(
                    charge_controller.current_stage,
                    battery_v,
                    i,
                    t,
                    ah,
                    f"TEMP_INT_PRECRITICAL_{temp_int:.0f}C",
                )
                _charge_notify(
                    f"🌡 Температура блока {temp_int:.0f}°C ≥ {TEMP_INT_PRECRITICAL:.0f}°C. "
                    "Выход выключен для защиты БП."
                )
                await _hard_stop_charge()

            # Команда off: выключить по напряжению / току / таймеру (защиты не отключаются)
            if output_on and _has_manual_off_condition():
                now_ts = time.time()
                off_reason = _operator_off_conditions.evaluate_reason(
                    battery_v, i, now_s=now_ts, reach_eps=OFF_REACH_EPS
                )
                if off_reason:
                    log_event(charge_controller.current_stage, battery_v, i, t, ah, f"MANUAL_OFF_{off_reason[:30]}")
                    _charge_notify(f"⏹ Выключено по условию: {off_reason}")
                    await _hard_stop_charge()
                    _clear_manual_off()
            
            await add_record(battery_v, i, p, t)

            # Explicit operator pause: keep telemetry/safety monitoring alive, but
            # never let recovery, controller ticks or link restoration re-energize
            # the Output until the operator explicitly resumes the session.
            if _operator_pause_active():
                if output_on:
                    logger.warning("Operator pause found Output ON; forcing verified OFF")
                    await _runtime_execution_port().request_verified_off()
                await asyncio.sleep(30)
                continue

            # All normal restore/state changes and subsequent tick/action
            # share the same app owner. Verified emergency OFF remains outside.
            async with _runtime_execution_port()._guard_owner_lock:
                recovery_cycle = await SessionRecoveryService.run_cycle(
                    observation=SessionRecoveryObservation(
                        output_on=output_on,
                        current_a=i,
                        temperature_available=(
                            temp_ext is not None
                            and temp_ext not in ("unavailable", "unknown", "")
                        ),
                        battery_voltage_v=battery_v,
                        temperature_c=t,
                        amp_hours=ah,
                        is_cv=is_cv,
                        is_cc=is_cc,
                        input_voltage_v=input_voltage,
                    ),
                    controller=charge_controller,
                    live=live,
                    session_path=SESSION_FILE,
                    minimum_input_voltage_v=MIN_INPUT_VOLTAGE,
                    execution_port_getter=_runtime_execution_port,
                    cap_current=_cap_current,
                )
                output_on = recovery_cycle.output_on
                if recovery_cycle.last_checkpoint_time is not None:
                    last_checkpoint_time = recovery_cycle.last_checkpoint_time
                for effect in recovery_cycle.effects:
                    if effect.kind == "event":
                        log_event(
                            effect.event_stage,
                            effect.event_voltage_v,
                            effect.event_current_a,
                            effect.event_temperature_c,
                            effect.event_ah,
                            effect.message,
                        )
                    elif effect.kind == "notify":
                        if effect.critical is None:
                            _charge_notify(effect.message)
                        else:
                            _charge_notify(effect.message, critical=effect.critical)
                    else:
                        log_method = getattr(logger, effect.kind)
                        if not effect.log_arguments:
                            log_method(effect.message)
                        else:
                            log_method(effect.message, *effect.log_arguments)

                now_ts = time.time()
                # Hold the same app-wide normal execution owner from the
                # controller decision/session checkpoint through the resulting
                # physical action. Emergency verified OFF remains independent.
                async with _runtime_execution_port()._guard_owner_lock:
                    prev_stage = charge_controller.current_stage
                    outcome = await run_main_guard_cycle(
                        app=sys.modules[__name__],
                        port=_runtime_execution_port(),
                        controller=charge_controller,
                        shadow=_main_guard_shadow,
                        live=live,
                        session_path=SESSION_FILE,
                        now_epoch_s=now_ts,
                        manual_active=manual_active,
                        manual_off_condition=_has_manual_off_condition(),
                    )
                    if outcome is not None:
                        if outcome.verified:
                            logger.info(
                                "MAIN Guard Iset reduced and journaled: %.2f A",
                                outcome.guard.hardware_limit_a,
                            )
                        else:
                            logger.warning(
                                "MAIN Guard reduction not verified: %s; OFF=%s; diagnostic=%s",
                                outcome.reason, outcome.off_confirmed,
                                outcome.diagnostic,
                            )
                    actions = (await run_charge_session_tick(
                        charge_controller,
                        battery_v, i, temp_ext, is_cv, ah, output_switch,
                        manual_off_active=_has_manual_off_condition(),
                        is_cc=is_cc,
                        manual_active=manual_active,
                    ) if _runtime_execution_port().session_recovery_guard.may_run_automatic_control() else {})
                    if actions.get("notify"):
                        _charge_notify(str(actions["notify"]))
                    last_checkpoint_time = record_charge_cycle_journal(
                        previous_stage=prev_stage,
                        current_stage=charge_controller.current_stage,
                        actions=actions,
                        charge_active=charge_controller.is_active,
                        last_checkpoint_time=last_checkpoint_time,
                        now_s=now_ts,
                        voltage_v=battery_v,
                        current_a=i,
                        temperature_c=t,
                        ah=ah,
                        live=live,
                        signal=getattr(charge_controller, "_v2_session_signal_context", None),
                        session_id=getattr(charge_controller, "_v2_trace_session_id", None),
                        hold_started_at=getattr(charge_controller, "finish_timer_start", None),
                        mix_stage=charge_controller.STAGE_MIX,
                        max_age_s=float(WATCHDOG_TIMEOUT_S.default),
                        log_event=log_event,
                        log_stage_end=log_stage_end,
                        log_checkpoint=log_checkpoint,
                        warn=logger.warning,
                    )
                    
                    # Очистка БД и журнала событий каждые 24 часа (записи старше 30 дней)
                    if now_ts - last_cleanup_time >= 86400:  # 24 часа
                        await cleanup_old_records()
                        try:
                            rotate_if_needed()
                            trim_log_older_than_days(30)
                        except Exception as ex:
                            logger.warning("trim_log_older_than_days: %s", ex)
                        last_cleanup_time = now_ts

                    if actions.get("emergency_stop"):
                        await _runtime_execution_port().request_emergency_off()
                        if actions.get("full_reset"):
                            charge_controller.full_reset()
                        # иначе контроллер уже сделал stop(clear_session=False) — сессия сохранена для restore при возврате связи
                    elif charge_controller.is_active:
                        await _apply_controller_output_actions(
                            actions,
                            live,
                            battery_v=battery_v,
                            current=i,
                            temp=t,
                            ah=ah,
                        )

        except Exception as ex:
            err_str = str(ex).lower()
            recoverable_link_error = _is_recoverable_link_boundary_error(ex)
            transition = transition_link_outage(
                category=("cycle_readback" if recoverable_link_error else "unexpected_cycle"),
                recoverable_link_error=recoverable_link_error,
                failure_streak=link_failure_streak,
                alert_sent=link_lost_alert_sent,
                last_known_output_on=charge_controller._last_known_output_on,
                session_active=charge_controller.is_active,
                notification_threshold=LINK_FAILURE_NOTIFY_THRESHOLD,
            )
            link_failure_streak = transition.failure_streak
            if transition.mark_unavailable:
                mark_link_unavailable(charge_controller, lost_at_s=time.time())
            if recoverable_link_error:
                if transition.notify_repeated_outage:
                    _charge_notify("🚨 Связь с RD6018 не восстановилась после "
                                   f"{link_failure_streak} попыток. Аппаратный lease остаётся последним рубежом.")
                link_lost_alert_sent = transition.alert_sent
                logger.warning(
                    "ESPHome transport outage during cycle #%d; no host STOP sent: %s",
                    link_failure_streak,
                    ex,
                )
                await asyncio.sleep(30)
                continue
            if "name resolution" in err_str or "dns" in err_str or "nodename" in err_str:
                logger.warning("data_logger (DNS/сеть): %s", ex)
            else:
                logger.error("data_logger: %s", ex)
            
            # v2.5 Умный watchdog: поведение зависит от последнего состояния выхода
            output_was_on = charge_controller._last_known_output_on

            if not output_was_on:
                # Выход был выключен — тихий переход в IDLE, без уведомлений
                if transition.stop_idle_session:
                    charge_controller.stop(clear_session=False)
                    logger.info("Link lost with output OFF: quiet transition to IDLE")
            else:
                # Выход был включён — однократное уведомление и аварийное отключение
                if transition.notify_active_charge_loss:
                    _charge_notify("🚨 Связь потеряна во время активного заряда!")
                    link_lost_alert_sent = transition.alert_sent
                    logger.critical("Link lost during active charge: emergency shutdown")

                if transition.request_emergency_off:
                    try:
                        # The existing ExecutionPort remains the only path
                        # for unexpected-cycle emergency containment.
                        off_confirmed = await _runtime_execution_port().request_emergency_off()
                        if not off_confirmed:
                            raise RuntimeError('emergency OFF was not verified')
                    except Exception as off_exc:
                        logger.exception('LINK_LOST_EMERGENCY_OFF_FAILED; session retained: %s', off_exc)
                        await asyncio.sleep(30)
                        continue

                    if charge_controller.is_active:
                        charge_controller.stop(clear_session=False)
                        log_event(
                            "EMERGENCY",
                            0.0,
                            0.0,
                            0.0,
                            0.0,
                            "LINK_LOST_DURING_CHARGE",
                        )
        await asyncio.sleep(30)


def __getattr__(name: str):
    """Lazy compatibility exports retained for existing AI callers."""
    if name in {"ask_deepseek", "format_ai_snapshot", "format_recent_events", "AI_CONSULTANT_SYSTEM_PROMPT"}:
        from integrations import ai
        return getattr(ai, name)
    raise AttributeError(name)


# --- Handlers ---


async def get_ai_context() -> str:
    from integrations.ai.runtime import context
    return await context(sys.modules[__name__])


async def get_ai_context_dict() -> Dict[str, Any]:
    from integrations.ai.runtime import context_dict
    return await context_dict(sys.modules[__name__])


async def get_current_context_for_llm() -> str:
    """Compatibility alias for the optional AI context integration."""
    return await get_ai_context()


# Порог «достигли» для выключения по V или I (с любой стороны)
OFF_REACH_EPS = 0.02


def _record_text_ingress_chat(chat_id: int) -> None:
    global last_chat_id
    last_chat_id = chat_id


text_message_handler = install_text_message_handler(
    router,
    check_chat=lambda message: _check_chat_and_respond(message),
    awaiting_capacity=awaiting_ah,
    parse_off_command=lambda text: _parse_off_command(text),
    update_condition=_operator_off_conditions.update_from_document,
    save_condition=_save_manual_off_state,
    clear_condition=_clear_manual_off,
    set_last_chat=_record_text_ingress_chat,
    get_capacity_handler=lambda: globals()["handle_ah_input"],
    get_dialog_handler=lambda: globals()["handle_dialog_mode"],
    parse_mode=ParseMode.HTML,
)


async def handle_ah_input(message: Message, profile: str, user_id: int) -> None:
    """Обработка ввода ёмкости АКБ после выбора профиля."""
    route = globals().get("_v3_production_start_route")
    from production_bot_ui import format_start_feedback
    await handle_capacity_input(
        message,
        profile,
        user_id,
        route=route,
        pending_intent=_pending_intent,
        parse_mode=ParseMode.HTML,
        logger=logger,
        format_start_feedback=format_start_feedback,
    )


async def handle_dialog_mode(message: Message) -> None:
    from integrations.ai import AI_CONSULTANT_SYSTEM_PROMPT, ask_deepseek

    namespace = globals()
    await handle_dialog_delivery(
        message,
        ai_available=bool(DEEPSEEK_API_KEY),
        get_context=namespace["get_ai_context"],
        ask=namespace.get("ask_deepseek", ask_deepseek),
        system_prompt=namespace.get("AI_CONSULTANT_SYSTEM_PROMPT", AI_CONSULTANT_SYSTEM_PROMPT),
        sanitize=namespace["_sanitize_telegram_html"],
        parse_mode=ParseMode.HTML,
        logger=logger,
    )







_lifecycle = ProductionRuntimeLifecycle(sys.modules[__name__], _telegram_runtime)


async def on_shutdown(dispatcher: Dispatcher) -> None:
    await _lifecycle.on_shutdown(dispatcher)


async def main() -> None:
    await _lifecycle.run()


if __name__ == "__main__":
    asyncio.run(main())


