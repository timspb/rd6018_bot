# Local physical-test control plane

The physical-validation control plane is an opt-in, in-process interface for
the running `rd6018-bot` process. It exists to remove Telegram callback
simulation from physical validation while preserving the production safety
and adoption path.

## Activation boundary

It is disabled unless the bot environment explicitly contains:

```text
RD6018_PHYSICAL_TEST_CONTROL=1
```

When enabled, `bot.py` binds only the Unix-domain socket
`/run/rd6018-bot-physical-test-control.sock` with mode `0600`. There is no TCP
listener. The separate client only sends one newline-delimited JSON request;
it does not import or construct any production stateful manager.

Enabling this flag is a separate activation-stage change. It is not part of
the code deployment and must not be enabled during ordinary production runs.

## Typed operations

The server accepts exactly these requests:

```json
{"op":"status"}
{"op":"enter_hands_off_verified_off"}
{"op":"d061_adopt_battery","battery_id":"<saved-registry-id>"}
{"op":"d061_verified_stop"}
```

`d061_adopt_battery` resolves the supplied ID through `battery_registry`,
rejects `CUSTOM`, requires a positively read-back ON Output and in-process
HANDS_OFF, and delegates to the existing
`ManagedLiveAdoptionCoordinator.adopt()` preflight/TOCTOU/edge-lease path.
It does not accept setpoints, protection values, entity IDs, or arbitrary
parameters.

`enter_hands_off_verified_off` requires a positively read-back OFF Output and
delegates to the existing in-process mode manager. It never edits the durable
mode file directly. `d061_verified_stop` is stop-only, requires active adopted
Manual authority, and delegates to verified-OFF containment.

Startup recovery remains owned by the normal `bot.py` startup sequence: an
adopted session is contained and never resumed after restart.
