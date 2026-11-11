#!/usr/bin/env python3
"""SQLite storage and CLI for the Qianchuan material library. Times are source microseconds."""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path.home() / '.codex/qianchuan-data/materials.db'
VERSION = '1.0'

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, series TEXT NOT NULL, category_name TEXT NOT NULL,
 product_name TEXT, color_name TEXT, relative_folder_path TEXT NOT NULL UNIQUE,
 classification_status TEXT NOT NULL CHECK(classification_status IN ('confirmed','pending'))
);
CREATE INDEX IF NOT EXISTS products_match ON products(series,product_name,color_name,category_name);
CREATE TABLE IF NOT EXISTS assets (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 filename TEXT NOT NULL, absolute_path TEXT NOT NULL UNIQUE, relative_path TEXT NOT NULL UNIQUE,
 file_size INTEGER, modified_time INTEGER, file_fingerprint TEXT,
 duration_us INTEGER, fps_num INTEGER, fps_den INTEGER, width INTEGER, height INTEGER,
 codec TEXT, has_audio INTEGER, chatcut_project_id TEXT, chatcut_asset_id TEXT,
 availability_status TEXT NOT NULL DEFAULT 'online' CHECK(availability_status IN ('online','offline')),
 analysis_status TEXT NOT NULL DEFAULT 'pending' CHECK(analysis_status IN ('pending','processing','completed','failed','stale')),
 visual_product_status TEXT NOT NULL DEFAULT 'unverified' CHECK(visual_product_status IN ('unverified','matches','mismatch','mixed')),
 last_analyzed_at TEXT, analysis_version TEXT
);
CREATE INDEX IF NOT EXISTS assets_fingerprint ON assets(file_fingerprint);
CREATE INDEX IF NOT EXISTS assets_status ON assets(analysis_status,availability_status);
CREATE INDEX IF NOT EXISTS products_by_model ON products(product_name,color_name,series);
CREATE TABLE IF NOT EXISTS segments (
 id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 source_in_us INTEGER NOT NULL CHECK(source_in_us>=0),
 source_out_us INTEGER NOT NULL CHECK(source_out_us>source_in_us),
 content_description TEXT NOT NULL, shot_type TEXT, composition TEXT, lighting TEXT,
 camera_motion TEXT, subject_motion TEXT, visual_keywords TEXT, selling_points TEXT,
 aesthetic_score REAL CHECK(aesthetic_score BETWEEN 0 AND 10), score_reason TEXT,
 recommended_use TEXT, suggested_playback_rate REAL CHECK(suggested_playback_rate>0),
 confidence REAL CHECK(confidence BETWEEN 0 AND 1), analysis_version TEXT NOT NULL,
 timecode_precision TEXT NOT NULL DEFAULT 'coarse' CHECK(timecode_precision IN ('coarse','frame_verified')),
 UNIQUE(asset_id,source_in_us,source_out_us,analysis_version)
);
CREATE INDEX IF NOT EXISTS segments_asset ON segments(asset_id);
CREATE TABLE IF NOT EXISTS analysis_runs (
 id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id), started_at TEXT NOT NULL,
 finished_at TEXT, analysis_version TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('processing','completed','failed','interrupted')),
 error_message TEXT, retry_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS runs_asset ON analysis_runs(asset_id,started_at);
