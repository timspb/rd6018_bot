# RD6018 Canary Preflight Live Evaluation

Дата оценки: `2026-09-15T07:11:21Z`  
Режим: V2 — production owner; V3 — read-only evaluator.

## Итог

**CANARY_PREFLIGHT_LIVE_EVALUATED — CANARY_BLOCKED**

Canary не запускался. Authority, lease и physical execution не изменялись.

## Live inputs

Read-only snapshot получен через HA на `192.168.1.102`. Сервис `rd6018-bot.service` на 101 был `active` (`MainPID=2569980`); это подтверждает жизнеспособность V2 процесса, но не является доказательством готовности V3.

| Область | Наблюдение | Оценка |
|---|---|---|
| RD/HA telemetry | 17.16 V, 3.48 A, 59.87 W, battery 17.15 V, internal 42 °C; возраст свежих значений примерно 2.5–3.7 s | PASS |
| RD output | output state code `1`, configured/readback 17.5 V / 3.5 A | наблюдение, без команды |
| Lease | remaining 882.9 s, Modbus age 2.8 s, generation 248 | частично PASS |
| Lease freshness | armed entity `on`, но `last_reported` устарел примерно на 3643 s; tripped/quarantine также устарели | BLOCKED: safety ambiguity |
| HA | доступен, telemetry свежая | PASS |
| ESPHome direct | TCP-доступность известна, но direct API observation в этой оценке не подтверждена | BLOCKED: parity incomplete |
| V3 shadow evidence | текущая complete evidence/trace/session цепочка не предоставлена | BLOCKED |
| Approval | действующего Canary approval нет | BLOCKED |

## Readiness gates

- Architecture: не пройдена как Canary gate — standalone takeover не доказан.
- Domain: partial; остаются parity decisions.
- Safety: blocked — stale lease safety indicators и отсутствие live ownership proof.
- Execution: blocked — direct physical/readback parity не подтверждена.
- External: blocked — HA есть, ESPHome/RD direct parity неполная.
- Observability: blocked — нет свежей полной V3 shadow evidence chain.

## Blockers

1. Нет действующего explicit approval с owner, expiry и scope.
2. У lease safety entities устаревшие timestamps; physical safety state нельзя считать однозначно подтверждённым.
3. Не собрана прямая ESPHome parity observation и независимый RD readback parity.
4. Нет свежей V3 evidence с trace/session continuity, достаточной для Canary gate.
5. Базовая readiness matrix содержит активные ограничения по external parity, safety, execution и observability.

## Рекомендация

**Не переходить к Canary preparation/activation.** Сначала получить свежие read-only lease indicators, подтвердить direct ESPHome/RD parity, собрать полную V3 shadow evidence chain и оформить отдельный действующий approval. До этого статус остаётся `CANARY_BLOCKED`.

Проверка была read-only: commands, writes, lease renewal/takeover, START/STOP и physical actions не выполнялись.
