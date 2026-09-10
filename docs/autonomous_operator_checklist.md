# AUTONOMOUS operator checklist

Use [`autonomous_hardware_failure_capture.md`](autonomous_hardware_failure_capture.md)
for any failed or ambiguous hardware result.

Use this checklist with [`autonomous_bench_validation.md`](autonomous_bench_validation.md).
It is a field record, not permission to bypass a safety gate.

## Before test

- [ ] Record repository git SHA: `____________________________`
- [ ] Record exact ESPHome firmware SHA/version: `____________________________`
- [ ] Confirm Output is OFF: `____________________________`
- [ ] Confirm emergency physical disconnect is available and reachable.
- [ ] Record current edge/operation mode: `____________________________`
- [ ] Record current ownership state: `____________________________`
- [ ] Back up runtime state using the approved operational procedure.
- [ ] Record session/generation and initial V/I/OVP/OCP/protection readback.
- [ ] Confirm the intended load and test limits are documented.

## During test

- [ ] Use the numbered steps for the selected A01–A07 case.
- [ ] Record every mode/generation acknowledgement and Output transition timestamp.
- [ ] Do not issue bot actuator commands in AUTONOMOUS.
- [ ] Stop on unexpected Output change, missing acknowledgement, protection ambiguity or unsafe load behavior.

## After test

- [ ] Restore Output OFF unless the approved test explicitly requires otherwise.
- [ ] Record final mode, ownership, Output and protection state.
- [ ] Complete a failure report for any deviation.
- [ ] Do not declare production readiness until the exact-node bench evidence is reviewed.
