# D123 Sprint 59 — Guarded physical resume transaction

## Scope

Source-only work from requested HEAD `57b5b1a2bf718f658eaedab569fa31a8bd7ca987`
on `codex/d118-start-lease-repair-20261019`. No node104, ESP, HA, firmware,
service, deployment, GitHub, dependency install, or physical Output action was
performed. `charge_session.json.mix-authority.json` was already untracked and
was left untouched.

## Transaction and authority

`StartupRecovery.guarded_physical_resume` runs while holding the same
app-scoped `GuardExecutionOwnerLock` used by deferred restore. It requires
automatic-control permission, both guarded OFF latches, an active canonical
controller, and the retained activation candidate. It obtains a *new* direct
`get_native_guard_pre_on_snapshot()` and immediately invokes
`assess_main_guard_before_output_on`; activation-time evidence is never reused.
The assessor proves current freshness/provenance, independently-OFF Output,
normal protection, and already-matching Iset/OCP under the persisted monotone
Guard ceiling. The transaction does not write V/I/OVP/OCP.

Before producing a permit it rechecks session and battery IDs, canonical Guard
revision and exact file-byte digest, in-memory Guard/revision, controller stage
and profile, persisted current target, candidate identity, lock ownership,
controller activation, and recovery permission. The immutable
`GuardedPhysicalResumePermit` binds those identities plus the new Native
callback generation, activation generation, current task, and held lock.

The typed result states are `BLOCKED`, `READY_BUT_NOT_EXECUTED`, and
`VERIFIED_ON_COMMITTED`. Production has no resume endpoint installed, so a
successful source assessment returns `READY_BUT_NOT_EXECUTED` and keeps both
latches. The existing ExecutionPort accepts only a one-use permit and an
injectable endpoint. A positive `verified_on` receipt clears both latch values
at one source location; a failed or absent receipt does not. The synthetic
endpoint injection is not connected to hardware. Emergency OFF remains
independent.

## Verification and limitations

- Requested Python 3.12 venv was not available in this workspace. Existing
  venv candidates lack installed project dependencies; dependencies were not
  installed per instruction.
- Focused imports of startup/restore/Native suites were attempted with the
  existing `/tmp/pcp-sprint-venv`; they could not run because `yaml`, `pytz`,
  and `aiohttp` are absent. This is an environment limitation, not a passing
  test result.
- Source architecture tests were extended for the one latch-clear site, new
  Native read + assessor, no startup Output/setpoint writer, and no persistence
  write/HA aggregate authority.
- Compileall and `git diff --check` are recorded in the final task report.

The remaining work is separately authorized physical/live execution, exact
ESPHome contract compilation/flash/bench validation, and P5 release/acceptance.
No source result establishes physical state or `PHYSICAL PASS`.
