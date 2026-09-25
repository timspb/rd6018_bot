# RD6018 V2 → V3 ownership transition model — Phase 10.3

## Authority matrix

| Component | Current owner | Target owner | Mode | Approval gate |
|---|---|---|---|---|
| UI | V2 | V3 | staged | UI parity and operator rollback |
| telemetry | shared | V3 | mirror | ESP/HA arbitration and freshness |
| configuration | shared | V3 | shadow | no unresolved/conflicting values |
| diagnostics | shared | V3 | mirror | correlated evidence complete |
| persistence | V2 | V3 | shadow | candidates remain non-authorizing |
| domain decisions | V2 | V3 | shadow | shadow acceptance passed |
| safety decisions | V2 | V3 | shadow | zero unexplained safety conflicts |
| execution | V2 | V3 | shadow | intent/rollback/verification parity |
| HA control | V2 | V3 | cutover | explicit control approval |
| ESP control | V2 | V3 | cutover | ESP contract and bench gate |
| physical output | V2 | V3 | cutover | physical bench and emergency rollback |

The target column describes the future authority candidate, not current
ownership. Phase 10.3 has `ownership_transfer_enabled=false`.

## Migration rules

1. Mirror copies inputs without changing V2.
2. Shadow computes V3 decisions and records differences without execution.
3. Staged migration may expose V3 presentation/application boundaries while V2
   remains the active owner.
4. Cutover is a future, separately approved operation; it is not performed by
   this model.
5. Rollback returns authority to V2 and requires fresh safety/ownership
   verification; no old V3 session is resumed implicitly.

## Rollback conditions

- unexpected conflict rate exceeds accepted threshold;
- any unexplained safety or containment divergence;
- lost trace/evidence continuity;
- transport arbitration instability;
- failed rollback or readback verification;
- missing operator, bench or emergency-disconnect approval.

## Dual-run and conflict handling

V2 remains active during mirror/shadow/staged modes. V3 never executes an
`ActuatorIntent`, sends HA/ESP commands, mutates V2 FSM/session, or changes
physical output. Conflicts are persisted as evidence and require explicit
classification; there is no implicit V3 precedence.

START, ACTIVE, V2 runtime and physical ownership are unchanged.
