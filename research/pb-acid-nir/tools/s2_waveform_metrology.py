"""Synthetic offline validation of signed charge/energy accounting and observation rules.
No device control, no charging setpoints or battery efficacy claims."""
import math
def integrate(rows,max_gap):
    """Piecewise-linear interpolation of synchronous terminal U,I.
    Positive I charges, positive terminal voltage. Reject gaps, missing/negative U.
    Integrate sign-separated I and exact product of two linear functions."""
    qpos=qneg=wpos=wneg=0.
    if len(rows)<2: raise ValueError('insufficient samples')
    for (t0,u0,i0),(t1,u1,i1) in zip(rows,rows[1:]):
        if not all(map(math.isfinite,(t0,u0,i0,t1,u1,i1))):raise ValueError('nonfinite')
        dt=t1-t0
        if not 0<dt<=max_gap or min(u0,u1)<=0:raise ValueError('invalid interval')
        cuts=[0.,1.]
        if i0*i1<0:cuts.insert(1,-i0/(i1-i0))
        for a,b in zip(cuts,cuts[1:]):
            h=dt*(b-a)/3600
            ia=i0+(i1-i0)*a;ib=i0+(i1-i0)*b
            ua=u0+(u1-u0)*a;ub=u0+(u1-u0)*b
            q=h*(ia+ib)/2
            w=h*(2*ua*ia+ua*ib+ub*ia+2*ub*ib)/6
            if q>=0:qpos+=q;wpos+=w
            else:qneg-=q;wneg-=w
    return qpos,qneg,wpos,wneg
def close(a,b):assert math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-10),(a,b)
a=integrate([(0,12,2),(3600,12,-2)],3600)
for x,y in zip(a,(.5,.5,6,6)):close(x,y)
b=integrate([(0,10,0),(3600,14,6)],3600)
close(b[0],3);close(b[2],38)
# Net charge zero is not zero energy: correlated voltage/current.
c=integrate([(0,14,2),(3600,10,-2)],3600)
close(c[0]-c[1],0);close(c[2]-c[3],4/3)
# Synthetic smooth waveform sampled at phase-locked zeroes.
# Exact over 1h: mean current 1A + 1A*sin(2*pi*t/10s).
# To demonstrate aliasing use same mean but nonzero alternating component;
# low-rate samples have no evidence of variance.
phase_locked=[(t,12,1.) for t in range(0,3601,10)]
q=integrate(phase_locked,10)
close(q[0],1);close(q[2],12)
# True mean-square current=1.5 A², sampled mean-square=1 A².
print('ALIAS mean-square true/sample',1.5,1.,'underestimate_percent',100*(1-1/1.5))
for rows,mg in [([(0,12,1),(0,12,1)],1), ([(0,12,1),(2,12,1)],1), ([(0,12,1),(1,float('nan'),1)],1), ([(0,12,1),(1,-12,1)],1)]:
    try:integrate(rows,mg)
    except ValueError:pass
    else:raise AssertionError('invalid trace admitted')
print('SIGNED_CROSSING',a,'VARIABLE_U_I',b,'ZERO_NET_ENERGY',c[2]-c[3])
# Paired independent experimental-unit effects; illustrative values, not pilot data.
# Normal planning approximation for difference-in-differences; SD of pair-level
# contrast includes biological + measurement variation, estimated by independent pilot.
for sd in (2.,4.,8.):
    for delta in (2.,4.):
        n=math.ceil(((1.959964+.841621)*sd/delta)**2)
        print('SYNTHETIC_PAIR_PLANNING SD',sd,'effect_above_null',delta,'n_pairs',n)
# Censoring: administrative end is not failure; safety-stop is competing outcome,
# not silently censored in a composite failure endpoint.
def classify_event(observed_failure,safety_stop,admin_end):
    if sum((observed_failure,safety_stop,admin_end))!=1:raise ValueError('ambiguous')
    return 'FAILURE' if observed_failure else 'SAFETY_STOP' if safety_stop else 'RIGHT_CENSORED'
assert classify_event(False,False,True)=='RIGHT_CENSORED'
assert classify_event(False,True,False)=='SAFETY_STOP'
print('S2_WAVEFORM_METROLOGY_PASS; synthetic checks only')