CREATE TABLE IF NOT EXISTS contact_sheets (
 id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 image_path TEXT NOT NULL, source_times_us TEXT NOT NULL, created_at TEXT NOT NULL,
 analysis_version TEXT NOT NULL, UNIQUE(asset_id,analysis_version)
);
CREATE TABLE IF NOT EXISTS feedback (
 id INTEGER PRIMARY KEY, asset_id INTEGER REFERENCES assets(id), segment_id INTEGER REFERENCES segments(id) ON DELETE SET NULL,
 created_at TEXT NOT NULL, project_id TEXT, source_in_us INTEGER, source_out_us INTEGER,
 action TEXT NOT NULL CHECK(action IN ('prefer','avoid','replace','trim','rate','note')),
 comment TEXT NOT NULL, user_confirmed INTEGER NOT NULL DEFAULT 1,
 applicable_scope TEXT NOT NULL DEFAULT 'asset', reusable_rule TEXT,
 CHECK(source_in_us IS NULL OR source_in_us>=0),
 CHECK(source_out_us IS NULL OR (source_in_us IS NOT NULL AND source_out_us>source_in_us))
);
CREATE INDEX IF NOT EXISTS feedback_lookup ON feedback(asset_id,segment_id,action);
CREATE TABLE IF NOT EXISTS supplemental_assets (
 id INTEGER PRIMARY KEY, root_path TEXT NOT NULL, relative_path TEXT NOT NULL,
 absolute_path TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
 media_type TEXT NOT NULL CHECK(media_type IN ('image','document','audio')),
 role TEXT NOT NULL DEFAULT 'unclassified' CHECK(role IN ('unclassified','unboxing','certification','sound_effect','other')),
 product_id INTEGER REFERENCES products(id), applies_to_all_products INTEGER NOT NULL DEFAULT 0
 CHECK(applies_to_all_products IN (0,1)), file_size INTEGER, modified_time INTEGER,
 file_fingerprint TEXT, availability_status TEXT NOT NULL DEFAULT 'online'
 CHECK(availability_status IN ('online','offline')),
 review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('pending','confirmed')),
 content_description TEXT, keywords TEXT, placement_keywords TEXT, confirmation_note TEXT,
 UNIQUE(root_path,relative_path)
);
CREATE INDEX IF NOT EXISTS supplemental_scope ON supplemental_assets(product_id,role,review_status,availability_status);
CREATE INDEX IF NOT EXISTS supplemental_root ON supplemental_assets(root_path,relative_path);
CREATE TABLE IF NOT EXISTS motion_events (
 id INTEGER PRIMARY KEY, asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 segment_id INTEGER REFERENCES segments(id) ON DELETE SET NULL,
 source_start_us INTEGER NOT NULL CHECK(source_start_us>=0),
 source_end_us INTEGER NOT NULL CHECK(source_end_us>source_start_us),
 motion_description TEXT NOT NULL, pattern TEXT NOT NULL CHECK(pattern IN ('single','repeated','continuous')),
 cycle_index INTEGER CHECK(cycle_index IS NULL OR cycle_index>0),
 boundary_precision TEXT NOT NULL CHECK(boundary_precision IN ('coarse','frame_verified')),
 evidence_note TEXT, UNIQUE(asset_id,source_start_us,source_end_us,pattern,cycle_index)
);
CREATE INDEX IF NOT EXISTS motion_asset ON motion_events(asset_id,source_start_us);
CREATE TABLE IF NOT EXISTS asset_product_mentions (
 asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 product_id INTEGER NOT NULL REFERENCES products(id),
 evidence_note TEXT NOT NULL, PRIMARY KEY(asset_id,product_id)
);
CREATE INDEX IF NOT EXISTS asset_mentions_product ON asset_product_mentions(product_id,asset_id);
CREATE TABLE IF NOT EXISTS audio_metadata (
 supplemental_id INTEGER PRIMARY KEY REFERENCES supplemental_assets(id) ON DELETE CASCADE,
 source_fingerprint TEXT NOT NULL, duration_us INTEGER CHECK(duration_us>0),
 sample_rate INTEGER CHECK(sample_rate>0), channels INTEGER CHECK(channels>0), codec TEXT,
 file_sha256 TEXT, decoded_pcm_sha256 TEXT, peak_dbfs REAL, rms_dbfs REAL,
 technical_json TEXT NOT NULL, measured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audio_pcm_identity ON audio_metadata(decoded_pcm_sha256);
CREATE TABLE IF NOT EXISTS audio_observations (
 id INTEGER PRIMARY KEY,
 supplemental_id INTEGER NOT NULL REFERENCES supplemental_assets(id) ON DELETE CASCADE,
 source_in_us INTEGER NOT NULL CHECK(source_in_us>=0),
 source_out_us INTEGER NOT NULL CHECK(source_out_us>source_in_us),
 description TEXT NOT NULL, model_id TEXT NOT NULL, model_revision TEXT NOT NULL,
 analysis_label TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
 prompt_sha256 TEXT NOT NULL, evidence_path TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(supplemental_id,model_revision,analysis_label,source_in_us,source_out_us,prompt_sha256)
);
CREATE INDEX IF NOT EXISTS audio_observations_lookup ON audio_observations(supplemental_id,model_revision);
'''

def connect(path=DEFAULT_DB):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=5000')
    db.executescript(SCHEMA)
    if 'visual_product_status' not in [r[1] for r in db.execute('PRAGMA table_info(assets)')]:
        db.execute("ALTER TABLE assets ADD COLUMN visual_product_status TEXT NOT NULL DEFAULT 'unverified'")
    cols = [r[1] for r in db.execute('PRAGMA table_info(assets)')]
    if 'asset_role' not in cols:
        db.execute("ALTER TABLE assets ADD COLUMN asset_role TEXT NOT NULL DEFAULT 'product_footage'")
    if 'mixed_note' not in cols:
        db.execute('ALTER TABLE assets ADD COLUMN mixed_note TEXT')
    if 'applies_to_all_products' not in [r[1] for r in db.execute('PRAGMA table_info(supplemental_assets)')]:
        db.execute('ALTER TABLE supplemental_assets ADD COLUMN applies_to_all_products INTEGER NOT NULL DEFAULT 0')
    if 'supplemental_id' not in [r[1] for r in db.execute('PRAGMA table_info(feedback)')]:
        db.execute('ALTER TABLE feedback ADD COLUMN supplemental_id INTEGER REFERENCES supplemental_assets(id)')
    if 'is_generic_broll' not in [r[1] for r in db.execute('PRAGMA table_info(assets)')]:
        db.execute('ALTER TABLE assets ADD COLUMN is_generic_broll INTEGER NOT NULL DEFAULT 0')
    db.execute('CREATE INDEX IF NOT EXISTS feedback_support ON feedback(supplemental_id,action)')
    db.execute('CREATE INDEX IF NOT EXISTS assets_product_scope ON assets(product_id,availability_status,analysis_status,visual_product_status)')
    db.execute('CREATE INDEX IF NOT EXISTS assets_generic_scope ON assets(is_generic_broll,asset_role,analysis_status,availability_status)')
    return db

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def start_run(db, asset_id):
    with db:
        db.execute("UPDATE assets SET analysis_status='processing' WHERE id=?", (asset_id,))
        retry = db.execute('SELECT COUNT(*) FROM analysis_runs WHERE asset_id=? AND status=?', (asset_id,'failed')).fetchone()[0]
        cur = db.execute('INSERT INTO analysis_runs(asset_id,started_at,analysis_version,status,retry_count) VALUES(?,?,?,?,?)', (asset_id,now(),VERSION,'processing',retry))
    return cur.lastrowid

def finish_run(db, asset_id, run_id, status, error=None, segments=None):
    if status not in ('completed','failed'): raise ValueError('invalid status')
    with db:
        if segments is not None:
            duration = db.execute('SELECT duration_us FROM assets WHERE id=?',(asset_id,)).fetchone()[0]
            if duration is None: raise ValueError('duration unknown')
            db.execute('DELETE FROM motion_events WHERE asset_id=?',(asset_id,))
            db.execute('DELETE FROM segments WHERE asset_id=?',(asset_id,))
            fields = ('source_in_us','source_out_us','content_description','shot_type','composition','lighting','camera_motion','subject_motion','visual_keywords','selling_points','aesthetic_score','score_reason','recommended_use','suggested_playback_rate','confidence','analysis_version','timecode_precision')
            for s in segments:
                if not (0 <= s['source_in_us'] < s['source_out_us'] <= duration): raise ValueError('segment outside source duration')
                values = [s.get(f) for f in fields]
                values[fields.index('analysis_version')] = s.get('analysis_version',VERSION)
                values[fields.index('timecode_precision')] = s.get('timecode_precision','coarse')
                db.execute('INSERT INTO segments(asset_id,'+','.join(fields)+') VALUES('+','.join('?' for _ in range(len(fields)+1))+')',(asset_id,*values))
        db.execute('UPDATE analysis_runs SET finished_at=?,status=?,error_message=? WHERE id=? AND asset_id=?',(now(),status,error,run_id,asset_id))
        db.execute('UPDATE assets SET analysis_status=?,last_analyzed_at=?,analysis_version=? WHERE id=?',(status,now() if status=='completed' else None,VERSION if status=='completed' else None,asset_id))

def search(db, series=None, product=None, color=None, category=None, text=None, min_score=None,
           allow_mixed=False, limit=30, product_prefix=None, series_prefix=None, mixed_only=False, role=None):
    if not any((series, product, color, category, product_prefix, series_prefix)):
        raise ValueError('必须指定用户授权的系列、产品或颜色范围；不执行全库读取')
    if mixed_only and not allow_mixed:
        raise ValueError('只查混合素材需要显式 --allow-mixed')
    if not 1 <= limit <= 500:
        raise ValueError('limit must be 1..500')
    status = 'a.visual_product_status="mixed"' if mixed_only else ('a.visual_product_status IN ("matches","mixed")' if allow_mixed else 'a.visual_product_status="matches"')
    cond=['a.product_id=p.id','s.asset_id=a.id','a.availability_status="online"','a.analysis_status="completed"',"p.classification_status='confirmed'","a.asset_role NOT IN ('unclassified','collection_montage')",status]; args=[]
    if role:cond.append('a.asset_role=?');args.append(role)
    scopes=[];scope_args=[]
    for col,val in [('series',series),('product_name',product),('color_name',color),('category_name',category)]:
        if val: scopes.append('{alias}.'+col+'=?'); scope_args.append(val)
    if product_prefix:
        scopes.append('{alias}.product_name LIKE ? ESCAPE "\\"'); scope_args.append(escape_like(product_prefix)+'%')
    if series_prefix:
        scopes.append('{alias}.series LIKE ? ESCAPE "\\"'); scope_args.append(escape_like(series_prefix)+'%')
    direct=' AND '.join(x.format(alias='p') for x in scopes)
    if allow_mixed:
        mentioned=' AND '.join(x.format(alias='p2') for x in scopes)
        cond.append('(('+direct+') OR (a.visual_product_status="mixed" AND EXISTS (SELECT 1 FROM asset_product_mentions pm JOIN products p2 ON p2.id=pm.product_id WHERE pm.asset_id=a.id AND '+mentioned+')))')
        args += scope_args*2
    else:
        cond.append('('+direct+')');args += scope_args
    if min_score is not None: cond.append('s.aesthetic_score>=?');args.append(min_score)
    if text:
        cond.append("(s.content_description LIKE ? OR s.visual_keywords LIKE ? OR s.selling_points LIKE ? OR s.composition LIKE ? OR s.subject_motion LIKE ? OR s.recommended_use LIKE ?)")
        args += ['%'+text+'%']*6
    product_index='products_by_model' if (product or product_prefix) else 'products_match'
    query='''SELECT s.*,a.absolute_path,a.relative_path,a.duration_us,a.chatcut_project_id,a.chatcut_asset_id,
      a.visual_product_status,a.asset_role,a.mixed_note,
      p.series,p.category_name,p.product_name,p.color_name,
      COALESCE((SELECT SUM(CASE f.action WHEN 'prefer' THEN 1 WHEN 'avoid' THEN -2 WHEN 'replace' THEN -2 ELSE 0 END)
        FROM feedback f WHERE f.segment_id=s.id OR (f.segment_id IS NULL AND f.asset_id=a.id)),0) AS feedback_weight
      FROM products p INDEXED BY '''+product_index+''' CROSS JOIN assets a INDEXED BY assets_product_scope
      CROSS JOIN segments s INDEXED BY segments_asset
      WHERE '''+' AND '.join(cond)+''' ORDER BY feedback_weight DESC,s.aesthetic_score DESC LIMIT ?'''
    return [dict(r) for r in db.execute(query,(*args,limit))]

def escape_like(value):
    return value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')

def list_scopes(db):
    return [dict(r) for r in db.execute('''SELECT p.id,p.series,p.category_name,p.product_name,p.color_name,
      COUNT(a.id) AS video_count FROM products p LEFT JOIN assets a ON a.product_id=p.id
      AND a.availability_status='online' AND a.analysis_status='completed'
      GROUP BY p.id ORDER BY p.series,p.product_name,p.color_name''')]

def search_generic(db, role='unboxing', text=None, limit=30):
    if role not in ('unboxing','other'):raise ValueError('generic search requires unboxing or other role')
    if not 1<=limit<=500:raise ValueError('limit must be 1..500')
    cond=["a.is_generic_broll=1","a.asset_role=?","a.analysis_status='completed'","a.availability_status='online'","s.asset_id=a.id"]
    args=[role]
    if text:
        # Descriptions and use notes may say “没有掀盖”; only positive action tags
        # and observed subject motion can match an action query.
        cond.append('(s.visual_keywords LIKE ? OR s.subject_motion LIKE ?)')
        args+=['%'+text+'%']*2
    query='''SELECT s.*,a.absolute_path,a.relative_path,a.duration_us,a.chatcut_project_id,a.chatcut_asset_id,
      a.asset_role,a.is_generic_broll,
      COALESCE((SELECT SUM(CASE f.action WHEN 'prefer' THEN 1 WHEN 'avoid' THEN -2 WHEN 'replace' THEN -2 ELSE 0 END)
        FROM feedback f WHERE f.segment_id=s.id OR (f.segment_id IS NULL AND f.asset_id=a.id)),0) AS feedback_weight
      FROM assets a INDEXED BY assets_generic_scope CROSS JOIN segments s INDEXED BY segments_asset
      WHERE '''+' AND '.join(cond)+' ORDER BY feedback_weight DESC,s.aesthetic_score DESC LIMIT ?'
    return [dict(r) for r in db.execute(query,(*args,limit))]

def search_collections(db, all_series=False, text=None, limit=30):
    """Only explicitly requested all-series mixed montages; never product-scoped."""
    if not all_series:
        raise ValueError('合集仅用于全系列混合展示，需要显式 --all-series')
    if not 1<=limit<=500:
        raise ValueError('limit must be 1..500')
    cond=["a.is_generic_broll=0", "a.asset_role='collection_montage'",
          "a.visual_product_status='mixed'", "a.analysis_status='completed'",
          "a.availability_status='online'", 's.asset_id=a.id']
    args=[]
    if text:
        cond.append('(s.content_description LIKE ? OR s.visual_keywords LIKE ? OR s.recommended_use LIKE ?)')
        args+=['%'+text+'%']*3
    query='''SELECT s.*,a.absolute_path,a.relative_path,a.duration_us,
      a.chatcut_project_id,a.chatcut_asset_id,a.asset_role,a.visual_product_status,a.mixed_note,
      'all_series_mixed_only' AS usage_scope,
      COALESCE((SELECT SUM(CASE f.action WHEN 'prefer' THEN 1 WHEN 'avoid' THEN -2 WHEN 'replace' THEN -2 ELSE 0 END)
        FROM feedback f WHERE f.segment_id=s.id OR (f.segment_id IS NULL AND f.asset_id=a.id)),0) AS feedback_weight
      FROM assets a INDEXED BY assets_generic_scope CROSS JOIN segments s INDEXED BY segments_asset
      WHERE '''+' AND '.join(cond)+' ORDER BY feedback_weight DESC,s.aesthetic_score DESC LIMIT ?'
    return [dict(r) for r in db.execute(query,(*args,limit))]

def support_search(db, role=None, series=None, product=None, color=None, category=None,
                   product_prefix=None, series_prefix=None, text=None, limit=30):
    if not any((series,product,color,category,product_prefix,series_prefix)) and role!='sound_effect':
        raise ValueError('必须指定系列或产品范围')
    if not 1 <= limit <= 500:raise ValueError('limit must be 1..500')
    cond=["x.review_status='confirmed'","x.availability_status='online'"]; args=[]
    if role: cond.append('x.role=?');args.append(role)
    scope=[];scope_args=[]
    for col,val in [('p.series',series),('p.product_name',product),('p.color_name',color),('p.category_name',category)]:
        if val:scope.append(col+'=?');scope_args.append(val)
    if product_prefix:scope.append('p.product_name LIKE ? ESCAPE "\\"');scope_args.append(escape_like(product_prefix)+'%')
    if series_prefix:scope.append('p.series LIKE ? ESCAPE "\\"');scope_args.append(escape_like(series_prefix)+'%')
    if scope:
        cond.append('(x.applies_to_all_products=1 OR ('+' AND '.join(scope)+'))')
        args+=scope_args
    if text:
        cond.append('(x.content_description LIKE ? OR x.keywords LIKE ? OR x.placement_keywords LIKE ?)')
        args += ['%'+text+'%']*3
    return [dict(r) for r in db.execute('''SELECT x.*,p.series,p.category_name,p.product_name,p.color_name,
      COALESCE((SELECT SUM(CASE f.action WHEN 'prefer' THEN 1 WHEN 'avoid' THEN -2 WHEN 'replace' THEN -2 ELSE 0 END)
        FROM feedback f WHERE f.supplemental_id=x.id),0) AS feedback_weight
      FROM supplemental_assets x LEFT JOIN products p ON p.id=x.product_id WHERE '''+
      ' AND '.join(cond)+' ORDER BY feedback_weight DESC,x.id LIMIT ?',(*args,limit))]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--db',default=str(DEFAULT_DB));sub=ap.add_subparsers(dest='command',required=True)
    q=sub.add_parser('search');
    for x in ('series','product','color','category','text'):q.add_argument('--'+x)
    q.add_argument('--product-prefix');q.add_argument('--series-prefix')
    q.add_argument('--min-score',type=float);q.add_argument('--allow-mixed',action='store_true');q.add_argument('--mixed-only',action='store_true');q.add_argument('--role',choices=('product_footage','unboxing','certification','other'));q.add_argument('--limit',type=int,default=30)
    g=sub.add_parser('search-generic');g.add_argument('--role',default='unboxing',choices=('unboxing','other'));g.add_argument('--text');g.add_argument('--limit',type=int,default=30)
    cg=sub.add_parser('search-collections');cg.add_argument('--all-series',action='store_true',required=True);cg.add_argument('--text');cg.add_argument('--limit',type=int,default=30)
    sub.add_parser('list-scopes')
    sq=sub.add_parser('support-search')
    for x in ('series','product','color','category','text','role','product-prefix','series-prefix'):sq.add_argument('--'+x)
    sq.add_argument('--limit',type=int,default=30)
    sp=sub.add_parser('support-pending');sp.add_argument('--limit',type=int,default=30)
    sn=sub.add_parser('support-note');sn.add_argument('id',type=int);sn.add_argument('--role',required=True,choices=('unclassified','unboxing','certification','sound_effect','other'))
    sn.add_argument('--description',required=True);sn.add_argument('--keywords');sn.add_argument('--placement-keywords');sn.add_argument('--note',required=True)
    ss=sub.add_parser('support-set');ss.add_argument('id',type=int);ss.add_argument('--role',required=True,choices=('unboxing','certification','sound_effect','other'))
    ss.add_argument('--product-id',type=int);ss.add_argument('--all-products',action='store_true');ss.add_argument('--description',required=True);ss.add_argument('--keywords');ss.add_argument('--placement-keywords');ss.add_argument('--confirmation-note',required=True)
    me=sub.add_parser('motion-event');me.add_argument('asset_id',type=int);me.add_argument('--segment-id',type=int);me.add_argument('--start-us',type=int,required=True);me.add_argument('--end-us',type=int,required=True)
    me.add_argument('--description',required=True);me.add_argument('--pattern',required=True,choices=('single','repeated','continuous'));me.add_argument('--cycle-index',type=int);me.add_argument('--precision',required=True,choices=('coarse','frame_verified'));me.add_argument('--evidence-note',required=True)
    am=sub.add_parser('mark-mixed');am.add_argument('asset_id',type=int);am.add_argument('--product-id',type=int,required=True);am.add_argument('--evidence-note',required=True)
    ar=sub.add_parser('asset-role');ar.add_argument('asset_id',type=int);ar.add_argument('role',choices=('product_footage','unboxing','certification','other','unclassified','collection_montage'));ar.add_argument('--note',required=True)
    ag=sub.add_parser('mark-generic');ag.add_argument('asset_id',type=int);ag.add_argument('--note',required=True)
    f=sub.add_parser('feedback');f.add_argument('--asset-id',type=int);f.add_argument('--supplemental-id',type=int);f.add_argument('--segment-id',type=int);f.add_argument('--action',required=True,choices=('prefer','avoid','replace','trim','rate','note'));f.add_argument('--comment',required=True);f.add_argument('--project-id');f.add_argument('--in-us',type=int);f.add_argument('--out-us',type=int);f.add_argument('--scope',default='asset');f.add_argument('--reusable-rule')
    r=sub.add_parser('run-start');r.add_argument('asset_id',type=int)
    m=sub.add_parser('metadata');m.add_argument('asset_id',type=int);m.add_argument('--json',required=True)
    c=sub.add_parser('run-complete');c.add_argument('asset_id',type=int);c.add_argument('run_id',type=int);c.add_argument('--segments-json',required=True)
    e=sub.add_parser('run-fail');e.add_argument('asset_id',type=int);e.add_argument('run_id',type=int);e.add_argument('--error',required=True)
    n=sub.add_parser('next');n.add_argument('--limit',type=int,default=10)
    sh=sub.add_parser('record-sheet');sh.add_argument('asset_id',type=int);sh.add_argument('--image-path',required=True);sh.add_argument('--source-times-us',required=True)
    mp=sub.add_parser('mark-product');mp.add_argument('asset_id',type=int);mp.add_argument('status',choices=('unverified','matches','mismatch','mixed'))
    sub.add_parser('init')
    a=ap.parse_args();db=connect(a.db)
    if a.command=='search': print(json.dumps(search(db,a.series,a.product,a.color,a.category,a.text,a.min_score,a.allow_mixed,a.limit,a.product_prefix,a.series_prefix,a.mixed_only,a.role),ensure_ascii=False,indent=2))
    elif a.command=='search-generic':print(json.dumps(search_generic(db,a.role,a.text,a.limit),ensure_ascii=False,indent=2))
    elif a.command=='search-collections':print(json.dumps(search_collections(db,a.all_series,a.text,a.limit),ensure_ascii=False,indent=2))
    elif a.command=='list-scopes':print(json.dumps(list_scopes(db),ensure_ascii=False,indent=2))
    elif a.command=='support-search':print(json.dumps(support_search(db,a.role,a.series,a.product,a.color,a.category,a.product_prefix,a.series_prefix,a.text,a.limit),ensure_ascii=False,indent=2))
    elif a.command=='support-pending':print(json.dumps([dict(r) for r in db.execute("SELECT * FROM supplemental_assets WHERE review_status='pending' AND availability_status='online' ORDER BY id LIMIT ?",(a.limit,))],ensure_ascii=False,indent=2))
    elif a.command=='support-note':
        with db:
            cur=db.execute('''UPDATE supplemental_assets SET role=?,product_id=NULL,applies_to_all_products=0,content_description=?,keywords=?,placement_keywords=?,confirmation_note=?,review_status='pending' WHERE id=?''',
              (a.role,a.description,a.keywords,a.placement_keywords,a.note,a.id))
            if cur.rowcount!=1:raise ValueError('unknown supplemental asset')
        print('support evidence saved; pending confirmation')
    elif a.command=='support-set':
        item=db.execute('SELECT media_type FROM supplemental_assets WHERE id=?',(a.id,)).fetchone()
        if not item:raise ValueError('unknown supplemental asset')
        if a.all_products and a.product_id is not None:raise ValueError('choose product-id or all-products')
        if a.role=='sound_effect' and item['media_type']!='audio':raise ValueError('sound effect must be audio')
        if a.role=='unboxing' and item['media_type']=='audio':raise ValueError('unboxing visual cannot be audio-only')
        if a.role=='certification' and (item['media_type']=='audio' or (a.product_id is None and not a.all_products)):raise ValueError('certification needs visual file and confirmed product scope')
        if a.role=='certification' and '核验' not in a.confirmation_note and '确认' not in a.confirmation_note:
            raise ValueError('认证素材需记录用户确认或核验依据')
        with db:
            cur=db.execute('''UPDATE supplemental_assets SET role=?,product_id=?,applies_to_all_products=?,content_description=?,keywords=?,placement_keywords=?,confirmation_note=?,review_status='confirmed' WHERE id=?''',
              (a.role,a.product_id,int(a.all_products),a.description,a.keywords,a.placement_keywords,a.confirmation_note,a.id))
            if cur.rowcount!=1:raise ValueError('unknown supplemental asset')
        print('support asset confirmed')
    elif a.command=='motion-event':
        row=db.execute('SELECT duration_us FROM assets WHERE id=?',(a.asset_id,)).fetchone()
        if not row or row[0] is None or not (0<=a.start_us<a.end_us<=row[0]):raise ValueError('motion outside source duration')
        if a.segment_id and not db.execute('SELECT 1 FROM segments WHERE id=? AND asset_id=?',(a.segment_id,a.asset_id)).fetchone():raise ValueError('segment does not belong to asset')
        if a.precision=='frame_verified' and '帧' not in a.evidence_note and 'frame' not in a.evidence_note.lower():raise ValueError('frame_verified requires frame evidence')
        with db:db.execute('''INSERT INTO motion_events(asset_id,segment_id,source_start_us,source_end_us,motion_description,pattern,cycle_index,boundary_precision,evidence_note) VALUES(?,?,?,?,?,?,?,?,?)''',
          (a.asset_id,a.segment_id,a.start_us,a.end_us,a.description,a.pattern,a.cycle_index,a.precision,a.evidence_note))
        print('motion event saved')
    elif a.command=='mark-mixed':
        row=db.execute('SELECT 1 FROM products WHERE id=?',(a.product_id,)).fetchone()
        if not row:raise ValueError('unknown product')
        with db:
            db.execute("UPDATE assets SET visual_product_status='mixed',mixed_note=? WHERE id=?",(a.evidence_note,a.asset_id))
            db.execute('INSERT INTO asset_product_mentions(asset_id,product_id,evidence_note) VALUES(?,?,?) ON CONFLICT(asset_id,product_id) DO UPDATE SET evidence_note=excluded.evidence_note',(a.asset_id,a.product_id,a.evidence_note))
        print('mixed product recorded')
    elif a.command=='asset-role':
        with db:
            cur=db.execute('UPDATE assets SET asset_role=? WHERE id=?',(a.role,a.asset_id))
            if cur.rowcount!=1:raise ValueError('unknown asset')
            db.execute('INSERT INTO feedback(asset_id,created_at,action,comment,applicable_scope) VALUES(?,?,?,?,?)',(a.asset_id,now(),'note',a.note,'classification'))
        print('asset role saved')
    elif a.command=='mark-generic':
        row=db.execute('SELECT asset_role FROM assets WHERE id=?',(a.asset_id,)).fetchone()
        if not row or row['asset_role'] not in ('unboxing','other'):raise ValueError('mark-generic requires reviewed unboxing/other role')
        with db:
            db.execute('UPDATE assets SET is_generic_broll=1 WHERE id=?',(a.asset_id,))
            db.execute('INSERT INTO feedback(asset_id,created_at,action,comment,applicable_scope) VALUES(?,?,?,?,?)',(a.asset_id,now(),'note',a.note,'generic-broll'))
        print('generic b-roll saved')
    elif a.command=='feedback':
        if (a.asset_id is None)==(a.supplemental_id is None):raise ValueError('choose one asset-id or supplemental-id')
        if a.segment_id is not None and a.asset_id is None:raise ValueError('segment-id needs asset-id')
        with db: db.execute('INSERT INTO feedback(asset_id,supplemental_id,segment_id,created_at,project_id,source_in_us,source_out_us,action,comment,applicable_scope,reusable_rule) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(a.asset_id,a.supplemental_id,a.segment_id,now(),a.project_id,a.in_us,a.out_us,a.action,a.comment,a.scope,a.reusable_rule))
        print('feedback saved')
    elif a.command=='run-start': print(start_run(db,a.asset_id))
    elif a.command=='metadata':
        info=json.loads(Path(a.json).read_text());fields=('duration_us','fps_num','fps_den','width','height','codec','has_audio','chatcut_project_id','chatcut_asset_id')
        with db:db.execute('UPDATE assets SET '+','.join(f+'=?' for f in fields)+' WHERE id=?',tuple(info.get(f) for f in fields)+(a.asset_id,))
    elif a.command=='run-complete': finish_run(db,a.asset_id,a.run_id,'completed',segments=json.loads(Path(a.segments_json).read_text()))
    elif a.command=='run-fail': finish_run(db,a.asset_id,a.run_id,'failed',a.error)
    elif a.command=='next': print(json.dumps([dict(r) for r in db.execute("SELECT a.id,a.absolute_path,a.relative_path,a.duration_us,a.chatcut_project_id,a.chatcut_asset_id,c.image_path AS contact_sheet_path,c.source_times_us FROM assets a LEFT JOIN contact_sheets c ON c.asset_id=a.id AND c.analysis_version=? WHERE a.availability_status='online' AND a.analysis_status IN ('pending','stale') ORDER BY a.id LIMIT ?",(VERSION,a.limit))],ensure_ascii=False,indent=2))
    elif a.command=='record-sheet':
        times=json.loads(a.source_times_us)
        if not times or any(not isinstance(t,int) or t<0 for t in times):raise ValueError('invalid source times')
        with db: db.execute('INSERT INTO contact_sheets(asset_id,image_path,source_times_us,created_at,analysis_version) VALUES(?,?,?,?,?) ON CONFLICT(asset_id,analysis_version) DO UPDATE SET image_path=excluded.image_path,source_times_us=excluded.source_times_us,created_at=excluded.created_at',(a.asset_id,a.image_path,json.dumps(times),now(),VERSION))
    elif a.command=='mark-product':
        with db:db.execute('UPDATE assets SET visual_product_status=? WHERE id=?',(a.status,a.asset_id))
    else: print(a.db)
if __name__=='__main__': main()
