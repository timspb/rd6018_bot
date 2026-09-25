# V3 START legacy execution isolation

## Current route map

```text
V2 battery UI
  |
  +-- v2_battery_start
  |      |
  |      v
  |  v2_bootstrap._v2_battery_start_route
  |      |
  |      v
  |  v2_startup.start_profile_transactional
  |      |
  |      v
  |  V2 controller / FSM / Safety / physical transaction
  |
  +-- v2_quick_start
         |
         v
     v2_bot_ui._start_profile
         |
         +-- production composition rebinds it to
             v2_startup.start_profile_transactional
```

The production composition is installed by `bot.py` through `install_v2()`.
There is one registered production handler for `v2_battery_start`, and the
action-aware quick-start compatibility handler resolves to the same
transactional V2 owner.

## Classification of direct legacy paths

| Path | Location | Classification | Current production status |
|---|---|---|---|
| Saved battery start | `v2_bootstrap._v2_battery_start_route` | authoritative V2 transaction | reachable from production V2 UI |
| Quick profile start implementation | `v2_bot_ui._start_profile` | compatibility surface; rebound during V2 composition | not the raw implementation in production |
| Legacy profile + Ah flow | `bot_legacy.handle_ah_input` | rollback/emergency compatibility | not exposed by the production V2 charge-mode keyboard |
| Legacy custom flow | `bot_legacy.start_custom_charge` | rollback/emergency compatibility | preserved; not the production auto-profile route |
| `/start` command | `bot_legacy.cmd_start` | dashboard presentation only | does not start charging |

## V3 boundary status

The V3 START preflight/plan/trace path remains a shadow boundary. It is not
made the production execution owner in this change. Therefore the current
production START owner is still the V2 transactional function, while the raw
legacy direct-start implementations remain preserved for rollback.

The isolation invariant added here is narrower and explicit: production has
one V2 transactional START callback, the production keyboard does not expose
legacy callback identifiers, and preserved legacy functions are not silently
selected by the production composition.

## Remaining migration blocker

Before V3 can become the production START owner, the existing V3 preflight,
approved plan, activation policy, and gated execution port require a separate
authorized migration and bench validation. This audit does not enable that
path and does not alter controller, FSM, Safety, or physical execution.
