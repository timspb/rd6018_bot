"""Archive public primary sources, calculate published temperature-capacity results.
No instrument commands or operational charging settings."""
from pathlib import Path
import urllib.request,hashlib,concurrent.futures,math
r=Path(__file__).resolve().parents[1]/'sources'/'S4';r.mkdir(parents=True,exist_ok=True)
urls={'Cao_2015_thesis.pdf':"https://etd.auburn.edu/bitstream/handle/10415/4817/Nan%20Cao%27s%20Thesis%20nzc0013.pdf?isAllowed=y&sequence=2",'Prasad_2023_preprint.pdf':'https://d197for5662m48.cloudfront.net/documents/publicationstatus/127748/preprint_pdf/1f997a6b25c7d118170701a83ea95c99.pdf'}
def fetch(item):
 n,u=item
 try:
  with urllib.request.urlopen(u,timeout=8) as f:b=f.read(25000001)
  assert b.startswith(b'%PDF') and len(b)<=25000000
  (r/n).write_bytes(b);return hashlib.sha256(b).hexdigest()+'  '+n,len(b)
 except Exception as e:print('NOT_ARCHIVED',n,str(e),flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:rows=[v for v in ex.map(fetch,urls.items()) if v]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x,n in rows if x not in old)+'\n',encoding='utf8')
for x,n in rows:print('ARCHIVED',x,n)
# Cao Table 8 pp70-71: first nine values visually verified, remaining text only.
q={-15:56.14,-10:57.73,-5:60.26,0:63.31,5:66.39,10:68.72,15:72.07,20:72.83,25:73.74,30:75.59,35:76.94,40:76.20,45:74.51,50:73.82,55:72.46,60:71.84}
base=q[25]
for T in (-15,0,15,25,35,60):
 print('CAO',T,q[T],'relative_25_pct',round(100*q[T]/base,4),'relative_nominal_pct',round(100*q[T]/70,4),'visual' if T<=25 else 'machine_text')
print('CAO secant Ah/C',[(a,b,round((q[b]-q[a])/(b-a),4)) for a,b in [(-15,0),(0,25),(25,35),(35,60)]])
# Check author polynomial coefficients, no extrapolation or transfer.
f=lambda t:-.00749*t*t+.5718*t+64.44
print('CAO_FIT_AT25',f(25),'RMSE_all_text_rows',math.sqrt(sum((f(t)-v)**2 for t,v in q.items())/len(q)))
print('CAO_aged_relative_separate_baseline',100*37.5/72.8,100*69/72.8)
# Prasad published §3.1: durations after 120 cycles, not 130-cycle figure.
for T,h in [(-10,1.5),(0,3.8),(25,2.5),(40,2.0)]:
 print('PRASAD120',T,'reported_h',h,'derived_Ah',.5*h)
for T,start,end,reported in [(-10,78,46,74),(0,95,89,17),(25,67,28,69),(40,73,10,92)]:
 print('PRASAD130',T,'relative_drop_from_SOH_pairs_pct',round(100*(1-end/start),2),'separate_reported_degradation_pct',reported)
print('S4_TEMPERATURE_AUDIT_PASS; descriptive arithmetic, no universal temperature correction')
