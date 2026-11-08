# RD6018 — Recipe Studio: план развития (2026-11-09)

## Решение владельца

Развить **существующий** модуль рецептов до удобной пользовательской системы: создание, редактирование, копирование, сохранение, импорт/экспорт и выбор рецептов через нормальный компьютерный UI и Telegram. Начать с компьютера, затем дать боту компактное управление **той же** библиотекой. Это продолжение проекта, не новый движок зарядки и не повод переделывать принятую архитектуру.

**Приоритет:** после P0 ручного управления `PB_MANAGED ↔ HANDS_OFF`; Recipe Studio — следующий продуктовый этап, допустимый для автономной *source-only* разработки. Production node104 остаётся на D144 slot16 COMMITTED, source `3f50133b0dca9d274a08d4dd7999f730ce90e962`. Разработка редактора не даёт разрешения на новую установку, физический START, OFF или изменение уставок.

## Фактическая кодовая база на старт этапа

Проверено в локальной ветке `feature/main-mix-countdown-display`, HEAD до этой записи `224c18c5678aa720e08950fdab8ca6999a4a742f`:

1. **Штатная интеллектуальная зарядка:** `runtime/charge/programs/native_recipe_catalog.py` — 3 химии (Ca/Ca, EFB, AGM) × 4 intent = 12 описаний существующих динамических владельцев. `native_recipe_parameters.py` предоставляет реальные `VariableSpec`; `native_recipe_draft.py` и `native_recipe_draft_library.py` — проверяемые неизменяемые версии копий. `native_recipe_session.py::require_supported_native_execution` не допускает параметров, ещё не подключённых к исполнению; `application/start_transaction_service.py` умеет выбирать и закреплять точную версию до START. Копия штатного рецепта **не** эквивалентна пользовательскому пошаговому runner.
2. **Пошаговые программы:** `recipe_schema.py`, `recipe_library.py`, `recipe_catalog.py`, `recipe_editor.py`, `recipe_preflight.py` и действующий runner. Исполняемый контракт: `{id,version,steps}`, каждый шаг `{action,params,until}`, action только `set/off/wait`; условия `after_seconds` либо поддерживаемые измеряемые пороги. Предусмотрены ограничения U/I, versioned immutable save, предварительная проверка. WAIT не наследует включённый Output: preflight требует непосредственно предыдущий OFF.
3. **Telegram:** `runtime/ui/telegram/recipes.py` — команды просмотра/копирования/редактирования пользовательских и native drafts; существующие `recipe_buttons.py`. Требуется перевести повседневные операции на понятный UI без дублирования бизнес-правил.
4. **ПК-прототип:** `tools/recipe_visual_editor_prototype.html` — автономный браузерный эскиз с таблицей этапов, графиком уставок, перемещением этапов, импортом/экспортом. Он **не подключён** к backend и экспортирует собственную `rd6018.recipe_visual_draft.v1` с полями `stages/kind/mode/on/v/i/min/cond/threshold`, где встречается `kind=native`. Такой документ **не является** ни `recipe_schema.Recipe`, ни `NativeRecipeDraft`; передавать его на START или автоматически переименовывать в исполняемый JSON нельзя. График — схема уставок, не прогноз электрохимии. `repeat_count` и составные native stage нельзя выдавать за доступное исполнение.

## Инварианты

- **Один источник истины:** действующие библиотеки/каталоги, схемы, `VariableSpec`, native session binding и текущий START owner. Редактор — исключительно способ создать/изменить данные.
- Два типа рецептов могут отображаться в одном UI, но их **семантика и исполняющие владельцы остаются разными**; никакого третьего runtime или смешивания `native` в SET/OFF runner.
- Все редактируемые поля имеют тип, единицы, реальные границы, применимость и признак *исполняется / пока только черновик*. Параметры берутся у своего владельца; нет отдельной таблицы порогов в JavaScript.
- Любое изменение — новая неизменяемая версия; существующая зарядная сессия сохраняет идентификатор, версию и content digest. Ни редактор, ни новый файл не меняет действующую сессию или актуаторы.
- Валидация и импорт недоверенного JSON выполняются в существующем backend до записи. В браузере — только удобная немедленная подсветка ошибок. Не создавать отдельный auth/ACL: использовать существующую операторскую авторизацию и безопасную привязку локального UI.
- Визуальный preview всегда отличает статическую схему уставок от реально условных переходов и ограничений химии. Никаких обещаний фактических U/I или момента завершения.
- До включения связи с оборудованием — source-only и offline regression, без изменения node104, ESP, HA, Telegram production, секретов и зарядных данных.

## План небольших изменений

### RS-0 — инвентаризация и контракты (стартовый этап)

- Зафиксировать текущее разделение двух типов, реальные пути записи/выбора и разрыв между HTML-драфтом и исполнителем.
- Сравнить доступные `VariableSpec` с `require_supported_native_execution`; показать недоступные поля, не молча игнорировать.
- Проверить соответствующие регрессии без физического исполнения.
- Результат: этот план и checkpoint, без изменения runtime. **2026-11-09: 26 targeted PASS**, source-only.

### RS-1 — компьютерный редактор на существующих контрактах

