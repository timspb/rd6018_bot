from pathlib import Path
import urllib.request,hashlib
r=Path(__file__).resolve().parents[1]/'sources'/'S1'
r.mkdir(parents=True,exist_ok=True)
sources={'Backer_Meisner_2013.pdf':'https://www.vertiv.com/48dd01/globalassets/documents/battcon-static-assets/2013/the-effects-of-mechanical-electrolyte-mixing-on-vla-cells.pdf','Santos_2025.pdf':'https://www.scielo.br/j/rmat/a/7gkWqYKRcRxdHqDKYM4rMJh/?format=pdf&lang=en'}
for name,url in sources.items():
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Pb-Research academic archive'}),timeout=8) as f:b=f.read(15000001)
  assert b.startswith(b'%PDF') and len(b)<=15000000
  (r/name).write_bytes(b)
  h=hashlib.sha256(b).hexdigest()
  p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf-8') if p.exists() else ''
  line=h+'  '+name
  if line not in old:p.write_text(old.rstrip()+'\n'+line+'\n',encoding='utf-8')
  print('ARCHIVED',name,len(b),h,flush=True)
 except Exception as e:print('NOT_ARCHIVED',name,str(e),flush=True)
top=[1.283,1.254,1.242,1.233];bottom=[1.283,1.293,1.309,1.312];meter=[1.283,1.255,1.243,1.233]
print('GRADIENT',[round(b-t,3) for b,t in zip(bottom,top)])
print('UPPER_ERROR',[round(t-m,3) for t,m in zip(top,meter)])
print('AH_EFFICIENCY',[round(100/x,2) for x in [1.2,1.06]],'EXCESS_CHARGE_RATIO',round(.2/.06,3))
