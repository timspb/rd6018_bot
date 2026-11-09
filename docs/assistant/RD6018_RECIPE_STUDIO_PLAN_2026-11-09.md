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

## 2026-11-09 — Recipe Studio RS-1B: canonical offline check/save (source-only)

Implemented offline bridge to existing **production canonical owners**, without a new daemon, API, device port, authorization layer or store:
- `runtime/charge/programs/recipe_studio_import.py`: `inspect_step_document` and `publish_step_document` accept **only** `{id, version, steps}`, apply existing `parse_recipe` with actual production limits and `inspect_recipe`, reject inadmissible WAIT/control-flow, stale/skipped revisions and archived recipes, then call the already immutable/atomic `RecipeLibrary.save`. OFF-first valid drafts are labelled not START-eligible; even SET-first never authorizes physical START.
- Same module `inspect_native_document` and `publish_native_document`: accept only `{name, version, draft:{schema:1,base_recipe_id,execution_kind:"native_authority",overrides}}`, use existing `validate_native_draft`, real `VariableSpec` ranges/policies, `require_supported_native_execution` (unsupported-but-displayed fields rejected), and unchanged immutable `NativeRecipeDraftLibrary.save`. Wrong base identity / stale version rejected by that library.
- `tools/recipe_studio_offline.py`: CLI `check`, `save`, `check-native`, `save-native`; explicit input JSON file and **mandatory explicitly chosen library root for save**. No implicit node104/production path, remote API, charging session or network socket. Pure checks do not create any library files. JSON responses include validation status, identity, version, warnings and `physical_start_authorized:false`. Nonfinite JSON refused. Source of hardware limit values reused from `config.MAX_MANUAL_VOLTAGE` and `runtime.safety.variables.MAX_STAGE_CURRENT_A.default`, matching production `bot.py`.

Examples from repository root:
```sh
python tools/recipe_studio_offline.py check --file ./exported-step-recipe.json
python tools/recipe_studio_offline.py save --file ./exported-step-recipe.json --library-root ./scratch-recipes
python tools/recipe_studio_offline.py check-native --file ./native-draft.json
python tools/recipe_studio_offline.py save-native --file ./native-draft.json --library-root ./scratch-native-drafts
```
Saved JSON is compatible with the existing backend catalog/draft library, **not automatically deployed to node104 or activated**. PC HTML currently exports canonical step candidates (RS-1A); a fully interactive native UI and browser-to-library persistence are **future work**, not represented as finished. Import via CLI is a documented interim offline bridge, not the final PC UX.

Acceptance: `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q` on 12 selected recipe/native/visual/start/catalog regression files: **48 passed, exit 0, 52.20 s**. `git diff --check` PASS. New test files: `tests/test_recipe_studio_offline_import.py`, `tests/test_recipe_studio_native_import.py`. No node104, BW600, HA102, ESP, Output or firmware operation.

Next RS-1C: introduce friendly native parameter editor UI with `VariableSpec` metadata exported by the **existing** backend; create a browser-save transport only after verifying existing operator ACL binding, without adding a public network listener or second charge executor. P0 manual mode physical validation remains independent and high priority.

## 2026-11-09 — Recipe Studio RS-1C: native parameter UI backed by the canonical metadata registry

**Status: SOURCE-TESTED, not deployed.** The existing browser editor `tools/recipe_visual_editor_prototype.html` now has an additional native-recipe panel beside the separate step-program panel. It selects all **12 canonical variants** (Ca/Ca/EFB/AGM × normal/recovery/conditioning/diagnostic), displays owner descriptions/units/defaults/min/max/type, permits overrides only for parameters actually executable by production stage owners, imports/exports versioned `{name,version,draft}` documents supported by the existing `NativeRecipeDraftLibrary`, and marks non-executable settings read-only. Previous step recipe editing remains separate. No device command, recipe START, new actor/service, new local network listener, new ACL or duplicate configuration registry.

**Canonical metadata** is built in `runtime/charge/programs/recipe_studio_native_catalog.py` from `native_recipes()`, `native_recipe_parameters()`, actual owner `VariableSpec` and each one-parameter draft passed through `validate_native_draft` + `require_supported_native_execution`. The browser loads generated `tools/recipe_studio_native_catalog.js`, produced by `tools/recipe_studio_offline.py catalog-native --output tools/recipe_studio_native_catalog.js`. Static catalog is a **generated UI snapshot, never the validation authority**; after any change in native specifications, regenerate it. `tests/test_recipe_studio_native_ui.py` asserts byte/semantic parity to current Python, so drift fails tests rather than silently presenting stale limits. A focused JS module `tools/recipe_studio_native_editor.js` implements rendering, input checks and JSON round-trip; the existing HTML remains source of layout and has no second embedded native rules registry.