- Доработать текущий `tools/recipe_visual_editor_prototype.html` вместо создания второй оболочки. Добавить явное переключение «Копия штатного рецепта / Пошаговая программа», соответствующие наборы полей, признак исполняемости и недоступности.
- Для *пошагового* режима обеспечить строго проверяемый экспорт/import **канонического** `recipe_schema` — либо явно маркированный неисполняемый draft при неподдерживаемых возможностях. Не переводить произвольный `native` шаг в `set`.
- Для *native* режима формировать `NativeRecipeDraft` с `base_recipe_id + overrides`; допустимые и исполняемые параметры получать из существующего backend каталога/схемы.
- Сначала offline golden test round-trip и отклонение некорректного/неподдерживаемого формата; затем подключить к **существующему** каталогу/библиотеке под имеющимся операторским ACL. Никакого нового сервиса зарядки и открытого сетевого API на node104.

### RS-2 — полноценная библиотека версий в ПК UI

- Создать копию, добавить/удалить/переставить шаги, изменить значения и условия, сохранить **новую** версию, архивировать, просмотреть историю и сравнить изменения; отказы на stale revision, повреждённый JSON и превышение лимитов.
- Импорт/экспорт только после серверной проверки и с явным обозначением `draft` или `executable`.
- Доступ к актуальному состоянию через текущую библиотеку, без конфликтующих копий в браузере/Telegram.

### RS-3 — Telegram без JSON-команд

- Пользовательские кнопки «Мои рецепты», «Копировать», «Изменить», «Проверить», «Сохранить», «Использовать при следующем START», «Архив» в уже существующем `runtime/ui/telegram/recipes.py` и `recipe_buttons.py`.
- Переиспользовать то же чтение/валидацию/версионирование, сохранить один Telegram panel lifecycle и тот же START owner. Изменение проекта рецепта не становится аппаратной командой.

### RS-4 — offline acceptance, затем отдельная эксплуатационная приёмка

- Паритет PC ↔ Telegram ↔ библиотека по identity/version/digest и значениям; тесты reconnect/restart, failed save, stale version, неподдерживаемые native параметры, недопустимая химия/intent, неподдерживаемые последовательности `WAIT`.
- Проверка предпросмотра, предупреждений и неисполняемых черновиков без ложного START.
- Лишь после отдельной авторизации — новый релиз и физическая приёмка реального оборудования. Текущий D144 slot16 не изменять в ходе source-only этапов.

## Следующее конкретное действие

RS-1A: сделать **безопасный офлайн экспорт/импорт исполняемых пошаговых `set/off/wait` рецептов** на основе существующей `recipe_schema`, отдельно помечая и сохраняя неисполняемый `native` визуальный черновик без возможности случайного START. Добавить regression tests валидного round-trip, `native` rejection, `WAIT` после OFF и недопустимых U/I. Не подключать устройство и не добавлять новый исполнитель.

## Связанные документы

`AGENTS.md`, `docs/assistant/RD6018_CURRENT_CHECKPOINT.md`, `docs/assistant/RD6018_AUTONOMOUS_PLAN_2026-11-08.md`, `docs/assistant/RD6018_AUTONOMOUS_HANDOFF_2026-11-08.md`, `docs/V3_PROJECT_RUNBOOK.md`, `docs/DEPLOYMENT.md`.


## 2026-11-09 — Recipe Studio RS-1A offline canonical bridge

Implemented **source-only** extension of existing `tools/recipe_visual_editor_prototype.html`: a separate `Экспорт SET/OFF/WAIT` produces exactly canonical `{id,version,steps:[{action,params,until}]}`; the existing import recognizes that canonical format and converts it back to visual `CUSTOM` stages. Draft JSON remains a separate, explicitly non-executable format. UI now exposes recipe ID (ASCII), version and local preliminary U/I ceilings; the latter are **not** hardware-authoritative and do not grant START or replace server `RecipeLibrary/recipe_schema/recipe_preflight`.

Fail-closed conversion refuses visual `kind=native` and named dynamic `MAIN/MIX/...` stages, unsupported repeat_count, non-zero minute budgets not expressible in the canonical format, mismatched Output action and U/I, stale/invalid predicates, unsigned/zero time waits, invalid step count/identity, SET exceeding local provisional ceilings, and WAIT not immediately preceded by OFF. Canonical import validates structure, fields, ceilings, OFF/WAIT sequencing and unknown actions before visual transformation. The bridge **does not** translate chemistry/capacity visual metadata into executable behavior; no actuator paths are added.

Added `tests/test_recipe_visual_canonical_bridge.py` with Node.js execution of the actual functions extracted from HTML; checks real Python `parse_recipe + inspect_recipe` for round-trip and rejection cases. Final focused run including user-recipe, native-draft, START-selection and UI catalogue tests: **34 PASS, exit 0**, WSL Ubuntu 24.04. Extracted embedded JavaScript `node --check` PASS; `git diff --check` PASS. No node104 deployment/restart, ESP/HA access, Output/charging/lease action, new backend, extra recipe runner or Telegram modification.

**Next:** RS-1B — replace provisional browser-only validation/import behavior with an explicit offline contract-based check and save flow through the **existing** `RecipeLibrary` / native draft library; expose immutable version, actual `VariableSpec`/supported-execution limits, and compare browser preview with backend admission. Do not expose a new unauthenticated network listener. Physical/manual control P0 remains the higher operational priority and must be accepted separately.
