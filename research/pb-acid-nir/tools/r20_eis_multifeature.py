"""Exploratory, fixed-model leave-one-cell-out comparison. No device I/O."""
from pathlib import Path
import runpy,contextlib,io,statistics as st,math
root=Path(__file__).resolve().parents[1]
with contextlib.redirect_stdout(io.StringIO()):
 a=runpy.run_path(str(root/'tools/r20_eis_capacity_join.py'))
rows=a['rows']
# Training-only standardization; fixed ridge penalty (lambda=1, sum-squared loss).
def solve(A,b):
 m=[list(x)+[y] for x,y in zip(A,b)]
 for j in range(len(b)):
  k=max(range(j,len(b)),key=lambda k:abs(m[k][j]))
  m[k],m[j]=m[j],m[k]
  v=m[j][j];assert abs(v)>1e-12
  m[j]=[x/v for x in m[j]]
  for i in range(len(b)):
   if i!=j:
    v=m[i][j];m[i]=[x-v*y for x,y in zip(m[i],m[j])]
 return [x[-1] for x in m]
def predict(train,test,features,lam):
 x=[features(r) for r in train];y=[r[2] for r in train]
 mu=[st.mean(c) for c in zip(*x)];sd=[st.pstdev(c) or 1 for c in zip(*x)]
 def trans(r):return [1]+[(v-m)/s for v,m,s in zip(features(r),mu,sd)]
 X=[trans(r) for r in train];p=len(X[0])
 A=[[sum(r[i]*r[j] for r in X)+(lam if i==j and i else 0) for j in range(p)] for i in range(p)]
 b=[sum(r[i]*v for r,v in zip(X,y)) for i in range(p)]
 w=solve(A,b)
 return [sum(x*y for x,y in zip(trans(r),w)) for r in test]
models=[
 ('FCE OLS',lambda r:[r[1]],0),
 ('1k OLS',lambda r:[r[3]],0),
 ('10Hz OLS',lambda r:[r[4]],0),
 ('FCE ridge',lambda r:[r[1]],1),
 ('two-band ridge',lambda r:[r[3],r[4]],1),
 ('FCE+two-band ridge',lambda r:[r[1],r[3],r[4]],1),
 ('FCE+1k+ratio ridge',lambda r:[r[1],r[3],math.log(r[4]/r[3])],1)]
def evaluate(rows,models):
 cells=sorted(set(r[0] for r in rows));out=[]
 for name,feat,lam in models:
  fold=[];allerr=[]
  for cell in cells:
   train=[r for r in rows if r[0]!=cell];test=[r for r in rows if r[0]==cell]
   pred=predict(train,test,feat,lam)
   err=[abs(v-r[2]) for v,r in zip(pred,test)]
   fold.append(st.mean(err));allerr+=err
  out.append((name,fold,st.mean(fold),st.mean(allerr)))
 print('CELLS',cells,'ROWS',len(rows))
 for name,fold,macro,micro in out:print(name,'folds',*[round(x,4) for x in fold],'macro',round(macro,4),'pooled',round(micro,4))
 return out
print('PRIMARY COMMON CASES');out=evaluate(rows,models)
# Additional lower frequency complete cases, same rows for all comparisons.
v=a['a']['selections']
three=[]
for r in rows:
 z=v[(r[0],r[1],1,'aftCyc')][2]
 if z[2]:three.append((*r,z[1]))
print('LOW_FREQ SENSITIVITY',len(three),{c:sum(r[0]==c for r in three) for c in sorted(set(r[0] for r in three))})
if len(set(r[0] for r in three))==4:
 evaluate(three,[models[0],models[3],models[5],('FCE+three-band ridge',lambda r:[r[1],r[3],r[4],r[5]],1)])
print('A08_COMPLETE exploratory fixed models, no independent validation')
