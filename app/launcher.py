# -*- coding: utf-8 -*-
"""库房出入库系统 · 后台启动器（Windows 上用 pythonw.exe 跑，没有黑窗口）
  pythonw app\launcher.py               启动（首次开浏览器；已在运行则安静退出，不再 startfile）
  pythonw app\launcher.py --background  开机自启用：不自动打开浏览器
  pythonw app\launcher.py --no-browser  热更/部署重启用：起服务但不强制开新首页
  pythonw app\launcher.py --open        已在运行时也打开浏览器（等同托盘「打开系统」）
  python  app/launcher.py --no-tray      其他系统 / 调试：不建托盘
做的事：日志写 data/logs/server.log（自动轮换）；单实例；Windows 托盘图标（打开系统 / 显示手机地址 / 退出）；
万一用了控制台窗口，关掉「快速编辑模式」，避免点一下窗口就把服务卡住。"""
import sys, os, io, json, time, threading, socket, traceback, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
# 嵌入式 Python 有 ._pth 文件时不会把脚本所在目录加进 sys.path，这里自己加
for p in (HERE, os.path.join(HERE, 'vendor')):
    if p not in sys.path: sys.path.insert(0, p)
IS_WIN = sys.platform == 'win32'
BASE = os.path.dirname(HERE)
DATA = os.environ.get('WH_DATA') or os.path.join(BASE, 'data')
LOG_DIR = os.path.join(DATA, 'logs')
RUN_FILE = os.path.join(LOG_DIR, 'running.json')
MUTEX_NAME = 'Local\\KufangChurukuXitong_8f2c'

# ---------------- 日志：stdout/stderr → 轮换文件（没有控制台时也绝不阻塞） ----------------
class LogStream(io.TextIOBase):
    """把 print / traceback 写到轮换日志；有控制台时也照样输出到控制台（控制台写失败就忽略）"""
    def __init__(self, handler, orig=None):
        self.h = handler; self.orig = orig; self.buf = ''; self.lock = threading.Lock()
    stamped = True   # 日志自带时间，server.log_message 不再重复加
    def writable(self): return True
    @property
    def encoding(self): return 'utf-8'
    def write(self, s):
        if not isinstance(s, str): s = str(s)
        if self.orig is not None:
            try: self.orig.write(s); self.orig.flush()
            except Exception: pass
        with self.lock:
            self.buf += s
            if '\n' in self.buf:
                lines, self.buf = self.buf.rsplit('\n', 1)
                self._emit(lines)
        return len(s)
    def _emit(self, text):
        import logging
        try: self.h.emit(logging.LogRecord('wh', logging.INFO, '', 0, text, None, None))
        except Exception: pass
    def flush(self):
        with self.lock:
            if self.buf: self._emit(self.buf); self.buf = ''
    def isatty(self): return False

