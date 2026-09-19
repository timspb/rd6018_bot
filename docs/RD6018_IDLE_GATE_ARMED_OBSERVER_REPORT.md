# RD6018 Idle Gate & Armed Observer — WORKSTREAM 81

Статус: `OBSERVER_ARMED_BEFORE_START`

## Fresh arm marker

`OBSERVER_ARMED_BEFORE_START`

- observation_id: `ws81-20260915T130058Z`
- timestamp: `2026-09-15T13:00:58Z`
- source health: node 101 SFTP read-only + HA 102 state API read-only
- current V2 session state: `stopped` / idle gate accepted
- output voltage/current: `0.0 V` / `0.0 A`
- battery voltage: `12.7 V`
- telemetry confidence: HIGH for idle/off gate

## Idle gate

Подтверждённого свежего состояния `V2=idle` нет. Последние доступные
observation-артефакты фиксируют `active`/`ARMED_WAITING`, а переход
`active → idle` не наблюдался.

Это было закрыто fresh read-only observation 2026-09-15T13:00:58Z:
persisted V2 state `stopped` согласован с HA output/current `0.0/0.0`.

Состояния `active`, `MIX`, `HOLD` и `SAFE_WAIT` не принимаются как idle.
Поэтому marker `OBSERVER_ARMED_BEFORE_START` не создавался: его создание без
fresh idle evidence было бы ложным подтверждением pre-START окна.

## Проверка gate

| Проверка | Результат |
|---|---|
| observer composition available | READY |
| read-only mode | READY |
| fresh V2 idle snapshot | PASS |
| source timestamp/confidence | PASS |
| telemetry availability at idle | PASS |
| `OBSERVER_ARMED_BEFORE_START` | CREATED |

## Разрешённое продолжение

После marker observer ждёт только естественный `idle → START/active`.
Короткое окно 13:00:58–13:01:07Z перехода не показало; capture продолжается
в режиме ожидания. До реального перехода graph/log/audit не заполняются.

Команды, writes, lease operations, ownership transfer, deployment и physical
execution не выполнялись. Fake START, reconstructed session и synthetic identity
не создавались.
