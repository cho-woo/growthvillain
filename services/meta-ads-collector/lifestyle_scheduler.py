"""One daily lifestyle collection and at most one verified post at 23:10 KST.

Startup never catches up a missed slot. The publication worker owns the shared
Naver lock and rechecks its three-hour ledger immediately before publication.
Manual receipts consume today's allowance too; OFF never kills active work.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from automation_bridge import (KST, Heartbeat, enabled, file_lock, hub_root,
                               parse_time, read_json, write_json)

ROOT = Path(__file__).resolve().parent
AUTOMATION_ID = 'lifestyle-blog'
TARGET_BLOG = 'ehfvnd2007'
TARGET_CATEGORY = 15


def next_daily(current):
    """Strictly future slot: starting after 23:10 does not publish a backlog."""
    current = current.astimezone(KST)
    target = current.replace(hour=23, minute=10, second=0, microsecond=0)
    return target if target > current else target + timedelta(days=1)


def target_ready(root, config):
    """Read only login status and session existence, never account secrets."""
    if (config.get('naver_blog_id') != TARGET_BLOG or
            type(config.get('naver_category_no')) is not int or
            config.get('naver_category_no') != TARGET_CATEGORY or
            config.get('naver_category_name') != '일상' or
            config.get('naver_topic') != '일상·생각'):
        return False, '일상 발행 대상·카테고리 확인 필요'
    login = read_json(root/'state/naver-login-status.json')
    auth_hold = read_json(root/'state/publication-auth-required.json')
    verification_limited = (
        login.get('blogId') == TARGET_BLOG and login.get('state') == 'verification_limited'
    ) or (
        auth_hold.get('blogId') in (None, TARGET_BLOG)
        and auth_hold.get('state') == 'verification_limited'
    )
    if verification_limited:
        return False, '보호조치 인증 횟수 초과 · 발행 보류 · 수집 일정 유지'
    if (login.get('state') != 'ready' or login.get('blogId') != TARGET_BLOG or
            (root/'state/publication-auth-required.json').exists()):
        return False, '일상 로그인 확인 필요 · 수집 일정 유지'
    session = config.get('naver_session_file')
    if not isinstance(session, str) or not session.strip():
        return False, '일상 로그인 세션 필요 · 수집 일정 유지'
    try:
        session_path = (root/session).resolve()
        expected_session = (root/'state/naver_blog_session-ehfvnd2007.json').resolve()
        exists = session_path == expected_session and session_path.is_file()
    except (OSError, ValueError):
        exists = False
    return (True, '') if exists else (False, '일상 로그인 세션 필요 · 수집 일정 유지')


def receipts(root):
    """Only this exact blog/category's receipts influence its daily allowance."""
    return [record for path in (root/'state/publications').glob('*.json')
            if (record := read_json(path)).get('blogId') == TARGET_BLOG
            and type(record.get('categoryNo')) is int
            and record.get('categoryNo') == TARGET_CATEGORY]


def attempted_today(state, records, current):
    day = current.astimezone(KST).date().isoformat()
    if state.get('publicationAttemptDate') == day:
        return True
    return any((at := parse_time(record.get('at'))) and
               at.date().isoformat() == day for record in records)


def successful_publication_at(records):
    dates = [at for record in records if record.get('status') == 'published'
             and (at := parse_time(record.get('at')))]
    return max(dates).isoformat(timespec='seconds') if dates else None


