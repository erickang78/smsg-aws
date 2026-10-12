from test_app import Flow
import unittest
class Games(Flow):
 def test_game_participants(self):
  response,_=self.call('/api/login','POST',{'password':'test password'});cookie=response['headers']['Set-Cookie'].split(';')[0]
  game={'date':'2026-10-18','course':'칠곡 아이위시CC','fairway':4,'green':4}
  self.assertEqual(self.call('/api/games','POST',dict(game,fairway=6),cookie)[0]['status'],'400 Bad Request')
  response,data=self.call('/api/games','POST',game,cookie);self.assertEqual(response['status'],'200 OK');id=data['id']
  self.call('/api/members','POST',{'id':'participant','name':'참가 회원','handicap':4.3},cookie)
  self.assertEqual(self.call('/api/game-participants','POST',{'id':id,'ids':['participant']},cookie)[0]['status'],'200 OK')
  self.assertEqual(self.call('/api/game-participants','POST',{'id':id,'ids':['missing']},cookie)[0]['status'],'400 Bad Request')
  state=self.call('/api/state',cookie=cookie)[1];self.assertEqual(next(g for g in state['games'] if g['id']==id)['participants'],['participant'])
  self.call('/api/games','POST',dict(game,id=id,green=3),cookie)
  g=next(g for g in self.call('/api/state',cookie=cookie)[1]['games'] if g['id']==id);self.assertEqual(g['green'],3);self.assertEqual(g['participants'],['participant'])
  self.call('/api/game-participants','POST',{'id':id,'ids':[]},cookie)
  self.assertEqual(next(g for g in self.call('/api/state',cookie=cookie)[1]['games'] if g['id']==id)['participants'],[])
if __name__=='__main__':unittest.main()
