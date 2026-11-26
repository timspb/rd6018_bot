# B1027 — direct Native Vset/Iset programmed-readback evidence

Run: `rd6018-b1027-20261126-r73-native-setpoint-proof`
Source base: `170aa91a7e7d8bc578f5dfa32d7fea12f411f9fa`
Disposition: **OFFLINE VALIDATOR READY; production causal receipt unavailable; P3 HOLD**

## Scope

This is the P3 Gate 2 source-evidence slice for programmed Vset/Iset, separate
from B1026's Output ON receipt route. It adds one offline-only validator and
deterministic fixtures. It does not change a production owner, transport,
ExecutionPort, START/ON policy, or hardware path. It does not collect live
evidence or close a P3/P8 checklist item.

OVP/OCP register 82/83 remains diagnostic/operator-managed only. This validator
does not accept or require those values and cannot authorize a threshold write.
Measured output V/I remains distinct from numeric programmed Vset/Iset.

## Existing ownership and evidence surfaces

- `esphome/packages/rd6018_telemetry_v2.yaml` declares read-only force-updated
  Modbus `SensorState` entities for Vset register 8 and Iset register 9.
  Writable number entities remain command endpoints, not readback evidence.
- `config/physical/esp128.yaml` maps `configured_voltage` and
  `configured_current` to `set_voltage_readback_v2` and
  `set_current_readback_v2`.
- `runtime/physical/transports/esp128.py::_on_state` maps those inventory
  entries to `SensorInfo` and retains only matching `SensorState` callbacks.
  `get_entity_state()` returns their Native source, object ID, entity key,
  device ID, connection generation, callback monotonic timestamp, and age.
  `get_live_values()` also projects the read-only setpoint sensors and marks
  source `esp_native_api`, type and callback timestamp; its aggregate metadata
  does not currently carry connection generation or object ID. The individual
  `get_entity_state()` record has those fields.
- The normal production selection in `config/physical/transports.yaml` is
  `ha102`; HA's `set_value`/`HassClient.set_voltage()` and `set_current()` return
  booleans. `application/execution_port.py` likewise awaits the setters as
  booleans, then compares a later aggregate readback. This is not a typed
  terminal V/I receipt and does not expose a write-completion monotonic time
  tied to the Native callback generation.
- `physical_test_control_programmed_readback.py` (B16) checks freshness and
  advancing `last_reported` for the configured Vset/Iset readback mirrors in
  its existing HA-shaped live view. This remains a distinct legacy HA
  programmed-readback check. Its heartbeat does not prove a direct Native
  callback, same ESP device, same Native generation, or callback-after-write
  causality.
- `runtime/safety/output_policy.py::SafetyPolicy` owns V/I readback tolerances
  (0.06 V and 0.06 A) and absolute ceilings (17.5 V and 12 A). The existing
  accepted direct-Native evidence freshness bound is 8 seconds. The helper
  accepts these values as arguments so it creates no parallel setting owner.

## Offline validator contract

`tools/b1027_native_setpoint_evidence.py::validate_programmed_setpoints`
consumes a caller-supplied actual transaction receipt, two Native sample
records, the configured object IDs, existing policy tolerances/ranges and the
existing maximum age. It requires the receipt to contain the request ID,
actual write-completion monotonic time, expected V/I, connection generation,
and each signal's pre-write callback timestamp. It accepts only matching
`esp_native_api` `SensorState` records from the configured read-only object IDs,
with the same device and receipt generation; callback timestamps must be
strictly later than both the baseline callback and actual write completion,
and remain fresh/not future-dated. Values must be finite, within the supplied
physical range, and match the requested setpoints within the supplied
tolerance.

The receipt is deliberately not synthesized by the helper. Current production
V/I writes expose booleans, so callers cannot truthfully populate a real
completion timestamp/generation from those return values alone. Until an
existing authorized capture contains the receipt fields and direct Native
callback records, Gate 2 live evidence remains **BLOCKED / NOT RUN**. No
alternate writer, observer, API call or transport was added to obtain them.

## Verification

`tests/test_b1027_native_setpoint_evidence.py` covers six deterministic offline
cases: valid same-device Native callbacks; stale, HA-only and wrong Native
type; configured object identity mismatch; device/generation mismatch;
pre-write and unchanged old heartbeat; impossible setpoint and missing real
completion receipt. Test output is recorded in `B1027_REPORT.md`.

## Decision

- Offline validator: **SOURCE-READY**, subject to focused tests passing.
- Native Vset/Iset readback after an actual production write: **BLOCKED / NOT
  RUN** because the current setter receipt is boolean-only and the aggregate
  production read does not expose all direct Native identity fields.
- P3 and P8: **HOLD**. This report is not a physical PASS and does not change
  the canonical checklist.
- No OVP/OCP setter, no requirement to read OVP/OCP, no output action, and no
  changes to the separate B1026 Output ON route.
