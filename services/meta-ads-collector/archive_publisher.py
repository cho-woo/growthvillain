"""Publish only the public archive using the repository's bounded Git publisher."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from catalog import atomic_json, now


# Only exact, authored messages from Publish-Archive.ps1 may enter diagnostics.
# Git output, remote URLs, credentials and arbitrary exception messages are not stored.
KNOWN_PUBLICATION_ERRORS = frozenset({
    'Git was not found. Install Git for Windows or start from Codex.',
    'Git operation failed.',
    'Unrelated staged or unpublished changes were found. Finish those changes separately before publishing the archive.',
    'The selected folder is not the repository root.',
    'Origin must point only to cho-woo/growthvillain on GitHub. Nothing was published.',
    'Switch to the master branch before publishing the archive.',
    'The public catalog is missing. Collect or export ads first.',
    'The public catalog format is invalid.',
    'Could not check GitHub. Check your network and Git authentication, then retry.',
    'GitHub contains newer changes. Update the project before publishing; no merge is attempted automatically.',
    'The staged archive failed validation.',
    'Could not create the archive commit. Check your Git name/email settings.',
    'GitHub push failed. Your archive commit is saved locally. Check Git authentication and retry this file.',
})


def known_publication_error(*outputs):
    for output in outputs:
        if isinstance(output, bytes):
            encoding = 'utf-16-le' if b'\0' in output[:256] else 'utf-8'
            output = output.decode(encoding, errors='replace')
        if not isinstance(output, str):
            continue
        for line in output.splitlines():
            line = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', line).strip()
            prefix = 'Publication stopped: '
            if line.startswith(prefix) and line[len(prefix):] in KNOWN_PUBLICATION_ERRORS:
                return line[len(prefix):]
    return None


class PublicationFailure(RuntimeError):
    def __init__(self, kind):
        self.kind = kind
        super().__init__(kind)


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
        for name in ('catalog.json', 'trends.json', 'investigations.json'):
            path = root / name
            if path.is_file():
                digest.update(name.encode())
                digest.update(path.read_bytes())
        # Runtime snapshots update locally every few seconds. Publish semantic
        # changes and one hourly heartbeat, not every countdown or push timestamp.
        path = root / 'automation.json'
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            items = [{k: row.get(k) for k in ('id','enabled','state','nextRunAt','lastSuccessAt','message')}
                     for row in data.get('automations', [])]
            digest.update(json.dumps(items, sort_keys=True, ensure_ascii=False).encode())
            publication = data.get('publication') or {}
            # Include meaningful publication recovery once, while excluding
            # timestamps/transient states that would make every push trigger
            # another push of its own status forever.
            publication_state = {'enabled': bool(publication.get('enabled')),
                                 'hasSuccess': bool(publication.get('lastSuccessAt')),
                                 'error': publication.get('error')}
            digest.update(json.dumps(publication_state, sort_keys=True, ensure_ascii=False).encode())
        digest.update(str(int(time.time() // 3600)).encode())
        return digest.hexdigest()

    def tick(self):
        # Both the monitor and an HTTP request may arrive here. Keep the
        # decision and worker reservation atomic; publication itself stays on
        # the worker, outside this lock during slow Git/network operations.
        with self.lock:
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

    def request_now(self):
        with self.lock:
            if not self.enabled:
                raise ValueError('자동 사이트 게시를 먼저 켜세요.')
            self.state['retryAfter'] = 0
            self.pending_since = time.time()-61
            self.last_tick = 0
            self.tick()
            return self.status()

    def publish(self, fingerprint):
        with self.lock:
            self.state.update(state='publishing', lastAttemptAt=now(), error=None)
            atomic_json(self.path, self.state)
        diagnostic = {'at': now(), 'stage': 'resolve_shell'}
        started = time.monotonic()
        try:
            shell = shutil.which('powershell.exe') or shutil.which('pwsh')
            if not shell:
                raise PublicationFailure('shell_not_found')
            script = Path(__file__).with_name('Publish-Archive.ps1')
            diagnostic['stage'] = 'locate_script'
            if not script.is_file():
                raise PublicationFailure('script_not_found')
            command = [shell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                       str(script), '-Repository', str(self.store.web_root)]
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            # Exports copy immutable, hashed media before atomically replacing
            # JSON. Git can read those files without holding the live DB lock.
            # Network publication must never block local status or ON/OFF.
            diagnostic['stage'] = 'powershell'
            result = subprocess.run(command, capture_output=True, timeout=240, **options)
            diagnostic['returncode'] = result.returncode
            if result.returncode:
                message = known_publication_error(getattr(result, 'stdout', None), getattr(result, 'stderr', None))
                if message:
                    diagnostic['message'] = message
                raise PublicationFailure('powershell_failed')
            with self.lock:
                self.state.update(state='synced', lastSuccessAt=now(), publishedHash=fingerprint, retryAfter=0, error=None)
        except Exception as error:
            diagnostic.update(exceptionType=type(error).__name__, elapsedMs=round((time.monotonic()-started)*1000))
            if isinstance(error, PublicationFailure):
                diagnostic['kind'] = error.kind
            elif isinstance(error, subprocess.TimeoutExpired):
                diagnostic.update(kind='timeout', timeoutSeconds=240)
            elif isinstance(error, FileNotFoundError):
                diagnostic['kind'] = 'process_file_not_found'
            elif isinstance(error, OSError):
                diagnostic['kind'] = 'process_os_error'
            else:
                diagnostic['kind'] = 'unexpected_error'
            if isinstance(getattr(error, 'errno', None), int):
                diagnostic['errno'] = error.errno
            with self.lock:
                self.state.update(state='error', error='사이트 동기화 실패 · Git 연결 또는 배포 상태 확인 필요', retryAfter=time.time()+900, diagnostic=diagnostic)
        finally:
            with self.lock:
                self.pending_since = 0
                atomic_json(self.path, self.state)
