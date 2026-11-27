"""AI-only stage and hold projections over the existing charge read model."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from runtime.charge.diagnostics import (
    AGM_FIRST_STAGE_HOLD_SEC, AGM_MIX_MAX_HOURS, CA_MIX_MAX_HOURS,
    DESULF_CURRENT_STUCK, DESULF_CURRENT_STUCK_AGM, EFB_MIX_MAX_HOURS,
    FIRST_STAGE_HOLD_SEC, HIGH_V_FAST_TIMEOUT, HIGH_V_THRESHOLD,
    MAX_STAGE_CURRENT, MIX_DONE_TIMER, SAFE_WAIT_MAX_SEC, SAFE_WAIT_V_MARGIN,
    TEMP_COMP_REF_C, TEMP_CRITICAL, TEMP_PAUSE, TEMP_WARNING, WATCHDOG_TIMEOUT,
    bank_fault_risk_snapshot, format_seconds, get_timers, post_charge_relaxation_snapshot, stage_path,
)

def ai_hold_snapshot(host, now: float) -> Optional[Dict[str, Any]]:
    """РљРѕСЂРѕС‚РєРёР№ СЃРЅРёРјРѕРє СѓРґРµСЂР¶Р°РЅРёСЏ С‚РѕРєР°/С‚Р°Р№РјРµСЂР° РґР»СЏ AI."""
    if host.current_stage == host.STAGE_MAIN:
        if host.battery_type == host.PROFILE_AGM:
            threshold = DESULF_CURRENT_STUCK_AGM
            required_sec = AGM_FIRST_STAGE_HOLD_SEC
            hold_kind = "AGM low-current hold"
        elif host.battery_type in (host.PROFILE_CA, host.PROFILE_EFB):
            threshold = DESULF_CURRENT_STUCK
            required_sec = FIRST_STAGE_HOLD_SEC
            hold_kind = "low-current hold"
        else:
            return None

        if host._first_stage_hold_since is None or host._first_stage_hold_current is None:
            return {
                "active": False,
                "kind": hold_kind,
                "threshold_a": threshold,
                "required_sec": required_sec,
            }

        elapsed = max(0.0, now - host._first_stage_hold_since)
        remaining = max(0.0, required_sec - elapsed)
        return {
            "active": True,
            "kind": hold_kind,
            "threshold_a": threshold,
            "required_sec": required_sec,
            "elapsed_sec": elapsed,
            "remaining_sec": remaining,
            "elapsed_text": format_seconds(host, elapsed),
            "remaining_text": format_seconds(host, remaining),
            "current_a": host._first_stage_hold_current,
            "rule_met": elapsed >= required_sec,
            "needs_new_minimum": True,
        }

    if host.current_stage == host.STAGE_DESULFATION:
        elapsed = max(0.0, now - host.stage_start_time)
        remaining = max(0.0, desulfation_duration_seconds() - elapsed)
        return {
            "active": True,
            "kind": "desulf timer",
            "required_sec": desulfation_duration_seconds(),
            "elapsed_sec": elapsed,
            "remaining_sec": remaining,
            "elapsed_text": format_seconds(host, elapsed),
            "remaining_text": format_seconds(host, remaining),
            "rule_met": elapsed >= desulfation_duration_seconds(),
        }

    if host.current_stage == host.STAGE_MIX and host.finish_timer_start is not None:
        elapsed = max(0.0, now - host.finish_timer_start)
        remaining = max(0.0, MIX_DONE_TIMER - elapsed)
        return {
            "active": True,
            "kind": "mix delta timer",
            "required_sec": MIX_DONE_TIMER,
            "elapsed_sec": elapsed,
            "remaining_sec": remaining,
            "elapsed_text": format_seconds(host, elapsed),
            "remaining_text": format_seconds(host, remaining),
            "rule_met": elapsed >= MIX_DONE_TIMER,
        }

    if host.current_stage == host.STAGE_SAFE_WAIT:
        elapsed = max(0.0, now - host._safe_wait_start)
        remaining = max(0.0, SAFE_WAIT_MAX_SEC - elapsed)
        threshold = host._safe_wait_target_v - SAFE_WAIT_V_MARGIN
        return {
            "active": True,
            "kind": "safe wait",
            "required_sec": SAFE_WAIT_MAX_SEC,
            "elapsed_sec": elapsed,
            "remaining_sec": remaining,
            "elapsed_text": format_seconds(host, elapsed),
            "remaining_text": format_seconds(host, remaining),
            "threshold_v": threshold,
            "target_v": host._safe_wait_target_v,
            "rule_met": elapsed >= SAFE_WAIT_MAX_SEC,
        }

    return None

def ai_stage_snapshot(host, temp_c: Optional[float] = None) -> Dict[str, Any]:
    """РЎРѕР±СЂР°С‚СЊ РєРѕРјРїР°РєС‚РЅС‹Р№ СЃРЅРёРјРѕРє СЃС‚СЂР°С‚РµРіРёРё Рё СЃРѕСЃС‚РѕСЏРЅРёСЏ РґР»СЏ LLM."""
    now = time.time()
    target_v, target_i = host._get_target_v_i(temp_c)
    base_target_v, _ = host._get_profile_target_v_i(None)
    timers = get_timers(host, )
    hold = ai_hold_snapshot(host, now)
    mix_exit_policy = None
    temperature_compensation = temperature_compensation_snapshot(host, base_target_v, target_v, temp_c)
    bank_fault = bank_fault_risk_snapshot(host,
        now,
        host._last_voltage or host._stage_start_voltage or target_v,
        host._last_current or host._stage_start_current or target_i,
        host._last_temp_ext or (temp_c if temp_c is not None else 0.0),
        host._last_ah if host._last_ah > 0 else None,
    )
    if bank_fault and bank_fault.get("status") == "stable":
        bank_fault = None

    if host.current_stage == host.STAGE_PREP:
        prep_current = host._prep_target(temp_c)[1]
        summary = f"Soft Start 12.0V/{prep_current:.2f}A (0.01C), Р·Р°С‚РµРј Main."
        next_stage = host.STAGE_MAIN
        transition = "РџРµСЂРµС…РѕРґ РІ Main РїРѕ Р·Р°РІРµСЂС€РµРЅРёРё РїРѕРґРіРѕС‚РѕРІРєРё."
    elif host.current_stage == host.STAGE_MAIN:
        if host.battery_type == host.PROFILE_AGM:
            summary = "Main РїРѕ СЃС‚СѓРїРµРЅСЏРј 14.4 -> 14.6 -> 14.8 -> 15.0V."
            next_stage = host.STAGE_MIX
            transition = "РЎР»РµРґСѓСЋС‰Р°СЏ СЃС‚СѓРїРµРЅСЊ Рё РїРµСЂРµС…РѕРґ РІ Mix: С‚РѕРє РЅРёР¶Рµ 0.2A 2С‡ Р±РµР· РЅРѕРІРѕРіРѕ РјРёРЅРёРјСѓРјР°."
        elif host.battery_type in (host.PROFILE_CA, host.PROFILE_EFB):
            summary = f"Main {target_v:.1f}V РґР»СЏ РїСЂРѕС„РёР»СЏ; hold РїРѕ РЅРёР·РєРѕРјСѓ С‚РѕРєСѓ Рё РІРѕР·РјРѕР¶РЅР°СЏ Desulfation."
            next_stage = host.STAGE_MIX
            transition = "РџРµСЂРµС…РѕРґ РІ Mix: С‚РѕРє РЅРёР¶Рµ 0.3A 3С‡ Р±РµР· РЅРѕРІРѕРіРѕ РјРёРЅРёРјСѓРјР°; РїСЂРё CV-РїРѕР»РєРµ >=40 РјРёРЅ РІРѕР·РјРѕР¶РЅР° Desulfation."
        else:
            summary = "Main РїРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРј СѓСЃС‚Р°РІРєР°Рј Рё delta-РїСЂР°РІРёР»Сѓ."
            next_stage = host.STAGE_MIX
            transition = "РџРµСЂРµС…РѕРґ РїРѕ delta-С‚СЂРёРіРіРµСЂСѓ: 3 РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ СЃ РёРЅС‚РµСЂРІР°Р»РѕРј 1 РјРёРЅ РїРѕСЃР»Рµ РІРєР»СЋС‡РµРЅРёСЏ РјРѕРЅРёС‚РѕСЂРёРЅРіР°."
    elif host.current_stage == host.STAGE_DESULFATION:
        summary = "РЎРµСЂРІРёСЃРЅР°СЏ РґРµСЃСѓР»СЊС„Р°С‚Р°С†РёСЏ 16.3V / 2%Ah / 2С‡."
        next_stage = host.STAGE_SAFE_WAIT
        transition = "РџРѕСЃР»Рµ 2С‡ -> SAFE_WAIT, Р·Р°С‚РµРј РІРѕР·РІСЂР°С‚ РІ Main."
    elif host.current_stage == host.STAGE_MIX:
        if host.finish_timer_start is not None:
            summary = "Mix РїРѕСЃР»Рµ delta-С‚СЂРёРіРіРµСЂР°: С‚Р°Р№РјРµСЂ 2С‡ РґРѕ Done."
            next_stage = host.STAGE_SAFE_WAIT
            transition = "Delta СѓР¶Рµ РїРѕРґС‚РІРµСЂР¶РґРµРЅР°: РёРґС‘С‚ 2С‡ С‚Р°Р№РјРµСЂ РґРѕ Done, Р·Р°С‚РµРј SAFE_WAIT."
            mix_exit_policy = {
                "mode": "delta_confirmed_timer_running",
                "primary": "timer",
                "delta_triggered": True,
                "delta_source": "CC_or_CV",
                "fallback_limit_hours": None,
            }
        elif host.battery_type == host.PROFILE_EFB:
            summary = "Mix 16.5V / 0.03C: РЅРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ РїРѕ О”V/О”I, Р»РёРјРёС‚ 24С‡ - fallback."
            next_stage = host.STAGE_SAFE_WAIT
            transition = "РќРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ: РїРѕ О”V/О”I; РµСЃР»Рё delta РЅРµ СЃСЂР°Р±РѕС‚Р°РµС‚, РѕРіСЂР°РЅРёС‡РµРЅРёРµ 24С‡ РїРµСЂРµРІРѕРґРёС‚ РІ SAFE_WAIT."
            mix_exit_policy = {
                "mode": "delta_or_time_fallback",
                "primary": "delta",
                "delta_triggered": False,
                "delta_source": "CC_or_CV",
                "fallback_limit_hours": EFB_MIX_MAX_HOURS,
            }
        elif host.battery_type == host.PROFILE_CA:
            summary = "Mix 16.5V / 0.03C: РЅРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ РїРѕ О”V/О”I, Р»РёРјРёС‚ 20С‡ - fallback."
            next_stage = host.STAGE_SAFE_WAIT
            transition = "РќРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ: РїРѕ О”V/О”I; РµСЃР»Рё delta РЅРµ СЃСЂР°Р±РѕС‚Р°РµС‚, РѕРіСЂР°РЅРёС‡РµРЅРёРµ 20С‡ РїРµСЂРµРІРѕРґРёС‚ РІ SAFE_WAIT."
            mix_exit_policy = {
                "mode": "delta_or_time_fallback",
                "primary": "delta",
                "delta_triggered": False,
                "delta_source": "CC_or_CV",
                "fallback_limit_hours": CA_MIX_MAX_HOURS,
            }
        elif host.battery_type == host.PROFILE_AGM:
            summary = "Mix 16.3V / 0.03C: РЅРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ РїРѕ О”V/О”I, Р»РёРјРёС‚ 10С‡ - fallback."
            next_stage = host.STAGE_SAFE_WAIT
            transition = "РќРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ: РїРѕ О”V/О”I; РµСЃР»Рё delta РЅРµ СЃСЂР°Р±РѕС‚Р°РµС‚, РѕРіСЂР°РЅРёС‡РµРЅРёРµ 10С‡ РїРµСЂРµРІРѕРґРёС‚ РІ SAFE_WAIT."
            mix_exit_policy = {
                "mode": "delta_or_time_fallback",
                "primary": "delta",
                "delta_triggered": False,
                "delta_source": "CC_or_CV",
                "fallback_limit_hours": AGM_MIX_MAX_HOURS,
            }
        else:
            summary = "Mix РїРѕ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРј РїСЂР°РІРёР»Р°Рј: РЅРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ РїРѕ О”V/О”I, Р·Р°С‚РµРј С‚Р°Р№РјРµСЂ."
            next_stage = host.STAGE_SAFE_WAIT
            transition = "РќРѕСЂРјР°Р»СЊРЅС‹Р№ РІС‹С…РѕРґ РїРѕ delta-С‚СЂРёРіРіРµСЂСѓ; РµСЃР»Рё delta РЅРµ СЃСЂР°Р±РѕС‚Р°РµС‚, СЃСЂР°Р±РѕС‚Р°РµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёР№ Р»РёРјРёС‚ РІСЂРµРјРµРЅРё."
            mix_exit_policy = {
                "mode": "delta_or_time_fallback",
                "primary": "delta",
                "delta_triggered": False,
                "delta_source": "CUSTOM",
                "fallback_limit_hours": host._custom_time_limit_hours,
            }
    elif host.current_stage == host.STAGE_SAFE_WAIT:
        summary = "РЁС‚Р°С‚РЅРѕРµ Р±РµР·РѕРїР°СЃРЅРѕРµ РѕР¶РёРґР°РЅРёРµ РїР°РґРµРЅРёСЏ РЅР°РїСЂСЏР¶РµРЅРёСЏ РїСЂРё РІС‹РєР»СЋС‡РµРЅРЅРѕРј РІС‹С…РѕРґРµ."
        next_stage = host._safe_wait_next_stage or host.STAGE_MAIN
        transition = "РџРµСЂРµС…РѕРґ РїСЂРё РїР°РґРµРЅРёРё РґРѕ РїРѕСЂРѕРіР° РёР»Рё РїРѕ С‚Р°Р№РјР°СѓС‚Сѓ 2С‡."
    elif host.current_stage == host.STAGE_COOLING:
        summary = "РџР°СѓР·Р° РЅР° РѕС…Р»Р°Р¶РґРµРЅРёРµ РґРѕ Р±РµР·РѕРїР°СЃРЅРѕР№ С‚РµРјРїРµСЂР°С‚СѓСЂС‹."
        next_stage = host._cooling_from_stage or host.STAGE_MAIN
        transition = "Р’РѕР·РІСЂР°С‚ РїСЂРё T <= 35В°C."
    elif host.current_stage == host.STAGE_DONE:
        summary = "Р—Р°РІРµСЂС€РµРЅРёРµ/С…СЂР°РЅРµРЅРёРµ."
        next_stage = host.STAGE_IDLE
        transition = "РђРєС‚РёРІРЅС‹Р№ Р·Р°СЂСЏРґ Р·Р°РІРµСЂС€С‘РЅ."
    else:
        summary = "Idle."
        next_stage = host.STAGE_IDLE
        transition = "РђРєС‚РёРІРЅС‹Р№ Р·Р°СЂСЏРґ РЅРµ РёРґС‘С‚."

    safety = {
        "current_limit_a": MAX_STAGE_CURRENT,
        "temp_warning_c": TEMP_WARNING,
        "temp_pause_c": TEMP_PAUSE,
        "temp_critical_c": TEMP_CRITICAL,
        "safe_wait_margin_v": SAFE_WAIT_V_MARGIN,
        "safe_wait_max_sec": SAFE_WAIT_MAX_SEC,
        "watchdog_timeout_sec": WATCHDOG_TIMEOUT,
        "watchdog_high_v_sec": HIGH_V_FAST_TIMEOUT,
        "watchdog_high_v_threshold": HIGH_V_THRESHOLD,
    }

    return {
        "profile": host.battery_type,
        "stage": host.current_stage,
        "previous_stage": host.previous_stage,
        "stage_path": stage_path(host, ),
        "last_transition_reason": host._last_transition_reason or transition,
        "is_active": host.is_active,
        "target_voltage": target_v,
        "target_current": target_i,
        "target_voltage_base": base_target_v,
        "temperature_compensation": temperature_compensation,
        "timers": timers,
        "summary": summary,
        "transition": transition,
        "next_stage": next_stage,
        "hold": hold,
        "safety": safety,
        "agm_stage_idx": host._agm_stage_idx,
        "desulf_attempts": host.antisulfate_count,
        "finish_timer_active": host.finish_timer_start is not None,
        "mix_exit_policy": mix_exit_policy,
        "session_reason": host._session_start_reason,
        "post_charge_relaxation": post_charge_relaxation_snapshot(host, now),
        "bank_fault_risk": bank_fault,
    }

def temperature_compensation_snapshot(host, base_v: float, final_v: float, temp_c: Optional[float]) -> Dict[str, Any]:
    """РљРѕРјРїР°РєС‚РЅРѕРµ РѕРїРёСЃР°РЅРёРµ С‚РµРјРїРµСЂР°С‚СѓСЂРЅРѕР№ РїРѕРїСЂР°РІРєРё РґР»СЏ AI/UI."""
    coeff = host._temperature_compensation_coeff()
    try:
        temp = float(temp_c) if temp_c is not None else None
    except (TypeError, ValueError):
        temp = None
    raw_delta = 0.0 if temp is None else coeff * (TEMP_COMP_REF_C - temp)
    applied_delta = final_v - base_v
    restored = bool(host._restored_target_v > 0 and host._restored_target_i > 0)
    enabled = temp is not None and host.current_stage in (
        host.STAGE_PREP,
        host.STAGE_MAIN,
        host.STAGE_DESULFATION,
        host.STAGE_MIX,
    ) and not restored
    return {
        "enabled": enabled,
        "restored": restored,
        "ref_c": TEMP_COMP_REF_C,
        "temp_c": temp,
        "coeff_v_per_c": coeff,
        "base_v": base_v,
        "final_v": final_v,
        "raw_delta_v": round(raw_delta, 3),
        "delta_v": round(applied_delta, 3),
        "clamped": abs(raw_delta - applied_delta) > 1e-9,
        "applied_stage": host.current_stage,
    }





def get_ai_stage_snapshot(host: Any, temp_c: Optional[float] = None) -> Dict[str, Any]:
    snapshot = ai_stage_snapshot(host, temp_c)
    return auto_ai_stage_snapshot(host, snapshot, temp_c)


def auto_ai_stage_snapshot(host: Any, snapshot: Dict[str, Any], temp_c: Optional[float] = None) -> Dict[str, Any]:
    from application.production_session_extensions import auto_mix_elapsed_s

    if not hasattr(host, "_v2_cooling_pause"):
        return snapshot
    if host.current_stage == host.STAGE_MIX and host.finish_timer_start is None:
        snapshot["mix_active_elapsed_s"] = auto_mix_elapsed_s(host, time.time())
        snapshot["mix_timeout_semantics"] = "MIX_TIMEOUT -> Output OFF -> manual diagnosis"
        if host.battery_type == host.PROFILE_EFB:
            snapshot["summary"] = "Mix 16.5V / 0.03C: normal exit by ΔV/ΔI; 24h active-time authority ceiling."
            snapshot["transition"] = ("Normal exit by ΔV/ΔI; without delta, 24h active-time ceiling -> "
                                      "MIX_TIMEOUT, Output OFF, manual diagnosis.")
            policy = snapshot.get("mix_exit_policy")
            if isinstance(policy, dict):
                policy["fallback_limit_hours"] = 24.0
                policy["fallback_outcome"] = "MIX_TIMEOUT"
    return snapshot
