"""Archive new open university-hosted primary experimental papers for positive active mass."""
from pathlib import Path
from urllib.request import Request,urlopen
from hashlib import sha256
OUT=Path(r"<RESEARCH_ROOT>\sources\R17")
DOCS=[
("Cattelan_2025_Carbon_Positive_AGM.pdf",
"https://research.unipd.it/retrieve/ec1452af-6f20-4281-a4b4-de86990ec1c2/Cattelan%20et%20al.%20-%202025%20-%20Effect%20of%20innovative%20carbon%20additives%20in%20the%20positive%20active%20mass%20of%20absorbent%20glass%20mat%20lead%20acid%20battery.pdf"),
("Cattelan_2026_Carbon_Positive_AGM.pdf",
"https://research.unipd.it/retrieve/167cd10c-7e85-4668-b757-a591691f6150/1-s2.0-S0013468626008868-main.pdf"),
]
for fn,url in DOCS:
 target=OUT/fn
 if target.exists() and target.read_bytes().startswith(b"%PDF"):
  print("EXISTING",fn,target.stat().st_size,sha256(target.read_bytes()).hexdigest(),flush=True)
  continue
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0"}),timeout=20) as h:
   data=h.read(25000001)
  if not data.startswith(b"%PDF") or len(data)>25000000:
   print("INVALID_PDF",fn,len(data),flush=True);continue
  target.write_bytes(data)
  print("ARCHIVED",fn,len(data),sha256(data).hexdigest(),flush=True)
 except Exception as exc:
  print("FAILED",fn,type(exc).__name__,flush=True)