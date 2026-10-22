# -*- coding: utf-8 -*-
"""1.1.28：WPS 向表格拖选多选 + 底部求和/计数/平均 + Ctrl+C TSV。"""
import os, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..')

class CellSel1128(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def r(*p):
            return open(os.path.join(ROOT, *p), encoding='utf-8').read()
        cls.ver = r('app', 'version.py')
        cls.vj = r('static', 'v.json')
        cls.core = r('static', 'core.js')
        cls.css = r('static', 'app.css')
        cls.idx = r('static', 'index.html')
        cls.rep = r('static', 'p_report.js')
        cls.daily = r('static', 'p_daily.js')
        cls.app = r('static', 'app.js')
        cls.manual = r('使用说明.md')

    def test_version(self):
        self.assertIn("VERSION = '1.1.28'", self.ver)
        self.assertIn('1.1.28', self.vj)
        self.assertIn("'version': '1.1.28'", self.ver)
        self.assertIn('表格拖选多选', self.ver)

    def test_core_cellsel_api(self):
        self.assertIn('const CellSel', self.core)
        self.assertIn('copyTSV', self.core)
        self.assertIn('consumeClick', self.core)
        self.assertIn('setSingle', self.core)
        self.assertIn('extendTo', self.core)
        self.assertIn('cell-sel', self.core)
        self.assertIn('cellBar', self.core)
        self.assertIn('data-nosel', self.core)
        self.assertIn('求和', self.core)
        self.assertIn('平均', self.core)

    def test_css_and_bar(self):
        self.assertIn('.cell-sel', self.css)
        self.assertIn('#cellBar', self.css)
        self.assertIn('id="cellBar"', self.idx)

    def test_report_hooks(self):
        self.assertIn('CellSel.setSingle', self.rep)
        self.assertIn('CellSel.consumeClick', self.rep)
        self.assertIn('CellSel.extendTo', self.rep)
        self.assertIn('CellSel.on(t', self.rep)

    def test_daily_and_lists(self):
        self.assertIn('CellSel.on(T)', self.daily)
        self.assertIn('CellSel.on(dt)', self.daily)
        out = open(os.path.join(ROOT, 'static', 'p_out.js'), encoding='utf-8').read()
        self.assertIn('data-nosel', out)
        self.assertIn("CellSel.on($('#olTbl'", out)
        arr = open(os.path.join(ROOT, 'static', 'p_arrival.js'), encoding='utf-8').read()
        self.assertIn("CellSel.on($('#arTbl'", arr)
        loan = open(os.path.join(ROOT, 'static', 'p_loan.js'), encoding='utf-8').read()
        self.assertIn('data-nosel', loan)
        self.assertIn("CellSel.on($('#llTbl'", loan)
        stock = open(os.path.join(ROOT, 'static', 'p_stock.js'), encoding='utf-8').read()
        self.assertIn("CellSel.on($('#stTbl'", stock)
        self.assertIn("CellSel.on($('#mvTbl'", stock)

    def test_route_clears(self):
        self.assertIn('CellSel.clear()', self.app)

    def test_manual(self):
        self.assertIn('表格拖选求和', self.manual)
        self.assertIn('v1.1.28', self.manual)

if __name__ == '__main__':
    unittest.main()
