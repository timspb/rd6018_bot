# B1060 — FC03 causal OFF evidence and operator-only boot under durable D084

Date: 2026-11-27. SOURCE-ONLY. P3/P8 physical acceptance HOLD.

## Observed source and hardware facts

Installed ESP 2.3-ha-canonical supplies rd6018_output_command and the correlated terminal status TextSensor. Firmware OutputOwner::on_read_holding_registers(18) performs the one-shot FC03 readback after FC06 acknowledge, then publishes APPLIED with request_id, requested target and observed_r18. The separate Native R18 SensorState telemetry stream is not a causal acknowledgement of that command.

The prior B1058 code incorrectly required the timestamp of the independent R18 callback to be strictly *after* terminal APPLIED. A fresh, correctly typed Native SensorState can precede APPLIED even though the FC03 terminal receipt already proves physical OFF. node104 logged start_pending_post_receipt_native_off_unproven repeatedly. D144 slot25 installation returned "new service not positively stable". One D145 recover restored original B1056 app/venv but failed "restored service not stable", because the pre-existing startup gate waits indefinitely for the quarantined recovery to finish before enabling Telegram polling. The D144 slot25 ledger remained STARTED; recovery is not complete.

## Single-owner correction

1. StartupRecovery requires the exact post-FC06, FC03-backed typed OutputCommandReceipt: requested_target=False, terminal_status=APPLIED, observed_r18=0, valid monotonic completion and connection generation, plus fresh and valid same-generation Native R18 SensorState=0 within eight seconds. The independent sensor corroborates but never substitutes for the causal receipt; it need not publish after terminal APPLIED. No HA REST read, switch fallback or duplicate command owner is introduced.
2. On an explicitly NONAUTONOMOUS edge and a persisted matching durable D084 quarantine, RdStartupAuthorityGate permits a separate managed_quarantined startup disposition for existing operator Telegram UI. It leaves reconciliation_complete=false, managed_recovery_complete=false, managed_actuation_ready=false, and discards deferred restore. ExecutionPort remains fail-closed for ON, V/I, managed START. Only the existing authenticated operator /recovery_clear route may clear the durable D084 incident after verified OFF. UNKNOWN edge and absent/invalid journal never take this UI branch.
3. D144 slot25 must be reconciled through its exact canonical recovery state machine. Never repeat D144 execute, forge polling evidence, remove D084/session bytes, or send direct ESP/Modbus Output commands. A further source-paired release can only follow confirmed safe reconciliation.

## Validation and status

- B1060 focused START and startup-authority + operator recovery: 143 tests and 15 subtests PASS.
- B1059 D137/D142/D144 recovery regression: 96 tests and 39 subtests PASS.
- Git diff --check and py_compile PASS.
- Current node104: physical OFF previously observed via direct ESP Native and independent D151. B1056 app/venv restored following failed slot25 recovery, bot process active but polling readiness not proven. D084 and START_PENDING preserved byte-for-byte, slot25 not COMMITTED or RESTORED.
