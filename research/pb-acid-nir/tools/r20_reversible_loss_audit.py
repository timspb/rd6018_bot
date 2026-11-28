"""R20-A04 arithmetic on published Table 1, plus approximate Fig 6 data. No hardware IO."""
from statistics import mean
rows=[(6,330,11,0,0),(14,320,13,370,2.2),(13,330,11,370,2.6),(24,350,12,310,1)]
assert 3*3*3*3==81
a,b=mean(r[1] for r in rows),mean(r[3] for r in rows)
assert a==332.5 and b==262.5
print("Selected cells only:",a,b,100*(b/a-1))
for cell,pre,g0,post,g1 in rows:
 print(cell,round(100*(post/pre-1),3),g0,g1)
assert mean(r[2] for r in rows if r[0] in (13,14))==12
assert abs(mean(r[4] for r in rows if r[0] in (13,14))-2.4)<1e-10
print("Fig6 approx: relative gain",100*(.56/.22-1),"final nominal percent",100*.56/1.2)
assert .56/1.2<.5
print("R20_A04_PASS: descriptive arithmetic; no fleet/pack inference, no charger control")
