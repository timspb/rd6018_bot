# D068c — Canonical MAIN Guard pre-Output-ON reconciliation

Source-only, non-actuating, and NOT wired into any production startup/restore/START/Telegram route. Completes the pure admission-evidence contract for a FUTURE implementation; does not itself authorize Output ON.

A guarded EFB/Ca/Ca MAIN session may be marked RECONCILED only if:
- real controller has restored its bound Guard, and exactly matching signed/checksummed canonical charge_session.json identity and revision can be read;
- original session, battery, stage, capacity, recipe current, segment, committed ceiling and sequence agree; no pending proposal, fault or ambiguous restart;
- active execution owner and independent Edge Safety Lease have current positive proof;
- canonical Output register-18 is fresh OFF, protection register NORMAL, and native programmed V2 Iset/OCP are fresh, time-coherent and match the proposed resume current;
- proposed and readback Iset are not above the previous monotone ceiling; OCP readback matches its existing provisional 0.1-A headroom.

The result is one of NOT_APPLICABLE (no Guard in either owner or document), BLOCKED (unknown, failed or incompatible proof), or RECONCILED (Guard-specific evidence only). RECONCILED is NOT a global Output ON permit: existing thermal, power, independent OFF, lease, stage and owner safety apply separately. If a lower Iset must be programmed while OFF, that must be a separate canonical-owner action followed by a NEW native readback and another full evaluation. This module has zero physical/device/session writes.

All guarded sessions remain blocked until a production orchestration owner routes ALL Output ON paths through this check under ONE lifecycle lock, with no bypass via manual START, background recovery, deferred startup or direct HA writes. Native Iset/OCP resolution/headroom and fresh lease proof need physical readback verification; D061 positive adopted-child SIGKILL remains open. No >15.5V physical trials; no MIX recipe or AGM changes.
