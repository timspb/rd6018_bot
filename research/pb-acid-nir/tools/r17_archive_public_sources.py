"""Best-effort local archive of specifically identified open scholarly PDFs (no bypass)."""
from pathlib import Path
from urllib.request import Request, urlopen
from hashlib import sha256
OUT=Path(r"<RESEARCH_ROOT>\sources\R17")
OUT.mkdir(parents=True,exist_ok=True)
DOCS=[
 ("Lach_2019_Review_Applications_of_Carbon.pdf","https://s1.solacity.com/docs/Miscellaneous/Lach2019_Article_ApplicationsOfCarbonInLead-aci.pdf"),
 ("Bozkaya_2022_DCA_Carbon_Screening.pdf","https://d-nb.info/1251270131/34"),
 ("Xie_2024_Carbon_Foam_HRPSoC.pdf","https://www.cell.com/heliyon/pdf/S2405-8440(24)07370-5.pdf"),
 ("Bauknecht_2023_DCA_Additives.pdf","https://www.mdpi.com/2313-0105/9/5/263/pdf"),
 ("NCC_2023_Hydrogen_Evolution.pdf","https://www.mdpi.com/1420-3049/28/14/5618/pdf"),
]
for file,url in DOCS:
 target=OUT/file
 if target.exists() and target.open("rb").read(5).startswith(b"%PDF"):
  print("EXISTING",file,target.stat().st_size,sha256(target.read_bytes()).hexdigest(),flush=True)
  continue
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 academic literature research"}),timeout=14) as resp:
   data=resp.read(25000001)
  if not data.startswith(b"%PDF") or len(data)>25000000:
   print("NOT_PDF_OR_TOO_BIG",file,len(data),flush=True);continue
  target.write_bytes(data)
  print("ARCHIVED",file,"bytes",len(data),"sha256",sha256(data).hexdigest(),flush=True)
 except Exception as ex:
  print("ARCHIVE_UNAVAILABLE",file,type(ex).__name__,flush=True)