"""Personal loopback-only collector. No employer systems, credentials or cloud bills."""
from __future__ import annotations

import argparse
import hmac
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, unquote

from catalog import now, inside, normalize_row, export_catalog, public_card, atomic_json
from ad_lifecycle import merge_observation, merge_status_observation
from archive_publisher import ArchivePublisher
from datetime import datetime, timezone
from storage_config import resolve_data_dir, assert_storage_available, StorageUnavailable
from trend_service import TrendService

API = '/api/meta-ads'
SERVICE_DIR = Path(__file__).resolve().parent


def publication_snapshot(status):
    result = {key: status.get(key) for key in ('state', 'lastAttemptAt', 'lastSuccessAt', 'error', 'enabled')}
    # A static page cannot observe the end of the push carrying its own snapshot.
    # Keep the last completed transfer visible instead of freezing "publishing".
    if result['state'] == 'publishing':
        result['state'] = 'synced' if result['lastSuccessAt'] else 'pending'
    return result


def integer(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f'{label}: {minimum}–{maximum} 범위의 정수가 필요합니다.')
    return value


def competitor_input(body):
    result = {}
    for key in ('name', 'keyword'):
        value = body.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100 or any(ord(c) < 32 for c in value):
            raise ValueError('이름과 검색어는 1–100자로 입력하세요.')
        result[key] = value.strip()
    domain = str(body.get('domain') or '').strip().lower().removeprefix('www.')
    if domain and not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', domain):
        raise ValueError('도메인은 example.com 형식으로 입력하세요.')
    result['domain'] = domain
    result['intervalHours'] = integer(body.get('intervalHours', 6), 1, 168, '수집 주기')
    return result


