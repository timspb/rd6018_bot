"""Read-only documentary acceptance count; no scientific validity inferred from count."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
t=(root/'RESEARCH_ACCEPTANCE.md').read_text(encoding='utf-8-sig')
road=(root/'ROADMAP.md').read_text(encoding='utf-8-sig')
rows=[x.strip().strip('|').split('|') for x in t.splitlines() if re.match(r'^\|\s*R\d\d(?:-D)?\s*\|',x)]
rows=[[c.strip() for c in x] for x in rows]
ids=re.findall(r'(?m)^\|\s*(R\d\d(?:-D)?)\s*\|',road)
assert len(rows)==22 and len(ids)==22 and set(x[0] for x in rows)==set(ids)
counts=[0,0,0,0]
for x in rows:
 assert len(x)==9,(x[0],len(x))
 m=re.fullmatch(r'PASS \(([^)]+)\)',x[2]);assert m and (root/m[1]).is_file()
 counts[0]+=1
 for j,k in enumerate([3,5,7],1):
  assert x[k] in ('PASS','OPEN') and x[k+1]
  counts[j]+=x[k]=='PASS'
assert counts==[22,20,19,1],counts
assert 'Current PASS 62/88' in t
print('ACCEPTANCE_COUNT_PASS',sum(counts),'/',len(rows)*4,'D Q K P',counts)
