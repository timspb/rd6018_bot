# B1029 — Vset/Iset write completion causality (source-only)

Run: `rd6018-b1029-20261126-r73-vi-write-causality`
Exact isolated base/code HEAD: `56a42c097d0bd753f124a8a98be56246ded1f50d`
Disposition: **NO PRODUCTION CHANGE; REAL V/I TERMINAL RECEIPT UNAVAILABLE; P3/P8 HOLD**

## Scope and result

Audited the existing programming call from `application/execution_port.py`
through the safety owner and the configured physical connector. The B1027
offline validator remains unchanged. No real receipt was synthesized, and no
production code or fake parity tests were added because the deployed source
route has no terminal V/I receipt contract to exercise honestly.

## Actual owner and connector path

1. `ExecutionPort.program_voltage()` / `program_current()` own serialized
   application calls. They call the existing `_execution_owner` setter,
   convert its result to `bool`, and update the adopted-write ratchet only
   after a true result. `program_voltage_current()` preserves V then I order
   inside the existing serialization. These public results are booleans.
2. The composed execution owner is `StrictRuntimeSafetyGuard` over
   `RuntimeSafetyGuard`. The strict wrapper retains bool semantics and its
   live voltage transition may first program a lower current before raising
   voltage. RuntimeSafetyGuard checks current admission/readback and then
   invokes its captured raw adapter setter; successful bool return remains
   the ratchet boundary. Recovery/quarantine, HANDS_OFF ownership, lease,
   safety limits, and existing lock/order remain with these owners.
3. `HassClient.set_voltage()` / `set_current()` return bool. The normal
   `config/physical/transports.yaml` selection is `ha102`: the connector sends
   Home Assistant `number/set_value` and receives an HTTP success status. This
   confirms service dispatch only; it is not an RD6018 terminal programming
   receipt, Native generation, or proof of hardware application. Exceptions
   collapse to false in the adapter.
4. The alternate existing `esp_direct` connector exposes direct Native
   `SensorState` reads and `native_connection_generation`, but its number
   setter calls `APIClient.number_command(...)` and returns no response or
   command ID. Unlike the existing Output command route, there is no V/I
   terminal status callback correlated by request ID. The Native setpoint
   sensors can supply read-only callback identity/time after collection, but
   cannot establish the missing actual write completion boundary.

Thus neither current write route can provide the B1027 receipt's real
`request_id`, `write_completed_monotonic`, and captured generation as one
transaction result. On HA102, generation is also not owned by the HA route.
Sampling a clock around a bool call, making up a request ID, or reading Native
afterward would not turn either into a terminal receipt.

## Minimal future path

The required prerequisite is a real terminal completion signal for a V/I
command on the already-authorized physical route, carrying a correlatable
request identity and the connection generation that was active for that
command. At that same serialized `ExecutionPort` programming call, capture
the pre-write Native Vset/Iset callback baselines already available from the
existing ESP subscription; on terminal completion, record the actual
monotonic completion and requested pair, then pass those captured facts to the
unchanged offline B1027 validator. Keep public bool methods and derive their
existing true/false behavior from the same result; retain one writer, order,
ratchet, and all current recovery/HANDS_OFF/safety behavior. If the selected
backend cannot supply that genuine terminal signal and generation, observation
must remain **NOT OBSERVED**. No second command, polling observer, extra
admission condition, or Output ON inference is justified by this audit.

## Verification and boundaries

- `tests.test_b1027_native_setpoint_evidence`: **6/6 PASS** with the requested
  `/home/home-pc/.venvs/pcp-test/bin/python`, inert `TG_TOKEN`, and
  `PYTHONPATH=.:tests:tools`. This verifies the unchanged offline validator
  only; it is not a V/I write parity or physical acceptance result.
- No production code, tests, B1027 validator, ESPHome/configuration, shared
  runbook/checkpoint/master/handoff, hardware, HA/ESP, node104, service,
  Output, setpoint, lease, firmware, or deployment was changed or accessed.
- No full suite, CI, network/GitHub, staging, commit, or push was performed.
- P3's V/I causal evidence remains **BLOCKED / NOT OBSERVED**; P3 and P8
  remain **HOLD**. Draft PR #182 remains unmerged.
