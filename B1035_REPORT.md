# B1035 — Native cross-client provenance

**Run:** `rd6018-b1035-20261126-r73-cross-client-evidence`
**Base HEAD:** `09c8457ec1563c57a117b85c49d01a7b9978ef0e`
**Scope:** source-only offline evidence validator and its focused tests. No runtime receipt/ExecutionPort, hardware, node104, ESP/HA, service, firmware, network, GitHub, commit, or push changes.

## Finding

B1024 compared `OutputCommandReceipt.connection_generation` with each Native callback's `meta.connection_generation`. This integer is local to one `ESPHomeTransport`: `runtime/physical/transports/esp128.py:46` initializes it to zero, and `:50-66` increments it when that transport connects. A separate instance can therefore also report generation 1. The command receipt carries only the generation integer and terminal values (`runtime/output/command_receipt.py:13-23`); no transport/session identity is present.

D106's `collect_live()` imports and instantiates a new `ESPHomeTransport` at `tools/node104_d106_live_observer.py:198-213`. Its phase-observation output at `:248-265` contains the observed phase, callback records, local monotonic capture time, and device info. `tools/node104_native_phase_capture.py:46-60, 75-90` preserves Native type/source, device/key, local generation and timestamp, but it has no actual transport-instance identity. Thus equal generation, device ID, Native type, and plausible callback age do not establish that D106 callbacks came from the app's command connection.

There is also no clock-domain identifier in these envelopes. Receipt completion and Native callback times are `time.monotonic()` values (`esp128.py:598-605`, D106 capture at `node104_d106_live_observer.py:202,249-257`). Their ordering/freshness is only meaningful if collected and compared within a known shared monotonic-clock domain. The current offline envelope does not establish that domain.

## Change

`tools/b1024_native_phase_evidence.py` keeps the existing typed receipt, source/type, generation equality, R18, post-OFF zero V/I, freshness, identity, and ordering validations. A structurally valid result now reports:

- `native_phase_observation_status: PASS`
- `causal_on_off_proof_status: NOT_PROVEN_MISSING_TRANSPORT_SESSION_IDENTITY`
- `clock_domain_status: UNVERIFIED_MONOTONIC_CLOCK_DOMAIN`

The top-level status is `NATIVE_PHASE_OBSERVATION_PASS`; it does not claim causal ON/OFF proof. No caller-supplied token, synthetic identity, crypto mechanism, protocol field, or new authorization gate was added.

## Same-session pairing seam

The evidence must be captured by an app-owned read-only report within the existing in-process Output transaction, using the *same already-connected `ESPHomeTransport` instance* for the terminal receipt and the subsequent Native callback readback, before that connection is closed or replaced. The report must carry that relationship directly from the existing in-process owner; matching numeric generations, host/device identity, or timestamps is insufficient. `application/execution_port.py:419-437` currently exposes an OFF receipt route but does not expose a same-client callback envelope. The D106 observer is a separate-client collector and cannot supply that missing link. B1034's task-local receipt propagation alone would not prove callback-session identity. Until an already-owned same-client seam is available, B1024 output must remain downgraded as above; no P3 or physical acceptance is implied.

## Verification

Using `/home/home-pc/.venvs/pcp-test/bin/python`:

```text
python -m unittest tests.test_b1024_native_phase_evidence -v
7 tests: PASS
```

Added regressions cover equal generation 1 from distinct transport instances with matching device ID, the D106-style separate client with matching device/type/age metadata, and explicit downgraded status for currently available envelopes. Existing stale, wrong type, pre-command, wrong-generation, R18 mismatch, post-OFF nonzero V/I, ambiguous receipt, and reordered/overlapping evidence checks remain enforced.

`py_compile` for the edited validator and test module: **PASS**. `git diff --check`: **PASS**. No full suite or physical test was run.
