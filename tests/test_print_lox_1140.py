# -*- coding: utf-8 -*-
"""1.1.40：打印页液氧表入口。不动业务库。"""
import os, json, unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def R(*a):
    with open(os.path.join(ROOT, *a), encoding='utf-8') as f:
        return f.read()

class V1140_PrintLox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prt = R('static', 'p_print.js')
        cls.rep = R('static', 'p_report.js')
        cls.app = R('static', 'app.js')
        cls.m = R('static', 'm', 'm.js')
        cls.ver = R('app', 'version.py')
        cls.doc = R('使用说明.md')
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f:
            cls.vj = json.load(f)

    def test_version(self):
        self.assertIn("VERSION = '1.1.40'", self.ver)
        self.assertEqual(self.vj.get('version'), '1.1.40')
        self.assertIn("'version': '1.1.40'", self.ver)
        self.assertIn('液氧表', self.ver)

    def test_print_tabs(self):
        self.assertIn("['out', 'in', 'lox', 'files']", self.prt)
        self.assertIn('data-t="lox"', self.prt)
        self.assertIn('>液氧表<', self.prt)
        self.assertIn('async function prLox', self.prt)
        self.assertIn('prLoxPrint', self.prt)
        self.assertIn('rPrintDlg', self.prt)
        self.assertIn('rEnsure', self.prt)
        self.assertIn('本次打印不改表数据', self.prt)
        self.assertIn('报表 · 液氧表', self.prt)

    def test_no_regress_bu_ru_zhang(self):
        # 出库单/入库单不入账文案必须保留
        self.assertIn('不入账、不进库存', self.prt)
        self.assertIn('print_mem_', self.prt)
        self.assertIn('prMemSave', self.prt)
        self.assertIn('data-t="out"', self.prt)
        self.assertIn('data-t="in"', self.prt)
        self.assertIn('data-t="files"', self.prt)
        self.assertIn('上传文件', self.prt)

    def test_report_fallback(self):
        self.assertIn("printLox", self.rep)
        self.assertIn("rPrintDlg('lox')", self.rep)

    def test_home_and_mobile(self):
        self.assertIn('出/入库单 · 液氧表', self.app)
        self.assertIn('href="#print/lox"', self.m)
        self.assertIn('液氧打印表', self.m)
        self.assertIn("arg === 'lox'", self.m)
        self.assertIn('打印入库单', self.m)
        self.assertIn('不入账', self.m)
        self.assertIn('bottle:', self.m)

    def test_docs(self):
        self.assertIn('v1.1.40', self.doc)
        self.assertIn('液氧表（液氧打印表', self.doc)
        self.assertIn('不写入出库 / 到货业务记录、不改库存', self.doc)

    def test_no_data_touch_markers(self):
        blob = self.prt + self.rep + self.app + self.m
        self.assertNotRegex(blob, r"(?i)UPDATE\s+out_orders\s+SET")
        self.assertNotRegex(blob, r"(?i)UPDATE\s+moves\s+SET")
        self.assertNotIn('parse_lox_qc', self.prt)
        self.assertIn('不动业务库', self.prt)

if __name__ == '__main__':
    unittest.main()
