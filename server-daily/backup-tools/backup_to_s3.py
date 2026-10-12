from pathlib import Path
import sys,os,json,sqlite3,tempfile,tarfile,hashlib,datetime,io,argparse
from zoneinfo import ZoneInfo
sys.path.insert(0,'/opt/kiwoom/backup-tools')
import backup as helper
parser=argparse.ArgumentParser();parser.add_argument('--kind',choices=['code','data'],required=True);kind=parser.parse_args().kind
os.umask(0o077);root=Path('/opt/smsg');now=datetime.datetime.now(datetime.timezone.utc);local=now.astimezone(ZoneInfo('Asia/Seoul'))
config=json.loads(Path('/opt/kiwoom/secrets/db-backup-config.json').read_text());credentials=json.loads(Path(config['credentials']).read_text())
try:
 with tempfile.TemporaryDirectory(prefix='smsg-backup-') as directory:
  stage=Path(directory);counts={}
  if kind=='data':
   db=stage/'smsg.sqlite3';src=sqlite3.connect('file:/opt/smsg/data/smsg.sqlite3?mode=ro',uri=True,timeout=30);dest=sqlite3.connect(db);src.backup(dest);src.close()
   if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or dest.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('invalid_database')
   tables=[r[0] for r in dest.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
   counts={name:dest.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in tables};dest.close()
   files={'data/smsg.sqlite3':db,'config/smsg.env':root/'.env','config/smsg.service':Path('/etc/systemd/system/smsg.service'),'config/nginx-smsg':Path('/etc/nginx/sites-available/smsg')}
  else:
   files={p.name:p for p in root.iterdir() if p.is_file() and not p.name.startswith('.') and p.suffix in ['.py','.json','.txt','.md','.yaml']}
   files.update({str(p.relative_to(root)):p for p in (root/'static').rglob('*') if p.is_file() and not p.is_symlink()})
   files.update({str(p.relative_to(root)):p for p in (root/'backup-tools').glob('*.py')})
  if kind=='data':
   for name in ['smsg-code-backup.service','smsg-code-backup.timer','smsg-data-backup.service','smsg-data-backup.timer']:
    files['config/'+name]=Path('/etc/systemd/system')/name
   files['config/recovery-public.crt']=Path('/opt/kiwoom/backup-tools/recovery-public.crt')
  if kind=='code':files['common/backup.py']=Path('/opt/kiwoom/backup-tools/backup.py')
  manifest={'format':1,'project':'smsg','kind':kind,'created_utc':now.isoformat(),'table_counts':counts,'files':[]}
  archive=stage/'backup.tar.gz'
  with tarfile.open(archive,'w:gz') as tar:
   for name,path in sorted(files.items()):
    if path.is_symlink():raise RuntimeError('unexpected_symlink')
    data=path.read_bytes();info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o600;tar.addfile(info,io.BytesIO(data));manifest['files'].append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
   raw=json.dumps(manifest,ensure_ascii=False,indent=2).encode();info=tarfile.TarInfo('manifest.json');info.size=len(raw);info.mode=0o600;tar.addfile(info,io.BytesIO(raw))
  encrypted=stage/'backup.cms';helper.encrypt(archive,'/opt/kiwoom/backup-tools/recovery-public.crt',encrypted)
  suffix='smsg-'+kind+'-'+now.strftime('%Y%m%dT%H%M%SZ')+'.cms';keys=['daily/smsg/'+kind+'/'+local.strftime('%Y/%m/%d/')+suffix]
  if local.day==1:keys.append('monthly/smsg/'+kind+'/'+local.strftime('%Y/%m/')+suffix)
  results=[helper.upload(config,credentials,key,encrypted) for key in keys]
  status={'ok':True,'kind':kind,'bucket':config['bucket'],'created_utc':now.isoformat(),'objects':results,'file_count':len(files),'table_counts':counts}
except Exception as error:
 status={'ok':False,'kind':kind,'created_utc':now.isoformat(),'error_type':type(error).__name__}
 (root/'backups'/('s3-'+kind+'-status.json')).write_text(json.dumps(status));raise RuntimeError('smsg_backup_failed') from None
(root/'backups'/('s3-'+kind+'-status.json')).write_text(json.dumps(status,ensure_ascii=False,indent=2));print(json.dumps(status,ensure_ascii=False))
