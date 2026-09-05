# D062/D063 physical-test control extension

This extension is **validation infrastructure only**. It is composed into the existing
`RD6018_PHYSICAL_TEST_CONTROL=1` in-process AF_UNIX server and creates no additional
listener. With the base control plane disabled, these operations are unreachable.

Production D062/D063 semantics remain in `rd_managed_mix.py`; the extension does not
duplicate the managed-Mix state machine.

## Operations

### `d063_prior_age`

Read-only. Reads the current live Output plus HA Recorder Mix evidence and reports
whether the current active session has a reliable explicit uninterrupted
`OFF -> ON -> ... -> current ON` edge.

An unproven age is returned as `proven=false` / `resolved_elapsed_s=null`; it is never
converted to zero.

### `d062_adopt_test_budget`

Arguments:

- `battery_id`
- `remaining_budget_s`

`remaining_budget_s` is deliberately restricted to **30..300 seconds**. The operation
resolves the selected saved Pb battery, performs the production D061 + chemistry
preflight, and creates an explicit operator-declared prior-age floor:

```text
declared prior age = chemistry hard limit - remaining_budget_s
```

If Recorder proves an older current session, the larger age wins. Therefore this test
operation can only make the physical validation budget more conservative; it cannot
create a new/full Ca/Ca 20 h, EFB 24 h or AGM 10 h window.

The resulting preview is delegated to the existing
`ManagedMixAdoptionCoordinator.adopt()`. A successful takeover remains non-actuating:
the operation itself never calls Output ON and never writes Vset/Iset/OVP/OCP.

### `d062_verified_stop`

Available only while `MIX_ADOPTED` owns active/off-pending authority. Delegates to the
production `stop_by_operator()` verified-OFF path and then requires canonical
Output/V2 OFF readback.

### `d062_fault_toctou_precommand`

Arguments:

- `battery_id`
- `remaining_budget_s` in the same conservative **30..300 second** range.

Uses the same real D062 preview/adoption path, but changes only the second **in-memory**
setpoint readback before the edge command. No HA/RD value is written.

The expected result is a read-only production TOCTOU rejection with:

- `command_may_have_executed=false`;
- unchanged edge generation;
- external Output still ON;
- no edge Adopt command;
- `hardware_writes_injected=0`.

### `d062_fault_ambiguous_edge_ack`

Arguments:

- `battery_id`
- `remaining_budget_s` in the same conservative **30..300 second** range.

Uses the real D062 coordinator and sends the real edge live-adoption command. After the
command is accepted, only the bounded positive-ACK readback window is hidden. The
wrapper is exhausted before verified-OFF/lease-disarm readback.

The production coordinator must therefore classify the command as uncertain and drive
its existing `MIX_ADOPTED_INCOMPLETE_AFTER_EDGE` verified-OFF containment. The test
surface never synthesizes OFF success and never writes V/I/OVP/OCP.

## Status

The existing `status` operation is extended with `managed_mix`:

- state / battery / chemistry;
- prior age and source;
- adopted and total active elapsed time;
- remaining chemistry budget;
- max/current authority;
- finish-hold marker;
- terminal reason and last status.

## Security / lifecycle

The base physical-test server remains:

- disabled by default;
- `/run/rd6018-bot-physical-test-control.sock`;
- AF_UNIX only;
- mode `0600`;
- no TCP listener;
- no eval or arbitrary entity/setpoint write interface.

The D062 fault operations accept only saved `battery_id` plus a bounded conservative
remaining-budget argument. They do not accept entity IDs, Output commands, setpoints or
protection values.

After each physical validation batch, disable `RD6018_PHYSICAL_TEST_CONTROL` and
restart the bot only after Output is positively confirmed OFF.
