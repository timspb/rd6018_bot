"""S5/P1/P2 offline synthetic reference-discharge validation. No device I/O."""
from math import isfinite,sqrt
def assess(rows, rated_ah, duration_h=20, cutoff=10.5, gap=2.0, limit=.02):
    # rows: elapsed seconds, terminal volts, positive discharge amperes,
    # validated battery temperature (not ambient), under_load bool.
    if len(rows)<2 or min(rated_ah,duration_h,gap,limit,cutoff)<=0: raise ValueError('metadata')
    target=rated_ah/duration_h
    q=w=0.; used=0; crossing=None
    if rows[0][0]!=0 or rows[0][1]<=cutoff: return {'status':'INVALID','reason':'start'}
    for a,b in zip(rows,rows[1:]):
        t0,v0,i0,T0,on0=a;t1,v1,i1,T1,on1=b
        if not all(isfinite(x) for x in (*a[:4],*b[:4])):return {'status':'INVALID','reason':'nonfinite'}
        if not 0<t1-t0<=gap:return {'status':'INVALID','reason':'time'}
        if not on0 or not on1:return {'status':'PARTIAL','reason':'unobserved loaded endpoint','observed_ah':q}
        if min(v0,v1)<=0 or max(abs(i0-target),abs(i1-target))>target*limit+1e-12 or max(abs(T0-25),abs(T1-25))>2:
            return {'status':'INVALID','reason':'out of test envelope'}
        f=1. if v1>cutoff else (v0-cutoff)/(v0-v1)
        h=(t1-t0)*f/3600
        v=v0+f*(v1-v0);i=i0+f*(i1-i0)
        q+=h*(i0+i)/2
        w+=h*(2*v0*i0+v0*i+v*i0+2*v*i)/6
        used+=1
        if v1<=cutoff:
            crossing=t0+(t1-t0)*f
            break
    return {'status':'TRACE_COMPLETE' if crossing is not None else 'PARTIAL','observed_ah':q,'observed_wh':w,'nominal_i_time_ah':target*crossing/3600 if crossing is not None else None,'cutoff_s':crossing,'intervals':used}
def classify(lo,hi,delta):
    if not all(isfinite(x) for x in (lo,hi,delta)) or lo>hi or delta<=0:raise ValueError('interval')
    if lo>delta:return 'MEANINGFUL_GAIN'
    if hi< -delta:return 'MEANINGFUL_LOSS'
    if lo>=-delta and hi<=delta:return 'PRACTICAL_EQUIVALENCE'
    return 'INCONCLUSIVE'
def delta_u(u0,u1,cov):
    if not all(isfinite(x) for x in (u0,u1,cov)) or min(u0,u1)<0 or abs(cov)>u0*u1:raise ValueError('covariance')
    return sqrt(max(0.,u0*u0+u1*u1-2*cov))
def main():
    # Constant current synthetic 72Ah at C20, exact 20h at cutoff.
    rows=[(t,12.7-2.2*t/72000,3.6,25.,True) for t in range(72001)]
    x=assess(rows,72)
    assert x['status']=='TRACE_COMPLETE' and abs(x['observed_ah']-72)<1e-7 and abs(x['observed_wh']-835.2)<1e-6,x
    assert assess(rows[:100],72)['status']=='PARTIAL'
    assert assess([rows[0],rows[3]],72)['reason']=='time'
    assert assess([rows[0],(1,12.69,3.8,25,True)],72)['status']=='INVALID'
    assert assess([rows[0],(1,12.69,3.6,28,True)],72)['status']=='INVALID'
    assert assess([rows[0],(1,12.69,0,25,False)],72)['status']=='PARTIAL'
    x=assess([(0,10.6,3.6,25,True),(2,10.4,3.6,25,True)],72)
    assert abs(x['cutoff_s']-1)<1e-10 and abs(x['observed_ah']-.001)<1e-12
    assert classify(4,6,3.6)=='MEANINGFUL_GAIN'
    assert classify(-6,-4,3.6)=='MEANINGFUL_LOSS'
    assert classify(-2,2,3.6)=='PRACTICAL_EQUIVALENCE'
    assert classify(-1,5,3.6)=='INCONCLUSIVE'
    assert delta_u(1,1,1)==0 and abs(delta_u(1,1,0)-sqrt(2))<1e-12
    print('P1/P2 synthetic trace + decision + covariance checks PASS; no hardware acceptance')
if __name__=='__main__':main()
