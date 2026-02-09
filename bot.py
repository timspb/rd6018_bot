import datetime
import io
import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

# Use non-interactive backend for servers/headless systems
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import requests
import urllib3
from dotenv import load_dotenv
from openai import OpenAI
import telebot
from telebot import types

# Disable SSL warnings for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables from .env
load_dotenv()

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
LOG_FILE = "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("rd6018_bot")

# -----------------------------------------------------------------------------
# Constants / Entity IDs
# -----------------------------------------------------------------------------
HA_URL = os.getenv("HA_URL", "").rstrip("/")
HA_TOKEN = os.getenv("HA_TOKEN", "")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner")

# RD6018 entities
SENSOR_VOLTAGE = "sensor.rd_6018_output_voltage"
SENSOR_CURRENT = "sensor.rd_6018_output_current"
SENSOR_POWER = "sensor.rd_6018_output_power"
SENSOR_TEMP_INTERNAL = "sensor.rd_6018_temperature"
SENSOR_TEMP_EXTERNAL = "sensor.rd_6018_temperature_external"
SENSOR_CAPACITY_AH = "sensor.rd_6018_battery_charge"
SENSOR_ENERGY_WH = "sensor.rd_6018_battery_energy"

NUMBER_SET_VOLTAGE = "number.rd_6018_output_voltage"
NUMBER_SET_CURRENT = "number.rd_6018_output_current"
SWITCH_OUTPUT = "switch.rd_6018_output"

BINARY_MODE_CC = "binary_sensor.rd_6018_constant_current"
BINARY_MODE_CV = "binary_sensor.rd_6018_constant_voltage"
BINARY_OVP = "binary_sensor.rd_6018_over_voltage_protection"
BINARY_OCP = "binary_sensor.rd_6018_over_current_protection"

ALL_RELEVANT_ENTITIES = [
    SENSOR_VOLTAGE,
    SENSOR_CURRENT,
    SENSOR_POWER,
    SENSOR_TEMP_INTERNAL,
    SENSOR_TEMP_EXTERNAL,
    SENSOR_CAPACITY_AH,
    SENSOR_ENERGY_WH,
    NUMBER_SET_VOLTAGE,
    NUMBER_SET_CURRENT,
    SWITCH_OUTPUT,
    BINARY_MODE_CC,
    BINARY_MODE_CV,
    BINARY_OVP,
    BINARY_OCP,
]

# -----------------------------------------------------------------------------
# Utility functions
# -----------------------------------------------------------------------------
def parse_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(str(value))
    except (ValueError, TypeError):
        return None


def estimate_soh_from_ocv(ocv: Optional[float]) -> Optional[int]:
    """
    Very rough SOH/SoC estimate based on 12V lead-acid OCV.
    11.8V ~ 0%, 12.8V ~ 100%.
    """
    if ocv is None:
        return None
    # Clamp within 11.8–12.8V
    v = max(11.8, min(12.8, ocv))
    soh = int((v - 11.8) / (12.8 - 11.8) * 100)
    return max(0, min(100, soh))


