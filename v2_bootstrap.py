from __future__ import annotations

import time
from typing import Any

import v2_bot_ui
from battery_registry import init_battery_registry, upsert_battery as registry_upsert_battery
from production_controller import ProductionChargeControllerV2
from v2_startup import start_profile_transactional


def install_v2(app: Any) -> None:
    """Install production V2 controller + Telegram presentation over bot_legacy."""
    if not isinstance(app.charge_controller, ProductionChargeControllerV2):
        app.charge_controller = ProductionChargeControllerV2(
            app.hass,
            notify_cb=app._charge_notify,
        )

    async def _upsert_from_ui(identity, lifecycle) -> None:
        await init_battery_registry()
        await registry_upsert_battery(
            identity,
            lifecycle,
            updated_at=time.time(),
        )

    # v2_bot_ui callback bodies resolve these module globals at execution time. Keep
    # the large Telegram adapter stable and inject the production-safe boundaries here.
    v2_bot_ui.upsert_battery = _upsert_from_ui
    v2_bot_ui._start_profile = start_profile_transactional
    v2_bot_ui.install_v2_ui(app)


async def init_v2_storage() -> None:
    """Create/migrate the physical battery and recovery-history tables at startup."""
    await init_battery_registry()