def setup_logging():
    import logging, logging.handlers
    os.makedirs(LOG_DIR, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(LOG_DIR, 'server.log'), maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8', delay=True)
    h.setFormatter(logging.Formatter('%(asctime)s %(message)s', '%Y-%m-%d %H:%M:%S'))
    # pythonw 下 sys.stdout / sys.stderr 是 None：直接替换；有控制台时“双写”
    sys.stdout = LogStream(h, sys.stdout if _usable(sys.stdout) else None)
    sys.stderr = LogStream(h, sys.stderr if _usable(sys.stderr) else None)
    return h

def _usable(f):
    if f is None: return False
    try: f.write(''); return True
    except Exception: return False

def disable_quickedit():
    """控制台的「快速编辑模式」：用户点一下窗口（标题出现「选择」）后，所有输出被挂起，服务跟着卡死。关掉它。"""
    if not IS_WIN: return False
    try:
        import ctypes
        from ctypes import wintypes as W
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.GetConsoleWindow.restype = W.HWND; k.GetConsoleWindow.argtypes = []
        if not k.GetConsoleWindow(): return False
        k.GetStdHandle.restype = W.HANDLE; k.GetStdHandle.argtypes = [W.DWORD]
        k.GetConsoleMode.restype = W.BOOL; k.GetConsoleMode.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        k.SetConsoleMode.restype = W.BOOL; k.SetConsoleMode.argtypes = [W.HANDLE, W.DWORD]
        h = k.GetStdHandle(ctypes.c_ulong(-10 & 0xFFFFFFFF).value)   # STD_INPUT_HANDLE
        m = W.DWORD()
        if not k.GetConsoleMode(h, ctypes.byref(m)): return False
        ENABLE_QUICK_EDIT_MODE, ENABLE_EXTENDED_FLAGS, ENABLE_INSERT_MODE = 0x40, 0x80, 0x20
        return bool(k.SetConsoleMode(h, (m.value | ENABLE_EXTENDED_FLAGS) & ~(ENABLE_QUICK_EDIT_MODE | ENABLE_INSERT_MODE)))
    except Exception:
        return False

# ---------------- 单实例 ----------------
_mutex = None
def acquire_single():
    """True = 我是第一个；False = 已经有一个在跑。Windows 用命名互斥量；其他系统靠端口判断（见 main）"""
    global _mutex
    if not IS_WIN: return True
    import ctypes
    from ctypes import wintypes as W
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.CreateMutexW.restype = W.HANDLE; k.CreateMutexW.argtypes = [W.LPVOID, W.BOOL, W.LPCWSTR]
    _mutex = k.CreateMutexW(None, False, MUTEX_NAME)
    return not (_mutex and ctypes.get_last_error() == 183)   # ERROR_ALREADY_EXISTS

def known_port():
    try: return int(json.load(open(RUN_FILE, encoding='utf-8'))['port'])
    except Exception: return int(os.environ.get('WH_PORT') or 8080)

def is_ours(port, timeout=2.0):
    """这个端口上跑的是不是本系统（不管新版旧版）"""
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/ping' % port, timeout=timeout) as r:
            return 'Warehouse' in (r.headers.get('Server') or '')
    except urllib.error.HTTPError as e:
        return 'Warehouse' in (e.headers.get('Server') or '')
    except Exception:
        return False

def open_browser(port, path='/'):
    url = 'http://127.0.0.1:%d%s' % (port, path)
    try:
        if IS_WIN: os.startfile(url)
        else:
            import webbrowser; webbrowser.open(url)
    except Exception as e:
        print('打不开浏览器：', e)

def _ver():
    try:
        import version; return version.VERSION
    except Exception: return ''

def phone_text(server):
    us = server.lan_urls()
    lines = ['手机连上库房 WiFi 后，用浏览器打开：', ''] + ['    %s/m/' % u for u in us]
    lines += ['', '访客借用登记（不用密码）：', ''] + ['    %s/m/guest' % u for u in us[:1]]
    lines += ['', '电脑上打开系统 →「设置 → 手机与访客二维码」也能看到这些地址和二维码。', '手机打不开：右键「允许手机访问_防火墙.bat」→ 以管理员身份运行一次。']
    return '\n'.join(lines)

def wait_up(port, sec=60):
    t = time.time()
    while time.time() - t < sec:
        if is_ours(port, 1.0): return True
        time.sleep(0.3)
    return False

# ---------------- 主流程 ----------------
def autostart_cli(opt):
    """给 开机自动启动.bat / 取消开机自动启动.bat 用：结果打印到窗口（不写日志、不启动服务）"""
    import autostart
    try:
        st = {'--install-autostart': autostart.install, '--remove-autostart': autostart.remove, '--autostart-status': autostart.status}[opt]()
        print(autostart.report(st)); sys.stdout.flush(); return 0
    except Exception as e:
        print('设置失败：%s' % e); sys.stdout.flush(); return 1

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for opt in ('--install-autostart', '--remove-autostart', '--autostart-status'):
        if opt in argv: return autostart_cli(opt)
    background = '--background' in argv; no_browser = background or '--no-browser' in argv
    force_open = '--open' in argv   # 显式要求开浏览器（热更默认不开；已在跑也不默认开）
    use_tray = IS_WIN and '--no-tray' not in argv
    setup_logging(); disable_quickedit()
    print('---- 启动 %s（pid %d，%s）----' % (sys.executable, os.getpid(), ' '.join(argv)))
    import wintray
    if not acquire_single():
        # 已在运行：默认不再 startfile（避免热更/重复双击抢焦点开新首页）；要开窗用托盘或 --open
        port = known_port()
        if force_open and not no_browser:
            print('已经在运行，按 --open 打开浏览器 :%d' % port)
            wait_up(port, 20); open_browser(port)
        else:
            print('已经在运行 :%d（不再打开浏览器；托盘右键「打开系统」或加 --open）' % port)
        return 0
    tray = None
    if use_tray:
        try:
            tray = wintray.Tray('库房出入库系统 v%s（正在启动…）' % _ver(), [], icon_path=os.path.join(HERE, 'tray.ico'))
        except Exception:
            print('托盘图标创建失败，改为无图标后台运行：'); traceback.print_exc(); tray = None
    state = {'srv': None, 'server': None}

    def boot():
        try:
            import server
            state['server'] = server
            try: srv = server.create_server()
            except OSError as e:
                port = server.PORT
                if is_ours(port):   # 端口上已经是本系统（比如旧版黑窗口还开着）
                    print('端口 %d 上已有本系统在运行（可能是旧版窗口），打开它' % port)
                    if not no_browser: open_browser(port)
                    if tray: tray.balloon('库房出入库系统', '系统已经在运行（可能是旧版黑色窗口）。如要换成新版，请先关掉旧窗口再双击「启动.bat」。')
                    time.sleep(1.5); _stop(); return
                raise RuntimeError('端口 %d 被别的程序占用，系统没能启动。\n（%s）\n\n可以在电脑上关掉占用 %d 端口的程序后再双击「启动.bat」。' % (port, e, port))
            state['srv'] = srv
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
                json.dump({'port': server.PORT, 'pid': os.getpid(), 'started': time.time()}, open(RUN_FILE, 'w', encoding='utf-8'))
            except Exception: pass
            if not os.environ.get('WH_NO_AUTOBACKUP'): server.backup.start_auto()
            server.banner()
            threading.Thread(target=srv.serve_forever, name='http', daemon=True).start()
            if tray:
                tray.set_tip('库房出入库系统 v%s · 运行中 :%d' % (_ver(), server.PORT))
                tray.balloon('库房出入库系统 已在后台运行', '右下角这个图标：右键 → 打开系统 / 显示手机地址 / 退出。\n不用管它，关浏览器不影响使用。')
            if not no_browser: open_browser(server.PORT)
        except Exception as e:
            traceback.print_exc()
            wintray.message_box('库房出入库系统没能启动：\n\n%s\n\n详细记录在 %s' % (e, os.path.join(LOG_DIR, 'server.log')), flags=wintray.MB_ICONERROR)
            _stop()

    def _stop():
        if tray: tray.quit()
        else: done.set()

    def do_open():
        if state['server']: open_browser(state['server'].PORT)
    def do_phone():
        if state['server']: wintray.message_box(phone_text(state['server']), '手机访问地址')
        else: wintray.message_box('系统还在启动，请稍等几秒再试。')
    def do_quit():
        if wintray.message_box('退出后，电脑和手机都打不开库房系统（数据不会丢）。\n\n确定退出？', '退出库房系统', wintray.MB_YESNO | wintray.MB_ICONQUESTION) == wintray.IDYES:
            tray.quit()

    done = threading.Event()
    threading.Thread(target=boot, name='boot', daemon=True).start()
    if tray:
        tray.menu[:] = [('打开系统', do_open), ('显示手机地址', do_phone), None, ('退出', do_quit)]
        tray.run()   # 阻塞到退出
    else:
        try:
            while not done.wait(1): pass
        except KeyboardInterrupt: pass
    srv = state['srv']
    if srv:
        print('正在停止…')
        try: srv.shutdown(); srv.server_close()
        except Exception: pass
        try: os.remove(RUN_FILE)
        except Exception: pass
    print('---- 已退出 ----'); sys.stdout.flush(); sys.stderr.flush()
    return 0

if __name__ == '__main__':
    try: rc = main()
    except SystemExit: raise
    except BaseException:
        try: traceback.print_exc()
        except Exception: pass
        rc = 1
    os._exit(rc or 0)   # 不等后台线程
