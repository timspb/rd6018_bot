# B1031 — direct Native phase capture availability

Run: `rd6018-b1031-20261126-r73-native-observer-capture`
Branch: `codex/rd6018-b1031-native-observer-capture-20261126`
Base/current Git HEAD: `56a42c097d0bd753f124a8a98be56246ded1f50d`
Disposition: **OFFLINE SOURCE/FAKE PASS; NO LIVE CAPTURE OR PHYSICAL CLAIM**

## Finding and bounded change

The existing direct ESP observer is D106, backed by D091's existing typed
Native subscription. `ESPHomeTransport` passes the subscribed connection
generation and client into `_on_state`. D091's temporary read-only callback
wrapper accepted only `state` and invoked the original callback without those
arguments. Thus generation was available to `get_entity_state()` and the keyed
transport cache, but was dropped at the fresh D091 callback seam. A later
cache lookup would not safely restore the identity of the earlier callback.

D091's callback wrapper now forwards the exact subscription metadata and adds
`connection_generation` to captured callback metadata when the transport
actually supplies an integer. D106's existing `_native_callback_record`
preserves that field when present. Its existing `project_off` path still
accepts generation-free records, applies the same OFF-only policy and returns
the unchanged `TrialOffProof` serialized schema. No production transport,
subscription owner, session, task, command path, or hardware state was added.

Added `tools/node104_native_phase_capture.py` with the optional pure
`capture_native_phase(records, phase_started_monotonic=...,
captured_at_monotonic=...)` API. It accepts already captured D106-shaped
records for exactly `output_r18`, `voltage_v` and `current_a`. It requires
`esp_native_api`, `SensorState`, matching field and actual object identity,
integer Native key/device/generation, one device, distinct keys, one shared
generation, callbacks at or after the phase start and at or before capture,
and the existing 8-second Native freshness bound. It copies the original
generation, key, device, callback timestamp and derived monotonic age into
each result. It allows R18 0 or 1 as observation only; it does not interpret a
phase as authorization, prove command causality, or validate typed receipts.
B1024 remains the separate consumer for receipt-linked phase evidence.

## Relevant existing owners and limits

- D091 owns the existing read-only ESP callback collector; its ordinary OFF
  proof behavior remains OFF-only.
- D106 owns the existing dual-source OFF projection; its public proof and
  serialized schema are unchanged.
- `ESPHomeTransport.get_entity_state()` exposes Native source, typed state,
  key, device, connection generation, monotonic callback timestamp and age.
  Source inspection only; no call to the live ESP128 transport was made.
- Duplicate ESPHome object IDs across `SensorInfo` and `NumberInfo` are
  resolved using the existing keyed `SensorState` callback plus inventory
  identity. Duplicate `SensorInfo` identities fail closed.
- D149 routes a separate release observer around D145/D090 transactions. It
  is not the D106 Native phase callback path and was not modified.
- No node104, Native API, HA, RD6018, hardware, Output/setpoint, firmware,
  SSH, network/GitHub, service, deployment, original dirty worktree, staging,
  commit or push operation occurred. The requested live physical capture was
  therefore **not performed** and no physical state is claimed.

## Verification

HOME-PC project venv, Python 3.12, inert `TG_TOKEN`, focused cohort:

```text
PYTHONPATH=.:tests:tools TG_TOKEN=b1031-inert \
  /home/home-pc/.venvs/pcp-test/bin/python -m unittest -v \
  tests.test_b1031_native_phase_capture \
  tests.test_node104_d091_physical_proof_collector \
  tests.test_node104_d106_native_callback_record \
  tests.test_node104_d106_readonly_recovery
74 tests PASS, exit 0
```

The five new fake-only tests cover valid generation/key/device/age projection,
wrong source and missing generation, before/after phase timestamps, stale
Native callbacks, mixed generations/devices and duplicate SensorInfo identity
alongside a colliding NumberInfo. `py_compile` of all five changed Python
paths: PASS. `git diff --check`: PASS. No broad suite or CI run.

P0–P9 remains 98/103. The three P3 physical items and two P8 release/physical
items remain HOLD. No shared checkpoint, runbook, master plan or handoff was
edited; controller reconciliation is outstanding. This source-only helper
does not close a checklist item or establish B1020 Gate 3 evidence.


## Independent controller safety correction — stale callback rejection

Source review found that ESPHomeTransport._on_state rejects stale/foreign
connection callbacks, but the new D091 temporary observer initially forwarded
a rejected callback to its own captured map after the original callback
returned. The controller fixed D091 to reject wrong
connection_generation/source_client BEFORE recording any SensorState.
A negative fixture now delivers both stale-generation and foreign-client
callbacks and requires a short bounded timeout instead of physical proof.
No second ESP connection, output operation or ownership path was added.


## Independent D149/D151 pin reconciliation
The extended D145/D149 regression found that the new generation-aware D091 source differs from the immutably pinned historical D151 collector bytes. The historical D151 SHA-256 `9500454a068d120f0b23740ad3933eb70ebd8cf24fbaa7c03ddafd3e729cb8d9` is **unchanged**; no installed proof collector was modified or silently repinned. Updated the stale architecture test to require this immutable historical hash and to assert that the evolving D091 candidate differs, so it cannot masquerade as the installed D151 collector. The existing D149 wrong-hash and unsafe-path rejection tests remain in force. A fresh exact source-paired release profile and separately reviewed proof collector would be required before live deployment; this is source readiness, not physical P3/P8 acceptance.
