import tempfile,os,json,io,hashlib,unittest
from pathlib import Path
_tmp=tempfile.TemporaryDirectory();os.environ['SMSG_DB']=str(Path(_tmp.name)/'test.sqlite3')
salt=b'unit-test-only!!';os.environ['SMSG_PASSWORD_HASH']=salt.hex()+':'+hashlib.pbkdf2_hmac('sha256',b'test password',salt,600000).hex()
import app
class Flow(unittest.TestCase):
 def call(self,path,method='GET',body=None,cookie='',origin='https://smsg.test',auth=''):
  payload=json.dumps(body or {}).encode();capture={}
  env={'PATH_INFO':path,'REQUEST_METHOD':method,'CONTENT_LENGTH':str(len(payload)),'wsgi.input':io.BytesIO(payload),'wsgi.url_scheme':'https','HTTP_HOST':'smsg.test','HTTP_ORIGIN':origin,'HTTP_COOKIE':cookie,'HTTP_AUTHORIZATION':auth,'REMOTE_ADDR':'127.0.0.2'}
  def start(s,h):capture.update(status=s,headers=dict(h))
  data=b''.join(app.application(env,start));return capture,json.loads(data)
 def test_public_member_directory_route(self):
  def page(path):
   capture={};env={'PATH_INFO':path,'REQUEST_METHOD':'GET','CONTENT_LENGTH':'0','wsgi.input':io.BytesIO(),'wsgi.url_scheme':'https','HTTP_HOST':'smsg.test'}
   def start(status,headers):capture.update(status=status,headers=dict(headers))
   body=b''.join(app.application(env,start));return capture,body
  status,body=page('/members');self.assertEqual(status['status'],'200 OK');self.assertIn(b'id="app"',body)
  status,body=page('/shared');self.assertEqual(status['status'],'200 OK');self.assertIn(b'id="shared-content"',body)
  status,_=page('/member');self.assertEqual(status['status'],'301 Moved Permanently');self.assertEqual(status['headers']['Location'],'/members')
 def test_full_flow(self):
  self.assertEqual(self.call('/api/state')[0]['status'],'401 Unauthorized')
  self.assertEqual(self.call('/api/change-password','POST',{'current_password':'test password','new_password':'another pass'})[0]['status'],'401 Unauthorized')
  self.assertEqual(self.call('/api/share-link','POST',{})[0]['status'],'401 Unauthorized')
  self.assertEqual(self.call('/api/login','POST',{'password':'bad'})[0]['status'],'401 Unauthorized')
  result,data=self.call('/api/login','POST',{'password':'test password'});self.assertEqual(result['status'],'200 OK');self.assertIn('Secure',result['headers']['Set-Cookie']);cookie=result['headers']['Set-Cookie'].split(';')[0]
  self.assertEqual(self.call('/api/change-password','POST',{'current_password':'bad','new_password':'another pass'},cookie)[0]['status'],'400 Bad Request')
  self.assertEqual(self.call('/api/change-password','POST',{'current_password':'test password','new_password':'short'},cookie)[0]['status'],'400 Bad Request')
  data=self.call('/api/state',cookie=cookie)[1];self.assertEqual(len(data['meals']),0);self.assertEqual(data['balance'],0)
  app.init();self.assertEqual(len(self.call('/api/state',cookie=cookie)[1]['meals']),0)
  self.assertEqual(self.call('/api/members','POST',{'name':'A','handicap':10},cookie,origin='https://evil.test')[0]['status'],'403 Forbidden')
  for i in range(9):self.assertEqual(self.call('/api/members','POST',{'id':str(i),'name':'Member '+str(i),'handicap':i*3},cookie)[0]['status'],'200 OK')
  token_data=self.call('/api/share-link','POST',{},cookie)[1];share_token=token_data['token']
  self.assertEqual(self.call('/api/shared-state')[0]['status'],'404 Not Found')
  shared=self.call('/api/shared-state',auth='Bearer '+share_token);self.assertEqual(shared[0]['status'],'200 OK');self.assertTrue(any(m['id']=='0' for m in shared[1]['members']))
  self.assertIn('meals',shared[1]);self.assertIn('games',shared[1])
  self.call('/api/share-link','DELETE',{},cookie);self.assertEqual(self.call('/api/shared-state',auth='Bearer '+share_token)[0]['status'],'404 Not Found')
  ids=[str(i) for i in range(9)];g=self.call('/api/rounds','POST',{'date':'2026-10-18','ids':ids,'size':4},cookie)[1]['groups'];self.assertEqual([len(x) for x in g],[3,3,3]);self.assertEqual(len({m['id'] for x in g for m in x}),9)
  bad=self.call('/api/rounds','POST',{'date':'2026-10-18','ids':['0','0'],'size':4},cookie);self.assertEqual(bad[0]['status'],'400 Bad Request')
  meal={'id':'new','date':'2026-10-18','place':'Test','people':4,'income':100000,'extra':300,'expense':90000,'note':''}
  self.assertEqual(self.call('/api/meals','POST',meal,cookie)[0]['status'],'200 OK');self.assertEqual(self.call('/api/state',cookie=cookie)[1]['balance'],10300)
  meal['expense']=95000;self.call('/api/meals','POST',meal,cookie);self.assertEqual(self.call('/api/state',cookie=cookie)[1]['balance'],5300)
  self.call('/api/meals','DELETE',{'id':'new'},cookie);app.init();self.assertEqual(self.call('/api/state',cookie=cookie)[1]['balance'],0)
  changed=self.call('/api/change-password','POST',{'current_password':'test password','new_password':'another pass'},cookie)
  self.assertEqual(changed[0]['status'],'200 OK');self.assertEqual(changed[1]['ok'],True)
  self.assertEqual(self.call('/api/state',cookie=cookie)[0]['status'],'200 OK')
  self.call('/api/logout','POST',{},cookie);self.assertEqual(self.call('/api/state',cookie=cookie)[0]['status'],'401 Unauthorized')
  self.assertEqual(self.call('/api/login','POST',{'password':'test password'})[0]['status'],'401 Unauthorized')
  self.assertEqual(self.call('/api/login','POST',{'password':'another pass'})[0]['status'],'200 OK')
  with app.connect() as c:c.execute("DELETE FROM settings WHERE id='password_hash'")
  self.assertEqual(self.call('/api/login','POST',{'password':'test password'})[0]['status'],'200 OK')
if __name__=='__main__':unittest.main()
