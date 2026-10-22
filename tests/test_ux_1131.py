# -*- coding: utf-8 -*-
"""1.1.31：未保存弹窗带保存、照片选用即完成、单据侧栏照片捷径、布局 page-act。不动 data。"""
import os, re, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding='utf-8').read()

class V1131_Version(unittest.TestCase):
    def test_version(self):
        self.assertIn("VERSION = '1.1.31'", read('app', 'version.py'))
        self.assertIn('"version": "1.1.31"', read('static', 'v.json'))
        self.assertIn("'version': '1.1.31'", read('app', 'version.py'))

class V1131_DirtyLeave(unittest.TestCase):
    def test_core_helpers(self):
        js = read('static', 'core.js')
        self.assertIn('function dirtyLeave', js)
        self.assertIn('function confirmDirty', js)
        self.assertIn("finish('save')", js)
        self.assertIn("finish('discard')", js)
        self.assertIn('不保存', js)
    def test_app_route_async(self):
        js = read('static', 'app.js')
        self.assertIn('async route()', js)
        self.assertIn('dirtyLeave(App.guard)', js)
        self.assertIn('guardSave', js)
        self.assertNotIn('if (!confirm(App.guard))', js)
    def test_daily_report_wire(self):
        d = read('static', 'p_daily.js')
        self.assertIn('confirmDirty', d)
        self.assertIn('App.guardSave = doSave', d)
        r = read('static', 'p_report.js')
        self.assertIn("App.guardSave = () => rSaveTabs", r)

class V1131_PhotoFlow(unittest.TestCase):
    def test_take_completes(self):
        js = read('static', 'core.js')
        self.assertIn('选用并完成', js)
        self.assertIn('ov.remove(); end(true);', js)
        self.assertIn('opt.lib', js)
        self.assertIn('function showLibQr', js)
        self.assertIn('data-lib', js)
        self.assertIn('data-libqr', js)
        self.assertIn('ph-quick', js)
    def test_entry_shortcuts(self):
        out = read('static', 'p_out.js')
        self.assertIn('outLib', out)
        self.assertIn('showLibQr', out)
        self.assertIn('page-act', out)
        self.assertIn('page-side-col', out)
        ar = read('static', 'p_arrival.js')
        self.assertIn('page-act', ar)
        ln = read('static', 'p_loan.js')
        self.assertIn('page-act', ln)

class V1131_NoRegress_1130(unittest.TestCase):
    def test_ex_side_nm(self):
        css = read('static', 'app.css')
        self.assertIn('.ex-side .lines .nm{flex:1 1 100%', css)
        self.assertIn('page-act', css)
        self.assertIn('ph-quick', css)
    def test_name_scrub(self):
        py = read('app', 'logic.py')
        self.assertIn('BAD_UI_NAME_KEYS', py)
        self.assertIn('待提出库', py)
        self.assertIn("'自提出库'", read('app', 'logic.py'))

class V1131_CellSel_Kept(unittest.TestCase):
    def test_cellsel_still_there(self):
        js = read('static', 'core.js')
        self.assertIn('CellSel', js)
        self.assertIn('cellBar', js)

if __name__ == '__main__':
    unittest.main()
