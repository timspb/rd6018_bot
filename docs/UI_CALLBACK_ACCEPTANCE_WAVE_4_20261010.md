# UI callback acceptance Wave 4

This evidence is for the offline acceptance run at the checked-out commit recorded in
`UI_CALLBACK_ACCEPTANCE_MATRIX_20261010.json`. It uses the installed production router
and invokes handlers with fake aiogram-shaped callbacks; filter matches alone are not
counted as coverage.

## Result

- Installed handlers: 85
- Actually dispatched handlers: 46
- Uncovered handlers: 39
- Hazardous routes excluded: 34
- Static matched handlers: 68
- Full scope remains offline: no Telegram API, node 104, START acceptance, lease
  mutation, Output ON, or physical connector command.

Wave 4 resolves the `v2_manual` ownership ambiguity. `manual_context` now owns only
`v2_manual_choose`; the historical `v2_manual` callback remains owned by
`manual_text`, preserving old Telegram keyboards without overlapping router filters.
Both routes are dispatched through the installed router, ACK within the two-second
bound, and are guarded against physical output calls.

The wave also dispatches safe SG access choices and Auto Mix menu/profile/battery
preview routes with fake registry state. Mix execution, ownership transfer/adoption,
Output OFF/ON, and other hazardous endpoints remain mock/preflight-only.

The machine-readable matrix is regenerated from actual invocation records by
`tools/ui_callback_acceptance.py --write`.
