import {matchesKeyword,normalizeKeyword} from './catalog.mjs';

export function metaSearchUrl(keyword) {
  return `https://www.facebook.com/ads/library/?${new URLSearchParams({active_status:'all',ad_type:'all',country:'KR',q:String(keyword||''),search_type:'keyword_unordered'})}`;
}
function day(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}/.test(value))return null;
  const date=value.slice(0,10),parsed=Date.parse(date);
  return Number.isFinite(parsed)&&new Date(parsed).toISOString().slice(0,10)===date?date:null;
}
export function startTiming(card,observation) {
  const start=day(card.startedAt),from=day(observation.previousDate),to=day(observation.currentDate||observation.date);
  if(!start||!from||!to||from>=to)return 'unknown';
  return start<=from?'before-window':start<=to?'during-window':'after-window';
}
export function copyMentionsKeyword(card,keyword) {
  const term=normalizeKeyword(keyword).replace(/\s+/g,'');
  const copy=normalizeKeyword([card.text,card.headline].filter(Boolean).join(' ')).replace(/\s+/g,'');
  return Boolean(term)&&copy.includes(term);
}
export function linkedAds(cards,observation) {
  const query=observation.searchQuery||observation.keyword;
  const ids=new Set(observation.adEvidence?.adIds||[]),unique=new Map();
  for(const card of cards){if(card?.id&&(ids.has(card.id)||matchesKeyword(card,query)))unique.set(card.id,card);}
  return [...unique.values()];
}
function groups(cards,field){
  const counts=new Map();
  for(const card of cards){const value=typeof card[field]==='string'?card[field].trim():'';if(value)counts.set(value,(counts.get(value)||0)+1);}
  return [...counts].map(([name,count])=>({name,count})).sort((a,b)=>b.count-a.count||a.name.localeCompare(b.name,'ko'));
}
export function summarizeKeyword(cards,observation) {
  const query=observation.searchQuery||observation.keyword,ads=linkedAds(cards,observation);
  const timing={'before-window':0,'during-window':0,'after-window':0,unknown:0};
  const expressions=[{label:'할인·적립',terms:['할인','쿠폰','특가','세일','sale','적립']},{label:'사은·배송',terms:['증정','사은','무료배송','무료 배송','1+1']},{label:'신규·한정',terms:['신제품','신상','출시','한정','마감']}];
  let mentioned=0,videoAds=0,imageAds=0;
  for(const card of ads){timing[startTiming(card,observation)]+=1;mentioned+=Number(copyMentionsKeyword(card,query));videoAds+=Number(card.media?.some(m=>m.type==='video'));imageAds+=Number(card.media?.some(m=>m.type==='image'));}
  const themes=expressions.map(item=>({...item,count:ads.filter(card=>item.terms.some(term=>normalizeKeyword([card.text,card.headline].join(' ')).includes(term))).length})).filter(item=>item.count>0);
  const startsDuring = ads.filter(card=>startTiming(card,observation)==='during-window');
  const hypotheses=[];
  if(startsDuring.length)hypotheses.push({title:'새 광고 시작 시점',fact:`비교 기간에 시작한 광고 ${startsDuring.length}개`,question:'새 집행의 노출 증가와 검색 관심도 상승이 같은 시기에 나타났는지 확인해 보세요.',needed:'일별 광고 노출·집행비, 네이버 일별 검색 추이'});
  if(themes.length)hypotheses.push({title:'혜택·출시 문구',fact:themes.map(item=>`${item.label} 표현 ${item.count}개`).join(' · '),question:'행사나 신제품 안내가 검색 동기와 관련됐는지, 해당 문구의 노출 시점부터 확인해 보세요.',needed:'행사 일정, 소재별 노출·클릭, 검색 유입 변화'});
  if(timing['before-window']&&!startsDuring.length)hypotheses.push({title:'기존 소재와 다른 유입 경로',fact:`이전 기준일까지 시작한 광고 ${timing['before-window']}개 · 시작일 미확인 ${timing.unknown}개`,question:'기존 광고의 집행량 변화와 다른 채널의 노출도 함께 비교해 보세요.',needed:'기존 소재별 일간 집행량, 콘텐츠 게시일, 유입 경로'});
  if(ads.length&&!startsDuring.length&&!timing['before-window'])hypotheses.push({title:'비교 기간과 자료 시점',fact:`현재 기준일 뒤에 시작 ${timing['after-window']}개 · 시작일 미확인 ${timing.unknown}개`,question:'현재 수집된 광고로 과거 상승을 설명하기 전에 당시의 광고 자료가 있는지 확인해 보세요.',needed:'상승 기간의 광고 기록, 원본 시작일, 당시 검색 유입 자료'});
  const priority=card=>(startTiming(card,observation)==='during-window'?2:0)+(copyMentionsKeyword(card,query)?1:0);
  return {query,ads:[...ads].sort((a,b)=>priority(b)-priority(a)||(Date.parse(b.startedAt)||0)-(Date.parse(a.startedAt)||0)),timing,mentioned,videoAds,imageAds,advertisers:groups(ads,'advertiser'),domains:groups(ads,'domain'),themes,hypotheses};
}
export function matchingInvestigation(entries,observation){
  return (Array.isArray(entries)?entries:[]).find(entry=>normalizeKeyword(entry.keyword)===normalizeKeyword(observation.keyword)&&entry.comparison?.previousDate===observation.previousDate&&entry.comparison?.currentDate===(observation.currentDate||observation.date))||null;
}
