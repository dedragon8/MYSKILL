#!/usr/bin/env python3
"""Discover image, PDF and audio files without guessing their content or use."""
import argparse
import json
import os
from pathlib import Path
from material_db import connect
from scan_library import fingerprint, SKIP, DEFAULT_ROOT

TYPES = {
    '.jpg':'image','.jpeg':'image','.png':'image','.webp':'image','.heic':'image',
    '.pdf':'document',
    '.wav':'audio','.mp3':'audio','.m4a':'audio','.aif':'audio','.aiff':'audio','.flac':'audio'
}

def scan(root, db):
    root = root.expanduser().resolve()
    if not root.is_dir(): raise FileNotFoundError(root)
    counts = dict(new=0, changed=0, moved=0, unchanged=0, offline=0, pending=0)
    found = set()
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d.lower() not in SKIP)
        for name in sorted(files):
            if name.startswith('.'): continue
            kind = TYPES.get(Path(name).suffix.lower())
            if kind is None: continue
            path=Path(base)/name; relative=path.relative_to(root).as_posix()
            stat=path.stat();size=stat.st_size;mtime=stat.st_mtime_ns
            old=db.execute('SELECT * FROM supplemental_assets WHERE absolute_path=?',(str(path),)).fetchone()
            if old and old['file_size']==size and old['modified_time']==mtime:
                found.add(old['id']);counts['unchanged']+=1;continue
            fp=fingerprint(path,size)
            parts=Path(relative).parts
            product=None
            if len(parts)>=3:
                product=db.execute('SELECT id FROM products WHERE relative_folder_path=?',('/'.join(parts[:2]),)).fetchone()
            product_id=product[0] if product else None
            with db:
                if old:
                    changed=old['file_fingerprint']!=fp
                    db.execute('''UPDATE supplemental_assets SET file_size=?,modified_time=?,file_fingerprint=?,availability_status='online',
                      review_status=CASE WHEN ? THEN 'pending' ELSE review_status END WHERE id=?''',(size,mtime,fp,changed,old['id']))
                    found.add(old['id']);counts['changed' if changed else 'unchanged']+=1
                else:
                    candidates=db.execute('SELECT id,absolute_path,product_id FROM supplemental_assets WHERE file_fingerprint=? AND media_type=?',(fp,kind)).fetchall()
                    missing=[r for r in candidates if not Path(r['absolute_path']).exists()]
                    if len(missing)==1:
                        aid=missing[0]['id']
                        changed_product=missing[0]['product_id']!=product_id
                        db.execute('''UPDATE supplemental_assets SET root_path=?,relative_path=?,absolute_path=?,filename=?,product_id=?,
                          file_size=?,modified_time=?,availability_status='online',
                          review_status=CASE WHEN ? THEN 'pending' ELSE review_status END WHERE id=?''',
                          (str(root),relative,str(path),name,product_id,size,mtime,changed_product,aid))
                        found.add(aid);counts['moved']+=1
                    else:
                        cur=db.execute('''INSERT INTO supplemental_assets(root_path,relative_path,absolute_path,filename,media_type,
                          product_id,file_size,modified_time,file_fingerprint) VALUES(?,?,?,?,?,?,?,?,?)''',
                          (str(root),relative,str(path),name,kind,product_id,size,mtime,fp))
                        found.add(cur.lastrowid);counts['new']+=1
    with db:
        for row in db.execute("SELECT id FROM supplemental_assets WHERE root_path=? AND availability_status='online'",(str(root),)).fetchall():
            if row['id'] not in found:
                db.execute("UPDATE supplemental_assets SET availability_status='offline' WHERE id=?",(row['id'],))
                counts['offline']+=1
    counts['pending']=db.execute("SELECT COUNT(*) FROM supplemental_assets WHERE root_path=? AND review_status='pending' AND availability_status='online'",(str(root),)).fetchone()[0]
    return counts

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(DEFAULT_ROOT));ap.add_argument('--db');a=ap.parse_args()
    db=connect(a.db) if a.db else connect()
    print(json.dumps(scan(Path(a.root),db),ensure_ascii=False,indent=2))
