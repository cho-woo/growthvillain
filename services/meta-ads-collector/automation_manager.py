"""Manage only the two explicitly configured local blog schedulers."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from automation_bridge import hub_root, read_json, write_json, parse_time, stamp, KST


def heartbeat_status(automation_id, name, heartbeat, enabled, current=None):
    current = current or datetime.now(KST)
    at = parse_time(heartbeat.get('heartbeatAt'))
    fresh = bool(at and -5 <= (current-at).total_seconds() <= 25 and heartbeat.get('state') != 'stopped')
    value = {'id': automation_id, 'name': name, 'enabled': bool(enabled), 'running': False,
             'state': 'offline' if enabled else 'paused', 'nextRunAt': None,
             'lastSuccessAt': heartbeat.get('lastSuccessAt'), 'controllable': True,
             'message': '프로세스 응답 없음' if enabled else '예약 실행 OFF'}
    if fresh:
        value.update({key: heartbeat.get(key) for key in
                      ('running', 'state', 'nextRunAt', 'lastSuccessAt', 'message')})
        value['running'] = heartbeat.get('running') is True
        if not enabled and not value['running']:
            value.update(state='paused', nextRunAt=None, message='예약 실행 OFF')
        elif not enabled and value['running']:
            value.update(state='stopping', message='현재 작업 완료 후 대기 · 다음 실행 OFF')
    return value


class AutomationManager:
    def __init__(self, controller=None, food_root=None, beauty_root=None, *, root=None, python=None):
        self.controller = controller
        self.root = Path(root) if root else hub_root()
        projects = Path.home() / 'Desktop/codex/개발'
        self.projects = {
            'food-blog': (Path(food_root or projects/'Bolg_Agent_two'), 'run_scheduler.py', '맛집 블로그'),
            'beauty-blog': (Path(beauty_root or projects/'Beauty_Blog_Agent'), 'beauty_scheduler.py', '뷰티 블로그'),
        }
        self.python = str(python or os.environ.get('AUTOMATION_BLOG_PYTHON') or sys.executable)
        self.children = {}
        self.last_attempt = {}
        self.launch_errors = {}
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None

    def status(self):
        flags = read_json(self.root/'control.json')
        rows = []
        for automation_id, (_, _, name) in self.projects.items():
            heartbeat = read_json(self.root/f'{automation_id}-heartbeat.json')
            row = heartbeat_status(automation_id, name, heartbeat, flags.get(automation_id) is True)
            if row['state'] == 'offline' and automation_id in self.launch_errors:
                row['message'] = self.launch_errors[automation_id]
            rows.append(row)
        return {'automations': rows, 'serverTime': stamp()}

    def set_enabled(self, automation_id, value):
        if automation_id not in self.projects or not isinstance(value, bool):
            raise ValueError('등록된 블로그 ID와 enabled true/false가 필요합니다.')
        with self.lock:
            flags = read_json(self.root/'control.json')
            flags[automation_id] = value
            write_json(self.root/'control.json', flags)
        # Threads stay alive while OFF and honor the switch before each new job.
        # Nothing is killed, including browser or publication child processes.
        if value:
            self.tick()
        return self.status()

    def tick(self):
        with self.lock:
            flags = read_json(self.root/'control.json')
            for automation_id, (project, script, _) in self.projects.items():
                if flags.get(automation_id) is not True:
                    continue
                heartbeat = read_json(self.root/f'{automation_id}-heartbeat.json')
                at = parse_time(heartbeat.get('heartbeatAt'))
                if at and -5 <= (datetime.now(KST)-at).total_seconds() <= 25 and heartbeat.get('state') != 'stopped':
                    continue
                child = self.children.get(automation_id)
                if child and child.poll() is None:
                    continue
                if time.monotonic()-self.last_attempt.get(automation_id, -1000) < 60:
                    continue
                self.last_attempt[automation_id] = time.monotonic()
                if not (project/script).is_file() or not (project/'automation_bridge.py').is_file():
                    self.launch_errors[automation_id] = '스케줄러 연결 파일이 필요합니다.'
                    continue
                environment = {k:v for k,v in os.environ.items() if not k.upper().startswith('PARSE_')}
                environment.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
                self.root.mkdir(parents=True, exist_ok=True)
                try:
                    with (self.root/f'{automation_id}.log').open('a', encoding='utf-8') as log:
                        self.children[automation_id] = subprocess.Popen(
                            [self.python, '-X', 'utf8', str(project/script)], cwd=project,
                            env=environment, stdout=log, stderr=log,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    self.launch_errors.pop(automation_id, None)
                except OSError:
                    self.launch_errors[automation_id] = 'Python 실행 환경을 확인하세요.'

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        def loop():
            while not self.stop_event.is_set():
                try:
                    self.tick()
                except (OSError, ValueError):
                    pass
                self.stop_event.wait(5)
        self.thread = threading.Thread(target=loop, name='blog-automation-monitor', daemon=True)
        self.thread.start()

    def stop(self):
        # Stop the monitor only. Persisted scheduler switches keep their meaning.
        self.stop_event.set()
