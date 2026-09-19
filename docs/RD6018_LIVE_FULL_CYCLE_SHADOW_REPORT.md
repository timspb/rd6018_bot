# RD6018 Live Full-Cycle Shadow Observation

Статус: **PARTIAL_OBSERVATION**

Причина: observer был запущен в момент, когда V2-сессия уже находилась в
`ACTIVE/MIX`. В bounded read-only окне новый START и переходы lifecycle не
произошли. Текущая MIX не используется для реконструкции предыдущих событий.

## Observation window

- observation window: `2026-09-15T12:04:52Z` — `2026-09-15T12:04:56Z`;
- observer: V3 read-only;
- V2: единственный production/control owner;
- sources: HA 102 state API и node 101 V2 persisted manual state через штатную
  сохранённую read-only WinSCP-сессию;
- cadence: 5 read-only snapshots с интервалом около 1 секунды.

Ни START, ни STOP, ни lease operation не выполнялись.

## Live V2 snapshot

| Field | Observed value |
|---|---|
| session state | active |
| program/profile | Manual / Baic72 |
| phase | MIX |
| output | ON |
| configured target | 17.5 V / 3.5 A |
| measured output | 17.10 V / 3.49 A / 59.68 W |
| temperature | 43 °C internal; 37 °C external |
| regulation | code 1; CC ON / CV OFF |
| protection | code 0 |
| lease | armed; remaining 732.4 → 728.4 s |
| Modbus age | fresh in the source snapshot |
| session/trace identity | UNKNOWN — legacy V2 state has no IDs |

V2 persisted state was read without modification. It contains the historical
`started_at`, profile and current `stage`, but no validated V3 session/trace
identity.

## Observed events

| Event | Result | Evidence |
|---|---|---|
| START | NOT OBSERVED | session already active at window start |
| PREP | NOT OBSERVED | no transition event |
| MAIN | NOT OBSERVED | no transition event |
| DESULFATION | NOT OBSERVED | no transition event |
| MIX | CURRENT STATE ONLY | observed active phase, not entry event |
| HOLD | NOT OBSERVED | no Hold event |
| SAFE_WAIT | NOT OBSERVED | no transition event |
| DONE | NOT OBSERVED | no termination event |
| STOP | NOT OBSERVED | no stop event |
| Delta start/completion | NOT OBSERVED | no event source evidence |
| Hold start/completion | NOT OBSERVED | no event source evidence |

## V2/V3 shadow parity

Для доступных текущих decision fields построен read-only shadow input:

```text
profile: Manual / Baic72
phase: MIX
state: ACTIVE
targets: 17.5 V / 3.5 A
telemetry: 17.10 V / 3.49 A / 43 C
safety observation: protection 0, lease armed
```

| Field | Result | Note |
|---|---|---|
| program | MATCH | `manual:Baic72` |
| phase | MATCH | `MIX` |
| targets | MATCH | 17.5 V / 3.5 A |
| safety | MATCH | observed protection/lease state |
| execution intent | MATCH | compared as data only; not submitted |
| lifecycle event chain | UNKNOWN | no events observed in window |
| session identity | UNKNOWN | legacy IDs absent |

Итоговый parity result применим только к текущему snapshot. Полная
START-to-STOP parity не утверждается.

## Safety and no-write proof

Выполнены только:

- HA GET/state reads;
- чтение V2 `manual_session_v2.json` с node 101;
- локальная normalization и V3 shadow comparison.

Не выполнялись: START/STOP, изменение уставок, HA/ESPHome writes, RD
commands, lease operations, deployment, ownership transfer и physical
execution. V3 не влиял на V2.

## Required next run

Для статуса `LIVE_FULL_CYCLE_SHADOW_VALIDATED` observer должен быть активен
до естественного V2 START и непрерывно наблюдать реальное событие START,
переходы фаз, Delta/Hold start и completion, termination и STOP. Missing IDs
должны остаться `UNKNOWN`, а не заполняться synthetic values.
