"""
ai_engine.py — интеграция с DeepSeek для анализа кривой заряда.
Для кнопки "AI анализ" используется строгий промпт, согласованный с логикой этапов бота.
"""
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

logger = logging.getLogger("rd6018")


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
    trend_block = (
        f"\nКраткий тренд: {trend_summary}\n"
        if trend_summary
        else ""
    )

    prompt = (
        "Контекст RD6018 (из бота):\n"
        f"- OUTPUT_STATUS: {output_status}\n"
        f"- Stage: {current_stage}\n"
        f"- Profile: {battery_type}\n"
        f"- Mode flags: {mode}\n"
        f"- Capacity_known: {'YES' if capacity_known else 'NO'}\n"
        f"- Capacity_Ah: {cap_text}\n"
        f"- Stage_remaining: {remaining_time}\n"
        f"- Current snapshot: V_batt={v_batt_now}, I={i_now}\n"
        + trend_block +
        "\nИстория (время, напряжение V, ток A):\n"
        f"{data_text}\n\n"
        "Сформируй краткий техотчет по пунктам:\n"
        "1) Что происходит сейчас (строго по Stage/OUTPUT_STATUS).\n"
        "2) Состояние по данным (без фантазий).\n"
        "3) Прогноз (если он реально обоснован Stage_remaining/трендом).\n"
        "4) Риски и рекомендации (только подтвержденные данными).\n"
    )

    system_content = (
        "Ты анализируешь только данные этого RD6018-бота.\n"
        "Жесткие правила:\n"
        "1) Запрещено использовать термины Bulk/Absorption/Float, если их нет в текущем этапе.\n"
        "2) Для этой логики после Main идет Mix, затем Safe_wait/Storage. Не пиши 'после Main сразу Float'.\n"
        "3) Если Capacity_known=YES, запрещено писать 'неизвестна емкость'.\n"
        "4) Напряжение ~12.6-12.9V в покое не называть 'глубоким разрядом'.\n"
        "5) При OUTPUT_STATUS=OFF не делать жестких выводов о неисправности АКБ.\n"
        "6) Если данных недостаточно — явно так и напиши.\n"
        "Ответ: кратко, по-русски, можно HTML <b>...</b>."
    )

    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 512,
        "temperature": 0.3,
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
