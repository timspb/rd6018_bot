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

## First physical write: verified OFF only

The first write-capable run is restricted to `DISABLE_OUTPUT`. It must use the
manual `PhysicalExecutionGate` and an active real bench lease. The runner must
not synthesize a lease or safety evidence. `PhysicalExecutionConfig.enabled`
remains `false` by default; enabling it for a bench run is an explicit,
operator-local action and is not a production configuration change.

Required order:

1. Read and record a pre-snapshot.
2. Pass Safety preflight, envelope validation, capability check and manual
   ARM.
3. Send exactly one `DISABLE_OUTPUT` through the selected transport.
4. Read a fresh post-snapshot.
5. Pass only when `output_state == OFF` and `measured_current == 0`.
6. Record operator, timestamps, transport, before/after snapshots, readback and
   result.

The physical sequence is always `V3 -> selected HA or ESPHome transport ->
RD6018 command -> RD state change -> fresh readback confirmation`. HA102 and
ESP128 are alternative paths to the RD, not a chained HA-then-ESP command
sequence. No success is recorded from command delivery alone.

This phase does not set voltage/current, enable Output, reset OVP/OCP or start
the production runtime. HA control is `switch.rd_6018_output`; ESPHome control
is object `output`. Their endpoint and entity mappings remain in
`config/physical/ha102.yaml` and `config/physical/esp128.yaml`.
