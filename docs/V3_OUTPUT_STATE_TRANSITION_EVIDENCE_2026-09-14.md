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


## 2026-10-07 independent ESP-direct controlled transition

Fresh read-only preflight immediately before execution showed both HA102 and
ESP128 `VALID` with `MATCH`, Output `OFF`, measured current `0.00 A`, battery
voltage about `13.07 V` and temperature `28 C`.

The independent ESP-direct path then executed the existing manual bench
`OFF -> ON -> OFF` transition through SafetyEngine, ExecutionPolicy,
conservative hardware/battery envelope validation, a scoped
`CONTROLLED_STATE_TRANSITION` bench lease and a manually armed
`PhysicalExecutionGate`. No automatic fallback to HA was used.

Battery-aware parameters were selected from the fresh snapshot:

```text
Vbat = 13.07 V
Vset = 13.57 V
Iset = 0.10 A
OVP  = 14.07 V
OCP  = 0.20 A
hold = 10.0 s
```

Observed physical evidence:
- programmed V/I/OVP/OCP readback: PASS;
- Output ON confirmation: `1.509 s` after the direct ESP command;
- configured ON hold: `10 s`;
- final Output OFF + `0.00 A`: `2.531 s` after disable;
- executor result: `EXECUTED`;
- final independent HA102/ESP128 post-check: both `VALID`, comparison `MATCH`;
- post-state: Output `OFF`, measured `0.00 V / 0.00 A`, battery about `13.08 V`,
  temperature `29 C`.

The bench-safe programmed values remain `13.57 V / 0.10 A / OVP 14.07 V /
OCP 0.20 A` with Output OFF. They were intentionally not restored to the prior
higher programmed current after the evidence run.

### Latency conclusion

The historical HA-ESP controlled retry measured `1.526 s` ON and `2.546 s`
OFF, while the independent ESP-direct run measured `1.509 s` ON and `2.531 s`
OFF+zero-current. The difference is only about `17 ms` / `15 ms`; therefore the
observed ~1.5 s ON and ~2.5 s OFF latency is not materially introduced by Home
Assistant. The dominant delay is downstream in ESP/RD command/readback
propagation and polling.

Result: **PASS** for independent ESP-direct transition and transport-latency
characterization.
