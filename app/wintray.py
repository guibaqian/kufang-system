# -*- coding: utf-8 -*-
"""Windows 托盘图标（纯 ctypes 调 Win32 API，不需要任何第三方库）。
只在 Windows 上 import 后使用；其他系统 import 本模块不会出错，但 Tray() 会抛 OSError。
要点：64 位下句柄/指针都是 8 字节，所有用到的 API 都显式声明 argtypes/restype（否则返回值被截成 32 位）；
WNDPROC 回调对象挂在 self 上一直引用着（否则被回收后窗口过程变成野指针，程序直接崩）。"""
import ctypes, sys, os, threading
from ctypes import wintypes as W

IS_WIN = sys.platform == 'win32'
LRESULT = ctypes.c_ssize_t
HCURSOR = W.HANDLE

if IS_WIN:
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
else:  # 只为在非 Windows 上能定义结构体（测试结构体大小用）
    WNDPROC = ctypes.CFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [('cbSize', W.UINT), ('style', W.UINT), ('lpfnWndProc', WNDPROC), ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                ('hInstance', W.HINSTANCE), ('hIcon', W.HICON), ('hCursor', HCURSOR), ('hbrBackground', W.HBRUSH),
                ('lpszMenuName', W.LPCWSTR), ('lpszClassName', W.LPCWSTR), ('hIconSm', W.HICON)]

class GUID(ctypes.Structure):
    _fields_ = [('Data1', W.DWORD), ('Data2', W.WORD), ('Data3', W.WORD), ('Data4', ctypes.c_ubyte * 8)]

class NOTIFYICONDATAW(ctypes.Structure):   # 完整 Vista+ 版本：x64 下 sizeof = 976
    _fields_ = [('cbSize', W.DWORD), ('hWnd', W.HWND), ('uID', W.UINT), ('uFlags', W.UINT), ('uCallbackMessage', W.UINT), ('hIcon', W.HICON),
                ('szTip', W.WCHAR * 128), ('dwState', W.DWORD), ('dwStateMask', W.DWORD), ('szInfo', W.WCHAR * 256),
                ('uVersion', W.UINT),  # 与 uTimeout 是 union，同大小
                ('szInfoTitle', W.WCHAR * 64), ('dwInfoFlags', W.DWORD), ('guidItem', GUID), ('hBalloonIcon', W.HICON)]

class MSG(ctypes.Structure):
    _fields_ = [('hwnd', W.HWND), ('message', W.UINT), ('wParam', W.WPARAM), ('lParam', W.LPARAM), ('time', W.DWORD), ('pt', W.POINT), ('lPrivate', W.DWORD)]

WM_DESTROY, WM_CLOSE, WM_COMMAND, WM_NULL = 0x0002, 0x0010, 0x0111, 0x0000
WM_QUERYENDSESSION, WM_ENDSESSION = 0x0011, 0x0016
WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0203, 0x0205, 0x007B
WM_APP = 0x8000
WM_TRAY, WM_CALL = WM_APP + 1, WM_APP + 2
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 0x10
NIIF_INFO, NIIF_ERROR = 1, 3
MF_STRING, MF_SEPARATOR = 0, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
IDI_APPLICATION = 32512
MB_OK, MB_YESNO, MB_ICONINFO, MB_ICONERROR, MB_ICONQUESTION = 0, 4, 0x40, 0x10, 0x20
MB_SETFOREGROUND, MB_TOPMOST, IDYES = 0x10000, 0x40000, 6
SM_CXSMICON, SM_CYSMICON = 49, 50

