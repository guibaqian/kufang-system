# -*- coding: utf-8 -*-
"""1.1.33：打印单字段扩容 + 设置全局搜索。不动业务库。"""
import os, sys, unittest, tempfile, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding='utf-8').read()

class V1133_Version(unittest.TestCase):
    def test_version(self):
        self.assertIn("VERSION = '1.1.33'", read('app', 'version.py'))
        self.assertIn('"version": "1.1.33"', read('static', 'v.json'))
        self.assertIn("'version': '1.1.33'", read('app', 'version.py'))
        self.assertIn('取货人', read('app', 'version.py'))
        self.assertIn('设置页顶部全局搜索', read('app', 'version.py'))

class V1133_PrintFields(unittest.TestCase):
    def test_defaults(self):
        sys.path.insert(0, os.path.join(ROOT, 'app'))
        td = tempfile.mkdtemp(prefix='wh_p1133_')
        try:
            os.environ['WH_DATA'] = td
            import importlib
            import db as dbmod
            dbmod.DATA = td
            dbmod.DB_PATH = os.path.join(td, 'warehouse.db')
            import printpage
            importlib.reload(printpage)
            printpage.PRINT_DIR = os.path.join(td, 'print_files')
            printpage.INDEX = os.path.join(printpage.PRINT_DIR, 'index.json')
            t = printpage.merge_templates({})
            out_f = t['out']['fields']
            for k in ('date', 'party', 'dept', 'picker', 'phone', 'purpose', 'dest', 'leader', 'handler', 'contact', 'remark'):
                self.assertIn(k, out_f)
                self.assertTrue(out_f[k]['show'] or k == 'out_no')
            self.assertFalse(out_f['out_no']['show'])
            self.assertEqual(out_f['picker']['label'], '取货人')
            in_f = t['in']['fields']
            for k in ('date', 'party', 'dept', 'handler', 'phone', 'receiver', 'location', 'remark'):
                self.assertIn(k, in_f)
            self.assertEqual(in_f['party']['label'], '送来处/供货方')
            self.assertTrue(t['out']['show_sign_area'])
            keys = [c['key'] for c in t['out']['line_cols']]
            self.assertIn('unit', keys)
            # 旧存模板只含少量字段时，新字段自动补上
            old = {'out': {'title': '发货单', 'fields': {'party': {'label': '客户', 'show': True}, 'date': {'label': '日期', 'show': True}}}}
            m = printpage.merge_templates(old)
            self.assertEqual(m['out']['title'], '发货单')
            self.assertEqual(m['out']['fields']['party']['label'], '客户')
            self.assertIn('picker', m['out']['fields'])
            self.assertEqual(m['out']['fields']['picker']['label'], '取货人')
            self.assertIn('out', printpage.FIELD_GROUPS)
            self.assertIn('in', printpage.FIELD_GROUPS)
            self.assertFalse(os.path.isfile(os.path.join(td, 'warehouse.db')))
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_js(self):
        js = read('static', 'p_print.js')
        self.assertIn('PR_GROUPS', js)
        self.assertIn('取货与送达', js)
        self.assertIn('show_sign_area', js)
        self.assertIn('pr-sheet', js)
        self.assertIn('送到哪里', js)
        self.assertIn("'dest'", js)
        m = read('static', 'm', 'm.js')
        self.assertIn('field_groups', m)
        self.assertIn('收货信息', m)
        self.assertIn('show_sign_area', m)

class V1133_SettingsSearch(unittest.TestCase):
    def test_search(self):
        js = read('static', 'p_sys.js')
        self.assertIn('SET_HINTS', js)
        self.assertIn('setMatch', js)
        self.assertIn('setFilterMenu', js)
        self.assertIn('setFilterBody', js)
        self.assertIn('id="sQ"', js)
        self.assertIn('set-hits', js)
        self.assertIn('搜设置', js)
        css = read('static', 'app.css')
        self.assertIn('.set-search', css)
        self.assertIn('.set-hits', css)

class V1133_NoRegress(unittest.TestCase):
    def test_prev(self):
        self.assertIn("print: '打印'", read('static', 'app.js'))
        self.assertIn('Pages.print', read('static', 'p_print.js'))
        self.assertIn('home2', read('static', 'm', 'm.js'))
        self.assertIn('dirtyLeave', read('static', 'core.js'))

if __name__ == '__main__':
    unittest.main()
