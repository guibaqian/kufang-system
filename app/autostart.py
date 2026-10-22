# -*- coding: utf-8 -*-
"""开机自动启动：写注册表 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run（只对当前用户，不要管理员，不用 COM / PowerShell）。
启动命令：pythonw.exe "...\\app\\launcher.py" --background （后台、无窗口、不弹浏览器）。
单实例：launcher 用命名互斥量，所以注册表 + 启动文件夹里的快捷方式同时存在也只会跑一个。"""
import os, sys, glob, ntpath

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE = 'WarehouseSystem'
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IS_WIN = os.name == 'nt'

def pythonw():
    """优先用便携版自带的 python\\pythonw.exe，其次当前解释器旁边的 pythonw.exe"""
    for p in (ntpath.join(ROOT, 'python', 'pythonw.exe'), ntpath.join(os.path.dirname(sys.executable), 'pythonw.exe')):
        if os.path.exists(p): return p
    return sys.executable

def command():
    return '"%s" "%s" --background' % (pythonw(), ntpath.join(HERE, 'launcher.py'))  # 两段都加引号：路径里有中文、空格、括号都没问题

def _reg():
    import winreg
    return winreg

def current():
    """注册表里现在的值（没有 = None）"""
    if not IS_WIN: return None
    w = _reg()
    try:
        with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_READ) as k:
            return w.QueryValueEx(k, VALUE)[0]
    except OSError:
        return None

def startup_shortcuts():
    """「启动」文件夹里指向本系统的快捷方式（以前的版本或手工放的）。只列出，不动它们。"""
    if not IS_WIN: return []
    d = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
    out = []
    for f in glob.glob(os.path.join(d, '*.lnk')):
        n = os.path.basename(f)
        try: body = open(f, 'rb').read()
        except OSError: body = b''
        hit = any(x in body for x in ('launcher.py'.encode('utf-16-le'), b'launcher.py', '启动.bat'.encode('utf-16-le'), '库房'.encode('utf-16-le')))
        if hit or '库房' in n or 'arehouse' in n: out.append(f)
    return out

def status():
    cur = current()
    return {'supported': IS_WIN, 'on': bool(cur), 'command': cur or '', 'expected': command() if IS_WIN else '',
            'stale': bool(cur) and cur != command(), 'shortcuts': startup_shortcuts()}

def install():
    if not IS_WIN: raise RuntimeError('只有 Windows 能设置开机自动启动')
    w = _reg()
    with w.CreateKey(w.HKEY_CURRENT_USER, RUN_KEY) as k:
        w.SetValueEx(k, VALUE, 0, w.REG_SZ, command())
    return status()

def remove():
    if not IS_WIN: raise RuntimeError('只有 Windows 能设置开机自动启动')
    w = _reg()
    try:
        with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_SET_VALUE) as k:
            w.DeleteValue(k, VALUE)
    except FileNotFoundError:
        pass
    return status()

def report(st):
    lines = []
    if st['on']: lines.append('开机自动启动：已开启（开机后在后台运行，右下角托盘有图标，不弹浏览器）。')
    else: lines.append('开机自动启动：已关闭。')
    if st['shortcuts']:
        lines.append('另外，「启动」文件夹里还有快捷方式：')
        lines += ['    ' + s for s in st['shortcuts']]
        lines.append('可以留着（系统只会运行一个，不会重复启动），也可以删掉，开机启动由上面这一项负责。')
    return '\n'.join(lines)
