# V3 physical execution migration gate

Baseline audited: `117d6e7` (branch `codex/v3-runtime-consolidation`).

This is an audit record only. No RD, HA, Output, ESPHome, lease, or node 101
operation is performed by this gate.

## Ownership result

| Decision | Current V3 owner | Evidence |
| --- | --- | --- |
| voltage/current/stage/completion | `ChargeStrategy` and its policies | `runtime/charge/strategy/` returns `ChargeIntent` |
| MIX transitions and authority | `MixPolicy` | `runtime/charge/strategy/mix.py` |
| intent validation | `SafetyEngine` | `runtime/safety/engine.py` |
| V3-to-output conversion | `OutputIntentFactory` | `runtime/output/factory.py` |
| output execution boundary | `OutputAdapter` | `runtime/output/adapter.py` |
| V2 mapping | `ShadowOutputBridge` only | `runtime/output/bridge/` |

No physical adapter or production wiring is present in the V3 path.

## Forbidden-path audit

The V3 charge, safety, and output domain modules contain no direct HA/RD/GPIO,
Telegram, lease, ESP, or actuator calls. `MockOutputAdapter` and
`ShadowOutputBridge` are non-physical test/shadow implementations.

## Gate requirements

### OVP/OCP geometry

The required migration contract is:

```text
OVP >= Vset + 0.05 V
OCP >= Iset + 0.05 A
OVP/OCP <= absolute ceilings
write + readback confirmation before enable
```

The geometry and readback transaction are still migration requirements for the
future physical bridge. The domain now represents the reset operation through
the same `SafeOutputIntent` action contract; this does not authorize physical
writes.

### MIX protection

CV MIX current containment is represented in `MixCurrentContainmentState`:

```text
after 30 min from MIX start:
Iset = confirmed Imin + Delta-I + 0.4 A
recalculate every 10 min
only decrease; never follow a rising measured current
```

`ResetProtectionIntent` is converted by `OutputIntentFactory` into the common
`SafeOutputIntent(RESET_PROTECTION)` action after an allowed safety decision.
It is intentionally not executed here.

### Temperature integrity

`MixTemperatureIntegrityPolicy` reuses the shared calibrated
`ExternalTempIntegrityMonitor`. A latched anomaly produces a MIX stop/diagnostic
decision. The monitor's configured consecutive-anomaly threshold remains a
required calibration input; a single suspicious sample is not silently
promoted to a latch.

## SafeOutputIntent coverage

Covered domain actions: enable, disable, set voltage, set current, and reset
OVP/OCP. The future bridge still requires explicit safety-reviewed mapping and
readback parity for the reset action.

## Checklist

### Software

- [x] V3 strategy produces decisions without physical calls
- [x] V3 safety produces `SafetyDecision`
- [x] one output execution boundary exists
- [x] V2 bridge is shadow-only
- [ ] V2 decision parity is accepted for all production vectors
- [x] OVP/OCP reset has one SafeOutputIntent representation
- [ ] OVP/OCP geometry/readback mapping is physically proven

### Safety

- [x] denied intents do not reach the output boundary
- [ ] verified-OFF parity is proven for the future bridge
- [ ] readback transaction parity is proven
- [ ] lease/authority parity is proven

### Bench

- [ ] voltage verification
- [ ] current verification
- [ ] emergency stop
- [ ] external sensor failure
- [ ] power-cycle restore

## Decision

V3 owns domain decisions and safety decisions, and has a single future output
boundary. Physical migration is **NOT READY** until the unchecked parity,
OVP/OCP reset, readback, lease, and bench gates are closed.
