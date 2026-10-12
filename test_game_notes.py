from test_app import Flow
import unittest
class Notes(Flow):
 def test_notes_create_update_clear(self):
  r,_=self.call('/api/login','POST',{'password':'test password'});cookie=r['headers']['Set-Cookie'].split(';')[0]
  game={'date':'2026-10-18','course':'비고테스트','fairway':4,'green':4,'note':'첫 줄\n둘째 줄'}
  r,data=self.call('/api/games','POST',game,cookie);self.assertEqual(r['status'],'200 OK');game['id']=data['id']
  def note():return next(g for g in self.call('/api/state',cookie=cookie)[1]['games'] if g['id']==game['id'])['note']
  self.assertEqual(note(),'첫 줄\n둘째 줄');game['note']='변경';self.call('/api/games','POST',game,cookie);self.assertEqual(note(),'변경')
  game['note']='x'*1001;self.assertEqual(self.call('/api/games','POST',game,cookie)[0]['status'],'400 Bad Request');self.assertEqual(note(),'변경')
  game['note']='';self.call('/api/games','POST',game,cookie);self.assertEqual(note(),'')
if __name__=='__main__':unittest.main()
