"""Build statement-level evidence/transfer index from explicit reviewed assignments.
No model fitting, device access or automatic upgrades of scientific evidence."""
from pathlib import Path
import re,collections
R=Path(__file__).resolve().parents[1]
def expand(s):
 out=[]
 for t in s.split():
  a,*b=t.split('-');out.extend(range(int(a),int(b[0])+1) if b else [int(a)])
 return out
# Each ID assigned once. E1 restricted to directly verified archive facts,
# E2 limited primary observations or secondary analyses of them, E3 limited
# source access/specification/synthesis. A is a separate nonempirical kind,
# not a new E grade; N is scoped negative search or exclusion.
groups=[
 ('E1','archive','118 134 135 176 177 178'),
 ('E2','observation','3 13 14 17 21 23 25 28 36 37 40 41 43 54 58 59 61 62 68 69 79 80 81 84 85 86 87 88 91 98 99 102 104 105 106 107 108 109 110 111 112 114 115 119 120 121 122 124 125 126 127 128 129 130 131 132 133 136 138 139 140 141 143 144 145 146 147 148 149 152 153 154 155 156 158 159 160 162 163 164 166 167 168 169 170 172 173 174 179 180 181 183 184 185 186 187 188 189 191 192'),
 ('E2','discrepancy','82 123 137 182'),
 ('E3','discrepancy','93'),
 ('E3','observation','6 48 53 56 70 71 73 78 92 94 96 113 116 142 157 161'),
 ('E3','specification','12 31 45 55 90 97 150 151 175'),
 ('E3','synthesis','1 2 4 7 8 9 10 16 19 20 22 24 26 29 30 32 33 34 38 39 42 44 46 47 49 50 51 52 57 60 63 64 65 66 67 72 74 75 76 83'),
 ('—','analytic','5 11 15 18 27 35 77 100 101 103 117 165 171'),
 ('—','search_limit','89'),
 ('—','excluded','95'),
 ('E2','model_not_measurement','190'),
]
g={}
for grade,kind,ids in groups:
 for i in expand(ids):
  assert i not in g,('duplicate grade',i)
  g[i]=(grade,kind)
assert set(g)==set(range(1,193)),('missing/extra',set(range(1,193))-set(g),set(g)-set(range(1,193)))
# Target: existing 12V automotive Ca/Ca/EFB/AGM, no exact model-specific
# independent validation claimed. T2 similar construction/measurement;
# T3 lab cell/stationary or otherwise materially different;
# T4 mixed/unknown scope, not a licence to transfer.
transfers=[
 ('T2','3 36 37 43 45 46 49 50 51 52 57 79 90 102 136 139 140 145 148 168 169 170 175 180 181 183'),
 ('T3','13 14 17 21 23 25 28 40 41 48 54 58 59 61 62 68 69 70 71 73 78 80 81 82 84 85 86 87 88 91 92 93 94 97 98 99 104 105 106 107 108 109 110 111 112 113 114 115 116 118 119 120 121 122 123 124 125 126 127 128 129 130 131 132 133 134 135 137 138 141 142 143 144 146 147 149 150 151 152 153 154 155 156 157 158 159 160 161 162 163 164 166 167 172 173 174 176 177 178 179 182 184 185 186 187 188 189 190 191 192'),
 ('T4','1 2 4 6 7 8 9 10 12 16 19 20 22 24 26 29 30 31 32 33 34 38 39 42 44 47 53 55 56 60 63 64 65 66 67 72 74 75 76 83 89 96'),
 ('—','5 11 15 18 27 35 77 95 100 101 103 117 165 171'),
]
t={}
for code,ids in transfers:
 for i in expand(ids):
  assert i not in t,('duplicate transfer',i)
  t[i]=code
