# B1025 — ESPHome managed safety parity review

Run: `rd6018-b1025-20261126-r73-esp-safety-parity`
Branch: `codex/rd6018-b1025-esp-safety-parity-20261126`
Base/code HEAD: `a5364c8cdc2e062a91aaef9861b1dd39e137fd91`
Result: **SOURCE REVIEW ACCEPTED; NO CONTROL SOURCE PATCH**. Physical readiness is documented separately and remains unproven until the supervised P3 bench matrix is executed.

## Scope and authority

Read the supplied `AGENTS.md`, the handoff canon, the first 103-checkbox block in the P0–P9 plan, master plan, V3 runbook, current checkpoint and B1020/B1022 focused acceptance records. The final current policy is the 2026-11-26 owner policy in `AGENTS.md` and current runbook: raw R16=1/2 are observable and nonblocking; R16=3 and unknown nonzero fail closed; no automatic OVP/OCP threshold programming; intrinsic overtemperature and the local managed lease remain independent safety paths. Historical statements in older checklist/handoff text that describe OVP/OCP as software trips are superseded and were not treated as current policy.

The supplied baseline is clean at the exact requested HEAD. No node104, live ESP/HA/RD6018, output/setpoint, firmware, service, production, SSH, network/GitHub, original dirty worktree, staging/commit/push, or other Codex worker action occurred.

## Source crosswalk

| Requirement | Current owner and source evidence | Finding |
|---|---|---|
| Target composition | `esphome/rd6018.yaml` includes `packages/rd6018_safety_lease.yaml`, `rd6018_intrinsic_safety.yaml`, telemetry and live-adoption packages. | Same-node packages; no alternate local safety owner found. |
| Raw R16 meaning | `rd6018_telemetry.py:87-98` maps 0 normal, 1 OVP, 2 OCP, 3 OPP, all other/invalid codes unknown. `runtime/safety/protection_boundary.py:99-138` returns CLEAR for OVP/OCP, TRIPPED for OPP, UNKNOWN for unknown. `runtime/safety/output_policy.py:225-228, 250-257` carries R16 status and blocks only OPP/unknown. | Python source parity with current policy. Raw R16 is preferred over legacy bits by `resolve_protection` (`rd6018_telemetry.py:100-117`). |
| ESP intrinsic local OFF | `esphome/packages/rd6018_intrinsic_safety.yaml:14-56` applies the same nonzero-except-1/2 predicate and internal-temperature cutoff in the binary diagnostic and local 5-second OFF action. The OFF action targets the existing public output switch; the package has no V/I/OVP/OCP setter or ON action. | OVP/OCP are not local software OFF causes; OPP and unknown nonzero are. Local threshold is 55°C. |
| No automatic OVP/OCP threshold writes | Automatic `OutputRequest` construction sites in `application/start_preflight.py:116+` and `application/execution_port.py:304,376` provide V/I without OVP/OCP. The explicit OVP/OCP validation/readback branches in `runtime/safety/output_policy.py:291-329` are conditional on explicit request fields. ESP intrinsic package has no setter. Current managed path does not request/program these thresholds. | No automatic threshold programming defect found. The separate explicit operator capability is not treated as charge-admission policy. |
| Local lease TTL and renewal | `esphome/packages/rd6018_safety_lease.yaml:25-27` declares 900000 ms TTL and 20000 ms stale bound. `runtime/safety/edge_lease.py:70-71,195,527+` owns 900 s TTL and 300 s renewal cadence; YAML documents 5-minute renewals. | Source values align: TTL 900 s, renew 300 s, control age 20 s. Physical timing/firmware behavior remains unproven. |
| Local OFF retry | `rd6018_safety_lease.yaml:366-401` latches trip on control stale or lease expiry, checks every 5 s and issues OFF through `rd6018_output_public`. Intrinsic OFF also repeats every 5 s. | Existing repeated local OFF mechanism is present. |
| Managed / autonomous / HANDS_OFF | Lease package boot logic (`:29-60`) quarantines non-autonomous or conflicting persisted state. Managed lease buttons (`:170-362`) reject autonomous/quarantined/tripped/unsafe states. Autonomous entry/exit require fresh register 10 and 18 and Output OFF (`:278-360`). HANDS_OFF release (`:363-394`) only clears managed ownership and does not set autonomous. | Distinct modes and conservative boot handling present. No new authority was introduced. |
| Physical Output R18 | `rd6018_safety_output_probe` reads register 18 and records its own receive timestamp (`rd6018_safety_lease.yaml:88-111`). Lease arm, disarm, mode changes and quarantine clear require fresh direct R18 evidence. | Register 18 is separately read and used; HA/API entity freshness alone does not substitute in the ESP package. |
| Python renewal and failure containment | `runtime/safety/strict_guard.py:80-160,182-244` requires a positively acknowledged edge lease before ON, renews while managed ON and uses existing verified-OFF containment on renewal failure. `runtime/safety/edge_lease.py` validates returned lease state. | No uncovered Python bypass identified in the reviewed entrypoints. |

## Verification

Executed on the project venv with the requested import path:

```text
PYTHONPATH=.:tests:tools /home/home-pc/.venvs/pcp-test/bin/python -m unittest \
  tests.test_esphome_intrinsic_safety_contract \
  tests.test_esphome_safety_lease_contract \
  tests.test_runtime_safety \
  tests.test_runtime_edge_lease

Ran 44 tests — OK (exit 0)
```

No full suite, ESPHome compiler/build, firmware activation, or physical test was run. Those would not prove behavior on the target unit and are outside this source-only task.

## Conclusion and limits

At this exact source HEAD, the reviewed ESPHome predicates, Python R16 normalization, explicit-only OVP/OCP request shape, lease timing constants, mode separation and R18 ownership agree with the current final policy. I found **no demonstrated source mismatch or unguarded path** warranting a production YAML/Python patch. This is negative source evidence only: it does not establish that the deployed ESP image matches these files, that the physical Modbus register behavior matches the code, or that OFF is actually achieved. The exact finite supervised bench evidence matrix is `docs/acceptance/B1025_ESP_SAFETY_PARITY.md`.

P0–P9 remains 98/103; three P3 and two P8 physical/release items remain HOLD. No checklist promotion is claimed. Draft PR #182, CI #2244 and dummy ESPHome build #163 are task-provided context, not newly queried or executed here.

Changed paths are only `B1025_REPORT.md` and `docs/acceptance/B1025_ESP_SAFETY_PARITY.md`. No code source or shared checkpoint/master/handoff/runbook was edited. `git diff --check` is recorded after report creation.

## Independent acceptance clarification — OVP/OCP are observation-only

The controller inspected the exact ESP intrinsic 5-second OFF predicate and
Python protection normalization and reran the 44-test offline cohort
(44/44 PASS). The original B1025 bench matrix allowed an ambiguous approved
OVP/OCP stimulus. Updated both R16=1 and R16=2 cases to OBSERVATION ONLY:
never deliberately induce OVP/OCP on live hardware, never write OVP/OCP
thresholds as an automatic guard; offline fixture observations are not
physical acceptance. No production source or device changed.
