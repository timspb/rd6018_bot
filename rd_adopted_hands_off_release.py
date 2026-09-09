from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from typing import Any, Optional

from runtime_safety import RuntimeSafetyError


_RELEASE_VERSION = 1
_RELEASE_FILE = "rd_adopted_hands_off_release_v2.json"


def _atomic_write(path: str, document: dict[str, Any]) -> None:
    absolute = os.path.abspath(path)
    directory = os.path.dirname(absolute) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".rd-adopted-release-",
        suffix=".tmp",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, absolute)
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass


def _read_intent(path: str) -> Optional[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or int(raw.get("version") or 0) != _RELEASE_VERSION:
        return None
    session_id = str(raw.get("session_id") or "").strip()
    if not session_id:
        return None
    return raw


def _clear_intent(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError:
        return


def _persist_intent(path: str, coordinator: Any) -> None:
    session_id = str(getattr(coordinator, "session_id", "") or "").strip()
    if not session_id:
        raise RuntimeSafetyError(
            "D061 HANDS_OFF release blocked: adopted-live session identity is missing"
        )
    try:
        _atomic_write(
            path,
            {
                "version": _RELEASE_VERSION,
                "session_id": session_id,
                "phase": "release_requested",
                "saved_at_s": time.time(),
            },
        )
    except OSError as exc:
        raise RuntimeSafetyError(
            f"D061 HANDS_OFF release blocked: durable release intent failed: {exc}"
        ) from exc


def _retire_adopted_authority(coordinator: Any, *, reason: str) -> None:
    state = getattr(coordinator, "state", None)
    state_type = type(state)
    interrupted = getattr(state_type, "INTERRUPTED", None)
    if interrupted is None:
        raise RuntimeSafetyError(
            "D061 HANDS_OFF release blocked: adoption state has no INTERRUPTED terminal"
        )

    task = getattr(coordinator, "_task", None)
    coordinator._task = None
    coordinator.state = interrupted
    coordinator.last_status = str(reason)
    persist = getattr(coordinator, "_persist", None)
    if not callable(persist):
        raise RuntimeSafetyError(
            "D061 HANDS_OFF release blocked: adoption journal is not persistable"
        )
    persist()

    if task is not None and not task.done():
        task.cancel()


def _intent_matches(path: str, coordinator: Any) -> bool:
    raw = _read_intent(path)
    if raw is None:
        return False
    return str(raw.get("session_id") or "") == str(
        getattr(coordinator, "session_id", "") or ""
    )


def install_adopted_hands_off_release_retirement(
    app: Any,
    manager: Any,
    *,
    intent_file: str = _RELEASE_FILE,
) -> None:
    """Retire D061 restart-OFF authority after an intentional D060 release.

    D061 ACTIVE normally becomes OFF_PENDING after a process restart, which is correct
    for a crash while bot-managed ownership still exists or edge adoption is uncertain.
    A deliberate active Manual -> HANDS_OFF transfer is different: once durable software
    HANDS_OFF commits, that same D061 journal must no longer survive as authority to turn
    the externally-owned PSU off on the next poll/restart.

    A small durable release-intent record bridges the two journals. If a crash happens
    before HANDS_OFF commits, PB_MANAGED remains authoritative and ordinary D061 restart
    OFF containment wins. If HANDS_OFF is durable and the marker matches the exact D061
    session, install-time reconciliation retires the stale adoption journal without
    touching Output. This avoids treating generic HANDS_OFF itself as proof of release.
    """
    coordinator = getattr(app, "rd_managed_live_adoption", None)
    if coordinator is None:
        raise RuntimeError("D061 HANDS_OFF release retirement requires managed adoption")
    if bool(getattr(manager, "_d061_hands_off_release_retirement_installed", False)):
        return

    path = str(intent_file)

    # Reconcile a crash between the two durable writes before D065 startup recovery is
    # installed. HANDS_OFF + a matching exact-session marker proves an intentional D060
    # release transaction. PB_MANAGED never consumes the marker as release authority.
    if _intent_matches(path, coordinator):
        if bool(getattr(manager, "hands_off", False)):
            _retire_adopted_authority(
                coordinator,
                reason=(
                    "intentional HANDS_OFF release recovered after restart; "
                    "D061 authority retired without Output change"
                ),
            )
            _clear_intent(path)
        elif bool(getattr(manager, "pb_managed", False)):
            _clear_intent(path)

    original_verified_off = coordinator._verified_off

    async def release_aware_verified_off(reason: str) -> bool:
        # Once the D060 durable commit is visible, an exact-session release marker means
        # D061 no longer owns Output. Before that commit this exemption is inactive, so
        # any pre-existing managed safety containment still wins.
        if (
            bool(getattr(manager, "hands_off", False))
            and bool(getattr(manager, "release_in_progress", False))
            and _intent_matches(path, coordinator)
            and bool(getattr(coordinator, "active", False))
        ):
            coordinator.last_status = (
                "intentional HANDS_OFF release committed; D061 OFF claim suppressed "
                "until journal retirement"
            )
            coordinator._persist()
            return False
        return bool(await original_verified_off(reason))

    coordinator._verified_off = release_aware_verified_off

    original_enter_hands_off = manager.enter_hands_off

    async def enter_hands_off() -> bool:
        if bool(getattr(coordinator, "off_pending", False)):
            raise RuntimeSafetyError(
                "RD HANDS_OFF blocked: D061 verified Output OFF containment is already pending"
            )

        releasing_d061 = bool(getattr(coordinator, "active", False))
        if not releasing_d061:
            return bool(await original_enter_hands_off())

        _persist_intent(path, coordinator)
        try:
            result = bool(await original_enter_hands_off())
        except Exception:
            if bool(getattr(manager, "hands_off", False)) and _intent_matches(path, coordinator):
                _retire_adopted_authority(
                    coordinator,
                    reason=(
                        "intentional HANDS_OFF release committed with transfer warning; "
                        "D061 authority retired without Output change"
                    ),
                )
                _clear_intent(path)
            else:
                _clear_intent(path)
            raise

        if bool(getattr(manager, "hands_off", False)) and _intent_matches(path, coordinator):
            _retire_adopted_authority(
                coordinator,
                reason=(
                    "intentional HANDS_OFF release completed; "
                    "D061 authority retired without Output change"
                ),
            )
            _clear_intent(path)
        return result

    manager.enter_hands_off = enter_hands_off
    manager._d061_hands_off_release_retirement_installed = True
