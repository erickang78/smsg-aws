from test_app import Flow
import app,unittest
class Results(Flow):
 def test_average_update_and_removal(self):
  response,_=self.call('/api/login','POST',{'password':'test password'});cookie=response['headers']['Set-Cookie'].split(';')[0]
  self.call('/api/members','POST',{'id':'scorer','name':'점수회원','handicap':5.3},cookie)
  with app.connect() as c:
   for i,n in enumerate([8,3,1,7,0,21,2,-1,-6,8,2,18]):c.execute('INSERT INTO historical_scores VALUES(?,?,?)',('scorer',i,n))
   app.recalculate_handicap(c,'scorer')
  game={'date':'2026-10-11','course':'결과테스트','fairway':4,'green':4}
  id=self.call('/api/games','POST',game,cookie)[1]['id']
  self.call('/api/game-participants','POST',{'id':id,'ids':['scorer']},cookie)
  def score(n):return self.call('/api/game-results','POST',{'id':id,'member_id':'scorer','score':n},cookie)
  self.assertEqual(score(0)[1]['handicap'],4.8)
  member=next(m for m in self.call('/api/state',cookie=cookie)[1]['members'] if m['id']=='scorer');self.assertEqual(member['last_attended'],'2026-10-11')
  self.assertEqual(score(-2)[1]['handicap'],4.7)
  self.assertEqual(score(-2)[1]['score_count'],13)
  self.assertEqual(score(True)[0]['status'],'400 Bad Request')
  self.assertEqual(score(301)[0]['status'],'400 Bad Request')
  self.assertEqual(self.call('/api/game-results','POST',{'id':id,'member_id':'missing','score':7},cookie)[0]['status'],'400 Bad Request')
  self.call('/api/game-participants','POST',{'id':id,'ids':['scorer']},cookie)
  result=next(g for g in self.call('/api/state',cookie=cookie)[1]['games'] if g['id']==id);self.assertEqual(result['results']['scorer'],-2)
  self.assertEqual(score(None)[1]['handicap'],5.3)
  score(7);self.call('/api/game-participants','POST',{'id':id,'ids':[]},cookie)
  member=next(m for m in self.call('/api/state',cookie=cookie)[1]['members'] if m['id']=='scorer');self.assertEqual(member['handicap'],5.3);self.assertEqual(member['score_count'],12);self.assertIsNone(member['last_attended'])
 def test_new_member_restores_original(self):
  response,_=self.call('/api/login','POST',{'password':'test password'});cookie=response['headers']['Set-Cookie'].split(';')[0]
  self.call('/api/members','POST',{'id':'newscorer','name':'신규점수회원','handicap':8},cookie)
  id=self.call('/api/games','POST',{'date':'2026-10-12','course':'신규테스트','fairway':4,'green':4},cookie)[1]['id']
  self.call('/api/game-participants','POST',{'id':id,'ids':['newscorer']},cookie)
  payload={'id':id,'member_id':'newscorer','score':0}
  self.assertEqual(self.call('/api/game-results','POST',payload,cookie)[1]['handicap'],0)
  payload['score']=None;self.assertEqual(self.call('/api/game-results','POST',payload,cookie)[1]['handicap'],8)
if __name__=='__main__':unittest.main()
