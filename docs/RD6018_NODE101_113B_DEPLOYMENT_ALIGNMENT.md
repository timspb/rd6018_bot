# RD6018 Node101 113B Deployment Alignment

Дата: 2026-09-16  
Режим: read-only alignment check; production и hardware не изменялись.

## Итог

**`BLOCKED_WITH_REASON`**

Node 101 не выровнен с development tree после WS113B.

## Проверка development tree

Локальная ветка: `codex/v3-runtime-consolidation`  
Локальный HEAD: `5c92750`

WS113B присутствует локально:

- `application/manual_phase_lifecycle.py`;
- `application/manual_execution_boundary.py`;
- `manual_mode.py` импортирует и создаёт обе boundary-модели;
- прямые `self.app.hass.set_current/set_voltage` из `manual_mode.py` удалены.

## Проверка node 101

- host: `192.168.1.101`;
- `rd6018-bot.service`: `active`;
- deployed HEAD: `10af870`;
- deployed worktree содержит локальное изменение `config/charge/manual.yaml`;
- deployed runtime не подтверждает наличие `ManualPhaseLifecycle`/`ManualExecutionBoundary`.

Следовательно, deployed commit не содержит WS113B и runtime/version match отсутствует.

## Почему deployment не выполнен

Development tree содержит большой набор незакоммиченных и untracked изменений,
включая runtime, конфигурацию, V3 application modules и tests. Exact release
branch/SHA для deployment не задан; деплой такого dirty tree означал бы замену
production runtime без проверяемого commit identity и нарушил бы deployment
boundary.

Backup/checkout/install/restart не выполнялись. Physical commands, START/STOP и
hardware changes не выполнялись.

## Acceptance matrix

| Проверка | Статус |
|---|---|
| deployed commit содержит WS113B | BLOCKED |
| ManualPhaseLifecycle active on node101 | BLOCKED |
| direct manual→setter path absent on node101 | BLOCKED |
| local boundary tests | PASS |
| local compileall | PASS |
| deployed/runtime version match | BLOCKED |
| physical side effects | NONE |

Для статуса `NODE101_ALIGNED` нужен отдельный разрешённый deployment exact
commit/SHA с backup, install, compile/test gate и проверкой service logs.
