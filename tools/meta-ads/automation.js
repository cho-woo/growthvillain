import {countdown,snapshotFreshness} from './monitoring.mjs';
const $ = selector => document.querySelector(selector);
const element = (tag,cls,text) => {const el=document.createElement(tag);if(cls)el.className=cls;if(text!==undefined)el.textContent=text;return el;};
let local=false,request=null,snapshot=null,lastContact=0,pollTimer=null,tickTimer=null,loading=false;
function timestamp(value){const d=new Date(value);return value&&!Number.isNaN(d.getTime())?d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'기록 없음';}
export function initAutomation({api,isLocal}) {
  if(local!==isLocal){lastContact=0;snapshot=null;}
  local=isLocal;request=api;
  clearTimeout(pollTimer);clearInterval(tickTimer);
  refresh();tickTimer=setInterval(render,1000);
}
async function refresh(){
  clearTimeout(pollTimer);
  if(loading){pollTimer=setTimeout(refresh,2000);return;}
  loading=true;
  try{
    if(local){snapshot=await request('/automations');}
    else {const response=await fetch('./data/automation.json',{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error('아직 게시된 자동화 상태가 없습니다.');snapshot=await response.json();}
    lastContact=Date.now();snapshot.error=null;
  }catch(error){if(!snapshot)snapshot={automations:[]};snapshot.error=error.message;}
  finally{loading=false;render();pollTimer=setTimeout(refresh,local?5000:60000);}
}
function render(){
  const root=$('#automation-cards');if(!root)return;
  const connected=local&&lastContact>0&&Date.now()-lastContact<15000&&!snapshot?.error;
  const freshness=snapshotFreshness(snapshot?.updatedAt);
  const pill=$('#automation-connection');pill.className=`monitor-pill ${connected?'connected':snapshot?.error||freshness.stale?'stale':''}`;
  pill.textContent=connected?'PC 실시간 연결':local?'PC 연결 끊김':'게시된 상태 기록';
  $('#automation-updated').textContent=local?(connected?'5초마다 상태 확인':`마지막 연결 ${lastContact?timestamp(new Date(lastContact).toISOString()):'없음'}`):`${freshness.label} · ${timestamp(snapshot?.updatedAt)}`;
  $('#automation-note').textContent=snapshot?.error|| (local?'이 PC에서 응답한 상태입니다. 자동 실행을 켜도 PC와 수집 프로그램이 실행 중이어야 합니다.':'공개 페이지는 마지막으로 게시된 상태를 보여줍니다. PC의 현재 ON/OFF는 상태창에서 확인하세요.');
  root.replaceChildren();
  const records=Array.isArray(snapshot?.automations)?snapshot.automations:[];
  for(const record of records){
    const card=element('article','automation-card');
    const heading=element('div','automation-card-heading');
    const active=Boolean(record.running),enabled=Boolean(record.enabled),state=record.state||'';
    heading.append(element('h3','',record.name||'자동화'),element('span',`automation-switch ${enabled?'on':'off'}`,`${local?'':'기록: '}${enabled?'ON':'OFF'}`));
    card.append(heading);
    const label=!connected&&local?'현재 상태 확인 필요':state==='offline'?'프로세스 응답 없음':state==='blocked'?'확인 필요':state==='stopping'?'현재 작업 후 대기':active?(local?'실행 중':'게시 당시 실행 중'):/fail|error/.test(state)?'확인 필요':enabled?'다음 실행 대기':'자동 실행 꺼짐';
    card.append(element('p',`automation-state ${active&&connected?'running':''}`,label));
    const facts=element('dl','automation-facts');
    facts.append(element('dt','','최근 성공'),element('dd','',timestamp(record.lastSuccessAt)));
    facts.append(element('dt','','다음 예정'),element('dd','',enabled&&record.nextRunAt?timestamp(record.nextRunAt):'예약 없음'));
    if(Number(record.intervalSeconds)>0)facts.append(element('dt','','수집 간격'),element('dd','',Number(record.intervalSeconds)>=3600?`${Number(record.intervalSeconds)/3600}시간마다`:`${Math.round(Number(record.intervalSeconds)/60)}분마다`));
    if(Number(record.statusCheckIntervalSeconds)>0)facts.append(element('dt','','상태 확인 주기'),element('dd','',`${record.statusCheckBatchSize||10}개 / ${Number(record.statusCheckIntervalSeconds)/3600}시간`));
    if(record.nextStatusCheckAt)facts.append(element('dt','','게재 상태 확인'),element('dd','',timestamp(record.nextStatusCheckAt)));
    card.append(facts);
    if(enabled&&record.nextRunAt)card.append(element('p','automation-countdown',local&&connected?countdown(record.nextRunAt):'게시 시점의 예정 일정'));
    if(record.message)card.append(element('p','automation-message',record.message));
    root.append(card);
  }
  if(!records.length)root.append(element('p','monitor-empty',snapshot?.error?'상태를 확인할 수 없습니다. 저장된 광고와 순위 기록은 아래에서 볼 수 있습니다.':'자동화 상태를 불러오는 중입니다.'));
  const publication=snapshot?.publication;
  $('#publication-state').textContent=publication?`사이트 게시 전송 · ${publication.error?'확인 필요':['running','publishing'].includes(publication.state)?'전송 중':timestamp(publication.lastSuccessAt)} · 연결된 사이트 빌드 후 반영`:'사이트 게시 전송 시각 확인 중';
}
