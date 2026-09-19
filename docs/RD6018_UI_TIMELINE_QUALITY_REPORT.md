# RD6018 V3 UI Timeline Quality Pass — WORKSTREAM 41

## Status

**`UI_TIMELINE_QUALITY_READY`**

Работа выполнена только в development tree. Node 101, `rd6018-bot.service`,
production runtime, FSM, START/STOP, lease и physical execution не затрагивались.

## Changes

`v3_core.ui_session` теперь предоставляет presentation-only quality contract:

- `TimelineDisplayEvent` с полями event time, phase, reason и condition;
- `TimelineDisplay` со статусами `READY` и `UNKNOWN`;
- `OperatorTimelineFormatter.display(..., session_id=...)` фильтрует только
  текущую session и не подмешивает исторические события;
- отсутствие событий или полей явно отображается как `UNKNOWN`, а не пустая
  строка;
- существующий `SessionTimeline.start()` сохраняет graph reset и новый
  timestamp origin через новый `SessionGraphBuffer`.

## Timeline contract

Операторская цепочка поддерживает:

`START → phase transitions → Delta start/end → Hold start/end → termination → STOP`

Форматтер не создаёт отсутствующие события и не имитирует START/STOP. Для
Delta/Hold доступны явные markers, reason и condition; если evidence отсутствует,
поле остаётся `UNKNOWN`.

## Validation

Добавлены `tests/test_workstream41_ui_timeline_quality.py`:

- graph reset при новой session;
- session isolation и исключение исторических событий;
- phase/Delta/Hold markers;
- reason/condition display;
- empty timeline → `UNKNOWN`;
- missing reason/condition → `UNKNOWN`;
- отсутствие runtime/physical imports.

Проверки:

- Workstream 41 tests: **6 passed**;
- UI session regression: **9 passed**;
- dashboard regression: **5 passed**;
- Telegram adapter regression: **4 passed**;
- `compileall`: passed;
- `git diff --check`: passed.

## Known limitation

Качество presentation-модели готово, но фактическая live timeline для legacy
active session по-прежнему зависит от наличия `session_id` и canonical events.
При их отсутствии UI обязан показывать `UNKNOWN`, что подтверждено тестами.
