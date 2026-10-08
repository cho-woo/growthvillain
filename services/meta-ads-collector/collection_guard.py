"""One persistent Meta cooldown and disk reserve for all collection entry points."""
from datetime import datetime, timezone
import math
import shutil
import threading
import time


MIN_FREE_BYTES = 5 * 1024**3
BLOCK_DELAYS = (3600, 6 * 3600, 24 * 3600)
FAILURE_DELAY = 300


def _stamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec='seconds') if value else None


class CollectionGuard:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        saved = store.setting('collectionGuard', {})
        saved = saved if isinstance(saved, dict) else {}
        until = saved.get('until', 0)
        self.until = until if isinstance(until, (int, float)) and not isinstance(until, bool) and math.isfinite(until) and until >= 0 else 0
        streak = saved.get('blockStreak', 0)
        self.block_streak = min(3, max(0, streak)) if isinstance(streak, int) and not isinstance(streak, bool) else 0
        self.kind = saved.get('kind') if saved.get('kind') in ('blocked', 'failure') else None

    def _save(self):
        self.store.set_setting('collectionGuard', {'until': self.until, 'blockStreak': self.block_streak, 'kind': self.kind})

    def status(self, *, media=True):
        storage_ready = True
        try:
            # Both the private archive and the public copy need free capacity.
            storage_ready = all(shutil.disk_usage(path).free > MIN_FREE_BYTES
                                for path in (self.store.root, self.store.web_root))
        except OSError:
            storage_ready = False
        with self.lock:
            cooling = self.until > time.time()
            state = self.kind if cooling else 'storage' if media and not storage_ready else 'ready'
            reason = ('Meta 접근 제한 · 다음 자동 시도까지 대기' if state == 'blocked' else
                      'Meta 조회 오류 · 5분 대기 후 다음 작업 확인' if state == 'failure' else
                      '저장 공간 5GiB 이하 또는 드라이브 접근 불가 · 새 광고 수집 대기' if state == 'storage' else None)
            return {'state': state, 'reason': reason, 'nextAllowedAt': _stamp(self.until) if cooling else None,
                    'blockedUntil': _stamp(self.until) if cooling and self.kind == 'blocked' else None,
                    'blockStreak': self.block_streak, 'storageReady': storage_ready,
                    'minimumFreeBytes': MIN_FREE_BYTES}

    def allowed(self, *, media=True):
        return self.status(media=media)['state'] == 'ready'

    def blocked(self):
        with self.store.lock, self.lock:
            self.block_streak = min(3, self.block_streak + 1)
            self.until = time.time() + BLOCK_DELAYS[self.block_streak - 1]
            self.kind = 'blocked'
            self._save()

    def failed(self):
        with self.store.lock, self.lock:
            # A generic error cannot shorten an existing access-restriction wait.
            if self.kind == 'blocked' and self.until > time.time():
                return
            self.until = time.time() + FAILURE_DELAY
            self.kind = 'failure'
            self._save()

    def succeeded(self, *, reset_blocks=True):
        with self.store.lock, self.lock:
            if not reset_blocks and self.kind == 'blocked' and self.until > time.time():
                return
            self.until = 0
            self.kind = None
            if reset_blocks:
                self.block_streak = 0
            self._save()
