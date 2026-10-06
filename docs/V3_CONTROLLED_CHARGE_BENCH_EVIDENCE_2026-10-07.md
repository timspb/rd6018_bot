# V3 controlled chemistry charge bench evidence — 2026-10-07

Status: **PASS WITH CONTAINED STOP-READBACK RESIDUAL**.

Battery selected by operator:
- chemistry/profile: `Ca/Ca`;
- nominal capacity: `72 Ah`;
- identity: `Leoch-72Ah` (`Leoch`, model label `72Ah`);
- intent: `recovery`;
- declared condition: `unknown` (not inferred from voltage).

## Fresh preflight

Canonical `StartPreflightService` result immediately before the run:
- allowed: `True`;
- ownership: `available`;
- telemetry: `valid`;
- safety: `allowed`;
- recipe: `ca_ca:recovery`;
- recovery voltage ceiling: `16.5 V`;
- initial stage: `MAIN`;
- target preview: `14.7 V / 7.2 A`.

Startup authority reconciliation returned `managed`; the controlled run then used
the existing production START route and application-owned transaction owner.
## Physical run

Pre-state: Output OFF, measured `0.00 V / 0.00 A`, battery about `13.08 V`,
external temperature `23 C`, internal temperature `29 C`.

START result:
- accepted: `True`;
- reason: `started`;
- trace: `80f16fddcdad48b1a6f81975f6d66c64`;
- programmed setpoint: about `14.74 V / 7.20 A`;
- protections: about `14.84 V / 7.30 A`.

Bounded observation samples during the 30 s chemistry bench:
- sample 1: `14.75 V / 3.82 A`, battery `14.73 V`, internal `29 C`;
- sample 2: `14.75 V / 3.69 A`, battery `14.73 V`, internal `30 C`;
- sample 3: `14.75 V / 3.57 A`, battery `14.73 V`, internal `30 C`;
- sample 4: `14.75 V / 3.46 A`, battery `14.73 V`, internal `30 C`;
- sample 5: `14.74 V / 3.35 A`, battery `14.73 V`, internal `30 C`.

No configured or measured envelope was exceeded during the bounded run.
## Stop and containment evidence

The canonical managed AUTO stop issued Output OFF. Its strict edge-heartbeat
confirmation did not complete inside the configured confirmation window and
raised `OutputOffNotConfirmed`. The existing fail-closed fallback did not
accept that as a normal success: it re-read the physical state, required Output
OFF plus zero current, then retired the AUTO session while preserving the
containment fact in the stop result.

Immediate final state after that path:
- Output: `OFF`;
- measured voltage/current: `0.00 V / 0.00 A`;
- battery: about `13.42 V`;
- external/internal temperature: `23 C / 31 C`.

A separate fresh dual-source post-check then returned:
- HA102: `VALID`;
- ESP128: `VALID`;
- comparison: `MATCH`;
- Output: `OFF` on both;
- current: `0.00 A` on both;
- battery: about `13.39 V` on both.

Therefore physical shutdown is proven. The remaining residual is observability:
the strict HA/edge heartbeat confirmation window did not recognize the OFF
transition before its timeout even though subsequent independent sources agreed
on OFF/0 A. Do not weaken freshness rules to hide this residual.