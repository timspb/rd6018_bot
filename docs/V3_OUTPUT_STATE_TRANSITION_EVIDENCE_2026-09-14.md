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

## Evidence conclusion

The battery-aware target selection is now enforced, and the failure did not leave Output enabled. The physical transition gate remains blocked until the HA output control mapping/behavior is diagnosed and a new operator-approved run is started. No automatic fallback or second connector execution was performed.
