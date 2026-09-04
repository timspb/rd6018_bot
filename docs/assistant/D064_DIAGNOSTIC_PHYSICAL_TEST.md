# Diagnostic probe cancellation / restart physical gate

Status: **repo/software ready; physical validation pending**.

The existing root-only `RD6018_PHYSICAL_TEST_CONTROL` AF_UNIX plane now exposes two hard-coded operations:

```text
diagnostic_probe_cancel_after_step
diagnostic_probe_prepare_restart_window
```

Both require initial `HANDS_OFF`, canonical Output OFF, normal raw protection, battery temperature below 35 C, fresh edge Modbus state, lease unarmed/untripped, no active AUTO/Manual/D061/D062 authority, and a saved non-CUSTOM Pb `battery_id`.

The client cannot supply voltage/current/protection/entity/timestamp values. The harness temporarily returns RD to `PB_MANAGED` and starts the ordinary production Manual path with exactly `14.00 V / 0.30 A`; ordinary derived protection is `14.10 V / 0.40 A`. The controlled probe can only reduce current to `0.20 A`.

## Cancellation

`diagnostic_probe_cancel_after_step` runs the real `PersistentControlledCurrentProbe`. After a real baseline and positive 0.20 A readback, its second sample is held at an await point and the task receives a real `Task.cancel()`.

PASS requires the production probe cancellation cleanup to restore 0.30 A and positively read it back while Output is still ON. The probe journal must no longer be RUNNING. The harness then stops the temporary Manual session through normal verified Output OFF, requires lease OFF, and restores `HANDS_OFF`.

Any probe/journal infrastructure failure after temporary Manual start is also covered by shielded verified-stop cleanup; it may not strand test authority.

## SIGKILL restart

`diagnostic_probe_prepare_restart_window` returns only after all of these are true:

- Output remains positively ON;
- Iset 0.20 A is positively read back;
- edge lease is armed;
- the durable diagnostic PROBE journal record is still RUNNING.

The response opens a hard-coded 20 s window. The physical executor must SIGKILL the production `bot.py` process. A graceful service restart is not equivalent because asyncio cancellation can execute the normal probe restore path before process exit.

If SIGKILL does not occur, the in-process deadline cancels the probe, lets the production cleanup restore 0.30 A or force OFF, stops Manual with verified OFF, and restores `HANDS_OFF`.

After a real SIGKILL, normal startup `recover_diagnostic_persistence()` must convert the RUNNING probe to `ABORTED_RESTART` and invoke the already-composed production `app.hass.turn_off()` path. On this branch that is canonical post-command register-18 OFF verification followed by edge lease disarm. Neither the probe nor Manual authority may resume.

No ESPHome, TTL/renewal cadence, chemistry policy, HA registry, DNS, or normal diagnostic semantics are changed by this test surface.
