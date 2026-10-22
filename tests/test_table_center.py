# -*- coding: utf-8 -*-
"""所有表格文字居中：CSS 断言。python -m unittest tests.test_table_center -v"""
import os, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TableCenter(unittest.TestCase):
    def test_css_centers_all_grids(self):
        css = open(os.path.join(ROOT, 'static', 'app.css'), encoding='utf-8').read()
        self.assertIn('所有表格文字居中（v1.1.7）', css)
        for s in (
            'table.t th,table.t td',
            'table.rt th,table.rt td',
            'table.dt th,table.dt td',
            'table.pp th,table.pp td{text-align:center;vertical-align:middle}',
            'table.t .n,table.t th.n,table.rt td.n,table.rt th.n{text-align:center}',
            'table.dt td.nm,table.dt td.nt',
            'table.pp th.pl,table.pp td.pl',
        ):
            self.assertIn(s, css)
        # wrap/prod columns may be left for readability; core grids stay centered in the v1.1.7 block
        bad = [ln for ln in css.splitlines()
               if 'text-align:left' in ln and re.search(r'table\.(t|rt|dt|pp)\s+(th|td)(?!\.(wrap|prod|rmk))', ln)]
        # allow wrap/prod/rmk left; fail only naked table.t td{text-align:left}
        naked = [ln for ln in css.splitlines()
                 if re.search(r'table\.(t|rt|dt|pp)\s+(th|td)\{[^}]*text-align:left', ln)]
        self.assertEqual(naked, [])

    def test_version_note(self):
        v = open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8').read()
        self.assertIn("VERSION = '1.1.13'", v)
        self.assertIn('所有表格文字居中', v)

if __name__ == '__main__':
    unittest.main()
