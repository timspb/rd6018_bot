# B1035 — Native cross-client provenance acceptance

**Run ID:** `rd6018-b1035-20261126-r73-cross-client-evidence`
**Source base:** `09c8457ec1563c57a117b85c49d01a7b9978ef0e`
**Scope result:** offline Native phase validation can PASS; causal ON/OFF proof remains NOT PROVEN.

## Source evidence

- `runtime/physical/transports/esp128.py:46,50-66`: `_native_connection_generation` is initialized per transport instance and incremented on that instance's connection. It is not a process-global or device-global session number.
- `runtime/physical/transports/esp128.py:557-606`: command receipt construction captures the local generation and monotonic completion time; `OutputCommandReceipt` contains no transport-instance/session identity (`runtime/output/command_receipt.py:13-23`).
- `tools/node104_d106_live_observer.py:198-213`: D106 creates a new `ESPHomeTransport` for its observation. `:248-265` returns a separate phase snapshot.
- `tools/node104_native_phase_capture.py:46-60,75-90`: callback projection checks and preserves Native type/source, keyed field/device, local generation, timestamp and age, but no client-instance identity.
- `application/execution_port.py:419-437`: existing OFF receipt route returns a receipt; it does not include same-client Native callbacks.
- Monotonic timestamps are produced at `esp128.py:598-605` and D106 at `tools/node104_d106_live_observer.py:202,249-257`. The captured envelopes do not identify their clock domain.

Therefore, generation equality, host/device ID, Native type, timestamp order, and age cannot prove that a receipt and callback came from the same actual transport client. No accepted fixture currently carries existing same-client session provenance.

## Acceptance behavior

The B1024 validator retains its prior type, source, generation equality, R18, OFF zero V/I, freshness, per-phase device identity, and ordering checks. Passing those checks yields `native_phase_observation_status=PASS`, alongside:

```text
causal_on_off_proof_status=NOT_PROVEN_MISSING_TRANSPORT_SESSION_IDENTITY
clock_domain_status=UNVERIFIED_MONOTONIC_CLOCK_DOMAIN
```

It cannot return causal ON/OFF proof PASS with the present receipt/callback formats. No same-client identity was synthesized or added as a new cryptographic or approval mechanism.

## Path to causal evidence

Use an app-owned read-only report inside the existing in-process Output transaction. It must obtain the terminal receipt and post-command Native callbacks from the same already-connected `ESPHomeTransport` instance before reconnect/close, and retain their relationship from that existing owner. D106's separate observer cannot establish the link. If the existing app transaction cannot expose same-client callbacks, the current evidence remains downgraded until that seam exists; do not infer it from matching counters or device details. The independent B1034 receipt propagation is insufficient on its own to establish callback identity.

## Verification

`/home/home-pc/.venvs/pcp-test/bin/python -m unittest tests.test_b1024_native_phase_evidence -v`: **7 PASS**. New negative coverage includes equal numeric generation across distinct clients with matching device ID and D106-style matching metadata without session identity. Existing stale and wrong-generation rejection remains covered. Targeted `py_compile` and `git diff --check`: **PASS**.

No runtime production code, node104, ESP/HA, hardware, Output/setpoints, lease, service, deployment, firmware, network/GitHub, commit, or push was changed or exercised. P0–P9 remains **98/103**; P3 (3) and P8 (2) remain HOLD. R16 OVP/OCP codes 1/2 remain diagnostic/operator-only; R16 OPP 3 and unknown nonzero, measured V/I/temperature/R18, and the ESP-local 900-second lease retain their existing protection policy.
