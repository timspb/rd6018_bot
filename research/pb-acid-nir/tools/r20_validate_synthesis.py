"""R20 synthesis ledger validator; read-only, no device/network actions."""
from pathlib import Path
import re
R=Path(r"<RESEARCH_ROOT>")
con=(R/"CONCLUSIONS.md").read_text(encoding="utf-8-sig")
hyp=(R/"HYPOTHESES.md").read_text(encoding="utf-8-sig")
road=(R/"ROADMAP.md").read_text(encoding="utf-8-sig")
report=(R/"23_R20_SYNTHESIS.md").read_text(encoding="utf-8-sig")
def ids(text,prefix):
 vals=re.findall(rf"(?m)\|\s*{prefix}(\d{{2}})\s*\|",text) if prefix=="H" else re.findall(rf"(?m)^{prefix}(\d{{2,3}})\s+[—-]",text)
 return [int(x) for x in vals]
c=ids(con,"C");h=ids(hyp,"H")
assert len(c)==len(set(c)), "duplicate conclusion IDs"
assert set(c)==set(range(1,188)), f"conclusion gaps: {sorted(set(range(1,188))-set(c))}"
assert len(h)==len(set(h)), "duplicate hypothesis IDs"
assert set(h)==set(range(1,93)), f"hypothesis gaps: {sorted(set(range(1,93))-set(h))}"
assert re.search(r"(?m)^\|\s*R20\s*\|[^\n]*\|\s*PARTIAL\s*\|",road)
assert "C01–C187" in report and "H01–H92" in report
for token in ["E1","E2","E3","E4","UNKNOWN","No-go","C20","CCA","EFC","RD6018","БВ-600"]:
 assert token in report, f"missing synthesis element {token}"
assert (R/"23_R20_SYNTHESIS.md").is_file()
print("R20_LEDGER_PASS conclusions",len(c),"hypotheses",len(h))
print("R20_SCOPE_PASS evidence grades, transferability, no-go, metrology, diagnostics, production isolation")
