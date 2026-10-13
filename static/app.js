'use strict';
let state,tab='members',busy=false,selectedGame=null,memberSort='handicap';const $=s=>document.querySelector(s),money=n=>Number(n).toLocaleString('ko-KR'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const profileName=decodeURIComponent(location.pathname).replace(/^\/|\/$/g,'');
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
function status(s){$('#status').textContent=s}
async function api(path,method='GET',body){const r=await fetch('/api/'+path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const j=await r.json();if(!r.ok){if(r.status===401){$('#app').hidden=true;$('#login').hidden=false;$('#logout').hidden=true}throw Error(j.error||'요청을 처리하지 못했습니다.')}return j}
async function refresh(){if(profileName){await refreshProfile();return}state=await api('state');$('#login').hidden=true;$('#app').hidden=false;$('#logout').hidden=false;$('#balance').textContent=money(state.balance)+'원';$('#membercount').textContent=state.members.filter(m=>m.active).length+'명의 멤버';render()}
$('#loginform').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;try{await api('login','POST',{password:new FormData(e.target).get('password')});e.target.reset();await refresh();status('')}catch(e){status(e.message)}finally{busy=false}};
$('#logout').onclick=async()=>{try{await api('logout','POST',{});location.reload()}catch(e){status(e.message)}};
$('nav').onclick=e=>{if(e.target.dataset.tab){tab=e.target.dataset.tab;render()}};
function heading(title,sub,button=''){return `<div class="title"><div><h2>${title}</h2><p>${sub}</p></div>${button}</div>`}
function render(){document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('selected',b.dataset.tab===tab));const c=$('#content');
 if(tab==='members'){c.innerHTML=heading('우리 멤버','이름과 핸디를 등록하고 모임을 함께 관리해요.','<button class="primary" id="newmember">＋ 멤버</button>')+`<div class="filters"><label>정렬 기준<select id="membersort">${[['handicap','핸디 낮은 순'],['name','이름 가나다순'],['age','나이 많은 순'],['recent','최근 참석순']].map(([value,label])=>`<option value="${value}" ${memberSort===value?'selected':''}>${label}</option>`).join('')}</select></label></div>`+(state.members.length?'<div class="cards">'+sortedMembers().map(m=>`<button class="card clickable" data-member="${esc(m.id)}"><h3>${esc(m.name)}</h3><div class="member-details"><div class="member-detail"><span>핸디</span><b>${m.handicap}</b></div><div class="member-detail"><span>참석횟수</span><b>${m.score_count||0}회</b></div><div class="member-detail"><span>${esc(memberNote(m).replace(/생년\s*:\s*(\d{2,4})년/,'생년 $1년생'))}</span></div><div class="member-detail"><span>마지막참석</span><b>${m.last_attended?esc(m.last_attended):'기록 없음'}</b></div></div></button>`).join('')+'</div>':'<div class="empty">아직 등록된 멤버가 없습니다.<br>첫 멤버를 등록해주세요.</div>');$('#membersort').onchange=e=>{memberSort=e.target.value;render()};$('#newmember').onclick=()=>memberEditor();c.querySelectorAll('[data-member]').forEach(b=>b.onclick=()=>memberEditor(state.members.find(m=>m.id===b.dataset.member)))}
 if(tab==='games'){renderGames(c)}
 if(tab==='meals'){c.innerHTML=heading('식대정산','사진에서 옮긴 43건부터 이어서 기록하세요.','<button class="primary" id="newmeal">＋ 기록</button>')+'<div class="filters"><input id="search" placeholder="장소 검색" aria-label="장소 검색"><select id="month" aria-label="월 선택"><option value="">전체</option>'+[...new Set(state.meals.map(m=>m.date.slice(0,7)))].reverse().map(m=>`<option>${m}</option>`).join('')+'</select></div><div id="meallist" class="cards"></div><p class="note">정산 = 식대 수입 − 지출 · 잔액에는 캐시백·이자 포함<br>이월 잔액 132,843원 · 사진의 빈 지출은 0원으로 입력했습니다.<br>장소명이 다르면 기록을 눌러 수정하세요.</p><button id="csv">↓ CSV 내려받기</button>';$('#newmeal').onclick=()=>mealEditor();$('#search').oninput=mealList;$('#month').onchange=mealList;$('#csv').onclick=exportCSV;mealList()}}
