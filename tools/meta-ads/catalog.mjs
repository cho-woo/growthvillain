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
  const start = Date.parse(card.startedAt), end = Date.parse(card.collectedAt);
  return Number.isFinite(start) && Number.isFinite(end) && end >= start ? Math.floor((end-start)/86400000) : null;
}
export function filterCards(cards, filters, favorites = new Set()) {
  const q = (filters.q || '').trim().toLocaleLowerCase();
  return cards.filter(card => (!q || [card.advertiser,card.text,card.domain,card.keyword].join(' ').toLocaleLowerCase().includes(q))
    && (!filters.keyword || card.keyword === filters.keyword)
    && (!filters.advertiser || card.advertiser === filters.advertiser)
    && (!filters.domain || card.domain === filters.domain)
    && (!filters.media || (filters.media === 'video' ? card.media.some(m=>m.type==='video') : !card.media.some(m=>m.type==='video')))
    && (!filters.favorites || favorites.has(card.id))
    && (!filters.days || (elapsedDays(card) !== null && elapsedDays(card) >= filters.days)))
    .sort((a,b) => filters.sort === 'longest' ? (elapsedDays(b) ?? -1)-(elapsedDays(a) ?? -1) :
      (Date.parse(filters.sort === 'newest' ? b.startedAt : b.collectedAt)||0)-(Date.parse(filters.sort === 'newest' ? a.startedAt : a.collectedAt)||0));
}
