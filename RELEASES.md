# Релизы


**Historical release notes — not the current source candidate.**
The `Unreleased (2026-03-07)` section below is historical/draft text,
not approved release instructions. Its OVP/OCP offset programming
and unconditional Main-to-Mix claims are superseded by the accepted
runtime/safety canon. No automatic OVP/OCP programming is permitted.
The current V3 source candidate is reviewed in Draft PR #182;
new release notes must be compiled from the actual accepted release
candidate after P3/P8 physical acceptance. Preserve these older lines
only as history.

## Unreleased (2026-03-07)

### Изменения логики и защит
- Глобальный лимит тока на всех этапах: `12.0A` (`MAX_STAGE_CURRENT`).
- Смещение защит RD6018 обновлено: `OVP/OCP = target + 0.1`.
- Для профилей **Ca/Ca** и **EFB** при тайм-ауте Main выполняется принудительный переход в Mix.
- Уточнена логика переходов и сбросов между этапами/режимами.

### Интерфейс и UX
- Дашборд закреплён как одно рабочее сообщение (edit/delete вместо накопления сообщений).
- Переработаны кнопки диапазона графика (`Норма`, `30м`, `2ч`, `Сессия`) и поведение возврата к дашборду.
- Улучшен экран «Логи»: меньше служебного шума и повторов.
- Обновлён `/help`: короткая практическая справка по режимам и командам.

### AI-анализ
- AI-кнопка и диалоговые ответы разделены по отдельным путям (`ai_engine.py`, `ai_system_prompt.py`).
- Промпты приведены к фактической логике профилей (EFB/AGM/Ca/Ca, Mix/Safe Wait и т.д.).
- Снижено использование внутренних технических названий в пользовательском тексте.

### Документация
- Полностью обновлён `README.md` под текущее поведение проекта.

## v2.7.0 (2025-02-12)

### Новое
- **ALLOWED_CHAT_IDS** — ограничение доступа по списку разрешённых chat_id.
- **USER_TIMEZONE** — единый пользовательский часовой пояс для отчётов и логов.
- Автоочистка старых данных (`charging_history.log`, БД) старше 30 дней.

### Изменения
- Обновление поведения дашборда после запросов `/stats`, логов и AI.
- Улучшены проверки доступа и стабильность обработки событий.
