"""Windows notification-area icon with a dedicated Win32 message thread.

Only strings are sent to the provided Queue. Tk is never called from this thread.
Uses Shell_NotifyIconW and a hidden top-level window so Explorer's TaskbarCreated
broadcast can restore the icon after Explorer restarts. No third-party packages.
"""
from __future__ import annotations

import os
import threading


class WindowsTray:
    def __init__(self, events):
        self.events = events
        self.registered = False
        self.window = None
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.thread = None
        self.user32 = None

    def start(self):
        if os.name != 'nt':
            self.ready.set()
            return False
        if not self.thread:
            self.thread = threading.Thread(target=self._run, name='automation-tray', daemon=True)
            self.thread.start()
        return self.registered

    def ensure_registered(self):
        if not self.registered and self.window and self.user32 and not self.stopping.is_set():
            self.user32.PostMessageW(self.window, 0x8002, 0, 0)
        return self.registered

    def close(self):
        self.stopping.set()
        if self.window and self.user32:
            self.user32.PostMessageW(self.window, 0x0010, 0, 0)  # WM_CLOSE
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def _run(self):
        import ctypes as ct
        from ctypes import wintypes as wt

        user32 = ct.WinDLL('user32', use_last_error=True)
        shell32 = ct.WinDLL('shell32', use_last_error=True)
        kernel32 = ct.WinDLL('kernel32', use_last_error=True)
        self.user32 = user32
        LRESULT = ct.c_ssize_t
        WNDPROC = ct.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

        class GUID(ct.Structure):
            _fields_ = [('Data1', wt.DWORD), ('Data2', wt.WORD), ('Data3', wt.WORD), ('Data4', wt.BYTE * 8)]

        class NOTIFYICONDATAW(ct.Structure):
            _fields_ = [('cbSize', wt.DWORD), ('hWnd', wt.HWND), ('uID', wt.UINT),
                        ('uFlags', wt.UINT), ('uCallbackMessage', wt.UINT), ('hIcon', wt.HICON),
                        ('szTip', wt.WCHAR * 128), ('dwState', wt.DWORD), ('dwStateMask', wt.DWORD),
                        ('szInfo', wt.WCHAR * 256), ('uVersion', wt.UINT), ('szInfoTitle', wt.WCHAR * 64),
                        ('dwInfoFlags', wt.DWORD), ('guidItem', GUID), ('hBalloonIcon', wt.HICON)]

        class WNDCLASSW(ct.Structure):
            _fields_ = [('style', wt.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ct.c_int),
                        ('cbWndExtra', ct.c_int), ('hInstance', wt.HINSTANCE), ('hIcon', wt.HICON),
                        ('hCursor', wt.HANDLE), ('hbrBackground', wt.HBRUSH),
                        ('lpszMenuName', wt.LPCWSTR), ('lpszClassName', wt.LPCWSTR)]

        signatures = {
            'DefWindowProcW': ([wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], LRESULT),
            'RegisterClassW': ([ct.POINTER(WNDCLASSW)], wt.ATOM),
            'UnregisterClassW': ([wt.LPCWSTR, wt.HINSTANCE], wt.BOOL),
            'CreateWindowExW': ([wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ct.c_int, ct.c_int,
                                 ct.c_int, ct.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID], wt.HWND),
            'DestroyWindow': ([wt.HWND], wt.BOOL),
            'IsWindow': ([wt.HWND], wt.BOOL),
            'LoadIconW': ([wt.HINSTANCE, ct.c_void_p], wt.HICON),
            'RegisterWindowMessageW': ([wt.LPCWSTR], wt.UINT),
            'GetMessageW': ([ct.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT], wt.BOOL),
            'TranslateMessage': ([ct.POINTER(wt.MSG)], wt.BOOL),
            'DispatchMessageW': ([ct.POINTER(wt.MSG)], LRESULT),
            'PostMessageW': ([wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], wt.BOOL),
            'PostQuitMessage': ([ct.c_int], None),
            'CreatePopupMenu': ([], wt.HMENU),
            'AppendMenuW': ([wt.HMENU, wt.UINT, ct.c_size_t, wt.LPCWSTR], wt.BOOL),
            'SetMenuDefaultItem': ([wt.HMENU, wt.UINT, wt.UINT], wt.BOOL),
            'DestroyMenu': ([wt.HMENU], wt.BOOL),
            'GetCursorPos': ([ct.POINTER(wt.POINT)], wt.BOOL),
            'SetForegroundWindow': ([wt.HWND], wt.BOOL),
            'TrackPopupMenu': ([wt.HMENU, wt.UINT, ct.c_int, ct.c_int, ct.c_int, wt.HWND, wt.LPVOID], wt.UINT),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(user32, name)
            function.argtypes, function.restype = arguments, result
        kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wt.HMODULE
        shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ct.POINTER(NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wt.BOOL
        instance = kernel32.GetModuleHandleW(None)
        class_name = f'AutomationLiveTray.{os.getpid()}.{threading.get_ident()}'
        created_message = user32.RegisterWindowMessageW('TaskbarCreated')
        icon = NOTIFYICONDATAW()
        icon.cbSize = ct.sizeof(NOTIFYICONDATAW)
        icon.uID = 1
        icon.uFlags = 0x01 | 0x02 | 0x04 | 0x80  # message, icon, tooltip, show-tooltip
        icon.uCallbackMessage = 0x8001
        # A shared system icon needs no DestroyIcon call.
        icon.hIcon = user32.LoadIconW(None, ct.c_void_p(32516))
        icon.szTip = '자동화 LIVE · 더블 클릭으로 열기 · 우클릭으로 종료'
        registered_class = False

        def add_icon():
            if self.stopping.is_set():
                return
            self.registered = bool(shell32.Shell_NotifyIconW(0, ct.byref(icon)))
            if self.registered:
                icon.uVersion = 4
                shell32.Shell_NotifyIconW(4, ct.byref(icon))
            else:
                self.events.put('unavailable')

        def menu():
            handle = user32.CreatePopupMenu()
            if not handle:
                self.events.put('open')
                return
            try:
                user32.AppendMenuW(handle, 0, 1, '현황판 열기')
                user32.AppendMenuW(handle, 0x800, 0, None)
                user32.AppendMenuW(handle, 0, 2, '현황판 종료 (자동화 유지)')
                user32.SetMenuDefaultItem(handle, 1, 0)
                point = wt.POINT()
                user32.GetCursorPos(ct.byref(point))
                user32.SetForegroundWindow(self.window)
                # Return command ID synchronously; no Tk calls inside the callback.
                choice = user32.TrackPopupMenu(handle, 0x100 | 0x02, point.x, point.y, 0, self.window, None)
                if choice == 1:
                    self.events.put('open')
                elif choice == 2:
                    self.events.put('exit')
                user32.PostMessageW(self.window, 0, 0, 0)
                shell32.Shell_NotifyIconW(3, ct.byref(icon))
            finally:
                user32.DestroyMenu(handle)

        @WNDPROC
        def procedure(hwnd, message, wparam, lparam):
            try:
                if message == created_message or message == 0x8002:
                    if message == created_message:
                        self.registered = False
                    if not self.registered:
                        add_icon()
                    return 0
                if message == 0x8001:
                    event = lparam & 0xFFFF
                    if event in (0x0203, 0x0400, 0x0401):  # double-click, select, keyboard select
                        self.events.put('open')
                    elif event in (0x007B, 0x0205):  # context menu, legacy right-button-up
                        menu()
                    return 0
                if message == 0x0010:
                    shell32.Shell_NotifyIconW(2, ct.byref(icon))
                    self.registered = False
                    user32.DestroyWindow(hwnd)
                    return 0
                if message == 0x0002:
                    user32.PostQuitMessage(0)
                    return 0
            except Exception:
                self.events.put('unavailable')
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        try:
            window_class = WNDCLASSW()
            window_class.lpfnWndProc = procedure
            window_class.hInstance = instance
            window_class.lpszClassName = class_name
            if not user32.RegisterClassW(ct.byref(window_class)):
                raise OSError('tray class unavailable')
            registered_class = True
            self.window = user32.CreateWindowExW(0, class_name, 'Automation LIVE tray', 0,
                                                  0, 0, 0, 0, None, None, instance, None)
            if not self.window:
                raise OSError('tray window unavailable')
            icon.hWnd = self.window
            add_icon()
            self.ready.set()
            message = wt.MSG()
            while not self.stopping.is_set():
                result = user32.GetMessageW(ct.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ct.byref(message))
                user32.DispatchMessageW(ct.byref(message))
        except Exception:
            self.events.put('unavailable')
        finally:
            self.registered = False
            self.ready.set()
            if self.window:
                shell32.Shell_NotifyIconW(2, ct.byref(icon))
                if user32.IsWindow(self.window):
                    user32.DestroyWindow(self.window)
                self.window = None
            if registered_class:
                user32.UnregisterClassW(class_name, instance)
