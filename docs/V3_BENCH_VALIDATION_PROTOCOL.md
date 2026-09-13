# V3 bench validation protocol

Automatic execution remains disabled. The bench layer defines reproducible
manual scenarios and records evidence; it does not create a transport or
enable the physical bridge. A real run must use the existing
`PhysicalBridgeExecutor`, whose `PhysicalExecutionGate` requires explicit
configuration, operator ARM, safety approval, active lease, and capability
match.

Run in order:

1. `discovery`: capability discovery and hardware snapshot only.
2. `read_only`: voltage, current, temperature, output, OVP/OCP and setpoint readback.
3. `verified_off`: disable, confirm Output OFF, verify current, then reset protection.
4. `safe_parameter_write`: set voltage and current, with readback after each; never enable.
5. `controlled_enable`: set V/I/OVP/OCP, read back, enable, and verify ON.

Any missing safety precondition, stale/invalid readback, HARD_STOP, capability
mismatch, or gate rejection is a fail-closed result. Every step records
operator, command, expected/observed result, readback and notes. The final
controlled-enable scenario is not an automatic charge test and must not be
connected to scheduler, Telegram, HA, or production runtime.

