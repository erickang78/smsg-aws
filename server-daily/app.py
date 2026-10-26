import os,json,sqlite3,secrets,hashlib,hmac,time,re,math
from pathlib import Path
from http.cookies import SimpleCookie
ROOT=Path(__file__).parent
DB=Path(os.environ.get('SMSG_DB',str(ROOT/'data'/'smsg.sqlite3')))

MEAL_NOTE_2='진팀이 이긴팀 밥사주기'
MEAL_NOTE_5='밥값\n1등 1만원\n2등 1.5만원\n3등 2만원\n4등 2.5만원\n5등 3만원'
MEAL_NOTE_5_OLD_DEFAULT='밥값 1등 5천원, 2등 1만원, 3등 1만5천원, 4등 2만원, 5등 3만원'
MEAL_NOTE_5_OLD_CUSTOM='밥값 \n1등 1만원\n2등 1.5만원\n3등 2.5만원\n4등 3만원'
MEAL_NOTE_3='밥값 1등 1만원, 2등 2만원, 3등 3만원'
MEAL_NOTE_4='밥값 1등 5천원, 2등 1만원, 3등 2만원 4등 3만원'

def connect():
 c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c

def init():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.executescript('''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS game_groupings(game_id TEXT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,groups_json TEXT NOT NULL,group_count INTEGER NOT NULL,group_size INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS game_notes(game_id TEXT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY,date TEXT NOT NULL,course TEXT NOT NULL,fairway INTEGER NOT NULL,green INTEGER NOT NULL,deleted_at INTEGER);
CREATE TABLE IF NOT EXISTS game_change_log(id INTEGER PRIMARY KEY AUTOINCREMENT,game_id TEXT NOT NULL,action TEXT NOT NULL,game_date TEXT NOT NULL,course TEXT NOT NULL,changed_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS game_participants(game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,member_id TEXT NOT NULL REFERENCES members(id),PRIMARY KEY(game_id,member_id));
CREATE TABLE IF NOT EXISTS historical_scores(member_id TEXT NOT NULL REFERENCES members(id),position INTEGER NOT NULL,score REAL NOT NULL,PRIMARY KEY(member_id,position));
CREATE TABLE IF NOT EXISTS game_results(game_id TEXT NOT NULL,member_id TEXT NOT NULL,score REAL NOT NULL,PRIMARY KEY(game_id,member_id),FOREIGN KEY(game_id,member_id) REFERENCES game_participants(game_id,member_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,name TEXT NOT NULL,handicap REAL NOT NULL,note TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,phone TEXT NOT NULL DEFAULT '',nickname TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS meals(id TEXT PRIMARY KEY,date TEXT NOT NULL,place TEXT NOT NULL,people INTEGER NOT NULL,income INTEGER NOT NULL,extra INTEGER NOT NULL,expense INTEGER NOT NULL,note TEXT NOT NULL,position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rounds(date TEXT PRIMARY KEY,groups_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS member_logins(member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,username TEXT NOT NULL UNIQUE,salt TEXT NOT NULL,password_hash TEXT NOT NULL,created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY,count INTEGER NOT NULL,reset INTEGER NOT NULL);''')
  if 'phone' not in [r['name'] for r in c.execute('PRAGMA table_info(members)')]:
   c.execute("ALTER TABLE members ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
  if 'nickname' not in [r['name'] for r in c.execute('PRAGMA table_info(members)')]:
   c.execute("ALTER TABLE members ADD COLUMN nickname TEXT NOT NULL DEFAULT ''")
  if 'deleted_at' not in [r['name'] for r in c.execute('PRAGMA table_info(games)')]:
   c.execute('ALTER TABLE games ADD COLUMN deleted_at INTEGER')
  if 'member_id' not in [r['name'] for r in c.execute('PRAGMA table_info(sessions)')]:
   c.execute('ALTER TABLE sessions ADD COLUMN member_id TEXT REFERENCES members(id)')
  c.execute('BEGIN IMMEDIATE')
  if not c.execute("SELECT 1 FROM settings WHERE id='seeded'").fetchone():
   for i,r in enumerate(json.loads((ROOT/'seed.json').read_text())):
    c.execute('INSERT INTO meals VALUES(?,?,?,?,?,?,?,?,?)',tuple(r[k] for k in ['id','date','place','people','income','extra','expense','note'])+(i,))
   c.execute("INSERT INTO settings VALUES('opening','132843')");c.execute("INSERT INTO settings VALUES('seeded','1')")

def records(c):
 rows=[dict(r) for r in c.execute('SELECT * FROM meals ORDER BY date,position,id')];balance=int(c.execute("SELECT value FROM settings WHERE id='opening'").fetchone()[0])
 for r in rows:r['settlement']=r['income']-r['expense'];balance+=r['settlement']+r['extra'];r['balance']=balance
 return rows,balance

def state_data(c,include_private=False):
 meals,balance=records(c)
 members=[]
 for row in c.execute('SELECT * FROM members ORDER BY name'):
  m=dict(row)
  if not include_private:m.pop('phone',None);m.pop('nickname',None)
  summary=recalculate_handicap(c,m['id']);m['handicap']=summary['handicap'];m['handicap_basis']=summary['basis'];m['score_count']=summary['count'];m['last_attended']=c.execute('SELECT MAX(g.date) FROM game_results r JOIN games g ON g.id=r.game_id WHERE r.member_id=? AND g.deleted_at IS NULL',(m['id'],)).fetchone()[0];members.append(m)
 rounds=[dict(r) for r in c.execute('SELECT * FROM rounds ORDER BY date DESC')]
 historical_scores=[dict(r) for r in c.execute('SELECT h.member_id,m.name AS member_name,h.position,h.score FROM historical_scores h JOIN members m ON m.id=h.member_id ORDER BY m.name,h.position')]
 games=[dict(r,note=(lambda row:row[0] if row else '')(c.execute('SELECT note FROM game_notes WHERE game_id=?',(r['id'],)).fetchone()),grouping=(lambda row:dict(row,groups=json.loads(row['groups_json'])) if row else None)(c.execute('SELECT * FROM game_groupings WHERE game_id=?',(r['id'],)).fetchone()),results={x['member_id']:x['score'] for x in c.execute('SELECT member_id,score FROM game_results WHERE game_id=?',(r['id'],))},participants=[x[0] for x in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(r['id'],))]) for r in c.execute('SELECT * FROM games WHERE deleted_at IS NULL ORDER BY date DESC,rowid DESC')]
 period=get_handicap_period(c)
 return {'members':members,'meals':meals,'rounds':rounds,'historical_scores':historical_scores,'games':games,'opening':132843,'balance':balance,'settings':{'handicap_period_months':period}}

