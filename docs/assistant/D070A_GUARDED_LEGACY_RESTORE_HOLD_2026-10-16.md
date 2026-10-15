# D070a — Guarded legacy session restore is held until owner reconciliation

**Scope:** source-only safety gate, no hardware commands, no production deployment.

## Observed gap

D068c can classify authentic MAIN Guard pre-ON evidence, but existing
runtime/charge/persistence.py legacy restore did not consult that classifier
and could restore an EFB/Ca/Ca session from charge_session.json before any
guard-aware owner lock and readback transaction existed. A persisted lower
MAIN Iset must never be reset to I0 by an ordinary process restart.

## Applied containment

If the canonical session document contains main_current_guard_v1, the
legacy restore function refuses to resume before mutating the controller or
deleting an expired checkpoint. This includes malformed, pending, or
otherwise untrusted guard records. A real, correctly installed shared owner
and native pre-ON reconciliation will supersede this HOLD in a separately
reviewed integration.

For a session without a guard, existing restore behavior remains unchanged;
no additional restrictions are introduced for AGM or unguarded profiles.

Returning HOLD is NOT independent proof of electrical Output OFF. Actual
output state and edge lease still belong to the existing physical safety
owner, and no previously active guarded session may be called safe merely
because the restore function returned False.

## Evidence / next step

- Five targeted offline tests cover EFB/Ca/Ca, bad/pending guard, old
  checkpoint retention, non-dict session and legacy non-guard expiry.
- Full WSL2 and hosted matrix results must accompany PR acceptance.
- Next: one app-wide lifecycle/execution lock across automatic tick,
  START, operator/manual, startup and deferred recovery, output writes and
  canonical journal commits; prove no deadlock and no bypass.
- D061 adopted-child positive SIGKILL physical test and D063 natural
  EFB/Ca/Ca SAFE_WAIT remain OPEN.
- Physical authorization unchanged: <=15.5 V. AGM and MIX unchanged.
