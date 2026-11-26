# RD6018 AD-006 — OPERATOR PAUSE OWNERSHIP / 2026-11-12
**ГЛАВНАЯ ЗАДАЧА: ПОЛНАЯ ДЕКОМПОЗИЦИЯ И МОДУЛЬНОСТЬ ВСЕГО ПРОЕКТА. CHATGPT = ЕДИНСТВЕННЫЙ АРХИТЕКТОР/ПРИЁМЩИК; CODEX LUNA = РУКИ.**

## Основание P6-10 (source-only)
- `runtime/production_runtime.py` содержит mutable `operator_pause_started_at`, JSON-файл `operator_pause_state.json`, функции `_save_operator_pause_state`, `_load_operator_pause_state`, `_clear_operator_pause`, `_operator_pause_active` и `_shift_operator_pause_clocks`.
- `_operator_pause_toggle` отвечает за UI request, verified OFF, сохранение сессии, затем pause timestamp; resume проверяет телеметрию и active/session restore, программирует V/I, запрашивает verified ON и **только затем** сдвигает stage clocks и очищает pause. SAFE_WAIT resume не включает Output.
- `_shift_operator_pause_clocks` меняет поля charge_controller и _main_sample_evidence. Это engine responsibility, а не repository/state.
- Pause sidecar `{ "started_at": <unix epoch seconds> }` — отдельный от charge_session.json. Существующие тесты почти не покрывают malformed/stale/missing pause sidecar, clock shift и failure OFF/ON.
- Аудит P6-10 source-only; наличие 900s edge lease и safety watchdog не является доказательством физической приёмки node104.

## Принятое разделение
1. **OperatorPauseState owner** — один компактный объект paused_since + путь/запись/чтение operator_pause_state.json. Использовать имеющееся `runtime/operator/`, никакого нового background service/dispatcher/framework или второй state truth. Строковый JSON-контракт старых инсталляций сохранён.
2. **Charge Engine clock adjustment** — отдельная existing function/port owner для stage clock shifts; при первом переходе код сдвига не переписывать, лишь не перемещать в state writer.
3. **ExecutionPort/safety owner** — verified OFF/ON и admission. UI route не обходит их, pause state не умеет физические действия.
4. **Startup** — повреждённая/необъектная/нечисловая/неfinite пауза должна быть игнорирована безопасно, без Output ON. Пустая/отсутствующая sidecar → unpaused. Не добавлять требование подписи, ручного допуска или искусственного rearm.
5. **Stale valid pause** — текущие сценарии не менять самовольно. Сначала зафиксировать и проверить поведения valid pause/restore, orphan sidecar/explicit START и protected DONE; затем архитектор отдельно определит необходимое упрощение.
6. **Timer semantics** — сохранить прежний wall-clock duration и сдвиг **только после verified ON** при обычном resume; SAFE_WAIT сдвигается без включения Output. Не менять 900s lease, R16=3 OPP, 72h fuse.

## План
- **P6-11:** source-only fake tests на legacy pause state/storage and toggle success/failure, malformed JSON (историческую ошибку задокументировать, не маскировать), restore/save timing and output gate. Не вызывать физику/HA/ESP.
- **P6-12A:** один OperatorPauseState в `runtime/operator/` с совместимым JSON и безопасным atomic writer; isolated tests; production runtime не трогать.
- **P6-12B:** cutover `production_runtime` с сохранением тонких helper names и ownership clock shift, тесты parity+Manual/AUTO. Исключить второй mutable pause global.
- **P6-13:** отделить UI callback от применения pause/resume через существующие application APIs, только после end-to-end fake parity.
- Любые новые физические изменения запрещены до отдельной приёмки. node104 остается на старом релизе; git dirty tree сохранять, no commit/push/reset.
