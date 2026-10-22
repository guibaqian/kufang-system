# -*- coding: utf-8 -*-
"""1.1.27（版本断言随当前基线）：全局 UX 同规格 — 占位符不回显原名；看大图旋转立刻保存全入口。"""
import os, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..')

class UxBatch1127(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def r(*p):
            return open(os.path.join(ROOT, *p), encoding='utf-8').read()
        cls.ver = r('app', 'version.py')
        cls.vj = r('static', 'v.json')
        cls.sys = r('static', 'p_sys.js')
        cls.rep = r('static', 'p_report.js')
        cls.core = r('static', 'core.js')
        cls.mcss = r('static', 'm', 'm.css')
        cls.mhtml = r('static', 'm', 'index.html')

    def test_version(self):
        self.assertIn("VERSION = '1.1.28'", self.ver)
        self.assertIn('1.1.28', self.vj)
        self.assertIn("'version': '1.1.28'", self.ver)

    def test_nav_placeholder_no_echo(self):
        self.assertIn('placeholder="改显示名…"', self.sys)
        self.assertIn('navVal', self.sys)
        bad = "placeholder=\"${esc(lab === '产品出入库情况' ? '日表' : lab)}\""
        self.assertNotIn(bad, self.sys)
        nav = self.sys.split('SET_FN.nav')[1].split('SET_FN.reportcols')[0]
        self.assertNotIn('placeholder="设置"', nav)

    def test_names_and_report_col_placeholder(self):
        self.assertIn('placeholder="改显示名…"', self.sys)
        self.assertIn('placeholder="改列名…"', self.rep)
        self.assertIn('colVal', self.rep)
        self.assertNotIn('placeholder="${esc(rFullLabel(k, c))}"', self.rep)

    def test_photo_rotate_shared(self):
        self.assertIn("api('/api/photo/rotate'", self.core)
        self.assertIn('转 90°（马上保存）', self.core)
        self.assertIn('base(x) === base(src)', self.core)
        self.assertIn('.rec', self.core)
        self.assertIn('/core.js', self.mhtml)
        self.assertIn('.iv-ov', self.mcss)

    def test_daily_nav_and_preserve_still_there(self):
        daily = open(os.path.join(ROOT, 'static', 'p_daily.js'), encoding='utf-8').read()
        self.assertIn('dNavHtml', daily)
        self.assertIn('dReloadBody', daily)
        self.assertIn('不空写已有数', daily)
        rep_py = open(os.path.join(ROOT, 'app', 'reports.py'), encoding='utf-8').read()
        self.assertIn('def preserve_filled', rep_py)
        self.assertIn('已保住未空写', rep_py)

if __name__ == '__main__':
    unittest.main()
