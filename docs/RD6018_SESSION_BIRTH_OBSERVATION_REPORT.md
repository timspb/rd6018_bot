# RD6018 Session Birth Observation — WORKSTREAM 24

## Итог

**BLOCKED** — новая реальная `idle → START → active` граница в текущем read-only окне не наблюдалась.

V2 остаётся production owner. V3 не выполнял START/STOP, commands, writes, lease operations или ownership transfer.

## Current observation

На последнем live snapshot уже была активная V2-сессия `Baic72/MIX` (`started_at=2026-09-15T06:07:21Z`). Это состояние позволяет видеть active profile/phase и direct HA/ESP telemetry, но не доказывает birth event: before-state был не captured, persisted record не содержит `session_id`, а `trace_id` START отсутствует.

## Observer contract

`LiveSessionBirthObserver` принимает только supplied before/start/after snapshots и фиксирует:

- idle-to-active transition;
- timestamp/source;
- session_id/trace_id;
- profile/initial phase;
- missing identity fields.

`SessionBirthTimelineGuard` допускает UI timeline только для matching session с reset graph и без historical events.

## Required capture

Для закрытия `CB-EVIDENCE-001` нужен естественный V2-owned цикл, начатый из подтверждённого idle, с полями:

`timestamp + session_id + trace_id + profile + initial phase + telemetry correlation`

После birth нужно продолжить read-only capture до Delta, Hold, termination и STOP. Длинный цикл можно оставить partial; это не закрывает blocker.

## Decision

`SESSION_BIRTH_CAPTURED` не выдан. Статус остаётся `BLOCKED`; persisted state и runtime не изменялись.
