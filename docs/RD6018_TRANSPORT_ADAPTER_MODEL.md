# RD6018 transport adapter model (Phase 8.2)

Статус: shadow adapters only. Реальные HA/ESP clients и physical execution не
подключены.

## Common surface

```text
ExecutionRequest
       |
       +---- HAExecutionAdapter --------> ExecutionResult(deferred)
       |
       +---- ESPDirectExecutionAdapter -> ExecutionResult(deferred)
```

Both adapters implement the same read/control contract:

- `read_telemetry()`;
- `read_output_state()`;
- `read_readback()`;
- `set_voltage()`;
- `set_current()`;
- `output_on()`;
- `output_off()`.

The adapter `dispatch()` accepts a validated `ExecutionRequest` and returns an
`ExecutionResult`. Every supported operation is marked `deferred=True`; no
transport is selected and no command is sent.

## Parity

HA and ESP Direct use the same operation vocabulary, validation and result
semantics. Their only difference is the diagnostic source label. Synthetic
read methods return empty snapshots with a timestamp; they never claim live
hardware evidence.

## Forbidden behavior

The shadow adapters must not import or instantiate:

- HA clients;
- ESPHome/API clients;
- RD physical connectors;
- charge domain/profile/FSM logic;
- Telegram/UI handlers;
- persistence writers.

They do not invoke `ExecutionDispatcher`, `SafeOutputCoordinator`, controller,
lease or any actuator method. A future real adapter must be introduced behind
the same contract and separately authorized.

## Explicit non-goals

No START/ACTIVE wiring, production composition change, real telemetry claim,
physical command, HA call, ESP call or RD6018 state change is included.
