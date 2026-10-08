import {collectionPolicyText} from './trend-policy.mjs';
import {categoryName,scopeRows,observationKey,categorySources,fixedSettings,notesForCategory} from './trend-scope.mjs';
import {periodDays,rankChange} from './monitoring.mjs';
import {linkedAds,summarizeKeyword,startTiming,copyMentionsKeyword,metaSearchUrl,matchingInvestigation} from './keyword-evidence.mjs';
import {safeUrl} from './catalog.mjs';
const $ = selector => document.querySelector(selector);
const el = (tag, cls, text) => {const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
let request,local=false,data=null,initialized=false,pending=false,timer=null,formInitialized=false;
let visibleCount=8,historyLimit=30,selected=null,researchSignature='',viewCategory='all';
let getCards=()=>[],renderCard=null;
let investigations={entries:[]},lastNotesFetch=0;
const datetime=value=>{const d=new Date(value);return value&&!Number.isNaN(d.getTime())?d.toLocaleString('ko-KR',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'기록 없음';};
export function initTrends({api,isLocal,cards,cardView}) {
  request=api;local=isLocal;getCards=cards||getCards;renderCard=cardView||renderCard;
  $('#trend-local').hidden=!local;$('#trend-public').hidden=local;
  if(!initialized){bind();initialized=true;}
  refresh();refreshInvestigations();
}
async function refreshInvestigations(){
  if(Date.now()-lastNotesFetch<300000)return;lastNotesFetch=Date.now();
  try{const response=await fetch('./data/investigations.json',{cache:'no-store',signal:AbortSignal.timeout(10000)});if(response.ok){const value=await response.json();if(Array.isArray(value.entries))investigations=value;}else if(response.status===404)investigations={entries:[]};}
  catch{}
  researchSignature='';renderInvestigation();
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
  refreshInvestigations();timer=setTimeout(refresh,local?6000:60000);
}
async function action(path,body={}){
  if(pending||!local)return false;pending=true;showError(null);
  try{const result=await request(path,'POST',body);if(result.settings)render(result);await refresh();return true;}
  catch(error){showError(error);return false;}finally{pending=false;}
}
function settings(){return fixedSettings($('#trend-rise').value,$('#trend-new').value);}
function periodLabel(row){const n=periodDays(row);return n?`${n}일 비교`:'비교 기간 미확인';}
function render(value){
  const completed=(value.candidates||[]).some(c=>c.state==='done'&&data?.candidates?.some(old=>old.dispatchKey===c.dispatchKey&&old.state==='queued'));
  data=value;
  if(completed)window.dispatchEvent(new CustomEvent('meta-ads-trend-complete'));
  if(!formInitialized&&value.settings){$('#trend-rise').value=String(value.settings.minimumRise);$('#trend-new').value=String(value.settings.newTop);formInitialized=true;}
  $('#trend-auto').textContent=value.autoEnabled?'켜짐':'꺼짐';$('#trend-auto').setAttribute('aria-pressed',String(Boolean(value.autoEnabled)));
  $('#trend-scan').disabled=Boolean(value.scanning);$('#trend-scan').textContent=value.scanning?'네이버 순위 비교 중…':'지금 순위 비교 ↗';
  $('#trend-settings').querySelectorAll('select,button').forEach(control=>control.disabled=Boolean(value.scanning));
  $('#trend-results').setAttribute('aria-busy',String(Boolean(value.scanning)));
  const rows=scopeRows(value.candidates,viewCategory).sort((a,b)=>(Number(b.rankRise)||0)-(Number(a.rankRise)||0)||(Number(a.currentRank)||100)-(Number(b.currentRank)||100));
  const history=scopeRows(value.history,viewCategory);
  const connected=rows.filter(c=>(c.adEvidence?.adCount||linkedAds(getCards(),c).length)>0).length;
  $('#trend-candidate-count').textContent=rows.length;$('#trend-linked-count').textContent=connected;$('#trend-history-count').textContent=history.length;
  const policy=value.collectionPolicy;
  $('#trend-policy').textContent=collectionPolicyText(policy,{trendEnabled:value.autoEnabled,formatTime:datetime});
  const sources=categorySources(value);
  $('#trend-source-date').textContent=sources.map(source=>`${source.categoryName} ${source.sourceDate||'수집 대기'}`).join('\n');
  const sourceStatus=$('#trend-source-status');sourceStatus.replaceChildren();
  for(const source of sources){const item=el('li');item.append(el('strong','',source.categoryName),el('span','',source.sourceDate?`${source.previousSourceDate||'?'} → ${source.sourceDate}`:'첫 순위 기록 대기'));if(source.lastChecked)item.append(el('small','',`확인 ${datetime(source.lastChecked)}`));if(source.error)item.append(el('small','source-error',`확인 필요 · ${source.error}`));sourceStatus.append(item);}
  const selectedCategoryName=viewCategory==='all'?'건강식품 · 다이어트식품':categoryName(viewCategory);
  const last=value.lastSuccessAt||value.lastChecked;
  $('#trend-status').textContent=value.scanning&&local?'두 분야의 일간 순위를 확인하고 있습니다.':value.error?value.error:last?`${selectedCategoryName} · 일간 순위 / 매시간 확인${local?'':` · 게시 ${datetime(value.updatedAt)}`}`:'두 분야의 첫 일간 순위 비교를 기다리고 있습니다.';
  const container=$('#trend-results'),focusKey=document.activeElement?.dataset?.trendFocus;
  container.replaceChildren();
  for(const c of rows.slice(0,visibleCount)){
    const row=el('article','trend-candidate'),identity=el('div','trend-identity');
    const count=c.adEvidence?.adCount||linkedAds(getCards(),c).length;
    identity.append(el('span','trend-category-badge',categoryName(c.category)),el('span',count?'trend-tag confirmed':'trend-tag',count?`연결 광고 ${count}개`:'콘텐츠 수집 대기'),el('h3','',c.keyword));
    if(c.collectionReason==='historical-backlog')identity.append(el('p','trend-keyword',`과거 상승 기록 · ${c.sourceAgeDays}일 전 기준`));
    if(c.brandName)identity.append(el('p','trend-keyword',`참고 광고주·브랜드명 · ${c.brandName}`));
    const rank=el('div','trend-rank');rank.append(el('strong','',rankChange(c)),el('span','rank-movement',c.isNew?'상위권 신규 진입':`↑ ${c.rankRise}계단 상승`),el('small','',`${periodLabel(c)} · ${c.previousDate||'?'} → ${c.currentDate||c.date||'?'}`));
    const actions=el('div','trend-row-actions');
    const button=(label,handler,secondary=false)=>{const b=el('button',secondary?'text-button':'button compact',label);b.type='button';b.dataset.trendFocus=`${observationKey(c)}:${label}`;b.addEventListener('click',handler);return b;};
    actions.append(button('콘텐츠 조사 →',()=>selectKeyword(c)));
    const direct=el('a','text-button','Meta 검색 ↗');direct.href=metaSearchUrl(c.searchQuery||c.keyword);direct.target='_blank';direct.rel='noopener noreferrer';actions.append(direct);
    const labels={queued:'광고 검색 대기·진행 중',cooldown:'최근 검색한 키워드',done:'광고 검색 완료',failed:'광고 검색 실패',stale:'순위 갱신 필요',ready:'자동 검색 차례 대기',backlog:'과거 상승 · 수집 대기'};
    if(c.state)actions.append(el('span','trend-state',labels[c.state]||c.state));
    if(local){const b=button(c.state==='failed'?'광고 다시 수집':'지금 광고 수집',()=>action('/trends/collect',{dispatchKey:c.dispatchKey,limit:100}),true);b.disabled=['queued','cooldown','done','stale'].includes(c.state)||!c.dispatchKey;actions.append(b);}
    row.append(identity,rank,actions);container.append(row);
  }
  if(!rows.length)container.append(el('div','trend-empty',last?'이번 비교에서 기준을 충족한 상승 후보가 없습니다. 누적 기록은 계속 보관됩니다.':'첫 수집이 완료되면 이전·현재 순위를 비교해 표시합니다.'));
  if(rows.length>visibleCount){const more=el('button','button compact',`상승 후보 ${rows.length-visibleCount}개 더 보기 ↓`);more.type='button';more.addEventListener('click',()=>{visibleCount+=8;render(data);});container.append(more);}
  if(focusKey)[...container.querySelectorAll('button')].find(b=>b.dataset.trendFocus===focusKey)?.focus({preventScroll:true});
  if(selected)selected=[...rows,...history].find(row=>observationKey(row)===observationKey(selected))||selected;
  if(!selected&&rows.length)selected=rows.find(row=>linkedAds(getCards(),row).length)||rows[0];
  renderHistory();
  renderInvestigation();
}
function showAds(candidate,filters={}){window.dispatchEvent(new CustomEvent('meta-ads-filter',{detail:{keyword:candidate.searchQuery||candidate.keyword,ids:linkedAds(getCards(),candidate).map(card=>card.id),...filters}}));$('#gallery').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
function historyRows(){const q=$('#trend-history-search').value.trim().toLocaleLowerCase();return scopeRows(data?.history,viewCategory).filter(row=>!q||String(row.keyword||'').toLocaleLowerCase().includes(q)).sort((a,b)=>(Date.parse(b.currentDate||b.date)||0)-(Date.parse(a.currentDate||a.date)||0)||(Number(b.rankRise)||0)-(Number(a.rankRise)||0));}
function renderHistory(){
  const container=$('#trend-history-results'),rows=historyRows();container.replaceChildren();
  $('#trend-history-export').disabled=!rows.length;
  if(!rows.length){container.append(el('p','trend-empty',data?.history?.length?'검색 조건에 맞는 기록이 없습니다.':'아직 누적된 상승 기록이 없습니다. 첫 비교부터 날짜별로 쌓입니다.'));return;}
  const scroll=el('div','trend-table-scroll'),table=el('table','trend-table');
  const caption=el('caption','sr-only','네이버 인기검색어 상승 기록: 순위 변동, 비교 기간, 관측 시각');table.append(caption);
  const head=el('thead'),tr=el('tr');for(const title of ['급상승 키워드','이전 → 현재','변동','비교 기간','기록 시각']){const th=el('th','',title);th.scope='col';tr.append(th);}head.append(tr);table.append(head);
  const body=el('tbody');
  for(const row of rows.slice(0,historyLimit)){
    const tr=el('tr'),identity=el('td'),rank=el('td','history-rank',rankChange(row)),rise=el('td','history-rise',row.isNew?'신규 진입':`↑ ${row.rankRise}계단`),period=el('td'),recorded=el('td','history-recorded');
    const choose=el('button','history-keyword',row.keyword);choose.type='button';choose.addEventListener('click',()=>selectKeyword(row));identity.append(el('span','trend-category-badge',categoryName(row.category)),choose,el('small','',`광고 ${row.adEvidence?.adCount||linkedAds(getCards(),row).length}개 · 콘텐츠 조사 ↗`));
    period.append(el('span','',periodLabel(row)),el('small','',`${row.previousDate||'?'} — ${row.currentDate||row.date||'?'}`));
    recorded.append(el('span','',datetime(row.observedAt||row.lastObservedAt)));
    tr.append(identity,rank,rise,period,recorded);body.append(tr);
  }
  table.append(body);scroll.append(table);container.append(scroll,el('p','history-count',`총 ${rows.length}개 기록 · ${Math.min(rows.length,historyLimit)}개 표시`));
  if(rows.length>historyLimit){const more=el('button','button compact','이전 기록 더 보기 ↓');more.addEventListener('click',()=>{historyLimit+=30;renderHistory();});container.append(more);}
}
function selectKeyword(candidate){
  selected=candidate;researchSignature='';renderInvestigation();
  $('#keyword-investigation').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});
  $('#keyword-investigation-title').focus({preventScroll:true});
}
function researchButton(label,handler,cls='button compact'){
  const button=el('button',cls,label);button.type='button';button.addEventListener('click',handler);return button;
}
function renderInvestigation(){
  if(!selected)return;
  const summary=summarizeKeyword(getCards(),selected),note=matchingInvestigation(notesForCategory(investigations.entries,selected.category),selected),signature=JSON.stringify({selected,ads:summary.ads,note});
  if(signature===researchSignature)return;researchSignature=signature;
  $('#keyword-investigation').hidden=false;
  $('#keyword-investigation-title').textContent=`“${selected.keyword}” 콘텐츠 조사`;
  $('#keyword-comparison').textContent=`${categoryName(selected.category)} · ${rankChange(selected)} · ${periodLabel(selected)} · ${selected.previousDate||'?'} → ${selected.currentDate||selected.date||'?'}`;
  const actions=$('#keyword-investigation-actions');actions.replaceChildren();
  const search=el('a','button compact','Meta에서 이 키워드 검색 ↗');search.href=metaSearchUrl(summary.query);search.target='_blank';search.rel='noopener noreferrer';actions.append(search);
  if(summary.ads.length)actions.append(researchButton(`연결 광고 ${summary.ads.length}개 전체 보기 ↓`,()=>showAds(selected)));
  if(local&&selected.dispatchKey&&['ready','backlog','failed'].includes(selected.state))actions.append(researchButton('이 키워드 광고 수집',()=>action('/trends/collect',{dispatchKey:selected.dispatchKey,limit:100})));
  const dates=summary.ads.map(card=>card.collectedAt).filter(Boolean).sort();
  const collectedAt=selected.adEvidence?.lastCollectedAt||dates.at(-1);
  $('#keyword-evidence-source').textContent=`검색어 “${summary.query}”로 수집된 광고 · 최근 수집 ${datetime(collectedAt)} · 검색 결과 연결이며 상승 원인으로 확정된 자료는 아닙니다.`;
  const facts=$('#keyword-facts');facts.replaceChildren();
  for(const [label,value] of [['연결된 광고',summary.ads.length],['비교 기간에 시작',summary.timing['during-window']],['문구에 키워드 포함',summary.mentioned],['확인된 광고주',summary.advertisers.length]]){const item=el('div');item.append(el('span','',label),el('strong','',String(value)));facts.append(item);}
  const timing=$('#keyword-timing');timing.replaceChildren();
  timing.append(el('h4','','광고 시작일과 검색 순위 비교 기간'));
  const bar=el('div','keyword-timing-bar');bar.setAttribute('aria-hidden','true');
  const legend=el('div','keyword-timing-legend');
  const labels={'before-window':'이전 기준일까지 시작','during-window':'비교 기간에 시작','after-window':'현재 기준일 뒤에 시작',unknown:'시작일·비교일 미확인'};
  for(const [key,count] of Object.entries(summary.timing)){
    if(count){const segment=el('span',`timing-${key}`);segment.style.flexGrow=String(count);bar.append(segment);}
    legend.append(el('span',`timing-label timing-${key}`,`${labels[key]} ${count}개`));
  }
  if(summary.ads.length)timing.append(bar,legend);
  timing.append(el('p','timing-definition',`비교 기간: ${selected.previousDate||'?'} 다음 날부터 ${selected.currentDate||selected.date||'?'}까지. 광고 시작일과 실제 노출량은 서로 다른 정보입니다.`));
  const observed=$('#keyword-observations');observed.replaceChildren();
  const media=el('p','observation-media',`영상 포함 광고 ${summary.videoAds}개 · 이미지 포함 광고 ${summary.imageAds}개 (한 광고에 둘 다 있을 수 있음)`);observed.append(media);
  const group=(title,items,field)=>{
    const block=el('div','observation-group');block.append(el('h5','',title));
    if(!items.length)block.append(el('p','muted','아직 확인된 자료 없음'));
    for(const item of items.slice(0,5))block.append(researchButton(`${item.name} · ${item.count}개`,()=>showAds(selected,{[field]:item.name}),'evidence-chip'));
    observed.append(block);
  };
  group('광고주별 소재',summary.advertisers,'advertiser');group('랜딩 도메인',summary.domains,'domain');
  const themes=el('div','observation-group');themes.append(el('h5','','광고 문구에 등장한 표현'));
  for(const theme of summary.themes)themes.append(el('span','evidence-chip',`${theme.label} · ${theme.count}개`));
  if(!summary.themes.length)themes.append(el('p','muted','분류할 혜택·출시 표현이 아직 없습니다. 원문에서 직접 확인할 수 있습니다.'));
  observed.append(themes);
  const hypotheses=$('#keyword-hypotheses');hypotheses.replaceChildren();
  for(const hypothesis of summary.hypotheses){const item=el('article','keyword-hypothesis');item.append(el('h5','',hypothesis.title),el('p','hypothesis-fact',hypothesis.fact),el('p','',hypothesis.question),el('small','',`추가로 필요한 자료 · ${hypothesis.needed}`));hypotheses.append(item);}
  if(!summary.hypotheses.length)hypotheses.append(el('p','research-empty','광고가 수집되면 시작일과 문구를 근거로 확인할 가설을 정리합니다.'));
  const creatives=$('#keyword-creatives');creatives.replaceChildren();
  $('#keyword-creative-order').textContent=summary.ads.length?'비교 기간 시작 → 문구 일치 순 · 성과 순위 아님':'';
  for(const card of summary.ads.slice(0,6)){
    if(!renderCard)break;
    const wrap=el('div','research-creative'),badges=el('div','research-creative-badges');
    badges.append(el('span',`timing-badge timing-${startTiming(card,selected)}`,labels[startTiming(card,selected)]));
    if(copyMentionsKeyword(card,summary.query))badges.append(el('span','copy-match-badge','문구 키워드 일치'));
    wrap.append(badges,renderCard(card));creatives.append(wrap);
  }
  if(!summary.ads.length)creatives.append(el('div','trend-empty',selected.adEvidence?.adCount?'연결 기록이 확인되었습니다. 소재 파일의 사이트 반영을 기다리고 있습니다.':'아직 이 키워드로 저장된 광고가 없습니다. 수집 결과가 들어오면 이미지·영상·문구가 연결됩니다.'));
  const more=$('#keyword-more');more.replaceChildren();
  if(summary.ads.length)more.append(researchButton(`갤러리에서 ${summary.ads.length}개 광고 비교하기 →`,()=>showAds(selected)));
  renderInvestigationNote(note);
}
function renderInvestigationNote(note){
  const container=$('#keyword-notes');container.replaceChildren();container.hidden=!note;if(!note)return;
  container.append(el('p','research-label','SOURCE CHECK'),el('h4','','출처를 추가 확인한 조사 메모'),el('p','keyword-note-date',`${note.comparison.previousDate} → ${note.comparison.currentDate} 비교 · 메모 갱신 ${datetime(investigations.updatedAt)}`));
  const observations=el('ul','investigation-observations');
  for(const observation of note.observations||[]){const li=el('li');li.append(el('p','',observation.text));for(const url of observation.sourceUrls||[]){const safe=safeUrl(url);if(!safe)continue;const source=(note.sources||[]).find(item=>item.url===url);const link=el('a','investigation-source',`${source?.title||'출처 확인'} ↗`);link.href=safe;link.target='_blank';link.rel='noopener noreferrer';li.append(link);}observations.append(li);}container.append(observations);
  if(note.hypotheses?.length){container.append(el('h5','','검토할 가설'));const list=el('ul','investigation-hypotheses');for(const text of note.hypotheses)list.append(el('li','',text));container.append(list);}
  if(note.limitations?.length){container.append(el('h5','','확인되지 않은 부분'));const list=el('ul','investigation-limitations');for(const text of note.limitations)list.append(el('li','',text));container.append(list);}
  const ids=new Set(note.adIds||[]),stored=getCards().filter(card=>ids.has(card.id));
  if(ids.size){
    container.append(el('h5','','조사 메모에 참고한 광고'),el('p','keyword-note-provenance',`참고 광고 ${ids.size}개 중 보관된 소재 ${stored.length}개 · 조사 메모로 연결한 자료이며, 이 키워드의 정확한 검색 결과와는 별도로 표시합니다.`));
    const samples=el('div','cards note-creatives');for(const card of stored.slice(0,3)){if(renderCard)samples.append(renderCard(card));}container.append(samples);
    if(stored.length)container.append(researchButton(`참고 광고 ${stored.length}개 전체 비교 →`,()=>{window.dispatchEvent(new CustomEvent('meta-ads-filter',{detail:{keyword:selected.keyword,ids:[...ids],mode:'notes',label:'조사 메모 참고 광고'}}));$('#gallery').scrollIntoView({behavior:'smooth',block:'start'});}));
    const originals=el('details','note-originals');originals.append(el('summary','',`참고 광고 원문 ${ids.size}개`));for(const id of ids){if(!/^\d+$/.test(String(id)))continue;const link=el('a','investigation-source',`광고 ${id} ↗`);link.href=`https://www.facebook.com/ads/library/?id=${id}`;link.target='_blank';link.rel='noopener noreferrer';originals.append(link);}container.append(originals);
  }
}
function chooseTab(id){for(const tab of document.querySelectorAll('.trend-tabs [role=tab]')){const selected=tab.id===id;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;$('#'+tab.getAttribute('aria-controls')).hidden=!selected;}}
function bind(){
  $('#trend-view-category').addEventListener('change',()=>{viewCategory=$('#trend-view-category').value;visibleCount=8;historyLimit=30;selected=null;researchSignature='';$('#keyword-investigation').hidden=true;if(data)render(data);});
  $('#trend-settings').addEventListener('submit',e=>{e.preventDefault();action('/trends/settings',settings());});
  $('#trend-scan').addEventListener('click',async()=>{if(await action('/trends/settings',settings()))await action('/trends/scan');});
  $('#trend-auto').addEventListener('click',()=>action('/trends/settings',{autoEnabled:!data?.autoEnabled}));
  for(const tab of document.querySelectorAll('.trend-tabs [role=tab]')){
    tab.addEventListener('click',()=>chooseTab(tab.id));
    tab.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const id=e.key==='Home'?'trend-current-tab':e.key==='End'?'trend-history-tab':tab.id==='trend-current-tab'?'trend-history-tab':'trend-current-tab';chooseTab(id);$('#'+id).focus();}});
  }
  $('#trend-history-search').addEventListener('input',()=>{historyLimit=30;renderHistory();});
  $('#trend-history-export').addEventListener('click',()=>{const blob=new Blob([JSON.stringify({exportedAt:new Date().toISOString(),source:'네이버 쇼핑 인사이트 일간 인기검색어',history:historyRows()},null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='네이버-상승기록.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  window.addEventListener('meta-ads-catalog-updated',()=>{researchSignature='';if(data)render(data);});
}
