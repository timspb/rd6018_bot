"""
charging_log.py — детальное логирование событий заряда в charging_history.log.
Формат: [ГГГГ-ММ-ДД ЧЧ:ММ:SS] | СТАДИЯ | V | I | T_ext | Ah | СОБЫТИЕ
"""
import logging
import os
import shutil
from datetime import datetime

LOG_FILE = "charging_history.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 МБ

_charge_logger: logging.Logger = None


def _ensure_logger() -> logging.Logger:
    global _charge_logger
    if _charge_logger is None:
        _charge_logger = logging.getLogger("charging_history")
        _charge_logger.setLevel(logging.INFO)
        if not _charge_logger.handlers:
            h = logging.FileHandler(LOG_FILE, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(message)s"))
            _charge_logger.addHandler(h)
        _charge_logger.propagate = False
    return _charge_logger


def rotate_if_needed() -> None:
    """Если лог > 5МБ — архивировать и начать новый."""
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX_BYTES:
        archive = f"{LOG_FILE}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        shutil.move(LOG_FILE, archive)


def log_event(
    stage: str,
    v: float,
    i: float,
    t_ext: float,
    ah: float,
    event: str,
) -> None:
    """Записать событие в лог с пользовательским часовым поясом."""
    try:
        from time_utils import format_datetime_user_tz
        ts = format_datetime_user_tz(fmt="%Y-%m-%d %H:%M:%S")
    except ImportError:
        # Fallback если time_utils недоступен
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    line = f"[{ts}] | {stage:12} | {v:5.2f} | {i:5.2f} | {t_ext:5.1f} | {ah:6.2f} | {event}"
    _ensure_logger().info(line)


def log_checkpoint(stage: str, v: float, i: float, t_ext: float, ah: float) -> None:
    """Контрольная точка (каждые 10 мин)."""
    log_event(stage, v, i, t_ext, ah, "CHECKPOINT")


def get_recent_events(limit: int = 5) -> list:
    """v2.6 Получить последние N событий из лога для AI контекста."""
    if not os.path.exists(LOG_FILE):
        return []
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Фильтруем значимые события (не CHECKPOINT)
        significant_events = []
        for line in lines:
            line = line.strip()
            if line and "CHECKPOINT" not in line:
                significant_events.append(line)
        
        # Возвращаем последние N событий
        return significant_events[-limit:] if significant_events else []
    except Exception:
        return []
