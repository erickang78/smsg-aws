#!/opt/smsg/venv/bin/python
import datetime,json,os,secrets,socketserver,sys,time
from pathlib import Path
sys.path.insert(0,"/opt/kiwoom/current")
import kakao_notifications as kakao
SOCKET=Path("/run/smsg-kakao-login/bridge.sock")
class Server(socketserver.ThreadingUnixStreamServer):
 daemon_threads=True
 allow_reuse_address=True
class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  try:
   raw=self.rfile.readline(2049)
   if not raw or len(raw)>2048:raise ValueError("invalid_request")
   body=json.loads(raw.decode("utf-8"));action=body.get("action","enqueue")
   if action=="status":
    state=kakao.control({"action":"status"})
    result={"ok":True,"configured":state.get("configured",False),"connected":state.get("connected",False)}
   elif action=="enqueue":
    username="".join(ch for ch in str(body.get("username","")).strip() if ch.isprintable() and ch not in "\r\n\t")[:64]
    if not username:raise ValueError("invalid_username")
    now=time.time();kst=datetime.timezone(datetime.timedelta(hours=9));when=datetime.datetime.fromtimestamp(now,kst).strftime("%Y-%m-%d %H:%M:%S")
    with kakao.locked() as db:
     config=kakao.load(db)
     if not config.get("connected"):result={"ok":True,"queued":False,"reason":"not_connected"}
     else:
      event_id=-secrets.randbelow(1_000_000_000_000_000)-1
      text="[일조해 로그인 알림]\n계정: "+username+"\n로그인 시각: "+when+" (한국시간)"
      db.execute("INSERT INTO queue(intent,qty,text,status) VALUES(?,0,?,'pending')",(event_id,text));db.commit()
      result={"ok":True,"queued":True}
   payload=json.dumps(result,ensure_ascii=False).encode("utf-8")+b"\n"
   self.wfile.write(payload)
  except Exception as error:
   payload=json.dumps({"ok":False,"reason":type(error).__name__}).encode()+b"\n"
   try:self.wfile.write(payload)
   except OSError:pass
ThreadedServer=Server
if __name__=="__main__":
 SOCKET.parent.mkdir(parents=True,exist_ok=True)
 try:SOCKET.unlink()
 except FileNotFoundError:pass
 with ThreadedServer(str(SOCKET),Handler) as server:
  os.chmod(SOCKET,0o660)
  server.serve_forever()