def get_handicap_period(c):
 row=c.execute("SELECT value FROM settings WHERE id='handicap_period_months'").fetchone()
 try:period=int(row['value']) if row else 3
 except (TypeError,ValueError):period=3
 return period if period in (1,2,3,6,12) else 3

def score_summary(c,member_id):
 row=c.execute('SELECT COUNT(*) AS count,COALESCE(SUM(score),0) AS total FROM (SELECT score FROM historical_scores WHERE member_id=? UNION ALL SELECT r.score FROM game_results r JOIN games g ON g.id=r.game_id WHERE r.member_id=? AND g.deleted_at IS NULL)',(member_id,member_id)).fetchone()
 return dict(row)

def recalculate_handicap(c,member_id,as_of=None):
 from decimal import Decimal,ROUND_HALF_UP
 from datetime import date,datetime
 from zoneinfo import ZoneInfo
 import calendar
 today=date.fromisoformat(as_of) if isinstance(as_of,str) else as_of or datetime.now(ZoneInfo('Asia/Seoul')).date()
 def months_before(months):
  month=today.month-months;year=today.year+(month-1)//12;month=(month-1)%12+1
  return today.replace(year=year,month=month,day=min(today.day,calendar.monthrange(year,month)[1])).isoformat()
 period=get_handicap_period(c)
 cutoff=months_before(period)
 rows=c.execute('''SELECT g.date,r.score FROM game_results r JOIN games g ON g.id=r.game_id
                   WHERE r.member_id=? AND g.deleted_at IS NULL AND g.date>=? AND g.date<=?''',
                (member_id,cutoff,today.isoformat())).fetchall()
 scores=[r['score'] for r in rows]
 if not scores and period<12:
  rows=c.execute('''SELECT g.date,r.score FROM game_results r JOIN games g ON g.id=r.game_id
                    WHERE r.member_id=? AND g.deleted_at IS NULL AND g.date>=? AND g.date<=?''',
                 (member_id,months_before(12),today.isoformat())).fetchall()
  scores=[r['score'] for r in rows]
 basis=(f'{period}M' if period<12 else '1Y') if scores and (period==12 or any(r['date']>=cutoff for r in rows)) else '1Y' if scores else '초기'
 if scores:
  total=sum((Decimal(str(score)) for score in scores),Decimal(0))
  hd=float((total/Decimal(len(scores))).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP))
  c.execute('UPDATE members SET handicap=? WHERE id=?',(hd,member_id))
 else:
  initial=c.execute("SELECT value FROM settings WHERE id=?",('handicap_initial:'+member_id,)).fetchone()
  if initial:
   hd=float(initial[0]);c.execute('UPDATE members SET handicap=? WHERE id=?',(hd,member_id))
  else:hd=float(c.execute('SELECT handicap FROM members WHERE id=?',(member_id,)).fetchone()[0])
 return {**score_summary(c,member_id),'handicap':hd,'basis':basis,'window_count':len(scores)}

def fair_game_groups(members,group_count,group_size):
 import random
 rng=random.Random(2026);ordered=sorted(members,key=lambda m:(-m['handicap'],m['id']))
 weights={m['id']:int(round(m['handicap']*10)) for m in members};best=None;best_cost=None
 for attempt in range(48):
  if attempt:
   shuffled=ordered[:];rng.shuffle(shuffled);groups=[shuffled[i*group_size:(i+1)*group_size] for i in range(group_count)]
  else:
   groups=[[] for _ in range(group_count)]
   for i,m in enumerate(ordered):
    row,col=divmod(i,group_count);groups[col if row%2==0 else group_count-1-col].append(m)
  sums=[sum(weights[m['id']] for m in g) for g in groups]
  for _ in range(80):
   change=None;delta_best=0
   for a in range(group_count):
    for b in range(a+1,group_count):
     for ia,ma in enumerate(groups[a]):
      for ib,mb in enumerate(groups[b]):
       diff=weights[mb['id']]-weights[ma['id']]
       delta=2*diff*(sums[a]-sums[b]+diff)
       if delta<delta_best:delta_best=delta;change=(a,b,ia,ib,diff)
   if change is None:break
   a,b,ia,ib,diff=change;groups[a][ia],groups[b][ib]=groups[b][ib],groups[a][ia];sums[a]+=diff;sums[b]-=diff
  cost=sum(n*n for n in sums)
  if best_cost is None or cost<best_cost:best_cost=cost;best=groups
  if max(sums)-min(sums)<=1:break
 return [sorted(g,key=lambda m:(m['handicap'],m['name'])) for g in best]

