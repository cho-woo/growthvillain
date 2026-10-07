export function periodDays(row) {
  const first = Date.parse(row.previousDate), last = Date.parse(row.currentDate || row.date);
  if (Number.isFinite(first) && Number.isFinite(last) && last > first) return Math.round((last-first)/86400000);
  return Number.isInteger(row.periodDays) && row.periodDays > 0 ? row.periodDays : null;
}
export function rankChange(row) {
  const rank = Number(row.currentRank), previous = Number(row.previousRank);
  if (!Number.isInteger(rank) || rank < 1) return '순위 미확인';
  const window = Number.isInteger(row.rankWindow) ? row.rankWindow : 100;
  return row.isNew || row.previousRank == null ? `${window}위 밖 → ${rank}위` : `${previous}위 → ${rank}위`;
}
export function countdown(value, now = Date.now()) {
  const at = Date.parse(value);
  if (!Number.isFinite(at)) return '일정 없음';
  const seconds = Math.ceil((at - now)/1000);
  if (seconds <= 0) return '예정 시각 지남 · 상태 갱신 대기';
  const days = Math.floor(seconds/86400), hours = Math.floor(seconds%86400/3600), minutes = Math.floor(seconds%3600/60);
  return days ? `${days}일 ${hours}시간 후` : hours ? `${hours}시간 ${minutes}분 후` : minutes ? `${minutes}분 ${seconds%60}초 후` : `${seconds}초 후`;
}
export function snapshotFreshness(value, now = Date.now()) {
  const at = Date.parse(value);
  if (!Number.isFinite(at)) return {stale:true,label:'갱신 시각 미확인'};
  const minutes = Math.max(0,Math.floor((now-at)/60000));
  return {stale:minutes > 10, label:minutes < 1 ? '1분 이내 게시' : minutes < 60 ? `${minutes}분 전 게시` : minutes < 1440 ? `${Math.floor(minutes/60)}시간 전 게시` : `${Math.floor(minutes/1440)}일 전 게시`};
}
