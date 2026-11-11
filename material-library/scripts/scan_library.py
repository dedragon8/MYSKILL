#!/usr/bin/env python3
"""Incremental read-only scan of source footage; never changes source files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from material_db import connect

EXT={'.mp4','.mov','.m4v','.avi','.mkv'}
SKIP={'__MACOSX','.git','cache','caches','tmp','temp','代理','缓存'}
DEFAULT_ROOT=Path.home()/'Desktop/千川AI剪辑素材库'
DICT=Path(__file__).resolve().parents[1]/'references/classification.json'

def fingerprint(path,size):
    h=hashlib.sha256();h.update(str(size).encode())
    with path.open('rb') as f:
        h.update(f.read(1024*1024))
        if size>2*1024*1024:
            f.seek(max(0,size//2-512*1024));h.update(f.read(1024*1024))
            f.seek(max(0,size-1024*1024));h.update(f.read(1024*1024))
    return h.hexdigest()

def classify(parts,dictionary):
    series,category=parts[0],parts[1]
    exact=dictionary.get('name_mappings',{}).get(series+'/'+category)
    if exact:return (*exact,'confirmed')
    normalized=category.replace(' ','')
    products=sorted(dictionary.get('products',[]),key=len,reverse=True)
    colors=sorted(dictionary.get('colors',[]),key=len,reverse=True)
    for product in products:
        if normalized.startswith(product):
            rest=normalized[len(product):]
            for color in colors:
                if rest==color:return (product,color,'confirmed')
    return (None,None,'pending')

def scan(root,db,dictionary):
    root=root.expanduser().resolve()
    if not root.is_dir():raise FileNotFoundError(root)
    found=set();counts={k:0 for k in ('new','changed','moved','unchanged','offline','unclassified')}
    for base,dirs,files in os.walk(root):
        dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d.lower() not in SKIP)
        for name in sorted(files):
            if name.startswith('.') or Path(name).suffix.lower() not in EXT:continue
            path=Path(base)/name;rel=path.relative_to(root);parts=rel.parts
            if len(parts)>=3:
                series,category=parts[:2];folder='/'.join(parts[:2])
                product,color,status=classify(parts,dictionary)
            elif len(parts)==2:
                series=category=parts[0];folder=parts[0]
                product=color=None;status='pending'
            else:
                series=category='[root]';folder='.'
                product=color=None;status='pending'
            relative=rel.as_posix()
            st=path.stat();mtime=st.st_mtime_ns;size=st.st_size
            old=db.execute('SELECT * FROM assets WHERE relative_path=?',(relative,)).fetchone()
            if old and old['file_size']==size and old['modified_time']==mtime:
                found.add(old['id']);counts['unchanged']+=1;continue
            fp=fingerprint(path,size)
            with db:
                db.execute('''INSERT INTO products(series,category_name,product_name,color_name,relative_folder_path,classification_status)
                 VALUES(?,?,?,?,?,?) ON CONFLICT(relative_folder_path) DO UPDATE SET
                 product_name=CASE WHEN excluded.classification_status='confirmed' THEN excluded.product_name ELSE products.product_name END,
                 color_name=CASE WHEN excluded.classification_status='confirmed' THEN excluded.color_name ELSE products.color_name END,
                 classification_status=CASE WHEN excluded.classification_status='confirmed' THEN 'confirmed' ELSE products.classification_status END''',(series,category,product,color,folder,status))
                pid=db.execute('SELECT id FROM products WHERE relative_folder_path=?',(folder,)).fetchone()[0]
                if old:
                    changed=old['file_fingerprint']!=fp
                    # A timestamp-only change must retain a visually confirmed color
                    # split within a shared physical folder.
                    reviewed_pid = pid if changed else old['product_id']
                    db.execute('''UPDATE assets SET product_id=?,filename=?,absolute_path=?,file_size=?,modified_time=?,file_fingerprint=?,availability_status='online',
                      analysis_status=CASE WHEN ? THEN 'stale' ELSE analysis_status END,
                      visual_product_status=CASE WHEN ? THEN 'unverified' ELSE visual_product_status END,
                      asset_role=CASE WHEN ? THEN 'unclassified' ELSE asset_role END,
                      is_generic_broll=CASE WHEN ? THEN 0 ELSE is_generic_broll END,
                      mixed_note=CASE WHEN ? THEN NULL ELSE mixed_note END WHERE id=?''',
                      (reviewed_pid,name,str(path),size,mtime,fp,changed,changed,changed,changed,changed,old['id']))
                    if changed:
                        db.execute('DELETE FROM asset_product_mentions WHERE asset_id=?',(old['id'],))
                        db.execute('DELETE FROM motion_events WHERE asset_id=?',(old['id'],))
                        db.execute('DELETE FROM contact_sheets WHERE asset_id=?',(old['id'],))
                    found.add(old['id']);counts['changed' if changed else 'unchanged']+=1
                else:
                    matches=[r for r in db.execute("SELECT id,product_id,absolute_path,relative_path,availability_status FROM assets WHERE file_fingerprint=?",(fp,)).fetchall() if r['availability_status']=='offline' or not Path(r['absolute_path']).exists()]
                    if len(matches)==1:
                        aid=matches[0]['id']
                        old_parts=Path(matches[0]['relative_path']).parts
                        old_folder='/'.join(old_parts[:2]) if len(old_parts)>=3 else old_parts[0] if len(old_parts)==2 else '.'
                        reviewed_pid=matches[0]['product_id'] if old_folder==folder else pid
                        changed_product=matches[0]['product_id']!=reviewed_pid
                        db.execute('''UPDATE assets SET product_id=?,filename=?,absolute_path=?,relative_path=?,file_size=?,modified_time=?,availability_status='online',
                          analysis_status=CASE WHEN ? THEN 'stale' ELSE analysis_status END,
                          visual_product_status=CASE WHEN ? THEN 'unverified' ELSE visual_product_status END,
                          asset_role=CASE WHEN ? THEN 'unclassified' ELSE asset_role END,
                          is_generic_broll=CASE WHEN ? THEN 0 ELSE is_generic_broll END,
                          mixed_note=CASE WHEN ? THEN NULL ELSE mixed_note END WHERE id=?''',
                          (reviewed_pid,name,str(path),relative,size,mtime,changed_product,changed_product,changed_product,changed_product,changed_product,aid))
                        if changed_product:db.execute('DELETE FROM asset_product_mentions WHERE asset_id=?',(aid,))
                        found.add(aid);counts['moved']+=1
                    else:
                        cur=db.execute('''INSERT INTO assets(product_id,filename,absolute_path,relative_path,file_size,modified_time,file_fingerprint,asset_role) VALUES(?,?,?,?,?,?,?,'unclassified')''',(pid,name,str(path),relative,size,mtime,fp))
                        found.add(cur.lastrowid);counts['new']+=1
    with db:
        for row in db.execute("SELECT id FROM assets WHERE availability_status='online'").fetchall():
            if row['id'] not in found:
                db.execute("UPDATE assets SET availability_status='offline' WHERE id=?",(row['id'],));counts['offline']+=1
    counts['unclassified']=db.execute("SELECT COUNT(*) FROM assets a JOIN products p ON p.id=a.product_id WHERE a.availability_status='online' AND p.classification_status='pending' AND a.is_generic_broll=0").fetchone()[0]
    return counts

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(DEFAULT_ROOT));ap.add_argument('--db');a=ap.parse_args()
    d=json.loads(DICT.read_text());db=connect(a.db) if a.db else connect()
    print(json.dumps(scan(Path(a.root),db,d),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
