# RD6018 Telegram Operator Adapter — WORKSTREAM 34

## Status

`TELEGRAM_OPERATOR_VIEW_READY`.

`TelegramOperatorViewAdapter` accepts only one `OperatorDashboardState` and
returns formatted operator text. It does not import Telegram clients or
handlers and cannot read HA, ESPHome, history or runtime directly.

## Displayed information

The message presents current profile/state/phase, V/A/W, temperature, source,
confidence, current-session timeline, decision explanation, phase conditions,
protection/lease observations, stale indicators, warnings, blockers,
historical faults, parity and Canary status.

Missing values are shown as `UNKNOWN`; historical faults are labelled
separately. The control boundary is explicitly shown as unavailable.

No command, START/STOP, lease or physical path exists in this adapter.
