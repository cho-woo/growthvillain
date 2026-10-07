"""Pure ranking comparison for complete, dated Naver Shopping Insight snapshots.

Rankings describe shopping keywords, not sales or Meta ad performance. A brand is
identified only through the caller's confirmed brand names and aliases. ``isNew``
means new within the compared ranking window, never a new business or product.
"""
from __future__ import annotations

from datetime import date as calendar_date
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit


def _integer(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f'{label}: {minimum}–{maximum} 범위의 정수가 필요합니다.')
    return value


def _text(value, label, maximum=200):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(unicodedata.category(c).startswith('C') for c in value)):
        raise ValueError(f'{label} 값이 올바르지 않습니다.')
    return value.strip()


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('순위 날짜는 YYYY-MM-DD 형식이어야 합니다.')
    try:
        return calendar_date.fromisoformat(value)
    except ValueError as error:
        raise ValueError('존재하지 않는 순위 날짜입니다.') from error


def normalize_keyword(value):
    """Compare Korean/Latin aliases independent of case and spacing."""
    value = _text(value, '검색어')
    return ''.join(unicodedata.normalize('NFKC', value).casefold().split())


def validate_snapshot(snapshot, *, expected_count=100):
    """Return a canonical complete snapshot or fail; never accept partial data.

    Contract: ``{category, date, sourceUrl, entries: [{rank, keyword}]}``.
    Ranks must cover 1..expected_count exactly once. Extra source metadata is not
    retained. The caller must obtain and verify the source's selected date and
    category before constructing this record.
    """
    expected_count = _integer(expected_count, 1, 500, '순위 개수')
    if not isinstance(snapshot, dict):
        raise ValueError('순위 스냅샷은 객체여야 합니다.')
    category = _text(snapshot.get('category'), '카테고리', 100)
    day = _date(snapshot.get('date')).isoformat()
    source = _text(snapshot.get('sourceUrl'), '출처 URL', 2048)
    try:
        url = urlsplit(source)
        valid_url = (url.scheme == 'https' and url.hostname == 'datalab.naver.com'
                     and url.port in (None, 443) and not url.username and not url.password)
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ValueError('네이버 데이터랩의 HTTPS 출처 URL이 필요합니다.')
    entries = snapshot.get('entries')
    if not isinstance(entries, list) or len(entries) != expected_count:
        raise ValueError(f'순위가 불완전합니다. {expected_count}개 전체가 필요합니다.')
    clean, ranks, keywords = [], set(), set()
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError('순위 항목은 객체여야 합니다.')
        rank = _integer(row.get('rank'), 1, 500, '순위')
        keyword = _text(row.get('keyword'), '검색어')
        normalized = normalize_keyword(keyword)
        if rank in ranks or normalized in keywords:
            raise ValueError('중복 순위 또는 중복 검색어가 있습니다.')
        ranks.add(rank)
        keywords.add(normalized)
        clean.append({'rank': rank, 'keyword': keyword})
    if ranks != set(range(1, expected_count + 1)):
        raise ValueError('순위가 누락되었거나 범위를 벗어났습니다.')
    return {'category': category, 'date': day, 'sourceUrl': source,
            'entries': sorted(clean, key=lambda row: row['rank'])}


def validate_brands(brands):
    """Normalize confirmed ``[{id, name, aliases: [...]}]`` without guessing.

    The name itself is always an alias. An alias assigned to two brands is an
    error rather than permission to select one arbitrarily.
    """
    if not isinstance(brands, (list, tuple)) or len(brands) > 500:
        raise ValueError('확정 브랜드 목록은 500개 이하의 배열이어야 합니다.')
    result, ids, alias_owners = [], set(), {}
    for brand in brands:
        if not isinstance(brand, dict):
            raise ValueError('브랜드 항목은 객체여야 합니다.')
        brand_id = _text(brand.get('id'), '브랜드 ID', 100)
        name = _text(brand.get('name'), '브랜드명', 100)
        if brand_id in ids:
            raise ValueError('중복 브랜드 ID가 있습니다.')
        ids.add(brand_id)
        supplied_aliases = brand.get('aliases', [])
        if not isinstance(supplied_aliases, list) or len(supplied_aliases) > 30:
            raise ValueError('브랜드 별칭은 30개 이하의 배열이어야 합니다.')
        aliases, seen = [], set()
        for alias in [name, *supplied_aliases]:
            alias = _text(alias, '브랜드 별칭', 100)
            normalized = normalize_keyword(alias)
            owner = alias_owners.get(normalized)
            if owner is not None and owner != brand_id:
                raise ValueError('같은 별칭을 여러 브랜드에 지정할 수 없습니다.')
            alias_owners[normalized] = brand_id
            if normalized not in seen:
                seen.add(normalized)
                aliases.append(alias)
        result.append({'id': brand_id, 'name': name, 'aliases': aliases})
    return result