# -----------------------------------------------------------------------------
# Home Assistant Service (Singleton)
# -----------------------------------------------------------------------------
class HAService:
    """
    Singleton wrapper around Home Assistant REST API.
    Uses a shared requests.Session and 3s TTL cache.
    """

    _instance: Optional["HAService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "HAService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self.base_url: str = HA_URL
        self.token: str = HA_TOKEN
        self.session = requests.Session()
        self.session.verify = False

        if not self.base_url or not self.token:
            logger.warning("HA_URL or HA_TOKEN not configured; HAService limited.")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.session.headers.update(headers)

        self._cache_data: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 3.0  # seconds

        self._initialized = True

    # Internal helpers
    def _extract_rd6018_data(self, states: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_id: Dict[str, Dict[str, Any]] = {
            s.get("entity_id"): s for s in states if isinstance(s, dict)
        }

        def state_float(entity_id: str) -> Optional[float]:
            s = by_id.get(entity_id)
            if not s:
                return None
            return parse_float(s.get("state"))

        def state_bool(entity_id: str) -> Optional[bool]:
            s = by_id.get(entity_id)
            if not s:
                return None
            st = str(s.get("state", "")).lower()
            if st in {"on", "off"}:
                return st == "on"
            return None

        data: Dict[str, Any] = {
            "voltage": state_float(SENSOR_VOLTAGE),
            "current": state_float(SENSOR_CURRENT),
            "power": state_float(SENSOR_POWER),
            "temperature_internal": state_float(SENSOR_TEMP_INTERNAL),
            "temperature_external": state_float(SENSOR_TEMP_EXTERNAL),
            # Для обратной совместимости оставляем "temperature" как внутреннюю
            "temperature": state_float(SENSOR_TEMP_INTERNAL),
            "capacity_ah": state_float(SENSOR_CAPACITY_AH),
            "energy_wh": state_float(SENSOR_ENERGY_WH),
            "set_voltage": state_float(NUMBER_SET_VOLTAGE),
            "set_current": state_float(NUMBER_SET_CURRENT),
            "output_on": state_bool(SWITCH_OUTPUT),
            "mode_cc": state_bool(BINARY_MODE_CC),
            "mode_cv": state_bool(BINARY_MODE_CV),
            "ovp": state_bool(BINARY_OVP),
            "ocp": state_bool(BINARY_OCP),
        }

        data["raw_states"] = {k: by_id.get(k) for k in ALL_RELEVANT_ENTITIES}
        return data

    # Public API
    def get_data(self) -> Optional[Dict[str, Any]]:
        """Fetch all relevant entities in one go, with 3s cache TTL."""
        now = time.time()
        if (
            self._cache_data is not None
            and now - self._cache_timestamp <= self._cache_ttl
        ):
            return self._cache_data

        if not self.base_url or not self.token:
            logger.error("HAService is not fully configured.")
            return self._cache_data

        try:
            url = f"{self.base_url}/api/states"
            resp = self.session.get(url, timeout=5)
            resp.raise_for_status()
            states = resp.json()
            data = self._extract_rd6018_data(states)
            self._cache_data = data
            self._cache_timestamp = now
            return data
        except requests.RequestException as exc:
            logger.error("Error fetching HA data: %s", exc)
            # Return last known cache if available
            return self._cache_data

    def set_value(self, entity_id: str, value: Any) -> bool:
        """
        Automatically call correct HA service:
        - number.* -> number.set_value
        - switch.* -> switch.turn_on / switch.turn_off
        """
        if not self.base_url or not self.token:
            logger.error("HAService is not fully configured.")
            return False

        domain = entity_id.split(".", 1)[0]
        service: str
        payload: Dict[str, Any]

        if domain == "number":
            service = "set_value"
            val = parse_float(value)
            if val is None:
                logger.error("Invalid numeric value for %s: %s", entity_id, value)
                return False
            payload = {"entity_id": entity_id, "value": val}
        elif domain == "switch":
            # Interpret truthiness as ON/OFF
            is_on = bool(value)
            service = "turn_on" if is_on else "turn_off"
            payload = {"entity_id": entity_id}
        else:
            logger.error("Unsupported entity domain for set_value: %s", entity_id)
            return False

        try:
            url = f"{self.base_url}/api/services/{domain}/{service}"
            resp = self.session.post(url, data=json.dumps(payload), timeout=5)
            resp.raise_for_status()
            logger.info("Set %s via %s.%s: %s", entity_id, domain, service, payload)
            return True
        except requests.RequestException as exc:
            logger.error("Error setting HA value for %s: %s", entity_id, exc)
            return False

    def toggle_output(self, on: bool) -> bool:
        """
        Удобный шорткат для включения/выключения выхода RD6018.
        """
        return self.set_value(SWITCH_OUTPUT, bool(on))


# -----------------------------------------------------------------------------
# Safety Manager
# -----------------------------------------------------------------------------
class SafetyManager:
    """
    Enforces safe operating limits for RD6018 when charging lead-acid batteries.
    """

    MAX_VOLTAGE: float = 17.0
    HIGH_VOLTAGE_THRESHOLD: float = 15.0
    MAX_CURRENT_HIGH_VOLTAGE: float = 2.5

    def enforce(
        self,
        target_voltage: Optional[float],
        target_current: Optional[float],
    ) -> Tuple[Optional[float], Optional[float], List[str]]:
        """
        Apply safety rules and return adjusted voltage/current and warnings.
        """
        warnings: List[str] = []

        if target_voltage is not None and target_voltage > self.MAX_VOLTAGE:
            target_voltage = self.MAX_VOLTAGE
            warnings.append(
                f"Voltage limited to {self.MAX_VOLTAGE:.1f}V (hard maximum)."
            )

        if (
            target_voltage is not None
            and target_current is not None
            and target_voltage > self.HIGH_VOLTAGE_THRESHOLD
            and target_current > self.MAX_CURRENT_HIGH_VOLTAGE
        ):
            target_current = self.MAX_CURRENT_HIGH_VOLTAGE
            warnings.append(
                f"Current limited to {self.MAX_CURRENT_HIGH_VOLTAGE:.1f}A "
                f"for voltage above {self.HIGH_VOLTAGE_THRESHOLD:.1f}V."
            )

        return target_voltage, target_current, warnings


# -----------------------------------------------------------------------------
# Data Monitor (Background Thread)
# -----------------------------------------------------------------------------
class DataMonitor(threading.Thread):
    """
    Polls Home Assistant every 10s and stores last ~4 hours of V/I/P.
    """

    def __init__(self, ha_service: HAService) -> None:
        super().__init__(daemon=True)
        self.ha_service = ha_service
        # 4 hours at 10 s interval -> 1440 points
        self.timestamps: deque[datetime.datetime] = deque(maxlen=1440)
        self.voltages: deque[float] = deque(maxlen=1440)
        self.currents: deque[float] = deque(maxlen=1440)
        self.powers: deque[float] = deque(maxlen=1440)
        self._stop_event = threading.Event()

        # Состояние алгоритма десульфатации (управляется этим же потоком мониторинга).
        self.desulf_lock = threading.Lock()
        # Флаг активности режима
        self.desulf_mode_active: bool = False
        # Этап: SEARCHING (поиск триггера), TIMER (3 часа), COOLDOWN (65 с малого тока)
        self.desulf_stage: str = "SEARCHING"
        # Привязанный чат
        self.desulf_chat_id: Optional[int] = None
        # Начальное напряжение при старте режима
        self.desulf_start_v: Optional[float] = None
        # Минимальный ток (для CV) и максимальное напряжение (для CC)
        self.desulf_min_i: Optional[float] = None
        self.desulf_max_v: Optional[float] = None
        # Время, с которого условие по дельте считается устойчивым (≥30 с)
        self.desulf_delta_ok_since: Optional[float] = None
        # Время запуска 3‑часового таймера
        self.desulf_timer_start: Optional[float] = None
        # Время начала стадии COOLDOWN
        self.desulf_cooldown_start: Optional[float] = None

        # Время начала текущего «сеанса заряда» (включение выхода)
        self.output_on_since: Optional[datetime.datetime] = None
        self._last_output_on: Optional[bool] = None
        # Флаг активной аварии перегрева, чтобы не спамить каждые 10 секунд
        self._overheat_active: bool = False
        # Последние состояния аппаратных защит
        self._last_ovp: Optional[bool] = None
        self._last_ocp: Optional[bool] = None

    def run(self) -> None:
        logger.info("DataMonitor thread started.")
        while not self._stop_event.is_set():
            try:
                data = self.ha_service.get_data()
                if data:
                    ts = datetime.datetime.now()
                    v = data.get("voltage") or 0.0
                    i = data.get("current") or 0.0
                    p = data.get("power") or 0.0
                    output_on = bool(data.get("output_on"))
                    self.timestamps.append(ts)
                    self.voltages.append(v)
                    self.currents.append(i)
                    self.powers.append(p)
                    # Отслеживаем время начала заряда (включения выхода)
                    if self._last_output_on is None:
                        self._last_output_on = output_on
                        if output_on:
                            self.output_on_since = ts
                    else:
                        if not self._last_output_on and output_on:
                            # Переход OFF -> ON
                            self.output_on_since = ts
                        elif self._last_output_on and not output_on:
                            # Переход ON -> OFF
                            self.output_on_since = None
                        self._last_output_on = output_on
                    # Глобальный монитор безопасности (перегрев, аппаратные защиты)
                    self._update_global_safety(data)
                    # Обновляем неблокирующую логику десульфатации.
                    self._update_desulfation_logic(data)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in DataMonitor: %s", exc)
            self._stop_event.wait(10.0)

    def stop(self) -> None:
        self._stop_event.set()

    def generate_plot(self) -> Optional[io.BytesIO]:
        """
        Generate a Voltage/Current vs Time chart for all available history
        (up to ~4 hours).
        Voltage on left axis, Current on right axis.
        Returns BytesIO PNG ready for Telegram, or None if no data.
        """
        if not self.timestamps:
            return None

        try:
            fig, ax1 = plt.subplots(figsize=(9, 4))
            ax1.plot(
                self.timestamps,
                self.voltages,
                color="tab:blue",
                label="Voltage (V)",
            )
            ax1.set_xlabel("Time")
            ax1.set_ylabel("Voltage (V)", color="tab:blue")
            ax1.tick_params(axis="y", labelcolor="tab:blue")

            ax2 = ax1.twinx()
            ax2.plot(
                self.timestamps,
                self.currents,
                color="tab:red",
                label="Current (A)",
            )
            ax2.set_ylabel("Current (A)", color="tab:red")
            ax2.tick_params(axis="y", labelcolor="tab:red")

            fig.tight_layout()
            fig.autofmt_xdate()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight")
            plt.close(fig)
            buf.seek(0)
            buf.name = "rd6018_history.png"
            return buf
        except Exception as exc:  # noqa: BLE001
            logger.error("Error generating plot: %s", exc)
            return None

    def _build_plot(
        self,
        times: list[datetime.datetime],
        voltages: list[float],
        currents: list[float],
        filename: str,
    ) -> Optional[io.BytesIO]:
        if not times:
            return None
        try:
            fig, ax1 = plt.subplots(figsize=(9, 4))
            ax1.plot(times, voltages, color="tab:blue", label="Voltage (V)")
            ax1.set_xlabel("Time")
            ax1.set_ylabel("Voltage (V)", color="tab:blue")
            ax1.tick_params(axis="y", labelcolor="tab:blue")

            ax2 = ax1.twinx()
            ax2.plot(times, currents, color="tab:red", label="Current (A)")
            ax2.set_ylabel("Current (A)", color="tab:red")
            ax2.tick_params(axis="y", labelcolor="tab:red")

            fig.tight_layout()
            fig.autofmt_xdate()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight")
            plt.close(fig)
            buf.seek(0)
            buf.name = filename
            return buf
        except Exception as exc:  # noqa: BLE001
            logger.error("Error generating plot: %s", exc)
            return None

    def generate_plot_30m(self) -> Optional[io.BytesIO]:
        """
        График U/I за последние 30 минут.
        """
        if not self.timestamps:
            return None
        now = datetime.datetime.now()
        cutoff = now - datetime.timedelta(minutes=30)
        times_30m: list[datetime.datetime] = []
        volts_30m: list[float] = []
        curr_30m: list[float] = []
        for t, v, c in zip(self.timestamps, self.voltages, self.currents):
            if t >= cutoff:
                times_30m.append(t)
                volts_30m.append(v)
                curr_30m.append(c)
        if len(times_30m) < 2:
            return None
        return self._build_plot(times_30m, volts_30m, curr_30m, "rd6018_30m.png")

    def generate_plot_charge(self) -> Optional[io.BytesIO]:
        """
        График U/I с момента последнего включения выхода (сеанс заряда).
        """
        if not self.timestamps or self.output_on_since is None:
            return None
        start = self.output_on_since
        times_ch: list[datetime.datetime] = []
        volts_ch: list[float] = []
        curr_ch: list[float] = []
        for t, v, c in zip(self.timestamps, self.voltages, self.currents):
            if t >= start:
                times_ch.append(t)
                volts_ch.append(v)
                curr_ch.append(c)
        if len(times_ch) < 2:
            return None
        return self._build_plot(times_ch, volts_ch, curr_ch, "rd6018_charge.png")

    # --- Логика десульфатации (неблокирующая) ---

    def is_desulf_active(self) -> bool:
        with self.desulf_lock:
            return self.desulf_mode_active

    def start_desulfation(self, chat_id: int) -> bool:
        with self.desulf_lock:
            if self.desulf_mode_active:
                return False
            # Включаем режим и обнуляем состояние автомата
            self.desulf_mode_active = True
            self.desulf_stage = "SEARCHING"
            self.desulf_chat_id = chat_id
            self.desulf_start_v = None
            self.desulf_min_i = None
            self.desulf_max_v = None
            self.desulf_delta_ok_since = None
            self.desulf_timer_start = None
            self.desulf_cooldown_start = None
            self.desulf_delta_ok_since = time.time() + 5
        self._notify("🔨 Десульфатация включена. Ожидание выхода на режим 16.3 V / 1.0 A.")
        logger.info("Desulfation sequence started for chat %s", chat_id)
        return True

    def stop_desulfation(self, turn_output_off: bool = False) -> None:
        with self.desulf_lock:
            prev_active = self.desulf_mode_active
            self.desulf_mode_active = False
            self.desulf_stage = "SEARCHING"
            self.desulf_start_v = None
            self.desulf_min_i = None
            self.desulf_max_v = None
            self.desulf_delta_ok_since = None
            self.desulf_timer_start = None
            self.desulf_cooldown_start = None
        if turn_output_off:
            try:
                self.ha_service.set_value(SWITCH_OUTPUT, False)
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to switch off output on desulf stop: %s", exc)
        if prev_active:
            logger.info("Desulfation sequence stopped.")

    # --- Глобальная безопасность (перегрев, аппаратные защиты) ---

    def _notify_global(self, text: str) -> None:
        # Используем последний активный чат для уведомлений
        if last_chat_id is None:
            return
        try:
            bot.send_message(last_chat_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send global safety notification: %s", exc)

    def _update_global_safety(self, data: Dict[str, Any]) -> None:
        """
        Глобальный монитор: перегрев АКБ и аппаратные защиты OVP/OCP.
        Вызывается из run() каждые ~10 секунд.
        """
        # Температура АКБ
        t_ext = data.get("temperature_external")
        if t_ext is not None:
            if t_ext > 45.0 and not self._overheat_active:
                # Аварийное отключение выхода и остановка десульфатации
                try:
                    self.ha_service.toggle_output(False)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to switch off output on overheat: %s", exc)
                # Останавливаем десульфатацию и дополнительно выключаем выход
                self.stop_desulfation(turn_output_off=True)
                self._overheat_active = True
                msg = (
                    f"🚨🚨🚨 КРИТИЧЕСКИЙ ПЕРЕГРЕВ АКБ! "
                    f"Текущая температура: {t_ext:.1f}°C. "
                    "ПИТАНИЕ ОТКЛЮЧЕНО!"
                )
                logger.warning("Battery overheat: %s", msg)
                self._notify_global(msg)
            elif t_ext <= 42.0 and self._overheat_active:
                # Гистерезис для повторных срабатываний
                self._overheat_active = False

        # Аппаратные защиты OVP/OCP
        ovp = bool(data.get("ovp"))
        ocp = bool(data.get("ocp"))

        if self._last_ovp is None:
            self._last_ovp = ovp
        if self._last_ocp is None:
            self._last_ocp = ocp

        # Срабатывание OVP
        if ovp and not self._last_ovp:
            self._notify_global(
                "⚠️ Сработала аппаратная защита RD6018 по перенапряжению (OVP)! "
                "Проверьте уставки и состояние нагрузки."
            )
            logger.warning("Hardware OVP protection triggered.")

        # Срабатывание OCP
        if ocp and not self._last_ocp:
            self._notify_global(
                "⚠️ Сработала аппаратная защита RD6018 по превышению тока (OCP)! "
                "Проверьте уставки и состояние нагрузки."
            )
            logger.warning("Hardware OCP protection triggered.")

        self._last_ovp = ovp
        self._last_ocp = ocp

    def _notify(self, text: str) -> None:
        if self.desulf_chat_id is None:
            return
        try:
            bot.send_message(self.desulf_chat_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send desulfation notification: %s", exc)

    def _update_desulfation_logic(self, data: Dict[str, Any]) -> None:
        """
        Неблокирующий автомат десульфатации.
        Вызывается каждые ~10 секунд из потока мониторинга.
        """
        with self.desulf_lock:
            mode_active = self.desulf_mode_active
            stage = self.desulf_stage
        if not mode_active:
            return

        now_ts = time.time()
        v_now = data.get("voltage")
        i_now = data.get("current")
        set_v = data.get("set_voltage")
        set_i = data.get("set_current")
        output_on = data.get("output_on")

        # Безопасность: если выход выключен внешним действием — останавливаем алгоритм.
        if not output_on:
            self._notify("🛑 Десульфатация остановлена: выход RD6018 отключён.")
            self.stop_desulfation(turn_output_off=False)
            return

        mode, _ = determine_mode(i_now, set_i)

        # При первом заходе в режим SEARCHING переводим БП в нужные уставки 16.3 V / 1.0 A
        if stage == "SEARCHING":
            with self.desulf_lock:
                already_started = self.desulf_start_v is not None
            if not already_started:
                try:
                    self.ha_service.set_value(NUMBER_SET_VOLTAGE, 16.3)
                    self.ha_service.set_value(NUMBER_SET_CURRENT, 1.0)
                    self.ha_service.set_value(SWITCH_OUTPUT, True)
                    with self.desulf_lock:
                        self.desulf_start_v = v_now
                    self._notify("🔨 Десульфатация: установлено 16.3 V / 1.0 A, выход включён.")
                    logger.info("Desulfation: set 16.3 V / 1.0 A and enabled output.")
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to set desulfation initial setpoints: %s", exc)
                    self._notify(
                        "❌ Не удалось задать 16.3 V / 1.0 A. Десульфатация остановлена."
                    )
                    self.stop_desulfation(turn_output_off=False)
                    return

        # MONITORING: отслеживаем устойчивое изменение тока/напряжения (30 с).
        if stage == "SEARCHING":
            if mode == "CV" and i_now is not None:
                with self.desulf_lock:
                    i_min = self.desulf_min_i
                    delta_since = self.desulf_delta_ok_since
                if i_min is None or i_now < i_min:
                    i_min = i_now
                cond = i_min is not None and i_now >= i_min + 0.02
                if cond:
                    if delta_since is None:
                        delta_since = now_ts
                    elif now_ts - delta_since >= 30.0:
                        # Устойчивый рост тока ≥0.02 А в течение ≥30 с — триггер.
                        with self.desulf_lock:
                            self.desulf_min_i = i_min
                            self.desulf_delta_ok_since = None
                            self.desulf_stage = "TIMER"
                            self.desulf_timer_start = now_ts
                        self._notify(
                            "🔨 Десульфатация: Trigger hit! (CV, устойчивый рост тока ≥0.02 A)."
                        )
                        self._notify("⏱ Таймер 3 часа запущен.")
                        logger.info("Desulfation trigger (CV) fired.")
                        return
                else:
                    delta_since = None
                with self.desulf_lock:
                    self.desulf_min_i = i_min
                    self.desulf_delta_ok_since = delta_since

            elif mode == "CC" and v_now is not None:
                with self.desulf_lock:
                    v_max = self.desulf_max_v
                    delta_since = self.desulf_delta_ok_since
                if v_max is None or v_now > v_max:
                    v_max = v_now
                cond = v_max is not None and v_now <= v_max - 0.02
                if cond:
                    if delta_since is None:
                        delta_since = now_ts
                    elif now_ts - delta_since >= 30.0:
                        # Устойчивое падение напряжения ≥0.02 В за ≥30 с — триггер.
                        with self.desulf_lock:
                            self.desulf_max_v = v_max
                            self.desulf_delta_ok_since = None
                            self.desulf_stage = "TIMER"
                            self.desulf_timer_start = now_ts
                        self._notify(
                            "🔨 Десульфатация: Trigger hit! (CC, устойчивое падение напряжения ≥0.02 V)."
                        )
                        self._notify("⏱ Таймер 3 часа запущен.")
                        logger.info("Desulfation trigger (CC) fired.")
                        return
                else:
                    delta_since = None
                with self.desulf_lock:
                    self.desulf_max_v = v_max
                    self.desulf_delta_ok_since = delta_since

        # TIMER: ждём 3 часа с момента триггера (не блокируя поток).
        with self.desulf_lock:
            timer_start = self.desulf_timer_start
        if stage == "TIMER" and timer_start is not None:
            if now_ts - timer_start >= 3 * 3600:
                # Через 3 часа переходим на малый ток 0.02 A.
                try:
                    self.ha_service.set_value(NUMBER_SET_CURRENT, 0.02)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to switch to 0.02 A in desulfation: %s", exc)
                    self._notify(
                        "❌ Не удалось перевести ток на 0.02 A. Десульфатация остановлена."
                    )
                    self.stop_desulfation(turn_output_off=False)
                    return
                with self.desulf_lock:
                    self.desulf_stage = "COOLDOWN"
                    self.desulf_cooldown_start = now_ts
                self._notify(
                    "❄️ Десульфатация: cooldown (0.02 A) запущен на 65 секунд."
                )
                logger.info("Desulfation entered cooldown stage.")
                return

        # COOLDOWN: 65 секунд малого тока, затем переход в Float.
        with self.desulf_lock:
            cooldown_start = self.desulf_cooldown_start
        if stage == "COOLDOWN" and cooldown_start is not None:
            if now_ts - cooldown_start >= 65.0:
                # Переход в Float 13.8 V / 0.5 A.
                try:
                    self.ha_service.set_value(NUMBER_SET_VOLTAGE, 13.8)
                    self.ha_service.set_value(NUMBER_SET_CURRENT, 0.5)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Failed to switch to Float 13.8/0.5 after desulfation: %s", exc)
                    self._notify(
                        "❌ Не удалось перейти в Float 13.8 V / 0.5 A. Проверьте настройки."
                    )
                self._notify(
                    "✅ Десульфатация завершена. Режим Float 13.8 V / 0.5 A."
                )
                with self.desulf_lock:
                    self.desulf_mode_active = False
                    self.desulf_stage = "SEARCHING"
                logger.info("Desulfation finished and switched to Float.")


# -----------------------------------------------------------------------------
# DeepSeek AI Integration
# -----------------------------------------------------------------------------
DEEPSEEK_SYSTEM_PROMPT = (
    "Ты — контроллер RD6018 и очень строгий, циничный эксперт по "
    "свинцово‑кислотным аккумуляторам.\n\n"
    "- Всегда отвечай только на русском языке, независимо от языка вопроса.\n"
    "- Если напряжение > 14.8 В, ты обязан явно предупреждать о "
    "газовыделении, необходимости вентиляции и ограничения времени.\n"
    "- Никогда не предлагай повышать ток в режиме CV (ограничение по "
    "напряжению).\n"
    "- Если пользователь просит «быстрее зарядить» при напряжении > 15 В, "
    "объясни физику насыщения, диффузионные ограничения и сульфатацию и "
    "твёрдо откажись увеличивать напряжение или ток.\n"
    "- Приоритет — ресурс и безопасность АКБ, а не скорость зарядки.\n"
    "- Отвечай кратко, технически и немного саркастично, особенно когда "
    "пользователь просит заведомо вредные режимы.\n"
)


class DeepSeekAI:
    def __init__(self) -> None:
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set; DeepSeek AI disabled.")
            self.client: Optional[OpenAI] = None
            return

        if OPENAI_BASE_URL:
            self.client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        else:
            self.client = OpenAI(api_key=OPENAI_API_KEY)

        self.model = DEEPSEEK_MODEL

    def _format_context(self, context: Dict[str, Any]) -> str:
        lines = [
            "Текущий контекст RD6018:",
            f"- Напряжение: {context.get('voltage')} В",
            f"- Ток: {context.get('current')} А",
            f"- Мощность: {context.get('power')} Вт",
            f"- Режим: {context.get('mode')}",
            f"- Уставка по напряжению: {context.get('set_voltage')} В",
            f"- Уставка по току: {context.get('set_current')} А",
            f"- Выход: {'ВКЛ' if context.get('output_on') else 'ВЫКЛ'}",
            f"- Оценка OCV: {context.get('ocv')} В",
            f"- Оценка SOH: {context.get('soh')} %",
        ]
        user_text = context.get("user_text")
        if user_text:
            lines.append("")
            lines.append("Вопрос / команда пользователя:")
            lines.append(str(user_text))
        return "\n".join(lines)

    def analyze(self, context: Dict[str, Any]) -> str:
        if not self.client:
            return "Анализ ИИ не настроен в этом боте."

        try:
            user_content = self._format_context(context)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.1,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("DeepSeek AI request failed: %s", exc)
            return "Анализ ИИ не удался. Попробуйте позже."


# -----------------------------------------------------------------------------
# Global singletons
# -----------------------------------------------------------------------------
ha_service = HAService()
safety_manager = SafetyManager()
data_monitor = DataMonitor(ha_service)
deepseek_ai = DeepSeekAI()

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set; bot cannot start.")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="HTML")

# Последний чат, с которым бот взаимодействовал (для аварийных уведомлений)
last_chat_id: Optional[int] = None


# -----------------------------------------------------------------------------
# Helper functions for bot logic
# -----------------------------------------------------------------------------
def determine_mode(
    current: Optional[float],
    current_set: Optional[float],
) -> Tuple[str, str]:
    """
    Determine CC/CV based on current vs set_current.
    CC if I_now >= I_set - 0.1A, else CV.
    Returns (mode_str, emoji).
    """
    if current is None or current_set is None:
        return "UNKNOWN", "❓"

    try:
        if current >= current_set - 0.1:
            return "CC", "⚡"
        return "CV", "📊"
    except TypeError:
        return "UNKNOWN", "❓"


def build_main_keyboard(output_on: Optional[bool]) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)

    # Row 1: Refresh / Output toggle
    refresh_btn = types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
    if output_on:
        toggle_btn = types.InlineKeyboardButton("🔴 OFF", callback_data="toggle_output")
    else:
        toggle_btn = types.InlineKeyboardButton("🟢 ON", callback_data="toggle_output")
    kb.row(refresh_btn, toggle_btn)

    # Row 2: Presets
    float_btn = types.InlineKeyboardButton(
        "🔋 Float 13.8V", callback_data="preset_float"
    )
    charge_btn = types.InlineKeyboardButton(
        "⚡ Charge 14.4V", callback_data="preset_charge"
    )
    eq_btn = types.InlineKeyboardButton("⚖️ Eq 16.2V", callback_data="preset_eq")
    kb.row(float_btn, charge_btn, eq_btn)

    # Row 3: Fine tuning
    v_plus = types.InlineKeyboardButton("V+0.1", callback_data="v_plus")
    v_minus = types.InlineKeyboardButton("V-0.1", callback_data="v_minus")
    i_plus = types.InlineKeyboardButton("I+0.1", callback_data="i_plus")
    i_minus = types.InlineKeyboardButton("I-0.1", callback_data="i_minus")
    kb.row(v_plus, v_minus, i_plus, i_minus)

    # Row 4: Tools
    graph_30m_btn = types.InlineKeyboardButton(
        "📈 30m", callback_data="graph_30m"
    )
    graph_charge_btn = types.InlineKeyboardButton(
        "📈 Заряд", callback_data="graph_charge"
    )
    ai_btn = types.InlineKeyboardButton("🤖 AI Check", callback_data="ai_check")
    kb.row(graph_30m_btn, graph_charge_btn)
    kb.row(ai_btn)

    # Row 5: Desulfation / STOP
    desulf_btn = types.InlineKeyboardButton(
        "🔨 Десульфатация", callback_data="desulf_start"
    )
    stop_btn = types.InlineKeyboardButton("🛑 STOP", callback_data="desulf_stop")
    kb.row(desulf_btn, stop_btn)

    return kb


def get_psu_context() -> Optional[Dict[str, Any]]:
    data = ha_service.get_data()
    if not data:
        return None

    voltage = data.get("voltage")
    current = data.get("current")
    power = data.get("power")
    set_voltage = data.get("set_voltage")
    set_current = data.get("set_current")
    output_on = data.get("output_on")
    temp_int = data.get("temperature_internal")
    temp_ext = data.get("temperature_external")
    cap_ah = data.get("capacity_ah")
    energy_wh = data.get("energy_wh")

    # Режим по бинарным сенсорам CC/CV, при их отсутствии — по току/уставке
    mode_cc = data.get("mode_cc")
    mode_cv = data.get("mode_cv")
    if mode_cc:
        mode = "CC"
        mode_emoji = "⚡"
    elif mode_cv:
        mode = "CV"
        mode_emoji = "📊"
    else:
        mode, mode_emoji = determine_mode(current, set_current)

    # Simple OCV approximation: if current is small, use voltage as OCV
    ocv: Optional[float]
    if current is not None and abs(current) < 0.1:
        ocv = voltage
    else:
        ocv = voltage

    soh = estimate_soh_from_ocv(ocv)

    return {
        "voltage": voltage,
        "current": current,
        "power": power,
        "temperature_internal": temp_int,
        "temperature_external": temp_ext,
        "capacity_ah": cap_ah,
        "energy_wh": energy_wh,
        "set_voltage": set_voltage,
        "set_current": set_current,
        "output_on": output_on,
        "ocv": ocv,
        "soh": soh,
        "mode": mode,
        "mode_emoji": mode_emoji,
    }


def format_status_message(ctx: Dict[str, Any]) -> str:
    v = ctx.get("voltage")
    i = ctx.get("current")
    p = ctx.get("power")
    t_int = ctx.get("temperature_internal")
    t_ext = ctx.get("temperature_external")
    cap = ctx.get("capacity_ah")
    en = ctx.get("energy_wh")
    sv = ctx.get("set_voltage")
    si = ctx.get("set_current")
    ocv = ctx.get("ocv")
    soh = ctx.get("soh")
    output_on = ctx.get("output_on")
    mode = ctx.get("mode")
    mode_emoji = ctx.get("mode_emoji")

    lines = [
        "<b>RD6018 — статус</b>",
        "",
        f"[РЕЖИМ: {mode_emoji} <b>{mode}</b>] | "
        f"[ВЫХОД: {'🟢 ON' if output_on else '🔴 OFF'}]",
        "",
        "<b>НАПРЯЖЕНИЕ / ТОК</b>",
        (
            f"U = <b>{v:.2f} В</b>"
            if v is not None
            else "U = <i>нет данных</i>"
        ),
        (
            f"I = <b>{i:.2f} А</b>"
            if i is not None
            else "I = <i>нет данных</i>"
        ),
        "",
        "<b>СТАТИСТИКА</b>",
        "Ah: "
        + (
            f"<b>{cap:.2f}</b>"
            if cap is not None
            else "<i>нет данных</i>"
        )
        + " | Wh: "
        + (
            f"<b>{en:.1f}</b>"
            if en is not None
            else "<i>нет данных</i>"
        )
        + " | W: "
        + (
            f"<b>{p:.1f}</b>"
            if p is not None
            else "<i>нет данных</i>"
        ),
        "",
        "<b>ТЕМПЕРАТУРА</b>",
        "Внутр: "
        + (
            f"<b>{t_int:.1f} °C</b>"
            if t_int is not None
            else "<i>нет данных</i>"
        )
        + " | АКБ: "
        + (
            f"<b>{t_ext:.1f} °C</b>"
            if t_ext is not None
            else "<i>нет данных</i>"
        ),
        "",
        "<b>УСТАВКИ</b>",
        "Uset: "
        + (
            f"<b>{sv:.2f} В</b>"
            if sv is not None
            else "<i>нет данных</i>"
        )
        + " | Iset: "
        + (
            f"<b>{si:.2f} А</b>"
            if si is not None
            else "<i>нет данных</i>"
        ),
    ]

    if ocv is not None:
        lines.append(f"OCV (оценка): <b>{ocv:.2f} В</b>")
    if soh is not None:
        lines.append(f"SOH (оценка): <b>{soh}%</b>")

    if v is not None and v > 14.8:
        lines.append("")
        lines.append(
            "⚠️ <b>Высокое напряжение для свинцово‑кислотной АКБ.</b> "
            "Ожидается газовыделение; ограничьте время и обеспечьте вентиляцию."
        )

    return "\n".join(lines)


def apply_voltage_current_changes(
    target_voltage: Optional[float],
    target_current: Optional[float],
) -> Tuple[bool, List[str]]:
    """
    Apply requested V/I changes via HA with SafetyManager enforcement.
    Returns (success, warnings).
    """
    # Fetch current setpoints if needed
    data = ha_service.get_data() or {}
    cur_sv = data.get("set_voltage")
    cur_si = data.get("set_current")

    if target_voltage is None:
        target_voltage = cur_sv
    if target_current is None:
        target_current = cur_si

    tv, ti, warnings = safety_manager.enforce(target_voltage, target_current)

    success = True
    if tv is not None and tv != cur_sv:
        success &= ha_service.set_value(NUMBER_SET_VOLTAGE, tv)
    if ti is not None and ti != cur_si:
        success &= ha_service.set_value(NUMBER_SET_CURRENT, ti)

    return success, warnings


def send_status(chat_id: int, message_id: Optional[int] = None) -> None:
    ctx = get_psu_context()
    if not ctx:
        text = (
            "Unable to retrieve RD6018 data from Home Assistant. "
            "Is HA online and configured?"
        )
        if message_id is None:
            bot.send_message(chat_id, text)
        else:
            bot.edit_message_text(text, chat_id, message_id)
        return

    text = format_status_message(ctx)
    keyboard = build_main_keyboard(ctx.get("output_on"))

    if message_id is None:
        bot.send_message(chat_id, text, reply_markup=keyboard)
    else:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=keyboard)


# -----------------------------------------------------------------------------
# Telegram Handlers
# -----------------------------------------------------------------------------
@bot.message_handler(commands=["start", "status"])
def handle_start_status(message: telebot.types.Message) -> None:
    global last_chat_id
    last_chat_id = message.chat.id
    logger.info("Command %s from %s", message.text, message.chat.id)
    send_status(message.chat.id)


@bot.message_handler(commands=["check"])
def handle_check(message: telebot.types.Message) -> None:
    """
    /check <resistance_mOm>
    Example: /check 3.03
    """
    global last_chat_id
    last_chat_id = message.chat.id
    logger.info("Command /check from %s: %s", message.chat.id, message.text)
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        bot.reply_to(
            message,
            "Usage: /check <resistance_mΩ>\nExample: <code>/check 3.03</code>",
        )
        return

    try:
        resistance_mohm = float(parts[1].strip())
    except ValueError:
        bot.reply_to(message, "Invalid resistance value. Use something like 3.03")
        return

    ctx = get_psu_context()
    if not ctx or ctx.get("voltage") is None:
        bot.reply_to(
            message,
            "Unable to read voltage/current from Home Assistant for health check.",
        )
        return

    voltage = ctx["voltage"]
    current = ctx.get("current") or 0.0

    # Approximate OCV = V_terminal + I * R_internal
    ocv = voltage + current * (resistance_mohm / 1000.0)
    cca = max(
        0,
        int(((ocv - 10.5) / (resistance_mohm / 1000.0)) * 1.1)
        if resistance_mohm > 0
        else 0,
    )

    # Classify status
    if ocv >= 12.6 and resistance_mohm <= 3.5:
        status = "EXCELLENT"
    elif ocv >= 12.4 and resistance_mohm <= 5.0:
        status = "GOOD"
    else:
        status = "BAD"

    reply = (
        f"Resist: <b>{resistance_mohm:.2f} mΩ</b>\n"
        f"OCV: <b>{ocv:.2f} V</b>\n"
        f"Status: <b>{status}</b>\n"
        f"Est. CCA: <b>~{cca} A</b>"
    )
    bot.reply_to(message, reply)


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call: telebot.types.CallbackQuery) -> None:
    try:
        data = call.data
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        global last_chat_id
        last_chat_id = chat_id
        logger.info("Callback %s from %s", data, chat_id)

        if data == "refresh":
            bot.answer_callback_query(call.id, "Refreshing status…")
            send_status(chat_id, message_id)
            return

        if data == "toggle_output":
            state = ha_service.get_data() or {}
            output_on = bool(state.get("output_on"))
            new_state = not output_on
            ok = ha_service.set_value(SWITCH_OUTPUT, new_state)
            if ok:
                # Если пользователь вручную отключил выход — останавливаем десульфатацию.
                if not new_state and data_monitor.is_desulf_active():
                    data_monitor.stop_desulfation(turn_output_off=False)
                bot.answer_callback_query(
                    call.id, "Output turned ON" if new_state else "Output turned OFF"
                )
                send_status(chat_id, message_id)
            else:
                bot.answer_callback_query(
                    call.id, "Failed to toggle output.", show_alert=True
                )
            return

        if data == "preset_float":
            bot.answer_callback_query(call.id, "Applying Float 13.8V preset…")
            if data_monitor.is_desulf_active():
                data_monitor.stop_desulfation(turn_output_off=False)
            success, warnings = apply_voltage_current_changes(13.8, None)
            if not success:
                bot.send_message(chat_id, "Failed to apply Float preset.")
            if warnings:
                bot.send_message(chat_id, "\n".join(warnings))
            send_status(chat_id, message_id)
            return

        if data == "preset_charge":
            bot.answer_callback_query(call.id, "Applying Charge 14.4V preset…")
            if data_monitor.is_desulf_active():
                data_monitor.stop_desulfation(turn_output_off=False)
            success, warnings = apply_voltage_current_changes(14.4, None)
            if not success:
                bot.send_message(chat_id, "Failed to apply Charge preset.")
            if warnings:
                bot.send_message(chat_id, "\n".join(warnings))
            send_status(chat_id, message_id)
            return

        if data == "preset_eq":
            # Ask for explicit confirmation for Equalization at 16.2V
            bot.answer_callback_query(
                call.id,
                "Equalization at 16.2V can damage batteries. Confirm required.",
            )
            if data_monitor.is_desulf_active():
                data_monitor.stop_desulfation(turn_output_off=False)
            kb = types.InlineKeyboardMarkup(row_width=2)
            yes_btn = types.InlineKeyboardButton(
                "✅ Yes, equalize 16.2V", callback_data="eq_confirm_yes"
            )
            no_btn = types.InlineKeyboardButton(
                "❌ Cancel", callback_data="eq_confirm_no"
            )
            kb.row(yes_btn, no_btn)
            bot.send_message(
                chat_id,
                (
                    "⚠️ <b>Equalization mode (16.2V)</b>\n\n"
                    "This is only for occasional recovery on flooded Pb batteries. "
                    "Electrolyte will gas vigorously. Do NOT use on AGM/GEL.\n\n"
                    "Are you sure?"
                ),
                reply_markup=kb,
            )
            return

        if data == "eq_confirm_yes":
            bot.answer_callback_query(call.id, "Equalization 16.2V requested.")
            if data_monitor.is_desulf_active():
                data_monitor.stop_desulfation(turn_output_off=False)
            success, warnings = apply_voltage_current_changes(16.2, None)
            if not success:
                bot.send_message(chat_id, "Failed to apply Equalization preset.")
            if warnings:
                bot.send_message(chat_id, "\n".join(warnings))
            send_status(chat_id)
            return

        if data == "eq_confirm_no":
            bot.answer_callback_query(call.id, "Equalization cancelled.")
            return

        # Fine tuning for V/I
        if data in {"v_plus", "v_minus", "i_plus", "i_minus"}:
            if data_monitor.is_desulf_active():
                data_monitor.stop_desulfation(turn_output_off=False)
            sign = 1.0 if data.endswith("plus") else -1.0
            is_voltage = data.startswith("v_")

            state = ha_service.get_data() or {}
            cur_sv = state.get("set_voltage")
            cur_si = state.get("set_current")

            if is_voltage:
                if cur_sv is None:
                    bot.answer_callback_query(
                        call.id,
                        "Current set voltage is unknown.",
                        show_alert=True,
                    )
                    return
                target_v = cur_sv + 0.1 * sign
                target_i = cur_si
            else:
                if cur_si is None:
                    bot.answer_callback_query(
                        call.id,
                        "Current set current is unknown.",
                        show_alert=True,
                    )
                    return
                target_v = cur_sv
                target_i = cur_si + 0.1 * sign

            bot.answer_callback_query(call.id, "Applying adjustment…")
            success, warnings = apply_voltage_current_changes(target_v, target_i)
            if not success:
                bot.send_message(chat_id, "Failed to apply adjustment.")
            if warnings:
                bot.send_message(chat_id, "\n".join(warnings))
            send_status(chat_id, message_id)
            return

        if data == "graph_30m":
            bot.answer_callback_query(call.id, "Generating 30m graph…")
            buf = data_monitor.generate_plot_30m()
            if not buf:
                bot.send_message(
                    chat_id,
                    "Недостаточно данных для построения графика за 30 минут.",
                )
                return
            bot.send_photo(
                chat_id,
                photo=buf,
                caption="RD6018: U/I за последние 30 минут.",
            )
            return

        if data == "graph_charge":
            bot.answer_callback_query(call.id, "Generating charge graph…")
            buf = data_monitor.generate_plot_charge()
            if not buf:
                bot.send_message(
                    chat_id,
                    "Нет достаточных данных с момента включения выхода для графика заряда.",
                )
                return
            bot.send_photo(
                chat_id,
                photo=buf,
                caption="RD6018: U/I за текущий сеанс заряда (с момента включения выхода).",
            )
            return

        if data == "ai_check":
            bot.answer_callback_query(call.id, "Running AI analysis…")
            ctx = get_psu_context()
            if not ctx:
                bot.send_message(
                    chat_id,
                    "Unable to get PSU context from Home Assistant for AI check.",
                )
                return
            ctx["user_text"] = "Дай оценку безопасности и состояния текущего режима."
            analysis = deepseek_ai.analyze(ctx)
            bot.send_message(chat_id, analysis)
            return

        if data == "desulf_start":
            if data_monitor.is_desulf_active():
                bot.answer_callback_query(
                    call.id,
                    "Desulfation sequence is already running.",
                    show_alert=True,
                )
                return

            bot.answer_callback_query(call.id, "Starting desulfation sequence…")
            # Кнопка только включает флаг в DataMonitor; вся логика и уставки внутри DataMonitor.
            if not data_monitor.start_desulfation(chat_id):
                bot.send_message(
                    chat_id,
                    "Desulfation manager is busy. Try again later.",
                )
                return
            bot.send_message(
                chat_id,
                "🔨 Десульфатация запущена: 16.3 V / 1.0 A, выход включен.",
            )
            return

        if data == "desulf_stop":
            bot.answer_callback_query(call.id, "Stopping desulfation sequence…")
            data_monitor.stop_desulfation(turn_output_off=True)
            bot.send_message(
                chat_id,
                "🛑 Десульфатация остановлена. Выход RD6018 выключен.",
            )
            send_status(chat_id, message_id)
            return

        # Fallback
        bot.answer_callback_query(call.id, "Unknown action.")
    except Exception as exc:  # noqa: BLE001
        logger.error("Error in callback handler: %s", exc)
        try:
            bot.answer_callback_query(
                call.id, "An error occurred while processing.", show_alert=True
            )
        except Exception:  # noqa: BLE001
            pass


@bot.message_handler(
    func=lambda m: bool(m.text) and not m.text.startswith("/")
)
def handle_free_text(message: telebot.types.Message) -> None:
    """
    Any non-command text is sent to DeepSeek AI with current PSU context.
    """
    global last_chat_id
    last_chat_id = message.chat.id
    logger.info("Free text from %s: %s", message.chat.id, message.text)
    ctx = get_psu_context()
    if not ctx:
        bot.reply_to(
            message,
            "Unable to get PSU context from Home Assistant. AI can’t assess safely.",
        )
        return

    ctx["user_text"] = message.text
    analysis = deepseek_ai.analyze(ctx)
    bot.reply_to(message, analysis)


# -----------------------------------------------------------------------------
# Main entrypoint
# -----------------------------------------------------------------------------
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is missing. Exiting.")
        return

    logger.info("Starting RD6018 bot.")
    data_monitor.start()

    # Resilient polling loop
    while True:
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=30,
                allowed_updates=[
                    "message",
                    "callback_query",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in polling: %s", exc)
            time.sleep(5)


if __name__ == "__main__":
    main()

