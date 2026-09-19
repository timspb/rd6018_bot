# RD6018 Operator UI Scenario Validation

Статус: `OPERATOR_UI_SCENARIO_VALIDATED`

Проверены synthetic/read-only сценарии:

- MANUAL + MIX;
- AUTO + MAIN;
- HOLD с условием удержания;
- SAFE_WAIT с причиной ожидания;
- DONE;
- legacy session без identity;
- отсутствующая telemetry;
- stale source.

Проверки охватывают header, battery, phase, AUTO/MANUAL, CC/CV, graph state,
current-session log, `UNKNOWN`/degraded handling и отделение diagnostics от
charge card.

Все snapshots synthetic. В тестах отсутствуют HA, ESPHome, RD, Modbus, runtime
writers и physical execution. Controls проверяются как presentation-only.
