# RD6018 domain module model (Phase 5.2)

Статус: decomposition contract only. Эти границы описывают будущую V3
структуру; они не являются runtime wiring и не создают executor.

## Dependency rule

```text
Measurements / validated intent / recipe data
                    |
        +-----------+-----------+----------------+
        v                       v                v
  Charge Domain          Profile Domain     Safety Domain
        |                       |                |
        +-----------+-----------+----------------+
                    v
            Strategy Domain
                    |
                    v
             Session Domain
                    |
                    v
              domain decision
```

Infrastructure (Telegram, HA, ESPHome, lease, persistence adapters and
physical/output owners) is outside this graph. A domain module may return a
data-only decision but may not execute it.

## Module contracts

| Module | Owns | Consumes | Exports | Forbidden dependencies |
|---|---|---|---|---|
| **Charge Domain** | canonical states, transition guards, phase lifecycle, invalid-transition decisions | validated intent, selected profile/recipe, measurements, domain safety result | `ChargeState`, transition decision, phase/event data | Telegram, HA, ESPHome, actuator/controller objects, persistence, UI |
| **Profile Domain** | AGM/EFB/Ca-Ca/Custom identity and recipe data | chemistry, capacity, explicit overrides, validated limits | immutable profile/recipe, phase targets, profile metadata | transport clients, runtime globals, UI text, controller/output |
| **Strategy Domain** | Main/Recovery/Mix policy, Delta evidence, confirmation/hold/timer rules | profile recipe, measurements, elapsed time, state continuity | `ChargeIntent`, strategy decision, evidence/termination reason | physical writes, Telegram, HA, lease/watchdog, session storage |
| **Session Domain** | data-only lifecycle: start/stop/pause/resume/restart guards | validated charge intent, charge state, fresh measurements, safety decision | session state transition, session identity, serializable continuity data | direct actuator calls, transport, UI callbacks, implicit resume/restore side effects |
| **Safety Domain** | domain envelope, limits, temperature/current/voltage guards | profile limits, measurements, phase/intent context | safety decision, limit violation, allowed/denied domain decision | HA-loss policy, ESPHome lease, output commands, emergency shutdown owner |

## Ownership boundaries

- Charge Domain is the only owner of canonical domain state transitions.
- Profile Domain is the only owner of profile-specific recipe data after
  validation; it does not choose transport or execution owner.
- Strategy Domain owns completion evidence, Delta confirmation and timed holds;
  it does not own session lifecycle or safety containment.
- Session Domain owns logical session lifecycle only; it cannot re-energize or
  restore physical state.
- Safety Domain owns domain safety decisions only. Infrastructure safety and
  physical containment remain outside V3.
- V2 remains the execution/physical owner until a separately authorized
  migration. This Phase 5.2 does not alter that ownership.

## V1/V2 concept mapping

| Extracted concept | Source | Target boundary | Status |
|---|---|---|---|
| legacy phase strings/FSM | V1 `charge_logic.py` | Charge Domain | mapped; compatibility vocabulary retained |
| AGM/EFB/Ca/Ca/Custom recipe branches | V1/V2 | Profile Domain | mapped; Custom needs explicit validated recipe |
| Main, Recovery, Mix and plateau logic | V2 strategy | Strategy Domain | mapped |
| Imin/Delta-I and Vmax/Delta-V evidence | V1/V2 + native V3 | Strategy Domain | parity decision required |
| start/stop/restore/pause semantics | V1 session scaffold/V2 manager | Session Domain | mapped as data-only contract |
| battery envelope and temperature rules | V1/V2 domain checks | Safety Domain | mapped |
| HA loss, lease and watchdog | V2/runtime safety | outside domain modules | explicitly not extracted |

## Boundary tests required before implementation

1. Import graph contains only standard library and domain modules.
2. Domain objects are data-only where specified and cannot reach actuator
   methods.
3. Every V1/V2 concept has one target owner; no second FSM/session owner is
   introduced.
4. Decisions with missing/stale evidence fail closed as domain decisions, while
   physical containment remains the existing V2 responsibility.

## Unresolved domain decisions

1. Canonical EFB Mix authority: legacy 20 h or current V2 strategy 24 h.
2. Canonical CC Delta evidence: production Vmax/Delta-V versus native V3
   current-drop implementation.
3. Explicit Custom recipe schema and its relation to the outer voltage/current
   envelope.
4. Exact pause/resume semantics after restart: serialized continuity versus
   mandatory fresh operator reauthorization.

Until these are resolved, no module may be wired to START/ACTIVE or to a
physical execution bridge.

## Explicit non-goals

No Telegram handlers, HA clients, ESPHome transport, persistence writer,
installer/bootstrap code, UI state, controller calls, SafeOutputCoordinator
changes or physical commands are part of this model.
