# V3 bench gate checklist

## Software

- [ ] decision parity PASS
- [ ] safety parity PASS
- [ ] execution parity PASS
- [ ] no duplicate actuator owner

## Readback

- [ ] programmed/measured voltage
- [ ] programmed/measured current
- [ ] OVP/OCP
- [ ] output state

## Safety

- [ ] verified OFF
- [ ] emergency disable
- [ ] stale telemetry reaction
- [ ] temperature fault
- [ ] battery-fault block

## Hardware bench

- [ ] voltage measurement
- [ ] current measurement
- [ ] enable sequence
- [ ] disable sequence
- [ ] power-cycle recovery

Этот checklist только gate документации. Dry-run не подтверждает физическое
поведение и не заменяет bench evidence.
