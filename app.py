import os,json,sqlite3,secrets,hashlib,hmac,time,re,math
from pathlib import Path
from http.cookies import SimpleCookie
ROOT=Path(__file__).parent
DB=Path(os.environ.get('SMSG_DB',str(ROOT/'data'/'smsg.sqlite3')))

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
CREATE TABLE IF NOT EXISTS games(id TEXT PRIMARY KEY,date TEXT NOT NULL,course TEXT NOT NULL,fairway INTEGER NOT NULL,green INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS game_participants(game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,member_id TEXT NOT NULL REFERENCES members(id),PRIMARY KEY(game_id,member_id));
CREATE TABLE IF NOT EXISTS historical_scores(member_id TEXT NOT NULL REFERENCES members(id),position INTEGER NOT NULL,score REAL NOT NULL,PRIMARY KEY(member_id,position));
CREATE TABLE IF NOT EXISTS game_results(game_id TEXT NOT NULL,member_id TEXT NOT NULL,score REAL NOT NULL,PRIMARY KEY(game_id,member_id),FOREIGN KEY(game_id,member_id) REFERENCES game_participants(game_id,member_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,name TEXT NOT NULL,handicap REAL NOT NULL,note TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS meals(id TEXT PRIMARY KEY,date TEXT NOT NULL,place TEXT NOT NULL,people INTEGER NOT NULL,income INTEGER NOT NULL,extra INTEGER NOT NULL,expense INTEGER NOT NULL,note TEXT NOT NULL,position INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS rounds(date TEXT PRIMARY KEY,groups_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(ip TEXT PRIMARY KEY,count INTEGER NOT NULL,reset INTEGER NOT NULL);''')
  c.execute('BEGIN IMMEDIATE')
  if not c.execute("SELECT 1 FROM settings WHERE id='seeded'").fetchone():
   for i,r in enumerate(json.loads((ROOT/'seed.json').read_text())):
    c.execute('INSERT INTO meals VALUES(?,?,?,?,?,?,?,?,?)',tuple(r[k] for k in ['id','date','place','people','income','extra','expense','note'])+(i,))
   c.execute("INSERT INTO settings VALUES('opening','0')");c.execute("INSERT INTO settings VALUES('seeded','1')")

def records(c):
 rows=[dict(r) for r in c.execute('SELECT * FROM meals ORDER BY date,position,id')];balance=int(c.execute("SELECT value FROM settings WHERE id='opening'").fetchone()[0])
 for r in rows:r['settlement']=r['income']-r['expense'];balance+=r['settlement']+r['extra'];r['balance']=balance
 return rows,balance

def score_summary(c,member_id):
 row=c.execute('SELECT COUNT(*) AS count,COALESCE(SUM(score),0) AS total FROM (SELECT score FROM historical_scores WHERE member_id=? UNION ALL SELECT score FROM game_results WHERE member_id=?)',(member_id,member_id)).fetchone()
 return dict(row)

def recalculate_handicap(c,member_id):
 from decimal import Decimal,ROUND_HALF_UP
 summary=score_summary(c,member_id)
 if summary['count']:
  hd=float((Decimal(str(summary['total']))/Decimal(summary['count'])).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP))
  c.execute('UPDATE members SET handicap=? WHERE id=?',(hd,member_id))
 else:
  initial=c.execute("SELECT value FROM settings WHERE id=?",('handicap_initial:'+member_id,)).fetchone()
  if initial:c.execute('UPDATE members SET handicap=? WHERE id=?',(float(initial[0]),member_id))
 return summary

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
 if method=='GET' and path.count('/')==1 and path not in ['/','/health']:
  with connect() as c:profile_page=c.execute('SELECT 1 FROM members WHERE name=?',(path[1:],)).fetchone() is not None
 if (path in ['/','/static/app.js','/static/style.css'] or profile_page) and method=='GET':
  filename='index.html' if path=='/' or profile_page else path.split('/')[-1];ctype={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[filename]
  start_response('200 OK',[('Content-Type',ctype),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]);return [(ROOT/'static'/filename).read_bytes()]
 if path=='/health' and method=='GET':return send({'ok':True})
 if not path.startswith('/api/'):return send({'error':'페이지를 찾을 수 없습니다.'},'404 Not Found')
 try:
  length=int(environ.get('CONTENT_LENGTH') or 0)
  if length>65536:return send({'error':'입력 크기가 너무 큽니다.'},'413 Content Too Large')
  body=json.loads(environ['wsgi.input'].read(length) or b'{}') if method!='GET' else {}
  if method!='GET':
   origin=environ.get('HTTP_ORIGIN');expected=environ['wsgi.url_scheme']+'://'+environ.get('HTTP_HOST','')
   if origin!=expected:return send({'error':'허용되지 않은 요청입니다.'},'403 Forbidden')
  with connect() as c:
   cookies=SimpleCookie();cookies.load(environ.get('HTTP_COOKIE',''));token=cookies['smsg_session'].value if 'smsg_session' in cookies else '';token_hash=hashlib.sha256(token.encode()).hexdigest();now=int(time.time())
   if path=='/api/login' and method=='POST':
    ip=environ.get('REMOTE_ADDR','unknown');a=c.execute('SELECT * FROM attempts WHERE ip=?',(ip,)).fetchone()
    if a and a['reset']>now and a['count']>=10:return send({'error':'잠시 후 다시 로그인해주세요.'},'429 Too Many Requests')
    spec=os.environ.get('SMSG_PASSWORD_HASH','')
    if not spec:return send({'error':'서버 관리자가 로그인 비밀번호를 설정해야 합니다.'},'503 Service Unavailable')
    salt,expected_hash=spec.split(':');actual=hashlib.pbkdf2_hmac('sha256',str(body.get('password','')).encode(),bytes.fromhex(salt),600000).hex()
    if not hmac.compare_digest(actual,expected_hash):
     count=a['count']+1 if a and a['reset']>now else 1;c.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(ip,count,now+900 if count==1 else a['reset']));return send({'error':'비밀번호를 확인해주세요.'},'401 Unauthorized')
    c.execute('DELETE FROM attempts WHERE ip=?',(ip,));c.execute('DELETE FROM sessions WHERE expires<?',(now,));token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?)',(hashlib.sha256(token.encode()).hexdigest(),now+86400))
    return send({'ok':True},headers=[('Set-Cookie','smsg_session='+token+'; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400'+('; Secure' if environ['wsgi.url_scheme']=='https' else ''))])
   if path=='/api/profile' and method=='GET':
    from urllib.parse import parse_qs
    name=parse_qs(environ.get('QUERY_STRING','')).get('name',[''])[0]
    matches=c.execute('SELECT * FROM members WHERE name=?',(name,)).fetchall()
    if len(matches)!=1:return send({'error':'회원을 찾을 수 없거나 같은 이름의 회원이 여러 명입니다.'},'404 Not Found')
    member=dict(matches[0]);id=member['id']
    games=[dict(r) for r in c.execute('SELECT g.id,g.date,g.course,r.score FROM games g JOIN game_results r ON r.game_id=g.id WHERE r.member_id=? ORDER BY g.date DESC,g.id',(id,))]
    member.update(score_count=score_summary(c,id)['count'],last_attended=games[0]['date'] if games else None)
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    upcoming=[dict(r) for r in c.execute('SELECT g.id,g.date,g.course,g.fairway,g.green,EXISTS(SELECT 1 FROM game_participants p WHERE p.game_id=g.id AND p.member_id=?) AS attending,EXISTS(SELECT 1 FROM game_results r WHERE r.game_id=g.id AND r.member_id=?) AS has_result FROM games g WHERE g.date>=? ORDER BY g.date,g.id',(id,id,today))]
    return send({'member':member,'games':games,'upcoming':upcoming})
   if path=='/api/profile-join' and method=='POST':
    from datetime import datetime
    from zoneinfo import ZoneInfo
    name=str(body.get('name',''));game_id=str(body.get('game_id',''))
    c.execute('BEGIN IMMEDIATE')
    members=c.execute('SELECT id,active FROM members WHERE name=?',(name,)).fetchall()
    if len(members)!=1 or not members[0]['active']:raise ValueError('활동 회원을 확인해주세요.')
    game=c.execute('SELECT date FROM games WHERE id=?',(game_id,)).fetchone()
    if not game or game['date']<datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat():raise ValueError('오늘 이후 경기만 참가할 수 있습니다.')
    member_id=members[0]['id']
    remove=body.get('remove',False)
    if type(remove)!=bool:raise ValueError('참석 여부를 확인해주세요.')
    if remove:
     if c.execute('SELECT 1 FROM game_results WHERE game_id=? AND member_id=?',(game_id,member_id)).fetchone():raise ValueError('결과 점수가 입력된 경기는 참석을 뺄 수 없습니다.')
     changed=c.execute('DELETE FROM game_participants WHERE game_id=? AND member_id=?',(game_id,member_id)).rowcount
    else:changed=c.execute('INSERT OR IGNORE INTO game_participants VALUES(?,?)',(game_id,member_id)).rowcount
    if changed:c.execute('DELETE FROM game_groupings WHERE game_id=?',(game_id,))
    return send({'ok':True,'attending':not remove})
   if not c.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?',(token_hash,now)).fetchone():return send({'error':'로그인이 필요합니다.'},'401 Unauthorized')
   if path=='/api/logout' and method=='POST':c.execute('DELETE FROM sessions WHERE token=?',(token_hash,));return send({'ok':True},headers=[('Set-Cookie','smsg_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')])
   if path=='/api/state' and method=='GET':
    meals,balance=records(c);return send({'members':[dict(r,score_count=score_summary(c,r['id'])['count'],last_attended=c.execute('SELECT MAX(g.date) FROM game_results r JOIN games g ON g.id=r.game_id WHERE r.member_id=?',(r['id'],)).fetchone()[0]) for r in c.execute('SELECT * FROM members ORDER BY name')],'meals':meals,'rounds':[dict(r) for r in c.execute('SELECT * FROM rounds ORDER BY date DESC')],'games':[dict(r,note=(lambda row:row[0] if row else '')(c.execute('SELECT note FROM game_notes WHERE game_id=?',(r['id'],)).fetchone()),grouping=(lambda row:dict(row,groups=json.loads(row['groups_json'])) if row else None)(c.execute('SELECT * FROM game_groupings WHERE game_id=?',(r['id'],)).fetchone()),results={x['member_id']:x['score'] for x in c.execute('SELECT member_id,score FROM game_results WHERE game_id=?',(r['id'],))},participants=[x[0] for x in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(r['id'],))]) for r in c.execute('SELECT * FROM games ORDER BY date DESC,rowid DESC')],'opening':0,'balance':balance})
   if path=='/api/games' and method=='POST':
    from datetime import date
    date.fromisoformat(body['date']);course=str(body.get('course','')).strip();fairway=body.get('fairway');green=body.get('green')
    if not course or len(course)>120 or any(type(n)!=int or not 0<=n<=5 for n in (fairway,green)):raise ValueError('경기장 이름과 난이도(1~5)를 확인해주세요.')
    note=body.get('note','')
    if not isinstance(note,str) or len(note)>1000:raise ValueError('비고는 1000자 이내로 입력해주세요.')
    id=str(body.get('id') or secrets.token_hex(16))
    c.execute('INSERT INTO games VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET date=excluded.date,course=excluded.course,fairway=excluded.fairway,green=excluded.green',(id,body['date'],course,fairway,green))
    if 'note' in body:c.execute('INSERT INTO game_notes VALUES(?,?) ON CONFLICT(game_id) DO UPDATE SET note=excluded.note',(id,note))
    return send({'ok':True,'id':id})
   if path=='/api/games' and method=='DELETE':
    id=str(body['id']);c.execute('BEGIN IMMEDIATE')
    if not c.execute('SELECT 1 FROM games WHERE id=?',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
    ids=[r[0] for r in c.execute('SELECT member_id FROM game_participants WHERE game_id=?',(id,))]
    c.execute('DELETE FROM games WHERE id=?',(id,))
    for member_id in ids:recalculate_handicap(c,member_id)
    return send({'ok':True})
   if path=='/api/game-participants' and method=='POST':
    id=str(body['id']);ids=body.get('ids')
    if not c.execute('SELECT 1 FROM games WHERE id=?',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
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
    if not c.execute('SELECT 1 FROM games WHERE id=?',(id,)).fetchone():raise ValueError('경기를 찾을 수 없습니다.')
    members=[dict(r) for r in c.execute('SELECT m.id,m.name,m.handicap FROM members m JOIN game_participants p ON p.member_id=m.id WHERE p.game_id=? ORDER BY m.id',(id,))]
    if not members or len(members)>128 or len(members)!=count*size:raise ValueError(f'참가자는 {len(members)}명입니다. 조 수 × 조당 인원이 참가자 수와 같아야 합니다.')
    groups=fair_game_groups(members,count,size)
    if count in (3,4):
     note=c.execute('SELECT note FROM game_notes WHERE game_id=?',(id,)).fetchone()
     if not note or note[0] in ('',MEAL_NOTE_3,MEAL_NOTE_4):c.execute('INSERT INTO game_notes VALUES(?,?) ON CONFLICT(game_id) DO UPDATE SET note=excluded.note',(id,MEAL_NOTE_4 if count==4 else MEAL_NOTE_3))
    c.execute('INSERT INTO game_groupings VALUES(?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET groups_json=excluded.groups_json,group_count=excluded.group_count,group_size=excluded.group_size',(id,json.dumps(groups,ensure_ascii=False),count,size));return send({'ok':True,'groups':groups})
   if path=='/api/game-results' and method=='POST':
    id=str(body['id']);member_id=str(body['member_id']);score=body.get('score')
    if score is not None and (type(score) not in (int,float) or not math.isfinite(score) or not -100<=score<=300):raise ValueError('결과 점수는 -100~300 사이의 숫자로 입력해주세요.')
    c.execute('BEGIN IMMEDIATE')
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
    id=str(body.get('id') or secrets.token_hex(16));c.execute('INSERT INTO members VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,handicap=excluded.handicap,note=excluded.note,active=excluded.active',(id,name,hd,note,1 if body.get('active',True) else 0));recalculate_handicap(c,id);return send({'ok':True})
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
    members=[dict(c.execute('SELECT * FROM members WHERE id=? AND active=1',(id,)).fetchone() or {}) for id in ids]
    if any(not m for m in members):raise ValueError('등록된 활동 멤버만 선택할 수 있습니다.')
    groups=balanced_groups(members,size);c.execute('INSERT OR REPLACE INTO rounds VALUES(?,?)',(body['date'],json.dumps(groups,ensure_ascii=False)));return send({'ok':True,'groups':groups})
   return send({'error':'지원하지 않는 요청입니다.'},'404 Not Found')
 except (ValueError,KeyError,TypeError) as e:return send({'error':str(e) or '입력을 확인해주세요.'},'400 Bad Request')
 except Exception:return send({'error':'서버 오류가 발생했습니다. 다시 시도해주세요.'},'500 Internal Server Error')

init()
if __name__=='__main__':
 from wsgiref.simple_server import make_server
 print('Local preview: http://127.0.0.1:8091')
 make_server('127.0.0.1',8091,application).serve_forever()
