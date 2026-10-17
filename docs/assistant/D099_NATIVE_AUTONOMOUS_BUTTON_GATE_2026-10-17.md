# D099 — Native ESPHome AUTONOMOUS button availability contract

**Status:** software fix and regression tests, **not** physical D097 PASS.
Baseline: main `da5c3aa` and installed ESPHome `2.2-autonomous-authority`.

## Concrete incompatibility

The physical native transport exposes `ButtonInfo` for ESPHome buttons. It
does not publish a `ButtonState` on the subscription used for numeric/binary
sensors. D097 `EdgeAutonomousAuthority._require_button()` previously used
`lease._state_value()` for `safety_enter_autonomous` and
`safety_exit_autonomous`. That is not a reliable native button-presence test.

Additionally `config/physical/esp128.yaml` mapped lease Renew/Disarm but
not explicit AUTONOMOUS Enter/Exit buttons. Thus even a recognized command
could not be dispatched by the existing native transport allowlist.

## Changes

- Add explicit recipe entries `edge_autonomous_enter` and
  `edge_autonomous_exit`; no open-ended native command capability.
- Use the configured backend's read-only `get_button_info()` and require
  `status=ok`, `native_type=ButtonInfo`, and `exists=true` before
  the existing transition. A missing or wrong-type native command fails
  closed; HA-only adapters retain their previous entity-state compatibility.
- Keep `_press()`, serialized command path, generation ACK,
  unmanaged lease safety predicates, and 900s/300s unchanged.
- Regression covers native enter/exit inventory without ButtonState,
  invalid native entity type, explicit native mapping/press and mapping
  absence. No real ESP button was invoked by these tests.

## Acceptance boundary

Do **not** copy only this patched module onto the older installed node.
Build an exact-source candidate including all current tracked modules and
recipes, and validate independent readbacks from its entire composition.
D090 remains pinned to a different source and unsigned/unpinned firmware;
its gates must not be weakened to install this fix.
