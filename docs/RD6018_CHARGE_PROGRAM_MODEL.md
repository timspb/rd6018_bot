# RD6018 charge program model (Phase 5.1)

Значения ниже отражают текущие V1/V2 contracts and factory recipe data. В этой
фазе значения не изменяются и не исполняются.

## Common contract

Every program defines: phase target(s), required measurements, transition guard,
termination/evidence rule, hold/timer limits, and domain safety envelope.
Output writes, HA, Telegram and lease operations are explicitly outside it.

| Profile | Main | Mix | Exit/hold | Authority/limits |
|---|---|---|---|---|
| AGM | staged 14.4/14.6/14.8/15.0 V; 8 A factory target; I<0.2 A hold 2 h | CC/CV around 16.3 V, 2.4 A | Vmax→Delta-V in CC or Imin→Delta-I in CV; 3 confirmations; 2 h hold | 10 h Mix; 17.5 V outer manual limit; temp-comp coefficient 0.016 V/°C |
| EFB | 14.8 V, 7 A; I<0.3 A hold 3 h | 16.5 V, 2.1 A | same confirmed Delta and 2 h hold | V2 strategy 24 h; legacy scaffold 20 h; generic AUTO ceiling 16.5 V |
| Ca/Ca | 14.7 V, 7 A; I<0.3 A hold 3 h | 16.5 V, 2.1 A | same confirmed Delta and 2 h hold | 20 h Mix; temp-comp coefficient 0.018 V/°C |
| Custom | explicit Main V/I, user Delta and time limit | explicit profile-specific targets/Delta | explicit validated rule; no implicit chemistry recipe | default legacy limit 24 h; bounded by global current and voltage envelope |

## Phase behavior

`MAIN` applies tail-current and plateau evidence. `RECOVERY` may return to
Main only through the strategy contract. `MIX` is a separate authority with
CC and CV exit policies. A confirmed Delta starts a sticky two-hour hold;
timeout is a safe/diagnostic path, not a successful storage completion.

Legacy `DESULFATION` is a bounded recovery attempt after profile-specific
stuck-current evidence. It exits through `SAFE_WAIT`, preserving the outer
V2 safety/output owner.

## V1/V2 divergences to resolve before V3 execution

1. EFB Mix maximum: `charge_logic.py` uses 20 h, current V2 factory strategy
   uses 24 h. Choose one canonical contract with an explicit decision record.
2. Native V3 CC Delta implementation currently captures a reference current and
   detects a current drop; production parity documentation expects Vmax/Delta-V
   evidence. Do not wire CC execution until resolved.
3. Custom is explicit data, not a chemistry alias. It needs a validated recipe
   contract before registry adoption.

## Required domain measurements

`voltage`, `current`, `temperature`, `output_state`, and monotonic `time` are
required where their rule is active. Transport connectivity, HA health, lease
state and source freshness belong to infrastructure context and cannot alter
the program definition silently.

## Completion and containment

Completion requires accepted evidence and hold. Main/Mix authority expiry,
invalid measurements, or a safety violation produce a non-success decision.
The existing V2 controller/SafeOutputCoordinator performs any physical
containment; this model only reports the domain decision.
