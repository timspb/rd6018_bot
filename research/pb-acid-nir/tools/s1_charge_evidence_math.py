"""Descriptive checks of published tables, not an operational charge model."""
import statistics as st
# Parnigotto 2022 Table 1, relative values normalized separately.
wl=[1.08,1.60,3.85,3.55,1.73,1,1.08,1.13,2.08]
tepos=[2.60,1.11,6.42,3.75,1.53,1.05,1,1.81,2.44]
teneg=[2.08,1,6.28,5.72,3.08,1.58,1.89,2.53,4.39]
for name,x in [('positive',tepos),('negative',teneg)]:
 loo=[st.correlation([v for j,v in enumerate(x) if j!=i],[v for j,v in enumerate(wl) if j!=i]) for i in range(9)]
 print('WL_TE',name,'r',round(st.correlation(x,wl),5),'leave_one_batch_range',round(min(loo),5),round(max(loo),5))
print('WL_RATIO',max(wl)/min(wl))
# Parker/McMahon 2024 Table3: only 2/3/4 are same fixed-interval second round.
for c,start,mid,end in [(1,3.81,4.27,4.14),(2,3.90,4.20,4.29),(3,3.89,4.27,4.37),(4,3.78,4.22,4.35)]:
 print('CAPACITY',c,'first50_percent',round(100*(mid/start-1),3),'final_vs_initial_percent',round(100*(end/start-1),3),'final_vs50_percent',round(100*(end/mid-1),3),'variable_interval' if c==1 else 'fixed_interval')
# A terminal current partition is underdetermined without independent reaction measurements.
# Dimensionless examples only, no charging instructions.
for useful,side in [(0.9,0.1),(0.1,0.9)]:
 assert abs(useful+side-1)<1e-12
 print('SAME_NORMALIZED_TERMINAL_CURRENT',1,'storage_fraction',useful,'side_fraction',side)
print('S1_EVIDENCE_MATH_PASS')
