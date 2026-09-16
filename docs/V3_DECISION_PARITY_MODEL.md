# V3/V2 decision parity shadow

This is a non-executing comparison model. It converts an already supplied V2
decision mapping with `LegacyDecisionAdapter`, converts V3
`ChargeIntent -> SafetyDecision -> SafeOutputIntent` with
`V3DecisionSnapshot`, and compares the resulting decision fields.

## Compared

- phase and stage;
- transition/reason;
- completion;
- enable/disable intent;
- requested voltage and current;
- safety allowed/denied and violation types.

## Not compared

No controller tick, HA state, RD response, physical voltage/current, lease
mutation, or actuator call is part of parity. A mismatch is evidence only and
does not auto-correct either path.

Representative vectors cover MAIN, RECOVERY, MIX CC/CV, completion, chemistry
profile decisions, safety denial, current containment, and protection reset.

## Unified output intent

All allowed execution-shaped actions use `SafeOutputIntent`: enable, disable,
set voltage, set current, and reset OVP/OCP. `ResetProtectionIntent` is a
domain input to `OutputIntentFactory`; it does not create a second execution
channel. `ShadowOutputBridge` only maps and records `executed=False`.

## Migration status

The contract is complete enough for replay/shadow comparison. Physical
migration remains blocked until exact V2 parity, verified-OFF/readback/lease
parity, and bench evidence are independently accepted.
