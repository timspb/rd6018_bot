# RD6018 Controlled Test Suite Execution

Статус: `CONTROLLED_TEST_SUITE_COMPLETE`

Режим: controlled hardware test через существующий V2/HA execution boundary.  
Дата live-прогона: `2026-09-15` 14:45–14:47 UTC.

## Safety invariants

- maximum current: `0.9 A`;
- voltage targets проверялись относительно свежего Vbat перед каждым START;
- OutputStateConfidence и Protection Status Code проверялись перед каждым тестом;
- после каждого подтверждённого ON выдерживалось не менее `10 s`;
- ранний STOP не выполнялся;
- физический fault намеренно не создавался.

## Physical test matrix

| Test | Settings / change | ON hold | Max current | Result |
|---|---|---:|---:|---|
| 1. START/STOP BASIC | 13.0 V / 0.4 A | 10.126 s | 0.39 A | PASS |
| 2. LOW CURRENT CHARGE | 13.0 V / 0.5 A | 10.157 s | 0.49 A | PASS |
| 3. CURRENT CHANGE WHILE ON | 0.4 A → 0.8 A | 10.195 s | 0.79 A | PASS |
| 4. VOLTAGE CHANGE WHILE ON | 13.0 V → 13.5 V, 0.5 A | 10.157 s | 0.49 A | PASS |
| 5. CC/CV TRANSITION PREPARATION | 13.8 V / 0.5 A | 10.165 s | 0.48 A | PASS |

Для всех пяти тестов финальный readback был `Output State Code V2=0 / OFF`,
`current=0.0 A`, `Protection Status Code=0 / normal`.

## Failure-path checks (read-only)

Проверены без изменения железа:

- stale Modbus age → `DENY`;
- protection code 1 → `DENY`;
- invalid Output State Code → `DENY`.

## V2/V3 shadow parity

Статус: `UNKNOWN_LEGACY_NO_IDENTITY`.

Live V2 payload не экспортировал V3 shadow decision, `session_id`, `trace_id` или
`decision_id`. Поэтому `MATCH/EXPECTED_DIFFERENCE/DIVERGENCE` не выдумывались.
Physical V2 observations сохранены; parity требует отдельного подключённого
read-only V3 shadow pipeline.

## Evidence limitations

Direct controlled runner зафиксировал before/on/change/hold/stop/final snapshots
и readback. Production V2 path не отдаёт отдельные graph/log/audit references и
lifecycle identity; эти поля отмечены как `UNKNOWN`, без synthetic events.

В ходе первого runner-а был обнаружен pre-existing Output ON после прерывания
runner-а. Он наблюдался 10 секунд, затем штатно выключен и подтверждён OFF до
повторного чистого запуска матрицы.

Ownership, V3 direct execution, deployment и production configuration не менялись.
