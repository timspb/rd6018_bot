"""Offline index contract checks, not scientific verification."""
import knowledge_index as k
from pathlib import Path
import sqlite3,time
def main():
    k.build()
    t=time.perf_counter()
    with k.connect() as c:
        counts=dict(c.execute('SELECT category,count(*) FROM items GROUP BY category'))
        assert counts['claim']==192 and counts['hypothesis']==93 and counts['supplement']==18
        tests=[('хлыст','S013','supplement'),('бережок','S008','supplement'),('сульфатация','C01','claim'),('импеданс','C16','claim')]
        for q,id,cat in tests:
            hits=k.search(c,q,15,cat); assert id in [h['id'] for h in hits],(q,id)
        for q in ['стратификация','релаксация','дендриты','main','mix','коррозия','метрология','ёмкость','нагрев','киберпапа','coup de fouet','capacity']:
            assert k.search(c,q,8),q
        for id in ['C01','C192','H01','H93','S004','S005','S013','S015','S018']:
            x=k.detail(c,id); assert x and x['limitation']
            assert x['first_line']<=x['last_line']
            assert (k.DOCS/x['file']).is_file()
            assert id in k.read(x['file']).splitlines()[x['first_line']-1]
        assert 'not direct MAIN/MIX termination' in k.detail(c,'S013')['limitation']
        assert 'Exclude from lead-acid' in k.detail(c,'S005')['limitation']
        assert k.detail(c,'missing') is None
        assert not k.search(c,'zzzznotabatterytermzzzz',5)
        try:c.execute("DELETE FROM items")
        except sqlite3.OperationalError:pass
        else:raise AssertionError('read-only failed')
        assert not c.execute("SELECT count(*) FROM items WHERE file LIKE '%private%' OR file LIKE '%.jsonl%'").fetchone()[0]
        print('KB_CHECKS_PASS',counts,'16 queries, exact IDs, source lines, negative query, read-only',round(time.perf_counter()-t,3),'s')
if __name__=='__main__':main()
