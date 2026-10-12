from test_app import Flow
import app,unittest
class Groupings(Flow):
 def test_fair_partition(self):
  values=[0.7,2.9,4.3,4.4,4.9,5.6,8.0,8.8,9.0,9.6,9.7,11.2]
  members=[{'id':str(i),'name':str(i),'handicap':hd} for i,hd in enumerate(values)]
  groups=app.fair_game_groups(members,3,4)
  self.assertEqual([len(g) for g in groups],[4,4,4]);self.assertEqual(len({m['id'] for g in groups for m in g}),12)
  sums=[round(sum(m['handicap'] for m in g),1) for g in groups];self.assertLessEqual(max(sums)-min(sums),0.2)
  print('SAMPLE_GROUP_TOTALS',sums)
 def test_save_and_invalidate(self):
  response,_=self.call('/api/login','POST',{'password':'test password'});cookie=response['headers']['Set-Cookie'].split(';')[0]
  ids=[]
  for i,hd in enumerate([-2,0,4,8]):
   id='group-test-'+str(i);ids.append(id);self.call('/api/members','POST',{'id':id,'name':id,'handicap':hd},cookie)
  game=self.call('/api/games','POST',{'date':'2026-10-11','course':'조편성테스트','fairway':4,'green':4},cookie)[1]['id']
  self.call('/api/game-participants','POST',{'id':game,'ids':ids},cookie)
  self.assertEqual(self.call('/api/game-groupings','POST',{'id':game,'group_count':3,'group_size':2},cookie)[0]['status'],'400 Bad Request')
  response,data=self.call('/api/game-groupings','POST',{'id':game,'group_count':2,'group_size':2},cookie);self.assertEqual(response['status'],'200 OK')
  groups=data['groups']
  edited=[[m['id'] for m in g] for g in groups];edited[0][0],edited[1][0]=edited[1][0],edited[0][0]
  response,data=self.call('/api/game-groupings','PUT',{'id':game,'groups':edited},cookie);self.assertEqual(response['status'],'200 OK');groups=data['groups']
  self.assertEqual([[m['id'] for m in g] for g in groups],edited)
  duplicate=[edited[0],edited[0]];self.assertEqual(self.call('/api/game-groupings','PUT',{'id':game,'groups':duplicate},cookie)[0]['status'],'400 Bad Request')
  wrongsize=[edited[0]+[edited[1][0]],edited[1][1:]];self.assertEqual(self.call('/api/game-groupings','PUT',{'id':game,'groups':wrongsize},cookie)[0]['status'],'400 Bad Request')
  self.call('/api/game-participants','POST',{'id':game,'ids':ids},cookie)
  state=self.call('/api/state',cookie=cookie)[1];self.assertEqual(next(g for g in state['games'] if g['id']==game)['grouping']['groups'],groups)
  self.call('/api/game-results','POST',{'id':game,'member_id':ids[0],'score':10},cookie)
  state=self.call('/api/state',cookie=cookie)[1];self.assertEqual(next(g for g in state['games'] if g['id']==game)['grouping']['groups'],groups)
  self.call('/api/game-participants','POST',{'id':game,'ids':ids[:2]},cookie)
  state=self.call('/api/state',cookie=cookie)[1];self.assertIsNone(next(g for g in state['games'] if g['id']==game)['grouping'])
if __name__=='__main__':unittest.main()