**Usage:** open `tools/recipe_visual_editor_prototype.html` from PC on HOME-PC; use the new section 'Копия штатного интеллектуального рецепта' and 'Экспорт копии JSON'. To check and save selected file via **existing** backend: `python tools/recipe_studio_offline.py check-native --file native.json` and `python tools/recipe_studio_offline.py save-native --file native.json --library-root ./scratch-native-drafts`. Using a test library (not production) is intentional; no browser-to-node104 publish, not yet final 'Save' button. A new immutable version is chosen explicitly; stale or wrong-parent revisions are rejected by the already existing native library. Browsers can reject wrong types/out-of-range/unknown input locally but final Python admission also checks cross-field combinations and excludes unsupported policies.

**Acceptance:** `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q` for `tests/test_recipe_studio_native_ui.py` and 8 native/user recipe/visual/start/UI regression modules: **45 PASS, 0 FAIL, 47.21 sec**, `node --check` for both newly generated catalog and native editor + HTML inline script PASS; `git diff --check` PASS. Tests execute real JS via Node sandbox with synthetic DOM; catalog diffed to canonical Python. Production node104 remains D144 slot16 COMMITTED code source `3f50133`, unchanged and untested physically by this source-only stage.

**Next RS-1D:** make local authenticated browser→library persistence through already available operator boundary, reusing `publish_step_document` / `publish_native_document` and existing catalog; first choose an existing safe user-facing process/ACL, not a new public or network service. Regression must test race/stale version, real reload and isolated state. P0 manual-control physical validation remains separately outstanding.

## 2026-11-09 — RS-1D local browser→canonical library persistence (source-only)

**Status:** implemented on HOME-PC source branch; not deployed on node104 and never sends device commands. The existing HTML `tools/recipe_visual_editor_prototype.html` gains **«Проверить в библиотеке» and «Сохранить новую версию»** buttons for **both** step SET/OFF/WAIT and native parameter copies. There is no second charger or recipe executor. Actions use new browser-only `tools/recipe_studio_save.js` and existing native editor UI to call an **explicitly started, short-lived localhost bridge** `tools/recipe_studio_local.py`. It invokes only `inspect_step_document/publish_step_document` or `inspect_native_document/publish_native_document` from the existing canonical implementation. Save returns the identity/version/readback digest or native base, and `physical_start_authorized=false` in all cases. No START/STOP/output/HA/ESP/firmware routes exist; backend does not import hardware execution.

**Launching from HOME-PC:** double-click `E:\CODEX\rd6018_bot\tools\start-recipe-studio.cmd`. This starts a transient Python server from the existing WSL Ubuntu-24.04 environment, opens `http://127.0.0.1:8768/studio`, and keeps the terminal alive only while the local editor is in use. The chosen scratch storage path is `E:\CODEX\rd6018_bot\.recipe-studio-local\` (mapped to /mnt/e...), separated into `steps/` and `native/`; this directory is gitignored. Browser opened as `file://` cannot save, because the bridge is required. Closing the terminal stops the bridge. If port 8768 is already used, launching fails visibly rather than silently picking a public port.

**Browser boundary:** HTTP binds only `127.0.0.1`, verifies Host, same-origin POST Origin, JSON Content-Type, short-lived random capability token via custom header, 256 KiB input limit; no CORS wildcard. The sensitive `studio-config.js` token is given only to a same-origin subresource fetch from `/studio` with `Sec-Fetch-Site: same-origin` and exact local Referer, to prevent foreign websites loading it as a JavaScript tag. Files served from fixed allowlist; no arbitrary files, templating, shell exec, arbitrary destination paths or actuator interfaces. Every save uses the *same* original immutable library and production schema/preflight; result reload is verified. A thread lock serializes local saves; version mismatch and no-overwrite hardlink publication reject duplicate/stale revisions. The local token is not equivalent to the Telegram operator ACL and is **not** used for remote/prod exposure. Existing native `VariableSpec` generated catalog remains read-only display; Python validation authoritative.

