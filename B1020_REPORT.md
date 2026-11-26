# B1020 — P3/P8 real hardware acceptance preparation

Date: 2026-11-26
Branch: `codex/rd6018-b1020-hardware-acceptance-20261126`
Base/current HEAD: `775c856c14a2d4ab78e2e335a7bd6deda58c7fd2`
Initial working tree: clean.
Scope: documentation-only preparation in the specified independent clone.

## Result

Created the ready-to-execute supervised physical matrix at
[`docs/acceptance/B1020_P3_P8_PHYSICAL_ACCEPTANCE.md`](docs/acceptance/B1020_P3_P8_PHYSICAL_ACCEPTANCE.md).
It maps the open P3 and P8 checks to the existing D091 read-only collector,
D106 observer, B16 programmed-readback route, D061 typed test control, D094
offline-only harness, D090 release procedure and production operator routes.
For actions without a safe general live CLI, it explicitly requires the
operator's existing production route and says to mark BLOCKED rather than
inventing a command.

The matrix includes deterministic before/after fields and PASS/FAIL/BLOCKED
rules for V/I programming/readback, ON/OFF Native receipt causality, R18,
R16=3 OPP and unknown nonzero faults, thermal and the physical 900 s local
lease gate, equipment authorization, and verified OFF/operator control. It
separates P8 physical release acceptance from any later node104 deployment
decision and preserves the current 97/103 count and HOLDs.

The controlling current owner policy is represented: OVP/OCP registers 82/83
and R16=1/2 are diagnostic/operator-managed only and never automatic software
or ESP protection/stop/admission conditions. No intentional OVP/OCP trip is
included. The D065-specific 15.5 V setpoint ceiling is identified as a test
envelope rather than a general battery target; any battery-connected test
requires explicit chemistry, capacity, battery identity and approved target.

## Evidence and limits

- Inspected `AGENTS.md`, the canonical P0–P9 plan, handoff canon, master plan,
  runbook and current checkpoint; safety/Native evidence and lease rules; and
  D090/D091/D094/D102, B16, physical-test-control and existing bench procedures.
- The first canonical checklist still has six open criteria: three P3, two P8
  and one P9. This preparation does not close any item.
- D091 is a read-only proof collector bound to the authorized node104 runtime;
  it is not a local general-purpose live test command. D094's D065 executor
  explicitly accepts `OfflineNode` only and disables live execution. These
  boundaries are recorded in the matrix.
- No device/system connection, live test, firmware build/flash, HA/ESP call,
  service restart, SSH, physical setpoint or Output action, network/GitHub
  access, source change, test-suite run, stage, commit or push occurred.
- No production source safety defect was established. No shared runbook,
  checkpoint, master plan or handoff document was edited; those are left for
  controller reconciliation.
- Task-supplied CI #2243 and ESPHome build #162 are recorded only as supplied
  source-build context, not independently queried and not physical evidence.
- Node104 state and origin gap were not queried. No R7.2 execution or ACK is
  claimed here. Existing Wake R7.3 launcher owns completion delivery.

## Changed paths

- `B1020_REPORT.md` — this report.
- `docs/acceptance/B1020_P3_P8_PHYSICAL_ACCEPTANCE.md` — executable future
  bench matrix and evidence/decision criteria.

Both P3/P8 remain **HOLD**; node104 deployment is **not authorized**. The
physical matrix must be used only after a separate owner authorization and
accepted release-candidate boundary. No release is pre-approved.


## Independent controller review — superseded B16 historical instruction

The controller inspected the current production source
`physical_test_control_programmed_readback.py`: its readback map and
same-value adapter wrappers include **set_voltage and set_current only**,
with no OVP/OCP setter operations. The legacy
`docs/assistant/B16_PROGRAMMED_READBACK_PHYSICAL_TEST.md` still says the old
coordinator writes OVP/OCP/V/I; that historical text conflicts with the
currently accepted canon. The B1020 execution matrix has been corrected to
explicitly forbid following those obsolete steps and to require verification
of the exact installed V/I-only B16 version before any future authorized
test. No hardware or source code was modified, and this is not a physical PASS.


## Independent controller clarification — no circular release prerequisite

Gate 0 now distinguishes explicit supervised BENCH TEST approval of the exact
source/scenario from final P8 production release acceptance, which necessarily
follows the P3 physical evidence. No added signature, approval system, or
circular P8-before-P3 gate is introduced. Equipment deployment remains HOLD.
