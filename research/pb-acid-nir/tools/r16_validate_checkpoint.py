"""Validate R16 local evidence and references without touching user devices."""
from pathlib import Path
from hashlib import sha256

ROOT=Path(r"<RESEARCH_ROOT>")
must_exist=[
    "19_R16_ELECTROLYTE_ALLOYS.md",
    "sources/R16/NBS_1939_Craig_Vinal_PbSO4_solubility.pdf",
    "sources/R16/NBS_1934_Vinal_Craig_H2SO4_resistivity.pdf",
    "tools/r16_archive_nist.py",
    "tools/r16_nbs_solubility_analysis.py",
]
for name in must_exist:
    file=ROOT/name
    assert file.exists() and file.stat().st_size>100, f"Missing or empty: {name}"
    print("FILE_PASS",name,file.stat().st_size)
roadmap=(ROOT/"ROADMAP.md").read_text(encoding="utf-8")
assert "| R16 | Электролит и легирование | P1 | PARTIAL | 19_R16_ELECTROLYTE_ALLOYS |" in roadmap
assert "| R17 | Углерод и активные массы | P1 | OPEN |" in roadmap
report=(ROOT/"19_R16_ELECTROLYTE_ALLOYS.md").read_text(encoding="utf-8")
assert all(x in report for x in ("S01.", "S11.", "C59", "C66", "H38", "H42"))
summary=(ROOT/"CURRENT_CHECKPOINT.md").read_text(encoding="utf-8")
assert "R16 PARTIAL:" in summary
cons=(ROOT/"CONCLUSIONS.md").read_text(encoding="utf-8")
hypo=(ROOT/"HYPOTHESES.md").read_text(encoding="utf-8")
for i in range(59,67):
    assert f"C{i} " in cons, f"Missing conclusion C{i}"
for i in range(38,43):
    assert f"H{i} " in hypo, f"Missing hypothesis H{i}"
files={
"NBS_1939_Craig_Vinal_PbSO4_solubility.pdf":"ea372944c18a41410f2f09c1794823fa8550105af08a5cf54762412d30f15370",
"NBS_1934_Vinal_Craig_H2SO4_resistivity.pdf":"33eeb9469a1fc44a92b71ef2797bd1aee2307e4b9d05192d9e384ff0ee10d83b",
}
for fn,h in files.items():
    data=(ROOT/"sources"/"R16"/fn).read_bytes()
    assert data.startswith(b"%PDF")
    assert sha256(data).hexdigest()==h
print("R16_CHECKPOINT_PASS: 2 primary PDFs hashes, report, sources, 8 conclusions, 5 hypotheses, roadmap; R17 open")