"""Publish only the public archive using the repository's bounded Git publisher."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

from catalog import atomic_json, now


class ArchivePublisher:
    def __init__(self, store):
        self.store = store
        self.path = store.root / 'publication_state.json'
        try:
            self.state = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.state = {}
        self.state['state'] = 'idle'
        self.enabled = False
        self.thread = None
        self.last_tick = 0
        self.pending_since = 0
        self.pending_hash = None
        self.lock = threading.RLock()

    def status(self):
        with self.lock:
            return {**{k: self.state.get(k) for k in ('state','lastAttemptAt','lastSuccessAt','error')}, 'enabled': self.enabled}

    def fingerprint(self):
        root = self.store.web_root / 'tools/meta-ads/data'
        digest = hashlib.sha256()
        for name in ('catalog.json', 'trends.json'):
            path = root / name
            if path.is_file():
                digest.update(name.encode())
                digest.update(path.read_bytes())
        # Runtime snapshots update locally every few seconds. Publish semantic
        # changes and one hourly heartbeat, not every countdown or own push state.
        path = root / 'automation.json'
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            items = [{k: row.get(k) for k in ('id','enabled','state','nextRunAt','lastSuccessAt','message')}
                     for row in data.get('automations', [])]
            digest.update(json.dumps(items, sort_keys=True, ensure_ascii=False).encode())
        digest.update(str(int(time.time() // 3600)).encode())
        return digest.hexdigest()

    def tick(self):
        if not self.enabled or (self.thread and self.thread.is_alive()):
            return
        stamp = time.time()
        if stamp - self.last_tick < 20:
            return
        self.last_tick = stamp
        fingerprint = self.fingerprint()
        if fingerprint == self.state.get('publishedHash'):
            self.pending_since = 0
            return
        if not self.pending_since:
            self.pending_since = stamp
        if stamp - self.pending_since < 60 or stamp < self.state.get('retryAfter', 0):
            return
        self.thread = threading.Thread(target=self.publish, args=(fingerprint,), name='archive-publisher', daemon=True)
        self.thread.start()

    def publish(self, fingerprint):
        with self.lock:
            self.state.update(state='publishing', lastAttemptAt=now(), error=None)
            atomic_json(self.path, self.state)
        try:
            shell = shutil.which('powershell.exe') or shutil.which('pwsh')
            if not shell:
                raise RuntimeError('shell')
            command = [shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                       str(Path(__file__).with_name('Publish-Archive.ps1')), '-Repository', str(self.store.web_root)]
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            # Exports copy immutable, hashed media before atomically replacing
            # JSON. Git can read those files without holding the live DB lock.
            # Network publication must never block local status or ON/OFF.
            result = subprocess.run(command, capture_output=True, timeout=240, **options)
            if result.returncode:
                raise RuntimeError('publish')
            with self.lock:
                self.state.update(state='synced', lastSuccessAt=now(), publishedHash=fingerprint, retryAfter=0, error=None)
        except Exception:
            with self.lock:
                self.state.update(state='error', error='사이트 동기화 실패 · Git 연결 또는 배포 상태 확인 필요', retryAfter=time.time()+900)
        finally:
            with self.lock:
                self.pending_since = 0
                atomic_json(self.path, self.state)
