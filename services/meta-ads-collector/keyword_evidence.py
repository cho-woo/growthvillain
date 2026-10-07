"""Exact collection-query links are observations, never attribution of rank growth."""
from datetime import date, datetime, timezone
import hashlib
import re

from naver_trends import normalize_keyword


def keyword_id(query):
    return hashlib.sha256(normalize_keyword(query).encode('utf-8')).hexdigest()


def _query(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
        return None
    try:
        normalize_keyword(value)
        return value.strip()
    except ValueError:
        return None


def _stamp(value):
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat(timespec='seconds')
    except ValueError:
        return None


def query_history(card):
    """Existing records fall back only to their recorded collection keyword."""
    history = card.get('queryEvidence', [])
    history = history if isinstance(history, list) else []
    records = [item for item in history if isinstance(item, dict)]
    records.append({'query': card.get('keyword'), 'firstCollectedAt': card.get('collectedAt'),
                    'lastCollectedAt': card.get('collectedAt')})
    result = {}
    for record in records:
        query = _query(record.get('query'))
        if not query:
            continue
        key = normalize_keyword(query)
        first, last = _stamp(record.get('firstCollectedAt')), _stamp(record.get('lastCollectedAt'))
        stamps = [stamp for stamp in (first, last) if stamp]
        item = result.setdefault(key, {'query': query, 'firstCollectedAt': None, 'lastCollectedAt': None})
        stamps += [stamp for stamp in (item['firstCollectedAt'], item['lastCollectedAt']) if stamp]
        if stamps:
            item.update(firstCollectedAt=min(stamps), lastCollectedAt=max(stamps))
    return [result[key] for key in sorted(result)]


def merge_query_fields(previous, current):
    history = query_history({'queryEvidence': query_history(previous) + query_history(current)})
    return {'matchedKeywords': [item['query'] for item in history], 'queryEvidence': history}


def evidence_index(cards):
    result = {}
    for card in cards:
        ad_id = str(card.get('id') or '')
        if not re.fullmatch(r'\d{5,40}', ad_id):
            continue
        for record in query_history(card):
            key = normalize_keyword(record['query'])
            result.setdefault(key, []).append({'id': ad_id, 'advertiser': str(card.get('advertiser') or '')[:180],
                'startedAt': card.get('startedAt') or None, 'query': record['query'],
                'firstCollectedAt': record['firstCollectedAt'], 'lastCollectedAt': record['lastCollectedAt']})
    return result


def ad_evidence(candidate, index):
    query = candidate['keyword']
    entries = index.get(normalize_keyword(query), [])
    ads, advertisers = [], {}
    for entry in entries:
        started = entry.get('startedAt')
        try:
            start = date.fromisoformat(started)
            previous, current = date.fromisoformat(candidate['previousDate']), date.fromisoformat(candidate['date'])
            timing = 'before-window' if start <= previous else 'after-window' if start > current else 'during-window'
        except (TypeError, ValueError):
            timing = 'unknown'
        ads.append(dict(entry, startTiming=timing))
        name = entry['advertiser']
        if name:
            advertisers[name] = advertisers.get(name, 0) + 1
    ads.sort(key=lambda item: (item['lastCollectedAt'] or '', item['id']), reverse=True)
    return {'query': query, 'matchType': 'collected-with-query', 'adCount': len(ads),
            'adIds': [item['id'] for item in ads], 'ads': ads,
            'lastCollectedAt': max((item['lastCollectedAt'] for item in ads if item['lastCollectedAt']), default=None),
            'advertisers': [{'name': name, 'adCount': count} for name, count in sorted(advertisers.items(), key=lambda item: (-item[1], item[0]))],
            'causationEstablished': False}
