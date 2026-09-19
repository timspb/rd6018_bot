# RD6018 Canary Blocker Resolution Plan

Статус: **CANARY_BLOCKERS_CLASSIFIED**. Это план закрытия блокеров, не approval и не разрешение Canary.

## Реестр активных блокеров

| ID | Категория | Суть | Владелец | Критерий закрытия |
|---|---|---|---|---|
| CB-APPROVAL-001 | Approval | Нет explicit approval | назначенный оператор/approver | approval с owner/scope/expiry/revoke |
| CB-SAFETY-LEASE-001 | Safety | Lease safety indicators stale | V2/edge safety owner | свежие согласованные armed/tripped/quarantine/expiry данные |
| CB-EXTERNAL-001 | External | ESPHome/RD direct parity неполная | external integration owner | согласованные свежие HA/ESP/RD/readback evidence |
| CB-EVIDENCE-001 | Operational | Нет полной V3 shadow evidence chain | V3 observability owner | START → phases → Delta → Hold → termination → STOP с trace/session continuity |
| CB-READINESS-001 | Execution | Readiness matrix содержит ограничения | V3 migration gate owner | все critical items PASS и rollback подтверждён |

## Approval blocker

Approval не создаётся этим workstream. Модель требует designated approval owner, явный scope Canary, обязательный evidence package, timestamp/expiry и revoke conditions: safety divergence, ownership conflict, unknown physical state, health degradation, lease failure или manual revoke.

## Safety/lease blocker

В live evaluation lease remaining и Modbus age были свежими, но armed/tripped/quarantine indicators имели устаревшие timestamps. Для PASS нужна свежая согласованная read-only картина источника, owner, active/expired/tripped состояния и renewal/expiry. Lease не изменяется.

## External validation gaps

HA telemetry была доступна и свежа. ESPHome direct observation и независимый RD readback parity не были полностью подтверждены. Нужны read-only snapshots обеих внешних веток с timestamp, freshness, mapping, observed state и verification result; физические команды для этого плана не требуются.

## Минимальный evidence package

Одна непрерывная session/trace цепочка:

`START → phase changes → Delta start/end → Hold start/end → termination → STOP`

Каждое событие должно иметь `session_id`, `trace_id`, timestamp, source; пакет должен включать telemetry, diagnostics, lease observation и replay/divergence result. Evidence не является runtime state.

## Приоритетный план

| Приоритет | Блокер | Действие | Риск | Валидация | Rollback |
|---:|---|---|---|---|---|
| 1 | CB-SAFETY-LEASE-001 | Обновить read-only safety evidence и устранить неоднозначность timestamps | неизвестное physical safety state | повторная preflight-проверка | сохранить текущего V2 owner; никаких lease writes |
| 2 | CB-EXTERNAL-001 | Собрать HA/ESP/RD parity package | расхождение telemetry/readback | сравнение свежих snapshots | вернуть evaluation в BLOCKED |
| 3 | CB-EVIDENCE-001 | Провести полную V2-owned observation session | неполная replayability | correlation/replay tests | discard incomplete evidence |
| 4 | CB-READINESS-001 | Обновить matrix только доказательствами | преждевременное разрешение | readiness gate review | оставить matrix BLOCKED/PARTIAL |
| 5 | CB-APPROVAL-001 | После закрытия technical blockers запросить approval отдельно | несанкционированный Canary | проверка owner/scope/expiry/revoke | approval не создавать/отозвать |

## Operator view

`CanaryBlockerSnapshot` предоставляет только active blocker IDs, progress и evidence state. Он не создаёт approval, не меняет ownership и не маршрутизирует execution.

## Ограничения

В рамках WORKSTREAM 19 не выполнялись команды, записи, START/STOP, lease renewal/takeover, Canary activation или runtime migration. До закрытия всех critical blockers статус остаётся `CANARY_BLOCKED`.
## WORKSTREAM 20 update — CB-EVIDENCE-001

Статус: **OPEN / BLOCKED**. Canonical chain validator и replay path проверены на synthetic complete chain, но это не live evidence. Доступный HA-only пакет не содержит полной V3 trace/session цепочки `START → phases → Delta → Hold → termination → STOP`; прямой ESPHome source также не подтверждён. Blocker закрывается только свежей V2-owned read-only observation с полной корреляцией, не synthetic тестами.
## WORKSTREAM 21 update — direct evidence sources

