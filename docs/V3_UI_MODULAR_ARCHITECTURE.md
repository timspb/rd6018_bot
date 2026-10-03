# V3 Modular UI Architecture

Status: **required architecture**, not optional cleanup.

The UI has historically been the easiest layer to lose during runtime
refactors. V3 therefore treats UI screens, buttons, navigation and operator
actions as versioned modules with static contracts.

## 1. Layer boundary

```text
Application Read Model
        |
        v
OperatorSnapshot / ViewModel
        |
        v
ScreenSpec
  +-- text/components
  +-- ButtonSpec[]
        |
        v
Telegram renderer/transport
```

Actions travel in the opposite direction:

```text
ButtonSpec.action
        -> UIAction
        -> OperatorIntent
        -> Application service
```

UI never calls controller, safety internals, HA, ESPHome or RD6018.

## 2. Target structure

```text
runtime/ui/
  models.py
  actions.py
  buttons.py
  variables.py
  routing/
    registry.py
    state_router.py
  screens/
    home/
    charging/
    batteries/
    manual/
    diagnostics/
    recovery/
    mix/
    settings/
    service/
    graph/
  components/
    telemetry.py
    safety.py
    progress.py
    confirmations.py
    pagination.py
  telegram/
    renderer.py
    adapter.py
    transport.py
```

The exact filenames may evolve, but ownership boundaries may not collapse back
into a monolithic handler module.

## 3. Buttons

All V3 buttons are declarative `ButtonSpec` objects. A button owns:

- stable id;
- display label key/text;
- UI action id;
- optional confirmation requirement;
- optional visibility capability;
- navigation target where applicable.

A screen composes buttons. It does not implement the action.

No new V3 code outside the UI button/renderer layer may construct
`InlineKeyboardButton` or assign raw Telegram `callback_data`.

## 4. Navigation

Navigation uses stable `ScreenId` values. It must not depend on unrelated
historical callback names such as multiple variants of "back", "home" or
"dashboard".

Adding a future screen must require only:

1. its screen module;
2. its button declarations;
3. registration in UI routing;
4. optional application intent handler when it introduces a new use case.

It must not require editing the charge FSM or runtime monolith.

## 5. State and available actions

The application/read-model layer determines what actions are available for the
current state. UI renders those capabilities.

A button must never remain enabled merely because an old Telegram message
contains its callback. The routed action is re-authorized against current state.

## 6. UI variables

UI-owned configurable values live in `runtime/ui/variables.py` or a specific
component/screen `variables.py` when ownership is narrower.

Examples:

- refresh cadence;
- graph window;
- pagination size;
- confirmation lifetime;
- maximum journal rows rendered.

Each variable uses the common metadata contract from the modular architecture.
Charge/safety values are forbidden in UI variable files.

## 7. Forbidden imports/calls

Canonical V3 UI must not import:

- `runtime.v2_runtime`;
- `charge_logic` / historical ChargeController;
- `hass_api`;
- ESPHome/HA physical transports;
- safety/output executors;
- database mutation APIs.

Canonical V3 UI must not call:

- `turn_on`, `turn_off`;
- `set_voltage`, `set_current`, `set_ovp`, `set_ocp`;
- session mutation or charge-stage transition methods.

Telegram is a renderer/transport adapter only.

## 8. Migration

The existing V1/V2 UI is a behavior/reference source while screens move one at
a time. A migrated screen receives a canonical ViewModel and emits canonical
actions. After parity, its old callback/rendering path is removed rather than
kept as a fallback.

## 9. Completion gate

UI migration is complete when a future button or screen can be added without
touching `runtime/v2_runtime.py`, `charge_logic.py`, controller classes,
physical execution or safety modules.
