# B1036 — same-client Native post-ON phase observation

Run: `rd6018-b1036-20261126-r73-same-client-native-phase`
Branch: `codex/rd6018-b1036-same-client-native-phase-20261126`
Starting HEAD: `62b4206e1baf90c5bfb44030af813962866fc2cb`
Draft PR: #182 (not accessed or changed)

## Result

Implemented an optional post-ON Native phase observation through the existing
ExecutionPort → composed safety guard → HassClient → ESPDirectConnector →
ESPHomeTransport chain. `ExecutionPort.enable()` asks for this ancillary sample
only after the existing safe-enable result is accepted and the existing
B1034 typed ON receipt is present. It does not dispatch another ON, affect
acceptance, or alter `ExecutionPortResult`.

The Native transport now retains each original callback object alongside its
original monotonic callback time, typed entity domain/key, current generation,
source APIClient object, and source ESPHomeTransport object. The projector accepts only three unique
`SensorInfo`/`SensorState` records (R18, measured voltage, measured current)
from the current transport client, at the receipt's actual generation, with
timestamps strictly after terminal completion. It returns the original
`SensorState` object in each record. A missing, stale, ambiguous, wrong-type,
pre-terminal, reconnecting, changed-client, wrong-generation, or non-ON R18
sample returns `NOT_OBSERVED`; no output action follows.

The same-client guarantee comes from the existing production wiring and
identity checks at the transport callback source, not from comparing
generation integers between separate clients. HA102/non-ESPDirect backends
return `NOT_OBSERVED`. `NumberInfo` is not accepted as measured sensor data,
including when it shares an object ID with a sensor.

## Changed paths

- `application/execution_port.py` — optional ancillary phase callback after
  accepted existing enable.
- `hass_api.py`, `runtime/safety/runtime_guard.py` — read-only forwarding along
  the existing owner path; no HA fallback.
- `runtime/physical/connectors/esp_direct.py` — uses the connector's existing
  transport instance.
- `runtime/physical/transports/esp128.py` — retain typed callback object
  references and project validated post-receipt records.
- `tests/test_b1034_tasklocal_on_receipt.py` — same-client and transaction
  regressions.
- `B1036_REPORT.md`
- `docs/acceptance/B1036_SAME_CLIENT_NATIVE_ON_READBACK.md`

## Verification

Using `/home/home-pc/.venvs/pcp-test/bin/python`, with `PYTHONPATH=.:tests:tools`
and inert `TG_TOKEN`:

```text
tests.test_b1034_tasklocal_on_receipt
tests.test_b1033_d106_native_phase_observation
Ran 16 tests — OK
```

The cohort verifies one existing ON call and unchanged accepted result shape,
exact raw callback object identity, strict post-terminal time, stale and
generation rejection, wrong transport client despite matching integer
generation, different transport instance despite matching client and
generation, NumberInfo collision rejection, no Native proof from HA, and
existing request-scope reset. `py_compile` passed for all five changed
production Python modules and the focused test. `git diff --check` passed.

This is source/fake evidence only. No live ESP, HA, RD6018, node104, Output,
setpoint, lease, firmware, service, deployment, network, GitHub, stage,
commit, or push action occurred. Shared checkpoint/runbook/master/handoff were
not edited per task scope. P0–P9 remains 98/103; the three P3 physical and two
P8 physical/release items remain HOLD. No release or physical acceptance is
claimed.


## Independent controller acceptance corrections
The first 189-test independent cohort passed, but code review found the new
post-ON projector still used only per-client integer generation to relate
the receipt to its producer and had no eight-second freshness cap. Before
acceptance, the controller bound the actual receipt to the exact original
ESPHomeTransport and APIClient object references in B1034's request-local
ContextVar. The phase projector now rejects any other transport or client,
even if their generations are numerically equal; this origin is sourced from
the same single existing physical command, not guessed or externally signed.
The phase projector also rejects callbacks aged beyond the existing 8-second
evidence window, nonfinite numeric readbacks and mixed device IDs. All changes
are read-only observation: the existing boolean Output ON transaction, lease,
Guard and final readback remain unmodified. The independent corrected worker
cohort passed **148/148 tests** and compile/diff checks before integration.
This is source-backed fake evidence, NOT supervised physical P3 acceptance.
