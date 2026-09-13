from __future__ import annotations

import unittest
from types import SimpleNamespace

from application.operator_snapshot import snapshot_from_mapping
from presentation.panel_renderer import render_panel
from telegram.adapter import OperatorPanelAdapter


def make_snapshot(state: str, **extra):
    data = {
        "state": state,
        "battery": {"label": "AGM100"},
        "telemetry": {"voltage": 14.42, "current": 2.31},
        "safety": {"allowed": True},
        "output": {"enabled": state == "CHARGING"},
        "charge": {"stage": "MIX CV", "timer_text": "01:42"},
    }
    data.update(extra)
    return snapshot_from_mapping(data)


class OperatorPanelPr1Tests(unittest.TestCase):
    def test_charging_is_compact_and_has_no_power_toggle(self):
        rendered = render_panel(make_snapshot("CHARGING"))
        self.assertIn("MIX CV", rendered.text)
        self.assertNotIn("POWER", rendered.text.upper())
        self.assertEqual([a.label for a in rendered.layout.actions], ["STOP", "LOG", "GRAPH"])

    def test_idle_has_start_but_fault_does_not(self):
        idle = render_panel(make_snapshot("IDLE"))
        fault = render_panel(make_snapshot("FAULT", faults=("OCP",), output={"enabled": False}))
        self.assertIn("START", [a.label for a in idle.layout.actions])
        self.assertNotIn("START", [a.label for a in fault.layout.actions])

    def test_stale_idle_is_fail_closed_for_actions(self):
        rendered = render_panel(make_snapshot("IDLE", telemetry_fresh=False))
        self.assertNotIn("START", [a.label for a in rendered.layout.actions])

    def test_snapshot_is_data_only(self):
        value = make_snapshot("IDLE")
        self.assertFalse(hasattr(value, "hass"))
        self.assertFalse(hasattr(value, "controller"))


class _Transport:
    def __init__(self):
        self.edits = []
        self.sends = []

    async def edit(self, chat_id, message_id, text, actions):
        self.edits.append((chat_id, message_id, text, actions))

    async def send(self, chat_id, text, actions):
        self.sends.append((chat_id, text, actions))
        return SimpleNamespace(message_id=42)


class PanelRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_reuses_authoritative_message(self):
        source = lambda: make_snapshot("IDLE")
        async def get_operator_snapshot():
            return source()
        interface = type("Interface", (), {"get_operator_snapshot": staticmethod(get_operator_snapshot)})()
        transport = _Transport()
        panel = OperatorPanelAdapter(interface, transport)
        first = await panel.refresh(7)
        second = await panel.refresh(7)
        self.assertEqual(first, second)
        self.assertEqual(len(transport.sends), 1)
        self.assertEqual(len(transport.edits), 1)


if __name__ == "__main__":
    unittest.main()
