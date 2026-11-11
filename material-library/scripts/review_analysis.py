#!/usr/bin/env python3
"""Apply evidence-based visual corrections without replacing segment identities."""
import argparse
import json
from pathlib import Path
from material_db import connect, now

SCHEMA = '''CREATE TABLE IF NOT EXISTS visual_reviews (
 id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 reviewed_at TEXT NOT NULL, review_version TEXT NOT NULL, reviewer TEXT NOT NULL,
 decision TEXT NOT NULL CHECK(decision IN ('keep','revise','new')),
 reason TEXT NOT NULL, evidence_json TEXT NOT NULL,
 before_json TEXT NOT NULL, after_json TEXT NOT NULL,
 UNIQUE(asset_id,review_version));
 CREATE INDEX IF NOT EXISTS visual_reviews_asset ON visual_reviews(asset_id,reviewed_at);'''
FIELDS = {'source_in_us','source_out_us','content_description','shot_type','composition',
          'lighting','camera_motion','subject_motion','visual_keywords','selling_points',
          'aesthetic_score','score_reason','recommended_use','suggested_playback_rate',
          'confidence','timecode_precision'}

def snapshot(db, aid):
    asset = db.execute('SELECT * FROM assets WHERE id=?',(aid,)).fetchone()
    if asset is None:
        raise ValueError('asset missing')
    return {'asset':dict(asset), 'segments':[dict(r) for r in db.execute(
        'SELECT * FROM segments WHERE asset_id=? ORDER BY id',(aid,))],
        'motion_events':[dict(r) for r in db.execute(
        'SELECT * FROM motion_events WHERE asset_id=? ORDER BY id',(aid,))]}

def apply_review(db, record, version, reviewer='current_codex_visual_review'):
    aid = record['id']; patches = record.get('patches',{})
    if record['decision'] not in ('keep','revise','new'):
        raise ValueError('invalid review decision')
    if patches and record['decision']!='revise':
        raise ValueError('corrections require revise decision')
    if not record.get('observation') or not record.get('evidence'):
        raise ValueError('reason and seen evidence are required')
    for evidence in record['evidence']:
        if not Path(evidence['image_path']).is_file():
            raise ValueError('evidence file missing')
    db.executescript(SCHEMA)
    with db:
        prior = db.execute('SELECT * FROM visual_reviews WHERE asset_id=? AND review_version=?',
                           (aid,version)).fetchone()
        if prior:
            raise ValueError('review version already recorded; use a new version')
        before = snapshot(db, aid); duration=before['asset']['duration_us']
        for sid, patch in patches.items():
            if not patch or set(patch)-FIELDS:
                raise ValueError('unsupported patch fields')
            old = db.execute('SELECT * FROM segments WHERE id=? AND asset_id=?',(int(sid),aid)).fetchone()
            if old is None: raise ValueError('segment does not belong to asset')
            new = dict(old);new.update(patch)
            if duration is None or not 0 <= new['source_in_us'] < new['source_out_us'] <= duration:
                raise ValueError('segment outside source duration')
            fields=list(patch)
            db.execute('UPDATE segments SET '+','.join(f+'=?' for f in fields)+
                       ',analysis_version=? WHERE id=?',(*[patch[f] for f in fields],version,int(sid)))
        stamp=now()
        db.execute('UPDATE assets SET last_analyzed_at=? WHERE id=?',(stamp,aid))
        if record['decision']=='revise':
            db.execute('UPDATE assets SET analysis_version=? WHERE id=?',(version,aid))
        after=snapshot(db,aid)
        db.execute('INSERT INTO visual_reviews(asset_id,reviewed_at,review_version,reviewer,decision,reason,evidence_json,before_json,after_json) VALUES(?,?,?,?,?,?,?,?,?)',
                   (aid,stamp,version,reviewer,record['decision'],record['observation'],
                    json.dumps(record['evidence'],ensure_ascii=False),json.dumps(before,ensure_ascii=False),json.dumps(after,ensure_ascii=False)))
        db.execute("INSERT INTO analysis_runs(asset_id,started_at,finished_at,analysis_version,status) VALUES(?,?,?,?,'completed')",
                   (aid,stamp,stamp,version))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',required=True);p.add_argument('--records',required=True)
    p.add_argument('--version',required=True);a=p.parse_args()
    records=json.loads(Path(a.records).read_text());db=connect(a.db)
    for record in records:apply_review(db,record,a.version)
    print(json.dumps({'reviewed':len(records),'version':a.version}))
