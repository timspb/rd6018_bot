# V3 START ACTIVE Bench Authorization Package (Historical)

Статус документа: historical migration package; approval windows are no longer
part of the production START path.

Физическое исполнение и запуск заряда этим документом не выполняются и не
разрешаются автоматически.

## 1. Software identity

| Поле | Подтверждённое значение |
| --- | --- |
| Host | `101` (`192.168.1.101`) |
| Deployment SHA | `92a200dfa583b1e5af6833eae21e00be9dfde2e2` |
| Python | `3.11.11` |
| Virtual environment | `/opt/rd6018-bot-venv/bin/python` |
| Repository | `/root/rd6018_bot` |
| Service | `rd6018-bot.service` active |
| Restart count | `0` at validation |
| DRY_RUN | PASS |
| ACTIVE | denied without activation gates |
| Physical execution | not executed |

Software validation included dependency check, compileall, START route/runner
tests, Telegram dispatch tests and frozen namespace tests. DRY_RUN preserves
trace correlation and does not call the V2 transaction owner.

## 2. Execution ownership

### V3 ownership

- operator intent;
- intent validation;
- preflight;
- approved start plan;
- execution boundary;
- trace correlation;
- activation policy evaluation.

### V2 ownership

- `ChargeController`;
- FSM;
- session lifecycle;
- `SafetySupervisor`;
- `SafeOutputCoordinator`;
- rollback;
- physical execution.

No V3 layer is allowed to become a second controller, FSM or actuator owner.

## 3. Activation gates

ACTIVE may be considered only when all conditions are true:

- `explicit_active_enable=True`;
- `bench_validation_passed=True`;
- `rollback_validation_passed=True`;
- `physical_gate_passed=True`.

The default policy keeps ACTIVE disabled. Missing any one gate is a hard deny.
This package does not change or populate the gates.

## 4. Rollback readiness

Before ACTIVE, the operator must validate and record:

- failed START handling;
- `OFF_CONFIRMED` result;
- `OFF_UNCONFIRMED` containment;
- session containment;
- ownership recovery;
- no automatic retry after ambiguous physical state.

The preserved V2 transaction owner remains responsible for rollback and
verified-OFF semantics. V3 only normalizes and correlates the result.

## 5. Physical bench checklist

Checklist only; nothing below was executed by this package.

- [ ] Safe battery connected and identified.
- [ ] Operator present at the bench.
- [ ] Emergency disconnect available and tested for access.
- [ ] Readback procedure available for voltage, current, Output and protections.
- [ ] Expected voltage/current recorded from the approved plan.
- [ ] Recovery procedure available for enable failure, readback failure and
      `OFF_UNCONFIRMED`.
- [ ] No second START path or concurrent operator is active.

## 6. First ACTIVE run procedure

Only after independent operator approval and all gates PASS:

1. Enable the ACTIVE gate manually for one controlled run.
2. Submit exactly one START.
3. Capture the correlated V3/V2 transaction trace.
4. Verify programmed voltage and current.
5. Verify fresh readback.
6. Verify the Output state transition.
7. Verify the rollback/failure path and record evidence.

Stop immediately on stale telemetry, capability mismatch, safety denial,
readback mismatch or uncertain Output state.

## 7. Explicit blockers before ACTIVE

The following are mandatory PASS items, not assumptions:

- [ ] Explicit operator approval.
- [ ] Bench prepared with a safe battery and emergency disconnect.
- [ ] Rollback validated.
- [ ] Readback validated.
- [ ] Physical gate approved.
- [ ] Activation policy contains all four required ACTIVE prerequisites.
- [ ] One authoritative START route confirmed.
- [ ] Evidence capture is ready before the first command.

Until every item is checked and separately evidenced, ACTIVE remains denied and
no physical START is permitted.

## 8. Current decision

**READINESS PACKAGE CREATED — ACTIVE NOT AUTHORIZED.**

This document records software readiness and the required bench procedure. It
does not authorize changing `StartActivationPolicy`, enabling ACTIVE, starting
Telegram-driven execution, or touching the RD6018.
