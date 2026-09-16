# RD6018 RD transport contract (Phase 5.3)

## Contract

`application.rd_transport.RDTransport` defines the transport-neutral operations:

| Operation | Direction | Meaning |
|---|---|---|
| `read_telemetry()` | read | voltage/current/temperature/output plus timestamp |
| `read_output_state()` | read | authoritative transport report of output state |
| `read_readback()` | read | programmed voltage/current/output readback |
| `set_voltage(value)` | command | request a voltage setpoint |
| `set_current(value)` | command | request a current setpoint |
| `output_on()` | command | request output enable |
| `output_off()` | command | request output disable |

The contract is asynchronous and transport-neutral. It does not define retries,
lease renewal, safety policy, authorization or ownership transfer.

## Adapter boundaries

### `HARDAdapter`

HA-backed implementation boundary. It may translate the common operations to HA
entities in a future adapter module. It must not contain charge profile logic,
FSM transitions or UI presentation.

### `ESPDirectRDAdapter`

ESP-direct implementation boundary. It may translate the common operations to
the direct RD/ESP transport in a future adapter module. It must not contain
charge profile logic, FSM transitions or UI presentation.

Both adapters must be substitutable at the contract level. This does not claim
that either physical path is currently available or safe for production.

## Telemetry/control split

`TelemetryProvider` contains only read operations. `ControlProvider` contains
only writes/commands. `RDTransport` combines both solely as a complete adapter
surface; domain modules must consume the narrower read-only contract and must
not receive `RDTransport`.

## Safety boundary

The contract does not authorize an operation. Existing V2 controller,
SafetySupervisor, SafeOutputCoordinator, lease and physical ownership remain
unchanged. Any future bridge must preserve preflight, activation gates,
readback and rollback semantics before an adapter call.

## Explicit non-goals

No HA client, ESPHome client, transport implementation, polling, command
dispatch, retry policy, lease manipulation or physical command was added.
