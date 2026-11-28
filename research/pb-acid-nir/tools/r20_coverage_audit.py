"""Frozen A09 models: full-coverage grouped fallback comparison; offline."""
from pathlib import Path
import runpy,contextlib,io,statistics as st
root=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
 a=runpy.run_path(str(root/'tools/r20_rest_history_audit.py'))
rows=a['rows'];joint=a['joint'];predict=a['predict']
J={(r[0],r[1]):r for r in joint}
fce=lambda r:[r[1]]
combined=lambda r:[r[1],r[9],r[10],r[3],r[4],r[5]]
cells=sorted(set(r[0] for r in rows))
all_errors=[[],[]];macro=[[],[]]
for cell in cells:
 train=[r for r in rows if r[0]!=cell];test=[r for r in rows if r[0]==cell]
 jtrain=[r for r in joint if r[0]!=cell];jtest=[r for r in joint if r[0]==cell]
 base=predict(train,test,fce,1)
 jp=predict(jtrain,jtest,combined,1)
 lookup={(r[0],r[1]):y for r,y in zip(jtest,jp)}
 e=[[],[]]
 for r,y in zip(test,base):
  key=(r[0],r[1]);v=lookup.get(key,y)
  e[0].append(abs(y-r[2]));e[1].append(abs(v-r[2]))
  if key not in lookup:print('FALLBACK',cell,r[1],round(r[2],4),round(y,4),round(abs(y-r[2]),4))
 for k in range(2):
  all_errors[k]+=e[k];macro[k].append(st.mean(e[k]))
 print('FOLD',cell,'coverage',len(jtest),len(test),'MAE baseline/hybrid',*[round(st.mean(x),5) for x in e])
print('TOTAL',len(rows),'JOINT',len(joint),'MACRO',*[round(st.mean(x),5) for x in macro],'POOLED',*[round(st.mean(x),5) for x in all_errors])
assert len(rows)==31 and len(joint)==26
print('A10_COVERAGE_PASS; exploratory only, no tuning and no hardware I/O')
