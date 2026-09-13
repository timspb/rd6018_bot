# V3 controlled output state transition evidence

Status: **FAIL / not approved for continuation**

Baseline: `13def3e040b4d8afb238361fa37a2f8bfe9a4658` (working tree also contains the bench-only changes listed below)

## Safety-relevant pre-state

Read-only snapshots through HA102 and ESP128 agreed:

- battery voltage: `13.13 V`;
- Output: `OFF`;
- measured current: `0 A`;
- temperature: `31 °C`.

The earlier failed attempt had temporarily written `12.0 V / 0.10 A / OVP 0 / OCP 0`; with Output still OFF, the known pre-test values were restored and confirmed after propagation as `13.94 V / 0.55 A / OVP 16.70 V / OCP 12.00 A`.

## Battery-aware bench parameters

The fixed `12.0 V` bench target was removed. The runner now calculates values after the pre-snapshot:

```text
Vset = Vbattery + configured margin = 13.13 + 0.50 = 13.63 V
Iset = 0.10 A
OVP  = Vset + configured margin = 14.13 V
OCP  = Iset + configured margin = 0.20 A
```

The configured ON hold is `10 s`, followed by disable and OFF/current readback.

## Runs

### HA-ESP connector, first attempt

The run reached parameter writes but stopped before enable because OCP readback was temporarily stale. No `ENABLE_OUTPUT` was sent. Subsequent read-only snapshots confirmed the intended parameters and Output `OFF`.

### HA-ESP connector, second attempt

Parameter readback passed. `ENABLE_OUTPUT` was sent, but the following fresh snapshot did not confirm `Output ON`; the executor failed closed. Post-run HA and ESP snapshots both showed Output `OFF` and measured current `0 A`.

Result: **FAIL**, because the HA-ESP path did not produce a confirmed ON transition. The ESP-direct path was not run after this failure.

### Controlled retry with latency measurement

The battery-aware precheck passed with `13.14-13.15 V` battery voltage. The
selected values were approximately `13.64 V / 0.10 A / OVP 14.14 V / OCP
0.20 A`.

- ON command: both HA and ESP reported `ON` after `1.526 s`;
- configured ON hold: `10 s`;
- OFF command: both HA and ESP reported `OFF` after `2.546 s`;
- the first OFF snapshot still showed `0.09 A`, so the run was not accepted at
  that point;
- a fresh readback 5 seconds later confirmed `OFF`, `0.00 A`.

The physical transition therefore completed safely, but the original executor
had an insufficient post-OFF verification model. It now polls until both OFF
and zero current are confirmed, using configured timeout and interval.

## Evidence conclusion

The battery-aware target selection is enforced. The measured retry completed
`OFF -> ON -> OFF` through HA-ESP-RD with independent ESP readback and final
`OFF / 0 A` confirmation. The earlier HA latency failure is retained as
evidence; no automatic fallback was used. A separate ESP-direct execution is
still pending if dual-connector evidence remains required.
