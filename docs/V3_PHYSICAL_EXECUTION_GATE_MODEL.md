# V3 physical execution gate

Physical execution is exposed only as an explicitly constructed,
manual-bench contract. `PhysicalExecutionConfig.enabled` defaults to `false`
and runtime activation is rejected. With the gate enabled, an operator must
arm it before a plan can execute; the plan must also have an accepted
execution-policy decision, an active lease, and compatible hardware
capabilities.

`PhysicalBridgeExecutor` receives an injected transport and records every
attempt in `PhysicalExecutionAudit`. It does not create a transport, wire
itself into production, or provide Telegram/HA activation.

The modeled order is fail-closed: ENABLE programs and reads back before
enabling, then verifies ON; DISABLE disables, verifies OFF, and only then
resets protection; RESET performs the reset and readback. Any exception moves
the gate to `FAILED` and records the error. A future bench integration must
provide the transport and separately validate RD/V2 parity, lease behavior,
readback, verified OFF, rollback, and emergency stop.

No production physical execution was enabled or performed in this phase.