assert set(t)==set(g),('transfer missing/extra',set(g)-set(t),set(t)-set(g))
# Source-specific corrections and unresolved conflicts must accompany earlier rows.
overrides={
 6:'R04-D-Q OPEN; risk plausible/observed association, not verified conductive metallic path or safe initial current.',
 31:'R11 and report44: corrected IEC 60095-1 scope; exact complete protocol not obtained.',
 40:'R13 and report43: external shunt EFB70Ah differs from internally degraded SLI35Ah; no direct bridge resistance.',
 41:'Report43 corrects specimen attribution; no universal sensitivity or exclusion threshold.',
 48:'Abstract only; no measured prevalence or diagnostic threshold.',
 59:'NBS Table5 smoothed/interpolated data, not independent point replicates; equilibrium total dissolved material.',
 84:'Same Karami evidence as C91; do not count twice.',
 91:'Same Karami evidence as C84; no new cohort.',
 95:'Excluded chemistry; not admissible lead-acid evidence.',
 107:'Wagner/Sauer and Bopp Talhof cohort overlaps.',
 114:'R06 and report45: decoding verified; no external classifier or exact timestamp.',
 119:'Report45 resolves author-intended mOhm, not instrument calibration; no re-fit.',
 124:'Report45: 0.15 mOhm author-intended; zHit not linearity or calibration.',
 126:'After-cycling residual discharge, never fully charged C20.',
 127:'Same four cells as C118–133; no independent cohort.',
 128:'Same four cells as C118–133; no independent cohort.',
 129:'Same four cells as C118–133; no independent cohort.',
 130:'Same four cells; identical quasi-rest U not a C20 label.',
 131:'Same four cells; no independent cohort.',
 132:'Same four cells; exploratory subset, not replication.',
 133:'Same four cells; frozen result, do not fit again.',
 134:'Telemetry and GITT not acquired; repair/censoring are not C20 or mechanism.',
 137:'Invalid voltage excluded rather than divide by ten.',
 140:'Lot association, not independent causal effect.',
 147:'Sequential same bank; direct water weighing not confirmed.',
 155:'Denominator estimated from nominal mean I×time, not measured Ah.',
 157:'150 observed, 1296 projected; not lifetime measurement.',
 158:'Scheduled 1000-cycle cap vs later305; no measured early failure at1000.',
 161:'72% denominator unverified; no count inferred.',
 163:'Factory prototype, not restoration; model-based gas partition.',
 166:'Screened sample has no eligible hour; not absence of self-discharge.',
 170:'Erratum supersedes earlier EFB/SLI attribution; gray spots not phase/conductance proof.',
 172:'30 duplicate plot triples; label origin not verified, reject external training/test.',
 175:'Part8 auxiliary/backup scope distinct, full corrected procedure not verified.',
 176:'Exact numeric decode only; excludes text fields, not instrument validation.',
 177:'Aggregate count agreement, not individual mask identity; author mOhm not calibrated.',
 178:'Date and phase join only, no shared time axis.',
 181:'Separate fresh ageing baseline; no blind SOH or held-out specimen.',
 182:'Contradictory denominators retained; no life fit.',
 184:'27.47% residual in middle charge; inferred reaction heat, not directly partitioned.',
 188:'Approximate figure reading; current ceiling/order and nominal SOC confounding.',
 190:'Simulation, not 18 independent experiments; postmortem disagreement retained.',
 192:'AFM field disappearance, not chemical conversion; proposed detachment not proven.'
}
source=(R/'CONCLUSIONS.md').read_text(encoding='utf-8-sig')
rows={}
for l in source.splitlines():
 m=re.match(r'^C(\d+)\s*—\s*(.+)$',l)
 if m:
  i=int(m[1]);assert i not in rows;i0=m[2];rows[i]=i0
assert set(rows)==set(g)
def esc(x):return x.replace('|',r'\|')
out=['# S5 — statement-level evidence and transfer index',
 '2026-11-29. Reviewed assignments C01–C192. Canon E1–E4/H unchanged. E1 here applies to verifiable archive facts, never a battery-wide efficacy claim; E2 limited primary observation/analysis; E3 synthesis/specification/limited access. Analytic/search/excluded entries have no empirical E grade. T refers to transfer toward an unspecified 12V automotive Ca/Ca/EFB/AGM target; no T1 or operational authorization inferred. A dash means not applicable, not a low score. Each row retains the full ledger statement including source references and conditions. This is a documentary reclassification, not a fresh reading of every original. Later errata override older interpretations. No new conclusions or physical experiments.',
 '| ID | E | Kind | T | Statement and source | Additional restriction / correction |','|---|---|---|---|---|---|']
for i in sorted(rows):
 grade,kind=g[i]
 out.append('| C%02d | %s | %s | %s | %s | %s |'%(i,grade,kind,t[i],esc(rows[i]),esc(overrides.get(i,{'observation':'Bounded to stated sample, method and endpoint; no universal setting.','synthesis':'Use as methodological boundary, not quantified target effect.','archive':'Archive verification only, not physical accuracy.','specification':'Only applicable model/edition/mode; no generic setting.','analytic':'Within stated assumptions; not a measured battery result.','discrepancy':'Retain conflicting values; no silent reconciliation.','model_not_measurement':'Model prediction only.','search_limit':'Search scope only; absence of evidence is not proof of absence.','excluded':'Outside lead-acid scope.'}[kind]))))
out += ['', '## Coverage', str(dict(collections.Counter(v[0] for v in g.values()))), str(dict(collections.Counter(t.values()))), 'No duplicate IDs, no missing rows. Grades do not represent independent sources or number of replicated findings.']
(R/'49_S5_STATEMENT_EVIDENCE_MATRIX.md').write_text('\n'.join(out)+'\n',encoding='utf-8')
print('S5_MATRIX_PASS',len(rows),dict(collections.Counter(v[0] for v in g.values())),dict(collections.Counter(t.values())))
