import {periodDays,rankChange} from './monitoring.mjs';
const $ = selector => document.querySelector(selector);
const el = (tag, cls, text) => {const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
let request,local=false,data=null,initialized=false,pending=false,timer=null,formInitialized=false;
let reviewedKeyword='',visibleCount=8,historyLimit=30;
const datetime=value=>{const d=new Date(value);return value&&!Number.isNaN(d.getTime())?d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'기록 없음';};
export function initTrends({api,isLocal}) {
  request=api;local=isLocal;
  $('#trend-local').hidden=!local;$('#trend-public').hidden=local;
  if(!initialized){bind();initialized=true;}
  refresh();
}
function showError(error){$('#trend-error').textContent=error?.message||'';$('#trend-error').hidden=!error;}
async function refresh(){
  clearTimeout(timer);
  try{
    let result;
    if(local)result=await request('/trends');
    else {const response=await fetch('./data/trends.json',{cache:'no-store',signal:AbortSignal.timeout(10000)});if(!response.ok)throw new Error('아직 게시된 네이버 순위 기록이 없습니다. 첫 수집이 완료되면 표시됩니다.');result=await response.json();}
    if(!result||!Array.isArray(result.candidates))throw new Error('순위 기록의 형식을 확인할 수 없습니다.');
    render(result);showError(null);
  }catch(error){showError(error);if(!data){$('#trend-status').textContent='순위 기록 대기';$('#trend-results').replaceChildren(el('p','trend-empty','기록이 수집되면 이전 순위 → 현재 순위와 비교 기간이 여기에 표시됩니다.'));}}
  timer=setTimeout(refresh,local?6000:60000);
}
async function action(path,body={}){
  if(pending||!local)return false;pending=true;showError(null);
  try{const result=await request(path,'POST',body);if(result.settings)render(result);await refresh();return true;}
  catch(error){showError(error);return false;}finally{pending=false;}
}
function settings(){return {category:$('#trend-category').value,minimumRise:Number($('#trend-rise').value),newTop:Number($('#trend-new').value)};}
function periodLabel(row){const n=periodDays(row);return n?`${n}일 비교`:'비교 기간 미확인';}
function render(value){
  const completed=(value.candidates||[]).some(c=>c.state==='done'&&data?.candidates?.some(old=>old.dispatchKey===c.dispatchKey&&old.state==='queued'));
  data=value;
  if(completed)window.dispatchEvent(new CustomEvent('meta-ads-trend-complete'));
  if(!formInitialized&&value.settings){$('#trend-category').value=value.settings.category;$('#trend-rise').value=String(value.settings.minimumRise);$('#trend-new').value=String(value.settings.newTop);formInitialized=true;}
  $('#trend-auto').textContent=value.autoEnabled?'켜짐':'꺼짐';$('#trend-auto').setAttribute('aria-pressed',String(Boolean(value.autoEnabled)));
  $('#trend-scan').disabled=Boolean(value.scanning);$('#trend-scan').textContent=value.scanning?'네이버 순위 비교 중…':'지금 순위 비교 ↗';
  $('#trend-settings').querySelectorAll('select,button').forEach(control=>control.disabled=Boolean(value.scanning));
  $('#trend-results').setAttribute('aria-busy',String(Boolean(value.scanning)));
  const rows=[...(value.candidates||[])].sort((a,b)=>Number(a.needsReview)-Number(b.needsReview)||(Number(b.rankRise)||0)-(Number(a.rankRise)||0));
  const history=Array.isArray(value.history)?value.history:[];
  const confirmed=new Set(rows.filter(c=>!c.needsReview).map(c=>c.brandId||c.brandName||c.keyword)).size;
  $('#trend-candidate-count').textContent=rows.length;$('#trend-brand-count').textContent=confirmed;$('#trend-history-count').textContent=history.length;
  const dates=[value.sourceDate,value.latestDate,...rows.map(c=>c.currentDate||c.date),...history.map(c=>c.currentDate||c.date)].filter(v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)).sort();
  $('#trend-source-date').textContent=dates.at(-1)||'수집 대기';
  const categoryName=[...$('#trend-category').options].find(o=>o.value===value.settings?.category)?.textContent||'선택 분야';
  const last=value.lastSuccessAt||value.lastChecked;
  $('#trend-status').textContent=value.scanning&&local?'두 날짜의 일간 순위를 확인하고 있습니다.':value.error?value.error:last?`${categoryName} · 마지막 비교 ${datetime(last)}${local?' · 일간 순위 / 매시간 확인':` · 게시 ${datetime(value.updatedAt)}`}`:'첫 일간 순위 비교를 기다리고 있습니다.';
  const container=$('#trend-results'),focusKey=document.activeElement?.dataset?.trendFocus;
  container.replaceChildren();
  for(const c of rows.slice(0,visibleCount)){
    const row=el('article','trend-candidate'),identity=el('div','trend-identity');
    identity.append(el('span',c.needsReview?'trend-tag':'trend-tag confirmed',c.needsReview?'브랜드 미확인 검색어':'확인된 브랜드'),el('h3','',c.brandName||c.keyword));
    if(c.brandName&&c.brandName!==c.keyword)identity.append(el('p','trend-keyword',`검색어 · ${c.keyword}`));
    const rank=el('div','trend-rank');rank.append(el('strong','',rankChange(c)),el('span','rank-movement',c.isNew?'상위권 신규 진입':`↑ ${c.rankRise}계단 상승`),el('small','',`${periodLabel(c)} · ${c.previousDate||'?'} → ${c.currentDate||c.date||'?'}`));
    const actions=el('div','trend-row-actions');
    const button=(label,handler,secondary=false)=>{const b=el('button',secondary?'text-button':'button compact',label);b.type='button';b.dataset.trendFocus=`${c.keyword}:${label}`;b.addEventListener('click',handler);return b;};
    if(local){
      if(c.needsReview)actions.append(button('브랜드 확인',()=>openReview(c)),button('일반 검색어 · 제외',()=>action('/trends/ignore',{keyword:c.keyword}),true));
      else {
        const labels={queued:'수집 대기·진행 중',cooldown:'최근 수집한 브랜드',done:'수집 완료',failed:'수집 실패',stale:'순위 갱신 필요'};
        if(c.state&&c.state!=='ready')actions.append(el('span','trend-state',labels[c.state]||c.state));
        const b=button(c.state==='failed'?'다시 수집':'광고 수집',()=>action('/trends/collect',{dispatchKey:c.dispatchKey,limit:20}));b.disabled=['queued','cooldown','done','stale'].includes(c.state)||!c.dispatchKey;actions.append(b);
      }
    }
    if(!c.needsReview)actions.append(button('저장된 광고 보기 ↗',()=>showAds(c),true));
    row.append(identity,rank,actions);container.append(row);
  }
  if(!rows.length)container.append(el('div','trend-empty',last?'이번 비교에서 기준을 충족한 상승 후보가 없습니다. 누적 기록은 계속 보관됩니다.':'첫 수집이 완료되면 이전·현재 순위를 비교해 표시합니다.'));
  if(rows.length>visibleCount){const more=el('button','button compact',`상승 후보 ${rows.length-visibleCount}개 더 보기 ↓`);more.type='button';more.addEventListener('click',()=>{visibleCount+=8;render(data);});container.append(more);}
  if(focusKey)[...container.querySelectorAll('button')].find(b=>b.dataset.trendFocus===focusKey)?.focus({preventScroll:true});
  const brands=$('#trend-brands');brands.replaceChildren();
  if(value.brands?.length){brands.append(el('strong','','확인한 브랜드'));for(const b of value.brands)brands.append(el('span','trend-brand-chip',`${b.name}${b.domain?' · '+b.domain:''}`));}
  renderHistory();
}
function showAds(candidate){window.dispatchEvent(new CustomEvent('meta-ads-filter',{detail:{query:candidate.brandName||candidate.keyword}}));$('#gallery').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
function historyRows(){const q=$('#trend-history-search').value.trim().toLocaleLowerCase();return [...(data?.history||[])].filter(row=>!q||[row.brandName,row.keyword].join(' ').toLocaleLowerCase().includes(q)).sort((a,b)=>(Date.parse(b.currentDate||b.date)||0)-(Date.parse(a.currentDate||a.date)||0)||(Number(b.rankRise)||0)-(Number(a.rankRise)||0));}
function renderHistory(){
  const container=$('#trend-history-results'),rows=historyRows();container.replaceChildren();
  $('#trend-history-export').disabled=!rows.length;
  if(!rows.length){container.append(el('p','trend-empty',data?.history?.length?'검색 조건에 맞는 기록이 없습니다.':'아직 누적된 상승 기록이 없습니다. 첫 비교부터 날짜별로 쌓입니다.'));return;}
  const scroll=el('div','trend-table-scroll'),table=el('table','trend-table');
  const caption=el('caption','sr-only','네이버 인기검색어 상승 기록: 순위 변동, 비교 기간, 관측 시각');table.append(caption);
  const head=el('thead'),tr=el('tr');for(const title of ['브랜드·검색어','이전 → 현재','변동','비교 기간','기록 시각']){const th=el('th','',title);th.scope='col';tr.append(th);}head.append(tr);table.append(head);
  const body=el('tbody');
  for(const row of rows.slice(0,historyLimit)){
    const tr=el('tr'),identity=el('td'),rank=el('td','history-rank',rankChange(row)),rise=el('td','history-rise',row.isNew?'신규 진입':`↑ ${row.rankRise}계단`),period=el('td'),recorded=el('td','history-recorded');
    identity.append(el('strong','',row.brandName||row.keyword),el('small','',row.needsReview?'브랜드 미확인':row.brandName!==row.keyword?`검색어 · ${row.keyword}`:'확인된 브랜드'));
    period.append(el('span','',periodLabel(row)),el('small','',`${row.previousDate||'?'} — ${row.currentDate||row.date||'?'}`));
    recorded.append(el('span','',datetime(row.observedAt||row.lastObservedAt)));
    tr.append(identity,rank,rise,period,recorded);body.append(tr);
  }
  table.append(body);scroll.append(table);container.append(scroll,el('p','history-count',`총 ${rows.length}개 기록 · ${Math.min(rows.length,historyLimit)}개 표시`));
  if(rows.length>historyLimit){const more=el('button','button compact','이전 기록 더 보기 ↓');more.addEventListener('click',()=>{historyLimit+=30;renderHistory();});container.append(more);}
}
function openReview(candidate){reviewedKeyword=candidate.keyword;$('#trend-review-keyword').textContent=`네이버 검색어: ${candidate.keyword}`;$('#trend-brand-name').value=candidate.brandName||candidate.keyword;$('#trend-brand-aliases').value='';$('#trend-brand-domain').value='';$('#trend-review-error').hidden=true;$('#trend-review').showModal();$('#trend-brand-name').focus();}
function chooseTab(id){for(const tab of document.querySelectorAll('.trend-tabs [role=tab]')){const selected=tab.id===id;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;$('#'+tab.getAttribute('aria-controls')).hidden=!selected;}}
function bind(){
  $('#trend-settings').addEventListener('submit',e=>{e.preventDefault();action('/trends/settings',settings());});
  $('#trend-scan').addEventListener('click',async()=>{if(await action('/trends/settings',settings()))await action('/trends/scan');});
  $('#trend-auto').addEventListener('click',()=>action('/trends/settings',{autoEnabled:!data?.autoEnabled}));
  $('#trend-review-close').addEventListener('click',()=>$('#trend-review').close());
  for(const tab of document.querySelectorAll('.trend-tabs [role=tab]')){
    tab.addEventListener('click',()=>chooseTab(tab.id));
    tab.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const id=e.key==='Home'?'trend-current-tab':e.key==='End'?'trend-history-tab':tab.id==='trend-current-tab'?'trend-history-tab':'trend-current-tab';chooseTab(id);$('#'+id).focus();}});
  }
  $('#trend-history-search').addEventListener('input',()=>{historyLimit=30;renderHistory();});
  $('#trend-history-export').addEventListener('click',()=>{const blob=new Blob([JSON.stringify({exportedAt:new Date().toISOString(),source:'네이버 쇼핑 인사이트 일간 인기검색어',history:historyRows()},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='네이버-상승기록.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  $('#trend-brand-form').addEventListener('submit',async e=>{
    e.preventDefault();if(!local)return;const button=e.submitter;button.disabled=true;
    try{const name=$('#trend-brand-name').value.trim(),aliases=[...new Set([name,reviewedKeyword,...$('#trend-brand-aliases').value.split(',')].map(v=>v.trim()).filter(Boolean))];await request('/trends/brands','POST',{name,aliases,domain:$('#trend-brand-domain').value.trim()});$('#trend-review').close();await refresh();}
    catch(error){$('#trend-review-error').textContent=error.message;$('#trend-review-error').hidden=false;}finally{button.disabled=false;}
  });
}
