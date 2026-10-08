"""Daily public-data collection and at most one verified beauty publication.

No unverified reference draft can pass the existing publish_beauty worker.
Collection runs initially, then at 07:00 KST. Publishing waits for a three-hour
gap from food jobs and uses the same process lock as the food scheduler.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from automation_bridge import (KST, Heartbeat, enabled, file_lock, hub_root,
                               parse_time, publish_slot, read_json, stamp, write_json)
from naver_auth_hold import publication_auth_hold, auth_hold_message

ROOT = Path(__file__).resolve().parent


def next_collection(current, last_date):
    if not last_date:
        return current
    target = current.replace(hour=7, minute=0, second=0, microsecond=0)
    if str(last_date) >= current.date().isoformat() or target > current:
        return target + (timedelta(days=1) if str(last_date) >= current.date().isoformat() else timedelta())
    return current


def publication_time(current, food_state, ledger=None):
    target = current
    events = [parse_time(job.get('time')) for job in food_state.get('jobs', [])]
    if ledger:
        finished = parse_time(ledger.get('finishedAt'))
        if finished and ledger.get('automationId') == 'food-blog':
            events.append(finished)
    # Iterating until stable handles multiple food slots whose exclusion windows overlap.
    for _ in range(len(events)+1):
        before = target
        for event in sorted(value for value in events if value):
            if abs((target-event).total_seconds()) < 3*3600:
                target = event + timedelta(hours=3)
        if target == before:
            break
    return target


def pending_article(root):
    candidates = []
    for path in (root/'drafts').glob('*/article.json'):
        article = read_json(path)
        if article.get('status') != 'draft' or not article.get('goodsNo'):
            continue
        if any((root/'state/publications').glob('*-'+str(article['goodsNo'])+'.json')):
            continue
        created = parse_time(article.get('generatedAt'))
        if created:
            candidates.append((created, path))
    return sorted(candidates, reverse=True)[0][1] if candidates else None


def run_child(script, *arguments):
    environment = {name:value for name,value in os.environ.items() if not name.upper().startswith('PARSE_')}
    # The collector loads its own .env; the publisher additionally sanitizes its worker.
    return subprocess.run([sys.executable, '-X', 'utf8', str(ROOT/script), *map(str, arguments)],
                          cwd=ROOT, env=environment, check=False).returncode


def publication_session_ready(root, config):
    """Check the configured local session only; authentication belongs to the publisher."""
    if publication_auth_hold(root, config.get('naver_blog_id')):
        return False
    session_file = config.get('naver_session_file')
    return bool(config.get('naver_blog_id') and session_file
                and (root/str(session_file)).is_file())


def publication_is_current(state, config):
    # Receipts from the former shared blog have no target marker and stay historical.
    blog_id = config.get('naver_blog_id')
    return bool(blog_id and state.get('lastPublicationBlogId') == blog_id)


def current_success_at(state, config):
    """Do not present the former blog's successful post as this target's success."""
    candidates = []
    if state.get('lastCollectionOk') is True:
        candidates.append(state.get('lastCollectionAt'))
    if publication_is_current(state, config) and state.get('lastPublicationOk') is True:
        candidates.append(state.get('lastPublicationAt'))
    dated = [(parse_time(value), value) for value in candidates if parse_time(value)]
    return max(dated, key=lambda item: item[0])[1] if dated else None


def waiting_status(state, config, session_ready, article, current, auth_hold=None):
    if auth_hold:
        return 'blocked', auth_hold_message(auth_hold) + ' · 수집 ON'
    if not session_ready:
        return 'blocked', f"{config.get('naver_blog_id') or '뷰티 블로그'} 로그인 필요 · 수집 ON"
    if state.get('lastCollectionOk') is False:
        return 'error', '최근 수집 실패 · 다음 일정에 재시도'
    current_publication = publication_is_current(state, config)
    if (current_publication and state.get('lastPublicationOk') is False
            and state.get('publicationAttemptDate') == current.date().isoformat()):
        return 'blocked', '발행 확인 필요 · 오늘 자동 재발행 보류'
    if not article:
        message = ('최근 뷰티 발행 완료 · 다음 수집 대기'
                   if current_publication and state.get('lastPublicationOk') is True
                   else '수집 ON · 확인된 발행용 초안 0개')
        return 'waiting', message
    return 'waiting', '맛집과 3시간 간격 · 하루 최대 1회 발행'


def main():
    hub = hub_root()
    with file_lock(hub/'beauty-blog-process.lock') as singleton:
        if not singleton:
            return 0
        heartbeat = Heartbeat('beauty-blog', ROOT).start()
        state_path = ROOT/'state/scheduler.json'
        state = read_json(state_path)
        config = read_json(ROOT/'config.json')
        food = (ROOT/config.get('restaurant_project', '../Bolg_Agent_two')).resolve()
        try:
            while True:
                current = datetime.now(KST)
                # A newly saved account/session becomes available without a scheduler restart.
                config = read_json(ROOT/'config.json')
                if not enabled('beauty-blog'):
                    heartbeat.update(running=False, state='paused', nextRunAt=None, message='예약 실행 OFF')
                    time.sleep(5)
                    continue
                due = next_collection(current, state.get('collectionDate'))
                if due <= current:
                    # Persist before starting: an interrupted or failed API call is not retried in a tight loop.
                    state['collectionDate'] = current.date().isoformat()
                    write_json(state_path, state)
                    heartbeat.update(running=True, state='running', nextRunAt=None, message='공개 랭킹·공식 전성분 수집 중')
                    result = run_child('beauty_agent.py', 'run')
                    state['lastCollectionAt'] = stamp()
                    state['lastCollectionOk'] = result == 0
                    if result == 0:
                        state['lastSuccessAt'] = stamp()
                    write_json(state_path, state)
                    heartbeat.update(running=False, lastSuccessAt=current_success_at(state, config))
                    current = datetime.now(KST)
                    due = next_collection(current, state.get('collectionDate'))
                article = pending_article(ROOT)
                session_ready = publication_session_ready(ROOT, config)
                if session_ready and article and state.get('publicationAttemptDate') != current.date().isoformat():
                    publish_at = publication_time(current, read_json(food/'scheduler_state.json'),
                                                  read_json(hub/'publication-ledger.json'))
                    if publish_at <= current and enabled('beauty-blog'):
                        with publish_slot('beauty-blog') as permitted:
                            if permitted:
                                state['publicationAttemptDate'] = current.date().isoformat()
                                write_json(state_path, state)
                                heartbeat.update(running=True, state='running', nextRunAt=None, message='확인된 뷰티 초안 발행 중')
                                result = run_child('publish_beauty.py', article)
                                state['lastPublicationAt'] = stamp()
                                state['lastPublicationOk'] = result == 0
                                state['lastPublicationBlogId'] = config['naver_blog_id']
                                if result == 0:
                                    state['lastSuccessAt'] = stamp()
                                write_json(state_path, state)
                        heartbeat.update(running=False)
                    else:
                        due = min(due, publish_at)
                state_name, message = waiting_status(
                    state, config, session_ready, article, current,
                    publication_auth_hold(ROOT, config.get('naver_blog_id')))
                heartbeat.update(running=False, state=state_name, nextRunAt=due.isoformat(),
                                 lastSuccessAt=current_success_at(state, config), message=message)
                time.sleep(5)
        except KeyboardInterrupt:
            return 0
        finally:
            heartbeat.stop()


if __name__ == '__main__':
    raise SystemExit(main())