def _api():
    u = ctypes.WinDLL('user32', use_last_error=True); s = ctypes.WinDLL('shell32', use_last_error=True); k = ctypes.WinDLL('kernel32', use_last_error=True)
    def f(dll, name, res, *args):
        fn = getattr(dll, name); fn.restype = res; fn.argtypes = list(args); return fn
    A = type('A', (), {})()
    A.RegisterClassExW = f(u, 'RegisterClassExW', W.ATOM, ctypes.POINTER(WNDCLASSEXW))
    A.CreateWindowExW = f(u, 'CreateWindowExW', W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID)
    A.DefWindowProcW = f(u, 'DefWindowProcW', LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    A.DestroyWindow = f(u, 'DestroyWindow', W.BOOL, W.HWND)
    A.PostQuitMessage = f(u, 'PostQuitMessage', None, ctypes.c_int)
    A.PostMessageW = f(u, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    A.GetMessageW = f(u, 'GetMessageW', W.BOOL, ctypes.POINTER(MSG), W.HWND, W.UINT, W.UINT)
    A.TranslateMessage = f(u, 'TranslateMessage', W.BOOL, ctypes.POINTER(MSG))
    A.DispatchMessageW = f(u, 'DispatchMessageW', LRESULT, ctypes.POINTER(MSG))
    A.RegisterWindowMessageW = f(u, 'RegisterWindowMessageW', W.UINT, W.LPCWSTR)
    A.CreatePopupMenu = f(u, 'CreatePopupMenu', W.HMENU)
    A.AppendMenuW = f(u, 'AppendMenuW', W.BOOL, W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR)
    A.SetMenuDefaultItem = f(u, 'SetMenuDefaultItem', W.BOOL, W.HMENU, W.UINT, W.UINT)
    A.TrackPopupMenu = f(u, 'TrackPopupMenu', W.BOOL, W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.LPVOID)
    A.DestroyMenu = f(u, 'DestroyMenu', W.BOOL, W.HMENU)
    A.GetCursorPos = f(u, 'GetCursorPos', W.BOOL, ctypes.POINTER(W.POINT))
    A.SetForegroundWindow = f(u, 'SetForegroundWindow', W.BOOL, W.HWND)
    A.LoadIconW = f(u, 'LoadIconW', W.HICON, W.HINSTANCE, W.LPVOID)   # 第二参数用 MAKEINTRESOURCE 整数
    A.LoadImageW = f(u, 'LoadImageW', W.HANDLE, W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT)
    A.GetSystemMetrics = f(u, 'GetSystemMetrics', ctypes.c_int, ctypes.c_int)
    A.MessageBoxW = f(u, 'MessageBoxW', ctypes.c_int, W.HWND, W.LPCWSTR, W.LPCWSTR, W.UINT)
    A.Shell_NotifyIconW = f(s, 'Shell_NotifyIconW', W.BOOL, W.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
    A.GetModuleHandleW = f(k, 'GetModuleHandleW', W.HMODULE, W.LPCWSTR)
    return A

_A = None
def api():
    global _A
    if _A is None: _A = _api()
    return _A

def message_box(text, title='库房出入库系统', flags=MB_OK | MB_ICONINFO):
    """弹系统提示框（任何线程都可调用；非 Windows 只打印）"""
    if not IS_WIN:
        print('[%s] %s' % (title, text)); return IDYES
    return api().MessageBoxW(None, text, title, flags | MB_SETFOREGROUND | MB_TOPMOST)

class Tray:
    """menu: [(文字, 回调) 或 None(分隔线)]；第一项为默认项（加粗，双击图标执行）。
    回调在托盘线程里执行（就是调用 run() 的线程）。其他线程要改提示/弹气泡用 call_soon()。"""
    def __init__(self, tip, menu, icon_path=None, on_quit=None):
        if not IS_WIN: raise OSError('托盘只支持 Windows')
        self.A = api(); self.tip = tip; self.menu = menu; self.on_quit = on_quit
        self._calls = []; self._lock = threading.Lock(); self.hwnd = None; self._added = False
        self._proc = WNDPROC(self._wndproc)   # 必须一直引用着
        hinst = self.A.GetModuleHandleW(None)
        wc = WNDCLASSEXW(); wc.cbSize = ctypes.sizeof(WNDCLASSEXW); wc.lpfnWndProc = self._proc; wc.hInstance = hinst
        self._cls = 'KufangTrayWnd_%d' % os.getpid(); wc.lpszClassName = self._cls
        if not self.A.RegisterClassExW(ctypes.byref(wc)): raise ctypes.WinError(ctypes.get_last_error())
        self._wc = wc
        # 普通的隐藏顶层窗口（不 ShowWindow 就一直看不见）；不用 HWND_MESSAGE，因为那种窗口收不到 TaskbarCreated 广播
        self.hwnd = self.A.CreateWindowExW(0, self._cls, '库房出入库系统', 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd: raise ctypes.WinError(ctypes.get_last_error())
        self.WM_TASKBAR = self.A.RegisterWindowMessageW('TaskbarCreated')
        self.hicon = None
        if icon_path and os.path.isfile(icon_path):
            self.hicon = self.A.LoadImageW(None, icon_path, IMAGE_ICON, self.A.GetSystemMetrics(SM_CXSMICON), self.A.GetSystemMetrics(SM_CYSMICON), LR_LOADFROMFILE)
        if not self.hicon: self.hicon = self.A.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        if not self._notify(NIM_ADD): raise OSError('Shell_NotifyIconW(NIM_ADD) 失败')

    def _nid(self, flags):
        n = NOTIFYICONDATAW(); n.cbSize = ctypes.sizeof(NOTIFYICONDATAW); n.hWnd = self.hwnd; n.uID = 1
        n.uFlags = flags; n.uCallbackMessage = WM_TRAY; n.hIcon = self.hicon; n.szTip = self.tip[:127]
        return n
    def _notify(self, op, flags=NIF_MESSAGE | NIF_ICON | NIF_TIP, info=None):
        n = self._nid(flags)
        if info:
            n.uFlags |= NIF_INFO; n.szInfoTitle = info[0][:63]; n.szInfo = info[1][:255]; n.dwInfoFlags = info[2] if len(info) > 2 else NIIF_INFO
        ok = bool(self.A.Shell_NotifyIconW(op, ctypes.byref(n)))
        if op == NIM_ADD: self._added = ok
        if op == NIM_DELETE: self._added = False
        return ok

    # ---- 线程安全的接口 ----
    def call_soon(self, fn):
        with self._lock: self._calls.append(fn)
        if self.hwnd: self.A.PostMessageW(self.hwnd, WM_CALL, 0, 0)
    def set_tip(self, tip):
        def f(): self.tip = tip; self._notify(NIM_MODIFY)
        self.call_soon(f)
    def balloon(self, title, text, error=False):
        self.call_soon(lambda: self._notify(NIM_MODIFY, info=(title, text, NIIF_ERROR if error else NIIF_INFO)))
    def quit(self):
        self.call_soon(lambda: self.A.DestroyWindow(self.hwnd))

    # ---- 托盘线程 ----
    def _show_menu(self):
        m = self.A.CreatePopupMenu()
        try:
            for i, it in enumerate(self.menu):
                if it is None: self.A.AppendMenuW(m, MF_SEPARATOR, 0, None)
                else: self.A.AppendMenuW(m, MF_STRING, 1000 + i, it[0])
            self.A.SetMenuDefaultItem(m, 1000, 0)
            pt = W.POINT(); self.A.GetCursorPos(ctypes.byref(pt))
            self.A.SetForegroundWindow(self.hwnd)   # 否则点菜单外面菜单不消失
            cmd = self.A.TrackPopupMenu(m, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0, self.hwnd, None)
            self.A.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally: self.A.DestroyMenu(m)
        if cmd >= 1000 and self.menu[cmd - 1000]: self._safe(self.menu[cmd - 1000][1])
    def _safe(self, fn):
        try: fn()
        except Exception:
            import traceback; traceback.print_exc()
    def _wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == WM_TRAY:
                ev = lp & 0xFFFF
                if ev in (WM_RBUTTONUP, WM_LBUTTONUP, WM_CONTEXTMENU): self._show_menu()
                elif ev == WM_LBUTTONDBLCLK and self.menu and self.menu[0]: self._safe(self.menu[0][1])
                return 0
            if msg == WM_CALL:
                with self._lock: calls, self._calls = self._calls, []
                for fn in calls: self._safe(fn)
                return 0
            if msg == self.WM_TASKBAR and self.WM_TASKBAR:   # 资源管理器重启后图标会丢，重新加
                self._notify(NIM_ADD); return 0
            if msg == WM_QUERYENDSESSION: return 1
            if msg == WM_ENDSESSION:
                if wp: self._notify(NIM_DELETE)
                return 0
            if msg == WM_CLOSE:
                self.A.DestroyWindow(hwnd); return 0
            if msg == WM_DESTROY:
                self._notify(NIM_DELETE); self.A.PostQuitMessage(0); return 0
        except Exception:
            import traceback; traceback.print_exc()
        return self.A.DefWindowProcW(hwnd, msg, wp, lp)

    def run(self):
        """消息循环（阻塞，直到 quit() 或窗口被销毁）"""
        msg = MSG()
        while True:
            r = self.A.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if r == 0 or r == -1: break
            self.A.TranslateMessage(ctypes.byref(msg)); self.A.DispatchMessageW(ctypes.byref(msg))
        if self._added: self._notify(NIM_DELETE)
        if self.on_quit: self._safe(self.on_quit)
