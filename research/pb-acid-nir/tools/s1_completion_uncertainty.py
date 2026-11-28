"""Offline metrology examples and public document archive; no hardware commands."""
from pathlib import Path
import math,urllib.request,hashlib
r=Path(__file__).resolve().parents[1]/'sources'/'S1'
sources={
'Yuasa_NP_rev2000.pdf':'https://gsyuasa-es.com/Downloads/NP_Application_manual.pdf',
'Cyclon_2008.pdf':'https://www.enersys.com/493c0d/globalassets/documents/product-documentation/cyclon/amer/us-cyc-am-007_0408.pdf',
'Yu_2018_efficiency.pdf':'https://pure.tudelft.nl/ws/portalfiles/portal/46987973/energies_11_02305_v2.pdf'}
for name,url in sources.items():
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Pb-Research academic archive'}),timeout=6) as f:b=f.read(15000001)
  assert b.startswith(b'%PDF') and len(b)<=15000000
  (r/name).write_bytes(b);line=hashlib.sha256(b).hexdigest()+'  '+name
  p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf-8') if p.exists() else ''
  if line not in old:p.write_text(old.rstrip()+'\n'+line+'\n',encoding='utf-8')
  print('ARCHIVED',len(b),line,flush=True)
 except Exception as e:print('NOT_ARCHIVED',name,str(e),flush=True)
# Exact algebra: integral efficiency cannot be substituted for differential efficiency.
# Synthetic piecewise stored-charge law in dimensionless units.
qout=[.90,.95,1.0]
qin=[.92,1.02,1.22]
print('SYNTHETIC integral efficiencies',[round(a/b,4) for a,b in zip(qout,qin)])
print('SYNTHETIC marginal efficiencies',[round((qout[j]-qout[j-1])/(qin[j]-qin[j-1]),4) for j in (1,2)])
# Synthetic reference-capacity repeatability; 72Ah example, 2% standard uncertainty,
# independent measurement errors. Not a measured instrument specification.
u=1.44;ud=math.sqrt(2)*u;udd=math.sqrt(4)*u
for delta in (1,4,8):
 print('SYNTHETIC effect Ah',delta,'paired 95% halfwidth',round(1.96*ud,3),'difference-in-differences halfwidth',round(1.96*udd,3))
# A completed electrical profile cannot logically identify electrochemical state.
# Identical terminal current; different admissible effective partitions.
assert .1+.9==.9+.1
print('S1_COMPLETION_AUDIT_PASS')
