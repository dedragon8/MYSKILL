#!/usr/bin/env python3
"""Commit Codex-reviewed contact-sheet annotations, one asset per transaction."""
import argparse,json
from pathlib import Path
from material_db import connect,start_run,finish_run,VERSION

def main():
 ap=argparse.ArgumentParser();ap.add_argument('annotations');ap.add_argument('--db');a=ap.parse_args()
 db=connect(a.db) if a.db else connect(); rows=json.loads(Path(a.annotations).read_text())
 for row in rows:
  aid=row['id'];asset=db.execute('SELECT duration_us FROM assets WHERE id=?',(aid,)).fetchone()
  if not asset or not asset[0]:raise ValueError(f'missing duration: {aid}')
  duration=asset[0];segments=[]
  for s in row['segments']:
   begin=round(s['in']*1_000_000);end=min(duration,round(s.get('out',duration/1_000_000)*1_000_000))
   segments.append({'source_in_us':begin,'source_out_us':end,'content_description':s['description'],
    'shot_type':s.get('shot'),'composition':s.get('composition'),'lighting':s.get('lighting'),
    'camera_motion':s.get('camera_motion'),'subject_motion':s.get('subject_motion'),
    'visual_keywords':s.get('keywords'),'selling_points':s.get('selling_points'),
    'aesthetic_score':s.get('score'),'score_reason':s.get('reason'),
    'recommended_use':s.get('use'),'suggested_playback_rate':s.get('playback_rate'),
    'confidence':s.get('confidence',0.65),'analysis_version':VERSION,'timecode_precision':'coarse'})
  run=start_run(db,aid)
  try:
   finish_run(db,aid,run,'completed',segments=segments)
   with db:db.execute('UPDATE assets SET visual_product_status=? WHERE id=?',(row['product_status'],aid))
  except Exception as e:
   finish_run(db,aid,run,'failed',str(e));raise
 print(f'imported {len(rows)} visual reviews')
if __name__=='__main__':main()