**Acceptance:** 50 PASS, 0 FAIL on browser bridge, native PC UI, canonical conversion, offline importer, preflight, atomic-save and START-selection regression; `node --check` for all edited JS and extracted inline HTML script; `git diff --check` PASS. `tests/test_recipe_studio_local_bridge.py` verifies both kinds, save→readback, immutable v1/v2, repeated/stale writes, CSRF/Host/Content-Type, token leak via cross-site script, path traversal, absent hardware routes. No GUI browser automation yet; DOM/JS tests remain in Node. Runtime node104 still prior installed D144 source; hardware mode P0, physical START, MAIN→MIX, and zero OVP/OCP firmware semantics are separate outstanding tasks.

**Next:** RS-2 operator-facing history/version selection, archive/revision comparison, and user-friendlier rendering for step recipes, using this same local boundary and canonical library. Do not turn the local bridge into a persistent production service or silently upload local recipes to node104. Physical P0 START/mode acceptance is still urgent and independent.


## 2026-11-09 — RS-2: local recipe history, immutable revision load, diff and archival

**Status:** RS-2 source implemented and offline verified; node104, HA102, ESP, firmware, physical output and running production untouched. The existing PC HTML now contains the "Библиотека рецептов · версии и архив" panel; user can select step/native collection and recipe, inspect all historical version numbers, load a chosen saved version into the **same existing editor** as an unsaved `latest+1` draft, compare arbitrary existing versions via safe textual diff, or archive with explicit browser confirmation. Archived history remains readable and comparable but cannot be opened for editing or receive new versions. Step visual import uses existing `visualFromCanonical`; native import uses existing `inspectDraft`; neither re-implements the charging algorithms.

**Authoritative owners reused:** `RecipeLibrary` and `NativeRecipeDraftLibrary` for load/versions/save, `RecipeCatalog` for step list/archive, `NativeRecipeDraftLibrary.archive` for native archival (added to the same owner), `runtime/charge/programs/recipe_studio_history.py` as pure read/diff dispatcher only. Both `RecipeLibrary.save` and `NativeRecipeDraftLibrary.save` reject new revisions when `.archived` exists; prevents bypass through direct calls by editor components. Historical `vN.json` bytes are never changed. `tools/recipe_studio_local.py` adds only `/api/list`, `/api/load`, `/api/compare`, `/api/archive` behind the existing localhost Host/Origin/capability-token check, fixed JSON shapes and explicit identity fields; no arbitrary paths or actuator endpoints. `tools/recipe_studio_save.js` and `tools/recipe_studio_history.js` implement browser UI; the same `tools/start-recipe-studio.cmd` remains the entry point, using isolated `.recipe-studio-local/` storage.

**Behavior:** `load` returns the exact immutable existing revision and the browser chooses `latest+1`; saving still requires canonical Python validation and same library optimistic version policy, so stale/racing saves are refused. `compare` performs canonical sorted-key JSON diff (version label excluded from content, preserving meaningful parameter changes), up to 24000 output characters. Archive is permanent from this UI (readable, no delete); no silent restore or deletion. PC-local scratch library does not replicate to node104 or modify pinned sessions. Native source selection remains fixed across revisions. Dynamic MAIN/MIX are not mapped into primitive SET/OFF steps.

**Acceptance:** WSL Ubuntu 24.04 pytest for 11 Recipe Studio, step/native admission, visual canonical bridge, atomic save, catalog, preflight, native draft library and START selection regression modules: **67 PASS, 0 FAIL, 63.61 seconds**. JavaScript syntax checks: `recipe_studio_history.js`, `recipe_studio_save.js`, `recipe_studio_native_editor.js`, and extracted HTML inline script PASS. `git diff --check` PASS. End-to-end HTTP tests in `tests/test_recipe_studio_history.py` cover two native/step revision chains, exact readback, compare, archival preserving bytes, read-only archive, direct-library bypass rejection, invalid paths and unsupported production endpoints and same-origin credential boundary.

**Next:** RS-3 Telegram user-friendly UI on the existing `runtime/ui/telegram/recipes.py` and `recipe_buttons.py`: version history and copy/edit/save next revision, reuse canonical stores, preserve one Telegram panel lifecycle. Physical P0 manual control, START/OVP/OCP zero semantics and MAIN→MIX transition tests remain outstanding and are independent of this source-only recipe editor effort.

