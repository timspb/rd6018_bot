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

Normal operations:

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

## D061 deterministic fault operations

These operations exist only for the remaining short physical validation gates.
They are one-shot, in-process and available only while the same opt-in Unix
control plane is enabled:

```json
{"op":"d061_fault_toctou_precommand","battery_id":"<saved-registry-id>"}
{"op":"d061_fault_ambiguous_edge_ack","battery_id":"<saved-registry-id>"}
{"op":"d061_fault_raw_protection_unavailable"}
```

They do not accept setpoints or entity IDs and cannot issue Output ON or widen
V/I/OVP/OCP authority.

### `d061_fault_toctou_precommand`

Requires normal HANDS_OFF + positively confirmed Output ON and a saved battery.
The control plane builds a normal D061 preview, then injects a synthetic change
into only the coordinator's second in-process fingerprint read. No HA/RD value
is written. The existing coordinator must reject the mismatch before the edge
command uncertainty boundary. Acceptance requires:

- `command_may_have_executed=false`;
- edge generation unchanged;
- external Output remains ON;
- zero injected hardware writes.

This is the deterministic replacement for trying to race a physical setpoint
change by hand between preview and edge command.

### `d061_fault_ambiguous_edge_ack`

Requires the same normal D061 preconditions. The real edge live-adopt button
press is sent, but only the configured positive-ACK readback samples are hidden
behind the pre-command lease snapshot. The wrapper is exhausted before
containment. Therefore the production coordinator must classify the edge command
as possibly executed and drive its existing verified-OFF containment using real
Output/lease readback.

This operation may physically arm the edge lease briefly. It must be run only
with the established low-current D061 physical baseline and an operator near the
RD6018. It never injects an ON command or any setpoint/protection write.

### `d061_fault_raw_protection_unavailable`

Requires an already ACTIVE D061 adopted Manual session. It does not modify the
HA protection entity or provoke electrical OVP/OCP. Instead it makes the already
installed D061 raw register-16 renewal gate fail once in-process. The normal
strict runtime must verify Output OFF; the normal adopted observer then retires
the now-OFF authority and disarms the edge lease.

The injected condition is explicitly distinguishable in logs/errors as:

```text
physical-test injected raw RD6018 protection-code unavailable
```

These hooks are validation-only. Disable `RD6018_PHYSICAL_TEST_CONTROL` and
remove the Unix socket after each physical test batch.
