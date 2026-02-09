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
SENSOR_TEMP = "sensor.rd_6018_temperature_external"
SENSOR_CAPACITY_AH = "sensor.rd_6018_ah_capacity"
SENSOR_ENERGY_WH = "sensor.rd_6018_wh_energy"

NUMBER_SET_VOLTAGE = "number.rd_6018_output_voltage"
NUMBER_SET_CURRENT = "number.rd_6018_output_current"
SWITCH_OUTPUT = "switch.rd_6018_output"

ALL_RELEVANT_ENTITIES = [
    SENSOR_VOLTAGE,
    SENSOR_CURRENT,
    SENSOR_POWER,
    SENSOR_TEMP,
    SENSOR_CAPACITY_AH,
    SENSOR_ENERGY_WH,
    NUMBER_SET_VOLTAGE,
    NUMBER_SET_CURRENT,
    SWITCH_OUTPUT,
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
            "temperature": state_float(SENSOR_TEMP),
            "capacity_ah": state_float(SENSOR_CAPACITY_AH),
            "energy_wh": state_float(SENSOR_ENERGY_WH),
            "set_voltage": state_float(NUMBER_SET_VOLTAGE),
            "set_current": state_float(NUMBER_SET_CURRENT),
            "output_on": state_bool(SWITCH_OUTPUT),
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
                    self.timestamps.append(ts)
                    self.voltages.append(v)
                    self.currents.append(i)
                    self.powers.append(p)
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


class DesulfationManager:
    """
    State machine for десульфатация (high‑voltage conditioning).

    Алгоритм:
    - Старт: V=16.3 В, I=1.0 А, выход включен.
    - Если режим CV: отслеживаем I_min, при I_now >= I_min + 0.02 А — «Trigger hit».
    - Если режим CC: отслеживаем V_max, при V_now <= V_max - 0.02 В — «Trigger hit».
    - После триггера: 3 часа тайм‑аут.
    - Затем: I=0.02 А на 65 секунд (cooldown).
    - После cooldown: Float 13.8 В, 0.5 А.
    - В любой момент STOP отменяет последовательность и отключает выход.
    """

    def __init__(self, ha: HAService) -> None:
        self.ha = ha
        self.state_lock = threading.Lock()
        self.state: str = "idle"  # idle | monitoring | timer | cooldown
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.chat_id: Optional[int] = None
        self.i_min: Optional[float] = None
        self.v_max: Optional[float] = None
        self.trigger_time: Optional[float] = None
        self.cooldown_start: Optional[float] = None

    def is_active(self) -> bool:
        with self.state_lock:
            return self.state != "idle"

    def start_desulfation(self, chat_id: int) -> bool:
        with self.state_lock:
            if self.state != "idle":
                return False
            self.state = "monitoring"

        self.chat_id = chat_id
        self.i_min = None
        self.v_max = None
        self.trigger_time = None
        self.cooldown_start = None
        self.stop_event.clear()

        # Запускаем фоновую логику
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("Desulfation sequence started for chat %s", chat_id)
        return True

    def stop_desulfation(self) -> None:
        with self.state_lock:
            prev_state = self.state
            self.state = "idle"
        self.stop_event.set()
        # Отключаем выход питания
        self.ha.set_value(SWITCH_OUTPUT, False)
        logger.info("Desulfation sequence stopped (prev state: %s)", prev_state)

    def _notify(self, text: str) -> None:
        if self.chat_id is None:
            return
        try:
            bot.send_message(self.chat_id, text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to send desulfation notification: %s", exc)

    def _run_loop(self) -> None:
        try:
            self._notify("🔨 Десульфатация: режим мониторинга запущен.")
            check_interval = 10.0
            while not self.stop_event.is_set():
                with self.state_lock:
                    state = self.state

                if state == "idle":
                    break

                data = self.ha.get_data()
                if not data:
                    time.sleep(check_interval)
                    continue

                v_now = data.get("voltage")
                i_now = data.get("current")
                sv = data.get("set_voltage")
                si = data.get("set_current")
                mode, _ = determine_mode(i_now, si)

                now_ts = time.time()

                if state == "monitoring":
                    if mode == "CV" and i_now is not None:
                        if self.i_min is None or i_now < self.i_min:
                            self.i_min = i_now
                        if (
                            self.i_min is not None
                            and i_now >= self.i_min + 0.02  # type: ignore[operator]
                        ):
                            self.trigger_time = now_ts
                            with self.state_lock:
                                self.state = "timer"
                            self._notify("🔨 Десульфатация: Trigger hit! (CV, рост тока).")
                            self._notify("⏱ Таймер 3 часа запущен.")
                    elif mode == "CC" and v_now is not None:
                        if self.v_max is None or v_now > self.v_max:
                            self.v_max = v_now
                        if (
                            self.v_max is not None
                            and v_now <= self.v_max - 0.02  # type: ignore[operator]
                        ):
                            self.trigger_time = now_ts
                            with self.state_lock:
                                self.state = "timer"
                            self._notify("🔨 Десульфатация: Trigger hit! (CC, падение напряжения).")
                            self._notify("⏱ Таймер 3 часа запущен.")

                elif state == "timer":
                    if self.trigger_time is not None and now_ts - self.trigger_time >= 3 * 3600:
                        # Переход в стадию малый ток
                        ok, warnings = apply_voltage_current_changes(None, 0.02)
                        if not ok:
                            self._notify(
                                "❌ Не удалось перевести ток на 0.02 A. Десульфатация остановлена."
                            )
                            self.stop_desulfation()
                            break
                        for w in warnings:
                            self._notify(w)
                        self.cooldown_start = now_ts
                        with self.state_lock:
                            self.state = "cooldown"
                        self._notify("❄️ Десульфатация: cooldown (0.02 A) запущен на 65 секунд.")

                elif state == "cooldown":
                    if self.cooldown_start is not None and now_ts - self.cooldown_start >= 65:
                        ok, warnings = apply_voltage_current_changes(13.8, 0.5)
                        if not ok:
                            self._notify(
                                "❌ Не удалось перейти в Float 13.8 V / 0.5 A. Проверьте настройки."
                            )
                        for w in warnings:
                            self._notify(w)
                        self._notify(
                            "✅ Десульфатация завершена. Режим Float 13.8 V / 0.5 A."
                        )
                        with self.state_lock:
                            self.state = "idle"
                        break

                time.sleep(check_interval)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error in DesulfationManager loop: %s", exc)
            self._notify("❌ Ошибка в логике десульфатации. Процесс остановлен.")
            self.stop_desulfation()


desulf_manager = DesulfationManager(ha_service)


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
    graph_btn = types.InlineKeyboardButton(
        "📈 Graph history", callback_data="graph_history"
    )
    ai_btn = types.InlineKeyboardButton("🤖 AI Check", callback_data="ai_check")
    kb.row(graph_btn, ai_btn)

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

    # Simple OCV approximation: if current is small, use voltage as OCV
    ocv: Optional[float]
    if current is not None and abs(current) < 0.1:
        ocv = voltage
    else:
        ocv = voltage

    soh = estimate_soh_from_ocv(ocv)
    mode, mode_emoji = determine_mode(current, set_current)

    return {
        "voltage": voltage,
        "current": current,
        "power": power,
        "temperature": data.get("temperature"),
        "capacity_ah": data.get("capacity_ah"),
        "energy_wh": data.get("energy_wh"),
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
    t = ctx.get("temperature")
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
        "<b>RD6018 Power Supply Status</b>",
        "",
        f"Mode: {mode_emoji} <b>{mode}</b>",
        f"Output: {'🟢 ON' if output_on else '🔴 OFF'}",
        "",
        f"V: <b>{v:.2f} V</b>" if v is not None else "V: <i>unknown</i>",
        f"I: <b>{i:.2f} A</b>" if i is not None else "I: <i>unknown</i>",
        f"P: <b>{p:.1f} W</b>" if p is not None else "P: <i>unknown</i>",
        f"🌡 Temp: <b>{t:.1f} °C</b>"
        if t is not None
        else "🌡 Temp: <i>unknown</i>",
        f"Capacity: <b>{cap:.2f} Ah</b>"
        if cap is not None
        else "Capacity: <i>unknown</i>",
        f"Energy: <b>{en:.1f} Wh</b>"
        if en is not None
        else "Energy: <i>unknown</i>",
        "",
        "Setpoints:",
        f"- Voltage: <b>{sv:.2f} V</b>" if sv is not None else "- Voltage: <i>unknown</i>",
        f"- Current: <b>{si:.2f} A</b>" if si is not None else "- Current: <i>unknown</i>",
    ]

    if ocv is not None:
        lines.append(f"OCV (est): <b>{ocv:.2f} V</b>")
    if soh is not None:
        lines.append(f"SOH (est): <b>{soh}%</b>")

    if v is not None and v > 14.8:
        lines.append("")
        lines.append(
            "⚠️ <b>High voltage for Pb battery.</b> Expect gassing; limit time and "
            "ensure ventilation."
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
    logger.info("Command %s from %s", message.text, message.chat.id)
    send_status(message.chat.id)


@bot.message_handler(commands=["check"])
def handle_check(message: telebot.types.Message) -> None:
    """
    /check <resistance_mOm>
    Example: /check 3.03
    """
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
            success, warnings = apply_voltage_current_changes(13.8, None)
            if not success:
                bot.send_message(chat_id, "Failed to apply Float preset.")
            if warnings:
                bot.send_message(chat_id, "\n".join(warnings))
            send_status(chat_id, message_id)
            return

        if data == "preset_charge":
            bot.answer_callback_query(call.id, "Applying Charge 14.4V preset…")
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

        if data == "graph_history":
            bot.answer_callback_query(call.id, "Generating history graph…")
            buf = data_monitor.generate_plot()
            if not buf:
                bot.send_message(
                    chat_id,
                    "Not enough data yet to generate graph (need some history).",
                )
                return
            bot.send_photo(
                chat_id,
                photo=buf,
                caption="RD6018 Voltage/Current history (up to ~4 hours).",
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
            if desulf_manager.is_active():
                bot.answer_callback_query(
                    call.id,
                    "Desulfation sequence is already running.",
                    show_alert=True,
                )
                return

            bot.answer_callback_query(call.id, "Starting desulfation sequence…")
            # Установить 16.3 V / 1.0 A и включить выход
            success, warnings = apply_voltage_current_changes(16.3, 1.0)
            if not success:
                bot.send_message(
                    chat_id,
                    "Failed to set 16.3 V / 1.0 A for desulfation.",
                )
                return
            if warnings:
                bot.send_message(chat_id, "\n".join(warnings))

            ha_service.set_value(SWITCH_OUTPUT, True)

            if not desulf_manager.start_desulfation(chat_id):
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
            desulf_manager.stop_desulfation()
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

