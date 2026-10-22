"""开机自动启动（注册表 Run，用假的 winreg 测）和 .bat 文件编码。python -m unittest tests.test_autostart -v"""
import os, sys, io, re, glob, unittest, contextlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
import autostart, launcher

class FakeReg:
    HKEY_CURRENT_USER = 'HKCU'; KEY_READ = 1; KEY_SET_VALUE = 2; REG_SZ = 1
    def __init__(self): self.d = {}
    @contextlib.contextmanager
    def OpenKey(self, root, path, res=0, acc=0): yield path
    @contextlib.contextmanager
    def CreateKey(self, root, path): yield path
    def QueryValueEx(self, k, n):
        if (k, n) not in self.d: raise FileNotFoundError(n)
        return self.d[(k, n)], 1
    def SetValueEx(self, k, n, r, t, v): self.d[(k, n)] = v
    def DeleteValue(self, k, n):
        if (k, n) not in self.d: raise FileNotFoundError(n)
        del self.d[(k, n)]

class A1_Registry(unittest.TestCase):
    def setUp(self):
        self.reg = FakeReg(); self.o = (autostart.IS_WIN, autostart._reg, autostart.startup_shortcuts, autostart.HERE, autostart.ROOT)
        autostart.IS_WIN = True; autostart._reg = lambda: self.reg; autostart.startup_shortcuts = lambda: []
        autostart.ROOT = r'C:\Users\王 二\桌面\库房 (新)\库房出入库系统'; autostart.HERE = autostart.ROOT + r'\app'
    def tearDown(self): autostart.IS_WIN, autostart._reg, autostart.startup_shortcuts, autostart.HERE, autostart.ROOT = self.o

    def test_install_remove_status(self):
        self.assertFalse(autostart.status()['on'])
        st = autostart.install(); self.assertTrue(st['on']); self.assertFalse(st['stale'])
        cmd = self.reg.d[(autostart.RUN_KEY, 'WarehouseSystem')]
        self.assertTrue(cmd.endswith(r'\app\launcher.py" --background'), cmd)
        self.assertIn(r'"C:\Users\王 二\桌面\库房 (新)\库房出入库系统\app\launcher.py"', cmd)   # 中文、空格、括号路径整体加引号
        self.assertTrue(cmd.startswith('"') and cmd.count('"') == 4)
        autostart.install(); self.assertEqual(len(self.reg.d), 1)                 # 重复设置不重复写
        autostart.ROOT = r'D:\搬家后'; autostart.HERE = r'D:\搬家后\app'
        self.assertTrue(autostart.status()['stale'])                             # 文件夹搬了，提示重新设置
        st = autostart.remove(); self.assertFalse(st['on']); self.assertEqual(self.reg.d, {})
        autostart.remove()                                                        # 没有也不报错

    def test_cli_and_report(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): rc = launcher.main(['--install-autostart'])
        self.assertEqual(rc, 0); self.assertIn('已开启', out.getvalue())
        autostart.startup_shortcuts = lambda: [r'C:\Users\x\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\库房.lnk']
        out = io.StringIO()
        with contextlib.redirect_stdout(out): launcher.main(['--autostart-status'])
        self.assertIn('不会重复启动', out.getvalue()); self.assertIn('库房.lnk', out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out): launcher.main(['--remove-autostart'])
        self.assertIn('已关闭', out.getvalue())

    def test_non_windows(self):
        autostart.IS_WIN = False
        self.assertFalse(autostart.status()['supported'])
        with self.assertRaises(RuntimeError): autostart.install()

class A2_Bat(unittest.TestCase):
    def test_bat_files(self):
        names = sorted(os.path.basename(f) for f in glob.glob(os.path.join(ROOT, '*.bat')))
        self.assertEqual(names, sorted(['启动.bat', '停止系统.bat', '允许手机访问_防火墙.bat', '开机自动启动.bat', '取消开机自动启动.bat']))
        for n in names:
            b = open(os.path.join(ROOT, n), 'rb').read()
            self.assertNotIn(b'\xef\xbb\xbf', b[:3], n)
            self.assertEqual(b.count(b'\n'), b.count(b'\r\n'), n + ' 要用 CRLF')
            t = b.decode('gbk')
            self.assertNotIn('chcp', t.lower(), n)
            self.assertNotIn('CreateShortcut', t, n)
            for ln in t.splitlines():
                s = ln.strip()
                if not s or s.lower().startswith(('rem ', 'echo ', 'echo.')): continue
                self.assertTrue(all(ord(ch) < 128 for ch in s), '%s 命令行里有中文：%s' % (n, s))
                if '%~dp0' in s: self.assertNotRegex(s, r'^\s*if .*\(|^\)', '%s：%%~dp0 不要放在 ( ) 块里' % n)
        a = open(os.path.join(ROOT, '开机自动启动.bat'), 'rb').read().decode('gbk')
        self.assertIn('--install-autostart', a)
        self.assertIn('--remove-autostart', open(os.path.join(ROOT, '取消开机自动启动.bat'), 'rb').read().decode('gbk'))

if __name__ == '__main__': unittest.main()