def _brand_match(keyword, brands):
    key = normalize_keyword(keyword)
    matches = []
    for brand in brands:
        lengths = [len(alias_key) for alias in brand['aliases']
                   if key.startswith(alias_key := normalize_keyword(alias))]
        if lengths:
            matches.append((max(lengths), brand))
    if not matches:
        return None
    # Equal-length collisions are excluded by validate_brands.
    return max(matches, key=lambda item: item[0])[1]


def match_brand(keyword, brands):
    """Return the longest confirmed leading alias match, or None."""
    return _brand_match(keyword, validate_brands(brands))


def dispatch_key(category, day, brand_id):
    """Stable idempotency key for one brand in one category/date snapshot."""
    values = [_text(category, '카테고리', 100), _date(day).isoformat(),
              _text(brand_id, '브랜드 ID', 100)]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def compare_snapshots(current, previous, brands=(), *, minimum_rise=10,
                      new_top=20, expected_count=100, lookback_days=7):
    """Return rising keyword candidates with optional confirmed brand identity.

    A candidate rises >= minimum_rise, or newly enters the compared window at
    rank <= new_top. With no valid baseline, fail instead of labeling everything
    new. Missing previous rank/delta remains None. Known brands deduplicate to
    their strongest measured rise, then best current rank; measured changes
    precede unquantifiable new entries. Unknown keywords remain separate for
    review and never receive a dispatch key.
    """
    minimum_rise = _integer(minimum_rise, 1, 499, '급상승 기준')
    new_top = _integer(new_top, 1, 500, '신규 진입 기준')
    lookback_days = _integer(lookback_days, 1, 366, '비교 간격')
    current = validate_snapshot(current, expected_count=expected_count)
    previous = validate_snapshot(previous, expected_count=expected_count)
    brands = validate_brands(brands)
    if current['category'] != previous['category']:
        raise ValueError('같은 카테고리의 순위만 비교할 수 있습니다.')
    if (_date(current['date']) - _date(previous['date'])).days != lookback_days:
        raise ValueError(f'비교 순위는 정확히 {lookback_days}일 전 자료여야 합니다.')
    previous_ranks = {normalize_keyword(row['keyword']): row['rank'] for row in previous['entries']}
    candidates = []
    for row in current['entries']:
        prior_rank = previous_ranks.get(normalize_keyword(row['keyword']))
        is_new = prior_rank is None
        rise = None if is_new else prior_rank - row['rank']
        if not ((is_new and row['rank'] <= new_top) or (rise is not None and rise >= minimum_rise)):
            continue
        brand = _brand_match(row['keyword'], brands)
        candidates.append({
            'category': current['category'], 'date': current['date'],
            'currentDate': current['date'], 'periodDays': lookback_days,
            'rankWindow': expected_count,
            'previousDate': previous['date'], 'sourceUrl': current['sourceUrl'],
            'keyword': row['keyword'], 'currentRank': row['rank'],
            'previousRank': prior_rank, 'rankRise': rise, 'isNew': is_new,
            'brandId': brand['id'] if brand else None,
            'brandName': brand['name'] if brand else None,
            'needsReview': brand is None,
            'dispatchKey': dispatch_key(current['category'], current['date'], brand['id']) if brand else None,
        })
    candidates.sort(key=lambda item: (item['rankRise'] is None,
                                     -(item['rankRise'] or 0), item['currentRank'],
                                     normalize_keyword(item['keyword'])))
    result, seen_brands = [], set()
    for candidate in candidates:
        brand_id = candidate['brandId']
        if brand_id is not None:
            if brand_id in seen_brands:
                continue
            seen_brands.add(brand_id)
        result.append(candidate)
    return result
