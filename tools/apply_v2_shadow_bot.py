#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "bot.py"
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    text = text.replace(old, new, 1)


replace_once(
    "from charging_log import clear_event_logs, get_recent_events, log_checkpoint, log_event, log_stage_end, rotate_if_needed, trim_log_older_than_days\n",
    "from charging_log import clear_event_logs, get_recent_events, log_checkpoint, log_event, log_stage_end, rotate_if_needed, trim_log_older_than_days\nfrom charge_controller_v2 import ChargeControllerV2\n",
    "ChargeControllerV2 import",
)

replace_once(
    "charge_controller = ChargeController(hass, notify_cb=_charge_notify)\n",
    "charge_controller = ChargeControllerV2(hass, notify_cb=_charge_notify)\n",
    "controller construction",
)

path.write_text(text, encoding="utf-8")
print("Applied guarded ChargeControllerV2 shadow migration")
