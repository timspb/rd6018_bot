# RD6018 Post-Manual Boundary Migration Validation

Дата: 2026-09-16  
Режим: local regression + read-only deployment verification.

## Итог

**`BLOCKED_WITH_REAL_REASON`** для live controlled test.

Локальная post-migration проверка прошла. Физический controlled test не
выполнялся, потому что штатный node 101 ещё запущен с deployed HEAD `10af870`,
в котором отсутствует Workstream 113B boundary. Запуск физики на этом узле
проверил бы старый runtime и не являлся бы post-migration validation.

## Local validation

PASS:

- Manual START-related regression: 7 tests;
- Manual V2 runtime regression: 14 tests;
- Workstream 113B boundary tests: 3 tests;
- identity bridge: 6 tests;
- bridged-cycle contracts: 6 tests;
- V3 execution policy: 5 tests;
- V3 dry-run executor: 4 tests;
- operator HMI: 33 tests;
- operator dashboard: 11 tests;
- `compileall -q .`;
- `git diff --check`.

## Boundary checks

PASS:

- `manual_mode.py` не содержит прямых `set_current`/`set_voltage` вызовов;
- MAIN→MIX decision создаётся `ManualPhaseLifecycle`;
- targets и typed `ExecutionIntent` создаются до execution;
- `ManualExecutionBoundary` требует session/trace identity;
- V2 setter path сохраняет canonical readback verification;
- controlled `0.9 A` ограничение остаётся run-local envelope;
- `HassClient`, физический owner и hardware safety guards не менялись.

## Deployment read-only evidence

- node: `192.168.1.101`;
- `rd6018-bot.service`: active;
- deployed HEAD: `10af870`;
- deployed worktree имеет локальное изменение `config/charge/manual.yaml`;
- deployed `manual_mode.py` не содержит `ManualExecutionBoundary`/113B path.

## Physical controlled matrix

Статус: **NOT RUN**.

Не выполнялись START, target changes или STOP. Поэтому отсутствуют новые
доказательства:

- Output OFF→ON→OFF;
- ON hold >=10 s;
- current <=0.9 A;
- final current 0;
- protection OK;
- live post-migration identity/audit chain.

## Acceptance

`FINAL_VALIDATION_PASS` не заявляется. Для продолжения нужен отдельный
разрешённый deployment 113B на node 101 с backup, exact-head validation и затем
контролируемый тест через существующий V2 physical owner.
