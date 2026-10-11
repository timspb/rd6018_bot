# UI callback acceptance Wave 3

This evidence is for the offline acceptance run at the checked-out commit recorded in
`UI_CALLBACK_ACCEPTANCE_MATRIX_20261010.json`. It uses the installed production router
and invokes handlers with fake aiogram-shaped callbacks; filter matches alone are not
counted as coverage.

## Result

- Installed handlers: 85
- Actually dispatched handlers: 40
- Uncovered handlers: 45
- Hazardous routes excluded: 34
- Static matched handlers: 68
- Full scope remains offline: no Telegram API, node 104, START acceptance, lease
  mutation, Output ON, or physical connector command.

Wave 3 adds real invocation evidence for canonical journal, OFF-condition, entity,
analysis, custom-cancel and home navigation screens, plus operator graph/range,
refresh, diagnostics/help, pause, and SG menu/pick flows. Each scenario requires an
installed handler, a bounded callback completion, and a callback acknowledgement or
message response. The fake `safe_enable_output` guard raises if a callback attempts an
output operation; START scenarios remain explicitly rejected by the fake preflight.

## Harness safety

Callback execution is bounded to 2 seconds. Any tasks left by a fake callback are
cancelled and gathered with a second bounded 2-second cleanup wait before the offline
session ends. This prevents interface async mocks or best-effort background work from
turning acceptance into an unbounded process.

## Classification

The 34 excluded routes remain hazardous output/lease/ownership transactions: START,
STOP/managed stop, Output OFF, HANDS_OFF transfer, live/managed adoption, autonomous
execute, and managed Mix execution paths. They are not made green by synthetic success;
their existing fake safety-preflight tests remain the applicable software evidence.

The remaining uncovered rows are stateful or legacy routes not required for this
read-only wave. In particular, `v2_manual` is blocked from invocation because the
installed router has two matching handlers (`manual_text` and `manual_context`). The
route is therefore ambiguous at the actual dispatch boundary; selecting one handler
would be false coverage. No further dependency patch attempts are made for that
specific screen in Wave 3.

The machine-readable matrix is the acceptance inventory and is regenerated from the
actual invocation records by `tools/ui_callback_acceptance.py --write`.
