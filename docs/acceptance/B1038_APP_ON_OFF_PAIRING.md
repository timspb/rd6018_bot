# B1038 app-owned ON/OFF pairing contract

This note describes source behavior only. It is not a physical acceptance or release record.

## Producer and consumer

The existing `ExecutionPort.enable(..., on_native_phase_observed=...)` callback and `ExecutionPort.request_emergency_off_receipt(on_native_off_observed=...)` callback each deliver the exact typed `OutputCommandReceipt` plus the phase result after that existing request's owner/guard acceptance. Their Native sample is read from the same ESPHome connection already owned by the application request. Successful samples now include the original `source_transport` and `source_client` object references, and each record includes the raw `SensorInfo` alongside the original `SensorState`.

Pass each exact callback pair to `tools.b1038_app_on_off_pair.pair_execution_port_callbacks(on_callback=..., off_callback=..., now_monotonic=time.monotonic())`. The helper compares actual transport and API-client objects with `is`, and validates each receipt, target/R18, Native source/type, raw entity/state consistency, one device per phase, finite measurements, post-terminal timestamps and freshness no greater than 8 seconds. It enforces ordered ON receipt/callbacks before OFF receipt/callbacks and zero measured voltage/current after OFF. Equal integer connection generations, an ESP ID, matching type, or matching timestamps never substitute for original object identity.

The caller passes callback values explicitly. The helper holds no state and creates no observer, connection, command, cache, or persistence. The existing B1024 external-envelope API is unchanged.

## Result meaning and limits

Successful output is `SOURCE_PAIR_CONSISTENT`, `same_transport_client_status=SAME_OBJECTS`, and `physical_p3_status=NOT_ESTABLISHED_SOURCE_ONLY`. This means only that the supplied source callback objects are internally consistent. It does not establish that a live target produced them, that physical calibration or an installation matches the source, or that P3 passed. Missing origin references are rejected. Separate-client data such as D106 cannot be paired by matching its local generation counter.

## P3 physical HOLD and operator path

P3 remains **HOLD** pending actual project-authorized live evidence. The canonical P0–P9 checklist remains 98/103; three P3 physical checks and two P8 physical/release checks remain HOLD. No hardware collection or actuation was performed for B1038.

When the existing project owner separately authorizes physical acceptance, use the approved target bench procedure through the running application and its sole ExecutionPort. Capture the exact existing accepted ON callback and canonical emergency-OFF callback in that same process, run the helper while both callback samples still satisfy the 8-second bound, and submit the helper output with the fresh direct ESP Native evidence required by the existing P3 procedure. Independent acceptance must verify target identity and live R18/U/I, plus existing protection and release conditions. Any missing/stale/mismatched callback or nonzero post-OFF voltage/current leaves P3 on HOLD. This helper never authorizes an operation or promotes source tests to physical PASS.
