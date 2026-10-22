# -*- coding: utf-8 -*-
"""表格交互（筛选/列宽/十字/吸顶）：静态断言。python -m unittest tests.test_table_ux -v"""
import os, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TableUx(unittest.TestCase):
    def setUp(self):
        self.css = open(os.path.join(ROOT, 'static', 'app.css'), encoding='utf-8').read()
        self.core = open(os.path.join(ROOT, 'static', 'core.js'), encoding='utf-8').read()
        self.rep = open(os.path.join(ROOT, 'static', 'p_report.js'), encoding='utf-8').read()
        self.ver = open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8').read()

    def test_unified_page_shells(self):
        core = open(os.path.join(ROOT, 'static', 'core.js'), encoding='utf-8').read()
        self.assertIn('const UI = {', core)
        self.assertIn('ph(title, sub, help, acts)', core)
        self.assertIn('listShell', core)
        self.assertIn('entryShell', core)
        css = open(os.path.join(ROOT, 'static', 'app.css'), encoding='utf-8').read()
        self.assertIn('页面骨架统一', css)
        self.assertIn('.grid2.page-entry', css)
        for name in ('p_out.js', 'p_loan.js', 'p_arrival.js', 'p_stock.js', 'p_misc.js', 'p_slip.js', 'p_report.js', 'p_daily.js', 'p_sys.js'):
            js = open(os.path.join(ROOT, 'static', name), encoding='utf-8').read()
            self.assertIn('UI.ph(', js, name)
        ver = open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8').read()
        self.assertIn('页面骨架统一', ver)

    def test_version_1113(self):
        self.assertIn("VERSION = '1.1.13'", self.ver)
        self.assertIn('表格交互再稳', self.ver)
        v = open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8').read()
        self.assertIn('1.1.13', v)

    def test_no_relative_breaks_sticky_on_list_th(self):
        self.assertNotIn('table.t thead th{position:relative}', self.css)
        self.assertNotIn("th.style.position = 'relative'", self.core)
        self.assertIn('function syncStickyHeads', self.core)

    def test_reset_widths_path(self):
        self.assertIn('rResetWidths', self.rep)
        self.assertIn('重置列宽', self.rep)
        self.assertIn('data-rzw', self.core)
        self.assertIn('重置列宽', self.core)

    def test_colgroup_resize_and_filter(self):
        self.assertIn('rAttachResize', self.rep)
        self.assertIn('colgroup', self.rep)
        self.assertIn('rFilterPop', self.rep)
        self.assertIn('r-fpop', self.css)
        self.assertTrue("addEventListener('scroll'" in self.rep or 'addEventListener("scroll"' in self.rep)

    def test_crosshair_opacity(self):
        self.assertIn('rgba(61,111,216,.06)', self.css)
        chunk = self.core[self.core.find('function gridFocus'):self.core.find('function gridFocusOn') + 240]
        self.assertIn('requestAnimationFrame', chunk)
        self.assertIn('hl-r', self.core)

    def test_css_parses_braces(self):
        text = re.sub(r'/\*.*?\*/', '', self.css, flags=re.S)
        self.assertEqual(text.count('{'), text.count('}'))

if __name__ == '__main__':
    unittest.main()
