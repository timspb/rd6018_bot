# RD6018 V2/V3 Shadow Decision Bridge — WORKSTREAM 91

Статус: `SHADOW_DECISION_BRIDGE_READY`

Bridge является read-only comparison boundary. Он не подключает V2 runtime
управления, physical owner, node 101, HA/ESPHome/Modbus control и не меняет
lease/ownership.

## 1. Input contract

`ShadowDecisionInput` собирается из наблюдений и содержит:

```text
v2_live_state
telemetry_snapshot
active_program
current_phase
safety_state
session_id / trace_id (если доказаны)
observed_at
freshness
confidence
```

Input immutable и не содержит client/handler/executor. Источники только читаются;
bridge не вызывает V2 decision method и не пишет обратно в него.

## 2. V3 shadow output

На том же input V3 строит data-only result:

```text
selected_program
phase_decision
target_voltage / target_current
safety_decision
execution_intent (simulation metadata only)
decision_id
trace/session identity
reason and confidence
```

`execution_intent` не превращается в physical request и не передаётся в
dispatcher. Его назначение — сравнение и audit.

## 3. Comparison model

`ShadowDecisionComparison` сравнивает V2 observed и V3 shadow values по полям:

- program;
- phase;
- targets;
- safety;
- intent.

Итоговая классификация:

- `MATCH` — значения и identity согласованы;
- `EXPECTED_DIFFERENCE` — расхождение объяснено известной архитектурной или
  configuration причиной;
- `DIVERGENCE` — необъясненное расхождение, сохраняется для анализа;
- `UNKNOWN` — недостаточно свежих или связанных данных.

Каждый result содержит timestamp, session/trace identity (или explicit
unknown), source references, reason и confidence.

## 4. Fail-closed rules

| Состояние входа | Shadow result | Side effect |
|---|---|---|
| missing telemetry | `UNKNOWN` / safety `DENY` | none |
| stale V2 state | `UNKNOWN` | none |
| identity mismatch | `UNKNOWN` / safety `DENY` | none |
| missing program/phase | `UNKNOWN` | none |
| healthy correlated input | normal comparison | none |

Bridge не реконструирует события и не угадывает отсутствующие identity.

## 5. Ownership and safety

V2 остаётся фактическим decision/physical reference для comparison run; V3
строит независимое shadow decision. Ни один результат V3 не влияет на V2.
Safety `DENY` является данными comparison layer, а не командой containment.
Lease state только наблюдается.

## 6. No-side-effect invariant

Bridge не содержит:

- command handlers;
- HA/ESPHome/Modbus writes;
- execution dispatcher calls;
- lease mutation;
- V2 state mutation;
- physical calls.

Повторный input с тем же `session_id + trace_id + observed_at` должен быть
идемпотентен для evidence и не создавать новую control operation.

