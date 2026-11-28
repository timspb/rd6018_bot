"""Offline P3 feature extraction; no device control, no battery diagnosis.
All thresholds and windows supplied by preregistered research protocol.
Sign convention: positive current into battery. Time relative to observed transition.
"""
from dataclasses import dataclass
from math import isfinite
from statistics import median

@dataclass(frozen=True)
class Sample:
    t: float
    u: float
    i: float
    temp: float

@dataclass(frozen=True)
class Limits:
    max_gap: float
    current_tol: float
    temperature_span: float
    voltage_error_bound: float
    min_recovery: float
    min_samples: int = 3

def validate(rows, lim):
    vals=(lim.max_gap,lim.current_tol,lim.temperature_span,lim.voltage_error_bound,lim.min_recovery)
    if not all(isfinite(v) and v>0 for v in vals) or lim.min_samples<2:
        raise ValueError("invalid protocol")
    if len(rows)<2 or any(not all(isfinite(v) for v in (r.t,r.u,r.i,r.temp)) or r.u<=0 for r in rows):
        raise ValueError("invalid samples")
    if any(not 0<b.t-a.t<=lim.max_gap for a,b in zip(rows,rows[1:])):
        raise ValueError("nonmonotonic clock or missing interval")

def window(rows, start, end, lim):
    if not start<end: raise ValueError("invalid window")
    z=[r for r in rows if start<=r.t<end]
    if len(z)<lim.min_samples or z[0].t-start>lim.max_gap or end-z[-1].t>lim.max_gap:
        raise ValueError("insufficient window coverage")
    return median(r.u for r in z)

def stable(rows, start, end, current, lim):
    z=[r for r in rows if start<=r.t<end]
    if not z or z[0].t-start>lim.max_gap or end-z[-1].t>lim.max_gap:
        raise ValueError("incomplete phase")
    if any(abs(r.i-current)>lim.current_tol for r in z):
        raise ValueError("current not stable")
    if max(r.temp for r in z)-min(r.temp for r in z)>lim.temperature_span:
        raise ValueError("temperature drift")
    return z

def cdf(rows, lim, *, load, pre, settle, bin_seconds, bins, plateau_bins=3):
    """Fixed-window candidate detector; never infer SOC or cause.
    Plateau = final preregistered bins, not extrapolated equilibrium.
    """
    if not isfinite(load) or load<=lim.current_tol or pre<=0 or settle<0 or bin_seconds<=0 or bins<6 or not 2<=plateau_bins<bins-2:
        raise ValueError("invalid CDF design")
    try:
        validate(rows,lim)
        end=settle+bin_seconds*bins
        stable(rows,-pre,0,0,lim)
        stable(rows,settle,end,-load,lim)
        u0=window(rows,-pre,0,lim)
        values=[window(rows,settle+j*bin_seconds,settle+(j+1)*bin_seconds,lim) for j in range(bins)]
        # Joint temperature drift, including baseline; no claim internal T is observed.
        z=[r.temp for r in rows if -pre<=r.t<end]
        if max(z)-min(z)>lim.temperature_span:raise ValueError("temperature drift across transition")
    except ValueError as exc:
        return {"status":"INVALID","reason":str(exc)}
    j=min(range(bins-plateau_bins),key=lambda j:values[j])
    trough=values[j];plateau=median(values[-plateau_bins:])
    delta=plateau-trough
    bound=2*lim.voltage_error_bound
    feature={"baseline_v":u0,"first_loaded_bin_v":values[0],
             "trough_v":trough,"trough_bin_s":[settle+j*bin_seconds,settle+(j+1)*bin_seconds],
             "late_window_v":plateau,"recovery_v":delta,"difference_error_bound_v":bound}
    # Initial fall must precede trough, with demonstrable later recovery.
    if j==0 or delta+bound<lim.min_recovery-1e-12:
        return {"status":"NOT_RESOLVED_IN_WINDOW",**feature}
    if delta-bound<lim.min_recovery+1e-12 or values[0]-trough<=bound+1e-12:
        return {"status":"AMBIGUOUS",**feature}
    # Detect a second supported dip after recovery, not noise-sized wiggles.
    # An earlier supported dip and recovery before the global trough also
    # make the single-dip interpretation ambiguous.
    for k in range(1,j):
        if values[0]-values[k]>bound and max(values[k+1:j+1])-values[k]-bound>=lim.min_recovery+1e-12:
            return {"status":"MULTIPLE_DIP_OR_DRIFT",**feature}
    peak=trough
    for v in values[j+1:]:
        peak=max(peak,v)
        if peak-v-bound>=lim.min_recovery+1e-12:
            return {"status":"MULTIPLE_DIP_OR_DRIFT",**feature}
    if max(values[-plateau_bins:])-min(values[-plateau_bins:])>bound+1e-12:
        return {"status":"RECOVERY_WITHOUT_STABLE_LATE_WINDOW",**feature}
    return {"status":"CDF_CANDIDATE",**feature}

