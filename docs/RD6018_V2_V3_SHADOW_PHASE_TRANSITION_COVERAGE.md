# RD6018 V2/V3 Shadow Phase Transition Coverage

Статус: **BLOCKED**

Причина: в доступном read-only evidence окне наблюдалась уже активная
`MANUAL / Baic72 / MIX` сессия. Ни один phase transition event не был пойман
в момент перехода. События задним числом не реконструируются.

Режим: V2 — production owner; V3 — read-only shadow observer.

## Transition matrix

| Transition | Timestamp | Session | Program | Reason/conditions | V2/V3 comparison | Status |
|---|---|---|---|---|---|---|
| PREP → MAIN | — | UNKNOWN | UNKNOWN | no live edge event | UNKNOWN | NOT OBSERVED |
| MAIN → DESULFATION | — | UNKNOWN | UNKNOWN | no live edge event | UNKNOWN | NOT OBSERVED |
| DESULFATION → MIX | — | UNKNOWN | UNKNOWN | no live edge event | UNKNOWN | NOT OBSERVED |
| MIX → HOLD | — | UNKNOWN | UNKNOWN | no Delta completion event | UNKNOWN | NOT OBSERVED |
| HOLD → SAFE_WAIT | — | UNKNOWN | UNKNOWN | no Hold completion event | UNKNOWN | NOT OBSERVED |
| SAFE_WAIT → DONE | — | UNKNOWN | UNKNOWN | no termination event | UNKNOWN | NOT OBSERVED |

## Delta/Hold coverage

| Event | Evidence | Status |
|---|---|---|
| Delta start | absent from current canonical event/history evidence | UNKNOWN |
| Delta completion | absent; current MIX does not prove completion | UNKNOWN |
| Hold start | absent | UNKNOWN |
| Hold completion | absent | UNKNOWN |

Observed current state from the previous bounded read-only snapshot:

- program: `Manual / Baic72`;
- phase: `MIX`;
- telemetry: approximately `17.10 V / 3.49 A / 59.67 W`;
- safety: protection code `0`, lease observed armed;
- session/trace identity: `UNKNOWN_LEGACY_NO_IDENTITY`.

This is a state observation, not evidence of `PREP → MAIN`, `MAIN → MIX`,
Delta start/completion or any subsequent transition.

## Classification rules

- `MATCH` — both V2 event and V3 shadow event observed with the same edge,
  reason and conditions;
- `EXPECTED_DIFFERENCE` — a documented semantic difference with evidence;
- `DIVERGENCE` — both sides observed but inconsistent without explanation;
- `UNKNOWN` — one or both edge events/evidence are missing.

Current transition rows are `UNKNOWN`, not `MATCH`.

## Required next observation

Нужен bounded read-only observation window, начинающийся до следующего
естественного V2 transition, с корреляцией `timestamp`, `session_id`/`trace_id`,
previous/next phase, reason, conditions и telemetry. Для Delta/Hold требуется
поймать start и completion события отдельно.

## Safety boundary

Не выполнялись deployment, activation, ownership transfer, START/STOP, lease
operations, HA/ESPHome writes, RD commands или physical commands. V3 не влиял
на V2.

Итог: artifact готов для следующего observation window, но фактическое
transition coverage пока **BLOCKED**.
