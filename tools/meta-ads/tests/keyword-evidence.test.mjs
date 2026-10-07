import test from 'node:test';
import assert from 'node:assert/strict';
import {cardKeywords,filterCards,matchesKeyword} from '../catalog.mjs';
import {linkedAds,startTiming,summarizeKeyword,copyMentionsKeyword,matchingInvestigation,metaSearchUrl} from '../keyword-evidence.mjs';

const observation={keyword:'락토핏유산균',previousDate:'2026-09-29',date:'2026-10-06'};
const ad=(id,extra={})=>({id,keyword:'락토핏유산균',advertiser:'광고주',domain:'example.com',text:'',media:[],...extra});

test('one ad preserves all recorded search queries',()=>{
  const card=ad('a',{keyword:'락토핏',matchedKeywords:['락토핏유산균','  락토핏  '],queryEvidence:[{query:'유산균'}]});
  assert.deepEqual(cardKeywords(card),['락토핏','락토핏유산균','유산균']);
  assert.equal(matchesKeyword(card,' 락토핏유산균 '),true);
  assert.equal(filterCards([card],{keyword:'유산균'}).length,1);
});
test('free-text mentions and partial query matches do not invent collected linkage',()=>{
  const card=ad('a',{keyword:'락토핏',text:'락토핏유산균 할인'});
  assert.equal(copyMentionsKeyword(card,observation.keyword),true);
  assert.deepEqual(linkedAds([card],observation),[]);
  assert.equal(filterCards([card],{keyword:'유산균'}).length,0);
});
test('explicit query evidence ad IDs link a legacy card without duplicating it',()=>{
  const card=ad('a',{keyword:'old query'});
  assert.equal(linkedAds([card,card],{...observation,adEvidence:{adIds:['a']}}).length,1);
});
test('comparison baseline is excluded, final source date is included',()=>{
  assert.equal(startTiming(ad('a',{startedAt:'2026-09-29'}),observation),'before-window');
  assert.equal(startTiming(ad('a',{startedAt:'2026-09-30'}),observation),'during-window');
  assert.equal(startTiming(ad('a',{startedAt:'2026-10-06'}),observation),'during-window');
  assert.equal(startTiming(ad('a',{startedAt:'2026-10-07'}),observation),'after-window');
});
test('invalid/missing dates stay unknown',()=>{
  assert.equal(startTiming(ad('a',{startedAt:'2026-02-30'}),observation),'unknown');
  assert.equal(startTiming(ad('a'),observation),'unknown');
  assert.equal(startTiming(ad('a',{startedAt:'2026-10-01'}),{...observation,previousDate:'2026-10-09'}),'unknown');
});
test('observations count ads, dates and literal text separately',()=>{
  const cards=[ad('a',{startedAt:'2026-09-30',text:'락토핏 유산균 쿠폰 할인',media:[{type:'video'},{type:'image'}]}),ad('b',{startedAt:'2026-09-28',text:'무료배송',media:[{type:'image'}]}),ad('c',{startedAt:'2026-10-07',text:'신제품 출시',advertiser:'다른 광고주'})];
  const value=summarizeKeyword(cards,observation);
  assert.equal(value.timing['during-window'],1);assert.equal(value.timing['before-window'],1);assert.equal(value.timing['after-window'],1);
  assert.equal(value.mentioned,1);assert.equal(value.videoAds,1);assert.equal(value.imageAds,2);
  assert.deepEqual(value.advertisers,[{name:'광고주',count:2},{name:'다른 광고주',count:1}]);
  assert.equal(value.themes.find(item=>item.label==='할인·적립').count,1);
  assert.equal(value.ads[0].id,'a');
});
test('points promotions are counted from actual ad copy',()=>{
  const value=summarizeKeyword([ad('a',{text:'10% 적립 혜택'})],observation);
  assert.equal(value.themes.find(item=>item.label==='할인·적립').count,1);
});
test('ads beginning after the observed rise do not become evidence of a new campaign in that rise',()=>{
  const value=summarizeKeyword([ad('a',{startedAt:'2026-10-07'})],observation);
  assert.equal(value.timing['during-window'],0);
  assert.equal(value.hypotheses[0].title,'비교 기간과 자료 시점');
});
test('research-note ad scope remains distinct from exact query results',()=>{
  const cards=[ad('a',{keyword:'락토핏'}),ad('b')];
  assert.deepEqual(filterCards(cards,{keyword:observation.keyword,keywordIds:['a'],ids:['a']}).map(row=>row.id),['a']);
  assert.deepEqual(linkedAds(cards,observation).map(row=>row.id),['b']);
});
test('a sourced investigation matches both keyword and observation period',()=>{
  const note={keyword:observation.keyword,comparison:{previousDate:'2026-09-29',currentDate:'2026-10-06'}};
  assert.equal(matchingInvestigation([note],observation),note);
  assert.equal(matchingInvestigation([note],{...observation,date:'2026-10-07'}),null);
  assert.equal(matchingInvestigation([note],{...observation,keyword:'락토핏'}),null);
});
test('every keyword gets an encoded public Meta search URL',()=>{
  const keyword='유산균 & 비타민';const url=new URL(metaSearchUrl(keyword));
  assert.equal(url.origin,'https://www.facebook.com');assert.equal(url.pathname,'/ads/library/');
  assert.equal(url.searchParams.get('q'),keyword);assert.equal(url.searchParams.get('active_status'),'all');
});