## 2026-11-09 — RS-3A Telegram version navigation, copy and archival

Source-only improvement in **existing** `runtime/ui/telegram/recipe_buttons.py`; no new Telegram UI owner, service, ACL or charge executor. Individual step recipe panel now includes inline actions "История версий", "Копировать", "В архив". History is paginated (8 per page), loads immutable versions via existing `recipes:view:` route, and preserves Telegram callback 64-byte size cap. Copy calls existing `RecipeCatalog.duplicate` with generated `copy_<random>` name, creates independent v1 and routes to established step editor. Archive requires a separate confirmation/cancel callback, calls `RecipeCatalog.archive`, does not alter version bytes and prevents further edits via the canonical `RecipeLibrary.save` guard from RS-2. Existing `app._check_chat_and_respond` applies to all operations, and all responses explicitly avoid physical START. Native recipes remain their independent catalog; no native execution altered.

**Acceptance:** `tests/test_recipe_telegram_history_buttons.py` + `tests/test_recipe_real_callback_chain.py`, `tests/test_unified_recipe_catalog_ui.py`, `tests/test_user_recipe_catalog_pagination.py`, `tests/test_user_recipe_editor_pagination.py`, `tests/test_recipe_empty_preview_entry.py`: **12 PASS, 0 FAIL**, ~26.5 sec. Includes chain history→duplicate→archive-confirm, unchanged source versions, archive blocking new versions, 18-version pagination, Telegram callback max64, refusal for missing source, denied-chat mutation. `git diff --check` PASS. Not installed to node104; local source development only.

Next: RS-3B native user-copy Telegram browser, safe revision through existing `NativeRecipeDraftLibrary` with supported-override validation and no new persistence channel; then independent RS-4 acceptance. Production physical D151–D153/START and MIX transition remain separate outstanding work.

## 2026-11-09 — RS-3B native Telegram copy/browser and strict supported override check

Extends the existing `runtime/ui/telegram/recipe_buttons.py` owner; no second router or service. The 12 canonical native variants now offer a "Создать свою копию" button. This creates a non-energizing draft `copy_<10hex>` v1 through the **same** `NativeRecipeDraftLibrary` object used by the registered `/native_copy` and `/native_set` commands (passed into `install_recipe_buttons`). Adds "Мои копии штатных программ" listing and versioned read-only view with up to 10 recent versions. Callback length <=64 bytes is enforced for dynamically generated buttons; very long names are not presented as oversized callback payloads. Each callback uses the canonical chat ACL and returns no hardware activation or execution grants.

**Important correction:** Telegram `/native_set` previously called only `validate_native_draft` before `save`, allowing syntactically/range-valid overrides unsupported by the production stage owners. It now additionally calls `require_supported_native_execution`, matching Recipe Studio local/CLI and START admission. Existing immutable version semantics and archive guards stay owned by the same native library.

**Acceptance:** `tests/test_recipe_telegram_native_drafts.py` + `tests/test_recipe_telegram_history_buttons.py`, `tests/test_recipe_real_callback_chain.py`, `tests/test_unified_recipe_catalog_ui.py`, `tests/test_user_recipe_catalog_pagination.py`, `tests/test_user_recipe_editor_pagination.py`, `tests/test_recipe_empty_preview_entry.py`: **15 PASS, 0 FAIL**, 29.74 seconds. Confirmed native copy, readback and view, denied chat, missing canonical native ID, step history/copied/archive workflow and callback pagination. `git diff --check` PASS. Not deployed to node104 or connected to physical RD6018; still source-only.

**RS-3 overall:** step buttons history/copy/confirm archive (RS-3A), native canonical program copy and draft view (RS-3B). Editing native parameters continues through `/native_set`, creating immutable revisions, now with supported-execution check. A dedicated inline native parameter adjustment UI remains possible for later UX iteration, not marked complete. Next RS-4: integration/regression of PC and Telegram stores, preserve pinned selection, verify no START/output routes and prepare source release with install/rollback plan; physical P0/START/MIX remains a separate urgent gate.

## 2026-11-09 — RS-4 integration gate 1: unified source regression after RS-3

