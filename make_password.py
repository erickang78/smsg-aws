import getpass,hashlib,secrets
from pathlib import Path
p=Path('.env')
if p.exists():raise SystemExit('.env가 이미 있습니다. 기존 비밀번호를 덮어쓰지 않습니다.')
a=getpass.getpass('모임 비밀번호: ');b=getpass.getpass('비밀번호 확인: ')
if a!=b or len(a)<12:raise SystemExit('12자 이상으로 입력하고 확인값을 맞춰주세요.')
salt=secrets.token_bytes(16);value=salt.hex()+':'+hashlib.pbkdf2_hmac('sha256',a.encode(),salt,600000).hex()
with p.open('x') as f:f.write('SMSG_PASSWORD_HASH='+value+'\n')
p.chmod(0o600);print('.env 설정 완료 (비밀번호는 출력하지 않음)')
