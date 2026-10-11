# UI callback acceptance — Wave 2

Offline acceptance evidence for the canonical `bot.ProductionComposition` at
the Wave 2 implementation head.

| Measure | Result |
| --- | ---: |
| Installed callback handlers | 85 |
| Actually dispatched by fake aiogram callbacks | 25 |
| Uncovered handlers | 60 |
| Static declarations | 89 |

The 25 covered rows are derived from handlers that were matched, invoked, and
observed to produce a callback acknowledgement and/or fake-message response.
The report does not treat `handler.check()` as execution coverage.  The
tracked static inventory is required by the tool and is therefore available in
a fresh checkout; the report records the runtime `HEAD` used to produce it.

START callbacks use a fake rejected transactional route and assert that
`safe_enable_output()` is never called. Lease, ownership-transfer, Output ON,
and stop/execute endpoints remain separate hazardous skips; no Telegram API,
node104 deployment, or physical RD6018 mutation was performed.

Authoritative machine-readable evidence:
`docs/UI_CALLBACK_ACCEPTANCE_MATRIX_20261010.json`.

Validation: focused callback acceptance `5 PASS`; full unittest discovery
`1610 PASS / 3 skipped`; `compileall -q .` and `git diff --check` PASS.
