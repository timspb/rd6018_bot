"""Rebuildable, public-only Pb research retrieval. Markdown is canonical; no network/device access."""
import argparse, hashlib, json, re, sqlite3, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs' if (ROOT/'docs').is_dir() else ROOT
DB=ROOT/'knowledge_index.sqlite3'
MATRIX='49_S5_STATEMENT_EVIDENCE_MATRIX.md'
SUP='KNOWLEDGE_SUPPLEMENT.md'
# Curated cross-language concept aliases, not inferred evidence or synonyms of diagnoses.
ALIASES={
 'сульфатация':'sulfat* сульфат* pbso4 рекристалл* recrystall*',
 'стратификация':'stratificat* стратификац* расслоен* sg',
 'хлыст':'хлыст* coup fouet cdf',
 'ёмкость':'емкост* capacity c20 qout',
 'импеданс':'impedance импеданс* eis',
 'релаксация':'relaxation релаксац* отстой rest',
 'саморазряд':'саморазряд* self discharge leakage утечк*',
 'дендриты':'дендрит* dendrit* metalliz* металлиз*',
 'коррозия':'корроз* corrosion passivation',
 'зарядоприёмность':'зарядоприемност* dca acceptance',
 'нагрев':'нагрев* thermal температур* temperature',
 'плотность':'плотност* density sg',
 'восстановление':'восстанов* recovery retention',
 'метрология':'метролог* calibration uncertainty калибров*',
 'бережок':'бережок* beregok berezhok zaryd10 beregok7',
 'киберпапа':'киберпап* cyberpapa zaryadakbin',
 'main':'main tail',
 'mix':'mix перемешиван* equalization',
}
EXCLUDE={'CHANGELOG.md','CURRENT_CHECKPOINT.md','HANDOFF_NEW_CHAT.md','RUNBOOK.md','AGENTS.md','OPERATOR_METHODS.md','TELEGRAM_CONNECTOR.md','README.md','ROADMAP.md','CONCLUSIONS.md','KNOWLEDGE_START.md','KNOWLEDGE_SUPPLEMENT.md',MATRIX,'HYPOTHESES.md'}
def norm(s):return s.casefold().replace('ё','е').replace('₄','4').replace('₂','2')
def read(name):return (DOCS/name).read_text(encoding='utf-8-sig')
def documents():
    return sorted(p for p in DOCS.glob('*.md') if p.is_file() and not p.is_symlink())
def fingerprint():
    return hashlib.sha256(json.dumps([('indexer',hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),*[(p.name,hashlib.sha256(p.read_bytes()).hexdigest()) for p in documents()]],ensure_ascii=False).encode()).hexdigest()
def records():
    for name,prefix in [(MATRIX,'C'),(SUP,'S')]:
        for n,line in enumerate(read(name).splitlines(),1):
            if re.match(r'^\| '+prefix+r'\d+ \|',line):
                parts=[x.strip() for x in line.strip('|').split('|')]
                if len(parts)!=6:raise ValueError((name,n,len(parts)))
                id,e,kind,t,body,lim=parts
                yield (id,'claim' if prefix=='C' else 'supplement',name,n,n,body,e,t,kind,lim)
    for n,line in enumerate(read('HYPOTHESES.md').splitlines(),1):
        if re.match(r'^\| H\d+ \|',line):
            id,body,status,lim=[x.strip() for x in line.strip('|').split('|')]
            yield(id,'hypothesis','HYPOTHESES.md',n,n,body,'—','—',status,lim)
    for p in documents():
        if p.name in EXCLUDE:continue
        lines=read(p.name).splitlines()
        heading='';start=1;buf=[]
        def chunk():
            body='\n'.join(buf).strip()
            if body: return (f'{p.stem}:{start}','document',p.name,start,start+len(buf)-1,heading+'\n'+body,'—','—','context','Read source and scope; not independently graded.')
        for n,line in enumerate(lines,1):
            if (line.startswith('#') or sum(map(len,buf))>=2400) and buf:
                r=chunk()
                if r:yield r
                buf=[];start=n
            if line.startswith('#'):heading=line
            if not buf:start=n
            buf.append(line)
        if buf:
            r=chunk()
            if r:yield r
