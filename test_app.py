import tempfile,os,json,io,hashlib,unittest
from pathlib import Path
_tmp=tempfile.TemporaryDirectory();os.environ['SMSG_DB']=str(Path(_tmp.name)/'test.sqlite3')
salt=b'unit-test-only!!';os.environ['SMSG_PASSWORD_HASH']=salt.hex()+':'+hashlib.pbkdf2_hmac('sha256',b'test password',salt,600000).hex()
import app
class Flow(unittest.TestCase):
 def call(self,path,method='GET',body=None,cookie='',origin='https://smsg.test'):
  payload=json.dumps(body or {}).encode();capture={}
  env={'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(payload)),'wsgi.input':io.BytesIO(payload),'wsgi.url_scheme':'https','HTTP_HOST':'smsg.test','HTTP_ORIGIN':origin,'HTTP_COOKIE':cookie,'REMOTE_ADDR':'127.0.0.2'}
  def start(s,h):capture.update(status=s,headers=dict(h))
  data=b''.join(app.application(env,start));return capture,json.loads(data)
 def test_full_flow(self):
  self.assertEqual(self.call('/api/state')[0]['status'],'401 Unauthorized')
  self.assertEqual(self.call('/api/login','POST',{'password':'bad'})[0]['status'],'401 Unauthorized')
  result,data=self.call('/api/login','POST',{'password':'test password'});self.assertEqual(result['status'],'200 OK');self.assertIn('Secure',result['headers']['Set-Cookie']);cookie=result['headers']['Set-Cookie'].split(';')[0]
  data=self.call('/api/state',cookie=cookie)[1];self.assertEqual(len(data['meals']),0);self.assertEqual(data['balance'],0)
  app.init();self.assertEqual(len(self.call('/api/state',cookie=cookie)[1]['meals']),0)
  self.assertEqual(self.call('/api/members','POST',{'name':'A','handicap':10},cookie,origin='https://evil.test')[0]['status'],'403 Forbidden')
  for i in range(9):self.assertEqual(self.call('/api/members','POST',{'id':str(i),'name':'Member '+str(i),'handicap':i*3},cookie)[0]['status'],'200 OK')
  ids=[str(i) for i in range(9)];g=self.call('/api/rounds','POST',{'date':'2026-10-18','ids':ids,'size':4},cookie)[1]['groups'];self.assertEqual([len(x) for x in g],[3,3,3]);self.assertEqual(len({m['id'] for x in g for m in x}),9)
  bad=self.call('/api/rounds','POST',{'date':'2026-10-18','ids':['0','0'],'size':4},cookie);self.assertEqual(bad[0]['status'],'400 Bad Request')
  meal={'id':'new','date':'2026-10-18','place':'Test','people':4,'income':100000,'extra':300,'expense':90000,'note':''}
  self.assertEqual(self.call('/api/meals','POST',meal,cookie)[0]['status'],'200 OK');self.assertEqual(self.call('/api/state',cookie=cookie)[1]['balance'],10300)
  meal['expense']=95000;self.call('/api/meals','POST',meal,cookie);self.assertEqual(self.call('/api/state',cookie=cookie)[1]['balance'],5300)
  self.call('/api/meals','DELETE',{'id':'new'},cookie);app.init();self.assertEqual(self.call('/api/state',cookie=cookie)[1]['balance'],0)
  self.call('/api/logout','POST',{},cookie);self.assertEqual(self.call('/api/state',cookie=cookie)[0]['status'],'401 Unauthorized')
if __name__=='__main__':unittest.main()