function mealList(){const rows=state.meals.filter(m=>(!$('#month').value||m.date.startsWith($('#month').value))&&m.place.includes($('#search').value)).slice().reverse();$('#meallist').innerHTML=rows.map(m=>`<button class="card clickable" data-meal="${esc(m.id)}"><div class="row"><span class="muted">${esc(m.date)} · ${m.people}명</span><span class="badge ${m.settlement<0?'negative':''}">${m.settlement>0?'+':''}${money(m.settlement)}원</span></div><h3 class="gap">${esc(m.place)}</h3><div class="stats"><div><small>수입</small><b>${money(m.income)}</b></div><div><small>지출</small><b>${money(m.expense)}</b></div><div><small>잔액</small><b>${money(m.balance)}</b></div></div><div class="note">캐시백·이자 ${money(m.extra)}원</div></button>`).join('')||'<div class="empty">표시할 기록이 없습니다.</div>';document.querySelectorAll('[data-meal]').forEach(b=>b.onclick=()=>mealEditor(state.meals.find(m=>m.id===b.dataset.meal)))}
$('#close').onclick=()=>{if(!busy)$('#editor').close()};$('#editor').addEventListener('cancel',e=>{if(busy)e.preventDefault()});
function showEditor(title,html,save){$('#editor').classList.remove('participants-dialog','group-edit-dialog','member-edit-dialog');$('#editform').oninput=null;$('#editform').onchange=null;$('#dialogtitle').textContent=title;$('#editform').innerHTML=html+'<button class="primary full">저장하고 반영</button>';$('#editform').onsubmit=async e=>{e.preventDefault();await perform(()=>save(new FormData(e.target)),'저장했습니다.',true)};$('#editor').showModal()}
async function perform(fn,message,close=false){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);try{await fn();await refresh();if(close)$('#editor').close();status(message)}catch(e){status(e.message);if($('#editor').open){let p=$('#editerror');if(!p){p=document.createElement('p');p.id='editerror';p.setAttribute('role','alert');$('#editform').append(p)}p.textContent=e.message}}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false)}}
function memberEditor(m={name:'',handicap:0,note:'',active:1}){showEditor(m.id?'회원 정보':'새 멤버',`${m.id?`<div class="member-profile-labels"><div><span>이름</span><strong>${esc(m.name)}</strong></div><div><span>핸디</span><strong>${m.handicap}</strong></div></div>`:`<label>이름<input name="name" required maxlength="80" value="${esc(m.name)}"></label><label>핸디<input name="handicap" type="number" step="0.1" min="-100" max="300" required value="${m.handicap}"></label>`}${m.score_count?`<p class="note">핸디는 기존·신규 경기 결과 ${m.score_count}회 평균으로 자동 계산됩니다.</p>`:''}<label>메모<textarea name="note" maxlength="1000">${esc(memberNote(m))}</textarea></label><label class="check"><input name="active" type="checkbox" ${m.active?'checked':''}>활동 멤버</label><p class="note">비활동 멤버는 새 조편성에서 제외됩니다.</p>`,f=>api('members','POST',{id:m.id,name:m.id?m.name:f.get('name'),handicap:m.id?m.handicap:Number(f.get('handicap')),note:f.get('note'),active:f.has('active')}));if(m.id)$('#editor').classList.add('member-edit-dialog');$('#editform .primary').textContent='저장';if(m.id){const history=document.createElement('section');history.className='member-attendance-history';const games=(state.games||[]).filter(g=>Object.hasOwn(g.results||{},m.id)).sort((a,b)=>b.date.localeCompare(a.date));history.innerHTML=`<h3>참가한 날 · ${games.length}회</h3>${games.length?'<ul>'+games.map(g=>`<li><div class="attendance-date-course"><b class="attendance-date">${esc(g.date)}</b><strong class="attendance-course">${esc(g.course)}</strong></div><span>${esc(g.results[m.id])}</span></li>`).join('')+'</ul>':'<p class="note">아직 참가 기록이 없습니다.</p>'}`;$('#editform').append(history)}}
function mealEditor(m={date:today(),place:'',people:0,income:0,expense:0,extra:0,note:''}){showEditor(m.id?'식대 기록 수정':'새 식대 기록',`<div class="grid"><label>날짜<input name="date" type="date" required value="${esc(m.date)}"></label><label>인원수<input name="people" type="number" min="0" max="10000" value="${m.people}"></label><label class="wide">장소 / 모임명<input name="place" required maxlength="120" value="${esc(m.place)}"></label>${[['income','식대 수입'],['expense','지출'],['extra','캐시백·이자']].map(([k,l])=>`<label>${l} (원)<input name="${k}" type="number" inputmode="numeric" min="0" max="1000000000" value="${m[k]}"></label>`).join('')}<label class="wide">메모<textarea name="note" maxlength="1000">${esc(m.note)}</textarea></label></div><div class="calc row"><span>이번 정산</span><b id="livecalc">${money(m.income-m.expense)}원</b></div>`,f=>api('meals','POST',{id:m.id,date:f.get('date'),place:f.get('place'),people:Number(f.get('people')),income:Number(f.get('income')),expense:Number(f.get('expense')),extra:Number(f.get('extra')),note:f.get('note')}));$('#editform .primary').textContent='저장';$('#editform').oninput=()=>$('#livecalc').textContent=money(Number($('#editform [name=income]').value)-Number($('#editform [name=expense]').value))+'원';if(m.id){const b=document.createElement('button');b.type='button';b.className='delete';b.textContent='기록 삭제';b.onclick=()=>{if(confirm('이 기록을 삭제할까요? 이후 잔액도 다시 계산됩니다.'))perform(()=>api('meals','DELETE',{id:m.id}),'삭제했습니다.',true)};$('#editform').append(b)}}
function exportCSV(){const fields=['date','place','people','income','extra','expense','settlement','balance','note'];const data=[['날짜','장소','인원','수입','캐시백/이자','지출','정산','잔액','메모'],...state.meals.map(r=>fields.map(k=>r[k]))];const url=URL.createObjectURL(new Blob(['\uFEFF'+data.map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='일조해-식대정산.csv';a.click();URL.revokeObjectURL(url)}
refresh().catch(e=>{if(!e.message.includes('로그인'))status(e.message)});

function renderGames(c){
 const game=(state.games||[]).find(g=>g.id===selectedGame);
 if(!game){selectedGame=null;c.innerHTML=heading('경기','경기를 만들고 참가 회원을 추가하세요.','<button class="primary" id="newgame">＋ 경기만들기</button>')+'<div class="cards">'+(state.games||[]).map(g=>`<button class="card clickable" data-game="${esc(g.id)}"><div class="game-list-card-layout game-list-aligned"><h3>${esc(g.course)}</h3><span class="badge">${g.participants.length}명 참가</span><p>${esc(g.date)}</p><div class="muted">페어웨이 ${g.fairway||'미확인'} · 그린 ${g.green||'미확인'}</div></div></button>`).join('')+'</div>'+(!(state.games||[]).length?'<div class="empty">아직 만든 경기가 없습니다.</div>':'');$('#newgame').onclick=()=>gameEditor();c.querySelectorAll('[data-game]').forEach(b=>b.onclick=()=>{selectedGame=b.dataset.game;render();window.scrollTo({top:0,left:0,behavior:'instant'})});return}
 const members=game.participants.map(id=>state.members.find(m=>m.id===id)).filter(Boolean);
 c.innerHTML='<div class="row game-toolbar"><button id="backgames">← 경기 목록</button><button class="primary" id="makegamegroups">'+(game.grouping?'조편성 보기':'조편성')+'</button></div>'+heading(esc(game.course),`${esc(game.date)} · 페어웨이 ${game.fairway||'미확인'} · 그린 ${game.green||'미확인'}`,'<button id="editgame">경기 수정</button>')+heading(`참가 회원 ${members.length}명`,'이름을 눌러 경기 결과 점수를 입력하세요.','<button class="primary" id="participants">＋ 회원 추가</button>')+'<div class="cards">'+members.map(m=>`<section class="card participant-card participant-aligned"><button class="participant-result clickable participant-name" data-result="${esc(m.id)}"><h3>${esc(m.name)}</h3></button><span class="badge participant-handicap">핸디 ${m.handicap}</span><button class="participant-result clickable participant-score" data-result="${esc(m.id)}"><span class="muted">결과 점수 <b>${Object.hasOwn(game.results||{},m.id)?esc(game.results[m.id]):'미입력'}</b></span></button>${Object.hasOwn(game.results||{},m.id)?'':`<button type="button" class="participant-delete" data-remove-participant="${esc(m.id)}">경기에서 회원 삭제</button>`}</section>`).join('')+'</div>'+(!members.length?'<div class="empty">회원 추가를 눌러 참가자를 선택해주세요.</div>':'')+'<div class="game-delete-footer"><button class="game-delete" id="deletegame">경기 삭제</button></div>';$('#backgames').onclick=()=>{selectedGame=null;render()};$('#editgame').onclick=()=>gameEditor(game);$('#deletegame').onclick=()=>deleteGame(game);$('#participants').onclick=()=>participantsEditor(game);$('#makegamegroups').onclick=()=>game.grouping?showGroupingPopup(game):groupingEditor(game);c.querySelectorAll('[data-result]').forEach(b=>b.onclick=()=>resultEditor(game,state.members.find(m=>m.id===b.dataset.result)));c.querySelectorAll('[data-remove-participant]').forEach(b=>b.onclick=()=>removeGameParticipant(game,b.dataset.removeParticipant));
}
function gameEditor(g={date:today(),course:'',fairway:4,green:4,note:''}){
 showEditor(g.id?'경기 수정':'경기만들기',`<label>경기 날짜<input type="date" name="date" required value="${esc(g.date)}"></label><label>골프존 경기장 이름<input id="course-search" name="course" required maxlength="120" autocomplete="off" placeholder="구장 이름 검색 또는 직접 입력" value="${esc(g.course)}"></label><div id="course-results" class="course-results" aria-live="polite"></div><div class="grid">${[['fairway','페어웨이 난이도'],['green','그린 난이도']].map(([k,label])=>`<label>${label}<select name="${k}"><option value="" ${!g[k]?'selected':''}>미확인</option>${[1,2,3,4,5].map(n=>`<option value="${n}" ${g[k]===n?'selected':''}>${n}</option>`).join('')}</select></label>`).join('')}</div><label>비고<textarea name="note" maxlength="1000" rows="3" placeholder="경기 안내나 참고사항을 입력하세요">${esc(g.note||defaultMealNote(g.grouping?.group_count||3))}</textarea></label>`,async f=>{const result=await api('games','POST',{id:g.id,note:f.get('note'),date:f.get('date'),course:f.get('course'),fairway:f.get('fairway')===''?0:Number(f.get('fairway')),green:f.get('green')===''?0:Number(f.get('green'))});selectedGame=result.id});
 $('#editform .primary').textContent='저장';setupCourseSearch();
}
function participantsEditor(g){
 const members=state.members.filter(m=>m.active||g.participants.includes(m.id)).sort((a,b)=>a.handicap-b.handicap);
 showEditor('참가 회원 추가·변경','<p class="note">참가할 회원을 선택하세요. 체크를 해제하면 참가 명단에서 제외됩니다.</p><div class="cards">'+members.map(m=>`<label class="check"><input type="checkbox" name="ids" value="${esc(m.id)}" ${g.participants.includes(m.id)?'checked':''}>${esc(m.name)} <span class="muted">핸디 ${m.handicap}</span></label>`).join('')+'</div>',f=>{const ids=f.getAll('ids');if(g.participants.some(id=>!ids.includes(id)&&Object.hasOwn(g.results||{},id))&&!confirm('점수가 있는 회원을 제외하면 해당 경기 점수가 삭제되고 핸디도 다시 계산됩니다. 제외할까요?'))throw Error('참가 명단 변경을 취소했습니다.');return api('game-participants','POST',{id:g.id,ids})});
 $('#editor').classList.add('participants-dialog');$('#editform .primary').textContent='저장';$('#editform .primary').classList.add('participant-save');
}

function resultEditor(g,m){
 const hasScore=Object.hasOwn(g.results||{},m.id);
 showEditor(`${m.name} · 경기 결과`, `<p class="note">${esc(g.date)} · ${esc(g.course)}</p><label>결과 점수<input name="score" type="number" step="any" min="-100" max="300" required value="${hasScore?esc(g.results[m.id]):''}" placeholder="예: 7, 0, -2"></label><p class="note">현재 핸디 ${m.handicap} · 누적 결과 ${m.score_count||0}회<br>저장하면 기존 점수와 이번 경기 결과의 전체 평균을 핸디에 반영합니다. 미입력은 제외하고 0점은 포함합니다.</p>`,f=>api('game-results','POST',{id:g.id,member_id:m.id,score:Number(f.get('score'))}));
 if(hasScore){const b=document.createElement('button');b.type='button';b.className='delete';b.textContent='점수 입력 취소';b.onclick=()=>{if(confirm('이 점수를 삭제하고 핸디를 다시 계산할까요?'))perform(()=>api('game-results','POST',{id:g.id,member_id:m.id,score:null}),'점수를 삭제하고 핸디를 반영했습니다.',true)};$('#editform').append(b)}
}

function memberNote(m){return String(m.note||'').replace(/(?:\s*·\s*)?2026년 9월 27일 현황표 누적 핸디/g,'').trim()}
function koreanDate(date){const [y,m,d]=date.split('-');return `${y}년 ${Number(m)}월 ${Number(d)}일`}

function memberBirthYear(m){
 const match=String(m.note||'').match(/생년\s*:\s*(\d{2}|\d{4})년/);
 if(!match)return null;
 const year=Number(match[1]);const currentYear=Number(today().slice(0,4));return match[1].length===4?year:(year<=currentYear%100?Math.floor(currentYear/100)*100:Math.floor(currentYear/100)*100-100)+year;
}
function sortedMembers(){
 return state.members.slice().sort((a,b)=>{
  const nameOrder=a.name.localeCompare(b.name,'ko');
  if(memberSort==='name')return nameOrder;
  if(memberSort==='age'){const ay=memberBirthYear(a),by=memberBirthYear(b);return (ay??Infinity)-(by??Infinity)||nameOrder}
  if(memberSort==='recent')return (b.last_attended||'').localeCompare(a.last_attended||'')||nameOrder;
  return a.handicap-b.handicap||nameOrder;
 });
}

function groupingEditor(g){
 const n=g.participants.length;
 if(!n){status('먼저 참가 회원을 추가해주세요.');return}
 const size=[4,3,2,1].find(size=>n%size===0),count=n/size;
 showEditor('조편성',`<p class="note">${esc(g.course)} · 참가자 ${n}명</p><div class="grid"><label>몇 조<input name="group_count" type="number" min="1" max="32" step="1" required value="${g.grouping?.group_count||count}"></label><label>조당 몇 명<input name="group_size" type="number" min="1" max="20" step="1" required value="${g.grouping?.group_size||size}"></label></div><p class="note">조 수 × 조당 인원은 ${n}명이어야 합니다. 각 조의 평균 핸디가 비슷하도록 편성합니다.</p>`,f=>api('game-groupings','POST',{id:g.id,group_count:Number(f.get('group_count')),group_size:Number(f.get('group_size'))}));
 $('#editform .primary').textContent=g.grouping?'다시 편성하고 저장':'조편성하고 저장';
}
function manualGroupingEditor(g){
 const groups=g.grouping.groups;
 showEditor('편성된 조 수정',`<p class="note">회원별 배정할 조를 선택하세요. 각 조 ${g.grouping.group_size}명을 맞춰 저장하면 됩니다.</p><div id="groupeditpreview" class="calc"></div>${groups.map((group,i)=>group.map(m=>`<label>${esc(m.name)} · 핸디 ${m.handicap}<select name="group_${esc(m.id)}">${groups.map((_,j)=>`<option value="${j}" ${i===j?'selected':''}>${j+1}조</option>`).join('')}</select></label>`).join('')).join('')}`,f=>api('game-groupings','PUT',{id:g.id,groups:groups.map((_,i)=>groups.flat().filter(m=>Number(f.get('group_'+m.id))===i).map(m=>m.id))}));
 const list=document.createElement('div');list.className='group-edit-list';[...$('#editform').children].filter(node=>node.tagName==='LABEL').forEach(node=>list.append(node));$('#editform').insertBefore(list,$('#editform .primary'));$('#editor').classList.add('group-edit-dialog');
 $('#editform .primary').textContent='수정한 조 저장';
 const preview=()=>{const form=new FormData($('#editform'));$('#groupeditpreview').innerHTML=groups.map((_,i)=>{const members=groups.flat().filter(m=>Number(form.get('group_'+m.id))===i),sum=members.reduce((s,m)=>s+m.handicap,0);return `<div class="note">${i+1}조 · ${members.length}명 · 평균 ${members.length?(sum/members.length).toFixed(1):'—'} · 합계 ${sum.toFixed(1)}</div>`}).join('')};
 $('#editform').oninput=null;$('#editform').onchange=preview;preview();
}

function removeGameParticipant(g,id){
 const m=state.members.find(m=>m.id===id);
 const warning=Object.hasOwn(g.results||{},id)?' 해당 경기 결과 점수도 삭제되고 핸디·참석 기록이 다시 계산됩니다.':'';
 const grouping=g.grouping?' 기존 조편성은 초기화됩니다.':'';
 if(confirm(`${m.name} 회원을 이 경기에서 삭제할까요?${warning}${grouping}`))perform(()=>api('game-participants','POST',{id:g.id,ids:g.participants.filter(mid=>mid!==id)}),'경기 참가 회원을 삭제했습니다.');
}

function showGroupingPopup(g){
 if(!g.grouping)return;
 let popup=$('#groupviewer');
 if(!popup){popup=document.createElement('dialog');popup.id='groupviewer';popup.className='group-sheet';popup.setAttribute('aria-label','일조해 조편성 보기');document.body.append(popup)}
 const groups=g.grouping.groups,rank=groups.flat().slice().sort((a,b)=>a.handicap-b.handicap||a.name.localeCompare(b.name,'ko'));
 const name=m=>esc(state.members.find(member=>member.id===m.id)?.name||m.name);
 popup.innerHTML=`<div class="dialoghead"><div><small>${esc(g.date)}</small><h2>일조해 매치 조편성</h2></div><button type="button" id="closegroupviewer" aria-label="조편성 닫기">✕</button></div><div class="sheet-fit-controls" hidden><button type="button" id="fitlandscape" hidden>가로맞춤</button><button type="button" id="fitportrait" hidden>세로맞춤</button></div><div class="sheet-scroll"><div class="sheet-layout"><table class="match-table rank-table"><caption>참가자 핸디 순위</caption><thead><tr><th>순위</th><th>이름</th><th>핸디</th></tr></thead><tbody>${rank.map((m,i)=>`<tr><td>${i+1}</td><td>${name(m)}</td><td>${m.handicap.toFixed(1)}</td></tr>`).join('')}</tbody></table><table class="match-table groups-table"><caption>조별 편성</caption><thead><tr><th>조</th><th>이름</th><th>핸디</th><th>핸디 합계</th></tr></thead><tbody>${groups.map((group,i)=>{const sum=group.reduce((n,m)=>n+m.handicap,0);return group.map((m,j)=>`<tr class="team-${i%2}">${j===0?`<th rowspan="${group.length}">${i+1}조</th>`:''}<td>${name(m)}</td><td>${m.handicap.toFixed(1)}</td>${j===0?`<td class="team-total" rowspan="${group.length}"><b>${sum.toFixed(1)}</b><small>평균 ${(sum/group.length).toFixed(1)}</small></td>`:''}</tr>`).join('')}).join('')}</tbody></table><section class="match-info"><h3>경기 정보</h3><strong>${g.grouping.group_size}명 × ${groups.length}조</strong><p>경기장<br><b>${esc(g.course)}</b><br><span>페어웨이 ${g.fairway||'미확인'} · 그린 ${g.green||'미확인'}</span></p><p><b>시니어티</b><br>65세 이상 자유${g.note?`<span class="match-inline-note"><b>비고</b><br>${esc(g.note)}</span>`:''}</p><p><b>승점방식 · 홀별</b><br>${groups.map((_,i)=>`${i+1}위 ${groups.length-1-i}점`).join(' · ')}<br>파3 니어 점수 1~2점<br>17홀 18홀 배판(X2)</p><p class="note">편성 당시 핸디 기준</p></section></div></div><div class="sheet-actions"><button type="button" id="popupeditgroups">조 수정</button><button type="button" id="popupregroup">다시 편성</button><button type="button" class="primary" id="popupclosegroups">닫기</button></div>`;
 const close=()=>popup.close();$('#closegroupviewer').onclick=close;$('#popupclosegroups').onclick=close;
 $('#popupeditgroups').onclick=()=>{close();manualGroupingEditor(g)};$('#popupregroup').onclick=()=>{close();groupingEditor(g)};
 popup.classList.add('capture-fit');
 popup.dataset.fit='portrait';
 $('#fitlandscape').onclick=()=>{popup.dataset.fit='landscape';fitGroupingPopup()};
 $('#fitportrait').onclick=()=>{popup.dataset.fit='portrait';fitGroupingPopup()};
 popup.showModal();requestAnimationFrame(fitGroupingPopup);
}

function fitGroupingPopup(){
 const popup=$('#groupviewer');if(!popup?.open)return;
 const portrait=popup.dataset.fit==='portrait',layout=popup.querySelector('.sheet-layout'),scroll=popup.querySelector('.sheet-scroll');
 popup.classList.toggle('fit-portrait',portrait);
 layout.style.transform='none';scroll.style.width='';scroll.style.height='';
 const css=getComputedStyle(popup),horizontal=parseFloat(css.paddingLeft)+parseFloat(css.paddingRight),vertical=parseFloat(css.paddingTop)+parseFloat(css.paddingBottom);
 const viewportHeight=window.visualViewport?.height||window.innerHeight;
 const availableWidth=popup.clientWidth-horizontal;
 const chrome=popup.querySelector('.dialoghead').offsetHeight+popup.querySelector('.sheet-fit-controls').offsetHeight+popup.querySelector('.sheet-actions').offsetHeight+vertical+70;
 const availableHeight=Math.max(80,viewportHeight-chrome-16);
 const width=layout.offsetWidth,height=layout.offsetHeight;
 const scale=Math.min(1,availableWidth/width,availableHeight/height);
 layout.style.transform=`scale(${scale})`;scroll.style.width=`${width*scale}px`;scroll.style.height=`${height*scale}px`;
 $('#fitlandscape').setAttribute('aria-pressed',String(!portrait));$('#fitportrait').setAttribute('aria-pressed',String(portrait));
}
window.addEventListener('resize',()=>requestAnimationFrame(fitGroupingPopup));
window.visualViewport?.addEventListener('resize',()=>requestAnimationFrame(fitGroupingPopup));

function deleteGame(g){
 if(!confirm(`${g.date} ${g.course} 경기를 삭제할까요? 참가 명단·결과 점수·조편성이 함께 삭제되고 회원 핸디와 참석 기록이 다시 계산됩니다.`))return;
 perform(async()=>{await api('games','DELETE',{id:g.id});selectedGame=null;window.scrollTo({top:0,left:0,behavior:'instant'})},'경기를 삭제했습니다.');
}

async function refreshProfile(){
 const data=await api('profile?name='+encodeURIComponent(profileName)),m=data.member;
 $('#login').hidden=true;$('#app').hidden=false;$('#logout').hidden=true;$('nav').hidden=true;$('.hero').hidden=true;
 document.title=m.name+' · 일조해 회원 정보';
 $('#content').innerHTML=upcomingGamesView(data.upcoming||[])+heading('회원 정보',esc(m.name))+`<section class="card"><h2>${esc(m.name)}</h2><div class="member-details"><div class="member-detail"><span>핸디</span><b>${m.handicap}</b></div><div class="member-detail"><span>참석횟수</span><b>${m.score_count}회</b></div><div class="member-detail"><span>${esc(memberNote(m).replace(/생년\s*:\s*(\d{2,4})년/,'생년 $1년생'))}</span></div><div class="member-detail"><span>마지막참석</span><b>${esc(m.last_attended||'기록 없음')}</b></div></div><section class="member-attendance-history"><h3>참가한 날 · ${data.games.length}회</h3>${data.games.length?'<ul>'+data.games.map(g=>`<li><div class="attendance-date-course"><b class="attendance-date">${esc(g.date)}</b><strong class="attendance-course">${esc(g.course)}</strong></div><span>${esc(g.score)}</span></li>`).join('')+'</ul>':'<p class="note">아직 참가 기록이 없습니다.</p>'}</section></section>`;
 document.querySelectorAll('[data-join-game]').forEach(button=>button.onclick=()=>joinUpcomingGame(button.dataset.joinGame));document.querySelectorAll('[data-leave-game]').forEach(button=>button.onclick=()=>joinUpcomingGame(button.dataset.leaveGame,true));
}

function upcomingGamesView(games){
 return heading('예정 경기','오늘부터 예정된 경기입니다.')+(games.length?'<div class="cards">'+games.map(g=>`<section class="card"><div class="row"><b>${esc(g.date)}</b><span class="badge">${g.attending?'참석 완료':'참석 미등록'}</span></div><div class="upcoming-course-row gap"><h3>${esc(g.course)}</h3><div class="attendance-actions">${g.attending?'':`<button type="button" class="primary" data-join-game="${esc(g.id)}">참석</button>`}${g.attending&&!g.has_result?`<button type="button" class="game-delete" data-leave-game="${esc(g.id)}">참석빼기</button>`:''}</div></div><div class="muted">페어웨이 ${g.fairway||'미확인'} · 그린 ${g.green||'미확인'}</div></section>`).join('')+'</div>':'<div class="empty">예정된 경기가 없습니다.</div>');
}

async function joinUpcomingGame(gameId,remove=false){
 if(busy)return;busy=true;
 const button=document.querySelector(`[${remove?'data-leave-game':'data-join-game'}="${CSS.escape(gameId)}"]`);if(button)button.disabled=true;
 try{await api('profile-join','POST',{name:profileName,game_id:gameId,remove});await refreshProfile();status(remove?'참석을 취소했습니다.':'경기 참석이 등록되었습니다.')}catch(error){status(error.message);if(button)button.disabled=false}finally{busy=false}
}

function defaultMealNote(count){return {2:'진팀이 이긴팀 밥사주기',3:'밥값 1등 1만원, 2등 2만원, 3등 3만원',4:'밥값 1등 5천원, 2등 1만원, 3등 2만원 4등 3만원',5:'밥값 1등 5천원, 2등 1만원, 3등 1만5천원, 4등 2만원, 5등 3만원'}[count]||'밥값 1등 1만원, 2등 2만원, 3등 3만원'}

let courseCatalog=null;
async function setupCourseSearch(){
 const input=$('#course-search'),results=$('#course-results');if(!input||!results)return;
 results.innerHTML='<p class="note">골프존 코스 목록을 불러오는 중입니다.</p>';
 try{if(!courseCatalog)courseCatalog=await api('courses');if($('#course-search')!==input)return;
 const normalize=value=>String(value).toLocaleLowerCase().replace(/\s/g,'');
 const renderMatches=()=>{const query=normalize(input.value);if(!query){results.innerHTML='<p class="note">이름을 입력해 골프존 코스를 검색하세요. 직접 입력도 가능합니다.</p>';return}
 const matches=courseCatalog.courses.filter(c=>normalize(c.name).includes(query));
 results.innerHTML=matches.length?'<p class="note">검색 결과 '+matches.length+'개 · 최대 20개 표시</p>'+matches.slice(0,20).map(c=>`<button type="button" class="course-option" data-course-id="${c.id}"><div class="course-option-details"><b>${esc(c.name)}</b><span>코스 ${esc(c.course_difficulty)} / 5 · 그린 ${esc(c.green_difficulty)} / 5</span></div><small>${esc(c.region)}</small></button>`).join(''):'<p class="note">일치하는 코스가 없습니다. 입력한 이름 그대로 저장할 수 있습니다.</p>';
 results.querySelectorAll('[data-course-id]').forEach(button=>button.onclick=()=>{input.value=courseCatalog.courses.find(c=>String(c.id)===button.dataset.courseId).name;results.innerHTML='<p class="note">선택한 코스: '+esc(input.value)+'</p>'});
 };input.oninput=renderMatches;renderMatches();
 }catch(error){if($('#course-search')===input)results.innerHTML='<p class="note">코스 목록을 불러오지 못했습니다. 구장 이름을 직접 입력해주세요.</p>'}
}
