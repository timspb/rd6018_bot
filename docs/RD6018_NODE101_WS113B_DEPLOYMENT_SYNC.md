# RD6018 Node101 WS113B Deployment Sync

Дата: 2026-09-16  
Статус: `BLOCKED_WITH_REASON`

## Artifact verification

Указанный local HEAD `5c92750` существует, но это commit `refactor(v3):
extract legacy domain boundaries`. Проверка содержимого показала:

- `application/manual_phase_lifecycle.py` отсутствует в commit;
- `application/manual_execution_boundary.py` отсутствует в commit;
- `manual_mode.py` отличается от commit незакоммиченными изменениями.

Следовательно, `5c92750` не является deployable WS113B artifact.

## Current deployment

Ранее read-only проверенный node 101:

- deployed HEAD: `10af870`;
- `rd6018-bot.service`: active;
- WS113B boundary не подтверждён.

## Actions not performed

Из-за отсутствия проверенного commit/artifact не выполнялись:

- копирование или checkout production tree;
- restart `rd6018-bot.service`;
- START/STOP;
- `set_voltage`/`set_current`;
- physical commands.

## Required next step

Сначала нужен отдельный проверенный release commit, содержащий как минимум:

- `manual_mode.py`;
- `application/manual_phase_lifecycle.py`;
- `application/manual_execution_boundary.py`;
- boundary tests;
- deployment tests.

После этого допустим deployment exact SHA с backup, compile/test gate, restart и
read-only import/log verification. Dirty working tree нельзя использовать как
неидентифицируемый production artifact.
