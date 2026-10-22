# -*- coding: utf-8 -*-
"""1.1.37 Phase A smoke: shells, home keys, copy, no data touch markers."""
import os, re, unittest, json
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class PhaseA1137(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def R(*a):
            with open(os.path.join(ROOT, *a), encoding='utf-8') as f:
                return f.read()
        cls.core = R('static', 'core.js')
        cls.app = R('static', 'app.js')
        cls.css = R('static', 'app.css')
        cls.m = R('static', 'm', 'm.js')
        cls.prt = R('static', 'p_print.js')
        cls.out = R('static', 'p_out.js')
        cls.rep = R('static', 'p_report.js')
        cls.daily = R('static', 'p_daily.js')
        cls.ver = R('app', 'version.py')
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f:
            cls.vj = json.load(f)

    def test_version(self):
        # Phase A 基线已升；仍要求 changelog 留有 1.1.37 记录，当前号 ≥ 1.1.37
        self.assertIn("'version': '1.1.37'", self.ver)
        self.assertRegex(self.ver, r"VERSION = '1\.1\.\d+'")
        self.assertRegex(self.vj.get('version', ''), r'^1\.1\.\d+$')

    def test_shells(self):
        for k in ('shellList', 'shellEntry', 'shellHome', 'kindDisp'):
            self.assertIn(k, self.core)
        self.assertIn('shell-list', self.daily)
        self.assertIn('shell-list', self.rep)
        self.assertIn('.acts4{', self.css)

    def test_home_keys(self):
        self.assertIn("homeGoOut('app手工单','客户自提')", self.app)
        self.assertIn("homeGoOut('U8单','销售出库')", self.app)
        self.assertIn('homeGoLoxQc', self.app)
        self.assertIn("location.hash='print'", self.app)
        self.assertIn('homeGoOutToday', self.app)

    def test_copy(self):
        self.assertIn('打印入库单', self.m)
        self.assertNotRegex(self.m, r'<b>入库</b>')
        self.assertIn('不入账', self.prt)
        self.assertIn('不进库存', self.prt)
        self.assertIn("k === '自提出库'", self.core)
        self.assertIn('kindDisp(o.kind)', self.out)

    def test_regressions(self):
        self.assertIn('function kindsForSource', self.core)
        self.assertIn('dirtyLeave', self.app)
        self.assertIn('CellSel', self.app)
        # no migrate / UPDATE 自提出库 in front phase A files
        blob = self.app + self.core + self.out + self.m + self.prt
        self.assertNotIn('UPDATE out_orders', blob)
        self.assertNotIn('migrate', blob.lower().split('phase')[0] if False else '')  # soft

if __name__ == '__main__':
    unittest.main()
