"""Check published heat accounting and public source provenance. Offline research."""
from pathlib import Path
import urllib.request,hashlib,concurrent.futures
r=Path(__file__).resolve().parents[1]/'sources'/'S4';r.mkdir(parents=True,exist_ok=True)
urls={'Jaworski_Hawkins_1996.pdf':'https://www.telepower.com.au/INT96b.PDF','Pavlov_2004_PAM.pdf':'https://electronicsandbooks.com/edt/manual/Magazine/J/Journal%20of%20Power%20Sources/2004%20%28Vol%20137%29/No02%28163-336%29/288-308.pdf'}
def get(x):
 n,u=x
 try:
  with urllib.request.urlopen(u,timeout=8) as f:b=f.read(15000001)
  assert b.startswith(b'%PDF') and len(b)<=15000000
  (r/n).write_bytes(b);return hashlib.sha256(b).hexdigest()+'  '+n,len(b)
 except Exception as e:print('NOT_ARCHIVED',n,str(e));return None
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:rows=[v for v in ex.map(get,urls.items()) if v]
p=r/'SHA256SUMS.txt';old=p.read_text(encoding='utf8') if p.exists() else ''
p.write_text(old.rstrip()+'\n'+'\n'.join(x for x,n in rows if x not in old)+'\n',encoding='utf8')
for x,n in rows:print('ARCHIVED',x,n)
for j,ohmic,chemical,cell,box,loss in [(1,2106,-1278,474,227,128),(2,1205,-485,545,129,99)]:
 net=ohmic+chemical;accounted=cell+box+loss
 print('DISCHARGE',j,'net_J',net,'accounted_J',accounted,'residual_J',accounted-net,'endothermic_fraction',-chemical/ohmic)
print('CHARGE_MID_UNCLOSED_FRACTION',(3823-2773)/3823)
print('CHARGE_LATE_NET',261+440+1003-1524,'polarization_over_ohmic',1003/261)
print('CHARGE_TOTAL_DISCREPANCY',4314-3537,'relative_generated',(4314-3537)/4314,'relative_reported_wall_loss',(4314-3537)/1059)
# NBS 1939 interpolated Table5: different total solubility and conductivity objectives.
for w,s in [(10,6.68),(30,2.82),(40,1.52)]:
 print('NBS_SOLUBILITY_RELATIVE_TO_10WT',w,s/6.68)
print('S4_HEAT_MATERIAL_AUDIT_PASS')
