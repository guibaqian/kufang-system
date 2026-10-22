# -*- coding: utf-8 -*-
"""1.1.38 Phase B smoke: out again, batch kinds, print mem, lox wizard, U8 home, mobile exch."""
import os, re, unittest, json
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class PhaseB1138(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def R(*a):
            with open(os.path.join(ROOT, *a), encoding='utf-8') as f:
                return f.read()
        cls.out = R('static', 'p_out.js')
        cls.prt = R('static', 'p_print.js')
        cls.rep = R('static', 'p_report.js')
        cls.app = R('static', 'app.js')
        cls.arr = R('static', 'p_arrival.js')
        cls.m = R('static', 'm', 'm.js')
        cls.mcss = R('static', 'm', 'm.css')
        cls.css = R('static', 'app.css')
        cls.core = R('static', 'core.js')
        cls.ver = R('app', 'version.py')
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f:
            cls.vj = json.load(f)

    def test_version(self):
        self.assertIn("VERSION = '1.1.38'", self.ver)
        self.assertEqual(self.vj.get('version'), '1.1.38')
        self.assertIn("'version': '1.1.38'", self.ver)

    def test_out_again_and_dirty(self):
        self.assertIn('再来一笔同来源', self.out)
        self.assertIn('去出库记录', self.out)
        self.assertIn('confirmDirty', self.out)
        self.assertIn('App.guardSave', self.out)

    def test_batch_kindsForSource(self):
        self.assertIn('kindsForSource(OB.source', self.out)
        self.assertIn('kindsForSource', self.core)

    def test_print_mem_preview(self):
        self.assertIn('prMemSave', self.prt)
        self.assertIn('print_mem_', self.prt)
        self.assertIn('不入账、不进库存', self.prt)
        self.assertIn('pr-preview', self.prt)

    def test_lox_wizard(self):
        self.assertIn('rLoxPendingQc', self.rep)
        self.assertIn('待写入质检', self.rep)
        self.assertIn('将写入左侧入库列', self.rep)
        self.assertIn('rLoxFlashLedger', self.rep)
        self.assertIn('rLedgerNextBatchDlg', self.rep)
        self.assertIn('rLedgerTwoBatchDlg', self.rep)
        self.assertIn('r-flash', self.css)

    def test_home_u8(self):
        self.assertIn('homeGoArrivalU8', self.app)
        self.assertIn("AR.f = 'pending'", self.app + self.arr)
        self.assertIn('homeArrivalU8', self.arr)

    def test_mobile_exch(self):
        self.assertIn('ex-big', self.m)
        self.assertIn('ex-big', self.mcss)
        self.assertIn('换出 · 发出', self.m)

    def test_no_data_touch_markers(self):
        blob = self.out + self.prt + self.rep + self.app + self.m
        self.assertNotIn('UPDATE out_orders', blob)
        self.assertNotIn('migrate', blob.lower())
        self.assertNotRegex(blob, r'(?i)DELETE\s+FROM\s+')
        # algorithms still called (orchestration only)
        self.assertIn('rLoxInApply', self.rep)
        self.assertIn('kindsForSource', self.out)

    def test_regressions(self):
        self.assertIn('function kindsForSource', self.core)
        self.assertIn('dirtyLeave', self.app)
        self.assertIn('CellSel', self.app)
        self.assertIn('打印入库单', self.m)
        self.assertIn("homeGoOut('app手工单','客户自提')", self.app)

if __name__ == '__main__':
    unittest.main()
