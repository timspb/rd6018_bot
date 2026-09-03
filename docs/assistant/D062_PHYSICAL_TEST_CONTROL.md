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

After each physical validation batch, disable `RD6018_PHYSICAL_TEST_CONTROL` and
restart the bot only after Output is positively confirmed OFF.
