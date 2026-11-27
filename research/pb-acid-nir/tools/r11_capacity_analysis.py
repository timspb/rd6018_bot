"""R11 independent offline computation; NOT a charger or discharge-device controller."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite, log
from statistics import mean

@dataclass(frozen=True)
class Point:
    t_s: float
    v_batt: float
    discharge_a: float
    t_batt_c: float | None = None

def peukert_exponent(i1: float, t1_h: float, i2: float, t2_h: float) -> float:
    """Two complete discharges with the same cutoff, starting SOC and temperature."""
    if min(i1, i2, t1_h, t2_h) <= 0 or i1 == i2:
        raise ValueError("positive and distinct currents, positive times required")
    return log(t1_h / t2_h) / log(i2 / i1)

def modeled_capacity(c20_ah: float, discharge_a: float, k: float) -> float:
    """Illustrative Peukert Q(I); do not substitute for a measured C20."""
    if min(c20_ah, discharge_a) <= 0 or k < 1:
        raise ValueError("invalid model inputs")
    return c20_ah * (discharge_a / (c20_ah / 20.0)) ** (1.0 - k)

def integrate_until_cutoff(points: list[Point], cutoff_v: float = 10.50,
                           max_gap_s: float | None = None) -> dict:
    """Integrate pre-cutoff U,I records with linear cutoff interpolation.

    Once the battery crosses cutoff, a post-OFF sample must not be used.
    Instrument synchronization, calibration, and safe hardware cutoff are independent.
    """
    if len(points) < 2 or cutoff_v <= 0:
        raise ValueError("at least two observations and a positive cutoff required")
    if max_gap_s is not None and max_gap_s <= 0:
        raise ValueError("max_gap_s must be positive")
    for p in points:
        values = (p.t_s, p.v_batt, p.discharge_a)
        if not all(isfinite(v) for v in values) or p.v_batt <= 0 or p.discharge_a <= 0:
            raise ValueError("invalid telemetry; all samples must be under positive load")
        if p.t_batt_c is not None and not isfinite(p.t_batt_c):
            raise ValueError("invalid temperature")
    if points[0].v_batt <= cutoff_v:
        raise ValueError("battery already at/below cutoff when sampling began")
    q_ah = 0.0
    w_wh = 0.0
    cutoff_t = None
    used_points = 1
    for a,b in zip(points, points[1:]):
        dt = b.t_s - a.t_s
        if dt <= 0 or (max_gap_s is not None and dt > max_gap_s):
            raise ValueError("non-monotonic timestamp or telemetry gap")
        # Both observations must be made while the real discharge current is flowing.
        fraction = 1.0 if b.v_batt > cutoff_v else (
            (a.v_batt - cutoff_v) / (a.v_batt - b.v_batt) if a.v_batt > cutoff_v else 0.0
        )
        if fraction < 0 or fraction > 1:
            raise ValueError("invalid cutoff interpolation")
        elapsed = dt * fraction
        if elapsed > 0:
            i_at = a.discharge_a + fraction * (b.discharge_a - a.discharge_a)
            v_at = a.v_batt + fraction * (b.v_batt - a.v_batt)
            q_ah += (a.discharge_a + i_at) * 0.5 * elapsed / 3600
            w_wh += (a.discharge_a * a.v_batt + i_at * v_at) * 0.5 * elapsed / 3600
        used_points += 1
        if b.v_batt <= cutoff_v:
            cutoff_t = a.t_s + elapsed
            break
    return {
        "complete": cutoff_t is not None,
        "cutoff_t_s": cutoff_t,
        "elapsed_h": ((cutoff_t if cutoff_t is not None else points[-1].t_s) - points[0].t_s) / 3600,
        "observed_ah": q_ah,
        "observed_wh": w_wh,
        "used_points": used_points,
        "interpretation": "full_to_cutoff" if cutoff_t is not None else "partial_only",
    }

def main():
    # Synthetic input only. No battery operated.
    ps=[Point(t_s=i*3600, v_batt=12.7-2.2*i/20, discharge_a=3.6, t_batt_c=25.)
        for i in range(21)]
    x=integrate_until_cutoff(ps,cutoff_v=10.5,max_gap_s=3700)
    assert x["complete"] and abs(x["observed_ah"]-72)<1e-10
    assert abs(x["observed_wh"]-835.2)<1e-8
    assert abs(modeled_capacity(72, 7.2, 1.2) - 72*2**(-0.2)) < 1e-12
    assert abs(peukert_exponent(3.6,20,7.2,20/2**1.2)-1.2)<1e-12
    cropped=integrate_until_cutoff(ps[:11],cutoff_v=10.5)
    assert not cropped["complete"] and cropped["interpretation"]=="partial_only"
    # Crossing between records: at 3600s U=11.5; at 7200s U=10.3.
    y=integrate_until_cutoff([Point(0,12.6,4),Point(3600,11.5,4),Point(7200,10.3,4)])
    assert y["complete"] and abs(y["cutoff_t_s"]-6600)<1e-9
    assert abs(y["observed_ah"]-(4*6600/3600))<1e-10
    for invalid in ([Point(0,12,4),Point(60,11,0)],
                    [Point(0,12,4),Point(0,10.5,4)]):
        try:
            integrate_until_cutoff(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe telemetry should be rejected")
    print("R11 synthetic offline checks PASS: C20=72Ah, W=835.2Wh, cutoff interpolation, partial, Peukert, invalid telemetry")
if __name__=="__main__":
    main()