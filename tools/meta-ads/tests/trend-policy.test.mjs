import test from 'node:test';
import assert from 'node:assert/strict';
import {collectionPolicyText} from '../trend-policy.mjs';

const ready={maxDailyQueries:288,maxAdsPerQuery:100,intervalSeconds:300,dailyUsed:2,dailyRemaining:286,
  metaAutoEnabled:true,enabled:true,collectionGuard:{state:'ready',reason:null},nextDispatchAt:'NEXT'};
const options={trendEnabled:true,formatTime:value=>value};

test('ready policy describes upper bounds without promising new ads',()=>{
  const text=collectionPolicyText(ready,options);
  assert.match(text,/최소 5분 간격/);assert.match(text,/검색당 최대 100개 광고/);
  assert.match(text,/하루 최대 288회 검색/);assert.match(text,/기존 광고가 포함/);
  assert.match(text,/다음 검색 NEXT/);assert.doesNotMatch(text,/OFF|현재 대기/);
  assert.doesNotMatch(collectionPolicyText({...ready,collectionGuard:{state:'ready',reason:'정상'}},options),/현재 대기/);
});

test('temporary source block does not pretend an ON automation is OFF',()=>{
  const text=collectionPolicyText({...ready,enabled:false,pausedReason:'접근 제한 대기',
    collectionGuard:{state:'blocked',reason:'generic',nextAllowedAt:'LATER'},nextDispatchAt:'LATER'},options);
  assert.match(text,/자동 수집 설정 ON/);assert.match(text,/현재 대기 · 접근 제한 대기/);
  assert.match(text,/다음 확인 LATER/);assert.doesNotMatch(text,/OFF|generic/);
});

test('storage wait has no misleading next-time promise even if a stale time remains',()=>{
  const text=collectionPolicyText({...ready,enabled:false,collectionGuard:{state:'storage',reason:'C·D 저장 공간 확보 필요',storageReady:false}},options);
  assert.match(text,/현재 대기 · C·D 저장 공간 확보 필요/);
  assert.doesNotMatch(text,/OFF|다음 검색|다음 확인/);
});

test('actual OFF is stated separately and suppresses an old next schedule',()=>{
  const text=collectionPolicyText({...ready,metaAutoEnabled:false,enabled:false},options);
  assert.match(text,/메타 자동 수집 OFF/);assert.doesNotMatch(text,/다음 검색|설정 ON/);
  const trendOff=collectionPolicyText(ready,{...options,trendEnabled:false});
  assert.match(trendOff,/급상승 키워드 자동 수집 OFF/);assert.doesNotMatch(trendOff,/메타 자동 수집 OFF|다음 검색/);
});

test('generic failure uses guard reason while disabled request alone never implies OFF',()=>{
  assert.match(collectionPolicyText({...ready,enabled:false,collectionGuard:{state:'failure'}},options),/오류 후 대기/);
  const pending=collectionPolicyText({...ready,enabled:false},options);
  assert.match(pending,/자동 수집 요청 대기/);assert.doesNotMatch(pending,/OFF/);
});

test('old snapshots show their observed limit rather than pretending new limits already applied',()=>{
  const text=collectionPolicyText({...ready,maxDailyQueries:5,maxAdsPerQuery:20,intervalSeconds:900},options);
  assert.match(text,/15분 간격/);assert.match(text,/최대 20개/);assert.match(text,/최대 5회/);
  assert.doesNotMatch(text,/100개|288회/);
});
