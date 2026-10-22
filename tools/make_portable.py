"""打便携版：把 Windows 嵌入式 Python 和程序打成一个 zip，拷到主机解压即用（主机不用装任何东西、不用联网）。
用法（在任何能联网的电脑上跑一次）：python tools/make_portable.py
  - 会下载 python-3.12.10-embed-amd64.zip（约 11MB，官方 python.org），也可先手动下载放到 tools/ 下
  - 输出 dist/库房出入库系统_便携版.zip（整包），以及两个各小于 25MB 的分包（解压到同一位置会合并成一个文件夹）：
      dist/库房系统_第1包_程序.zip（不含 python/ 和数据）、dist/库房系统_第2包_运行环境.zip（只有 python/）
注意：Python 3.12 需要 Windows 8.1/10/11（不支持 Windows 7）。"""
import os, sys, zipfile, urllib.request, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VER = '3.12.10'; NAME = 'python-%s-embed-amd64.zip' % VER
URL = 'https://www.python.org/ftp/python/%s/%s' % (VER, NAME)
TOP = '库房出入库系统/'
SKIP_DIRS = {'__pycache__', 'dist', 'data', 'screens', 'tools', '.pytest_cache', '.git'}
DATA_NOTE = '数据都在这个文件夹（warehouse.db + photos）。备份请用系统里的「数据备份」。\r\n升级时解压新版本覆盖程序文件即可，这个文件夹里的数据不会被覆盖。\r\n'.encode('utf-8')
LIMIT = 25 * 1024 * 1024

def program_files():
    """程序文件（不含 python/、data/、测试、截图、打包工具）"""
    for d, ds, fs in os.walk(ROOT):
        rel = os.path.relpath(d, ROOT)
        ds[:] = sorted(x for x in ds if x not in SKIP_DIRS and not (rel == '.' and x in ('tests', 'python')))
        for f in sorted(fs):
            if rel == '.' and f.endswith(('.pyc', '.jpg', '.docx', '.zip')): continue
            if f.endswith(('.pyc', '.db', '.db-wal', '.db-shm')): continue
            p = os.path.join(d, f); yield p, TOP + os.path.relpath(p, ROOT).replace(os.sep, '/')

def python_files(local):
    with zipfile.ZipFile(local) as e:
        for i in e.infolist():
            data = e.read(i)
            if i.filename.endswith('._pth'):  # 允许 import site（不需要 pip，留着方便以后）
                data = data.replace(b'#import site', b'import site')
            yield TOP + 'python/' + i.filename, data

def main():
    local = os.path.join(ROOT, 'tools', NAME)
    if not os.path.isfile(local):
        print('下载', URL); urllib.request.urlretrieve(URL, local)
    dist = os.path.join(ROOT, 'dist'); os.makedirs(dist, exist_ok=True)
    full = os.path.join(dist, '库房出入库系统_便携版.zip')
    p1 = os.path.join(dist, '库房系统_第1包_程序.zip')
    p2 = os.path.join(dist, '库房系统_第2包_运行环境.zip')
    Z = lambda p: zipfile.ZipFile(p, 'w', zipfile.ZIP_DEFLATED, compresslevel=9)
    with Z(full) as zf, Z(p1) as z1, Z(p2) as z2:
        for p, arc in program_files(): zf.write(p, arc); z1.write(p, arc)
        for arc, data in python_files(local): zf.writestr(arc, data); z2.writestr(arc, data)
        zf.writestr(TOP + 'data/说明.txt', DATA_NOTE)   # 第1包不带 data/（升级时解压覆盖，绝不碰已有数据；新装时程序自己建 data/）
    for p in (full, p1, p2):
        n = os.path.getsize(p); print('完成：', p, '%.1f MB' % (n / 1048576))
    for p in (p1, p2):
        if os.path.getsize(p) >= LIMIT: raise SystemExit('超过 25MB：' + p)
if __name__ == '__main__': main()