def balanced_groups(members,size=4):
 # Capacity fixed at 3/4 for ordinary golf groups; requested size 2..4.
 n=math.ceil(len(members)/size);groups=[[] for _ in range(n)];sums=[0.0]*n
 for m in sorted(members,key=lambda x:(-x['handicap'],x['name'])):
  candidates=[i for i in range(n) if len(groups[i])<size]
  idx=min(candidates,key=lambda i:(len(groups[i]),sums[i],i));groups[idx].append(m);sums[idx]+=m['handicap']
 return groups

def application(environ,start_response):
 def send(data,status='200 OK',headers=()):
  payload=json.dumps(data,ensure_ascii=False).encode();start_response(status,[('Content-Type','application/json; charset=utf-8'),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]+list(headers));return [payload]
 path=environ.get('PATH_INFO','/');method=environ.get('REQUEST_METHOD','GET')
 try:path=path.encode('latin-1').decode('utf-8')
 except (UnicodeEncodeError,UnicodeDecodeError):pass
 profile_page=False
 member_directory_page=method=='GET' and path.rstrip('/')=='/members'
 shared_page=method=='GET' and path.rstrip('/')=='/shared'
 if method=='GET' and path.rstrip('/')=='/member':
  start_response('301 Moved Permanently',[('Location','/members'),('Cache-Control','no-store')]);return [b'']
 if method=='GET' and path.count('/')==1 and path not in ['/','/health']:
  with connect() as c:profile_page=c.execute('SELECT 1 FROM members WHERE name=?',(path[1:],)).fetchone() is not None
 if (path in ['/','/static/app.js','/static/style.css','/static/share.js','/static/share.css'] or profile_page or member_directory_page or shared_page) and method=='GET':
  filename={'/':'index.html','/shared':'share.html','/static/app.js':'app.js','/static/style.css':'style.css','/static/share.js':'share.js','/static/share.css':'share.css'}.get(path,'index.html' if profile_page or member_directory_page else path.split('/')[-1]);ctype={'index.html':'text/html; charset=utf-8','share.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','share.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8','share.css':'text/css; charset=utf-8'}[filename]
  start_response('200 OK',[('Content-Type',ctype),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' https://lobby.golfzon.com; img-src 'self' https://i.gzcdn.net; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]);return [(ROOT/'static'/filename).read_bytes()]
 if path=='/health' and method=='GET':return send({'ok':True})
 if not path.startswith('/api/'):return send({'error':'페이지를 찾을 수 없습니다.'},'404 Not Found')
 try:
  length=int(environ.get('CONTENT_LENGTH') or 0)
  max_length=9*1024*1024 if path in ('/api/game-result-image','/api/game-results-bulk') else 65536
  if length>max_length:return send({'error':'입력 크기가 너무 큽니다.'},'413 Content Too Large')
  body=json.loads(environ['wsgi.input'].read(length) or b'{}') if method!='GET' else {}
  if method!='GET':
   origin=environ.get('HTTP_ORIGIN');expected=environ['wsgi.url_scheme']+'://'+environ.get('HTTP_HOST','')
   if origin!=expected:return send({'error':'허용되지 않은 요청입니다.'},'403 Forbidden')
  with connect() as c:
   cookies=SimpleCookie();cookies.load(environ.get('HTTP_COOKIE',''));token=cookies['smsg_session'].value if 'smsg_session' in cookies else '';token_hash=hashlib.sha256(token.encode()).hexdigest();now=int(time.time())
   if path=='/api/member-login' and method=='POST':
    ip=environ.get('REMOTE_ADDR','unknown');a=c.execute('SELECT * FROM attempts WHERE ip=?',(ip,)).fetchone()
    if a and a['reset']>now and a['count']>=10:return send({'error':'잠시 후 다시 로그인해주세요.'},'429 Too Many Requests')
    user=c.execute('SELECT * FROM member_logins WHERE username=?',(str(body.get('username','')).strip().lower(),)).fetchone()
    salt_hex=user['salt'] if user else '00000000000000000000000000000000';expected_hash=user['password_hash'] if user else '0'*64
    actual=hashlib.pbkdf2_hmac('sha256',str(body.get('password','')).encode(),bytes.fromhex(salt_hex),600000).hex()
    if not user or not hmac.compare_digest(actual,expected_hash):
     count=a['count']+1 if a and a['reset']>now else 1;c.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(ip,count,now+900 if count==1 else a['reset']));return send({'error':'회원 ID 또는 비밀번호를 확인해주세요.'},'401 Unauthorized')
    c.execute('DELETE FROM attempts WHERE ip=?',(ip,));c.execute('DELETE FROM sessions WHERE expires<?',(now,));token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions(token,expires,member_id) VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),now+86400,user['member_id']))
    return send({'ok':True},headers=[('Set-Cookie','smsg_session='+token+'; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400'+('; Secure' if environ['wsgi.url_scheme']=='https' else ''))])
   if path=='/api/login' and method=='POST':
    return send({'error':'회원 ID와 회원 비밀번호로 로그인해주세요.'},'410 Gone')
   if path=='/api/shared-state' and method=='GET':
    provided=environ.get('HTTP_AUTHORIZATION','')
    token=provided[7:] if provided.startswith('Bearer ') else ''
    saved=c.execute("SELECT value FROM settings WHERE id='share_token_hash'").fetchone()
    if not saved or not token or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),saved['value']):return send({'error':'공유 링크가 만료되었거나 폐기되었습니다.'},'404 Not Found')
    return send(state_data(c))
   if path=='/api/profile' and method=='GET':
    from urllib.parse import parse_qs
    name=parse_qs(environ.get('QUERY_STRING','')).get('name',[''])[0]
    matches=c.execute('SELECT * FROM members WHERE name=?',(name,)).fetchall()
    if len(matches)!=1:return send({'error':'회원을 찾을 수 없거나 같은 이름의 회원이 여러 명입니다.'},'404 Not Found')
    member=dict(matches[0]);member.pop('phone',None);id=member['id']
    games=[dict(r) for r in c.execute('SELECT g.id,g.date,g.course,r.score FROM games g JOIN game_results r ON r.game_id=g.id WHERE r.member_id=? AND g.deleted_at IS NULL ORDER BY g.date DESC,g.id',(id,))]
    summary=recalculate_handicap(c,id);member.update(handicap=summary['handicap'],handicap_basis=summary['basis'],score_count=summary['count'],last_attended=games[0]['date'] if games else None)
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    upcoming=[dict(r) for r in c.execute('SELECT g.id,g.date,g.course,g.fairway,g.green,EXISTS(SELECT 1 FROM game_participants p WHERE p.game_id=g.id AND p.member_id=?) AS attending,EXISTS(SELECT 1 FROM game_results r WHERE r.game_id=g.id AND r.member_id=?) AS has_result FROM games g WHERE g.deleted_at IS NULL AND g.date>=? ORDER BY g.date,g.id',(id,id,today))]
    for game in upcoming:game['attendance_locked']=(datetime.fromisoformat(game['date']).date()-datetime.now(ZoneInfo('Asia/Seoul')).date()).days<=3
    return send({'member':member,'games':games,'upcoming':upcoming})
   if path=='/api/member-directory' and method=='GET':
    members=[]
    for r in c.execute('SELECT id,name,nickname FROM members ORDER BY name COLLATE NOCASE,name').fetchall():
     summary=recalculate_handicap(c,r['id']);last_attended=c.execute('SELECT MAX(g.date) FROM game_results r JOIN games g ON g.id=r.game_id WHERE r.member_id=? AND g.deleted_at IS NULL',(r['id'],)).fetchone()[0]
     members.append({'name':r['name'],'nickname':r['nickname'],'handicap':summary['handicap'],'handicap_basis':summary['basis'],'score_count':summary['count'],'last_attended':last_attended})
    return send({'members':members})
   if path=='/api/profile-join' and method=='POST':
    from datetime import datetime
    from zoneinfo import ZoneInfo
    name=str(body.get('name',''));game_id=str(body.get('game_id',''))
    c.execute('BEGIN IMMEDIATE')
    members=c.execute('SELECT id,active FROM members WHERE name=?',(name,)).fetchall()
    if len(members)!=1 or not members[0]['active']:raise ValueError('활동 회원을 확인해주세요.')
    game=c.execute('SELECT date FROM games WHERE id=? AND deleted_at IS NULL',(game_id,)).fetchone()
    if not game or (datetime.fromisoformat(game['date']).date()-datetime.now(ZoneInfo('Asia/Seoul')).date()).days<=3:raise ValueError('경기 3일 전부터 참석 변경이 마감됩니다.')
    member_id=members[0]['id']
    remove=body.get('remove',False)
    if type(remove)!=bool:raise ValueError('참석 여부를 확인해주세요.')
    if remove:
     if c.execute('SELECT 1 FROM game_results WHERE game_id=? AND member_id=?',(game_id,member_id)).fetchone():raise ValueError('결과 점수가 입력된 경기는 참석을 뺄 수 없습니다.')
     changed=c.execute('DELETE FROM game_participants WHERE game_id=? AND member_id=?',(game_id,member_id)).rowcount
    else:changed=c.execute('INSERT OR IGNORE INTO game_participants VALUES(?,?)',(game_id,member_id)).rowcount
    if changed:c.execute('DELETE FROM game_groupings WHERE game_id=?',(game_id,))
    return send({'ok':True,'attending':not remove})
   if path=='/api/courses' and method=='GET':return send(json.loads((ROOT/'golfzon-courses.json').read_text()))
   if not c.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?',(token_hash,now)).fetchone():return send({'error':'로그인이 필요합니다.'},'401 Unauthorized')
   if path=='/api/assistant' and method=='POST':
    question=str(body.get('question','')).strip()
    if not question or len(question)>500:return send({'error':'질문을 1~500자로 입력해주세요.'},'400 Bad Request')
    c.execute('CREATE TABLE IF NOT EXISTS assistant_usage(token TEXT NOT NULL,day TEXT NOT NULL,count INTEGER NOT NULL,PRIMARY KEY(token,day))')
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    used=c.execute('SELECT count FROM assistant_usage WHERE token=? AND day=?',(token_hash,today)).fetchone()
    if used and used['count']>=30:return send({'error':'AI 질문은 하루 30회까지 사용할 수 있습니다. 내일 다시 이용해주세요.'},'429 Too Many Requests')
    try:
     from ai_assistant import answer_question
     answer=answer_question(c,question,today)
    except RuntimeError as exc:return send({'error':str(exc)},'503 Service Unavailable')
    c.execute('INSERT INTO assistant_usage VALUES(?,?,1) ON CONFLICT(token,day) DO UPDATE SET count=count+1',(token_hash,today))
    c.execute('DELETE FROM assistant_usage WHERE day<?',(today,))
    return send({'answer':answer})
   if path=='/api/share-link' and method=='POST':
    token=secrets.token_urlsafe(32);token_hash=hashlib.sha256(token.encode()).hexdigest()
    c.execute("INSERT INTO settings VALUES('share_token_hash',?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",(token_hash,))
    return send({'token':token})
   if path=='/api/share-link' and method=='DELETE':
    c.execute("DELETE FROM settings WHERE id='share_token_hash'")
    return send({'ok':True})
   if path=='/api/logout' and method=='POST':c.execute('DELETE FROM sessions WHERE token=?',(token_hash,));return send({'ok':True},headers=[('Set-Cookie','smsg_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')])
   if path=='/api/settings/backup' and method=='GET':
    import datetime as dt
    raw=json.loads(Path('/opt/kiwoom/backup-status/smsg-status.json').read_text())
    now=dt.datetime.now(dt.timezone.utc); entries={}
    schedules={'github':'01:15','code':'01:20','data':'01:25','course_catalog':'01:30'}
    for key,schedule in schedules.items():
     item=raw.get(key,{}) if isinstance(raw,dict) else {}
     last=item.get('last_success'); entry={'status':'never','last_success':None,'file_count':None,'course_count':None,'schedule_kst':schedule}
     if type(item.get('file_count')) is int and item['file_count']>0: entry['file_count']=item['file_count']
     if type(item.get('course_count')) is int and item['course_count']>0: entry['course_count']=item['course_count']
     if isinstance(last,str):
      try:
       moment=dt.datetime.fromisoformat(last)
       if moment.tzinfo is not None and moment<=now+dt.timedelta(minutes=5):
        entry['last_success']=moment.isoformat()
        entry['status']='failed' if item.get('ok') is False else ('stale' if (now-moment).total_seconds()>=93600 else ('ok' if item.get('ok') is True else 'unavailable'))
       else: entry['status']='unavailable'
      except (ValueError,TypeError): entry['status']='unavailable'
     elif item.get('ok') is False: entry['status']='failed'
     entries[key]=entry
    return send({'smsg':entries})
   if path=='/api/game-history' and method=='GET':
    deleted=[dict(r) for r in c.execute('SELECT id,date,course,deleted_at FROM games WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT 100')]
    events=[dict(r) for r in c.execute('SELECT game_id,action,game_date,course,changed_at FROM game_change_log ORDER BY changed_at DESC,id DESC LIMIT 50')]
    return send({'deleted_games':deleted,'events':events})
   if path=='/api/settings' and method=='GET':return send({'handicap_period_months':get_handicap_period(c)})
   if path=='/api/settings' and method=='POST':
    period=body.get('handicap_period_months')
    if type(period) is not int or period not in (1,2,3,6,12):return send({'error':'핸디 계산 기간을 확인해주세요.'},'400 Bad Request')
    c.execute("INSERT INTO settings VALUES('handicap_period_months',?) ON CONFLICT(id) DO UPDATE SET value=excluded.value",(str(period),))
    ids=[r[0] for r in c.execute('SELECT id FROM members')]
    for member_id in ids:recalculate_handicap(c,member_id)
    return send({'ok':True,'handicap_period_months':period})
   if path=='/api/member-password' and method=='POST':
    username=str(body.get('username','')).strip().lower();current=str(body.get('current_password',''));new_password=str(body.get('new_password',''))
    if not username or len(username)>80 or not current or not 8<=len(new_password)<=128:raise ValueError('아이디와 현재 비밀번호를 확인하고 새 비밀번호는 8~128자로 입력해주세요.')
    user=c.execute('SELECT member_id,salt,password_hash FROM member_logins WHERE username=?',(username,)).fetchone()
    salt_hex=user['salt'] if user else '00000000000000000000000000000000';expected=user['password_hash'] if user else '0'*64
    actual=hashlib.pbkdf2_hmac('sha256',current.encode(),bytes.fromhex(salt_hex),600000).hex()
    if not user or not hmac.compare_digest(actual,expected):return send({'error':'아이디 또는 현재 비밀번호를 확인해주세요.'},'400 Bad Request')
    salt=secrets.token_bytes(16);password_hash=hashlib.pbkdf2_hmac('sha256',new_password.encode(),salt,600000).hex()
    c.execute('UPDATE member_logins SET salt=?,password_hash=? WHERE member_id=?',(salt.hex(),password_hash,user['member_id']))
    return send({'ok':True})
   if path=='/api/change-password' and method=='POST':
    return send({'error':'공용 비밀번호 변경은 사용할 수 없습니다.'},'410 Gone')
   if path=='/api/me' and method=='GET':
    account=c.execute('SELECT m.name FROM sessions s JOIN members m ON m.id=s.member_id WHERE s.token=? AND s.expires>?',(token_hash,now)).fetchone()
    return send({'name':account['name'] if account else None})
   if path=='/api/state' and method=='GET':
    return send(state_data(c,include_private=True))
   if path=='/api/games' and method=='POST':
    from datetime import date
    date.fromisoformat(body['date']);course=str(body.get('course','')).strip();fairway=body.get('fairway');green=body.get('green')
    if not course or len(course)>120 or any(type(n) not in (int,float) or not 0<=n<=5 or (n!=0 and n*2!=int(n*2)) for n in (fairway,green)):raise ValueError('경기장 이름과 난이도(1~5, 0.5 단위)를 확인해주세요.')
    note=body.get('note','')
    if not isinstance(note,str) or len(note)>1000:raise ValueError('비고는 1000자 이내로 입력해주세요.')
    id=str(body.get('id') or secrets.token_hex(16))
    c.execute('INSERT INTO games(id,date,course,fairway,green,deleted_at) VALUES(?,?,?,?,?,NULL) ON CONFLICT(id) DO UPDATE SET date=excluded.date,course=excluded.course,fairway=excluded.fairway,green=excluded.green',(id,body['date'],course,fairway,green))
    if 'note' in body:c.execute('INSERT INTO game_notes VALUES(?,?) ON CONFLICT(game_id) DO UPDATE SET note=excluded.note',(id,note))
    return send({'ok':True,'id':id})
   if path=='/api/games' and method=='DELETE':
    id=str(body['id']);c.execute('BEGIN IMMEDIATE')
    game=c.execute('SELECT date,course FROM games WHERE id=? AND deleted_at IS NULL',(id,)).fetchone()
    if not game:raise ValueError('경기를 찾을 수 없습니다.')
    ids=[r[0] for r in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(id,))]
    now=int(time.time())
    c.execute('UPDATE games SET deleted_at=? WHERE id=?',(now,id))
    c.execute('INSERT INTO game_change_log(game_id,action,game_date,course,changed_at) VALUES(?,?,?,?,?)',(id,'deleted',game['date'],game['course'],now))
    for member_id in ids:recalculate_handicap(c,member_id)
    return send({'ok':True})
   if path=='/api/games/restore' and method=='POST':
    id=str(body['id']);c.execute('BEGIN IMMEDIATE')
    game=c.execute('SELECT date,course FROM games WHERE id=? AND deleted_at IS NOT NULL',(id,)).fetchone()
    if not game:raise ValueError('복구할 경기를 찾을 수 없습니다.')
    ids=[r[0] for r in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(id,))]
    now=int(time.time())
    c.execute('UPDATE games SET deleted_at=NULL WHERE id=?',(id,))
    c.execute('INSERT INTO game_change_log(game_id,action,game_date,course,changed_at) VALUES(?,?,?,?,?)',(id,'restored',game['date'],game['course'],now))
    for member_id in ids:recalculate_handicap(c,member_id)
    return send({'ok':True})
   if path=='/api/game-participants' and method=='POST':
    id=str(body['id']);ids=body.get('ids')
    if not c.execute('SELECT 1 FROM games WHERE id=? AND deleted_at IS NULL',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
    if not isinstance(ids,list) or not all(isinstance(x,str) for x in ids) or len(ids)!=len(set(ids)):raise ValueError('참가 회원을 확인해주세요.')
    c.execute('BEGIN IMMEDIATE')
    previous={r[0] for r in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(id,))}
    if any(not c.execute('SELECT 1 FROM members WHERE id=? AND (active=1 OR id IN (SELECT member_id FROM game_participants WHERE game_id=?))',(x,id)).fetchone() for x in ids):raise ValueError('활동 회원만 추가할 수 있습니다.')
    if previous!=set(ids):c.execute('DELETE FROM game_groupings WHERE game_id=?',(id,))
    for member_id in previous-set(ids):
     c.execute('DELETE FROM game_participants WHERE game_id=? AND member_id=?',(id,member_id));recalculate_handicap(c,member_id)
    c.executemany('INSERT OR IGNORE INTO game_participants VALUES(?,?)',[(id,x) for x in ids]);return send({'ok':True})
   if path=='/api/game-groupings' and method=='PUT':
    id=str(body['id']);groups=body.get('groups')
    c.execute('BEGIN IMMEDIATE')
    if not c.execute('SELECT 1 FROM games WHERE id=? AND deleted_at IS NULL',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
    saved=c.execute('SELECT * FROM game_groupings WHERE game_id=?',(id,)).fetchone()
    if not saved:raise ValueError('먼저 조편성을 만들어주세요.')
    if not isinstance(groups,list) or len(groups)!=saved['group_count'] or any(not isinstance(g,list) or len(g)!=saved['group_size'] for g in groups):raise ValueError(f"각 조는 {saved['group_size']}명으로 맞춰주세요.")
    ids=[mid for g in groups for mid in g]
    if not all(isinstance(mid,str) for mid in ids) or len(ids)!=len(set(ids)):raise ValueError('회원이 중복 배정되었습니다.')
    participants={r[0] for r in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(id,))}
    snapshots={m['id']:m for g in json.loads(saved['groups_json']) for m in g}
    if set(ids)!=participants or set(ids)!=set(snapshots):raise ValueError('현재 참가 회원을 빠짐없이 배정해주세요. 참가자가 바뀌면 다시 편성해야 합니다.')
    updated=[[snapshots[mid] for mid in g] for g in groups]
    c.execute('UPDATE game_groupings SET groups_json=? WHERE game_id=?',(json.dumps(updated,ensure_ascii=False),id));return send({'ok':True,'groups':updated})
   if path=='/api/game-groupings' and method=='POST':
    id=str(body['id']);count=body.get('group_count');size=body.get('group_size')
    if type(count)!=int or type(size)!=int or not 1<=count<=32 or not 1<=size<=20:raise ValueError('조 수(1~32)와 조당 인원(1~20)을 확인해주세요.')
    c.execute('BEGIN IMMEDIATE')
    if not c.execute('SELECT 1 FROM games WHERE id=? AND deleted_at IS NULL',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
    members=[]
    for row in c.execute('SELECT m.id,m.name,m.handicap FROM members m JOIN game_participants p ON p.member_id=m.id WHERE p.game_id=? ORDER BY m.id',(id,)):
     member=dict(row);summary=recalculate_handicap(c,member['id']);member['handicap']=summary['handicap'];member['handicap_basis']=summary['basis'];members.append(member)
    if not members or len(members)>128 or len(members)!=count*size:raise ValueError(f'참가자는 {len(members)}명입니다. 조 수 × 조당 인원이 참가자 수와 같아야 합니다.')
    groups=fair_game_groups(members,count,size)
    if count in (2,3,4,5):
     note=c.execute('SELECT note FROM game_notes WHERE game_id=?',(id,)).fetchone()
     replaceable=('',MEAL_NOTE_2,MEAL_NOTE_3,MEAL_NOTE_4,MEAL_NOTE_5)
     if count==5:replaceable+=(MEAL_NOTE_5_OLD_DEFAULT,MEAL_NOTE_5_OLD_CUSTOM)
     if not note or note[0] in replaceable:c.execute('INSERT INTO game_notes VALUES(?,?) ON CONFLICT(game_id) DO UPDATE SET note=excluded.note',(id,{2:MEAL_NOTE_2,3:MEAL_NOTE_3,4:MEAL_NOTE_4,5:MEAL_NOTE_5}[count]))
    c.execute('INSERT INTO game_groupings VALUES(?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET groups_json=excluded.groups_json,group_count=excluded.group_count,group_size=excluded.group_size',(id,json.dumps(groups,ensure_ascii=False),count,size));return send({'ok':True,'groups':groups})
   if path=='/api/game-result-image' and method=='POST':
    id=str(body.get('id',''));data_urls=body.get('images',body.get('image',''))
    game=c.execute('SELECT id,date,course FROM games WHERE id=? AND deleted_at IS NULL',(id,)).fetchone()
    if not game:raise ValueError('경기를 찾을 수 없습니다.')
    if isinstance(data_urls,str):data_urls=[data_urls]
    if not isinstance(data_urls,list) or not 1<=len(data_urls)<=6 or sum(len(x) for x in data_urls if isinstance(x,str))>5*1024*1024:raise ValueError('스크린샷은 1~6장, 전체 5MB 이하로 선택해주세요.')
    import base64,binascii
    total_image_bytes=0
    for data_url in data_urls:
     if not isinstance(data_url,str):raise ValueError('이미지 파일을 확인해주세요.')
     match=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/]+={0,2})',data_url)
     if not match:raise ValueError('JPG, PNG, WEBP 이미지 파일을 선택해주세요.')
     try:image_bytes=base64.b64decode(match.group(2),validate=True)
     except (ValueError,binascii.Error):raise ValueError('이미지 파일을 읽을 수 없습니다.') from None
     if not image_bytes:raise ValueError('이미지 파일을 읽을 수 없습니다.')
     total_image_bytes+=len(image_bytes)
    if total_image_bytes>5*1024*1024:raise ValueError('스크린샷 전체 크기는 5MB 이하로 선택해주세요.')
    participants=[]
    for row in c.execute('SELECT m.id,m.name,m.nickname FROM members m JOIN game_participants p ON p.member_id=m.id WHERE p.game_id=? ORDER BY m.name',(id,)):
     participants.append(dict(row))
    if not participants:raise ValueError('이 경기에 참가 회원이 없습니다.')
    from golfzon_results import compare_game_headers,recognize_scores
    try:
     parsed=recognize_scores(data_urls,dict(game),participants)
     parsed['game_info_check']=compare_game_headers(parsed.get('game_headers'),dict(game))
    except RuntimeError as exc:return send({'error':str(exc)},'503 Service Unavailable')
    return send(parsed)
   if path=='/api/game-results-bulk' and method=='POST':
    id=str(body.get('id',''));scores=body.get('scores')
    if body.get('verified_game_info') is not True:raise ValueError('캡처의 경기 날짜와 경기장을 확인한 뒤 다시 저장해주세요.')
    if not isinstance(scores,list) or not scores or len(scores)>128:raise ValueError('저장할 결과 점수를 확인해주세요.')
    if any(not isinstance(item,dict) or not isinstance(item.get('member_id'),str) or type(item.get('score')) not in (int,float) or not math.isfinite(item['score']) or not -100<=item['score']<=300 for item in scores):raise ValueError('결과 점수는 -100~300 사이의 숫자로 입력해주세요.')
    ids=[item['member_id'] for item in scores]
    if len(ids)!=len(set(ids)):raise ValueError('회원이 중복되었습니다. 결과를 확인해주세요.')
    c.execute('BEGIN IMMEDIATE')
    if not c.execute('SELECT 1 FROM games WHERE id=? AND deleted_at IS NULL',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
    participants={r[0] for r in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(id,))}
    if not set(ids)<=participants:raise ValueError('경기 참가 회원만 저장할 수 있습니다.')
    for item in scores:
     member_id=item['member_id'];m=c.execute('SELECT handicap FROM members WHERE id=?',(member_id,)).fetchone()
     c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('handicap_initial:'+member_id,str(m['handicap'])))
     c.execute('INSERT INTO game_results VALUES(?,?,?) ON CONFLICT(game_id,member_id) DO UPDATE SET score=excluded.score',(id,member_id,item['score']))
    for member_id in ids:recalculate_handicap(c,member_id)
    return send({'ok':True,'saved':len(scores)})
   if path=='/api/game-results' and method=='POST':
    id=str(body['id']);member_id=str(body['member_id']);score=body.get('score')
    if score is not None and (type(score) not in (int,float) or not math.isfinite(score) or not -100<=score<=300):raise ValueError('결과 점수는 -100~300 사이의 숫자로 입력해주세요.')
    c.execute('BEGIN IMMEDIATE')
    if not c.execute('SELECT 1 FROM games WHERE id=? AND deleted_at IS NULL',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
    if not c.execute('SELECT 1 FROM game_participants WHERE game_id=? AND member_id=?',(id,member_id)).fetchone():raise ValueError('이 경기의 참가 회원이 아닙니다.')
    m=c.execute('SELECT handicap FROM members WHERE id=?',(member_id,)).fetchone()
    c.execute('INSERT OR IGNORE INTO settings VALUES(?,?)',('handicap_initial:'+member_id,str(m['handicap'])))
    if score is None:c.execute('DELETE FROM game_results WHERE game_id=? AND member_id=?',(id,member_id))
    else:c.execute('INSERT INTO game_results VALUES(?,?,?) ON CONFLICT(game_id,member_id) DO UPDATE SET score=excluded.score',(id,member_id,score))
    summary=recalculate_handicap(c,member_id);hd=c.execute('SELECT handicap FROM members WHERE id=?',(member_id,)).fetchone()[0]
    return send({'ok':True,'handicap':hd,'score_count':summary['count']})
   if path=='/api/members' and method=='POST':
    name=str(body.get('name','')).strip();hd=float(body.get('handicap',0));note=str(body.get('note',''))[:1000]
    if not name or len(name)>80 or not math.isfinite(hd) or not -100<=hd<=300:raise ValueError('이름과 핸디(-100~300)를 확인해주세요.')
    id=str(body.get('id') or secrets.token_hex(16));existing=c.execute('SELECT phone,nickname FROM members WHERE id=?',(id,)).fetchone();raw_phone=body.get('phone');raw_nickname=body.get('nickname')
    if raw_phone is None:
     phone=existing['phone'] if existing else ''
    else:
     raw_phone=str(raw_phone).strip()
     digits=re.sub(r'\D','',raw_phone)
     if digits.startswith('82'):digits=digits[2:]
     if digits.startswith('10'):digits='0'+digits
     if digits and (len(digits)!=11 or not digits.startswith('010')):raise ValueError('연락처는 010-1234-5678 형식으로 입력해주세요.')
     phone=f'{digits[:3]}-{digits[3:7]}-{digits[7:]}' if digits else ''
    nickname=(existing['nickname'] if existing else '') if raw_nickname is None else str(raw_nickname).strip()
    if len(nickname)>80:raise ValueError('골프존 닉네임은 80자 이내로 입력해주세요.')
    c.execute('INSERT INTO members(id,name,handicap,note,active,phone,nickname) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,handicap=excluded.handicap,note=excluded.note,active=excluded.active,phone=excluded.phone,nickname=excluded.nickname',(id,name,hd,note,1 if body.get('active',True) else 0,phone,nickname));recalculate_handicap(c,id);return send({'ok':True})
   if path=='/api/meals' and method=='POST':
    from datetime import date
    date.fromisoformat(body['date']);place=str(body['place']).strip()
    if not place or len(place)>120:raise ValueError('장소를 확인해주세요.')
    numbers=[body.get(k,0) for k in ['people','income','extra','expense']]
    if not all(type(n)==int and 0<=n<=1000000000 for n in numbers) or numbers[0]>10000:raise ValueError('인원과 금액을 확인해주세요.')
    id=str(body.get('id') or secrets.token_hex(16));c.execute('INSERT INTO meals VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET date=excluded.date,place=excluded.place,people=excluded.people,income=excluded.income,extra=excluded.extra,expense=excluded.expense,note=excluded.note',(id,body['date'],place,*numbers,str(body.get('note',''))[:1000],time.time_ns()));return send({'ok':True})
   if path=='/api/meals' and method=='DELETE':c.execute('DELETE FROM meals WHERE id=?',(str(body['id']),));return send({'ok':True})
   if path=='/api/rounds' and method=='POST':
    from datetime import date
    date.fromisoformat(body['date']);size=int(body.get('size',4));ids=body['ids']
    if size not in [2,3,4] or not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('참가자와 조 인원을 확인해주세요.')
    members=[]
    for id in ids:
     row=c.execute('SELECT * FROM members WHERE id=? AND active=1',(id,)).fetchone()
     if row:
      member=dict(row);member.pop('phone',None);summary=recalculate_handicap(c,id);member['handicap']=summary['handicap'];member['handicap_basis']=summary['basis'];members.append(member)
    if len(members)!=len(ids):raise ValueError('등록된 활동 멤버만 선택할 수 있습니다.')
    groups=balanced_groups(members,size);c.execute('INSERT OR REPLACE INTO rounds VALUES(?,?)',(body['date'],json.dumps(groups,ensure_ascii=False)));return send({'ok':True,'groups':groups})
   return send({'error':'지원하지 않는 요청입니다.'},'404 Not Found')
 except (ValueError,KeyError,TypeError) as e:return send({'error':str(e) or '입력을 확인해주세요.'},'400 Bad Request')
 except Exception:return send({'error':'서버 오류가 발생했습니다. 다시 시도해주세요.'},'500 Internal Server Error')

init()
if __name__=='__main__':
 from wsgiref.simple_server import make_server
 print('Local preview: http://127.0.0.1:8091')
 make_server('127.0.0.1',8091,application).serve_forever()
