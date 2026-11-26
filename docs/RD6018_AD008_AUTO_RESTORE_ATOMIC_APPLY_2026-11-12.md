# RD6018 AD-008 — АТОМАРНАЯ ГРАНИЦА ПРИМЕНЕНИЯ AUTO RESTORE (2026-11-12)
**ГЛАВНАЯ ЗАДАЧА — ПОЛНАЯ ДЕКОМПОЗИЦИЯ / МОДУЛЬНОСТЬ. ChatGPT — архитектор и приёмщик; Luna — исполнитель.**

## Подтверждённая проблема
`runtime/charge/persistence.py::restore_session` в текущем WIP изменяет контроллер до завершения разбора всех числовых полей документа. Fake fault injection `tests/test_modularization_auto_restore_atomic_admission.py` выполнил реальный restore_session и подтвердил частичную мутацию при повреждении ah_limit, agm_stage_idx, safe_wait_target_i, target_voltage и target_current. Независимая Windows проверка 41 PASS +38 subtests; тест фиксирует старый дефект, не объявляет его корректным поведением. P4-3 источник: `.recipe-studio-local/REPORT_MOD_P4_3_AUTO_RESTORE_AUDIT_20261112.txt`.

## Архитектурное решение
1. Разделить фазы: read/decode -> immutable native/retired/Guard admission -> pure numeric normalization -> **только затем** изменение полей controller -> persistence/continuation. Никаких новых permit, подписей, глобального singleton или дополнительной FSM.
2. Реализация — чистый узкий `runtime/charge/restore_projection.py`, возвращающий immutable DTO для восстановленных скалярных полей. Хранилищем и владельцем состояния остаются `runtime/charge/persistence.py` и действующий controller. Не дублировать поля/процессы в памяти после применения.
3. Первый P4-5 срез: валидировать и материализовать перед первой мутацией минимум ah_limit, current_retries, agm_stage_idx, start_ah, stage_start_ah, safe_wait_target_v/i, target_voltage/current, target_finish_time и все напрямую приводимые float/int поля; preserve existing defaults/clamps/fallbacks. Механизм guarded MAIN/candidate и компенсация trace остаются без изменений, а их прежние ранние побочные эффекты рассмотреть отдельно.
4. Любой malformed scalar обязан отказать до применения частично валидированных данных; ошибки, где legacy намеренно использовал fallback (stage_start_voltage/current/temp, stage timers), сохраняют fallback. Нельзя делать авто Output ON при недостоверной сессии.
5. Доказательства: fake rejected document -> zero mutations of controller authority fields, accepted legacy document -> identical values/stages/timers, guarded permit/candidate parity, no extra physical calls. Независимая Windows full relevant tests, git diff --check.
6. Production node104 не обновлять до полного release/safety acceptance. Никаких реальных физических операций в ходе P4-5.
