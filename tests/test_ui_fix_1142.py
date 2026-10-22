# -*- coding: utf-8 -*-
"""1.1.42：侧栏 sticky 冲突修复 + 借出快捷选品。"""
import os, json, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def R(*a):
    with open(os.path.join(ROOT, *a), encoding='utf-8') as f:
        return f.read()

class V1142_UiFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ver = R('app', 'version.py')
        cls.pl = R('static', 'p_loan.js')
        cls.po = R('static', 'p_out.js')
        cls.app = R('static', 'app.js')
        cls.css = R('static', 'app.css')
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f:
            cls.vj = json.load(f)

    def test_version(self):
        self.assertIn("VERSION = '1.1.42'", self.ver)
        self.assertEqual(self.vj.get('version'), '1.1.42')
        self.assertIn("'version': '1.1.42'", self.ver)
        self.assertIn('竖排', self.ver)
        self.assertIn('大按钮', self.ver)

    def test_home_note_not_override_side_sticky(self):
        # 全局入页侧栏 sticky 仍在
        self.assertIn('.sticky{position:sticky;top:76px}', self.css)
        # 便签用 hs-note，禁止再写裸 .sticky{width:148px
        self.assertIn('.hs-note{', self.css)
        self.assertIn('class="hs-note c-', self.app)
        self.assertNotIn('class="sticky c-', self.app)
        # 便签区不得再覆盖全局 .sticky 为 width/rotate
        bad = False
        for line in self.css.splitlines():
            s = line.strip()
            if s.startswith('.sticky{') and 'width:148px' in s:
                bad = True
            if s.startswith('.sticky{') and 'transform:rotate' in s:
                bad = True
        self.assertFalse(bad, 'home notes must not override .sticky')

    def test_qr_no_vertical_squeeze(self):
        self.assertTrue('.qr>div{' in self.css.replace(' ', '') or '.qr > div{' in self.css)
        self.assertIn('overflow-wrap:anywhere', self.css)
        self.assertIn('本单扫码拍', self.po)
        self.assertIn('class="qr"', self.po)

    def test_loan_picks_grid(self):
        self.assertIn('id="picks"', self.pl)
        self.assertIn('drawPicks', self.pl)
        self.assertIn('选择产品', self.pl)
        self.assertIn('loan-lines', self.pl)
        self.assertIn('data-nr=', self.pl)
        self.assertIn('>要还</button>', self.pl)
        # 单据来源保留
        self.assertIn('单据来源', self.pl)
