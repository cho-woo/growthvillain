"""Naver rising keywords, bounded exact-query ad collection and observed links."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time

from catalog import now
from naver_trends import compare_snapshots, normalize_keyword, validate_brands, match_brand, keyword_dispatch_key, dispatch_key as brand_dispatch_key
from keyword_evidence import keyword_id, evidence_index, ad_evidence
from storage_config import assert_storage_available

SOURCE_URL = 'https://datalab.naver.com/shoppingInsight/sCategory.naver'
DEFAULTS = {'category': '50000023', 'categories': ['50000023', '50000024'], 'minimumRise': 10, 'newTop': 20}
CATEGORIES = {'50000000', '50000001', '50000002', '50000003', '50000004',
              '50000005', '50000006', '50000007', '50000008', '50000009', '50000010', '50005542',
              '50000023', '50001899', '50001090', '50001092', '50017220', '50018919', '50000024'}
CATEGORY_NAMES = {'50000023': '건강식품', '50000024': '다이어트식품', '50001092': '영양제'}
KST = timezone(timedelta(hours=9))
INTERVAL_SECONDS = 3600
COMPARISON_DAYS = 7
DAILY_QUERY_LIMIT = 288
ADS_PER_QUERY = 100
DISPATCH_INTERVAL_SECONDS = 300
BACKLOG_DAYS = 14
MAX_SOURCE_AGE_DAYS = 3
PUBLIC_EVENT_FIELDS = ('id', 'category', 'date', 'currentDate', 'previousDate',
                       'sourceUrl', 'keyword', 'currentRank', 'previousRank', 'rankRise',
                       'isNew', 'brandId', 'brandName', 'needsReview', 'periodDays',
                       'rankWindow', 'observedAt', 'lastObservedAt', 'state',
                       'keywordId', 'searchQuery', 'adEvidence', 'sourceAgeDays', 'collectionReason')


def _integer(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f'{label}: {low}–{high} 범위의 정수가 필요합니다.')
    return value


def _text(value, label='브랜드명'):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100 or any(ord(c) < 32 for c in value):
        raise ValueError(f'{label}은 1–100자로 입력하세요.')
    return value.strip()


def _key(value):
    return normalize_keyword(value)


def _categories(value):
    if (not isinstance(value, list) or not 1 <= len(value) <= 2
            or any(not isinstance(item, str) or item not in CATEGORIES for item in value)
            or len(set(value)) != len(value)):
        raise ValueError('지원되는 네이버 쇼핑 카테고리를 중복 없이 1~2개 선택하세요.')
    return list(value)


def validate_recent_source_date(value, current=None):
    """The public source may lag; never relabel its date as yesterday."""
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('invalid source date')
    source_day = datetime.fromisoformat(value).date()
    today = (current or datetime.now(KST)).astimezone(KST).date()
    if not 1 <= (today-source_day).days <= MAX_SOURCE_AGE_DAYS:
        raise ValueError('source date is not a recent completed day')
    return source_day


class SourceDateRegression(ValueError):
    """A completed older day cannot replace the latest confirmed snapshot."""


class TrendService:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.auto_enabled = False
        self.scanning = False
        self.error = None
        self.thread = None
        self.process = None
        self.stop_event = threading.Event()
        self.next_attempt = 0
        self.last_attempt_at = None
        self.last_success_at = None
        self.last_error = None
        self.source_errors = {}
        assert_storage_available(store.root)
        with store.lock:
            store.db.executescript('''
                CREATE TABLE IF NOT EXISTS trend_settings (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trend_snapshots (category TEXT NOT NULL, date TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(category,date));
                CREATE TABLE IF NOT EXISTS trend_scans (category TEXT PRIMARY KEY, current_date TEXT NOT NULL,
                    previous_date TEXT NOT NULL, checked_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trend_brands (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trend_ignored (keyword TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS trend_dispatches (dispatch_key TEXT PRIMARY KEY, brand_id TEXT NOT NULL,
                    job_id TEXT NOT NULL, queued_at REAL NOT NULL, automatic INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS trend_runtime (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS trend_events (id TEXT PRIMARY KEY, category TEXT NOT NULL,
                    current_date TEXT NOT NULL, observed_at TEXT NOT NULL, last_observed_at TEXT NOT NULL,
                    payload TEXT NOT NULL);
            ''')
            store.db.execute('INSERT OR IGNORE INTO trend_settings(id,payload) VALUES(1,?)', (json.dumps(DEFAULTS),))
            # Keep old brand dispatch history (including quota use), while new
            # dispatches identify the actual query independently of a brand.
            columns = {row['name'] for row in store.db.execute('PRAGMA table_info(trend_dispatches)')}
            for name, definition in (('keyword', "TEXT NOT NULL DEFAULT ''"),
                                     ('keyword_key', "TEXT NOT NULL DEFAULT ''"),
                                     ('kind', "TEXT NOT NULL DEFAULT 'brand'")):
                if name not in columns:
                    store.db.execute(f'ALTER TABLE trend_dispatches ADD COLUMN {name} {definition}')
            for row in store.db.execute("SELECT d.dispatch_key,j.keyword FROM trend_dispatches d JOIN jobs j ON j.id=d.job_id WHERE d.keyword_key='' ").fetchall():
                try:
                    key = _key(row['keyword'])
                except ValueError:
                    continue
                store.db.execute('UPDATE trend_dispatches SET keyword=?,keyword_key=? WHERE dispatch_key=?',
                                 (row['keyword'], key, row['dispatch_key']))
            store.db.commit()
        saved = store.rows('SELECT payload FROM trend_runtime WHERE id=1')
        if saved:
            runtime = json.loads(saved[0]['payload'])
            self.auto_enabled = runtime.get('autoEnabled') is True
            self.next_attempt = runtime.get('nextAttempt', 0)
            self.last_attempt_at = runtime.get('lastAttemptAt')
            self.last_success_at = runtime.get('lastSuccessAt')
            self.last_error = runtime.get('lastError')
            errors = runtime.get('sourceErrors')
            if isinstance(errors, dict):
                self.source_errors = {key: value for key, value in errors.items()
                                      if key in CATEGORIES and isinstance(value, dict)
                                      and isinstance(value.get('message'), str)}
            elif isinstance(self.last_error, dict):
                # A legacy single-category error still belongs to its original
                # category; it must not contaminate a newly selected category.
                self.source_errors[self.settings()['category']] = self.last_error
            self._refresh_error()

    def _persist_runtime(self):
        payload = {'autoEnabled': self.auto_enabled, 'nextAttempt': self.next_attempt,
                   'lastAttemptAt': self.last_attempt_at, 'lastSuccessAt': self.last_success_at,
                   'lastError': self.last_error, 'sourceErrors': self.source_errors}
        self.store.write('INSERT INTO trend_runtime(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                         (json.dumps(payload, ensure_ascii=False),))

    def settings(self):
        stored = json.loads(self.store.rows('SELECT payload FROM trend_settings WHERE id=1')[0]['payload'])
        categories = _categories(stored.get('categories', [stored['category']]))
        return dict(stored, category=categories[0], categories=categories)

    def _refresh_error(self):
        issues = [(category, self.source_errors[category]) for category in self.settings()['categories']
                  if category in self.source_errors]
        if not issues:
            self.error, self.last_error = None, None
            return
        names = ', '.join(CATEGORY_NAMES.get(category, category) for category, _ in issues)
        self.error = names+' 순위를 확인하지 못했습니다. 해당 분야의 이전 확인 결과는 유지됩니다.'
        self.last_error = {'at': max((str(value.get('at') or '') for _, value in issues), default='') or None,
                           'message': self.error, 'categories': [category for category, _ in issues]}

    def source_summaries(self):
        result = []
        for category in self.settings()['categories']:
            current, previous, checked_at = self._snapshots(category)
            result.append({'category': category, 'categoryName': CATEGORY_NAMES.get(category, category),
                           'sourceDate': current['date'] if current else None,
                           'previousSourceDate': previous['date'] if previous else None,
                           'lastChecked': checked_at,
                           'error': (self.source_errors.get(category) or {}).get('message')})
        return result

    def brands(self):
        return [dict(json.loads(row['payload']), id=row['id'])
                for row in self.store.rows('SELECT * FROM trend_brands ORDER BY rowid')]

    def _snapshots(self, category):
        scans = self.store.rows('SELECT * FROM trend_scans WHERE category=?', (category,))
        if not scans:
            return None, None, None
        scan = scans[0]
        snapshots = self.store.rows('SELECT date,payload FROM trend_snapshots WHERE category=? AND date IN (?,?)',
                                    (category, scan['current_date'], scan['previous_date']))
        by_date = {row['date']: json.loads(row['payload']) for row in snapshots}
        return by_date.get(scan['current_date']), by_date.get(scan['previous_date']), scan['checked_at']

    def candidates(self, evidence=None):
        settings = self.settings()
        candidates = []
        brands = self.brands()
        for category in settings['categories']:
            current, previous, _ = self._snapshots(category)
            if current is not None and previous is not None:
                candidates.extend(compare_snapshots(current, previous, brands=brands,
                    minimum_rise=settings['minimumRise'], new_top=settings['newTop'], keyword_mode=True))
        return self._decorate_candidates(candidates, evidence)

    def _decorate_candidates(self, candidates, evidence=None):
        ignored = {row['keyword'] for row in self.store.rows('SELECT keyword FROM trend_ignored')}
        dispatches = {r['dispatch_key']: r for r in self.store.rows('SELECT * FROM trend_dispatches')}
        last_by_keyword = {}
        for row in dispatches.values():
            key = row['keyword_key']
            last_by_keyword[key] = max(last_by_keyword.get(key, 0), row['queued_at'])
        jobs = {r['id']: r['status'] for r in self.store.rows('SELECT id,status FROM jobs')}
        evidence = evidence if evidence is not None else evidence_index(self.store.cards())
        result = []
        for raw in candidates:
            if _key(raw['keyword']) in ignored:
                continue
            age = (datetime.now(KST).date() - datetime.fromisoformat(raw['date']).date()).days
            item = dict(raw, state='ready' if age == 1 else 'backlog', needsReview=False,
                        sourceAgeDays=age, collectionReason='current' if age == 1 else 'historical-backlog',
                        keywordId=keyword_id(raw['keyword']), searchQuery=raw['keyword'],
                        dispatchKey=keyword_dispatch_key(raw['category'], raw['date'], raw['keyword']))
            item['adEvidence'] = ad_evidence(item, evidence)
            dispatched = dispatches.get(item.get('dispatchKey'))
            if not dispatched and item.get('brandId'):
                legacy = dispatches.get(brand_dispatch_key(item['category'], item['date'], item['brandId']))
                if legacy and legacy['keyword_key'] == _key(item['keyword']):
                    dispatched = legacy
                    # Keep a usable idempotency key for a legacy exact-query job.
                    item['dispatchKey'] = legacy['dispatch_key']
            if dispatched:
                job_status = jobs.get(dispatched['job_id'], 'unknown')
                state = 'done' if job_status == 'done' else 'failed' if job_status in ('failed', 'canceled', 'unknown') else 'queued'
                item.update(state=state, jobId=dispatched['job_id'], jobStatus=job_status)
            elif time.time() - last_by_keyword.get(_key(item['keyword']), 0) < 24 * 3600:
                item['state'] = 'cooldown'
            elif not 1 <= age <= BACKLOG_DAYS:
                item['state'] = 'stale'
            result.append(item)
        return result

    def status(self):
        settings = self.settings()
        summaries = self.source_summaries()
        # Keep the single-source fields as first-category compatibility fields;
        # clients rendering both categories use sourceSummaries instead.
        first_source = summaries[0]
        checked_times = [item['lastChecked'] for item in summaries if item['lastChecked']]
        checked_at = max(checked_times, key=lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))) if checked_times else None
        self._refresh_error()
        next_run = (datetime.fromtimestamp(self.next_attempt, timezone.utc).isoformat(timespec='seconds')
                    if self.next_attempt else now()) if self.auto_enabled and not self.stop_event.is_set() else None
        evidence = evidence_index(self.store.cards())
        return {'version': 1, 'updatedAt': now(), 'settings': settings, 'autoEnabled': self.auto_enabled, 'scanning': self.scanning,
                'lastChecked': checked_at, 'error': self.error, 'candidates': self.candidates(evidence),
                'brands': self.brands(), 'sourceUrl': SOURCE_URL, 'history': self.history(evidence=evidence),
                'nextRunAt': next_run, 'intervalSeconds': INTERVAL_SECONDS,
                'sourceCadence': 'daily', 'comparisonDays': COMPARISON_DAYS,
                'sourceDate': first_source['sourceDate'], 'previousSourceDate': first_source['previousSourceDate'],
                'sourceSummaries': summaries,
                'lastAttemptAt': self.last_attempt_at, 'lastSuccessAt': checked_at,
                'lastError': self.last_error, 'collectionPolicy': self.collection_policy()}

    def collection_policy(self):
        midnight = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
        used = self.store.rows('SELECT COUNT(*) AS n FROM trend_dispatches WHERE automatic=1 AND queued_at>=?', (midnight.timestamp(),))[0]['n']
        pending = self.store.rows("SELECT COUNT(*) AS n FROM trend_dispatches d JOIN jobs j ON j.id=d.job_id WHERE j.status IN ('queued','running')")[0]['n']
        last = self.store.rows('SELECT MAX(queued_at) AS t FROM trend_dispatches WHERE automatic=1')[0]['t'] or 0
        meta_enabled = bool(getattr(self, 'can_collect', lambda: True)())
        guard = getattr(self, 'collection_guard', lambda: {'state': 'ready', 'storageReady': True})()
        ready = guard['state'] == 'ready'
        next_at = None
        if self.auto_enabled and meta_enabled and guard['storageReady'] and not self.stop_event.is_set() and not pending:
            due = max(time.time(), last + DISPATCH_INTERVAL_SECONDS)
            if guard.get('nextAllowedAt'):
                due = max(due, datetime.fromisoformat(guard['nextAllowedAt']).timestamp())
            if used >= DAILY_QUERY_LIMIT:
                due = max(due, (midnight + timedelta(days=1)).timestamp())
            next_at = datetime.fromtimestamp(due, timezone.utc).isoformat(timespec='seconds')
        return {'maxDailyQueries': DAILY_QUERY_LIMIT, 'maxAdsPerQuery': ADS_PER_QUERY, 'maxPending': 1,
                'intervalSeconds': DISPATCH_INTERVAL_SECONDS, 'keywordCooldownSeconds': 86400,
                'priority': 'uncollected-first-oldest-first', 'backlogDays': BACKLOG_DAYS,
                'dailyUsed': used, 'dailyRemaining': max(0, DAILY_QUERY_LIMIT-used),
                'pending': pending, 'nextDispatchAt': next_at, 'metaAutoEnabled': meta_enabled,
                'enabled': self.auto_enabled and meta_enabled and ready,
                'collectionGuard': guard, 'pausedReason': guard.get('reason')}

    def history(self, limit=2000, evidence=None, *, since_date=None):
        """Selected-category observations; other categories stay in the database."""
        brands = self.brands()
        categories = self.settings()['categories']
        ignored = {row['keyword'] for row in self.store.rows('SELECT keyword FROM trend_ignored')}
        result = []
        # Filter before LIMIT so newer records in another category cannot crowd
        # this category's history out of the dashboard or dispatch backlog.
        placeholders = ','.join('?' for _ in categories)
        query = f'SELECT * FROM trend_events WHERE category IN ({placeholders})'
        parameters = list(categories)
        if since_date is not None:
            query += ' AND trend_events.current_date>=?'
            parameters.append(since_date)
        query += ' ORDER BY trend_events.current_date DESC, observed_at DESC, id'
        if limit is not None:
            query += ' LIMIT ?'
            parameters.append(limit)
        for row in self.store.rows(query, parameters):
            item = json.loads(row['payload'])
            if item.get('category') not in categories or _key(item['keyword']) in ignored:
                continue
            brand = match_brand(item['keyword'], brands)
            item.update(id=row['id'], observedAt=row['observed_at'], lastObservedAt=row['last_observed_at'],
                        brandId=brand['id'] if brand else None, brandName=brand['name'] if brand else None,
                        needsReview=False, keywordId=keyword_id(item['keyword']), searchQuery=item['keyword'])
            result.append(item)
        return self._decorate_candidates(result, evidence)

    def _backlog_history(self, evidence=None):
        # The UI cap must not truncate two categories' full 14-day queue.
        cutoff = (datetime.now(KST).date() - timedelta(days=BACKLOG_DAYS)).isoformat()
        return self.history(limit=None, evidence=evidence, since_date=cutoff)

    def collection_candidates(self, *, all_categories=False):
        """A dated backlog keeps older uncollected rises eligible."""
        evidence = evidence_index(self.store.cards())
        combined = self.candidates(evidence) + self._backlog_history(evidence)
        latest = {}
        settings = self.settings()
        categories = settings['categories']
        for item in combined:
            if not all_categories and item['category'] not in categories:
                continue
            if not 1 <= item['sourceAgeDays'] <= BACKLOG_DAYS:
                continue
            if not ((item['isNew'] and item['currentRank'] <= settings['newTop']) or
                    (item['rankRise'] is not None and item['rankRise'] >= settings['minimumRise'])):
                continue
            key = _key(item['keyword'])
            if key not in latest or item['date'] > latest[key]['date']:
                latest[key] = item
        last_attempt = {}
        for row in self.store.rows('SELECT keyword_key,queued_at FROM trend_dispatches'):
            last_attempt[row['keyword_key']] = max(last_attempt.get(row['keyword_key'], 0), row['queued_at'])
        def priority(item):
            last_collected = item['adEvidence']['lastCollectedAt']
            last_collected = datetime.fromisoformat(last_collected).timestamp() if last_collected else 0
            last_activity = max(last_collected, last_attempt.get(_key(item['keyword']), 0))
            if not last_activity:
                last_activity = datetime.fromisoformat(item['date']).replace(tzinfo=KST).timestamp()
            return (item['adEvidence']['adCount'] > 0, last_activity, item['rankRise'] is None,
                    -(item['rankRise'] or 0), item['currentRank'], _key(item['keyword']))
        return sorted(latest.values(), key=priority)

    def export(self):
        """Export public rank evidence only; no queue IDs, local paths or raw logs."""
        with self.lock:
            assert_storage_available(self.store.root)
            status = self.status()
            public = {key: status[key] for key in ('version', 'updatedAt', 'autoEnabled', 'scanning',
                      'lastChecked', 'error', 'sourceUrl', 'nextRunAt', 'intervalSeconds', 'sourceCadence',
                      'comparisonDays', 'sourceDate', 'previousSourceDate', 'sourceSummaries', 'lastAttemptAt', 'lastSuccessAt', 'lastError', 'collectionPolicy')}
            public['settings'] = dict(status['settings'])
            public['mode'] = 'public'
            for key in ('candidates', 'history'):
                public[key] = [{name: item[name] for name in PUBLIC_EVENT_FIELDS if name in item}
                               for item in status[key]]
            public['brands'] = [{'id': item['id'], 'name': item['name']} for item in status['brands']]
            target = self.store.web_root / 'tools' / 'meta-ads' / 'data' / 'trends.json'
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix('.json.tmp')
            temporary.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temporary, target)
            return public

    def save_settings(self, body):
        with self.lock:
            settings = self.settings()
            categories = _categories(body['categories'] if 'categories' in body else
                                     [body['category']] if 'category' in body else settings['categories'])
            if 'categories' in body and 'category' in body and body['category'] != categories[0]:
                raise ValueError('category는 categories의 첫 번째 항목과 같아야 합니다.')
            updated = {'category': categories[0], 'categories': categories,
                       'minimumRise': _integer(body.get('minimumRise', settings['minimumRise']), 1, 99, '상승 순위'),
                       'newTop': _integer(body.get('newTop', settings['newTop']), 1, 100, '신규 진입 순위')}
            if 'autoEnabled' in body and not isinstance(body['autoEnabled'], bool):
                raise ValueError('자동 수집 여부는 true 또는 false여야 합니다.')
            if self.scanning and updated != settings:
                raise ValueError('순위 확인이 끝난 뒤 기준을 변경하세요.')
            self.store.write('UPDATE trend_settings SET payload=? WHERE id=1', (json.dumps(updated),))
            if 'autoEnabled' in body:
                changed = self.auto_enabled != body['autoEnabled']
                self.auto_enabled = body['autoEnabled']
                if self.auto_enabled and changed:
                    self.next_attempt = 0
            if self.auto_enabled and categories != settings['categories']:
                self.next_attempt = 0
            self._refresh_error()
            self._persist_runtime()
            self.export()
            return self.status()

    def save_brand(self, body):
        name = _text(body.get('name'))
        aliases = body.get('aliases', [])
        if not isinstance(aliases, list) or len(aliases) > 20:
            raise ValueError('브랜드 검색어는 최대 20개까지 입력하세요.')
        aliases = list(dict.fromkeys([name] + [_text(alias, '검색어') for alias in aliases]))
        domain = str(body.get('domain') or '').strip().lower().removeprefix('www.')
        if domain and not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
            raise ValueError('공식 도메인은 example.com 형식으로 입력하세요.')
        with self.lock, self.store.lock:
            assert_storage_available(self.store.root)
            existing = self.brands()
            match = next((b for b in existing if _key(b['name']) == _key(name)), None)
            if not match and len(existing) >= 100:
                raise ValueError('확인한 브랜드는 최대 100개입니다.')
            if match:
                aliases = list(dict.fromkeys(match['aliases'] + aliases))
                if len(aliases) > 21:
                    raise ValueError('브랜드 검색어는 최대 20개까지 입력하세요.')
                if 'domain' not in body:
                    domain = match.get('domain', '')
            alias_keys = {_key(alias) for alias in aliases}
            for brand in existing:
                if match and match['id'] == brand['id']:
                    continue
                if alias_keys & {_key(alias) for alias in brand['aliases']}:
                    raise ValueError('다른 브랜드에 등록된 검색어입니다.')
            brand_id = match['id'] if match else secrets.token_hex(8)
            competitor_id = match['competitorId'] if match else secrets.token_hex(8)
            competitor_exists = self.store.rows('SELECT id FROM competitors WHERE id=?', (competitor_id,))
            if not competitor_exists and len(self.store.competitors()) >= 100:
                raise ValueError('수집 대상은 최대 100개입니다.')
            payload = {'name': name, 'aliases': aliases, 'domain': domain, 'competitorId': competitor_id}
            validate_brands([b for b in existing if b['id'] != brand_id] + [dict(payload, id=brand_id)])
            competitor = {'name': name, 'keyword': name, 'domain': domain, 'intervalHours': 24, 'trendOnly': True}
            self.store.db.execute('INSERT INTO trend_brands(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                                  (brand_id, json.dumps(payload, ensure_ascii=False)))
            self.store.db.execute('INSERT INTO competitors(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                                  (competitor_id, json.dumps(competitor, ensure_ascii=False)))
            for alias in aliases:
                self.store.db.execute('DELETE FROM trend_ignored WHERE keyword=?', (_key(alias),))
            self.store.db.commit()
            if self.auto_enabled:
                self.next_attempt = 0
                self._persist_runtime()
            self.export()
            return dict(payload, id=brand_id)

    def ignore(self, keyword):
        self.store.write('INSERT OR IGNORE INTO trend_ignored(keyword) VALUES(?)', (_key(_text(keyword, '검색어')),))
        self.export()

    def _job(self, job_id):
        rows = self.store.rows('SELECT * FROM jobs WHERE id=?', (job_id,))
        if not rows:
            return None
        row = rows[0]
        return {'id': row['id'], 'competitorId': row['competitor_id'], 'name': row['name'], 'keyword': row['keyword'],
                'domain': row['domain'], 'limit': row['max_ads'], 'status': row['status'], 'requestedAt': row['requested_at'],
                'startedAt': row['started_at'], 'finishedAt': row['finished_at'], 'message': row['message'], 'imported': row['imported']}

    def collect(self, dispatch_key, limit=20, *, automatic=False):
        limit = _integer(limit, 1, ADS_PER_QUERY, '키워드별 수집 수')
        if not isinstance(dispatch_key, str) or not 1 <= len(dispatch_key) <= 500:
            raise ValueError('수집할 급상승 키워드를 선택하세요.')
        # The queue row and its idempotency record are committed together, under the
        # same lock used by the regular collector. A full queue never consumes a key.
        with self.lock, self.store.lock:
            assert_storage_available(self.store.root)
            categories = self.settings()['categories']
            candidate = next((c for c in self.candidates() + self._backlog_history() if c.get('dispatchKey') == dispatch_key), None)
            guard = getattr(self, 'collection_guard', lambda: {'state': 'ready'})()
            if guard['state'] != 'ready':
                raise ValueError(guard.get('reason') or '광고 수집 대기 중입니다.')
            if automatic and not getattr(self, 'can_collect', lambda: True)():
                raise ValueError('메타 광고 자동 수집이 OFF입니다.')
            if not candidate or candidate.get('category') not in categories:
                raise ValueError('현재 선택된 카테고리의 급상승 목록에서 키워드를 선택하세요.')
            existing = self.store.rows('SELECT job_id,automatic FROM trend_dispatches WHERE dispatch_key=?', (dispatch_key,))
            if existing:
                job = self._job(existing[0]['job_id'])
                if job and job['status'] not in ('failed', 'canceled'):
                    return job
                if automatic:
                    raise ValueError('실패한 작업은 확인 후 직접 다시 수집하세요.')
            age = (datetime.now(KST).date() - datetime.fromisoformat(candidate['date']).date()).days
            if not 1 <= age <= BACKLOG_DAYS:
                raise ValueError('오래된 순위입니다. 네이버 순위를 다시 확인하세요.')
            query = candidate['keyword']
            query_key = _key(query)
            target_id = 'keyword-' + keyword_id(query)
            recent = self.store.rows('SELECT queued_at FROM trend_dispatches WHERE keyword_key=? AND dispatch_key!=? ORDER BY queued_at DESC LIMIT 1', (query_key, dispatch_key))
            if recent and time.time() - recent[0]['queued_at'] < 24 * 3600:
                raise ValueError('같은 키워드는 24시간에 한 번 수집합니다.')
            busy = self.store.rows("SELECT competitor_id,keyword FROM jobs WHERE status IN ('queued','running')")
            if any(row['competitor_id'] == target_id or _key(row['keyword']) == query_key for row in busy):
                raise ValueError('이 키워드는 이미 수집 대기 중이거나 실행 중입니다.')
            if len(busy) >= 20:
                raise ValueError('대기 중인 작업은 최대 20개입니다.')
            if automatic:
                policy = self.collection_policy()
                if not self.auto_enabled or policy['dailyRemaining'] <= 0 or policy['pending']:
                    raise ValueError('자동 키워드 수집 한도 또는 실행 중인 작업을 확인하세요.')
                last = self.store.rows('SELECT MAX(queued_at) AS t FROM trend_dispatches WHERE automatic=1')[0]['t'] or 0
                if time.time() - last < DISPATCH_INTERVAL_SECONDS:
                    raise ValueError('자동 키워드 수집은 최소 5분 간격으로 실행합니다.')
            job_id = secrets.token_hex(12)
            try:
                self.store.db.execute('INSERT INTO jobs(id,competitor_id,name,keyword,domain,max_ads,status,requested_at) VALUES(?,?,?,?,?,?,?,?)',
                                      (job_id, target_id, query, query, '', limit, 'queued', now()))
                self.store.db.execute('INSERT INTO trend_dispatches(dispatch_key,brand_id,job_id,queued_at,automatic,keyword,keyword_key,kind) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(dispatch_key) DO UPDATE SET job_id=excluded.job_id,queued_at=excluded.queued_at,automatic=MAX(trend_dispatches.automatic,excluded.automatic),keyword=excluded.keyword,keyword_key=excluded.keyword_key,kind=excluded.kind',
                                      (dispatch_key, target_id, job_id, time.time(), int(automatic), query, query_key, 'keyword'))
                self.store.db.commit()
            except Exception:
                self.store.db.rollback()
                raise
            self.export()
            return self._job(job_id)

    def dispatch_ready(self):
        with self.lock:
            if not getattr(self, 'can_collect', lambda: True)() or not self.auto_enabled or self.stop_event.is_set():
                return 0
            policy = self.collection_policy()
            if not policy['enabled'] or policy['dailyRemaining'] <= 0 or policy['pending']:
                return 0
            last = self.store.rows('SELECT MAX(queued_at) AS t FROM trend_dispatches WHERE automatic=1')[0]['t'] or 0
            if time.time() - last < DISPATCH_INTERVAL_SECONDS:
                return 0
            for candidate in self.collection_candidates():
                if candidate['state'] not in ('ready', 'backlog'):
                    continue
                try:
                    self.collect(candidate['dispatchKey'], ADS_PER_QUERY, automatic=True)
                    return 1
                except ValueError:
                    continue
            return 0

    def record_snapshots(self, current, previous, category):
        if current.get('category') != category or previous.get('category') != category:
            raise ValueError('요청한 카테고리와 순위 데이터가 다릅니다.')
        # Validate complete, comparable source snapshots before replacing the last
        # successful scan. Partial ranks must never become false "new entries".
        settings = self.settings()
        # Keep keyword observations individually so later brand confirmation
        # never destroys the underlying evidence or invents an earlier rank.
        events = compare_snapshots(current, previous, minimum_rise=settings['minimumRise'],
                                   new_top=settings['newTop'], lookback_days=COMPARISON_DAYS)
        observed_at = now()
        with self.store.lock:
            assert_storage_available(self.store.root)
            try:
                for snapshot in (current, previous):
                    self.store.db.execute('INSERT INTO trend_snapshots(category,date,payload) VALUES(?,?,?) ON CONFLICT(category,date) DO UPDATE SET payload=excluded.payload',
                                          (category, snapshot['date'], json.dumps(snapshot, ensure_ascii=False)))
                self.store.db.execute('INSERT INTO trend_scans(category,current_date,previous_date,checked_at) VALUES(?,?,?,?) ON CONFLICT(category) DO UPDATE SET current_date=excluded.current_date,previous_date=excluded.previous_date,checked_at=excluded.checked_at',
                                      (category, current['date'], previous['date'], observed_at))
                for event in events:
                    event.pop('dispatchKey', None)
                    identity = [category, current['date'], previous['date'], _key(event['keyword'])]
                    event_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()
                    self.store.db.execute('INSERT INTO trend_events(id,category,current_date,observed_at,last_observed_at,payload) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_observed_at=excluded.last_observed_at,payload=excluded.payload',
                                          (event_id, category, current['date'], observed_at, observed_at,
                                           json.dumps(event, ensure_ascii=False)))
                self.store.db.commit()
            except Exception:
                self.store.db.rollback()
                raise
        self.last_success_at = observed_at
        self.source_errors.pop(category, None)
        self._refresh_error()
        self._persist_runtime()
        self.export()

    def scan(self):
        with self.lock:
            assert_storage_available(self.store.root)
            if self.scanning:
                raise ValueError('이미 네이버 순위를 확인하고 있습니다.')
            if self.stop_event.is_set():
                raise ValueError('수집기가 종료 중입니다.')
            settings = self.settings()
            self.scanning = True
            self.error = None
            self.last_attempt_at = now()
            self.next_attempt = time.time() + INTERVAL_SECONDS
            self._persist_runtime()
            self.export()
            self.thread = threading.Thread(target=self._scan, args=(settings,), name='naver-rank-scan', daemon=True)
            self.thread.start()

    def _scan(self, settings):
        categories = _categories(settings.get('categories', [settings['category']]))
        succeeded = False
        try:
            for category in categories:
                if self.stop_event.is_set():
                    break
                try:
                    self._scan_category(category)
                    succeeded = True
                except Exception as error:
                    if self.stop_event.is_set():
                        break
                    message = ('더 이전 날짜가 반환되어 이 분야의 최신 확인 자료를 유지합니다.'
                               if isinstance(error, SourceDateRegression) else
                               '네이버 순위를 확인하지 못했습니다. 이 분야의 이전 확인 결과는 유지됩니다.')
                    self.source_errors[category] = {'at': now(), 'message': message}
                    self._refresh_error()
                finally:
                    with self.lock:
                        self.process = None
            if succeeded and self.auto_enabled and self.settings() == settings and not self.stop_event.is_set():
                self.dispatch_ready()
        finally:
            with self.lock:
                self.next_attempt = time.time() + INTERVAL_SECONDS
                self.process = None
                self.scanning = False
                self._refresh_error()
                try:
                    self._persist_runtime()
                    self.export()
                except OSError:
                    # A disconnected archive must not redirect state onto C:.
                    pass

    def _scan_category(self, category):
        """One bounded child per category; successful categories commit separately."""
        assert_storage_available(self.store.root)
        run = self.store.root / 'trends' / secrets.token_hex(12)
        run.mkdir(parents=True)
        output_path = run / 'ranks.json'
        service_dir = Path(__file__).resolve().parent
        command = [sys.executable, str(service_dir / 'naver_rank_crawler.py'), '--category', category,
                   '--output', str(output_path)]
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
        with (run / 'scan.log').open('wb') as log:
            with self.lock:
                if self.stop_event.is_set():
                    raise RuntimeError('scan stopped')
                self.process = subprocess.Popen(command, cwd=service_dir, stdout=log, stderr=subprocess.STDOUT,
                                                env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1'), **options)
            deadline = time.monotonic() + 180
            while self.process.poll() is None:
                if self.stop_event.wait(.25) or time.monotonic() >= deadline:
                    self._kill_process()
                    raise RuntimeError('scan timed out')
            if self.process.returncode != 0:
                raise RuntimeError('source ranks unavailable')
        assert_storage_available(self.store.root)
        if not output_path.is_file() or output_path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('invalid rank data')
        result = json.loads(output_path.read_text(encoding='utf-8-sig'))
        validate_recent_source_date(result['current']['date'])
        current, _, _ = self._snapshots(category)
        if current and result['current']['date'] < current['date']:
            raise SourceDateRegression('source date regressed')
        self.record_snapshots(result['current'], result['previous'], category)

    def tick(self):
        if not self.auto_enabled or self.scanning or self.stop_event.is_set():
            return
        assert_storage_available(self.store.root)
        # Rank source polling remains hourly; bounded keyword dispatch can
        # progress independently after the previous queued search has finished.
        self.dispatch_ready()
        if time.time() < self.next_attempt:
            return
        target_date = (datetime.now(KST).date() - timedelta(days=1)).isoformat()
        current_snapshots = [self._snapshots(category)[0] for category in self.settings()['categories']]
        if all(current and current['date'] == target_date for current in current_snapshots):
            self.dispatch_ready()
            self.next_attempt = time.time() + INTERVAL_SECONDS
            self._persist_runtime()
            self.export()
        else:
            self.scan()

    def _kill_process(self):
        with self.lock:
            process = self.process
            if process is None or process.poll() is not None:
                return
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            else:
                import signal
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

    def stop(self):
        # Service shutdown is different from the user's OFF choice. Preserve
        # the last explicit setting so Windows restart can resume monitoring.
        self.stop_event.set()
        self._kill_process()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=20)