def build():
    tmp=DB.with_suffix('.tmp')
    if tmp.exists():tmp.unlink()
    c=sqlite3.connect(tmp)
    c.executescript('''CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE items(id TEXT PRIMARY KEY, category TEXT, file TEXT, first_line INTEGER,last_line INTEGER, statement TEXT, evidence TEXT,transfer TEXT,kind TEXT,limitation TEXT);
    CREATE VIRTUAL TABLE idx USING fts5(id UNINDEXED,content,tokenize='unicode61');
    CREATE TABLE links(id TEXT REFERENCES items(id), url TEXT, PRIMARY KEY(id,url));''')
    for r in records():
        c.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?)',r)
        c.execute('INSERT INTO idx VALUES(?,?)',(r[0],norm(r[5]+' '+r[9])))
        for url in set(re.findall(r'https?://[^\s<>\]]+',r[5]+' '+r[9])):
            c.execute('INSERT OR IGNORE INTO links VALUES(?,?)',(r[0],url.rstrip('.,;)')))
    c.execute('INSERT INTO meta VALUES(?,?)',('fingerprint',fingerprint()))
    c.commit()
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    counts=dict(c.execute('SELECT category,count(*) FROM items GROUP BY category'))
    expected=set(re.findall(r'(?m)^C(\d+)\s*—',read('CONCLUSIONS.md')))
    actual={r[0][1:] for r in c.execute("SELECT id FROM items WHERE category='claim'")}
    assert actual==expected,('claim coverage',actual^expected)
    for category,prefix in [('claim','C'),('hypothesis','H'),('supplement','S')]:
        ids=[int(r[0][1:]) for r in c.execute('SELECT id FROM items WHERE category=?',(category,))]
        assert sorted(ids)==list(range(1,len(ids)+1)),(category,'gaps')
    c.close();tmp.replace(DB)
    return counts
def connect():
    if not DB.exists():build()
    c=sqlite3.connect(DB.resolve().as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    if c.execute('SELECT value FROM meta WHERE key="fingerprint"').fetchone()[0]!=fingerprint():
        c.close();raise RuntimeError('STALE INDEX: run build')
    return c
def term_expr(q):
    words=re.findall(r'[\w]+\*?',norm(q))
    groups=[]
    for w in words:
        variants=ALIASES.get(w,w)
        # FTS operators generated from safe tokens, not raw user query.
        terms=re.findall(r'[\w]+\*?',variants)
        groups.append('('+' OR '.join('"'+t.rstrip('*')+'"'+('*' if t.endswith('*') else '') for t in terms)+')')
    if not groups:raise ValueError('empty query')
    return ' AND '.join(groups)
def search(c,q,limit=8,category=None):
    if not 1<=limit<=50:raise ValueError('limit 1..50')
    expr=term_expr(q)
    sql='''SELECT i.* FROM idx JOIN items i ON i.id=idx.id WHERE idx MATCH ?'''
    args=[expr]
    if category:sql+=' AND i.category=?';args.append(category)
    sql+=' ORDER BY bm25(idx),i.id LIMIT ?';args.append(limit)
    return [detail(c,r['id']) for r in c.execute(sql,args)]
def detail(c,id):
    r=c.execute('SELECT * FROM items WHERE id=?',(id,)).fetchone()
    if not r:return None
    d=dict(r);d['links']=[x[0] for x in c.execute('SELECT url FROM links WHERE id=? ORDER BY url',(id,))]
    return d
def main():
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('build');sp.add_parser('stats')
    q=sp.add_parser('search');q.add_argument('query');q.add_argument('--limit',type=int,default=8);q.add_argument('--category',choices=['claim','supplement','hypothesis','document'])
    d=sp.add_parser('get');d.add_argument('id')
    a=p.parse_args()
    if a.cmd=='build':out=build()
    else:
        with connect() as c:
            if a.cmd=='stats':out={'counts':dict(c.execute('SELECT category,count(*) FROM items GROUP BY category')),'links':c.execute('SELECT count(*) FROM links').fetchone()[0]}
            elif a.cmd=='get':out=detail(c,a.id)
            else:out=search(c,a.query,a.limit,a.category)
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
