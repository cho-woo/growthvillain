export function safeUrl(value) {
  if (typeof value !== 'string') return '';
  try {
    if (value.startsWith('/')) {
      const decoded = decodeURIComponent(value);
      return /^\/tools\/meta-ads\/media\/[\w./-]+$/.test(decoded) && !decoded.includes('..') ? decoded : '';
    }
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
  } catch { return ''; }
}
export function elapsedDays(card) {
  if (card.deliveryStatus === 'ended') {
    if (!card.endedAt && !(card.durationBasis === 'detected' && card.endedDetectedAt)) return null;
    if (Number.isInteger(card.durationDays) && card.durationDays >= 1) return card.durationDays;
    return calendarDays(card.startedAt, card.endedAt || card.endedDetectedAt);
  }
  return calendarDays(card.startedAt, card.statusCheckedAt || card.collectedAt);
}
function calendarDays(startValue, endValue) {
  const dateOnly = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value) ? Date.parse(value.slice(0,10)) : NaN;
  const start = dateOnly(startValue), end = dateOnly(endValue);
  return Number.isFinite(start) && Number.isFinite(end) && end >= start ? Math.floor((end-start)/86400000) + 1 : null;
}
export function deliveryLabel(card) {
  const days = elapsedDays(card);
  if (card.deliveryStatus === 'ended') return days === null ? '종료 · 기간 미확인' : `${days}일 게재 후 종료${card.durationBasis === 'detected' ? ' · 감지일 기준' : ''}`;
  if (card.deliveryStatus === 'active') return days === null ? '확인 당시 게재 중' : `${days}일째 · 확인 당시 게재 중`;
  return days === null ? '게재 상태 미확인' : `${days}일 경과 · 상태 미확인`;
}
export function filterCards(cards, filters, favorites = new Set()) {
  const q = (filters.q || '').trim().toLocaleLowerCase();
  return cards.filter(card => (!q || [card.advertiser,card.text,card.domain,card.keyword].join(' ').toLocaleLowerCase().includes(q))
    && (!filters.keyword || card.keyword === filters.keyword)
    && (!filters.advertiser || card.advertiser === filters.advertiser)
    && (!filters.domain || card.domain === filters.domain)
    && (!filters.delivery || (card.deliveryStatus || 'unknown') === filters.delivery)
    && (!filters.media || (filters.media === 'video' ? card.media.some(m=>m.type==='video') : !card.media.some(m=>m.type==='video')))
    && (!filters.favorites || favorites.has(card.id))
    && (!filters.days || (elapsedDays(card) !== null && elapsedDays(card) >= filters.days)))
    .sort((a,b) => filters.sort === 'longest' ? (elapsedDays(b) ?? -1)-(elapsedDays(a) ?? -1) :
      (Date.parse(filters.sort === 'newest' ? b.startedAt : b.collectedAt)||0)-(Date.parse(filters.sort === 'newest' ? a.startedAt : a.collectedAt)||0));
}
