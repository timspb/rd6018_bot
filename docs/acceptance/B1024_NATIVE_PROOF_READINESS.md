# B1024 — Native ON/OFF proof readiness

Run: `rd6018-b1024-20261126-r73-native-proof-readiness`
Source base: `a5364c8cdc2e062a91aaef9861b1dd39e137fd91`
Disposition: **OFFLINE VALIDATOR PASS; LIVE P3 EVIDENCE BLOCKED / NOT RUN**

This document records the bounded source-only B1024 result. B1020 remains the
physical acceptance authority. No P3 or P8 physical checklist row is closed.

## Finding

The existing production transport already carries the primitive fields needed
for causal proof: the immutable `OutputCommandReceipt` in
`runtime/output/command_receipt.py:13-23`, created from an APPLIED firmware
terminal in `runtime/physical/transports/esp128.py:557-607`; and direct Native
callback identity/generation/freshness metadata from
`runtime/physical/transports/esp128.py:258-298`. Existing OFF application
validation in `application/start_transaction_validation.py:11-53` checks typed
OFF receipt causality.

No existing read-only collector assembles both phases. D091 is OFF-only. D106's
observer collects fresh direct measurements (`tools/node104_d106_live_observer.py:121-159`)
but then calls an OFF-only projection (`:253-265`); that projection rejects
ON (`tools/node104_d106_readonly_projection.py:72-120`) and its normalized
records omit Native connection generation. D149 is phase-aware for release
observation routing, but is not a general production START/STOP Native
evidence recorder and does not supply this missing phase pair.

## Added offline validator

`tools/b1024_native_phase_evidence.py` validates captured records only. It
checks an exact typed APPLIED receipt for each target, R18 matching each target,
direct `esp_native_api` SensorState provenance, same device ID and connection
generation across phases, callback timestamps newer than receipt completion,
the existing 8-second freshness limit, and zero measured voltage/current after
OFF. It never reads the network or hardware and cannot claim physical PASS.

Focused fixture coverage is in `tests/test_b1024_native_phase_evidence.py`:
valid causal pair, HA-only provenance, stale/pre-command samples, wrong native
type, identity/generation mismatch, ambiguous receipt, unexpected R18, and
nonzero post-OFF voltage/current.

## Application receipt limitation

The normal ON application API currently reduces the owner result to a boolean:
`application/execution_port.py:517-524` (`request_verified_on`). Thus the
transport's typed ON receipt is not returned through that application method.
The OFF clearance path separately returns/validates typed OFF evidence. B1020
Gate 3 can proceed only if the accepted supervised production route or its
existing transaction artifact preserves the real ON typed receipt alongside
the Native callback records. Do not synthesize it from ACK or bypass the
ExecutionPort. If unavailable, mark Gate 3 **BLOCKED**.

## Evidence field map for the supervised B1020 packet

For each ON and OFF phase capture the actual `OutputCommandReceipt` fields:

- `request_id`, `requested_target`, `terminal_status`, `observed_r18`
- `terminal_completed_monotonic`, `connection_generation`

For each direct Native `output_r18`, `voltage_v`, and `current_a` record capture:

- value; `source=esp_native_api`; `native_type=SensorState`; `status=ok`
- `device_id`; `connection_generation`; `subscription_timestamp_monotonic`; `age_s`

Keep HA comparison separate. A cached HA value cannot satisfy a Native record.
Use the B1020 procedure for preflight, lease, temperature, R16, setpoint,
operator approval, and the supervised load/battery envelope. Do not infer ON
measurement plausibility limits here; the approved scenario and existing
production checks own those bounds.

## Result

- Offline validator implementation: **PASS**.
- Focused tests: **5/5 PASS** using `/home/home-pc/.venvs/pcp-test/bin/python`
  with `PYTHONPATH=.:tests:tools` and an inert process-local token.
- `git diff --check`: **PASS**.
- B1020 Gate 3 live evidence: **BLOCKED / NOT RUN**. No real ON/OFF command,
  callback, receipt or physical result was collected.
- Overall P3 and P8: **HOLD**. Do not claim Native ON/OFF physical PASS.

Detailed source line map, full limitations, and command are in
[`B1024_REPORT.md`](../../B1024_REPORT.md).
