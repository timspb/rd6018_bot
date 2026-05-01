"""
ai_engine.py - integration with DeepSeek for RD6018 charge analysis.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from ai_system_prompt import AI_CONSULTANT_SYSTEM_PROMPT
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

logger = logging.getLogger("rd6018")


def _format_seconds(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(seconds)}с"
    if seconds < 3600:
        return f"{int(seconds // 60)}м"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    if mins:
        return f"{hours}ч {mins}м"
    return f"{hours}ч"


def format_ai_snapshot(snapshot: Dict[str, Any]) -> str:
    """Сжать карточку стратегии контроллера в компактный текст для LLM."""
    if not snapshot:
        return "—"

    timers = snapshot.get("timers", {}) or {}
    hold = snapshot.get("hold") or {}
    safety = snapshot.get("safety", {}) or {}
    mix_exit_policy = snapshot.get("mix_exit_policy") or {}

    stage = snapshot.get("stage", "—")
    profile = snapshot.get("profile", "—")
    active = "YES" if snapshot.get("is_active") else "NO"
    summary = snapshot.get("summary", "—")
    transition = snapshot.get("transition", "—")
    next_stage = snapshot.get("next_stage", "—")
    target_v = snapshot.get("target_voltage", "—")
    target_i = snapshot.get("target_current", "—")

    if isinstance(target_v, (int, float)) and isinstance(target_i, (int, float)):
        targets_line = f"Targets: {target_v:.2f}V / {target_i:.2f}A"
    else:
        targets_line = f"Targets: {target_v} / {target_i}"

    lines = [
        f"Stage: {stage} | Profile: {profile} | Active: {active}",
        f"Rule summary: {summary}",
        f"Transition: {transition}",
        f"Next stage: {next_stage}",
        targets_line,
        f"Timers: total={timers.get('total_time', '—')} | stage={timers.get('stage_time', '—')} | remaining={timers.get('remaining_time', '—')}",
    ]

    if stage == "Mix Mode" or mix_exit_policy:
        if mix_exit_policy:
            primary = mix_exit_policy.get("primary", "—")
            mode = mix_exit_policy.get("mode", "—")
            delta_triggered = "YES" if mix_exit_policy.get("delta_triggered") else "NO"
            fallback_hours = mix_exit_policy.get("fallback_limit_hours")
            fallback_text = f"{fallback_hours}h" if isinstance(fallback_hours, (int, float)) else "—"
            lines.append(
                f"Mix exit: primary={primary} | mode={mode} | delta_triggered={delta_triggered} | fallback_limit={fallback_text}"
            )
        else:
            lines.append("Mix exit: primary=delta | mode=delta_or_time_fallback | delta_triggered=NO")
        lines.append(
            "Mix rule: normal exit is by ΔV/ΔI confirmation; stage timer is a fallback limit, not the main trigger."
        )
        lines.append(
            f"Finish timer active: {'YES' if snapshot.get('finish_timer_active') else 'NO'}"
        )

    if hold:
        hold_kind = hold.get("kind", "—")
        hold_active = "YES" if hold.get("active") else "NO"
        hold_elapsed = hold.get("elapsed_text", _format_seconds(hold.get("elapsed_sec")))
        hold_remaining = hold.get("remaining_text", _format_seconds(hold.get("remaining_sec")))
        hold_rule_met = "YES" if hold.get("rule_met") else "NO"
        lines.append(
            f"Hold: {hold_kind} | active={hold_active} | elapsed={hold_elapsed} | remaining={hold_remaining} | met={hold_rule_met}"
        )
        if hold.get("threshold_a") is not None:
            lines.append(f"Hold threshold: {hold.get('threshold_a'):.2f}A")
        if hold.get("current_a") is not None:
            lines.append(f"Hold current: {hold.get('current_a'):.2f}A")
        if hold.get("threshold_v") is not None:
            lines.append(f"Hold threshold V: {hold.get('threshold_v'):.2f}V")

    lines.append(
        "Safety: "
        f"I<= {safety.get('current_limit_a', '—')}A, "
        f"OVP/OCP +{safety.get('ovp_offset_v', '—')}V/+{safety.get('ocp_offset_a', '—')}A, "
        f"T={safety.get('temp_warning_c', '—')}/{safety.get('temp_pause_c', '—')}/{safety.get('temp_critical_c', '—')}C, "
        f"SafeWait={safety.get('safe_wait_margin_v', '—')}V / {safety.get('safe_wait_max_sec', '—')}s"
    )
    return "\n".join(lines)


def format_recent_events(events: List[str], limit: int = 8) -> str:
    """Сжать список событий до нескольких строк, сохранив триггеры."""
    if not events:
        return "—"

    def _parse_ts(event: str) -> Optional[datetime]:
        try:
            raw = event.split(" | ", 1)[0].strip("[]")
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    compact: List[str] = []
    pending_emergency: Optional[Dict[str, Any]] = None

    def _flush_emergency() -> None:
        nonlocal pending_emergency
        if not pending_emergency:
            return
        count = pending_emergency["count"]
        event = pending_emergency["event"]
        if count > 1:
            parts = event.split(" | ")
            if len(parts) > 6:
                parts[6] = f"EMERGENCY_UNAVAILABLE (x{count})"
                event = " | ".join(parts)
        compact.append(f"- {event[:180]}")
        pending_emergency = None

    for event in events[-limit:]:
        text = (event or "").strip()
        if not text:
            continue
        parts = text.split(" | ")
        event_name = parts[6].strip() if len(parts) > 6 else ""
        stage = parts[1].strip() if len(parts) > 1 else ""
        if event_name == "EMERGENCY_UNAVAILABLE":
            current_ts = _parse_ts(text)
            if pending_emergency:
                prev_stage = pending_emergency["stage"]
                prev_ts = pending_emergency["ts"]
                if prev_stage == stage and prev_ts and current_ts and (current_ts - prev_ts).total_seconds() <= 600:
                    pending_emergency["count"] += 1
                    pending_emergency["event"] = text
                    pending_emergency["ts"] = current_ts
                    continue
            _flush_emergency()
            pending_emergency = {"event": text, "count": 1, "stage": stage, "ts": current_ts}
            continue

        _flush_emergency()
        compact.append(f"- {text[:180]}")

    _flush_emergency()
    return "\n".join(compact) if compact else "—"


async def ask_deepseek(history_data: Dict[str, Any]) -> str:
    """Отправить историю V/I и контекст контроллера в DeepSeek."""
    if not DEEPSEEK_API_KEY:
        return "DeepSeek API ключ не настроен."

    times = history_data.get("times", [])
    voltages = history_data.get("voltages", [])
    currents = history_data.get("currents", [])

    if not times or not voltages or not currents:
        return "Недостаточно данных для анализа. Соберите 20+ минут истории."

    n = min(len(times), len(voltages), len(currents), 40)
    lines = []
    for i in range(n):
        v = voltages[i] if i < len(voltages) else 0
        c = currents[i] if i < len(currents) else 0
        t = times[i] if i < len(times) else ""
        lines.append(f"  {t}: U={v:.2f}V, I={c:.2f}A")

    data_text = "\n".join(lines)

    trend_summary = history_data.get("trend_summary", "")
    ai_ctx: Dict[str, Any] = history_data.get("ai_context", {}) or {}
    controller_snapshot = history_data.get("controller_snapshot", {}) or {}
    recent_events = history_data.get("recent_events", []) or []
    output_status = str(ai_ctx.get("output_status", "UNKNOWN"))
    current_stage = str(ai_ctx.get("current_stage", "UNKNOWN"))
    battery_type = str(ai_ctx.get("battery_type", "UNKNOWN"))
    mode = str(ai_ctx.get("mode", "UNKNOWN"))
    capacity_ah = ai_ctx.get("capacity_ah", "UNKNOWN")
    capacity_known = bool(ai_ctx.get("capacity_known", False))
    remaining_time = str(ai_ctx.get("remaining_time", "—"))
    v_batt_now = ai_ctx.get("v_batt_now")
    i_now = ai_ctx.get("i_now")

    cap_text = f"{capacity_ah}Ah" if capacity_known else "UNKNOWN"
    trend_block = f"\nКраткий тренд: {trend_summary}\n" if trend_summary else ""
    controller_block = format_ai_snapshot(controller_snapshot)
    events_block = format_recent_events(recent_events)

    prompt = (
        "Контекст RD6018 (из бота):\n"
        f"- OUTPUT_STATUS: {output_status}\n"
        f"- Stage: {current_stage}\n"
        f"- Profile: {battery_type}\n"
        f"- Mode flags: {mode}\n"
        f"- Capacity_known: {'YES' if capacity_known else 'NO'}\n"
        f"- Capacity_Ah: {cap_text}\n"
        f"- Остаток до защитного лимита этапа: {remaining_time}\n"
        f"- Current snapshot: V_batt={v_batt_now}, I={i_now}\n"
        + trend_block
        + "\nКарточка стратегии контроллера:\n"
        f"{controller_block}\n\n"
        "Последние важные события:\n"
        f"{events_block}\n\n"
        "История (время, напряжение V, ток A):\n"
        f"{data_text}\n\n"
        "Сформируй короткий техотчет по пунктам:\n"
        "1) Что происходит сейчас, без общих рассуждений.\n"
        "2) Какие факты подтверждены данными и карточкой стратегии.\n"
        "3) Какой следующий триггер или таймер важен прямо сейчас.\n"
        "4) Есть ли риски безопасности, только если они реально подтверждены.\n"
    )

    system_content = (
        AI_CONSULTANT_SYSTEM_PROMPT
        + "\n\nДополнительно для кнопки AI-анализа:\n"
        + "- Отвечай максимально кратко и опирайся на карточку стратегии, hold-снимок и последние события.\n"
        + "- Не называй ток 'минимальным', если hold-снимок не активен или rule_met не подтвержден.\n"
        + "- Если hold rule_met = YES, скажи, что условие удержания уже набрано, но не выдумывай точный момент переключения.\n"
        + "- Не делай прогнозов вне правил контроллера.\n"
    )

    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 512,
        "temperature": 0.2,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error("DeepSeek API error %d: %s", resp.status, text[:200])
                    return "Ошибка запроса к AI. Попробуйте позже."

                data = await resp.json()
                choices = data.get("choices", [])
                if not choices:
                    return "Пустой ответ от AI."
                msg = choices[0].get("message", {})
                return msg.get("content", "Пустой ответ.").strip()
    except aiohttp.ClientError as ex:
        logger.error("DeepSeek request failed: %s", ex)
        return "Нет связи с AI. Проверьте сеть и API ключ."
    except Exception as ex:
        logger.error("ask_deepseek failed: %s", ex)
        return f"Ошибка: {ex}"
