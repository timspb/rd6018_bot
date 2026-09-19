# RD6018 Full V3/V2 Bridged Control Cycle

Статус: `FULL_BRIDGED_CONTROL_CYCLE_COMPLETE`

Перед live-проверкой добавлена только contract-level intent identity:
`ExecutionIntent.intent_id` создаётся при создании intent и передаётся в
`ExecutionIdentityEnvelope` вместе с `session_id`, `trace_id` и decision id.

Физический исполнитель, V2 owner, HA, ESPHome, Modbus и RD execution path не
изменялись. `StartOrchestrator` по-прежнему не создаёт physical request;
контролируемый live шаг, если разрешён safety preflight, выполняется только
существующим `HassClient.safe_enable_output()` V2 owner.

## Live evidence

Дата: `2026-09-15` 15:00 UTC. Все значения ниже получены через существующий
V2 physical owner; V3 не обращался к hardware напрямую.

Identity envelope:

- session_id: `c1148d88dd424e6f9ed7e5b84ad0c389`;
- trace_id: `cb338f5fff4c46929b6d52c0c11c27bb`;
- decision_id: `c2fba69e3d4b4a83bb47ed88a127d1d3`;
- intent_id: `8192518c83654826823df8830be97e96`;
- START bridge: `PROPAGATED`;
- STOP bridge: `PROPAGATED`.

Preflight:

- battery voltage: `12.78 V`;
- target: `13.0 V / 0.4 A`;
- Output State Code V2: `0 / OFF`;
- Modbus age: `3.1 s`;
- Protection Status Code: `0 / normal`;
- OutputStateConfidence: `ALLOW`.

START:

- request timestamp: `2026-09-15T15:00:42.063674+00:00`;
- physical Output State Code V2: `1 / ON`;
- first ON readback: `12.78 V / 0.0 A`;
- later settled observation: `12.85 V / 0.39 A`.

Mandatory ON hold:

- duration: `10.157 s`;
- snapshots: `10`;
- maximum current: `0.39 A`;
- protection: always `0 / normal`;
- Output State Code: always `1 / ON` after confirmation.

STOP:

- request timestamp: `2026-09-15T15:00:53.772304+00:00`;
- STOP bridge: `PROPAGATED`;
- final Output State Code V2: `0 / OFF`;
- final current: `0.0 A`;
- final protection: `0 / normal`;
- final Modbus age: `6.2 s`.

## Audit and lifecycle note

Identity correlation for START, hold and STOP was preserved in the bridge
evidence. The existing V2 runtime still does not export an independent
canonical `SessionStopped` event or external audit record; the STOP entry above
is the controlled boundary correlation and physical verification, not a
synthetic V2 event. No identity was created after the fact.

No ownership transfer, deployment change, V3 direct execution or hardware
bypass occurred.
