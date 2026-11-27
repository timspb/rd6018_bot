# P1-AD082 — Safety authority owner decisions
Date: 2026-11-15
Status: ACCEPTED — six primary owner approvals; no code movement.

## Decisions

| Module | Primary owner | Decision and exclusions |
|---|---|---|
| runtime/safety/engine.py | Safety Authority | APPROVED AS-IS. Pure evaluation of supplied intent, measurements and context. No acquisition, mutable runtime state or actuator. |
| runtime/safety/edge_lease.py | Safety Authority | APPROVED WITH NARROW EXCLUSION. Lease policy/configuration, ACK epoch, renewal/suspension state, validation and lifecycle belong to Safety Authority. Native/HA button and entity transport invocation belongs to Physical Execution. Keep one EdgeSafetyLease instance; no second timer/lease manager. |
| runtime/safety/output_policy.py | Safety Authority | APPROVED WITH NARROW EXCLUSION. Policy DTOs, snapshot normalization and SafetySupervisor verdicts belong to Safety Authority. SafeOutputCoordinator transaction effects and adapter execution remain Physical Execution. No parallel coordinator/policy. |
| runtime/safety/critical_telemetry.py | Safety Authority | APPROVED AS-IS. Pure classification of supplied critical telemetry/protection/temperature values. Telemetry retains acquisition/provenance. |
| runtime/safety/telemetry_recovery.py | Safety Authority | APPROVED WITH NARROW EXCLUSION. Pure unsafe-observation and callback-recovery eligibility classification. Telemetry retains source facts/freshness; Managed guard/Recovery retain grace clock, quarantine and recovery lifecycle. |
| runtime/safety/temperature_integrity.py | Safety Authority | APPROVED WITH NARROW EXCLUSION. Integrity policy, anomaly/latch/re-arm algorithm and one monitor instance. Durable file mechanism remains a persistence adapter detail; no second temperature state owner. |
| runtime/safety/runtime_guard.py | NO FILE-LEVEL APPROVAL | Mixed: Safety Authority owns evidence/policy/latches; Physical Execution owns captured raw adapter calls, output verification and setpoint effect seam. Keep the installed guard as the one ExecutionPort physical owner. Only a function-group contract is justified; no new guard or wrapper. |

## Canonical boundaries

- Firmware rd6018_safety_lease remains the physical 900-second deadline/armed/tripped/generation owner. One Python EdgeSafetyLease per managed guard owns the renewal ACK epoch, suspended flag and operation serialization. Existing TTL and cadence remain unchanged.
- ManagedRuntimeSafetyGuard remains the production managed OVP/OCP/OPP decision and containment owner. Raw R16 normalization stays at the typed telemetry/protection boundary; MAIN Guard, Application and UI do not decode raw R16.
- Managed Storage proof does not bypass OVP/OCP/OPP, temperature, telemetry freshness, lease or verified-OFF rules.
- Firmware's static R18 owner remains the sole physical Output writer. No duplicate R18 writer was found in the seven audited targets.
- AD072 START cancellation containment remains OPEN: cancellation after Native ON submission does not guarantee a same-owner OFF submission and terminal receipt. No source patch or partial ExecutionPort-only change is authorized by AD082.

## Evidence and limits

Independent source review of the complete AD081 report and the six approved source modules confirms the proposed ownership boundaries. AD081's seven target source files, production composition and adjacent decision context were inspected. Tests were NOT RUN for AD081; no pass count or physical/firmware proof is claimed.

Relevant test inventory: test_runtime_safety.py, test_runtime_safety_audit.py, test_managed_runtime_safety.py, test_hass_safe_output_gate.py, test_safe_output.py, test_output_off_containment.py, test_runtime_hardware_trip.py, test_live_protection_policy.py, test_transport_outage_policy.py, test_foreign_output_ownership_grace.py, test_live_freshness_and_mix_eligibility.py, test_rd6018_telemetry.py, test_protection_boundary_architecture.py, test_protection_readback_heartbeat.py, test_execution_port_policy_boundary.py, test_guard_execution_owner_lock.py, test_modularization_physical_wiring.py, test_physical_connector_composition.py, test_output_enable_inventory.py, test_production_entrypoint.py, test_autonomous_startup_authority_contract.py, test_d072_start_manual_owner.py, test_start_transaction_service.py, test_esp_output_command_receipt.py. Not run in this decision.

No modules moved. No source, tests, CSV, registry or generated artifacts changed. No HA/ESP Native/network/hardware/firmware/OTA/node104/deployment or service operation. Release remains HOLD.
