#!/usr/bin/env python3
"""Read audio metadata and decoded signal statistics. Does NOT listen or label sounds.

Uses existing ffprobe/ffmpeg only. No dependency installation or network calls.
The supplemental review remains pending until actual listening supplies evidence.
"""
import argparse
import array
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from material_db import connect, DEFAULT_DB, now
from scan_support import scan
from scan_library import DEFAULT_ROOT

BUNDLED=Path('/Applications/ChatCut.app/Contents/Resources/app.asar.unpacked/node_modules/ffmpeg-ffprobe-static')


def executable(name, explicit=None):
    if explicit:
        path=Path(explicit).expanduser()
    else:
        system=shutil.which(name)
        path=Path(system) if system else BUNDLED/name
    if not path.is_file():
        raise FileNotFoundError(f'{name} unavailable; do not install without user authorization')
    return str(path)


def dbfs(value):
    return round(20*math.log10(value/32768),2) if value else None


def measure(path, ffprobe, ffmpeg):
    before=path.stat()
    info=json.loads(subprocess.run([ffprobe,'-v','error','-show_format','-show_streams','-of','json',str(path)],
        capture_output=True,text=True,check=True,timeout=60).stdout)
    stream=next(s for s in info['streams'] if s.get('codec_type')=='audio')
    # Normalized PCM identity ignores container/ID3 differences. Meter values
    # refer to this 44.1kHz stereo signed-16-bit decode, not LUFS or perceived level.
    pcm=subprocess.run([ffmpeg,'-v','error','-i',str(path),'-map','0:a:0','-vn','-f','s16le',
        '-acodec','pcm_s16le','-ar','44100','-ac','2','pipe:1'],capture_output=True,check=True,timeout=180).stdout
    samples=array.array('h');samples.frombytes(pcm)
    import sys
    if sys.byteorder!='little':samples.byteswap()
    if not samples:raise ValueError('No decoded audio samples')
    peak=max(abs(x) for x in samples)
    rms=math.sqrt(sum(x*x for x in samples)/len(samples))
    envelope=[]
    for start in range(0,len(samples),8820):
        chunk=samples[start:start+8820]
        envelope.append(dict(start_us=round(start/2/44100*1e6),end_us=round((start+len(chunk))/2/44100*1e6),
            rms_dbfs=dbfs(math.sqrt(sum(x*x for x in chunk)/len(chunk))),peak_dbfs=dbfs(max(abs(x) for x in chunk))))
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise RuntimeError('Source changed during measurement; rescan and retry')
    return dict(duration_us=round(len(samples)/2/44100*1e6),sample_rate=int(stream['sample_rate']),
        channels=stream['channels'],codec=stream['codec_name'],file_sha256=checksum,
        decoded_pcm_sha256=hashlib.sha256(pcm).hexdigest(),peak_dbfs=dbfs(peak),rms_dbfs=dbfs(rms),
        envelope_100ms=envelope,measurement='ffmpeg: 44100Hz stereo s16le; RMS/sample peak, not LUFS',
        content_listened=False,boundary_precision='signal_envelope_only')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',default=str(DEFAULT_ROOT));ap.add_argument('--db',default=str(DEFAULT_DB))
    ap.add_argument('--report',required=True);ap.add_argument('--ffprobe');ap.add_argument('--ffmpeg')
    args=ap.parse_args()
    probe=executable('ffprobe',args.ffprobe);decoder=executable('ffmpeg',args.ffmpeg)
    root=Path(args.root).expanduser().resolve();db=connect(args.db)
    scanned=scan(root,db);results=[]
    rows=db.execute("SELECT * FROM supplemental_assets WHERE root_path=? AND media_type='audio' AND availability_status='online' ORDER BY id",(str(root),)).fetchall()
    for row in rows:
        try:
            measured=measure(Path(row['absolute_path']),probe,decoder)
            keys=('duration_us','sample_rate','channels','codec','file_sha256','decoded_pcm_sha256','peak_dbfs','rms_dbfs')
            values=[measured[k] for k in keys]
            with db:
                db.execute('INSERT INTO audio_metadata(supplemental_id,source_fingerprint,'+','.join(keys)+',technical_json,measured_at) VALUES('+','.join('?' for _ in range(12))+') ON CONFLICT(supplemental_id) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in ('source_fingerprint',*keys,'technical_json','measured_at')),
                    (row['id'],row['file_fingerprint'],*values,json.dumps(measured,ensure_ascii=False),now()))
                if row['review_status']=='pending' and not row['content_description']:
                    db.execute("UPDATE supplemental_assets SET content_description=?,confirmation_note=? WHERE id=?",(
                        '音频技术检测完成，尚未实际试听；声音内容、动作、适用画面和循环接缝未确认。',
                        '仅技术测量，不是听审；不得按文件名确认内容或加入剪辑候选。',row['id']))
            results.append(dict(id=row['id'],filename=row['filename'],absolute_path=row['absolute_path'],ok=True,review_status=row['review_status'],**measured))
        except Exception as exc:
            results.append(dict(id=row['id'],filename=row['filename'],ok=False,error=str(exc),content_listened=False))
    report=Path(args.report).expanduser();report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(dict(scan=scanned,audio=results),ensure_ascii=False,indent=2))
    print(json.dumps(dict(audio_files=len(results),technical_ok=sum(r['ok'] for r in results),
        actually_listened=0,report=str(report)),ensure_ascii=False))
    if any(not r['ok'] for r in results):raise SystemExit(1)


if __name__=='__main__':main()
