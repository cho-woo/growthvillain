import test from 'node:test';
import assert from 'node:assert/strict';
import {deliveryLabel,elapsedDays,filterCards,safeUrl} from '../catalog.mjs';
import {rankChange,periodDays,countdown,snapshotFreshness} from '../monitoring.mjs';

test('reported end date freezes inclusive duration, independent of later collection',()=>{
  const card={deliveryStatus:'ended',startedAt:'2026-01-01',endedAt:'2026-07-01',collectedAt:'2026-10-07'};
  assert.equal(elapsedDays(card),182);assert.equal(deliveryLabel(card),'182일 게재 후 종료');
});
test('ended without known end never substitutes collection day',()=>{
  assert.equal(deliveryLabel({deliveryStatus:'ended',startedAt:'2026-01-01',collectedAt:'2026-10-07',durationDays:280}),'종료 · 기간 미확인');
});
test('detected end always labels its different basis',()=>{
  assert.equal(deliveryLabel({deliveryStatus:'ended',durationBasis:'detected',startedAt:'2026-01-01',endedDetectedAt:'2026-07-01T12:00:00+09:00'}),'182일 게재 후 종료 · 감지일 기준');
});
test('old cards are unknown, never active or ended by absence',()=>{
  assert.equal(deliveryLabel({startedAt:'2026-01-01',collectedAt:'2026-01-02'}),'2일 경과 · 상태 미확인');
  assert.equal(filterCards([{id:'1',media:[]},{id:'2',deliveryStatus:'ended',media:[]}],{delivery:'unknown'}).length,1);
});
test('date validation does not create negative periods',()=>{
  assert.equal(elapsedDays({deliveryStatus:'ended',startedAt:'2026-10-01',endedAt:'2026-01-01'}),null);
  assert.equal(elapsedDays({startedAt:'',collectedAt:'2026-10-01'}),null);
});
test('unranked prior term has no fabricated ordinal',()=>{
  assert.equal(rankChange({previousRank:null,currentRank:4,isNew:true,rankWindow:100}),'100위 밖 → 4위');
  assert.equal(rankChange({previousRank:60,currentRank:7}),'60위 → 7위');
  assert.equal(periodDays({previousDate:'2026-09-29',date:'2026-10-06'}),7);
});
test('a past schedule never claims imminent execution',()=>{
  const now=Date.parse('2026-10-07T03:00:00Z');
  assert.equal(countdown('2026-10-07T02:00:00Z',now),'예정 시각 지남 · 상태 갱신 대기');
  assert.equal(snapshotFreshness('2026-10-07T02:00:00Z',now).stale,true);
});
test('D drive assets use only site paths, refusing unsafe local URLs',()=>{
  assert.equal(safeUrl('/tools/meta-ads/media/123/file.mp4'),'/tools/meta-ads/media/123/file.mp4');
  for(const url of ['file:///D:/ad.mp4','/tools/meta-ads/media/../key','javascript:alert(1)','//evil.test/'])assert.equal(safeUrl(url),'');
});