RS-3A committed `b0fa187`; RS-3B committed `cf32156`. After both, a unified source-only 17-module Recipe Studio/Telegram integration run exercised browser local history/API, native and step immutable stores, version archive and readback, visual JSON bridge, offline admission, Telegram ACL and real callback chains, native supported-override guard, preflight and START selection. Command:
`PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q tests/test_recipe_telegram_native_drafts.py tests/test_recipe_telegram_history_buttons.py tests/test_recipe_studio_history.py tests/test_recipe_studio_local_bridge.py tests/test_recipe_studio_native_ui.py tests/test_recipe_studio_native_import.py tests/test_recipe_studio_offline_import.py tests/test_recipe_visual_canonical_bridge.py tests/test_user_recipe_atomic_save.py tests/test_user_recipe_catalog.py tests/test_user_recipe_preflight.py tests/test_native_recipe_draft_library.py tests/test_native_recipe_start_selection.py tests/test_recipe_real_callback_chain.py tests/test_unified_recipe_catalog_ui.py tests/test_user_recipe_catalog_pagination.py tests/test_user_recipe_editor_pagination.py`
**Result: 81 PASS / 0 FAIL, exit 0, 81.99 s**. Clean working tree before this note, branch `feature/main-mix-countdown-display` ahead of owned origin by 13 commits. No node104/HA102/ESP actions or charging hardware actuation.

Remaining RS-4 release boundaries: review/validate PC browser UI with a real browser on HOME-PC; confirm that the two local scratch libraries are isolated from production; release package/update plan, compatibility and rollback with the established node104 D144/D145 mechanism; independent physical START/MAIN→MIX/OVP-OCP zero-write and PB_MANAGED↔HANDS_OFF acceptance. No production PASS or installation solely from source tests. User-approved plan continues without redesign, extra authorizations or duplicate engines.


## 2026-11-09 — RS-4 real Edge E2E / local bridge fix

Verified on HOME-PC using actual Microsoft Edge headless via Chrome DevTools Protocol, local loopback `127.0.0.1:8768`, and isolated scratch library `.recipe-studio-local/rs4-e2e-20261109`. Initial real-browser run exposed an actual defect: `tools/recipe_studio_local.py` sent `Referrer-Policy: no-referrer` while `/studio-config.js` required the browser's same-origin `Referer: .../studio`. This prevented the browser client from receiving its local capability token, although static HTTP and unit tests passed. Corrected response header to `Referrer-Policy: same-origin`: same-origin subresources carry the necessary Referer, cross-origin websites receive none. Cross-site `Sec-Fetch-Site`, Host, Origin and token defenses remain in place. Added HTTP regression in `tests/test_recipe_studio_local_bridge.py`.

Real-browser interactive step workflow PASS: JS client `connected=true`; click Save v1; refresh library; click Open as v2; edit voltage 14.2 -> 14.4 in browser input; click Save v2; compare v1/v2, voltage diff observed; confirm archive; test Save v3 and receive precise `recipe is archived; it cannot receive new versions`. Successful isolated example: `rs4_e2e_197709807`; v1/v2 preserved. The CDP smoke driver is scratch-only at `.recipe-studio-local/rs4-browser-e2e.js` and is not a production runtime module.

Targeted regression: 41 PASS / 0 FAIL in 30.22s for bridge, history, native UI and canonical visual conversion tests. Production node104, ESP, charging output and libraries untouched. Scope remaining: native browser UI interactive E2E and release/rollback compatibility, plus independent physical START/MAIN/MIX/OVP-OCP firmware acceptance. Do not claim production PASS from this source-only acceptance.


### RS-4 real-browser native recipe E2E closure

Using the same isolated HOME-PC Edge/loopback setup, native EFB copy workflow also PASS: save v1, select the native recipe in the same history UI, load it as v2, change editable `charge.main.efb_voltage_v` to 14.6, save v2, compare versions and observe the 14.6 diff, archive with confirmation, then attempt v3 and observe `native draft is archived`. Exact scratch example `rs4_native_97856376`. The combined Edge CDP test in `.recipe-studio-local/rs4-browser-e2e.js` finished exit 0 and tested both step and native flows. This closes the interactive HOME-PC browser gate for both recipe families, not the production deploy or hardware gate.


### Final RS-4 targeted source regression and release boundary

