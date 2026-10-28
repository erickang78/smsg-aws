import json, time
from database import ROOT, connect, init
from services.handicap import get_handicap_period
from services.games import create_game, delete_game, restore_game, update_game_participants, create_game_grouping, update_game_grouping, change_profile_attendance, create_rounds, list_game_history, submit_game_results, submit_game_result
from services.game_result_images import analyze_game_result_images
from services.settings import get_backup_status
from services.settings import update_handicap_period
from services.auth import change_member_password, current_member_name, authenticate_member, logout_member
from services.members import get_member_profile, list_member_directory, save_member
from services.meals import save_meal, delete_meal
from services.http_utils import json_response, session_tokens, session_is_authenticated
from services.http_utils import read_api_request
from services.web import serve_web_page
from services.state import state_data
from services.assistant import ask_assistant, AssistantRequestError
from services.share import read_shared_state, create_share_link, revoke_share_link
from functools import partial
MEAL_NOTE_2='진팀이 이긴팀 밥사주기'
MEAL_NOTE_5='밥값\n1등 1만원\n2등 1.5만원\n3등 2만원\n4등 2.5만원\n5등 3만원'
MEAL_NOTE_5_OLD_DEFAULT='밥값 1등 5천원, 2등 1만원, 3등 1만5천원, 4등 2만원, 5등 3만원'
MEAL_NOTE_5_OLD_CUSTOM='밥값 \n1등 1만원\n2등 1.5만원\n3등 2.5만원\n4등 3만원'
MEAL_NOTE_3='밥값 1등 1만원, 2등 2만원, 3등 3만원'
MEAL_NOTE_4='밥값 1등 5천원, 2등 1만원, 3등 2만원 4등 3만원'










def application(environ,start_response):
 send=partial(json_response,start_response)
 path=environ.get('PATH_INFO','/');method=environ.get('REQUEST_METHOD','GET')
 try:path=path.encode('latin-1').decode('utf-8')
 except (UnicodeEncodeError,UnicodeDecodeError):pass
 web_response=serve_web_page(environ,start_response,path,method,connect,ROOT)
 if web_response is not None:return web_response
 if path=='/health' and method=='GET':return send({'ok':True})
 if not path.startswith('/api/'):return send({'error':'페이지를 찾을 수 없습니다.'},'404 Not Found')
 try:
  body,rejection=read_api_request(environ,path,method)
  if rejection:return send(rejection[0],rejection[1])
  with connect() as c:
   token,token_hash=session_tokens(environ);now=int(time.time())
   if path=='/api/member-login' and method=='POST':
    result,status,cookie=authenticate_member(c,body,environ.get('REMOTE_ADDR','unknown'),now,environ['wsgi.url_scheme']=='https')
    return send(result,status,headers=[('Set-Cookie',cookie)] if cookie else [])
   if path=='/api/login' and method=='POST':
    return send({'error':'회원 ID와 회원 비밀번호로 로그인해주세요.'},'410 Gone')
   if path=='/api/shared-state' and method=='GET':
    shared=read_shared_state(c,environ.get('HTTP_AUTHORIZATION',''))
    if shared is None:return send({'error':'공유 링크가 만료되었거나 폐기되었습니다.'},'404 Not Found')
    return send(shared)
   if path=='/api/profile' and method=='GET':
    from urllib.parse import parse_qs
    name=parse_qs(environ.get('QUERY_STRING','')).get('name',[''])[0]
    result=get_member_profile(c,name)
    if result is None:return send({'error':'회원을 찾을 수 없거나 같은 이름의 회원이 여러 명입니다.'},'404 Not Found')
    return send(result)
   if path=='/api/member-directory' and method=='GET':
    return send({'members':list_member_directory(c)})
   if path=='/api/profile-join' and method=='POST':
    return send(change_profile_attendance(c,body))
   if path=='/api/courses' and method=='GET':return send(json.loads((ROOT/'golfzon-courses.json').read_text()))
   if not session_is_authenticated(c,token_hash,now):return send({'error':'로그인이 필요합니다.'},'401 Unauthorized')
   if path=='/api/assistant' and method=='POST':
    try:
     return send(ask_assistant(c,token_hash,body.get('question','')))
    except AssistantRequestError as exc:return send({'error':str(exc)},exc.status)
   if path=='/api/share-link' and method=='POST':
    return send(create_share_link(c))
   if path=='/api/share-link' and method=='DELETE':
    return send(revoke_share_link(c))
   if path=='/api/logout' and method=='POST':
    result,cookie=logout_member(c,token_hash)
    return send(result,headers=[('Set-Cookie',cookie)])
   if path=='/api/settings/backup' and method=='GET':
    return send(get_backup_status())
   if path=='/api/game-history' and method=='GET':
    return send(list_game_history(c))
   if path=='/api/settings' and method=='GET':return send({'handicap_period_months':get_handicap_period(c)})
   if path=='/api/settings' and method=='POST':
    return send(update_handicap_period(c,body))
   if path=='/api/member-password' and method=='POST':
    return send(change_member_password(c,body))
   if path=='/api/change-password' and method=='POST':
    return send({'error':'공용 비밀번호 변경은 사용할 수 없습니다.'},'410 Gone')
   if path=='/api/me' and method=='GET':
    return send({'name':current_member_name(c,token_hash,now)})
   if path=='/api/state' and method=='GET':
    return send(state_data(c,include_private=True))
   if path=='/api/games' and method=='POST':
    return send(create_game(c,body))
   if path=='/api/games' and method=='DELETE':
    return send(delete_game(c,str(body['id'])))
   if path=='/api/games/restore' and method=='POST':
    return send(restore_game(c,str(body['id'])))
   if path=='/api/game-participants' and method=='POST':
    return send(update_game_participants(c,str(body['id']),body.get('ids')))
   if path=='/api/game-groupings' and method=='PUT':
    return send(update_game_grouping(c,str(body['id']),body.get('groups')))
   if path=='/api/game-groupings' and method=='POST':
    return send(create_game_grouping(c,str(body['id']),body.get('group_count'),body.get('group_size')))
   if path=='/api/game-result-image' and method=='POST':
    try:
     return send(analyze_game_result_images(c,body))
    except RuntimeError as exc:return send({'error':str(exc)},'503 Service Unavailable')
   if path=='/api/game-results-bulk' and method=='POST':
    return send(submit_game_results(c,body))
   if path=='/api/game-results' and method=='POST':
    return send(submit_game_result(c,body))
   if path=='/api/members' and method=='POST':
    return send(save_member(c,body))
   if path=='/api/meals' and method=='POST':
    return send(save_meal(c,body))
   if path=='/api/meals' and method=='DELETE':
    return send(delete_meal(c,body['id']))
   if path=='/api/rounds' and method=='POST':
    return send(create_rounds(c,body))
   return send({'error':'지원하지 않는 요청입니다.'},'404 Not Found')
 except (ValueError,KeyError,TypeError) as e:return send({'error':str(e) or '입력을 확인해주세요.'},'400 Bad Request')
 except Exception:return send({'error':'서버 오류가 발생했습니다. 다시 시도해주세요.'},'500 Internal Server Error')

init()
if __name__=='__main__':
 from wsgiref.simple_server import make_server
 print('Local preview: http://127.0.0.1:8091')
 make_server('127.0.0.1',8091,application).serve_forever()
