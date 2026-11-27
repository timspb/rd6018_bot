# B1038 — same-app ON→OFF callback pairing

**Run:** `rd6018-b1038-20261126-r73-paired-on-off-proof`
**Base:** `c05786dff896b02a75c57bb1bf65f12b6d5e47e5`
**Worktree:** isolated `/tmp/rd6018-b1038-paired-on-off-proof`
**Scope:** source and deterministic fake tests only. No physical device, node104, ESP/HA, command, setpoint, firmware, service, deployment, remote/GitHub, or shared runbook/checkpoint action.

## Result

Implemented `tools/b1038_app_on_off_pair.py`, a read-only helper for the exact `(OutputCommandReceipt, phase-result)` tuples delivered by the existing accepted ExecutionPort ON and canonical emergency-OFF callbacks. Each phase already proves, within its own request, exact receipt identity, same-transport Native callbacks, `SensorInfo`/`SensorState`, R18, finite U/I, monotonic post-terminal timestamps, and the existing 8-second freshness bound. The helper checks those callback objects and records again, including zero post-OFF U/I, same device, same actual transport and API client objects across both requests, and ordered ON then OFF receipt/callback clocks.

The existing phase result did not expose the transport/client object references or raw `SensorInfo` objects. The smallest producer seam adds these references to the successful read-only result in `runtime/physical/transports/esp128.py`. They are references to objects already used by that request. The change adds no connection, cache, persistence, command, timer, output route, admission guard, or authority. Numeric `connection_generation` remains supporting metadata only; equality is never accepted as cross-request identity.

The result is deliberately `SOURCE_PAIR_CONSISTENT` with `physical_p3_status=NOT_ESTABLISHED_SOURCE_ONLY`. The helper does not claim live callbacks occurred, calibrated physical truth, installed source pairing, or P3 acceptance. The legacy B1024 API and result schema are unchanged.

## Exact in-process wiring

The existing ON callback is `ExecutionPort.enable(..., on_native_phase_observed=callback)` and the existing OFF callback is `ExecutionPort.request_emergency_off_receipt(on_native_off_observed=callback)`. Their callback arguments are already `(exact_receipt, phase_result)`. A same-application caller may retain those two values in its current in-process operator operation and pass them directly:

```python
from tools.b1038_app_on_off_pair import pair_execution_port_callbacks

result = pair_execution_port_callbacks(
    on_callback=(on_receipt, on_phase_result),
    off_callback=(off_receipt, off_phase_result),
    now_monotonic=time.monotonic(),
)
```

No persistence is required or added. Call the helper while the observations still meet the current 8-second freshness limit. It rejects callbacks from separate clients/transports even if device ID and generation match. If references are missing, it fails closed with an explicit source error. It does not issue either operation; the only commands remain the existing ExecutionPort operations and their existing owner/guards.

## Verification

Using `/home/home-pc/.venvs/pcp-test/bin/python`, `PYTHONPATH=.:tests:tools`, and inert `TG_TOKEN`:

```text
python -m unittest tests.test_b1038_app_on_off_pair tests.test_b1034_tasklocal_on_receipt tests.test_b1037_same_client_native_off_readback tests.test_b1024_native_phase_evidence
Ran 30 tests — OK
```

The 8 new deterministic cases cover a matching existing callback pair, exact distinct receipt IDs, same original transport/client, equal generation with distinct clients/transports, preterminal/stale callbacks, missing R18, nonzero post-OFF voltage/current, cross-device records, and missing/unobserved callbacks. No broad test run was performed.

## Physical acceptance remains HOLD

There is no live Native callback sample here, and the helper output is source consistency only. P3 remains **HOLD**; canonical checklist remains 98/103, with its three P3 physical items and two P8 physical/release items on HOLD. No claim is made that node104 or the target hardware is ready or that any physical state is OFF.

Finite operator path when separately authorized by the project owner: run the approved paired bench procedure on the target using the existing application and sole ExecutionPort; collect the exact accepted ON and emergency-OFF callback tuples from those operations; invoke this helper in that same process while both Native observations meet the 8-second bound; retain the callback result and direct live ESP Native evidence under the existing P3 acceptance process; then have the independent project architect/acceptor review the physical evidence and existing release gates. If either callback is missing, mismatched, stale, or does not show OFF with zero measured U/I, stop the evidence attempt and keep P3 HOLD. This source task did not start that procedure.