After commit `72d754a`, the complete 17-module integration set returned **84 PASS, 0 FAIL, exit 0 in 80.84 seconds**, with the new referrer-policy test included. Real-browser Edge E2E for both step and native versions passed (details above). Current readiness: RS-4 local browser and source acceptance PASS; release to node104 remains HOLD. Existing D090/D144/D145/D138 owners must be respected; prior `docs/assistant/RD6018_AAA17C7_D145_RELEASE_READINESS_2026-11-08.md` explicitly records absent fresh paired source/preimage inventory, Python 3.11 candidate venv, and physical D091 proof. No staging/activation on node104 is authorized by these tests. The local `.recipe-studio-local` scratch history must not enter a release archive or be copied to production.


## 2026-11-09 — RS-4 exact-source offline release staging and archive acceptance

**Exact candidate:** `cd26376a61d3dd941b5f5afedb6abeddb8851161` on `feature/main-mix-countdown-display` (owned origin `timspb/rd6018_bot`, 15 local commits ahead when staged). This is a source-only candidate, **not** a D138-prepared installable production payload.

Existing `tools/node104_atomic_deploy.py stage` was run exclusively in HOME-PC WSL under `/tmp/rd6018-rs4-release-20261109/`. Output: `/tmp/rd6018-rs4-release-20261109/release-cd26376a61d3dd941b5f5afedb6abeddb8851161-f45t9gqw`. No node104 access or production writes.

**Archive integrity PASS:** 1448 manifest-listed tracked files, 0 digest/size mismatches, 0 missing/extra files; scratch `.recipe-studio-local/` paths absent. `source.tar` SHA256 `f38669599792a4bb4352a0ebf4d77a9cfab5243f993a3751a6a1869c664b472b` matches release manifest; `RELEASE_MANIFEST.json` SHA256 `563d348a4adccb212a3844d378b74194a14ed4731212d0b3fad80f6d822ecebc`; `STAGED_OK` records `tree_verified=true`, `directory_fsync=true` and matching manifest digest. Both values are tied to this exact source candidate, not earlier D145/D146 profiles.

**Git-less source-tree acceptance PASS:** from the staged `tree/` using HOME-PC WSL existing dev Python environment and Node.js, all 17 Recipe Studio/Telegram integration modules completed **84 PASS / 0 FAIL in 27.48 s**. A focused 3-module bridge/history/native-UI run from this tree also passed 31/31. This is source acceptance using the existing development environment; it is **not** evidence of a new Python 3.11 production venv, nor is it the whole repository's >3000-test suite.

**D138 and production release HOLD:** D090 offline `source.tar`/manifest/`STAGED_OK` packaging is distinct from the full D138 candidate layout (`tree/`, its expected D138 manifest schema and paired verified `venv/`). D138 still requires a contemporaneous installed-app preimage/Guard/session observation and working Python 3.11 candidate environment with `pip check` and byte inventory. Existing `tools/node104_d145_entrypoint.py` remains pinned to an earlier exact source/preimage/profile. Do not repoint it blindly, reuse old D146 identities, or claim activation authorization. Read-only production physical D091/ESP Native + HA observation and fresh D090/D144 journal review remain mandatory via the existing permitted owner; prior safety-policy refusals are not to be bypassed. No deploy, service stop/restart, START, OFF, setpoint, OVP/OCP write or firmware action performed.

**Next:** use the already established authorized read-only production pathway to obtain fresh node104 installed-app/venv/session/Guard/journal and independent ESP Native/HA proof; then build the exact source-paired D145 profile and D138 Python 3.11 candidate using the existing owners and run prepare-only admission. Production execution remains separately gated. Source-only Recipe Studio RS-4 is complete; no new executor or deployment authority is needed.


## 2026-11-09 — exact source archive full-suite acceptance

Full project tests executed directly from frozen Git-less offline release tree for source `cd26376a61d3dd941b5f5afedb6abeddb8851161` at `/tmp/rd6018-rs4-release-20261109/release-cd26376a61d3dd941b5f5afedb6abeddb8851161-f45t9gqw/tree` (HOME-PC WSL only). Command: `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q tests --disable-warnings`.

**Result 3131 passed, 10 skipped, 6 warnings, exit 0, 179.28 seconds.** Initial unscoped `pytest -q` collection failed on auxiliary `tools/acceptance_guard/test_sinks.py` importing unavailable old `managed_runtime_safety`. Canonical `tests/` suite collected and passed without source changes. No regression was concealed.

