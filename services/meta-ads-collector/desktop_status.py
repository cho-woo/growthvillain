"""Small always-on-top, loopback-only automation status and control window."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import queue
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import webbrowser

EXPECTED = [('meta-ads', '메타 광고'), ('naver-trends', '네이버 급상승'),
            ('food-blog', '맛집 블로그'), ('beauty-blog', '뷰티 블로그')]
KST_OFFSET_SECONDS = 9 * 3600


def seconds_until(value, current=None):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            from datetime import timedelta
            parsed = parsed.replace(tzinfo=timezone(timedelta(seconds=KST_OFFSET_SECONDS)))
        return max(0, int(parsed.timestamp() - (current if current is not None else time.time())))
    except (ValueError, TypeError, OverflowError):
        return None


def countdown(value, current=None):
    remaining = seconds_until(value, current)
    if remaining is None:
        return '다음 일정 없음'
    if remaining == 0:
        return '다음 실행 확인 중'
    days, rest = divmod(remaining, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    if days:
        return f'{days}일 {hours}시간 후'
    if hours:
        return f'{hours}시간 {minutes}분 후'
    if minutes:
        return f'{minutes}분 {seconds:02d}초 후'
    return f'{seconds}초 후'


def interval_label(seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds <= 0:
        return '미설정'
    if seconds >= 3600:
        return f'{seconds/3600:g}시간'
    return f'{seconds/60:g}분'


def row_view(row, online, current=None):
    if not online:
        return {'label': 'OFF · 연결 끊김', 'color': '#f09090',
                'detail': '서버 연결 없음 · 실행 상태 확인 불가', 'switch': '—', 'disabled': True}
    enabled = row.get('enabled') is True
    running = row.get('running') is True
    state = row.get('state', '')
    if running:
        label, color = ('ON · 실행 중', '#82e0bb') if enabled else ('OFF · 마무리 중', '#e9c581')
        detail = row.get('message') or '현재 작업이 끝난 뒤 상태 갱신'
    elif state in ('offline', 'unknown', 'stopped', 'unavailable'):
        label, color = 'OFF · 응답 없음', '#f09090'
        detail = row.get('message') or '프로세스 연결을 확인하세요'
    elif not enabled:
        label, color, detail = 'OFF · 일시 정지', '#a5afbf', '새 작업이 시작되지 않습니다'
    elif state in ('error', 'failed', 'blocked'):
        label, color = 'ON · 확인 필요', '#e9c581'
        detail = row.get('message') or '최근 실행 내용을 확인하세요'
    else:
        label, color = 'ON · 대기', '#82e0bb'
        detail = countdown(row.get('nextRunAt'), current)
        if not row.get('nextRunAt') and row.get('message'):
            detail = row['message']
    if row.get('id') == 'meta-ads' and enabled and not running:
        cadence = f"수집 {interval_label(row.get('intervalSeconds'))} · 상태 {row.get('statusCheckBatchSize', 10)}개/{interval_label(row.get('statusCheckIntervalSeconds'))}"
        detail = cadence+' · '+detail
    return {'label': label, 'color': color, 'detail': str(detail),
            'switch': '끄기' if enabled else '켜기', 'disabled': row.get('controllable') is not True}


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalClient:
    def __init__(self, port=4177):
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError('Invalid local port')
        self.origin = f'http://127.0.0.1:{port}'
        self.token = None
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def request(self, path, body=None):
        headers = {'Accept': 'application/json', 'Origin': self.origin}
        if self.token:
            headers['X-Meta-Ads-Token'] = self.token
        data = None
        if body is not None:
            data = json.dumps(body).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        request = Request(self.origin+'/api/meta-ads/'+path, data=data, headers=headers)
        with self.opener.open(request, timeout=3) as response:
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError('Local response too large')
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError('Invalid local response')
            return value

    def authenticate(self):
        value = self.request('bootstrap')
        token = value.get('token')
        if not isinstance(token, str) or not token:
            raise ValueError('Local authentication not ready')
        self.token = token

    def snapshot(self):
        if not self.token:
            self.authenticate()
        try:
            value = self.request('automations')
        except HTTPError as exc:
            if exc.code not in (401, 403):
                raise
            self.token = None
            self.authenticate()
            value = self.request('automations')
        rows = value.get('automations')
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Invalid automation status')
        return value

    def switch(self, automation_id, enabled):
        if not re.fullmatch(r'[a-z0-9-]{1,50}', automation_id) or not isinstance(enabled, bool):
            raise ValueError('Invalid automation switch')
        if not self.token:
            self.authenticate()
        self.request('automations/'+automation_id, {'enabled': enabled})
        return self.snapshot()


class StatusWindow:
    def __init__(self, root, client):
        import tkinter as tk
        self.tk, self.root, self.client = tk, root, client
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='local-status')
        self.results = queue.Queue()
        self.busy = False
        self.closed = False
        self.online = False
        self.last_received = 0.0
        self.clock_delta = 0.0
        self.rows = {}
        self.widgets = {}
        self.next_poll = 0.0
        root.title('자동화 LIVE')
        root.configure(bg='#111923')
        root.attributes('-topmost', True)
        root.resizable(False, False)
        root.geometry(self.position())
        root.protocol('WM_DELETE_WINDOW', self.close)
        header = tk.Frame(root, bg='#111923')
        header.pack(fill='x', padx=16, pady=(12, 7))
        tk.Label(header, text='AUTOMATION', bg='#111923', fg='#f2f5f8', font=('Malgun Gothic', 10, 'bold')).pack(side='left')
        self.live = tk.Label(header, text='● 연결 확인', bg='#111923', fg='#a5afbf', font=('Malgun Gothic', 9))
        self.live.pack(side='right')
        for automation_id, name in EXPECTED:
            frame = tk.Frame(root, bg='#1b2532', padx=11, pady=8)
            frame.pack(fill='x', padx=12, pady=3)
            top = tk.Frame(frame, bg='#1b2532')
            top.pack(fill='x')
            tk.Label(top, text=name, bg='#1b2532', fg='#f3f6fa', font=('Malgun Gothic', 9, 'bold')).pack(side='left')
            button = tk.Button(top, text='—', width=5, relief='flat', bd=0, bg='#304254', fg='#f3f6fa',
                               activebackground='#3f5a72', activeforeground='white',
                               disabledforeground='#7c8795', cursor='hand2', font=('Malgun Gothic', 9),
                               command=lambda target=automation_id: self.toggle(target))
            button.pack(side='right')
            status = tk.Label(top, text='OFF', bg='#1b2532', fg='#a5afbf', font=('Malgun Gothic', 8))
            status.pack(side='right', padx=8)
            detail = tk.Label(frame, text='상태 확인 중', bg='#1b2532', fg='#aab7c7',
                              font=('Malgun Gothic', 8), anchor='w')
            detail.pack(fill='x', pady=(4, 0))
            self.widgets[automation_id] = (status, detail, button)
            for target in (status, detail):
                target.bind('<Enter>', lambda event, target_id=automation_id: self.show_history(target_id))
                target.bind('<Leave>', lambda event: self.notice.configure(text='5초 갱신 · 창을 닫아도 자동화 유지'))
        footer = tk.Frame(root, bg='#111923')
        footer.pack(fill='x', padx=16, pady=(6, 9))
        self.notice = tk.Label(footer, text='5초 갱신 · 창을 닫아도 자동화 유지', bg='#111923', fg='#8191a6', font=('Malgun Gothic', 8))
        self.notice.pack(side='left')
        tk.Button(footer, text='대시보드 ↗', bg='#111923', fg='#a1c8ec', relief='flat', bd=0,
                  activebackground='#111923', activeforeground='white', cursor='hand2', font=('Malgun Gothic', 8),
                  command=lambda: webbrowser.open('https://1jang2.netlify.app/tools/meta-ads/')).pack(side='right')
        root.after(100, self.tick)

    @staticmethod
    def position():
        import tkinter as tk
        width, height = 380, 352
        left, top, right, bottom = 0, 0, tk._default_root.winfo_screenwidth(), tk._default_root.winfo_screenheight()
        try:
            import ctypes
            from ctypes import wintypes
            rectangle = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rectangle), 0):
                left, top, right, bottom = rectangle.left, rectangle.top, rectangle.right, rectangle.bottom
        except (ImportError, AttributeError, OSError):
            pass
        return f'{width}x{height}+{max(left,right-width-18)}+{top+16}'

    def submit(self, operation):
        if self.busy or self.closed:
            return
        self.busy = True
        def run():
            try:
                self.results.put(('ok', operation()))
            except (HTTPError, URLError, OSError, ValueError, TypeError):
                # Never put tokens, headers, request bodies or tracebacks in the widget.
                self.results.put(('error', None))
        self.pool.submit(run)

    def toggle(self, automation_id):
        row = self.rows.get(automation_id, {})
        if not self.online or self.busy or row.get('controllable') is not True:
            return
        desired = row.get('enabled') is not True
        self.notice.configure(text='설정 적용 중…')
        self.submit(lambda: self.client.switch(automation_id, desired))

    def show_history(self, automation_id):
        row = self.rows.get(automation_id, {})
        value = row.get('lastSuccessAt')
        try:
            shown = datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone().strftime('%m/%d %H:%M')
        except (ValueError, TypeError):
            shown = '기록 없음'
        self.notice.configure(text='마지막 성공 '+shown)

    def tick(self):
        if self.closed:
            return
        try:
            kind, value = self.results.get_nowait()
            self.busy = False
            self.next_poll = time.monotonic()+5
            if kind == 'ok':
                self.rows = {row.get('id'):row for row in value['automations']}
                self.online = True
                self.last_received = time.monotonic()
                server_time = value.get('serverTime')
                try:
                    self.clock_delta = datetime.fromisoformat(server_time.replace('Z', '+00:00')).timestamp()-time.time()
                except (ValueError, AttributeError, TypeError):
                    self.clock_delta = 0
                self.notice.configure(text='5초 갱신 · 창을 닫아도 자동화 유지')
            else:
                self.online = False
                self.notice.configure(text='로컬 서버 연결 또는 조작 실패 · 자동 재확인')
        except queue.Empty:
            pass
        if self.last_received and time.monotonic()-self.last_received > 15:
            self.online = False
        self.live.configure(text='● LIVE 연결' if self.online else '● 연결 끊김',
                            fg='#82e0bb' if self.online else '#f09090')
        for automation_id, (status, detail, button) in self.widgets.items():
            row = self.rows.get(automation_id, {})
            view = row_view(row, self.online and bool(row), time.time()+self.clock_delta)
            status.configure(text=view['label'], fg=view['color'])
            detail.configure(text=view['detail'][:47])
            button.configure(text=view['switch'], state='disabled' if self.busy or view['disabled'] else 'normal')
        if not self.busy and time.monotonic() >= self.next_poll:
            self.submit(self.client.snapshot)
        self.root.after(250, self.tick)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main():
    from automation_bridge import file_lock, hub_root
    with file_lock(hub_root() / 'desktop-status.lock') as locked:
        if locked:
            return run_window()


def run_window():
    parser = argparse.ArgumentParser(description='자동화 상태창 (창을 닫아도 예약 실행 유지)')
    parser.add_argument('--port', type=int, default=4177)
    args = parser.parse_args()
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    import tkinter as tk
    root = tk.Tk()
    StatusWindow(root, LocalClient(args.port))
    root.mainloop()


if __name__ == '__main__':
    main()
