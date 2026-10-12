from test_app import Flow
import app,unittest
class GameDelete(Flow):
 def test_delete_cascade_and_recalculate(self):
  response,_=self.call('/api/login','POST',{'password':'test password'});cookie=response['headers']['Set-Cookie'].split(';')[0]
  self.call('/api/members','POST',{'id':'delete-player','name':'삭제테스트','handicap':8},cookie)
  ids=[]
  for date,score in [('2026-10-11',0),('2026-10-18',10)]:
   id=self.call('/api/games','POST',{'date':date,'course':'삭제테스트','fairway':4,'green':4},cookie)[1]['id'];ids.append(id)
   self.call('/api/game-participants','POST',{'id':id,'ids':['delete-player']},cookie)
   self.call('/api/game-results','POST',{'id':id,'member_id':'delete-player','score':score},cookie)
   self.call('/api/game-groupings','POST',{'id':id,'group_count':1,'group_size':1},cookie)
  self.assertEqual(self.call('/api/games','DELETE',{'id':ids[1]})[0]['status'],'401 Unauthorized')
  self.assertEqual(self.call('/api/games','DELETE',{'id':ids[1]},cookie)[0]['status'],'200 OK')
  state=self.call('/api/state',cookie=cookie)[1];self.assertFalse(any(g['id']==ids[1] for g in state['games']))
  m=next(m for m in state['members'] if m['id']=='delete-player');self.assertEqual((m['handicap'],m['score_count'],m['last_attended']),(0,1,'2026-10-11'))
  with app.connect() as c:
   for table in ['game_results','game_participants','game_groupings']:self.assertEqual(c.execute('SELECT COUNT(*) FROM '+table+' WHERE game_id=?',(ids[1],)).fetchone()[0],0)
  self.call('/api/games','DELETE',{'id':ids[0]},cookie)
  m=next(m for m in self.call('/api/state',cookie=cookie)[1]['members'] if m['id']=='delete-player');self.assertEqual((m['handicap'],m['score_count'],m['last_attended']),(8,0,None))
if __name__=='__main__':unittest.main()