def pending_article(root, current, records=None):
    """Select today's reviewed, new draft; the publisher validates its evidence."""
    records = receipts(root) if records is None else records
    used = {record.get('publicationId') for record in records}
    candidates = []
    for path in (root/'drafts').glob('*/article.json'):
        article = read_json(path)
        identity = article.get('publicationId')
        validation = article.get('validation')
        generated = parse_time(article.get('generatedAt'))
        if (article.get('status') != 'draft' or article.get('reviewStatus') != 'verified'
                or not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,120}', identity)
                or identity in used or not isinstance(validation, dict)
                or validation.get('sourcesVerified') is not True
                or validation.get('claimsChecked') is not True
                or not generated or generated > current
                or generated.date() != current.astimezone(KST).date()):
            continue
        # Even a malformed/partial prior receipt must never trigger a duplicate.
        if (root/'state/publications'/f'{TARGET_BLOG}-{TARGET_CATEGORY}-{identity}.json').exists():
            continue
        candidates.append((generated, path))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def publication_time(current, food_state, ledger=None, publication_heartbeats=()):
    """Keep three hours before/after known other-blog slots and actual finishes."""
    target = current
    events = [parse_time(job.get('time')) for job in food_state.get('jobs', [])
              if isinstance(job, dict)]
    if ledger and ledger.get('automationId') != AUTOMATION_ID:
        events.append(parse_time(ledger.get('finishedAt')))
    # A collection nextRunAt is not a publication promise. Accept only an
    # explicitly identified publication slot from another scheduler.
    for heartbeat in publication_heartbeats:
        if heartbeat.get('id') != AUTOMATION_ID:
            events.append(parse_time(heartbeat.get('nextPublicationAt')))
    events = sorted(event for event in events if event)
    for _ in range(len(events)+1):
        before = target
        for event in events:
            if abs((target-event).total_seconds()) < 3*3600:
                target = event + timedelta(hours=3)
        if before == target:
            break
    return target


def run_child(root, script, *arguments):
    environment = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith('PARSE_')}
    environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable, '-X', 'utf8', str(root/script), *map(str, arguments)],
                          cwd=root, env=environment, check=False,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0).returncode


