"""Small always-on-top, loopback-only automation status and control window."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import queue
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import webbrowser

EXPECTED = [('meta-ads', '메타 광고'), ('naver-trends', '네이버 급상승'),
            ('food-blog', '맛집 블로그'), ('beauty-blog', '뷰티 블로그'), ('oliveyoung', '올리브영 순위')]
KST_OFFSET_SECONDS = 9 * 3600
DEFAULT_NOTICE = '5초 갱신 · X는 트레이로 숨김'


def opacity_percent(value):
    """Invalid preferences use the readable default; valid values stay 30–100%."""
    if isinstance(value, bool):
        return 100
    try:
        value = float(value)
        return max(30, min(100, round(value))) if math.isfinite(value) else 100
    except (ValueError, TypeError, OverflowError):
        return 100


class WidgetPreferences:
    def __init__(self, path=None):
        from automation_bridge import hub_root
        self.path = Path(path) if path else hub_root()/'widget-preferences.json'

    def opacity(self):
        from automation_bridge import read_json
        return opacity_percent(read_json(self.path).get('opacity', 100))

    def save_opacity(self, value):
        from automation_bridge import write_json
        write_json(self.path, {'opacity': opacity_percent(value)})


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
    if row.get('id') == 'meta-ads' and enabled:
        cadence = f"수집 {interval_label(row.get('intervalSeconds'))}마다 · 종료 점검 {row.get('statusCheckBatchSize', 10)}개/{interval_label(row.get('statusCheckIntervalSeconds'))}"
        upcoming = countdown(row.get('nextRunAt'), current)
        current_status = '수집 중 · ' if running else '최근 오류 · ' if state in ('error','failed','blocked') else ''
        detail = cadence+'\n'+current_status+'다음 수집 '+upcoming
    if row.get('id') == 'oliveyoung' and state == 'waiting' and enabled:
        count = re.match(r'\d+개', str(row.get('message', '')))
        detail = (count[0]+' · ' if count else '')+'뷰티 연동 · '+countdown(row.get('nextRunAt'), current)
    return {'label': label, 'color': color, 'detail': str(detail),
            'switch': '연동' if row.get('id') == 'oliveyoung' else '끄기' if enabled else '켜기',
            'disabled': row.get('controllable') is not True}


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
        try:
            self.request('automations/'+automation_id, {'enabled': enabled})
        except HTTPError as exc:
            if exc.code not in (401, 403):
                raise
            self.token = None
            self.authenticate()
            self.request('automations/'+automation_id, {'enabled': enabled})
        return self.snapshot()


class StatusWindow:
    def __init__(self, root, client, *, tray_factory=None, preferences_path=None, start_poll=True):
        import tkinter as tk
        from windows_tray import WindowsTray
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
        self.tray_events = queue.Queue()
        self.tray = (tray_factory or WindowsTray)(self.tray_events)
        self.tray_hidden = False
        self.next_tray_retry = 0.0
        self.preferences = WidgetPreferences(preferences_path)
        self.opacity = self.preferences.opacity()
        self.opacity_save_job = None
        self.tick_job = None
        self.tray_job = None
        root.title('자동화 LIVE')
        root.configure(bg='#111923')
        root.attributes('-topmost', True)
        root.resizable(False, False)
        root.geometry(self.position())
        root.protocol('WM_DELETE_WINDOW', self.hide_to_tray)
        root.attributes('-alpha', self.opacity/100)
        header = tk.Frame(root, bg='#111923')
        header.pack(fill='x', padx=16, pady=(12, 7))
        tk.Label(header, text='AUTOMATION', bg='#111923', fg='#f2f5f8', font=('Malgun Gothic', 10, 'bold')).pack(side='left')
        self.live = tk.Label(header, text='● 연결 확인', bg='#111923', fg='#a5afbf', font=('Malgun Gothic', 9))
        self.live.pack(side='right')
        menu_button = tk.Menubutton(header, text='⋯', bg='#111923', fg='#aab7c7',
                                   activebackground='#253346', activeforeground='white',
                                   relief='flat', cursor='hand2', font=('Malgun Gothic', 10))
        menu_button.pack(side='right', padx=(3, 7))
        window_menu = tk.Menu(menu_button, tearoff=False)
        window_menu.add_command(label='트레이로 숨기기', command=self.hide_to_tray)
        window_menu.add_separator()
        window_menu.add_command(label='현황판 종료 (자동화 유지)', command=self.close)
        menu_button.configure(menu=window_menu)
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
                              font=('Malgun Gothic', 8), anchor='nw', justify='left', wraplength=330,
                              height=2 if automation_id == 'meta-ads' else 1)
            detail.pack(fill='x', pady=(4, 0))
            self.widgets[automation_id] = (status, detail, button)
            for target in (status, detail):
                target.bind('<Enter>', lambda event, target_id=automation_id: self.show_history(target_id))
                target.bind('<Leave>', lambda event: self.notice.configure(text=DEFAULT_NOTICE))
        opacity_bar = tk.Frame(root, bg='#111923')
        opacity_bar.pack(fill='x', padx=16, pady=(3, 0))
        tk.Label(opacity_bar, text='불투명도', bg='#111923', fg='#aab7c7', font=('Malgun Gothic', 8)).pack(side='left')
        self.opacity_label = tk.Label(opacity_bar, text=f'{self.opacity}%', bg='#111923', fg='#d7e4f2',
                                      font=('Malgun Gothic', 8), width=5)
        self.opacity_label.pack(side='right')
        self.opacity_scale = tk.Scale(opacity_bar, from_=30, to=100, orient='horizontal', showvalue=False,
                                      resolution=1, length=245, width=7, sliderlength=12, bd=0,
                                      highlightthickness=0, bg='#111923', troughcolor='#304254',
                                      activebackground='#82e0bb', command=self.change_opacity)
        self.opacity_scale.set(self.opacity)
        self.opacity_scale.pack(side='right', padx=(9, 3))
        footer = tk.Frame(root, bg='#111923')
        footer.pack(fill='x', padx=16, pady=(6, 9))
        self.notice = tk.Label(footer, text=DEFAULT_NOTICE, bg='#111923', fg='#8191a6', font=('Malgun Gothic', 8))
        self.notice.pack(side='left')
        tk.Button(footer, text='대시보드 ↗', bg='#111923', fg='#a1c8ec', relief='flat', bd=0,
                  activebackground='#111923', activeforeground='white', cursor='hand2', font=('Malgun Gothic', 8),
                  command=lambda: webbrowser.open('https://1jang2.netlify.app/tools/meta-ads/')).pack(side='right')
        self.tray.start()
        self.tray_job = root.after(100, self.process_tray_events)
        if start_poll:
            self.tick_job = root.after(100, self.tick)

    @staticmethod
    def position():
        import tkinter as tk
        width, height = 380, 474
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

    def change_opacity(self, value):
        if self.closed:
            return
        self.opacity = opacity_percent(value)
        self.root.attributes('-alpha', self.opacity/100)
        self.opacity_label.configure(text=f'{self.opacity}%')
        if self.opacity_save_job is not None:
            self.root.after_cancel(self.opacity_save_job)
        self.opacity_save_job = self.root.after(300, self.persist_opacity)

    def persist_opacity(self):
        self.opacity_save_job = None
        try:
            self.preferences.save_opacity(self.opacity)
        except OSError:
            self.notice.configure(text='불투명도 저장 실패 · 이번 실행에 적용')

    def hide_to_tray(self):
        if self.closed:
            return
        if self.tray.ensure_registered():
            self.tray_hidden = True
            self.root.withdraw()
        else:
            # Never strand a hidden window without a tray icon. The normal taskbar
            # button remains available, and the ⋯ menu can still exit the widget.
            self.tray_hidden = False
            self.notice.configure(text='트레이 연결 실패 · 작업 표시줄로 최소화')
            self.root.iconify()

    def show(self):
        if self.closed:
            return
        self.tray_hidden = False
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        self.root.lift()
        self.root.focus_force()

    def process_tray_events(self):
        if self.closed:
            return
        while True:
            try:
                action = self.tray_events.get_nowait()
            except queue.Empty:
                break
            if action == 'open':
                self.show()
            elif action == 'exit':
                self.close()
                return
            elif action == 'unavailable':
                if self.tray_hidden:
                    self.show()
                self.notice.configure(text='트레이 연결 실패 · ⋯ 메뉴에서 종료 가능')
        if not self.tray.registered and time.monotonic() >= self.next_tray_retry:
            self.tray.ensure_registered()
            self.next_tray_retry = time.monotonic()+5
        self.tray_job = self.root.after(100, self.process_tray_events)

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
                self.notice.configure(text=DEFAULT_NOTICE)
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
            detail.configure(text=view['detail'])
            button.configure(text=view['switch'], state='disabled' if self.busy or view['disabled'] else 'normal')
        if not self.busy and time.monotonic() >= self.next_poll:
            self.submit(self.client.snapshot)
        self.tick_job = self.root.after(250, self.tick)

    def close(self):
        """Exit only this widget; no automation switches or processes are touched."""
        if self.closed:
            return
        for job in (self.opacity_save_job, self.tick_job, self.tray_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except self.tk.TclError:
                    pass
        if self.opacity_save_job is not None:
            self.persist_opacity()
        self.closed = True
        self.tray.close()
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
