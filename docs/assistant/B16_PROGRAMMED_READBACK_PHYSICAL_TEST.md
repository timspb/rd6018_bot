# B16 — fresh programmed-readback physical validation

Status: **repo/software ready; physical validation pending**.

This gate closes item B16 in `V2_VALIDATION_PLAN.md`: after a new OVP/OCP/V/I
programming transaction, stale pre-existing static readback must not be accepted as
proof that the write reached HA/RD. Output ON must remain unreachable until fresh
programmed readback is observed.

## Test operation

The existing opt-in root-only AF_UNIX physical-test server exposes one additional
hard-coded operation:

```text
b16_fault_hold_stale_set_voltage_readback
```

Transport-only client:

```bash
python tools/physical_test_programming_fault_client.py
```

The request accepts **no** setpoint, entity ID, timestamp, age, or arbitrary HA value.

## Preconditions

The operation is deliberately narrower than a normal charging start. It requires:

- `PB_MANAGED`, with no control-mode transfer in progress;
- no active AUTO, Manual, D061, or D062 authority;
- canonical Output already positively OFF;
- no previous unconfirmed Output-OFF containment;
- hardware protection state normal;
- edge lease unarmed/untripped and boot quarantine clear;
- valid normal idle preflight telemetry;
- a real, already-stale idle `set_voltage` heartbeat. A fresh Vset heartbeat is a
  read-only rejection, not something the harness makes stale in HA.

This last condition is intentional. Static V/I/OVP/OCP values are allowed to be old
while idle; B16 proves that the same old evidence becomes insufficient immediately
after a new programming transaction.

## What the operation does

1. Read the real current OVP/OCP/V/I values while Output is OFF.
2. Build the ordinary safe-output request using **exactly those same values**.
3. Install task-local guards around the already-composed production adapter:
   - each programming write must equal the captured value exactly;
   - any attempt to reach `turn_on()` is blocked before hardware actuation and makes
     the test fail;
   - after the Vset write, only the public `get_all_live()` view used by the
     `SafeOutputCoordinator` keeps the old Vset metadata entry.
4. Run the real `safe_enable_output()` transaction. The normal coordinator writes
   OVP -> OCP -> Vset -> Iset, then asks for fresh programmed readback.
5. Expected result: `telemetry_invalid` / `programmed readback telemetry
   missing/invalid`, with **zero Output-ON attempts**. The coordinator issues its
   normal fail-safe Output-OFF request while Output is already OFF.
6. Restore every wrapped production method before final proof.
7. Prove through the real reader that the actual Vset heartbeat did become fresh after
   the write. This distinguishes the deliberate one-shot holdback from a real HA/RD
   failure to report the write.
8. Re-prove canonical Output OFF, edge lease unarmed, and unchanged OVP/OCP/V/I
   numeric values.

## Safety properties

The harness cannot grant charging authority and cannot choose a hardware value. It
can perform only four same-value programming writes and a fail-safe OFF request.
Unexpected values are rejected before the underlying setter is called. An attempted
Output ON is intercepted before the production `turn_on()` method is invoked.

The operation does not change ESPHome, entity mappings, freshness thresholds, edge
TTL/renewal cadence, chemistry policy, or production authority semantics. It creates
no listener: it is composed onto the already-disabled-by-default AF_UNIX test server.

## PASS evidence for the later physical run

A physical PASS requires all of the following from one controlled invocation:

- initial Output OFF and clean idle PB-managed state;
- exactly one same-value write each for OVP, OCP, Vset, and Iset;
- the injected coordinator read reports old Vset freshness and fails before ON;
- `output_on_attempts = 0` and no physical Output ON transition;
- the real post-write Vset heartbeat is fresh after the injection is removed;
- final OVP/OCP/V/I equal the pre-test values within production readback tolerance;
- canonical Output OFF remains positively confirmed;
- edge lease remains unarmed with remaining time zero;
- no `OutputOffNotConfirmed` or unrelated containment reason occurs.

If the real Vset heartbeat does not become fresh, the run is **not** a B16 PASS: the
fault injection is then unproven and the HA/ESPHome reporting path must be investigated.
