# RD6018 Direct Evidence Source Enablement — WORKSTREAM 21

## Итог

**DIRECT_EVIDENCE_SOURCES_READY; evidence-chain blocker remains BLOCKED.** Read-only доступ к HA и ESPHome подтверждён фактическим live snapshot. Это закрывает source-enablement gap, но само по себе не создаёт отсутствующие V3 canonical events и не закрывает `CB-EVIDENCE-001`.

Ownership не менялся: V2 остаётся production/decision/execution/physical owner; V3 только collector/replay observer.

## Available sources

| Source | Доступность | Что доказано |
|---|---|---|
| HA | available | read-only telemetry/readback snapshot |
| V2 journal/manual session | partial | часть START/STOP/state history |
| `charging_history.log` | partial | coarse history, не полная canonical chain |
| ESPHome direct | validated read-only | Native API connected; entities/state/readback/lease observed |
| V3 trace/session | missing | observer worker не был live source |

## Live source check — 2026-09-15T07:40:14Z

Проверка выполнена через сохранённую WinSCP-сессию `Home Assist` для `192.168.1.102` и direct ESPHome Native API `192.168.1.28:6053`. Только GET/state subscription; service list не использовался для команд, write methods не вызывались.

| Source | Result |
|---|---|
| HA | HTTP 200; 220 entities, 41 RD-related; fresh output/readback telemetry |
| ESPHome | connected in ~2.02 s; 66 entities, 59 with state reports |
| Output | ON / state `true` / code `1.0` |
| Measurements | 17.14 V, 3.48 A, ~59.81 W, battery 17.13 V |
| Setpoints/readback | 17.50 V / 3.50 A; OVP 17.60 V, OCP 3.60 A |
| Temperature | internal 41 °C, external 35 °C |
| Protection/regulation | protection `0`; regulation mode `1` (CC); CV false |
| Lease | armed true, tripped false, quarantine false, TTL 900 s, remaining ~652 s, Modbus age ~5.3 s, generation 253 |

Основные RD/telemetry values HA и direct ESPHome согласованы. HA binary safety indicators имеют более старые `last_reported`, поэтому их freshness не следует считать эквивалентной свежести direct ESP state.

## Added contracts

- `ESPHomeEvidenceSource` принимает только supplied entity state, availability, timestamp и device health; service/command/write surfaces отклоняются.
- `TraceCorrelationValidator` выявляет missing/orphan/cross-session trace и session IDs.
- `default_runtime_event_inventory()` фиксирует фактические источники START, phases, Delta, Hold, termination и STOP.
- `EvidenceChainReassembler` преобразует supplied raw records в `CanonicalChargeEvent` и `ShadowEvidenceBundle` без source I/O.

## Evidence completeness

Текущий пакет **неполный**: отсутствуют подтверждённые Delta, Hold и termination canonical events с telemetry correlation и V3 trace/session chain. Direct ESPHome source теперь подтверждён; synthetic reassembly используется только тестами.

## UI observability

Session timeline contracts уже обеспечивают reset графика при новом session. Live UI validation для реальной полной цепочки не засчитывается, пока отсутствуют реальные START-to-STOP events и trace continuity.

## Blocker resolution

`CB-EVIDENCE-001` остаётся **OPEN/BLOCKED** только по event-chain/correlation части. Закрытие требует bounded read-only observation с уже доступными direct sources, полной event chain и едиными `session_id`/`trace_id`. Ни один источник не получил command/write surface.

## Guardrails

Commands, writes, execution, lease operations, ownership transfer и Canary не выполнялись. Отсутствие ESPHome credentials/API evidence не обходилось и не заменялось синтетическими значениями.