def relaxation(rows, lim, *, before_current, pre, windows):
    """Observed finite-time voltage differences, no extrapolation to Ueq."""
    if abs(before_current)<=lim.current_tol or pre<=0 or not windows:
        raise ValueError("invalid relaxation design")
    if any(a<0 or b<=a for a,b in windows) or any(b>c for (_,b),(c,_) in zip(windows,windows[1:])):
        raise ValueError("windows must be ordered and disjoint")
    try:
        validate(rows,lim)
        stable(rows,-pre,0,before_current,lim)
        stable(rows,0,windows[-1][1],0,lim)
        z=[r.temp for r in rows if -pre<=r.t<windows[-1][1]]
        if max(z)-min(z)>lim.temperature_span:raise ValueError("temperature drift across transition")
        u_pre=window(rows,-pre,0,lim)
        u=[window(rows,a,b,lim) for a,b in windows]
    except ValueError as exc:return {"status":"INVALID","reason":str(exc)}
    return {"status":"FINITE_WINDOW_FEATURES","pre_v":u_pre,"windows":windows,"u_v":u,
            "delta_from_first_v":[v-u[0] for v in u],
            "r_apparent_ohm":[(u_pre-v)/before_current for v in u],
            "difference_error_bound_v":2*lim.voltage_error_bound}

def main():
    # Artificial fixture values only, not approved physical settings.
    lim=Limits(.11,.02,.2,.005,.03,3)
    def trace(values, current=-3.):
        return [Sample(k/10,12.8 if k<0 else values[k//10],0 if k<0 else current,25.) for k in range(-10,10*len(values))]
    kw=dict(load=3.,pre=1.,settle=0.,bin_seconds=1.,bins=9)
    base=[12.5,12.43,12.38,12.42,12.46,12.48,12.48,12.48,12.48]
    cases=[
        ("single",base,"CDF_CANDIDATE"),
        ("monotone",[12.5-.01*j for j in range(9)],"NOT_RESOLVED_IN_WINDOW"),
        ("double",[12.5,12.38,12.48,12.4,12.45,12.48,12.48,12.48,12.48],"MULTIPLE_DIP_OR_DRIFT"),
        ("noise",[12.50,12.495,12.49,12.50,12.50,12.50,12.50,12.50,12.50],"NOT_RESOLVED_IN_WINDOW"),
        ("earlier dip",[12.5,12.42,12.49,12.36,12.45,12.48,12.48,12.48,12.48],"MULTIPLE_DIP_OR_DRIFT"),
        ("boundary",[12.5,12.48,12.46,12.49,12.49,12.49,12.49,12.49,12.49],"AMBIGUOUS"),
        ("drifting late",[12.5,12.38,12.42,12.44,12.45,12.46,12.47,12.48,12.50],"RECOVERY_WITHOUT_STABLE_LATE_WINDOW")]
    for name,v,expected in cases:
        x=cdf(trace(v),lim,**kw)
        assert x["status"]==expected,(name,x)
        print(name,x["status"])
    r=trace(base)
    for name,z in [
        ("gap",r[:30]+r[33:]),("duplicate",r[:30]+[r[29]]+r[30:]),
        ("load change",[Sample(a.t,a.u,-2 if a.t>=4 else a.i,a.temp) for a in r]),
        ("thermal drift",[Sample(a.t,a.u,a.i,26 if a.t>=4 else a.temp) for a in r]),
        ("nonfinite",[Sample(a.t,float("nan") if a.t==4 else a.u,a.i,a.temp) for a in r]),
        ("truncated",r[:-20])]:
        assert cdf(z,lim,**kw)["status"]=="INVALID",name
        print(name,"INVALID")
    for current in [3.,-3.]:
        z=[Sample(k/10,13. if k<0 else 12.8-.01*(k//10),current if k<0 else 0.,25.) for k in range(-10,60)]
        x=relaxation(z,lim,before_current=current,pre=1.,windows=[(0,1),(2,3),(5,6)])
        assert x["status"]=="FINITE_WINDOW_FEATURES" and abs(x["delta_from_first_v"][-1]+.05)<1e-10
        # Signs are preserved: apparent R is not forced positive.
        assert abs(x["r_apparent_ohm"][0]-(.2/current))<1e-10
    assert relaxation([Sample(a.t,a.u,.1 if a.t>=0 else a.i,a.temp) for a in z],lim,before_current=-3.,pre=1.,windows=[(0,1),(5,6)])["status"]=="INVALID"
    print("P3_SYNTHETIC_PASS: 16 cases; no physical validation")

if __name__=="__main__":main()