class Store:
    def __init__(self, data_dir, web_root):
        self.root = Path(data_dir).resolve()
        self.web_root = Path(web_root).resolve()
        if self.root == self.web_root or self.root.is_relative_to(self.web_root):
            raise ValueError('개인 데이터 폴더는 웹사이트 폴더 밖이어야 합니다.')
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets = self.root / 'media'
        self.assets.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        # One process owns this personal database, including import/export commands.
        self.process_lockfile = (self.root / 'collector.lock').open('a+b')
        self.process_lockfile.seek(0, os.SEEK_END)
        if self.process_lockfile.tell() == 0:
            self.process_lockfile.write(b'0')
            self.process_lockfile.flush()
        self.process_lockfile.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.process_lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.process_lockfile.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.process_lockfile.close()
            raise ValueError('이 데이터 폴더의 수집기가 이미 실행 중입니다. 기존 앱을 먼저 종료하세요.')
        self.db = sqlite3.connect(self.root / 'collector.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS ads (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS collector_settings (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS competitors (id TEXT PRIMARY KEY, payload TEXT NOT NULL, last_attempt REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, competitor_id TEXT NOT NULL,
                name TEXT NOT NULL, keyword TEXT NOT NULL, domain TEXT NOT NULL, max_ads INTEGER NOT NULL,
                status TEXT NOT NULL, requested_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                message TEXT NOT NULL DEFAULT '', imported INTEGER NOT NULL DEFAULT 0);
        ''')
        # A previous crash can never leave a permanently-running job.
        self.db.execute("UPDATE jobs SET status='failed', message=?, finished_at=? WHERE status IN ('running','queued')",
                        ('앱이 종료되어 작업이 중단되었습니다. 다시 수집을 시작하세요.', now()))
        self.db.commit()

    def close(self):
        self.db.close()
        self.process_lockfile.close()

    def rows(self, sql, values=()):
        assert_storage_available(self.root)
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, values).fetchall()]

    def write(self, sql, values=()):
        assert_storage_available(self.root)
        with self.lock:
            self.db.execute(sql, values)
            self.db.commit()

    def cards(self):
        return sorted([json.loads(r['payload']) for r in self.rows('SELECT payload FROM ads')],
                      key=lambda c: (c['collectedAt'], c['id']), reverse=True)

    def catalog(self):
        return {'version': 1, 'updatedAt': now(), 'mode': 'local', 'cards': [public_card(c) for c in self.cards()]}

    def export(self):
        assert_storage_available(self.root)
        with self.lock:
            return export_catalog(self.cards(), self.assets, self.web_root)

    def import_file(self, jsonl):
        assert_storage_available(self.root)
        jsonl = Path(jsonl).resolve()
        if not jsonl.is_file() or jsonl.name != 'cards.jsonl' or jsonl.stat().st_size > 20 * 1024 * 1024:
            raise ValueError('20MB 이하의 cards.jsonl 파일이 필요합니다.')
        prepared = []
        with jsonl.open(encoding='utf-8-sig') as stream:
            for line in stream:
                if line.strip():
                    if len(prepared) >= 5000:
                        raise ValueError('한 번에 5,000개까지 가져올 수 있습니다.')
                    prepared.append(normalize_row(json.loads(line), jsonl.parent, self.assets))
        if not prepared:
            raise ValueError('가져올 광고가 없습니다.')
        with self.lock:
            existing = {r['id']: json.loads(r['payload']) for r in self.rows('SELECT id,payload FROM ads')}
            for card in prepared:
                card = merge_observation(existing.get(card['id'], {}), card)
                self.db.execute('INSERT INTO ads(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                                (card['id'], json.dumps(card, ensure_ascii=False)))
            self.db.commit()
            self.export()
        on_import = getattr(self, 'on_import', None)
        if on_import:
            on_import()
        return len({c['id'] for c in prepared} - set(existing))

    def setting(self, key, default=None):
        rows = self.rows('SELECT payload FROM collector_settings WHERE key=?', (key,))
        return json.loads(rows[0]['payload']) if rows else default

    def set_setting(self, key, value):
        self.write('INSERT INTO collector_settings(key,payload) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload',
                   (key, json.dumps(value)))

    def competitors(self):
        return [dict(json.loads(r['payload']), id=r['id']) for r in self.rows('SELECT * FROM competitors ORDER BY rowid')]

    def save_competitor(self, body, competitor_id=None):
        value = competitor_input(body)
        if competitor_id:
            existing = self.rows('SELECT payload FROM competitors WHERE id=?', (competitor_id,))
            if not existing:
                raise KeyError('대상을 찾을 수 없습니다.')
            if json.loads(existing[0]['payload']).get('trendOnly'):
                value['trendOnly'] = True
        else:
            if len(self.competitors()) >= 100:
                raise ValueError('수집 대상은 최대 100개입니다.')
            competitor_id = secrets.token_hex(8)
        self.write('INSERT INTO competitors(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                   (competitor_id, json.dumps(value, ensure_ascii=False)))
        return dict(value, id=competitor_id)

    def jobs(self):
        rows = self.rows('SELECT * FROM jobs ORDER BY requested_at DESC, rowid DESC LIMIT 50')
        return [dict(id=r['id'], competitorId=r['competitor_id'], name=r['name'], keyword=r['keyword'],
                     domain=r['domain'], limit=r['max_ads'], status=r['status'], requestedAt=r['requested_at'],
                     startedAt=r['started_at'], finishedAt=r['finished_at'], message=r['message'], imported=r['imported']) for r in rows]

    def enqueue(self, competitor_id, limit):
        limit = integer(limit, 1, 100, '수집 수')
        with self.lock:
            match = next((c for c in self.competitors() if c['id'] == competitor_id), None)
            if match is None:
                raise KeyError('수집 대상을 찾을 수 없습니다.')
            busy = self.rows("SELECT competitor_id FROM jobs WHERE status IN ('queued','running')")
            if any(r['competitor_id'] == competitor_id for r in busy):
                raise ValueError('이 대상은 이미 수집 대기 중이거나 실행 중입니다.')
            if len(busy) >= 20:
                raise ValueError('대기 중인 작업은 최대 20개입니다.')
            job_id = secrets.token_hex(12)
            self.write('INSERT INTO jobs(id,competitor_id,name,keyword,domain,max_ads,status,requested_at) VALUES(?,?,?,?,?,?,?,?)',
                       (job_id, competitor_id, match['name'], match['keyword'], match['domain'], limit, 'queued', now()))
            return next(job for job in self.jobs() if job['id'] == job_id)


class Controller:
    def __init__(self, store):
        self.store = store
        self.token = secrets.token_urlsafe(32)
        self.auto_enabled = bool(store.setting('autoEnabled', False))
        self.stop_event = threading.Event()
        self.process_lock = threading.RLock()
        self.process = None
        self.current_job = None
        self.thread = None
        self.collector_ready = self.check_runtime()
        self.last_card_count = len(self.store.cards())
        self.trends = TrendService(store)
        self.store.on_import = self.trends.export
        self.trends.can_collect = lambda: self.auto_enabled
        self.publisher = ArchivePublisher(store)
        self.publisher.enabled = bool(store.setting('autoPublishEnabled', False))
        self.automations = None
        self.monitor_thread = None
        self.status_check_running = False

    def set_auto(self, enabled):
        with self.process_lock:
            self.auto_enabled = enabled
            self.store.set_setting('autoEnabled', enabled)
            if not enabled:
                # Complete an in-flight request, but do not start queued requests.
                for job in self.store.jobs():
                    if job['status'] == 'queued':
                        self.cancel(job['id'])

    def next_run_at(self):
        if not self.auto_enabled:
            return None
        times = [r['last_attempt'] + json.loads(r['payload'])['intervalHours'] * 3600
                 for r in self.store.rows('SELECT * FROM competitors') if not json.loads(r['payload']).get('trendOnly')]
        return datetime.fromtimestamp(max(time.time(), min(times)), timezone.utc).isoformat(timespec='seconds') if times else None

    @staticmethod
    def check_runtime():
        if not all(importlib.util.find_spec(n) is not None for n in ('playwright', 'requests')):
            return False
        try:
            # Query only the bundled browser path; do not open a browser or navigate.
            # Isolate driver startup failures so broken installs do not affect the API.
            code = ('from pathlib import Path\nfrom playwright.sync_api import sync_playwright\n'
                    'with sync_playwright() as p:\n print("ready" if Path(p.chromium.executable_path).is_file() else "missing")')
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=15, **options)
            return result.returncode == 0 and result.stdout.strip() == 'ready'
        except Exception:
            return False

    def status(self):
        available = self.store.root.is_dir()
        if available:
            self.last_card_count = len(self.store.cards())
        jobs = self.store.jobs() if available else []
        latest_success = next((j.get('finishedAt') for j in jobs if j['status'] == 'done'), None)
        latest_attempt = next((j.get('startedAt') for j in jobs if j.get('startedAt')), None)
        latest_failure = next((j.get('message') for j in jobs[:1] if j['status'] == 'failed'), None)
        return {'mode': 'local', 'autoEnabled': self.auto_enabled, 'runningJobId': self.current_job,
                'nextRunAt': self.next_run_at() if available else None, 'lastSuccessAt': latest_success,
                'lastAttemptAt': latest_attempt, 'lastError': latest_failure, 'serverTime': now(),
                'statusCheckRunning': self.status_check_running, 'publication': self.publisher.status(),
                'cardCount': self.last_card_count, 'collectorReady': self.collector_ready,
                'storagePath': str(self.store.root), 'storageAvailable': available,
                'message': ('이 PC에서 실행 중 · 자동 수집은 앱이 켜져 있을 때만 동작합니다.' if available else
                            '저장 드라이브에 접근할 수 없습니다. 외장 드라이브를 연결하세요. 다른 경로에 저장하지 않습니다.')}

    def start(self):
        from automation_manager import AutomationManager
        projects = self.store.web_root.parent
        blog_python = os.environ.get('AUTOMATION_BLOG_PYTHON') or str(Path(os.environ.get('LOCALAPPDATA', ''))/'Programs/Python/Python312/python.exe')
        self.automations = AutomationManager(self, food_root=projects/'Bolg_Agent_two',
                                             beauty_root=projects/'Beauty_Blog_Agent', python=blog_python)
        self.automations.start()
        self.trends.export()
        self.monitor_thread = threading.Thread(target=self.monitor, name='automation-monitor', daemon=True)
        self.monitor_thread.start()
        self.thread = threading.Thread(target=self.run, name='meta-ads-worker', daemon=True)
        self.thread.start()

    def automation_status(self):
        status = self.status()
        available = status['storageAvailable']
        trend = self.trends.status() if available else {'autoEnabled':False,'scanning':False,'error':'D드라이브 연결 필요'}
        meta_state = 'running' if self.current_job or self.status_check_running else 'error' if status.get('lastError') else 'waiting' if self.auto_enabled else 'off'
        intervals = [c['intervalHours']*3600 for c in self.store.competitors() if not c.get('trendOnly')] if available else []
        next_check = self.store.setting('nextStatusCheck', 0) if available else 0
        meta_message = status.get('lastError') or ('광고 라이브러리 수집 중' if self.current_job else
                         '종료 여부 확인 중' if self.status_check_running else '광고 라이브러리 수집 예약')
        if not available:
            meta_message = 'D드라이브 연결 필요'
        result = [{'id':'meta-ads', 'name':'메타 광고', 'enabled':self.auto_enabled,
                   'running':bool(self.current_job or self.status_check_running), 'state':meta_state,
                   'nextRunAt':status['nextRunAt'], 'lastSuccessAt':status['lastSuccessAt'],
                   'lastAttemptAt':status['lastAttemptAt'], 'intervalSeconds':min(intervals) if intervals else 21600,
                   'statusCheckIntervalSeconds':3600, 'statusCheckBatchSize':10,
                   'nextStatusCheckAt':datetime.fromtimestamp(max(time.time(),next_check),timezone.utc).isoformat(timespec='seconds') if self.auto_enabled else None,
                   'message':meta_message,
                   'controllable':True},
                  {'id':'naver-trends', 'name':'네이버 급상승', 'enabled':trend['autoEnabled'],
                   'running':trend['scanning'], 'state':'running' if trend['scanning'] else 'error' if trend.get('error') else 'waiting' if trend['autoEnabled'] else 'off',
                   'nextRunAt':trend.get('nextRunAt'), 'lastSuccessAt':trend.get('lastSuccessAt') or trend.get('lastChecked'),
                   'intervalSeconds':trend.get('intervalSeconds',3600),
                   'message':trend.get('error') or '1시간마다 확인 · 일간 순위 기준', 'controllable':True}]
        if self.automations:
            result.extend(self.automations.status()['automations'])
        return {'automations':result, 'serverTime':now(), 'publication':self.publisher.status()}

    def monitor(self):
        while not self.stop_event.is_set():
            try:
                assert_storage_available(self.store.root)
                self.trends.tick()
                data = self.automation_status()
                # Only a public operational summary, never credentials, paths,
                # process IDs, local article data, account names or session tokens.
                allowed = ('id','name','enabled','running','state','nextRunAt','lastSuccessAt','lastAttemptAt','message',
                           'intervalSeconds','statusCheckIntervalSeconds','statusCheckBatchSize','nextStatusCheckAt')
                public = {'mode':'snapshot', 'updatedAt':now(), 'automations':[
                    {k:r.get(k) for k in allowed} for r in data['automations']], 'publication':publication_snapshot(data['publication'])}
                with self.store.lock:
                    atomic_json(self.store.web_root / 'tools/meta-ads/data/automation.json', public)
                self.publisher.tick()
            except Exception as error:
                print('Monitor:', type(error).__name__, flush=True)
            self.stop_event.wait(5)

    def kill_process(self):
        with self.process_lock:
            process = self.process
            if process is not None and process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                else:
                    import signal
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()

    def cancel(self, job_id):
        with self.process_lock:
            rows = self.store.rows('SELECT status FROM jobs WHERE id=?', (job_id,))
            if not rows:
                raise KeyError('작업을 찾을 수 없습니다.')
            if rows[0]['status'] not in ('running', 'queued'):
                return
            self.store.write("UPDATE jobs SET status='canceled',finished_at=?,message=? WHERE id=?",
                             (now(), '사용자가 작업을 취소했습니다.', job_id))
            if self.current_job == job_id:
                self.kill_process()

    def stop(self):
        self.stop_event.set()
        self.trends.stop()
        if self.automations:
            self.automations.stop()
        if self.current_job:
            self.cancel(self.current_job)
        if self.thread:
            self.thread.join(timeout=20)
        if self.monitor_thread:
            self.monitor_thread.join(timeout=6)

    def run(self):
        while not self.stop_event.is_set():
            try:
                assert_storage_available(self.store.root)
                with self.process_lock:
                    if self.auto_enabled:
                        for row in self.store.rows('SELECT * FROM competitors'):
                            conf = json.loads(row['payload'])
                            if conf.get('trendOnly'):
                                continue
                            if time.time() - row['last_attempt'] >= conf['intervalHours'] * 3600:
                                try:
                                    self.store.enqueue(row['id'], 20)
                                except ValueError:
                                    pass
                queued = self.store.rows("SELECT * FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1")
                if queued:
                    self.execute(queued[0])
                elif self.auto_enabled and time.time() >= self.store.setting('nextStatusCheck', 0):
                    self.check_saved_ads()
            except StorageUnavailable:
                self.auto_enabled = False
                self.trends.auto_enabled = False
                # Keep waiting for the same drive; never open a fallback database.
            except Exception as error:
                # No raw DB paths, credential values or crawler content leave this process.
                print('Worker error:', type(error).__name__, flush=True)
            self.stop_event.wait(1)

    def check_saved_ads(self):
        """Refresh the oldest saved status checks; missing ads stay unconfirmed."""
        cards = sorted(self.store.cards(), key=lambda c:c.get('statusCheckAttemptAt') or c.get('statusCheckedAt') or '')
        if not cards:
            return
        self.store.set_setting('nextStatusCheck', time.time()+3600)
        selected = cards[:10]
        attempted_at = now()
        for card in selected:
            card['statusCheckAttemptAt'] = attempted_at
            card['statusCheckOutcome'] = 'unavailable'
            self.store.write('UPDATE ads SET payload=? WHERE id=?', (json.dumps(card, ensure_ascii=False),card['id']))
        output = self.store.root / 'runs' / ('status-' + secrets.token_hex(6) + '.json')
        output.parent.mkdir(exist_ok=True)
        self.status_check_running = True
        options = {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        try:
            completed = subprocess.run([sys.executable, str(SERVICE_DIR/'check_ad_status.py'), '--ids', ','.join(c['id'] for c in selected), '--output', str(output)],
                                       capture_output=True, timeout=480, **options)
            if completed.returncode or not output.is_file():
                return
            for observation in json.loads(output.read_text(encoding='utf-8')).get('observations', []):
                old = next((c for c in selected if c['id'] == observation.get('id')), None)
                if not old:
                    continue
                old = merge_status_observation(old, observation)
                self.store.write('UPDATE ads SET payload=? WHERE id=?', (json.dumps(old, ensure_ascii=False),old['id']))
        finally:
            self.status_check_running = False
            self.store.export()

    def execute(self, job):
        assert_storage_available(self.store.root)
        job_id = job['id']
        with self.process_lock:
            if self.stop_event.is_set() or self.store.rows('SELECT status FROM jobs WHERE id=?', (job_id,))[0]['status'] != 'queued':
                return
            self.current_job = job_id
            self.store.write("UPDATE jobs SET status='running',started_at=?,message=? WHERE id=?",
                             (now(), 'Meta 광고 라이브러리에서 수집 중입니다.', job_id))
            self.store.write('UPDATE competitors SET last_attempt=? WHERE id=?', (time.time(), job['competitor_id']))
        runs = self.store.root / 'runs'
        run_dir = runs / job_id
        command = [sys.executable, str(SERVICE_DIR / 'crawler.py'), '--keyword', job['keyword'],
                   '--domain', job['domain'], '--total', str(job['max_ads']), '--batch', str(min(10, job['max_ads'])),
                   '--run-id', job_id, '--output-dir', str(runs), '--headless']
        try:
            assert_storage_available(self.store.root)
            runs.mkdir(exist_ok=True)
            log = runs / (job_id + '.log')
            with log.open('wb') as output:
                kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
                with self.process_lock:
                    if self.store.rows('SELECT status FROM jobs WHERE id=?', (job_id,))[0]['status'] == 'canceled':
                        return
                    process_environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
                    self.process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                                    cwd=SERVICE_DIR, env=process_environment, **kwargs)
                deadline = time.monotonic() + 600
                while self.process.poll() is None:
                    if self.stop_event.wait(.25) or time.monotonic() > deadline:
                        self.kill_process()
                        raise RuntimeError('timeout')
                code = self.process.returncode
            state = self.store.rows('SELECT status FROM jobs WHERE id=?', (job_id,))[0]['status']
            if state == 'canceled':
                return
            if code == 20:
                self.store.write("UPDATE jobs SET status='failed',finished_at=?,message=? WHERE id=? AND status!='canceled'",
                                 (now(), 'Meta가 수집 요청을 차단했습니다(접근 제한). 저장된 광고는 유지됩니다.', job_id))
                return
            if code != 0:
                raise RuntimeError('crawler')
            with self.process_lock:
                if self.store.rows('SELECT status FROM jobs WHERE id=?', (job_id,))[0]['status'] == 'canceled':
                    return
                imported = self.store.import_file(run_dir / 'cards.jsonl')
                self.store.write("UPDATE jobs SET status='done',finished_at=?,message=?,imported=? WHERE id=?",
                                 (now(), f'수집 완료 · 신규 광고 {imported}개', imported, job_id))
        except Exception:
            self.store.write("UPDATE jobs SET status='failed',finished_at=?,message=? WHERE id=? AND status!='canceled'",
                             (now(), '수집하지 못했습니다. Meta 접근 제한·로그인 요구·검색 결과 없음 또는 수집 도구 설치 상태를 확인하세요. 저장된 광고는 유지됩니다.', job_id))
        finally:
            with self.process_lock:
                self.process = None
                self.current_job = None
            try:
                self.trends.export()
            except (OSError, ValueError):
                pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'PersonalMetaAds/1.0'

    def log_message(self, format, *args):
        pass

    @property
    def controller(self):
        return self.server.controller

    def trusted_request(self, mutation=False):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        host = self.headers.get('Host', '')
        if host not in hosts:
            return False
        origin = self.headers.get('Origin')
        if origin is not None and origin != 'http://' + host:
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            return False
        if mutation:
            return origin == 'http://' + host and hmac.compare_digest(
                self.headers.get('X-Meta-Ads-Token', '').encode('utf-8'), self.controller.token.encode('utf-8'))
        return True

    def send_headers(self, code, content_type, size):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(size))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.end_headers()

    def json(self, value, code=200):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_headers(code, 'application/json; charset=utf-8', len(data))
        if self.command != 'HEAD':
            self.wfile.write(data)

    def do_OPTIONS(self):
        self.json({'error': '교차 출처 요청은 허용하지 않습니다.'}, 403)

    def do_GET(self):
        try:
            return self.get_request()
        except StorageUnavailable:
            return self.json({'error': '저장 드라이브에 접근할 수 없습니다. 외장 드라이브를 연결하세요.'}, 503)
        except Exception:
            return self.json({'error': '요청을 완료하지 못했습니다. 로컬 앱을 확인하세요.'}, 500)

    def get_request(self):
        if not self.trusted_request():
            return self.json({'error': '허용되지 않은 요청입니다.'}, 403)
        path = urlsplit(self.path).path
        store = self.controller.store
        if path == API + '/bootstrap':
            return self.json({'token': self.controller.token, 'status': self.controller.status(),
                              'competitors': store.competitors() if store.root.is_dir() else [],
                              'jobs': store.jobs() if store.root.is_dir() else []})
        if path == API + '/status':
            return self.json(self.controller.status())
        if path == API + '/automations':
            return self.json(self.controller.automation_status())
        if path == API + '/cards':
            return self.json(store.catalog())
        if path == API + '/competitors':
            return self.json({'competitors': store.competitors()})
        if path == API + '/jobs':
            return self.json({'jobs': store.jobs()})
        if path == API + '/trends':
            return self.json(self.controller.trends.status())
        if path.startswith(API):
            return self.json({'error': '찾을 수 없는 API입니다.'}, 404)
        return self.serve_static(path)

    do_HEAD = do_GET

    def serve_static(self, raw_path):
        root = self.controller.store.web_root
        try:
            decoded = unquote(raw_path)
            if '\\' in decoded or '\x00' in decoded or any(p.startswith('.') for p in decoded.split('/') if p):
                raise ValueError()
            parts = decoded.strip('/').split('/')
            private_parts = {'services', 'scripts', 'docs', 'work', 'tests', 'node_modules'}
            if any(part.rstrip(' .').casefold() in private_parts for part in parts):
                raise ValueError()
            target = inside(root, root / decoded.lstrip('/') / 'index.html') if decoded.endswith('/') else inside(root, root / decoded.lstrip('/'))
            if any(part.startswith('.') or part.rstrip(' .').casefold() in private_parts for part in target.relative_to(root).parts):
                raise ValueError()
            allowed = {'.html', '.css', '.js', '.mjs', '.json', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.mp4', '.ico', '.woff', '.woff2', '.ttf', '.pdf'}
            if not target.is_file() or target.suffix.lower() not in allowed:
                raise ValueError()
            # JSON is served only from the intentionally public catalog directory.
            if target.suffix.lower() == '.json' and not target.is_relative_to(root / 'tools/meta-ads/data'):
                raise ValueError()
            length = target.stat().st_size
            content_type = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
            if target.suffix.lower() in ('.js', '.mjs'):
                content_type = 'text/javascript; charset=utf-8'
            # Range requests allow video seeking without downloading the entire clip.
            requested = self.headers.get('Range')
            start, end = 0, length - 1
            if requested:
                match = re.fullmatch(r'bytes=(\d+)-(\d*)', requested)
                if not match:
                    return self.json({'error': '지원되지 않는 범위입니다.'}, 416)
                start, end = int(match[1]), int(match[2]) if match[2] else length - 1
                if start > end or end >= length:
                    return self.json({'error': '범위를 벗어났습니다.'}, 416)
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{length}')
            else:
                self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('X-Frame-Options', 'SAMEORIGIN')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            if self.command != 'HEAD':
                with target.open('rb') as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
        except (ValueError, OSError):
            return self.json({'error': '파일을 찾을 수 없습니다.'}, 404)

    def mutate(self):
        if not self.trusted_request(mutation=True):
            return self.json({'error': '이 앱에서 직접 실행한 요청만 허용합니다.'}, 403)
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('지원되지 않는 전송 형식입니다.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 16384:
                raise ValueError('요청이 너무 큽니다.')
            if length and self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('JSON 요청이 필요합니다.')
            body = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(body, dict):
                raise ValueError('객체 형식의 요청이 필요합니다.')
            path = urlsplit(self.path).path
            store = self.controller.store
            trends = self.controller.trends
            auto_match = re.fullmatch(API + r'/automations/(meta-ads|naver-trends|food-blog|beauty-blog)', path)
            if auto_match and self.command == 'POST':
                if not isinstance(body.get('enabled'), bool):
                    raise ValueError('enabled must be boolean')
                key, enabled = auto_match[1], body['enabled']
                if key == 'meta-ads':
                    self.controller.set_auto(enabled)
                elif key == 'naver-trends':
                    trends.save_settings({'autoEnabled':enabled})
                elif self.controller.automations:
                    self.controller.automations.set_enabled(key, enabled)
                else:
                    raise ValueError('Automation manager is unavailable')
                return self.json(self.controller.automation_status())
            if path == API + '/trends/settings' and self.command == 'POST':
                return self.json(trends.save_settings(body))
            if path == API + '/trends/scan' and self.command == 'POST':
                trends.scan()
                return self.json(trends.status(), 202)
            if path == API + '/trends/brands' and self.command == 'POST':
                brand = trends.save_brand(body)
                return self.json(dict(trends.status(), brand=brand), 201)
            if path == API + '/trends/ignore' and self.command == 'POST':
                trends.ignore(body.get('keyword'))
                return self.json(dict(trends.status(), ok=True))
            if path == API + '/trends/collect' and self.command == 'POST':
                job = trends.collect(body.get('dispatchKey'), body.get('limit', 20))
                return self.json(dict(trends.status(), job=job), 202)
            if path == API + '/competitors' and self.command == 'POST':
                return self.json({'competitor': store.save_competitor(body)}, 201)
            match = re.fullmatch(API + r'/competitors/([a-f0-9]{16})', path)
            if match and self.command == 'PUT':
                return self.json({'competitor': store.save_competitor(body, match[1])})
            if match and self.command == 'DELETE':
                for job in store.jobs():
                    if job['competitorId'] == match[1] and job['status'] in ('queued', 'running'):
                        self.controller.cancel(job['id'])
                store.write('DELETE FROM competitors WHERE id=?', (match[1],))
                return self.json({'ok': True})
            if path == API + '/collect' and self.command == 'POST':
                return self.json({'job': store.enqueue(body.get('competitorId'), body.get('limit', 20))}, 202)
            match = re.fullmatch(API + r'/jobs/([a-f0-9]{24})/cancel', path)
            if match and self.command == 'POST':
                self.controller.cancel(match[1])
                return self.json({'ok': True})
            if path == API + '/settings' and self.command == 'POST':
                if not isinstance(body.get('autoEnabled'), bool):
                    raise ValueError('autoEnabled는 true 또는 false여야 합니다.')
                self.controller.set_auto(body['autoEnabled'])
                if 'autoPublishEnabled' in body:
                    if not isinstance(body['autoPublishEnabled'], bool):
                        raise ValueError('autoPublishEnabled must be boolean')
                    self.controller.publisher.enabled = body['autoPublishEnabled']
                    store.set_setting('autoPublishEnabled', body['autoPublishEnabled'])
                return self.json(self.controller.status())
            if path == API + '/export' and self.command == 'POST':
                exported = store.export()
                return self.json({'ok': True, 'cardCount': len(exported['cards'])})
            if path == API + '/publish' and self.command == 'POST':
                return self.json(self.controller.publisher.request_now(), 202)
            # Browser import is restricted to a selected run inside the private runs folder.
            if path == API + '/import' and self.command == 'POST':
                run_id = body.get('runId', '')
                if not isinstance(run_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', run_id):
                    raise ValueError('올바르지 않은 실행 ID입니다.')
                source = inside(store.root / 'runs', store.root / 'runs' / run_id / 'cards.jsonl')
                imported = store.import_file(source)
                store.write("UPDATE jobs SET status='done',finished_at=?,imported=?,message=? WHERE id=? AND status='failed'",
                            (now(), imported, f'저장된 원본에서 복구 완료 · 신규 광고 {imported}개', run_id))
                return self.json({'imported': imported})
            return self.json({'error': '찾을 수 없는 작업입니다.'}, 404)
        except KeyError:
            return self.json({'error': '대상 또는 작업을 찾을 수 없습니다.'}, 404)
        except StorageUnavailable:
            return self.json({'error': '저장 드라이브에 접근할 수 없습니다. 외장 드라이브를 연결하세요.'}, 503)
        except (ValueError, TypeError) as error:
            if locals().get('path', '').startswith(API + '/trends'):
                return self.json({'error': str(error)[:240]}, 400)
            return self.json({'error': '입력값을 확인하세요. 중복 작업·허용 범위 밖 입력은 실행하지 않습니다.'}, 400)
        except Exception:
            return self.json({'error': '작업을 완료하지 못했습니다. 로컬 앱을 확인하세요.'}, 500)

    do_POST = mutate
    do_PUT = mutate
    do_DELETE = mutate


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, port, controller):
        self.controller = controller
        super().__init__(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description='개인용 Meta 광고 수집기')
    parser.add_argument('--web-root', default=os.environ.get('WEB_ROOT', str(SERVICE_DIR.parent.parent)))
    parser.add_argument('--data-dir')
    parser.add_argument('--port', type=int, default=4177)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--import-jsonl', action='append', default=[])
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    if not Path(args.web_root).is_dir():
        parser.error('웹사이트 폴더를 찾을 수 없습니다.')
    try:
        data_dir = resolve_data_dir(args.data_dir)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    store = Store(data_dir, args.web_root)
    for source in args.import_jsonl:
        print('Imported new public ads:', store.import_file(source))
    if args.export_only:
        print('Exported cards:', len(store.export()['cards']))
        store.close()
        return
    controller = Controller(store)
    server = Server(args.port, controller)
    url = f'http://127.0.0.1:{server.server_port}/tools/meta-ads/'
    print('Personal Meta Ads:', url, flush=True)
    print('Automation restores the saved ON/OFF settings. Public archive auto-sync is separately configured.', flush=True)
    if args.open:
        webbrowser.open(url)
    controller.start()
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
        server.server_close()
        store.close()


if __name__ == '__main__':
    main()
