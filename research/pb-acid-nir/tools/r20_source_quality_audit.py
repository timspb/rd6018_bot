"""R20-A01: reproducible bibliographic/arithmetical consistency checks.
No battery I/O, no network, no charge/discharge control.
"""
from pathlib import Path
import math
ROOT=Path(r"<RESEARCH_ROOT>")
report=(ROOT/"24_R20_EVIDENCE_GAP_AUDIT.md").read_text(encoding="utf-8-sig")
assert all(x in report for x in ("Cleland","Catherino","Mankov","Frenander","C92","C96","H60","H61"))
assert math.isclose(46/126*100, 36.5079365079,rel_tol=0,abs_tol=1e-8)
assert math.isclose(47/126*100, 37.3015873016,rel_tol=0,abs_tol=1e-8)
assert round(47/126*100,1)!=36.5
assert round(46/126*100,1)==36.5
# Endpoint: a publication using Li-ion cannot substantiate Pb-acid recovery.
source_classes={
 "Cleland_2000":("lead_acid","immediate_conditioning",False),
 "Mankov_2026":("lead_acid","new_battery_cycle_prevention",False),
 "Catherino_2004":("lead_acid","critical_review",False),
 "Frenander_2026":("lithium_ion","cycle_prevention",False),
}
def is_valid_lead_acid_recovery_claim(data):
 chem,endpoint,has_matched_longitudinal_control=data
 return chem=="lead_acid" and endpoint=="restoration" and has_matched_longitudinal_control
assert not any(is_valid_lead_acid_recovery_claim(v) for v in source_classes.values())
print("R20_AUDIT_PASS Cleland 46/126=36.5%, 47/126=37.3% (publisher count DISPUTED)")
print("R20_AUDIT_PASS 4-source chemistry/endpoint filter: 0 robust controlled long-term recovery claims")
print("No physical experiment, no firmware/device changes")