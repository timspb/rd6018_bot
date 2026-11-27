"""Archive primary historical public-domain NBS/NIST publications for R16."""
from pathlib import Path
from urllib.request import Request, urlopen
from hashlib import sha256
ROOT=Path(r"<RESEARCH_ROOT>\sources\R16")
ROOT.mkdir(parents=True,exist_ok=True)
SOURCES=[
 ("NBS_1939_Craig_Vinal_PbSO4_solubility.pdf","https://nvlpubs.nist.gov/nistpubs/jres/22/jresv22n1p55_A1b.pdf"),
 ("NBS_1934_Vinal_Craig_H2SO4_resistivity.pdf","https://nvlpubs.nist.gov/nistpubs/jres/13/jresv13n5p689_A2b.pdf")
]
for filename,url in SOURCES:
 out=ROOT/filename
 if out.exists() and out.read_bytes().startswith(b"%PDF"):
  print("EXISTING",filename,"bytes",out.stat().st_size,"sha256",sha256(out.read_bytes()).hexdigest(),flush=True)
  continue
 try:
  req=Request(url,headers={"User-Agent":"Mozilla/5.0"})
  with urlopen(req,timeout=25) as response:
   data=response.read(26000001)
  if len(data)>26000000 or not data.startswith(b"%PDF"):
   print("REJECT_FORMAT_OR_SIZE",filename,len(data),flush=True)
  else:
   out.write_bytes(data)
   print("ARCHIVED",filename,"bytes",len(data),"sha256",sha256(data).hexdigest(),flush=True)
 except Exception as exc:
  print("UNAVAILABLE",filename,type(exc).__name__,flush=True)