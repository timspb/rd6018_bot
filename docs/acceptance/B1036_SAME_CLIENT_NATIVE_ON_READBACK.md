# B1036 acceptance — same-client Native ON readback

**Run:** `rd6018-b1036-20261126-r73-same-client-native-phase`
**Base:** `62b4206e1baf90c5bfb44030af813962866fc2cb`
**Scope:** source and fake tests only

## Contract

The optional `ExecutionPort.enable(on_native_phase_observed=...)` callback is
invoked only after the existing safe-enable owner returns accepted and B1034
has supplied the exact typed ON receipt. It receives the receipt and a
read-only phase result. It does not change the `ExecutionPortResult` shape or
the existing single ON dispatch. Callback and read failures are ancillary and
cannot reverse or otherwise alter the accepted output transaction.

The read follows the already composed owner path to the configured
`ESPDirectConnector` and its existing `ESPHomeTransport`. The transport keeps
the original callback object and monotonic callback timestamp, keyed by Native
info domain and key, and records the generation, APIClient, and
ESPHomeTransport instance that supplied
the callback. R18, measured voltage, and measured current must each resolve to
one `SensorInfo` and a `SensorState`; `NumberInfo` is not a substitute. Every
timestamp must be strictly greater than `receipt.terminal_completed_monotonic`,
each callback source must be the transport's current APIClient and exact
ESPHomeTransport instance, and the
generation must still equal the receipt's generation. R18 must be integer 1.
The returned entries retain the exact `SensorState` object plus device/key,
object ID, type, source, timestamp, age, and generation.

Missing/incomplete callbacks, stale or preterminal callbacks, reconnect or
generation change, different client, ambiguous/missing sensor mapping, wrong
Native type, and non-ON R18 return `NOT_OBSERVED`. A HA102 backend cannot
provide this Native evidence. No `get_all_live()` cache or `NumberInfo`
readback is treated as a causal proof.

## Fake evidence and limits

Focused project venv run: B1034 task-local receipt tests plus B1033 D106 Native
phase tests, **16 PASS**. Covers single existing ON invocation and unchanged
result shape, same transport/client, retained callback object identity,
post-terminal monotonic timestamps, stale and reconnect/generation rejection,
same integer generation on another client or transport instance rejection,
`NumberInfo` collision, HA exclusion, and no request-scope leakage. `py_compile`
and `git diff --check` passed.

No physical Native callback was collected. This does not prove live causality,
close P3, or authorize hardware/release/deployment. P0–P9 remains 98/103; P3
physical (3) and P8 physical/release (2) remain HOLD. OVP/OCP behavior and
thresholds, R16 policy, actuator owner, guards, lease, and firmware were not
changed.


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