Offline archive SHA256 `f38669599792a4bb4352a0ebf4d77a9cfab5243f993a3751a6a1869c664b472b`, manifest SHA256 `563d348a4adccb212a3844d378b74194a14ed4731212d0b3fad80f6d822ecebc`, 1448 files with 0 byte mismatches, 0 scratch files. **Full source regression PASS; D138 Python 3.11 + fresh preimage HOLD; D145 production activation HOLD**. No node104/ESP/HA/START/OVP/OCP/service actions were executed.


## 2026-11-09 — D138 readiness probe / Python 3.11 offline compatibility

Reviewed current HOME-PC repository at `abe3b0c` (clean tree before this note), existing D138 source preflight and D145 pinned entrypoint. Both available WSL distros (`Ubuntu-24.04`, `RD6018-CI`) contain Python 3.12.3, not 3.11; Windows `py` launcher and common Python311 paths not available; apt package lookup gave no Python 3.11 candidate. Existing D145 source/preimage/profile pins are historical and must not be reused for new `cd26376` source.

Ran existing nine D138/D139/D142/D143/D144/D147/D148/D149 test modules on HOME-PC: **78 PASS / 0 FAIL (30.36 s)**. Located preexisting offline Docker `python:3.11-bullseye` image. Ran exact archived `cd26376` source with `docker run --rm --network none --read-only` and only read-only mounts: Python **3.11.13** compiled **1017 `.py` files** via built-in `compile()`, **SYNTAX PASS**. No writes to source, user network or hardware. Separate image `pcp-p0k-builder:ci-pinned-python311` also reports Python 3.11.13 but has no `pytest` installed. No Python 3.11 full dependency suite or production virtual environment has been established.

**D138 PREPARE HOLD** remains for (1) approved node104-compatible Python 3.11 production venv with locked requirements, `pip check`, byte inventory; (2) contemporaneous installed-app preimage, session/Guard and journals via the existing authorized owner; (3) source/venv D138 manifest and fresh physical D091 independent ESP Native + HA proof. The existing prior policy refusal for production observer execution must NOT be bypassed by alternative transports, wrappers or tools. Current offline D090 archive is not a D138 full prepared stage. No new D145 profile was invented. No production writes, node104 service actions or charging commands were performed.


## 2026-11-09 — D138 offline dependency availability and frozen-tree contract audit

Executed D138/D139/D142/D143/D144/D147/D148/D149 nine-module suite **directly from the Git-less frozen `cd26376` release tree** with existing HOME-PC WSL dev venv: **78 PASS / 0 FAIL / exit 0 / 5.41 s**. This is independent of the prior 3131-test full source run and rechecks established release-owner/preflight contracts without staging on node104.

Both HOME-PC WSL distributions (`Ubuntu-24.04`, `RD6018-CI`) have Python 3.12.3 only. Local Docker images `python:3.11-bullseye` and `pcp-p0k-builder:ci-pinned-python311` offer Python 3.11.13 with base pip/setuptools/wheel but do not contain the project's dependency set. A **read-only, network-disabled, `--no-index --dry-run`** pip check against the exact frozen release `requirements.txt` fails at `aiogram>=3.0`: `No matching distribution found`. This is an offline wheel availability blocker, **not** a version incompatibility verdict. Python 3.11 syntax of all 1017 archived files was already accepted; runtime imports and production Python 3.11 venv remain unproven. No host Python install, pip download or dependency upgrade occurred.

D138 exact inputs are (1) matching D138 schema source manifest/tree with verified archive identity, (2) complete Python 3.11 candidate `venv/bin/python` with `pip check`, immutable byte/mode inventory and 256 MiB free, and (3) **fresh contemporaneous node104** installed-app preimage SHA plus original session/Guard state. The D090 source-only `source.tar`, `RELEASE_MANIFEST.json`, `STAGED_OK` currently available uses a *different* offline package format. Existing D145 entrypoint remains bound to older release identity; no new D145 profile may be asserted without fresh preimage and observer proof. Fresh D091 / independent ESP Native + HA, D090/D144 journal, no-activation owner prepare gate and production Python 3.11 dependencies remain **HOLD**. No production observer transport substituted for a previously refused execution, no node104, service, firmware, charging or OVP/OCP actions performed.

Next admissible implementation: obtain approved, source-compatible Python 3.11 dependencies/wheelhouse (or build inside the already approved node104 Python 3.11 preparation path) and current authorized node104 read-only owner evidence. Re-run D138 prepare-only with exact paired source/preimage, not a fake/synthetic preimage. Source regression PASS; activation HOLD.
