#!/usr/bin/env python3
import argparse,json
from material_db import connect,DEFAULT_DB
ap=argparse.ArgumentParser();ap.add_argument('--db',default=str(DEFAULT_DB));ap.add_argument('--retry-failed',action='store_true');ap.add_argument('--recover',action='store_true');a=ap.parse_args();db=connect(a.db)
with db:
    if a.retry_failed:db.execute("UPDATE assets SET analysis_status='pending' WHERE analysis_status='failed' AND availability_status='online'")
    if a.recover:
        db.execute("UPDATE analysis_runs SET status='interrupted',finished_at=datetime('now') WHERE status='processing'")
        db.execute("UPDATE assets SET analysis_status='pending' WHERE analysis_status='processing'")
counts={r[0]:r[1] for r in db.execute('SELECT analysis_status,COUNT(*) FROM assets GROUP BY analysis_status')}
total=sum(counts.values());done=counts.get('completed',0)
print(json.dumps({'total':total,'completed':done,'pending':counts.get('pending',0),'processing':counts.get('processing',0),'failed':counts.get('failed',0),'stale':counts.get('stale',0),'percent':round(100*done/total,1) if total else 0,'current':[dict(r) for r in db.execute("SELECT id,relative_path FROM assets WHERE analysis_status='processing'")],'offline':db.execute("SELECT COUNT(*) FROM assets WHERE availability_status='offline'").fetchone()[0]},ensure_ascii=False,indent=2))
