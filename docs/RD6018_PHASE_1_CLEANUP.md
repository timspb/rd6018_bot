# RD6018 Phase 1 Cleanup

## Scope

Phase 1 is behavior-neutral. It freezes ownership, configuration drift and
legacy route classification before normalizing contracts or moving execution.

## Completed in this phase

- ownership manifest;
- configuration drift report;
- legacy route inventory;
- static import/call/production-composition invariants;
- explicit characterization of transitional actuator surfaces.

## Not permitted in Phase 1

- START or ACTIVE changes;
- safety or timeout changes;
- physical actuator changes;
- configuration value changes;
- deletion of legacy handlers;
- changes to FSM, controller, lease or SafeOutputCoordinator.

## Exit criteria

- static invariants pass;
- all actuator call-site changes require an explicit reviewed inventory update;
- production SHA and deployed configuration checksums are recorded externally;
- no legacy route is removed without a separate migration decision.

## Next phases

1. Phase 2: canonical typed configuration and event contracts.
2. Phase 3: one production actuator execution port.
3. Phase 4: incremental V3 route migration with parity, rollback and bench gates.
