from pathlib import Path
import json,datetime,os
root=Path('/opt/smsg/backups');target=Path('/opt/kiwoom/backup-status/smsg-status.json')
try:prior=json.loads(target.read_text())
except (OSError,ValueError):prior={}
result={}
for kind,filename,time in [('github','github-code-status.json','01:15'),('code','s3-code-status.json','01:20'),('data','s3-data-status.json','01:25'),('course_catalog','course-catalog-status.json','01:30')]:
 try:d=json.loads((root/filename).read_text())
 except (OSError,ValueError):d={}
 result[kind]={'ok':d.get('ok'),'last_success':(d.get('last_success') or d.get('created_utc')) if d.get('ok') is True else prior.get(kind,{}).get('last_success'),'last_attempt':d.get('created_utc') or d.get('last_success'),'file_count':d.get('file_count'),'course_count':d.get('course_count'),'schedule_kst':time}
raw=json.dumps(result);temp=target.with_suffix('.smsg-tmp');temp.write_text(raw);temp.chmod(0o644);temp.replace(target)
