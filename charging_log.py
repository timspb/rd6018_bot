"""
charging_log.py — детальное логирование событий заряда в charging_history.log.
Формат: [ГГГГ-ММ-ДД ЧЧ:ММ:SS] | СТАДИЯ | V | I | T_ext | Ah | СОБЫТИЕ
"""
import logging
import os
import re
import shutil
from datetime import datetime, timedelta
from typing import Optional

from time_utils import format_datetime_user_tz

LOG_FILE = "charging_history.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 МБ
LOG_RETENTION_DAYS = 30  # хранить события не старше 30 дней

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


# Регулярка для извлечения даты из строки: [ГГГГ-ММ-ДД ЧЧ:ММ:SS]
_LOG_LINE_DATE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]")


def _parse_log_line_date(line: str) -> Optional[datetime]:
    """Извлечь дату из строки лога. Возвращает None, если не удалось распарсить."""
    line = line.strip()
    if not line:
        return None
    m = _LOG_LINE_DATE_RE.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def trim_log_older_than_days(days: int = LOG_RETENTION_DAYS) -> int:
    """
    Удалить из charging_history.log строки старше указанного числа дней.
    Возвращает количество удалённых строк.
    Перед перезаписью файла хендлер логгера временно снимается и затем восстанавливается.
    """
    if not os.path.exists(LOG_FILE):
        return 0
    logger_obj = _ensure_logger()
    # Снимаем файловый хендлер, чтобы можно было перезаписать файл
    handler_to_remove = None
    for h in logger_obj.handlers[:]:
        if getattr(h, "baseFilename", None) and LOG_FILE in str(h.baseFilename):
            handler_to_remove = h
            break
    if handler_to_remove:
        logger_obj.removeHandler(handler_to_remove)
        try:
            handler_to_remove.close()
        except Exception:
            pass

    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        kept = []
        for line in lines:
            dt = _parse_log_line_date(line)
            if dt is None:
                kept.append(line)
                continue
            if dt >= cutoff:
                kept.append(line)
            else:
                removed += 1
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.writelines(kept)
    except Exception as e:
        logging.getLogger("rd6018").warning("trim_log_older_than_days failed: %s", e)
    finally:
        # Восстанавливаем файловый хендлер
        if not any(
            getattr(h, "baseFilename", None) and LOG_FILE in str(getattr(h, "baseFilename", ""))
            for h in logger_obj.handlers
        ):
            h = logging.FileHandler(LOG_FILE, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(message)s"))
            logger_obj.addHandler(h)
    return removed


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
        ts = format_datetime_user_tz(fmt="%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] | {stage:12} | {v:5.2f} | {i:5.2f} | {t_ext:5.1f} | {ah:6.2f} | {event}"
    _ensure_logger().info(line)


def _format_duration(seconds: float) -> str:
    """Форматировать длительность: Xч Yм или Xм."""
    if seconds < 60:
        return f"{int(seconds)}с"
    if seconds < 3600:
        return f"{int(seconds // 60)}м"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if m:
        return f"{h}ч {m}м"
    return f"{h}ч"


def log_stage_end(
    stage: str,
    v: float,
    i: float,
    t_ext: float,
    ah: float,
    time_sec: float,
    ah_on_stage: float,
    trigger: str,
) -> None:
    """Записать завершение этапа: время на этапе, ёмкость, T, V, I, триггер."""
    try:
        ts = format_datetime_user_tz(fmt="%Y-%m-%d %H:%M:%S")
    except Exception:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_str = _format_duration(time_sec)
    event = (
        f"END | Время: {time_str} | Ёмкость: {ah_on_stage:.2f} Ач | "
        f"T: {t_ext:.1f}°C | V: {v:.2f}В | I: {i:.2f}А | Триггер: {trigger}"
    )
    line = f"[{ts}] | {stage:12} | {v:5.2f} | {i:5.2f} | {t_ext:5.1f} | {ah:6.2f} | {event}"
    _ensure_logger().info(line)


def log_checkpoint(stage: str, v: float, i: float, t_ext: float, ah: float) -> None:
    """Контрольная точка (каждые 10 мин)."""
    log_event(stage, v, i, t_ext, ah, "CHECKPOINT")


def clear_event_logs() -> None:
    """
    v2.7: Больше НЕ очищает файл журнала.

    История всех зарядов должна сохраняться в charging_history.log для последующего анализа.
    Очистка логов для пользователя теперь реализуется фильтрацией по текущей сессии
    (см. get_recent_events), поэтому эта функция оставлена только для обратной совместимости.
    """
    # Ничего не делаем умышленно.
    return None


def get_recent_events(limit: int = 5) -> list:
    """
    v2.7 Получить последние N событий ТЕКУЩЕЙ сессии из лога.

    Сессия начинается с последнего из:
    - START с profile= или START CUSTOM (новый заряд)
    - RESTORE (восстановление после потери связи)
    - START сразу после END (новый цикл после завершения этапа/ручного выкл)
    Так старые сессии не попадают в выборку.
    """
    if not os.path.exists(LOG_FILE):
        return []
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Ищем последнюю границу сессии: новый старт или восстановление
        start_idx = -1
        for idx, line in enumerate(lines):
            if ("START" in line and "profile=" in line) or "START CUSTOM" in line:
                start_idx = idx
            elif "RESTORE" in line:
                start_idx = idx
            elif "END " in line and idx + 1 < len(lines):
                next_line = lines[idx + 1]
                if "START" in next_line:
                    start_idx = idx + 1
                # иначе оставляем предыдущий start_idx
        
        if start_idx != -1:
            session_lines = lines[start_idx:]
        else:
            session_lines = lines
        
        # Фильтруем значимые события (не CHECKPOINT)
        significant_events = []
        for line in session_lines:
            line = line.strip()
            if line and "CHECKPOINT" not in line:
                significant_events.append(line)
        
        return significant_events[-limit:] if significant_events else []
    except Exception:
        return []
