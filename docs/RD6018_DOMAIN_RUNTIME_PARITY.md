# RD6018 domain runtime parity (Phase 7.1)

Статус: domain-only validation. Telegram, HA, ESPHome, RD transport,
persistence and physical execution are not involved.

## Classification

- **KEEP** — semantics required for V1/V2 compatibility and represented by the
  pure V3 contracts.
- **CHANGE** — an intentional future V3 contract change, not silently applied
  by this phase.
- **UNRESOLVED** — observed drift or insufficiently agreed semantics; retained
  as a blocker.

## 1. FSM parity

| Area | V1/V2 baseline | V3 pure runtime | Result |
|---|---|---|---|
| lifecycle states | IDLE, PREP, MAIN, DESULFATION, MIX, SAFE_WAIT, COOLING, DONE | same canonical states plus pure strategy substates | KEEP |
| initial transition | IDLE -> PREP for automatic start; explicit Custom may enter MAIN | transition table permits IDLE -> PREP/MAIN | KEEP |
| main path | PREP -> MAIN; MAIN may enter recovery/desulfation/Mix/safe wait | same phase boundary | KEEP |
| completion | accepted evidence/hold, then DONE; timeout is not success | pure decision reports completion/reason only | KEEP |
| invalid transition | reject rather than mutate an unrelated state | strict `ChargeEngine.transition()` rejects | KEEP |
| physical terminal action | V2 owner performs verified OFF/containment | absent by design | KEEP boundary |

V3 intentionally keeps generic program-local labels for evaluator compatibility;
canonical FSM callers use the strict transition API.

## 2. Profile parity

| Profile | V1/V2 facts | V3 factory/domain evidence | Result |
|---|---|---|---|
| AGM | staged 14.4/14.6/14.8/15.0 V; 2 h low-current holds; Mix authority 10 h | factory recipe: Main 15.0 V/8 A, 0.2 A/7200 s tail, Mix 16.3 V/2.4 A, 10 h | KEEP |
| EFB | Main ~14.8 V; Mix ceiling 16.5 V; legacy scaffold 20 h vs V2 strategy 24 h | factory recipe: 14.8 V/7 A, Mix 16.5 V/2.1 A, authority 24 h | UNRESOLVED Mix maximum |
| Ca/Ca | Main ~14.7 V; Mix 16.5 V; Delta/hold termination; Mix 20 h | factory recipe: 14.7 V/7 A, Mix 16.5 V/2.1 A, authority 20 h | KEEP |
| Custom | explicit Main V/I, user Delta and time limit; bounded by outer envelope | explicit registration only; no implicit chemistry recipe | KEEP contract / CHANGE registry policy later |

Custom completeness requires profile identity, Main targets, Mix/Delta rule,
hold/timer and validated limits. No fallback chemistry may be inferred.

## 3. Strategy parity

| Rule | V2 production meaning | V3 pure runtime | Result |
|---|---|---|---|
| CV finish | capture Imin, confirm Delta-I, sticky hold | `CVMixExitPolicy` captures Imin and confirms Delta-I | KEEP |
| CC finish | production contract is Vmax then confirmed Delta-V | native `DeltaProgram` captures reference current and detects current drop | UNRESOLVED parity blocker |
| confirmation | repeated evidence before hold | confirmation counter before `CONFIRMED_HOLD` | KEEP |
| hold | sticky 2 h hold before terminal completion | configurable `hold_seconds`, default 2 h | KEEP |
| authority timeout | safe/diagnostic exit, not successful completion | `MixPolicy` returns `MIX_TIMEOUT` completed decision | KEEP |
| EFB authority | V2 strategy 24 h; old V1/V2 scaffold contains 20 h | factory value 24 h | UNRESOLVED canonical source |

The CC difference is recorded, not corrected. Wiring it to execution requires
an explicit domain decision and new golden vectors.

## 4. Session parity

- `start` creates a logical session only after identity/profile are present.
- `stop` is terminal logical state; it does not issue Output OFF.
- `pause` is allowed only from ACTIVE; `resume` only from PAUSED.
- restart is a candidate restore, never an automatic physical resume. Fresh
  measurements, safety/preflight and operator authorization remain required.
- V3 `SessionManager` owns logical lifecycle; V2 persistence/physical owner is
  not imported.

## Golden scenarios

1. `PREP -> MAIN` is accepted.
2. `MAIN -> MIX` is accepted; `MAIN -> IDLE` is rejected.
3. AGM factory recipe preserves staged Main and 2 h hold.
4. EFB factory recipe preserves 24 h strategy authority while documenting the
   legacy 20 h conflict.
5. CV Delta reaches tracking, confirmed hold and completion only after evidence
   and hold.
6. Session ACTIVE -> PAUSED -> ACTIVE -> STOPPED is valid; resume from STOPPED
   is rejected.

## Decisions

### KEEP

- canonical phase vocabulary and invalid-transition rejection;
- AGM/EFB/Ca/Ca targets represented by pure profiles;
- confirmed Delta and sticky hold semantics;
- logical session lifecycle without physical authority;
- timeout as non-success/containment candidate.

### CHANGE

- future V3 must choose one canonical EFB Mix authority;
- future V3 must expose a deliberate Custom recipe schema;
- future V3 may replace generic program-local stage labels with typed substates
  only after compatibility vectors are complete.

### UNRESOLVED

- EFB Mix 20 h versus 24 h;
- CC Vmax/Delta-V versus V3 current-drop implementation;
- exact restart reauthorization policy;
- final mapping from domain containment request to existing V2 owner.

No unresolved decision was changed automatically in Phase 7.1.
