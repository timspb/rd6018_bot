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
    post_charge = snapshot.get("post_charge_relaxation") or {}
    bank_fault = snapshot.get("bank_fault_risk") or {}

    stage = snapshot.get("stage", "—")
    previous_stage = snapshot.get("previous_stage", "—")
    stage_path = snapshot.get("stage_path") or []
    last_transition_reason = snapshot.get("last_transition_reason", "—")
    profile = snapshot.get("profile", "—")
    active = "YES" if snapshot.get("is_active") else "NO"
    summary = snapshot.get("summary", "—")
    transition = snapshot.get("transition", "—")
    next_stage = snapshot.get("next_stage", "—")
    target_v = snapshot.get("target_voltage", "—")
    target_i = snapshot.get("target_current", "—")
    temp_comp = snapshot.get("temperature_compensation") or {}

    if isinstance(target_v, (int, float)) and isinstance(target_i, (int, float)):
        targets_line = f"Уставки: {target_v:.2f}V / {target_i:.2f}A"
    else:
        targets_line = f"Уставки: {target_v} / {target_i}"

    lines = [
        f"Stage: {stage} | Profile: {profile} | Active: {active}",
        f"Previous stage: {previous_stage}",
        f"Stage path: {' -> '.join(stage_path) if stage_path else '—'}",
        f"Rule summary: {summary}",
        f"Transition: {transition}",
        f"Last transition reason: {last_transition_reason}",
        f"Next stage: {next_stage}",
        targets_line,
        f"Время: всего={timers.get('total_time', '—')} | этап={timers.get('stage_time', '—')} | остаток={timers.get('remaining_time', '—')}",
        "Температуры: датчик АКБ и датчик БП/контроллера (вентилятор БП сам управляется; пороги АКБ к БП не применять)",
    ]

    if temp_comp:
        enabled = "YES" if temp_comp.get("enabled") else "NO"
        restored = "YES" if temp_comp.get("restored") else "NO"
        temp_c = temp_comp.get("temp_c")
        coeff = temp_comp.get("coeff_v_per_c")
        base_v = temp_comp.get("base_v")
        final_v = temp_comp.get("final_v")
        delta_v = temp_comp.get("delta_v")
        temp_text = f"{temp_c:.1f}C" if isinstance(temp_c, (int, float)) else "—"
        coeff_text = f"{coeff:.3f}V/°C" if isinstance(coeff, (int, float)) else "—"
        base_text = f"{base_v:.2f}V" if isinstance(base_v, (int, float)) else "—"
        final_text = f"{final_v:.2f}V" if isinstance(final_v, (int, float)) else "—"
        delta_text = f"{delta_v:+.2f}V" if isinstance(delta_v, (int, float)) else "—"
        lines.append(
            f"Temp comp: enabled={enabled} | restored={restored} | T={temp_text} | coeff={coeff_text} | base={base_text} | delta={delta_text} | final={final_text}"
        )

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

    if post_charge:
        post_status = post_charge.get("status", "—")
        post_reason = post_charge.get("reason", "—")
        post_risk = post_charge.get("stratification_risk", "—")
        post_conf = post_charge.get("confidence")
        post_drop = post_charge.get("drop_v")
        post_slope = post_charge.get("slope_mv_min")
        post_decay = post_charge.get("decay_mv_min")
        post_temp_span = post_charge.get("temp_span_c")
        post_window = post_charge.get("window_sec")
        post_samples = post_charge.get("sample_count")
        parts = [
            f"Post-charge: status={post_status}",
            f"reason={post_reason}",
            f"risk={post_risk}",
        ]
        if isinstance(post_drop, (int, float)):
            parts.append(f"drop={post_drop:.3f}V")
        if isinstance(post_decay, (int, float)):
            parts.append(f"decay={post_decay:.2f}mV/min")
        elif isinstance(post_slope, (int, float)):
            parts.append(f"slope={post_slope:.2f}mV/min")
        if isinstance(post_temp_span, (int, float)):
            parts.append(f"temp_span={post_temp_span:.2f}C")
        if isinstance(post_window, (int, float)):
            parts.append(f"window={int(post_window // 60)}m")
        if isinstance(post_samples, int):
            parts.append(f"samples={post_samples}")
        if isinstance(post_conf, (int, float)):
            parts.append(f"conf={post_conf:.2f}")
        lines.append(" | ".join(parts))
        window_summary = post_charge.get("window_summary")
        if window_summary:
            lines.append(f"Post-charge windows: {window_summary}")
        if post_charge.get("note"):
            lines.append(f"Post-charge note: {post_charge.get('note')}")

    if bank_fault:
        def _bank_status_label(status: Any) -> str:
            mapping = {
                "stable": "норма",
                "watch": "наблюдение",
                "probable": "вероятен",
                "high": "высокий",
            }
            return mapping.get(str(status or "").lower(), str(status or "—"))

        def _bank_reason_label(reason: str) -> str:
            mapping = {
                "prep_start_low": "низкий старт в Подготовке",
                "prep_slow_to_12V": "медленный выход к 12В в Подготовке",
                "prep_still_below_12V": "слишком долго ниже 12В в Подготовке",
                "main_duration": "Main дольше расчётного",
                "main_slow_v_rise<0.8V": "медленный рост напряжения в Main",
                "main_slow_v_rise<1.2V": "медленный рост напряжения в Main",
                "main_low_ah_acceptance": "низкая приёмка заряда в Main",
                "main_temp_rise": "рост температуры АКБ в Main",
                "safe_wait_decay_watch": "ускоренное падение напряжения в SAFE_WAIT",
                "safe_wait_decay_risk": "быстрое падение напряжения в SAFE_WAIT",
                "safe_wait_decay_high": "очень быстрое падение напряжения в SAFE_WAIT",
                "safe_wait_decay": "быстрое падение напряжения в SAFE_WAIT",
                "safe_wait_temp_rise": "рост температуры АКБ в SAFE_WAIT",
                "self_discharge_warning": "саморазряд",
                "temp_rise": "рост температуры АКБ",
            }
            if "=" in reason:
                head, tail = reason.split("=", 1)
                head = mapping.get(head, head)
                return f"{head}={tail}"
            return mapping.get(reason, reason)

        bank_status_raw = str(bank_fault.get("status", "—")).lower()
        bank_status = _bank_status_label(bank_status_raw)
        bank_score = bank_fault.get("score")
        bank_stage = bank_fault.get("stage", "—")
        bank_elapsed = bank_fault.get("elapsed_text") or _format_seconds(bank_fault.get("elapsed_sec"))
        bank_start_v = bank_fault.get("start_voltage")
        bank_curr_v = bank_fault.get("current_voltage")
        bank_start_t = bank_fault.get("start_temp_c")
        bank_curr_t = bank_fault.get("current_temp_c")
        bank_reasons = ", ".join(_bank_reason_label(r) for r in (bank_fault.get("reasons") or []))
        parts = [
            f"Риск по банке: {bank_status}",
            f"score={bank_score}",
            f"stage={bank_stage}",
        ]
        if bank_elapsed and bank_elapsed != "—":
            parts.append(f"elapsed={bank_elapsed}")
        if isinstance(bank_start_v, (int, float)) and isinstance(bank_curr_v, (int, float)):
            parts.append(f"АКБ V={bank_start_v:.2f}->{bank_curr_v:.2f}V")
        if isinstance(bank_start_t, (int, float)) and isinstance(bank_curr_t, (int, float)):
            parts.append(f"АКБ T={bank_start_t:.1f}->{bank_curr_t:.1f}C")
        if bank_reasons:
            parts.append(f"причины={bank_reasons}")
        lines.append(" | ".join(parts))

    lines.append(
        "Safety: "
        f"I<= {safety.get('current_limit_a', '—')}A, "
        f"OVP/OCP +{safety.get('ovp_offset_v', '—')}V/+{safety.get('ocp_offset_a', '—')}A, "
        f"T_ext={safety.get('temp_warning_c', '—')}/{safety.get('temp_pause_c', '—')}/{safety.get('temp_critical_c', '—')}C, "
        f"SafeWait={safety.get('safe_wait_margin_v', '—')}V / {safety.get('safe_wait_max_sec', '—')}s"
    )
    lines.append("Temp note: датчик БП/контроллера — только тепловой контроль; 35-49C это обычно тепло, а не риск АКБ.")
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
    temp_ext_now = ai_ctx.get("temp_ext_now")
    temp_int_now = ai_ctx.get("temp_int_now")

    cap_text = f"{capacity_ah}Ah" if capacity_known else "UNKNOWN"
    trend_block = f"\nКраткий тренд: {trend_summary}\n" if trend_summary else ""
    controller_block = format_ai_snapshot(controller_snapshot)
    events_block = format_recent_events(recent_events)

    prompt = (
        "Контекст RD6018 (из бота):\n"
        f"- Статус выхода: {output_status}\n"
        f"- Этап: {current_stage}\n"
        f"- Профиль: {battery_type}\n"
        f"- Режимы: {mode}\n"
        f"- Емкость известна: {'да' if capacity_known else 'нет'}\n"
        f"- Емкость АКБ: {cap_text}\n"
        f"- Остаток до лимита этапа: {remaining_time}\n"
        f"- Текущие значения: напряжение АКБ={v_batt_now}, ток={i_now}\n"
        f"- Температуры: АКБ={temp_ext_now}, БП={temp_int_now}\n"
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
