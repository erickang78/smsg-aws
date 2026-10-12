from pathlib import Path
import subprocess,os,shlex,hashlib,json,datetime,re
os.umask(0o077)
root=Path('/opt/smsg');base=root/'github-backup';repo=base/'repository';repo.mkdir(exist_ok=True)
env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_SSH_COMMAND='ssh -i '+shlex.quote(str(base/'deploy-key'))+' -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile='+shlex.quote(str(base/'known_hosts')))
def git(*args):return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','-C',str(repo),*args],env=env,text=True,stderr=subprocess.PIPE).strip()
try:
 if not (repo/'.git').exists():
  git('init','-b','server-daily-backup');git('remote','add','origin','git@github.com:erickang78/smsg-aws.git');git('config','user.name','SMSG Server Backup');git('config','user.email','smsg-backup@users.noreply.github.com')
 files={p.name:p for p in root.iterdir() if p.is_file() and not p.name.startswith('.') and p.suffix in ['.py','.json','.txt','.md','.yaml']}
 for directory in ['static','backup-tools']:
  for p in (root/directory).rglob('*'):
   if p.is_file() and p.suffix in ['.py','.html','.css','.js']:files[str(p.relative_to(root))]=p
 for name in ['smsg.service','smsg-code-backup.service','smsg-code-backup.timer','smsg-data-backup.service','smsg-data-backup.timer','smsg-github-backup.service','smsg-github-backup.timer']:files['config/'+name]=Path('/etc/systemd/system')/name
 files['config/nginx-smsg']=Path('/etc/nginx/sites-available/smsg')
 files['common/backup.py']=Path('/opt/kiwoom/backup-tools/backup.py')
 snapshot={}
 for name,p in files.items():
  if p.is_symlink():raise RuntimeError('unexpected_symlink')
  raw=p.read_bytes()
  if re.search(rb'(?:AKIA|ASIA)[A-Z0-9]{16}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----',raw):raise RuntimeError('secret_scan_failed')
  snapshot[name]=raw
 target=repo/'server-daily';target.mkdir(exist_ok=True)
 manifest={'project':'smsg','files':[{'path':name,'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in sorted(snapshot.items())]}
 snapshot['manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode()
 for p in target.rglob('*'):
  if p.is_symlink():raise RuntimeError('unexpected_repository_symlink')
  if p.is_file() and str(p.relative_to(target)) not in snapshot:p.unlink()
 for name,raw in snapshot.items():
  p=target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 git('add','--','server-daily')
 if git('diff','--cached','--name-only'):git('commit','-m','SMSG operating code backup '+datetime.datetime.now(datetime.timezone.utc).isoformat())
 git('push','-u','origin','server-daily-backup')
 status={'ok':True,'last_success':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commit':git('rev-parse','HEAD'),'file_count':len(files),'branch':'server-daily-backup'}
except Exception as error:
 (root/'backups/github-code-status.json').write_text(json.dumps({'ok':False,'error_type':type(error).__name__}));raise RuntimeError('github_code_backup_failed') from None
(root/'backups/github-code-status.json').write_text(json.dumps(status,indent=2));print(json.dumps(status))
