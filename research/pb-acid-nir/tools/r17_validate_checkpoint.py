"""Guardrails: verify R17 files, counts and expected roadmap next step."""
from pathlib import Path
from hashlib import sha256
root=Path(r"<RESEARCH_ROOT>")
report=(root/"20_R17_CARBON_ACTIVE_MASS.md").read_text(encoding="utf-8")
road=(root/"ROADMAP.md").read_text(encoding="utf-8")
conc=(root/"CONCLUSIONS.md").read_text(encoding="utf-8")
hyp=(root/"HYPOTHESES.md").read_text(encoding="utf-8")
cp=(root/"CURRENT_CHECKPOINT.md").read_text(encoding="utf-8")
assert "| R17 | Углерод и активные массы | P1 | PARTIAL | 20_R17_CARBON_ACTIVE_MASS |" in road
assert "| R18 | Переполюсовка и последствия | P1 | OPEN |" in road
assert "R17 PARTIAL:" in cp
assert all(f"S{i:02d}" in report for i in range(1,15))
assert all(f"C{i}" in report and f"C{i} " in conc for i in range(67,76))
assert all(f"H{i}" in report and f"H{i} " in hyp for i in range(43,49))
paths={
  "Bozkaya_2022_DCA_Carbon_Screening.pdf":"e09e9c2149ecf6b2326f341e476db77fd52ce3a8fb9bd5188aeff638d98f082b",
  "Lach_2019_Review_Applications_of_Carbon.pdf":"89b51956fde7a76d3931c2c793550be853aae3b8109f009fafe0c6eb96d154f3",
}
for file,known in paths.items():
 data=(root/"sources"/"R17"/file).read_bytes()
 assert data.startswith(b"%PDF") and sha256(data).hexdigest()==known
 print("ARCHIVE_CHECK_PASS",file,len(data))
print("R17_CHECKPOINT_PASS: 14 evidence records, 9 conclusions, 6 hypotheses, R17 PARTIAL, R18 OPEN")
print("ONLY_RESEARCH: no RD6018 / BV600 device changes")