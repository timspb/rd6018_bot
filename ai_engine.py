"""
ai_engine.py — интеграция с DeepSeek для анализа кривой заряда.
"""
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL

logger = logging.getLogger("rd6018")


async def ask_deepseek(history_data: Dict[str, Any]) -> str:
    """
    Отправить последние ~20 минут V/I в DeepSeek.
    Вопрос: фаза заряда (Bulk/Absorption/Float) и оценка времени до полного заряда.
    """
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
    trend_block = (
        f"\nКраткий тренд: {trend_summary}\n"
        if trend_summary
        else ""
    )

    prompt = (
        "Analyze this lead-acid battery charging curve from RD6018.\n"
        + trend_block +
        f"\nПолные данные (время, напряжение V, ток A):\n"
        f"{data_text}\n\n"
        "Questions:\n"
        "1. Определи стадию заряда: CC (Bulk), CV (Absorption) или Float.\n"
        "2. Оцени состояние АКБ по динамике.\n"
        "3. Дай прогноз: сколько времени осталось до конца заряда (минуты).\n"
        "4. Возможные риски (сульфатация, потеря ёмкости).\n"
        "Reply briefly in Russian."
    )

    system_content = (
        "Ты — эксперт по аккумуляторам. "
        "Проанализируй динамику заряда за последний час. "
        "Определи стадию (CC/CV/Float), оцени состояние АКБ и дай прогноз, сколько времени осталось до конца. "
        "Отвечай кратко на русском. Для выделения используй HTML-теги <b>текст</b>."
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
