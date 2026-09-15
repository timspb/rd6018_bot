# RD6018 charge state model (Phase 5.1)

Контрактная модель для V3; runtime не подключена.

## Lifecycle states

| State | Meaning | Entry guard | Exit |
|---|---|---|---|
| `IDLE` | no active domain session | no active session | validated start |
| `PREP` | bounded initial preparation | start and recipe accepted | preparation evidence or timeout |
| `MAIN` | chemistry-specific main charge | valid measurements | tail/plateau, recovery or timeout |
| `DESULFATION` | bounded anti-sulfation attempt | profile rule and stuck-current evidence | timer or evidence to safe wait |
| `MIX` | high-voltage controlled finishing | main evidence accepted | Delta hold, authority timeout or safe wait |
| `SAFE_WAIT` | output-safe waiting/recheck | recovery/cooling/transition requires it | Main, Done or containment decision |
| `COOLING` | thermal pause | temperature rule | safe temperature or stop |
| `DONE` | domain completion | terminal evidence/hold | IDLE after stop/acknowledgement |
| `STOPPED` | invalid/stale domain evidence | required evidence unavailable | explicit new validated session |

Legacy names `Подготовка`, `Main Charge`, `Десульфатация`, `Mix Mode`,
`Безопасное ожидание`, `Остывание`, `Done`, `Idle` map to the same states.

## Delta sub-state

`UNARMED -> TRACKING -> CONFIRMED_HOLD -> COMPLETE`.
Invalid evidence or an explicit stop leads to `STOPPED`. Confirmation count and
hold start are owned by the domain state, not by a transport or UI.

## Allowed domain transitions

```text
IDLE -> PREP | MAIN
PREP -> MAIN
MAIN -> MAIN | DESULFATION | MIX | COOLING | SAFE_WAIT | DONE | STOPPED
DESULFATION -> SAFE_WAIT
MIX -> MIX | SAFE_WAIT | DONE | STOPPED
SAFE_WAIT -> MAIN | DONE | STOPPED
COOLING -> MAIN | STOPPED
DONE -> IDLE
```

`PREP -> MAIN` may be skipped only by the documented initial-voltage guard.
`MIX -> DONE` requires accepted Delta evidence plus the sticky hold; an
authority timeout is not successful completion.

## Session semantics

- Start creates a new session in `PREP` (automatic) or `MAIN` (explicit Custom
  path in the legacy controller), after validation.
- Stop is an explicit terminal operation. A restore may retain serialized
  session data only within the bounded legacy restore window; it must not
  silently re-energize output.
- Pause/resume is an outer runtime concern. Domain state can be serialized and
  resumed only with fresh measurements and renewed safety/ownership checks.
- Restart recovery is not a domain executor and cannot bypass preflight.

## Invalid transitions

Reject transitions with missing measurements, stale evidence, absent recipe,
unknown chemistry, expired authority, or an attempt to resume a terminal/idle
session without a new validated request. Rejection produces a domain decision;
physical containment remains owned by existing V2 safety/output layers.

## Safety split

Domain safety: chemistry envelope, voltage/current limits, temperature rules,
phase evidence, timer bounds and completion criteria.

Infrastructure safety: HA/transport loss, lease renewal/expiry, ESPHome
dead-man, watchdog and physical OFF verification. These are inputs/context or
outer containment decisions, never hidden program transitions.
