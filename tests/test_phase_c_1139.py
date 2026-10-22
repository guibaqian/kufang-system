# -*- coding: utf-8 -*-
"""1.1.39 Phase C smoke: mobile IA, home phone, moveLabelDisp, empties, no data touch."""
import os, re, unittest, json
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class PhaseC1139(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def R(*a):
            with open(os.path.join(ROOT, *a), encoding='utf-8') as f:
                return f.read()
        cls.core = R('static', 'core.js')
        cls.app = R('static', 'app.js')
        cls.css = R('static', 'app.css')
        cls.m = R('static', 'm', 'm.js')
        cls.mcss = R('static', 'm', 'm.css')
        cls.stock = R('static', 'p_stock.js')
        cls.out = R('static', 'p_out.js')
        cls.prt = R('static', 'p_print.js')
        cls.rep = R('static', 'p_report.js')
        cls.sys = R('static', 'p_sys.js')
        cls.ver = R('app', 'version.py')
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f:
            cls.vj = json.load(f)

    def test_version(self):
        # 升版后仍保留 1.1.39 changelog；当前 VERSION 可能更高
        self.assertIn("'version': '1.1.39'", self.ver)
        self.assertRegex(self.ver, r"VERSION = '1\.1\.\d+'")
        self.assertRegex(self.vj.get('version') or '', r'^1\.1\.\d+$')

    def test_mobile_home_ia(self):
        self.assertIn('打印入库单', self.m)
        self.assertIn('客户自提 / 换货 / U8', self.m)
        self.assertIn('href="#more"', self.m)
        self.assertIn('MP.more', self.m)
        self.assertIn('mini4', self.m)
        self.assertIn('ok-acts', self.m)
        self.assertIn('再记一笔', self.m)
        # mini four: 日表 / 借用 / 待补全 / 更多
        self.assertIn('<b>日表</b>', self.m)
        self.assertIn('<b>借用</b>', self.m)
        self.assertIn('<b>待补全</b>', self.m)
        self.assertIn('<b>更多</b>', self.m)
        self.assertIn('① 换出 · 发出', self.m)

    def test_home_phone_fold(self):
        self.assertIn('home-phone', self.app)
        self.assertIn('连接手机', self.app)
        self.assertIn('homePhoneQrs', self.app)
        self.assertIn('phoneQrs()', self.app)
        self.assertIn('fillLibQr', self.app)
        self.assertIn('.home-phone', self.css)
        # settings search kept
        self.assertIn('sSearchTip', self.sys)

    def test_move_label_disp(self):
        self.assertIn('function kindDisp', self.core)
        self.assertIn("k === '自提出库'", self.core)
        self.assertIn('function moveLabelDisp', self.core)
        self.assertIn("split('自提出库').join('客户自提')", self.core)
        self.assertIn('moveLabelDisp(m.label)', self.stock)
        self.assertIn('moveLabelDisp(x.label)', self.stock)
        # no UPDATE of historical kinds in Phase C front files
        blob = self.core + self.app + self.m + self.stock
        self.assertNotRegex(blob, r"(?i)UPDATE\s+out_orders\s+SET")
        self.assertNotRegex(blob, r"(?i)UPDATE\s+moves\s+SET")
        self.assertNotIn('migrate', blob.lower())

    def test_empty_and_delete(self):
        self.assertIn('没有记录', self.app)
        self.assertIn('我已看过上面的影响，确定删除', self.core)
        self.assertIn('confirmDelete', self.core)

    def test_no_regress_ab(self):
        self.assertIn('acts4', self.app)
        self.assertIn("homeGoOut('app手工单','客户自提')", self.app)
        self.assertIn('再来一笔同来源', self.out)
        self.assertIn('kindsForSource(OB.source', self.out)
        self.assertIn('待写入质检', self.rep)
        self.assertIn('不入账、不进库存', self.prt)
        self.assertIn('打印入库单', self.m)
        self.assertIn('function kindsForSource', self.core)
        self.assertIn('shellList', self.core)
        self.assertIn('CellSel', self.app)
        self.assertIn('dirtyLeave', self.app)

if __name__ == '__main__':
    unittest.main()
