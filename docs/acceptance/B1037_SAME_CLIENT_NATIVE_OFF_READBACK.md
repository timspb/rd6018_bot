# B1037 acceptance — same-client Native OFF readback

**Run:** `rd6018-b1037-20261126-r73-same-client-off-proof`
**Base:** `97384fb6b1589aaa02b08c9b87fe42a0aeb56e54`
**Scope:** source and fake tests only

## Contract

The optional `ExecutionPort.request_emergency_off_receipt(on_native_off_observed=...)`
callback is ancillary. It runs only after the existing emergency OFF owner has
returned a typed receipt and only when that receipt is the exact object captured
from the existing OFF command in B1034's request-local ContextVar. The ContextVar
is reset in `finally`. The original typed OFF receipt return, Guard validation,
emergency containment and lease/recovery gates are unchanged.

The source remains the same `ESPDirectConnector` → `ESPHomeTransport` and
APIClient that issued the existing OFF command. The projector requires fresh
Native `SensorInfo`/`SensorState` R18, measured voltage and current callbacks;
timestamps strictly after `receipt.terminal_completed_monotonic`; age no greater
than 8 seconds; exact transport/client identity; the receipt's connection
generation; a single device ID; finite measured values; and integer R18 matching
the APPLIED receipt. OFF observation additionally requires measured voltage and
current exactly zero. Missing callbacks and any invalid or ambiguous metadata
produce `NOT_OBSERVED`. HA state cannot satisfy this contract.

No additional OFF is issued. Observation does not wait, retry, or change command
semantics. A positive source/fake sample does not constitute live physical
acceptance, P3 closure, P8 release approval, or deployment authorization.

## Fake evidence

Focused project venv cohort: **57/57 PASS** across B1037, B1034 task-local
receipt, ExecutionPort policy boundary, D091 physical collector, and typed OFF
receipt tests. The new composed-route test follows ExecutionPort →
RuntimeSafetyGuard → HassClient → ESPDirectConnector → ESPHomeTransport and
checks exact receipt identity, one command, and same-transport post-terminal
Native zero R18/U/I observation. Negative coverage rejects stale, preterminal,
missing, nonzero, malformed timestamp/type, changed client/transport/generation,
and unsupported/failed receipt paths. `py_compile` and `git diff --check` pass.

No physical Native callbacks were collected. Physical P3 and P8 remain HOLD.
