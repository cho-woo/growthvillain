/** Display actual switches separately from a temporary collection guard. */
export function collectionPolicyText(policy,{trendEnabled,formatTime=value=>String(value)}={}) {
  if(!policy)return '급상승 키워드를 순서대로 수집합니다. 수집한 결과부터 소재가 연결됩니다.';
  const parts=['미수집 급상승 키워드부터 순차 검색'];
  const minutes=Number(policy.intervalSeconds)/60;
  if(Number.isFinite(minutes)&&minutes>0)parts.push(`최소 ${Math.round(minutes)}분 간격`);
  if(Number(policy.maxAdsPerQuery)>0)parts.push(`검색당 최대 ${Number(policy.maxAdsPerQuery)}개 광고`);
  if(Number(policy.maxDailyQueries)>0)parts.push(`하루 최대 ${Number(policy.maxDailyQueries)}회 검색`);
  parts.push(`오늘 ${policy.dailyUsed||0}회 진행 / ${policy.dailyRemaining??'—'}회 남음`);
  const off=policy.metaAutoEnabled===false||trendEnabled===false;
  if(policy.metaAutoEnabled===false)parts.push('메타 자동 수집 OFF');
  if(trendEnabled===false)parts.push('급상승 키워드 자동 수집 OFF');
  const guard=policy.collectionGuard||{};
  const reasons={blocked:'접근 제한 후 대기',failure:'오류 후 대기',storage:'저장 공간 확보 대기'};
  const guarded=Boolean(guard.state&&guard.state!=='ready');
  const reason=policy.pausedReason||(guarded?(guard.reason||reasons[guard.state]):null);
  const paused=Boolean(policy.pausedReason)||guarded;
  if(paused){
    if(!off&&policy.metaAutoEnabled===true&&trendEnabled===true)parts.push('자동 수집 설정 ON');
    parts.push(`현재 대기 · ${reason||'수집 조건 확인 중'}`);
  }else if(policy.enabled===false&&!off){
    parts.push('자동 수집 요청 대기');
  }
  if(!off&&guard.state!=='storage'){
    const next=policy.nextDispatchAt||guard.nextAllowedAt||guard.blockedUntil;
    if(next)parts.push(`${paused?'다음 확인':'다음 검색'} ${formatTime(next)}`);
  }
  return parts.join(' · ')+' · 같은 검색어는 24시간 중복 검색을 막습니다. 검색 결과에는 기존 광고가 포함될 수 있습니다.';
}
