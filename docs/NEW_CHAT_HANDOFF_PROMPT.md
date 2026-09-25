# New chat handoff prompt — RD6018 forensic investigation

Paste the block below into a new chat.

```text
We are continuing repo-side forensic work on:

Repository: timspb/rd6018_bot

IMPORTANT: read first:
  docs/RD6018_FORENSIC_RUNBOOK.md
on branch:
  codex/pr00-runtime-characterization

The runbook is the persistent project handoff. Use the GitHub connector and inspect the actual repository before making claims.

MODE:
repo-side forensic engineer, not consultant.

Do NOT start by proposing another architecture/refactor plan.
Do NOT continue legacy removal / RuntimeApp extraction yet.
Do NOT deploy.
Do NOT touch production node 101 or ESPHome unless I explicitly authorize operational work.
Do NOT weaken safety tests or guards.

Current objective:
Find the real functional regressions in the current bot and decide, based on evidence, whether to:

1. KEEP_V2_AND_FIX
2. ROLLBACK_TO_V1
3. V1_PLUS_SAFETY_CHERRYPICKS
4. INSUFFICIENT_EVIDENCE

The user reports the current bot has major functional errors and is seriously considering returning to V1. A previous audit concluded KEEP_V2_AND_FIX, but that verdict is not final because much of the evidence is unit/FakeApp/source-contract evidence rather than real production composition.

==================================================
CURRENT REPOSITORY STATE / HISTORY
==================================================

Repository:
  timspb/rd6018_bot

Important code baselines established by forensic audit:

  V1_BASELINE=6da57edd35a0f263c84ab40889dd5a4705142a2e
  V2_START=591be3b882308aae872d8162db5f87107fa107df
  CURRENT_CODE=c204429ccbab1e16beebe18a6be30884f11a4e4a

Default main observed before handoff:
  ef2b4806a16723eaff67451667d0a2c73fca8fc4

Merge-base of current code line with main reported by audit:
  8b5a3c4637f697793809a0c8ada8e2ea2285c5eb

A docs-only handoff/runbook commit was added after c204429 on branch
`codex/pr00-runtime-characterization`; therefore re-fetch the branch head before work and distinguish code changes from docs-only handoff commits.

Forensic audit measured roughly:
  720 commits V1->current
  294 changed files
  +78,424 / -2,880 lines

First major introduction commits reported:
  ChargeControllerV2: 591be3b8
  V2 shadow bot composition: 0ebb145f
  production controller: 174346fc
  V2 manual: 1e111385
  ownership boundary: a8526270
  AUTONOMOUS coordinator: f769912b
  V2 safety layer: 085eb08c
  semantic HMI: 077fbb60

Never assume `main` is the same line as the forensic working branch.

==================================================
PRODUCTION / PHYSICAL CONTEXT
==================================================

Production bot node:
  101

Home Assistant / ESPHome server:
  192.168.1.102

RD6018 ESPHome device:
  hostname: rd6018-controller
  IP: 192.168.1.28
  MAC: C8:2B:96:30:FD:A5

Historical verified ESPHome production firmware before autonomous candidate work:
  firmware #23
  source commit 49eed46159b30b7586cade573cfedbea278f9227
  ESPHome 2026.8.2

Production bot was previously rebaselined successfully to:
  8b5a3c4637f697793809a0c8ada8e2ea2285c5eb
  service: rd6018-bot.service
  workdir: /root/rd6018_bot
  venv: /opt/rd6018-bot-venv

Historical rollback snapshot:
  /root/rd6018_bot-backups/preflight-20260910T063732Z

Do NOT infer c204429 is deployed to node 101 unless proven.

==================================================
NON-NEGOTIABLE SAFETY INVARIANTS
==================================================

- unknown != OFF
- 0 V / 0 A does NOT prove Output OFF
- only canonical fresh Output readback proves OFF
- verified-OFF semantics must remain intact
- fail-closed behavior must not be weakened
- startup authority semantics must remain explicit
- HANDS_OFF != AUTONOMOUS
- PB_MANAGED / HANDS_OFF / AUTONOMOUS are distinct authority states
- no Pb restore when authority forbids it
- ESPHome edge lease / authority contract is a physical safety boundary
- do not change EFB MIX 20h / 24h semantics during forensic/refactor work
- do not extend timeouts or bypass guards just to make tests pass
- node 101 is not an experimental target
- safety-changing changes require explicit physical/bench validation

==================================================
CURRENT RUNTIME ARCHITECTURE
==================================================

There is NO real RuntimeApp class in the current code baseline.
The app is still effectively module-as-app.

Startup is approximately:

python bot.py
  -> import bot_legacy as _legacy
  -> install many V2/runtime monkey-patches onto same module object
  -> create startup authority reconciliation task
  -> start helper/background control
  -> call bot_legacy.main()
  -> DB/init
  -> HA read
  -> try_restore_session
  -> Telegram polling

bot.py uses sys.modules aliasing so `import bot` effectively resolves to the legacy namespace.

PR00 characterization established:
  69 distinct app.<attr> writes
  62 writes from install* functions
  7 writes outside installers

Important namespace owners:
  charge_controller / manual_session_manager / charge_monitor -> v2_bootstrap
  runtime_safety_guard -> runtime_safety + runtime_safety_strict + runtime_safety_v2
  edge_safety_lease -> runtime_safety_strict
  ownership managers -> their rd_* installers
  _build_dashboard_keyboard -> multiple modules (last-writer risk)

Treat installer ordering and cached bound methods as real forensic risks.

==================================================
CONTROLLER / FSM
==================================================

Inheritance chain:

DiagnosticProductionChargeControllerV2
  -> AutoStrategyProductionChargeControllerV2
  -> ProductionChargeControllerV2
  -> ChargeControllerV2
  -> ChargeController

Critical fact:
V2 still executes the legacy scaffold through super().tick().

Do NOT accept “V2 masks legacy transition” as proof that legacy is harmless.
Audit all side effects performed by the legacy scaffold before/after masking.

Shared runtime state historically identified includes:
  current_stage
  stage_start_time
  finish_timer_start
  restored targets
  safe-wait state
  cooling state
  Vmax/Imin records
  delta trigger state
  antisulfate state
  AGM-stage state
  blanking timers
  first-stage hold state
  stuck-current state

Legacy-removal/controller-decomposition work is frozen until stability decision.

==================================================
OUTPUT / SAFETY SURFACE
==================================================

PR00 inventory found:
  36 turn_on/turn_off/safe_enable_output call-sites
  across 19 modules
  bot_legacy alone has 11 direct hass.turn_on/turn_off calls

Direct hass.turn_on is not automatically an unguarded bypass because HassClient itself is wrapped by safety/ownership layers.
Do not mechanically replace these calls during unrelated fixes.

Important modules:
  safe_output.py
  runtime_safety.py
  runtime_safety_strict.py
  runtime_safety_v2.py
  rd_control_mode.py
  rd_startup_authority.py
  rd_managed_adoption.py
  rd_managed_mix.py
  manual_mode.py
  manual_runtime_v2.py
  v2_startup.py
  v2_mix_mode.py
  recipe_output.py

For actuator claims prove LIVE install order/object identity, not source existence of wrapper classes.

==================================================
RESTORE ORDER
==================================================

Previously derived effective outer->inner chain:

rd_hands_off_background
  -> rd_startup_authority
  -> rd_control_mode
  -> production_guardrails_v2
  -> done_storage_restore
  -> MixActiveAuthorityMixin
  -> ProductionChargeControllerV2
  -> ChargeControllerV2
  -> ChargeController

Order is behaviorally significant.

==================================================
AUTONOMOUS / EDGE AUTHORITY
==================================================

AUTONOMOUS is distinct from HANDS_OFF.

Required semantics:
- general-purpose PSU authority mode, not Pb-only
- Wi-Fi/HA/Telegram loss is not by itself a shutdown reason in AUTONOMOUS
- bot actuator/start/restore writes are blocked when edge says autonomous
- telemetry may remain readable
- authority startup is tri-state: unknown/managed/autonomous
- unknown is fail-closed
- local intrinsic hardware protections remain active

Candidate ESPHome autonomous package had persistent edge bit and explicit enter/exit actions requiring fresh direct telemetry + confirmed Output OFF.

Physical candidate checks previously achieved:
- identity PASS
- boot Output OFF PASS
- autonomous enter PASS; Output remained OFF
- autonomous exit PASS; Output remained OFF

Not fully validated:
- bot control boundary with separately running runtime
- physical Wi-Fi-loss behavior
- reboot persistence

Do not call AUTONOMOUS fully production validated.

==================================================
CONFIRMED FORENSIC DEFECTS
==================================================

D-STARTUP-1
Severity: HIGH
First bad:
  0880dcc0d03b7ac292f0ebbed15181cf5fcab5e9
Last known good:
  d3464bedc18c88a8e5b4a067a5fc5353fc02701f

Mechanism:
1. bot.py launches authority reconciliation asynchronously.
2. _legacy_main() continues and immediately calls try_restore_session().
3. startup-authority gate rejects restore while authority remains unresolved.
4. delayed/unavailable edge read yields restore (False, None).
5. after authority later reconciles to managed, legacy session restore is not retried.

Actual effect:
process and possibly Telegram continue running, but interrupted managed charging may silently fail to resume.

This is fail-closed safety-wise but a serious functional startup regression.

D-TEST-1
Severity: MEDIUM / compatibility-contract
First bad:
  c34f6a91dd2e8c3a294766a0413b695566eff61c
Last known good:
  646fab326dec94ce0872284b7fbcadf0bb2170c6

AutoStrategyProductionChargeControllerV2._run_legacy_scaffold_tick()
gained required `manual_active`, while an existing direct test call did not pass it.
Production call site reportedly passes it.
Still: full suite is not green and release remains blocked until resolved/retested.

Environment-only known test issue:
  Windows lacks asyncio.start_unix_server used by test_physical_test_control.
Do not confuse this with Linux production runtime regression.

==================================================
TEST QUALITY / CURRENT EVIDENCE LIMITS
==================================================

Forensic run reported:
  1044 tests
  2 errors
  1 skipped

Focused safety/autonomous tests passed.

BUT most evidence is:
  AST/source contracts
  isolated unit tests
  FakeApp tests
  synthetic adapters

Still missing:
  real bot.py startup timing with delayed authority
  full Telegram update->handler through actual composition
  real HA transport composition
  production restart/restore integration
  physical RD/ESPHome validation

Therefore:
DO NOT conclude “V2 is fine” merely from focused green tests.

==================================================
OBSERVABILITY / HIDDEN FAILURE RISK
==================================================

Audit found roughly 233 broad exception / return-None / unsupervised-task patterns.

Important risks:
- restore failures can be caught/logged while startup continues
- HA/persistence failures may not kill the process
- handlers may return fallback UI instead of surfacing root failure
- background create_task calls lack central supervision

Remember:
  process alive != bot healthy != charge runtime healthy

A real prior symptom existed where Telegram `/start` produced no response after autonomous candidate/runtime work. It was NOT fully root-caused before architecture work took over. Treat that as unresolved evidence.

==================================================
CURRENT HEAD-SPECIFIC MANUAL/HMI WORK
==================================================

Current code baseline c204429 has commit message:
  fix: show manual mix finish evidence compactly

It changed operator_hmi.py and its test:
- imports MANUAL_MIX_FINISH_HOLD_SEC
- clamps displayed hold to configured finish hold
- displays Imin/Vmax + delta evidence

Manual end-to-end behavior still needs real validation despite no proven runtime regression from this HMI-only change.

==================================================
V1 VS CURRENT SUMMARY
==================================================

V1:
- simpler direct monolithic startup
- legacy FSM
- older safety/ownership model

Current:
- bot shim + many installers
- parallel startup authority reconciliation
- V2 authoritative transitions plus legacy scaffold mechanics
- layered readback/safety/ownership
- HANDS_OFF and AUTONOMOUS boundaries
- richer persistence/recovery/HMI

Known current confirmed functional defect:
- restart/restore race

Known unresolved major concern:
- real-world bot has reported large functional errors not fully represented by unit tests

==================================================
ROLLBACK OPTIONS
==================================================

Option A: exact V1
  base 6da57edd35a0f263c84ab40889dd5a4705142a2e
  simpler runtime
  but loses modern readback/ownership/autonomous safety and may conflict with current DB/session/ESPHome contract
  NEVER blindly deploy/reset to V1

Option B: V1 + safety cherry-picks
  no clean cherry-pick set established
  safety layers depend on V2 composition/state
  needs separate branch and full validation

Option C: current + targeted fixes
  keeps safety architecture
  must first prove/fix startup restore and all user-observed functional failures

Previous audit recommended C, but user has NOT accepted that as final.

==================================================
LEGACY REMOVAL / PR00 STATUS
==================================================

The earlier Runtime Ownership Extraction / legacy-removal plan is ON HOLD.

Do not proceed to RuntimeApp facade, constants extraction, session extraction, CycleState, inheritance removal, safety consolidation, or deletion while forensic stability work is open.

Architectural findings from that work remain useful:
- legacy_recipe_adapter.py is live despite its name
- runtime_safety.py still owns shared error/helper contract
- charge_logic.py has many constant-only external importers but few true behavior consumers
- restore wrapper order is sensitive
- EFB 20/24 divergence must be preserved during forensic work

==================================================
WHAT I EXPECT FROM YOU NOW
==================================================

1. Use GitHub connector and read the runbook/repo.
2. Re-fetch exact branch heads before any claim.
3. Work from actual code, not summaries alone.
4. Continue forensic investigation of REAL user-visible failures.
5. For every claimed defect give:
   - first bad commit if derivable
   - function/file
   - reproduction path
   - actual vs expected
   - safety impact
   - user impact
6. Distinguish:
   - source evidence
   - unit/FakeApp evidence
   - production-composition evidence
   - physical evidence
7. Do not make changes until the defect boundary is proven, unless I explicitly tell you to patch.
8. If I ask for patch work, work as repo-side engineer:
   analysis -> minimal patch -> focused tests -> full suite/CI -> commit/PR -> evidence.
9. Do not return repetitive status after every small step.
10. If a physical action is required, say exactly what cannot be proven repo-side.

The immediate question is NOT “how do we clean up legacy”.
The immediate question is:

WHAT IS ACTUALLY BROKEN IN CURRENT V2, AND IS THE SAFEST PRODUCTION PATH TO FIX IT OR RETURN TO V1?
```
