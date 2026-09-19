# RD6018 Live OBSERVE_ONLY Validation — WORKSTREAM 96

Статус: `LIVE_OBSERVE_ONLY_VALIDATED`

Режим: V2 production/physical owner, V3 read-only observer. Проверка выполнена
без START, STOP, PAUSE, setpoint writes, lease operations, ownership transfer и
physical execution.

## 1. Live source snapshot

| Source | Result | Observed |
|---|---|---|
| HA | PASS | authenticated read-only state collection |
| RD via HA | PASS | Output OFF; 0.0 V / 0.0 A / 0.0 W; battery 12.73 V |
| protection | PASS | code 0; normal; tripped=false |
| readback | PASS | configured/readback 13.0 V / 0.4 A |
| temperature | PASS | internal 31 C; external 25 C |
| ESPHome | PASS | endpoint reachable; prior authenticated entity/readback evidence retained |
| V2 lifecycle | OBSERVED | latest real V2 observation: Baic72/Manual/MIX/ACTIVE |

The current idle snapshot is authoritative for current output/safety values. The
latest active V2 observation is retained as a separate observation record and is
not merged into the current idle state.

## 2. V3 shadow view

For the active V2 observation, V3 shadow normalized:

```text
program: manual:Baic72
phase: MIX
targets: 17.5 V / 3.5 A
safety: ALLOW for the captured fresh observation
intent: simulation-only
```

For the current idle snapshot, V3 reports lifecycle `IDLE`, output `OFF`,
telemetry `0.0 V / 0.0 A / 0.0 W`, protection `normal`, and no execution intent.

## 3. Parity

| Field | Result |
|---|---|
| program | MATCH for captured active observation |
| phase | MATCH: MIX |
| targets | MATCH: 17.5 V / 3.5 A in active observation |
| safety | MATCH for captured fresh active observation; current idle safety normal |
| intent | MATCH as simulation tuple; never submitted |
| identity | UNKNOWN for legacy observation without session/trace identity |

Allowed classifications remain `MATCH`, `EXPECTED_DIFFERENCE`, `DIVERGENCE`
and `UNKNOWN`. Missing/stale fields do not become synthetic events.

## 4. Operator UI validation

- Charge card: current source/phase/telemetry values are read-only.
- Graph: uses observation/session boundary; no fake START or historical merge.
- Log: displays supplied canonical events only; missing chain is `UNKNOWN`.
- Diagnostics: remains a separate view and is not injected into the charge card.
- Control surface: unavailable in observer mode.

## 5. Side-effect proof

Only read-only source observations and shadow normalization were used. No HA
service, ESPHome service, RD command, setpoint write, lease operation or
physical adapter call was performed. V2 remained the sole control owner.

This status means the OBSERVE_ONLY path is validated. It does not imply
`APPROVED_CANARY`, V3 execution readiness or physical ownership transfer.