Статус: **OPEN / BLOCKED**. Read-only ESPHome source contract, trace validator, runtime source inventory и canonical reassembly подготовлены. Live ESPHome entity/API evidence и complete V3 trace/session chain по-прежнему отсутствуют; `CB-EVIDENCE-001` не закрыт.
## WORKSTREAM 21 live update

Direct source gap закрыт: HA вернул HTTP 200, direct ESPHome API подключился к `192.168.1.28:6053`, получены 66 entities/59 state reports; основные output/V/I/readback/lease значения совпали с HA. `CB-EXTERNAL-001` теперь имеет фактическое source evidence, но freshness HA safety binary entities отличается от direct ESP state. `CB-EVIDENCE-001` остаётся OPEN из-за отсутствующей полной canonical START-to-STOP chain и V3 trace/session correlation.
## WORKSTREAM 22 update — live charge cycle

Проверена текущая live-сессия: `Baic72`, `active`, `MIX`, persisted start `2026-09-15T06:07:21Z`. HA/ESPHome telemetry/readback согласованы, но session_id отсутствует, а текущая history не содержит полной Delta/Hold/termination/STOP canonical chain. `CB-EVIDENCE-001` остаётся **OPEN/BLOCKED**; естественный цикл не инициировался.
## WORKSTREAM 23 update — session correlation

Correlation layer готов: новые/restored/resumed identity различаются, старые события фильтруются, cross-session conflicts получают `AMBIGUOUS`, UI получает только current-session timeline. Live persisted record всё ещё без `session_id`; `CB-EVIDENCE-001` не закрыт до полного реального capture.
## WORKSTREAM 24 update — session birth observation

`LiveSessionBirthObserver` готов для before/start/after capture. Текущий live state уже active, поэтому новый START задним числом не создаётся; `SESSION_BIRTH_CAPTURED` не подтверждён. `CB-EVIDENCE-001` остаётся OPEN.
## WORKSTREAM 25 update — active session identity gap

Root cause identified: active `Baic72/MIX` uses `ProductionManualSessionManager`, whose `manual_session_v2.json` document contains state/request/timestamps but no session/trace identity. Automatic `ChargeControllerV2` has a separate `_v2_trace_session_id` path, so parity cannot be assumed. `CB-EVIDENCE-001` remains OPEN; no runtime repair was made.
## WORKSTREAM 26 update — Manual identity boundary design

Контракт boundary определён без runtime wiring: explicit start/resume identity, restore-existing при полной persisted identity, `AMBIGUOUS` для legacy state. `CB-EVIDENCE-001` остаётся открытым до реализации в отдельном разрешённом изменении и реального complete capture.

## WORKSTREAM 27 update — Manual identity runtime observation

`CB-EVIDENCE-001` остаётся **OPEN / BLOCKED**: V2 Manual runtime не подключает identity boundary, поэтому реальный identity-bearing START/event chain не наблюдается. Добавлен только read-only observer contract; запуск Manual, control, lease и ownership не выполнялись.

## WORKSTREAM 28 update — Manual identity boundary integration

Статус integration: **READY**. `ProductionManualSessionManager` теперь получает identity adapter для новых Manual starts, совместимого поля `session_identity` и in-memory canonical event exposure. Legacy active records не мигрируются и остаются `AMBIGUOUS`; `CB-EVIDENCE-001` остаётся OPEN до реального полного V2-owned capture.

## WORKSTREAM 29 update — first real Manual identity evidence

Статус: **BLOCKED**. В observation window новая Manual сессия не наблюдалась; `SessionStarted` и complete START-to-STOP chain не получены. Добавлен replay-only evidence collector, но synthetic/старая сессия не засчитываются.

## WORKSTREAM 30 update — active session V3 parity

Статус: **ACTIVE_SESSION_PARITY_READY**. Existing active Manual state допускается как parity input без START/STOP lifecycle; legacy absence of identity классифицируется `LEGACY_NO_IDENTITY`, а не physical/safety failure. `CB-EVIDENCE-001` по полной chain остаётся отдельным открытым blocker.
