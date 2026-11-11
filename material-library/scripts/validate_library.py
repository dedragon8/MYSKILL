#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from material_db import connect,DEFAULT_DB
ap=argparse.ArgumentParser();ap.add_argument('--db',default=str(DEFAULT_DB));a=ap.parse_args();db=connect(a.db)
errors=[]
for r in db.execute('SELECT a.*,p.series,p.category_name,p.product_name,p.color_name,p.classification_status FROM assets a JOIN products p ON a.product_id=p.id'):
    if r['availability_status']=='online' and not Path(r['absolute_path']).is_file():errors.append(f"missing online file: {r['id']}")
    if r['analysis_status']=='completed' and (r['duration_us'] is None or r['duration_us']<=0):errors.append(f"completed without duration: {r['id']}")
    if r['classification_status']=='confirmed' and not r['is_generic_broll'] and r['asset_role']!='collection_montage' and (not r['product_name'] or not r['color_name']):errors.append(f"bad classification: {r['id']}")
    if r['asset_role']=='collection_montage' and (r['visual_product_status']!='mixed' or r['is_generic_broll'] or not r['mixed_note']):errors.append(f"invalid all-series collection: {r['id']}")
    if r['is_generic_broll'] and r['asset_role'] not in ('unboxing','other'):errors.append(f"invalid generic role: {r['id']}")
for r in db.execute('SELECT s.*,a.duration_us FROM segments s JOIN assets a ON s.asset_id=a.id'):
    if not (0<=r['source_in_us']<r['source_out_us'] and r['duration_us'] is not None and r['source_out_us']<=r['duration_us']):errors.append(f"bad source range: {r['id']}")
for r in db.execute('SELECT m.*,a.duration_us FROM motion_events m JOIN assets a ON m.asset_id=a.id'):
    if not (0<=r['source_start_us']<r['source_end_us'] and r['duration_us'] is not None and r['source_end_us']<=r['duration_us']):errors.append(f"bad motion range: {r['id']}")
    if r['segment_id'] and not db.execute('SELECT 1 FROM segments WHERE id=? AND asset_id=?',(r['segment_id'],r['asset_id'])).fetchone():errors.append(f"motion segment mismatch: {r['id']}")
for r in db.execute('SELECT * FROM supplemental_assets'):
    if r['availability_status']=='online' and not Path(r['absolute_path']).is_file():errors.append(f"missing online support file: {r['id']}")
    if r['review_status']=='confirmed' and (r['role']=='unclassified' or not r['content_description'] or not r['confirmation_note']):errors.append(f"unconfirmed support classification: {r['id']}")
    if r['role']=='certification' and r['review_status']=='confirmed' and r['product_id'] is None and not r['applies_to_all_products']:errors.append(f"unbound certification: {r['id']}")
    if r['product_id'] is not None and r['applies_to_all_products']:errors.append(f"conflicting support scope: {r['id']}")
errors.extend('foreign key violation: '+str(tuple(r)) for r in db.execute('PRAGMA foreign_key_check'))
for r in db.execute('SELECT o.*,m.duration_us FROM audio_observations o LEFT JOIN audio_metadata m ON m.supplemental_id=o.supplemental_id'):
    if r['duration_us'] is not None and r['source_out_us']>r['duration_us']:errors.append(f"bad audio range: {r['id']}")
integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
if integrity!='ok':errors.append(integrity)
print(json.dumps({'ok':not errors,'errors':errors,'assets':db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]},ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