class DailyScheduler:
    def __init__(self, root, hub, heartbeat, *, clock=None, runner=None):
        self.root, self.hub, self.heartbeat = Path(root), Path(hub), heartbeat
        self.clock = clock or (lambda: datetime.now(KST))
        self.runner = runner or (lambda script, *args: run_child(self.root, script, *args))
        self.next_run = next_daily(self.clock())
        self.pending_day = None
        self.state_path = self.root/'state/scheduler.json'

    def update_state(self, **fields):
        state = read_json(self.state_path)
        state.update(fields)
        write_json(self.state_path, state)
        return state

    def invoke(self, script, *arguments):
        try:
            return self.runner(script, *arguments)
        except (OSError, ValueError):
            return 1

    def tick(self):
        current = self.clock()
        today = current.date().isoformat()
        if not enabled(AUTOMATION_ID, self.hub):
            self.pending_day = None
            if self.next_run <= current:
                self.next_run = next_daily(current)
            self.heartbeat.update(running=False, state='paused', nextRunAt=None,
                                  message='예약 실행 OFF')
            return

        state = read_json(self.state_path)
        if current >= self.next_run:
            # A sleeping/offline process must not catch up yesterday's slot.
            due_day = self.next_run.date().isoformat()
            self.next_run = next_daily(current)
            if due_day == today and state.get('collectionAttemptDate') != today:
                self.update_state(collectionAttemptDate=today)
                self.heartbeat.update(running=True, state='running', phase='collection', nextRunAt=None,
                                      message='일상 키워드 수집·근거 확인 중')
                result = self.invoke('lifestyle_agent.py', 'run')
                current = self.clock()
                self.update_state(lastCollectionAt=current.isoformat(timespec='seconds'),
                                  lastCollectionOk=result == 0)
                self.pending_day = today if result == 0 else None

        state = read_json(self.state_path)
        config = read_json(self.root/'config.json')
        records = receipts(self.root)
        ready, reason = target_ready(self.root, config)
        article = pending_article(self.root, current, records)
        day_used = attempted_today(state, records, current)
        next_at = self.next_run
        if self.pending_day == current.date().isoformat() and not day_used and ready and article:
            food = self.root.parent/'Bolg_Agent_two/scheduler_state.json'
            publish_at = publication_time(current, read_json(food),
                                          read_json(self.hub/'publication-ledger.json'),
                                          [read_json(self.hub/'beauty-blog-heartbeat.json')])
            if publish_at.date() != current.date():
                self.pending_day = None
                state = self.update_state(deferredDate=today)
            elif publish_at <= current and enabled(AUTOMATION_ID, self.hub):
                # Persist before invoking: failures and interrupted attempts do
                # not cause repeated logins or duplicate publication that day.
                self.update_state(publicationAttemptDate=current.date().isoformat())
                self.pending_day = None
                self.heartbeat.update(running=True, state='running', phase='publication', nextRunAt=None,
                                      message='확인된 일상 초안 발행 중')
                result = self.invoke('publish_lifestyle.py', article)
                current = self.clock()
                state = self.update_state(lastPublicationAt=current.isoformat(timespec='seconds'),
                                          lastPublicationOk=result == 0)
                records = receipts(self.root)
                ready, reason = target_ready(self.root, config)
                day_used = True
            else:
                next_at = min(next_at, publish_at)
        elif self.pending_day != current.date().isoformat() or day_used:
            self.pending_day = None

        state_name, message = 'waiting', '매일 23:10 · 맛집·뷰티와 3시간 간격'
        if not ready:
            state_name, message = 'blocked', reason
        elif state.get('lastCollectionOk') is False:
            state_name, message = 'error', '최근 수집 실패 · 다음 일정에 재시도'
        elif day_used:
            today_records = [record for record in records if (at := parse_time(record.get('at')))
                             and at.date() == current.date()]
            confirmed = any(record.get('status') == 'published' for record in today_records)
            failed_today = (state.get('publicationAttemptDate') == current.date().isoformat()
                            and state.get('lastPublicationOk') is False)
            if not confirmed or any(record.get('status') != 'published' for record in today_records) or failed_today:
                state_name, message = 'blocked', '오늘 발행 확인 필요 · 자동 재발행 보류'
            else:
                message = '오늘 발행 완료 · 다음 수집 일정 대기'
        elif state.get('deferredDate') == current.date().isoformat():
            message = '오늘은 발행 간격 부족 · 다음 일정 대기'
        elif self.pending_day == current.date().isoformat() and not article:
            message = '키워드 수집 완료 · 확인된 새 초안 0개'
        generation = read_json(self.root/'state/generation.json')
        if ready and generation.get('needsAttention') is True:
            # Public status may contain a short UI label, never provider errors
            # or raw API responses. This is informational, not a retry hold.
            label = generation.get('statusLabel')
            if label not in ('AI 작성 연결 확인 필요', 'AI 작성 설정 확인 필요', 'AI 작성 검토 필요'):
                label = 'AI 작성 확인 필요'
            confirmed_today = any(record.get('status') == 'published'
                                  and (at := parse_time(record.get('at')))
                                  and at.date() == current.date() for record in records)
            if confirmed_today:
                state_name, message = 'error', '오늘 발행 완료 · '+label
            elif state_name == 'blocked':
                message = '오늘 발행 확인 필요 · '+label
            else:
                state_name, message = 'error', label
        self.heartbeat.update(running=False, phase='waiting', state=state_name,
                              nextRunAt=next_at.isoformat(timespec='seconds'),
                              lastSuccessAt=successful_publication_at(records), message=message)


def main():
    hub = hub_root()
    with file_lock(hub/'lifestyle-blog-process.lock') as singleton:
        if not singleton:
            return 0
        heartbeat = Heartbeat(AUTOMATION_ID, ROOT).start()
        scheduler = DailyScheduler(ROOT, hub, heartbeat)
        try:
            while True:
                scheduler.tick()
                time.sleep(5)
        except KeyboardInterrupt:
            return 0
        finally:
            heartbeat.stop()


if __name__ == '__main__':
    raise SystemExit(main())
