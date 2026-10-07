"""Local-only cooperative switches, heartbeat and shared Naver publication lock."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import threading
import time

KST = timezone(timedelta(hours=9))


def stamp():
    return datetime.now(KST).isoformat(timespec='seconds')


def hub_root():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    return base / 'JoWooHyung/AutomationHub'


def read_json(path, default=None):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) else ({} if default is None else default)
    except (OSError, ValueError, TypeError):
        return {} if default is None else default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def enabled(automation_id, root=None):
    return read_json((root or hub_root()) / 'control.json').get(automation_id) is True


def parse_time(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=KST) if result.tzinfo is None else result.astimezone(KST)
    except (TypeError, ValueError):
        return None


@contextmanager
def file_lock(path):
    """Yield False immediately if a live process already owns this file lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        locked = False
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            pass
        try:
            yield locked
        finally:
            if locked:
                if os.name == 'nt':
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def cross_kind_ready(automation_id, ledger, current=None, gap_hours=3):
    current = current or datetime.now(KST)
    completed = parse_time(ledger.get('finishedAt'))
    return not (ledger.get('automationId') != automation_id and completed and
                current - completed < timedelta(hours=gap_hours))


@contextmanager
def publish_slot(automation_id, root=None, *, require_enabled=True):
    """Hold for the entire publication attempt; OFF never kills an active post."""
    root = root or hub_root()
    with file_lock(root / 'naver-publish.lock') as locked:
        permitted = locked and (not require_enabled or enabled(automation_id, root))
        if permitted:
            permitted = cross_kind_ready(automation_id, read_json(root / 'publication-ledger.json'))
        if not permitted:
            yield False
            return
        started = stamp()
        try:
            yield True
        finally:
            write_json(root / 'publication-ledger.json', {
                'automationId': automation_id, 'startedAt': started, 'finishedAt': stamp(),
            })


class Heartbeat:
    def __init__(self, automation_id, project_root, root=None):
        self.root = root or hub_root()
        self.automation_id = automation_id
        self.lock = threading.Lock()
        self.value = {'id': automation_id, 'pid': os.getpid(), 'projectRoot': str(project_root),
                      'running': False, 'state': 'starting', 'message': '시작 중', 'nextRunAt': None}
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.flush()
        self.thread.start()
        return self

    def update(self, **fields):
        with self.lock:
            self.value.update(fields, stateUpdatedAt=stamp())
        self.flush()

    def flush(self):
        with self.lock:
            value = dict(self.value, heartbeatAt=stamp(), enabled=enabled(self.automation_id, self.root))
        write_json(self.root / f'{self.automation_id}-heartbeat.json', value)

    def _loop(self):
        while not self.stop_event.wait(5):
            try:
                self.flush()
            except OSError:
                pass

    def stop(self):
        self.stop_event.set()
        self.update(running=False, state='stopped', message='프로세스 종료', nextRunAt=None)
