# V3 bench gate checklist

Status: 2026-10-07 post-ERADICATION / physical-evidence checkpoint.

## Software

- [x] decision/preflight parity covered by current START tests
- [x] safety preflight and SafeOutput contract covered
- [x] execution route parity covered
- [x] no duplicate START/actuator owner

## Readback

- [x] programmed/measured voltage
- [x] programmed/measured current
- [x] OVP/OCP
- [x] output state
- [x] battery voltage read before selecting bench Vset
- [x] Vset above measured battery voltage by configured margin
- [x] final OFF confirmation includes measured current = 0 A
- [x] ON/OFF readback latency recorded

## Safety

- [x] verified OFF
- [x] post-enable failure forces disable + verified-OFF containment
- [x] stale telemetry reaction covered by fail-closed tests
- [x] temperature fault covered by SafetySupervisor tests
- [x] implausible/missing battery telemetry blocks START

## Hardware bench

- [x] voltage readback
- [x] current readback
- [x] enable sequence
- [x] disable sequence
- [x] ESP power-cycle/reconnect recovery

## Controlled chemistry charge

- [ ] connected battery profile/chemistry explicitly selected
- [ ] nominal capacity Ah explicitly selected
- [ ] battery identity recorded
- [ ] intended program/condition recorded
- [ ] fresh START preflight PASS immediately before execution
- [ ] canonical START transaction trace captured

The unchecked items are operator/battery-specific inputs for the next physical
charge run. They are not transport or software defects and must not be inferred
from terminal voltage alone.
