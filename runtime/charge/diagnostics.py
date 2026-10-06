"""Read-only charge diagnostics and compatibility snapshots.

No actuator write or charge-transition authority lives here.  The functions
consume compatibility-shaped controller state while timing/safety limits come
from canonical V3 owners.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from runtime.charge.strategy.desulfation_variables import desulfation_duration_seconds
from runtime.charge.strategy.main_variables import (
    agm_tail_hold_seconds,
    main_fallback_seconds,
    standard_tail_hold_seconds,
)
from runtime.charge.strategy.mix_variables import (
    mix_finish_hold_seconds,
    mix_max_active_hours,
)
from runtime.charge.strategy.safe_wait_variables import (
    SAFE_WAIT_TARGET_MARGIN_V,
    safe_wait_max_seconds,
)
from runtime.charge.strategy.temperature_variables import TEMPERATURE_REFERENCE_C
from runtime.safety.thermal_variables import (
    BATTERY_TEMP_CRITICAL_C,
    BATTERY_TEMP_PAUSE_C,
    BATTERY_TEMP_WARNING_C,
)
from runtime.safety.variables import (
    HIGH_V_FAST_TIMEOUT_S,
    HIGH_V_THRESHOLD_V,
    MAX_STAGE_CURRENT_A,
    PROTECTION_OCP_MARGIN_A,
    PROTECTION_OVP_MARGIN_V,
    WATCHDOG_TIMEOUT_S,
)

POST_CHARGE_MAX_WINDOW_SEC = 60 * 60
POST_CHARGE_PERIODIC_WINDOWS_SEC = (5 * 60, 10 * 60, 15 * 60)
POST_CHARGE_IDLE_CURRENT_A = 0.05

BANK_FAULT_WATCH_SCORE = 30
BANK_FAULT_PROBABLE_SCORE = 50
BANK_FAULT_HIGH_SCORE = 70
BANK_FAULT_LOW_START_V = 10.8
BANK_FAULT_PREP_SLOW_12V_1 = 30 * 60
BANK_FAULT_PREP_SLOW_12V_2 = 60 * 60
BANK_FAULT_PREP_SLOW_12V_3 = 120 * 60
BANK_FAULT_PREP_V_FLOOR = 11.8
BANK_FAULT_RECENT_WINDOW_SEC = 20 * 60
BANK_FAULT_SAFE_WAIT_WATCH_SCORE = 20
BANK_FAULT_SAFE_WAIT_RISK_SCORE = 35

# Accepted production authorities, exposed under compatibility-shaped names only.
SAFE_WAIT_V_MARGIN = float(SAFE_WAIT_TARGET_MARGIN_V.default)
SAFE_WAIT_MAX_SEC = safe_wait_max_seconds()
MIX_DONE_TIMER = mix_finish_hold_seconds()
MAIN_STAGE_MAX_HOURS = main_fallback_seconds() / 3600.0
CA_MIX_MAX_HOURS = float(mix_max_active_hours("Ca/Ca") or 0.0)
EFB_MIX_MAX_HOURS = float(mix_max_active_hours("EFB") or 0.0)
AGM_MIX_MAX_HOURS = float(mix_max_active_hours("AGM") or 0.0)
MAX_STAGE_CURRENT = float(MAX_STAGE_CURRENT_A.default)
OVP_OFFSET = float(PROTECTION_OVP_MARGIN_V.default)
OCP_OFFSET = float(PROTECTION_OCP_MARGIN_A.default)
TEMP_WARNING = float(BATTERY_TEMP_WARNING_C.default)
TEMP_PAUSE = float(BATTERY_TEMP_PAUSE_C.default)
TEMP_CRITICAL = float(BATTERY_TEMP_CRITICAL_C.default)
WATCHDOG_TIMEOUT = float(WATCHDOG_TIMEOUT_S.default)
HIGH_V_FAST_TIMEOUT = float(HIGH_V_FAST_TIMEOUT_S.default)
HIGH_V_THRESHOLD = float(HIGH_V_THRESHOLD_V.default)
TEMP_COMP_REF_C = float(TEMPERATURE_REFERENCE_C.default)
FIRST_STAGE_HOLD_SEC = standard_tail_hold_seconds()
AGM_FIRST_STAGE_HOLD_SEC = agm_tail_hold_seconds()
DESULF_CURRENT_STUCK = 0.3
DESULF_CURRENT_STUCK_AGM = 0.2

def bank_fault_expected_main_hours(host, start_v: float, temp_c: float) -> float:
    """РћС†РµРЅРєР° РѕР¶РёРґР°РµРјРѕР№ РґР»РёС‚РµР»СЊРЅРѕСЃС‚Рё Main СЃ РїРѕРїСЂР°РІРєРѕР№ РЅР° СЃС‚Р°СЂС‚РѕРІРѕРµ РЅР°РїСЂСЏР¶РµРЅРёРµ Рё С‚РµРјРїРµСЂР°С‚СѓСЂСѓ."""
    expected = 10.0
    if start_v <= 10.4:
        expected += 4.0
    elif start_v <= 10.8:
        expected += 3.0
    elif start_v <= 11.2:
        expected += 1.5
    elif start_v <= 11.8:
        expected += 0.75

    if temp_c <= 15.0:
        expected += 1.0
    elif temp_c <= 20.0:
        expected += 0.5
    elif temp_c >= 30.0:
        expected -= 0.5
    return max(10.0, expected)

def bank_fault_risk_snapshot(
    host,
    now: float,
    voltage: float,
    current: float,
    temp: float,
    ah: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """РЎРѕР±С‹С‚РёР№РЅР°СЏ РѕС†РµРЅРєР° СЂРёСЃРєР° РєРѕСЂРѕС‚РЅСѓРІС€РµР№/СЃРёР»СЊРЅРѕ РґРµРіСЂР°РґРёСЂРѕРІР°РІС€РµР№ Р±Р°РЅРєРё."""
    if host.current_stage in (host.STAGE_IDLE, host.STAGE_DONE):
        return None

    score = 0
    reasons: List[str] = []
    stage = host.current_stage
    stage_elapsed = max(0.0, now - host.stage_start_time)
    stage_hours = stage_elapsed / 3600.0
    start_v = host._stage_start_voltage or voltage
    start_t = host._stage_start_temp or temp
    stage_ah = None
    if ah is not None and host._stage_start_ah > 0:
        stage_ah = max(0.0, ah - host._stage_start_ah)

    recent = [(t, v, i, a, te) for t, v, i, a, te in host._analytics_history if now - t <= BANK_FAULT_RECENT_WINDOW_SEC]
    temp_span = 0.0
    v_delta = 0.0
    current_avg = current
    if len(recent) >= 4:
        t0, v0, _, _, te0 = recent[0]
        t1, v1, _, _, te1 = recent[-1]
        _ = (t0, t1)  # keep the shape obvious for reviewers
        v_delta = v1 - v0
        temp_span = max(te for _, _, _, _, te in recent) - min(te for _, _, _, _, te in recent)
        current_avg = sum(i for _, _, i, _, _ in recent) / len(recent)

    if stage == host.STAGE_PREP:
        if start_v <= BANK_FAULT_LOW_START_V:
            score += 30
            reasons.append(f"prep_start_low={start_v:.2f}V")
        elif start_v <= 11.2:
            score += 15
            reasons.append(f"prep_start_low={start_v:.2f}V")

        if stage_elapsed >= BANK_FAULT_PREP_SLOW_12V_1 and voltage < BANK_FAULT_PREP_V_FLOOR:
            score += 10
            reasons.append(f"prep_slow_to_12V>{BANK_FAULT_PREP_SLOW_12V_1 // 60}m")
        if stage_elapsed >= BANK_FAULT_PREP_SLOW_12V_2 and voltage < BANK_FAULT_PREP_V_FLOOR:
            score += 15
            reasons.append(f"prep_slow_to_12V>{BANK_FAULT_PREP_SLOW_12V_2 // 60}m")
        if stage_elapsed >= BANK_FAULT_PREP_SLOW_12V_3 and voltage < 12.0:
            score += 20
            reasons.append(f"prep_still_below_12V>{BANK_FAULT_PREP_SLOW_12V_3 // 60}m")

    if stage == host.STAGE_MAIN:
        expected_main_hours = bank_fault_expected_main_hours(host, start_v, start_t)
        if stage_hours >= expected_main_hours * 2.5:
            score += 35
            reasons.append(f"main_duration>{expected_main_hours * 2.5:.1f}h")
        elif stage_hours >= expected_main_hours * 1.8:
            score += 25
            reasons.append(f"main_duration>{expected_main_hours * 1.8:.1f}h")
        elif stage_hours >= expected_main_hours * 1.4:
            score += 15
            reasons.append(f"main_duration>{expected_main_hours * 1.4:.1f}h")

        if stage_hours >= 2.0 and voltage - start_v < 0.8:
            score += 10
            reasons.append("main_slow_v_rise<0.8V")
        if stage_hours >= 4.0 and voltage - start_v < 1.2:
            score += 10
            reasons.append("main_slow_v_rise<1.2V")

        if stage_ah is not None and stage_hours >= 6.0:
            expected_ah = host.ah_capacity * stage_hours * 0.05
            if stage_ah < expected_ah * 0.75:
                score += 10
                reasons.append("main_low_ah_acceptance")

        if temp_span >= 1.0 and (voltage - start_v) < 1.0:
            score += 15
            reasons.append(f"main_temp_rise={temp_span:.1f}C")
        elif temp_span >= 0.7 and (voltage - start_v) < 0.7:
            score += 10
            reasons.append(f"main_temp_rise={temp_span:.1f}C")

    if stage == host.STAGE_SAFE_WAIT:
        relaxation = post_charge_relaxation_snapshot(host, now)
        if relaxation:
            status = str(relaxation.get("status") or "stable").lower()
            if status == "watch":
                score += BANK_FAULT_SAFE_WAIT_WATCH_SCORE
                reasons.append("safe_wait_decay_watch")
            elif status == "risk":
                score += BANK_FAULT_SAFE_WAIT_RISK_SCORE
                reasons.append("safe_wait_decay_risk")
            elif status == "high":
                score += BANK_FAULT_SAFE_WAIT_RISK_SCORE + 10
                reasons.append("safe_wait_decay_high")

            decay_mv_min = float(relaxation.get("decay_mv_min") or 0.0)
            temp_span_c = float(relaxation.get("temp_span_c") or 0.0)
            current_avg_a = float(relaxation.get("current_avg_a") or 0.0)
            if decay_mv_min >= 8.0:
                score += 15
                reasons.append(f"safe_wait_decay={decay_mv_min:.1f}mV/min")
            if temp_span_c >= 1.0 and current_avg_a <= POST_CHARGE_IDLE_CURRENT_A:
                score += 10
                reasons.append(f"safe_wait_temp_rise={temp_span_c:.1f}C")

        health = self_discharge_warning(host, )
        if health:
            score += 20
            reasons.append("self_discharge_warning")

    if stage in (host.STAGE_MAIN, host.STAGE_PREP) and len(recent) >= 4:
        if temp_span >= 1.0 and v_delta < 0.8:
            score += 10
            reasons.append(f"temp_rise={temp_span:.1f}C")
        if temp_span >= 1.5 and v_delta < 0.5:
            score += 10
            reasons.append(f"temp_rise={temp_span:.1f}C")

    if stage == host.STAGE_MAIN and current_avg <= 0.15:
        if score >= BANK_FAULT_PROBABLE_SCORE:
            score = BANK_FAULT_WATCH_SCORE + 10
        reasons.append(f"main_low_current_tail={current_avg:.2f}A")

    if not reasons:
        return {
            "active": False,
            "status": "stable",
            "score": 0,
            "reasons": [],
            "stage": stage,
            "profile": host.battery_type,
        }

    if score >= BANK_FAULT_HIGH_SCORE:
        status = "high"
    elif score >= BANK_FAULT_PROBABLE_SCORE:
        status = "probable"
    elif score >= BANK_FAULT_WATCH_SCORE:
        status = "watch"
    else:
        status = "stable"

    return {
        "active": status != "stable",
        "status": status,
        "score": score,
        "reasons": reasons[:6],
        "stage": stage,
        "profile": host.battery_type,
        "elapsed_sec": stage_elapsed,
        "elapsed_text": format_seconds(host, stage_elapsed),
        "start_voltage": start_v,
        "current_voltage": voltage,
        "start_temp_c": start_t,
        "current_temp_c": temp,
        "stage_ah": stage_ah,
        "recent_samples": len(recent),
    }

def stage_path(host) -> List[str]:
    """РљРѕСЂРѕС‚РєРёР№ РїСѓС‚СЊ СЌС‚Р°РїРѕРІ РґР»СЏ AI: Prep -> Main -> Mix ..."""
    path: List[str] = []
    for entry in host._stage_history:
        from_stage = str(entry.get("from") or "").strip()
        to_stage = str(entry.get("to") or "").strip()
        if from_stage and not path and from_stage != host.STAGE_IDLE:
            path.append(from_stage)
        if to_stage and to_stage != host.STAGE_IDLE and (not path or path[-1] != to_stage):
            path.append(to_stage)
    if not path and host.current_stage:
        path.append(host.current_stage)
    if len(path) > 6:
        path = path[-6:]
    return path

def self_discharge_warning(host) -> Optional[str]:
    """РџСЂРѕРІРµСЂРєР° СЃРєРѕСЂРѕСЃС‚Рё РїР°РґРµРЅРёСЏ V РІРѕ РІСЂРµРјСЏ SAFE_WAIT РїСЂРё V < 13.5Р’."""
    if host.current_stage != host.STAGE_SAFE_WAIT or len(host._safe_wait_v_samples) < 2:
        return None
    samples = list(host._safe_wait_v_samples)
    (t0, v0, _, _), (t1, v1, _, _) = samples[0], samples[-1]
    if t1 <= t0 or v0 >= 13.5 and v1 >= 13.5:
        return None
    dt_hours = (t1 - t0) / 3600.0
    if dt_hours < 0.01:
        return None
    dV_dt = abs(v1 - v0) / dt_hours  # Р’/С‡Р°СЃ
    avg_v = (v0 + v1) / 2
    if dV_dt > 0.5 and avg_v < 13.5:
        return "вљ пёЏ Р’С‹СЃРѕРєР°СЏ СЃРєРѕСЂРѕСЃС‚СЊ РїР°РґРµРЅРёСЏ РЅР°РїСЂСЏР¶РµРЅРёСЏ: РІРѕР·РјРѕР¶РЅРѕ РљР— РІ Р±Р°РЅРєРµ РёР»Рё СЃРёР»СЊРЅС‹Р№ СЃР°РјРѕСЂР°Р·СЂСЏРґ."
    return None

def evaluate_post_charge_window(
    host,
    samples: List[Tuple[float, float, float, float]],
    params: Dict[str, Any],
    window_sec: int,
) -> Dict[str, Any]:
    """РћС†РµРЅРёС‚СЊ РѕРґРЅРѕ РѕРєРЅРѕ РїРѕСЃС‚Р·Р°СЂСЏРґРЅРѕРіРѕ С‚СЂРµРЅРґР°."""
    label = f"{int(window_sec // 60)}m"
    min_samples = 2
    if len(samples) < min_samples:
        return {
            "window_sec": window_sec,
            "label": label,
            "status": "insufficient",
            "reason": "too_few_window_samples",
            "confidence": 0.0,
            "sample_count": len(samples),
        }

    t0, v0, i0, temp0 = samples[0]
    t1, v1, i1, temp1 = samples[-1]
    elapsed_sec = max(0.0, t1 - t0)
    if elapsed_sec <= 0:
        return {
            "window_sec": window_sec,
            "label": label,
            "status": "insufficient",
            "reason": "zero_window_span",
            "confidence": 0.0,
            "sample_count": len(samples),
        }

    xs = [s[0] - t0 for s in samples]
    ys = [s[1] for s in samples]
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    denom = len(samples) * sum_xx - sum_x * sum_x
    slope_v_per_sec = 0.0
    if abs(denom) > 1e-9:
        slope_v_per_sec = (len(samples) * sum_xy - sum_x * sum_y) / denom
    slope_mv_min = slope_v_per_sec * 60.0 * 1000.0
    decay_mv_min = max(0.0, -slope_mv_min)
    drop_v = v0 - v1
    temp_values = [s[3] for s in samples]
    temp_min = min(temp_values)
    temp_max = max(temp_values)
    temp_span = temp_max - temp_min
    current_max = max(abs(s[2]) for s in samples)
    current_avg = sum(abs(s[2]) for s in samples) / len(samples)

    confidence = 0.20 + float(params.get("confidence_bias", 0.0))
    if window_sec >= 10 * 60:
        confidence += 0.10
    if window_sec >= 15 * 60:
        confidence += 0.10
    if len(samples) >= 3:
        confidence += 0.15
    if len(samples) >= 4:
        confidence += 0.10
    if temp_span <= float(params["temp_stable_c"]):
        confidence += 0.20
    if current_max <= float(params["idle_current_a"]):
        confidence += 0.10
    confidence = max(0.0, min(1.0, confidence))

    if temp_span > float(params["temp_stable_c"]):
        status = "noisy"
        reason = "temp_drift"
    elif current_max > float(params["idle_current_a"]) * 1.8:
        status = "mixed"
        reason = "current_not_idle"
    elif decay_mv_min >= float(params["strong_slope_mv_min"]) or drop_v >= float(params["strong_drop_v"]):
        status = "watch"
        reason = "fast_decay"
    elif decay_mv_min >= float(params["watch_slope_mv_min"]) or drop_v >= float(params["watch_drop_v"]):
        status = "watch"
        reason = "moderate_decay"
    else:
        status = "stable"
        reason = "plateau"

    stratification_risk = "low"
    if status in ("mixed", "noisy"):
        stratification_risk = "unknown"
    elif status == "watch" and temp_span <= float(params["temp_stable_c"]) and current_max <= float(params["idle_current_a"]):
        stratification_risk = "medium"
    elif status == "stable" and drop_v <= 0.03:
        stratification_risk = "low"

    if status == "stable" and host.battery_type == host.PROFILE_AGM:
        stratification_risk = "very_low"
    if status == "watch" and host.battery_type == host.PROFILE_AGM and decay_mv_min < 7.0:
        stratification_risk = "low"
    if status == "watch" and host.battery_type in (host.PROFILE_CA, host.PROFILE_EFB):
        stratification_risk = "medium"
    if status == "watch" and float(params.get("risk_bias", 0.0)) < 0 and decay_mv_min < 7.5:
        stratification_risk = "low"

    return {
        "window_sec": window_sec,
        "label": label,
        "status": status,
        "reason": reason,
        "sample_count": len(samples),
        "window_span_sec": elapsed_sec,
        "drop_v": drop_v,
        "start_v": v0,
        "end_v": v1,
        "start_i": i0,
        "end_i": i1,
        "slope_mv_min": slope_mv_min,
        "decay_mv_min": decay_mv_min,
        "temp_start_c": temp0,
        "temp_end_c": temp1,
        "temp_min_c": temp_min,
        "temp_max_c": temp_max,
        "temp_span_c": temp_span,
        "current_max_a": current_max,
        "current_avg_a": current_avg,
        "profile": host.battery_type,
        "confidence": confidence,
        "stratification_risk": stratification_risk,
    }

def post_charge_relaxation_snapshot(host, now: float) -> Optional[Dict[str, Any]]:
    """
    РџРѕСЃС‚Р·Р°СЂСЏРґРЅР°СЏ СЌРІСЂРёСЃС‚РёРєР° РґР»СЏ РѕРєРЅР° SAFE_WAIT.
    Р­С‚Рѕ РЅРµ РґРѕРєР°Р·Р°С‚РµР»СЊСЃС‚РІРѕ СЃС‚СЂР°С‚РёС„РёРєР°С†РёРё, Р° С‚РѕР»СЊРєРѕ СЃРёРіРЅР°Р» РґР»СЏ РІРЅРёРјР°РЅРёСЏ.
    """
    if host.current_stage != host.STAGE_SAFE_WAIT:
        return None

    params = host._post_charge_profile_params()
    samples = list(host._safe_wait_v_samples)
    if len(samples) < params["min_samples"]:
        return {
            "active": True,
            "status": "insufficient",
            "reason": "too_few_samples",
            "confidence": 0.0,
            "window_sec": max(0.0, now - host._safe_wait_start),
            "sample_count": len(samples),
            "windows": [],
        }

    window_samples = [s for s in samples if now - s[0] <= POST_CHARGE_MAX_WINDOW_SEC]
    if len(window_samples) < params["min_samples"]:
        return {
            "active": True,
            "status": "insufficient",
            "reason": "too_few_recent_samples",
            "confidence": 0.0,
            "window_sec": max(0.0, now - host._safe_wait_start),
            "sample_count": len(window_samples),
            "windows": [],
        }

    window_reports = []
    for window_sec in POST_CHARGE_PERIODIC_WINDOWS_SEC:
        period_samples = [s for s in window_samples if now - s[0] <= window_sec]
        window_reports.append(evaluate_post_charge_window(host, period_samples, params, window_sec))

    valid_windows = [w for w in window_reports if w.get("status") not in ("insufficient",)]
    primary_window = valid_windows[-1] if valid_windows else window_reports[-1]

    t0, v0, i0, temp0 = window_samples[0]
    t1, v1, i1, temp1 = window_samples[-1]
    elapsed_sec = max(0.0, t1 - t0)
    if elapsed_sec < params["min_window_sec"]:
        return {
            "active": True,
            "status": "insufficient",
            "reason": "window_too_short",
            "confidence": 0.0,
            "window_sec": elapsed_sec,
            "sample_count": len(window_samples),
            "windows": window_reports,
        }

    # Р›РёРЅРµР№РЅС‹Р№ С‚СЂРµРЅРґ V(t), СѓРґРѕР±РЅРµРµ С‡РёС‚Р°С‚СЊ РІ РјР’/РјРёРЅ.
    return {
        "active": True,
        "status": primary_window.get("status", "stable"),
        "reason": primary_window.get("reason", "plateau"),
        "primary_window_sec": primary_window.get("window_sec"),
        "windows": window_reports,
        "window_summary": ", ".join(f"{w['label']}={w['status']}" for w in window_reports),
        "sample_count": len(window_samples),
        "window_sec": elapsed_sec,
        "drop_v": primary_window.get("drop_v"),
        "start_v": v0,
        "end_v": v1,
        "start_i": i0,
        "end_i": i1,
        "slope_mv_min": primary_window.get("slope_mv_min"),
        "decay_mv_min": primary_window.get("decay_mv_min"),
        "temp_start_c": temp0,
        "temp_end_c": temp1,
        "temp_min_c": primary_window.get("temp_min_c"),
        "temp_max_c": primary_window.get("temp_max_c"),
        "temp_span_c": primary_window.get("temp_span_c"),
        "current_max_a": primary_window.get("current_max_a"),
        "current_avg_a": primary_window.get("current_avg_a"),
        "profile": host.battery_type,
        "confidence": primary_window.get("confidence"),
        "stratification_risk": primary_window.get("stratification_risk"),
        "note": (
            "РљРѕСЃРІРµРЅРЅС‹Р№ РїРѕСЃС‚Р·Р°СЂСЏРґРЅС‹Р№ СЃРёРіРЅР°Р»: Р°РЅР°Р»РёР·РёСЂСѓРµРј РїР°РґРµРЅРёРµ V РїСЂРё РїРѕС‡С‚Рё РЅСѓР»РµРІРѕРј С‚РѕРєРµ Рё СЃС‚Р°Р±РёР»СЊРЅРѕР№ С‚РµРјРїРµСЂР°С‚СѓСЂРµ. "
            "Р­С‚Рѕ СЌРІСЂРёСЃС‚РёРєР°, Р° РЅРµ РґРѕРєР°Р·Р°С‚РµР»СЊСЃС‚РІРѕ СЃС‚СЂР°С‚РёС„РёРєР°С†РёРё."
        ),
    }

def get_timers(host) -> Dict[str, Any]:
    """v2.6 РџРѕР»СѓС‡РёС‚СЊ РґР°РЅРЅС‹Рµ С‚Р°Р№РјРµСЂРѕРІ РґР»СЏ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ Рё AI."""
    now = time.time()

    # РћР±С‰РµРµ РІСЂРµРјСЏ Р·Р°СЂСЏРґР°
    total_elapsed = now - host.total_start_time if host.total_start_time > 0 else 0
    total_hours = int(total_elapsed // 3600)
    total_mins = int((total_elapsed % 3600) // 60)
    total_str = f"{total_hours:02d}:{total_mins:02d}"

    # Р’СЂРµРјСЏ РІ С‚РµРєСѓС‰РµРј СЌС‚Р°РїРµ
    stage_elapsed = now - host.stage_start_time if host.stage_start_time > 0 else 0

    # Р—Р°С‰РёС‚Р° РѕС‚ Р±Р°РіР°: stage_time РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ Р±РѕР»СЊС€Рµ total_time
    if stage_elapsed > total_elapsed:
        stage_elapsed = total_elapsed

    stage_hours = int(stage_elapsed // 3600)
    stage_mins = int((stage_elapsed % 3600) // 60)
    stage_str = f"{stage_hours:02d}:{stage_mins:02d}"

    # РћСЃС‚Р°РІС€РµРµСЃСЏ РІСЂРµРјСЏ РґРѕ Р»РёРјРёС‚Р° С‚РµРєСѓС‰РµРіРѕ СЌС‚Р°РїР°
    remaining_str = "вЂ”"
    stage_limit_sec = None

    if host.current_stage == host.STAGE_MAIN:
        stage_limit_sec = MAIN_STAGE_MAX_HOURS * 3600  # 72 С‡Р°СЃР° Р·Р°С‰РёС‚РЅС‹Р№ Р»РёРјРёС‚
    elif host.current_stage == host.STAGE_DESULFATION:
        stage_limit_sec = desulfation_duration_seconds()  # 2 С‡Р°СЃР°
    elif host.current_stage == host.STAGE_MIX:
        if host.finish_timer_start:
            stage_limit_sec = MIX_DONE_TIMER
            stage_elapsed = now - host.finish_timer_start
        elif host.battery_type == host.PROFILE_EFB:
            stage_limit_sec = EFB_MIX_MAX_HOURS * 3600
        elif host.battery_type == host.PROFILE_CA:
            stage_limit_sec = CA_MIX_MAX_HOURS * 3600
        elif host.battery_type == host.PROFILE_AGM:
            stage_limit_sec = AGM_MIX_MAX_HOURS * 3600
        else:
            stage_limit_sec = MIX_DONE_TIMER
    elif host.current_stage == host.STAGE_SAFE_WAIT:
        stage_limit_sec = SAFE_WAIT_MAX_SEC  # 2 С‡Р°СЃР°
        stage_elapsed = now - host._safe_wait_start if host._safe_wait_start > 0 else 0

    if stage_limit_sec:
        remaining_sec = stage_limit_sec - stage_elapsed
        if remaining_sec > 0:
            rem_hours = int(remaining_sec // 3600)
            rem_mins = int((remaining_sec % 3600) // 60)
            remaining_str = f"{rem_hours:02d}:{rem_mins:02d}"
        else:
            remaining_str = "00:00"

    return {
        "total_time": total_str,
        "stage_time": stage_str,
        "remaining_time": remaining_str,
        "total_elapsed_sec": total_elapsed,
        "stage_elapsed_sec": stage_elapsed,
        "stage_limit_sec": stage_limit_sec,
    }

def format_seconds(host, seconds: Optional[float]) -> str:
    if seconds is None:
        return "вЂ”"
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(seconds)}СЃ"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}Рј"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    if mins:
        return f"{hours}С‡ {mins}Рј"
    return f"{hours}С‡"

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
        "ovp_offset_v": OVP_OFFSET,
        "ocp_offset_a": OCP_OFFSET,
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

__all__ = [
    "ai_stage_snapshot",
    "bank_fault_risk_snapshot",
    "get_timers",
]
