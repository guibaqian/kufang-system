# -*- coding: utf-8 -*-
"""1.1.32：打印顶栏、模板 settings、print_files 目录、手机两大按钮。不动业务库表结构。"""
import os, json, unittest, tempfile, shutil, base64, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding='utf-8').read()

class V1132_Version(unittest.TestCase):
    def test_version(self):
        self.assertIn("VERSION = '1.1.32'", read('app', 'version.py'))
        self.assertIn('"version": "1.1.32"', read('static', 'v.json'))
        self.assertIn("'version': '1.1.32'", read('app', 'version.py'))
        self.assertIn('打印', read('app', 'version.py'))

class V1132_Nav(unittest.TestCase):
    def test_desktop_nav(self):
        js = read('static', 'app.js')
        self.assertIn("print: '打印'", js)
        self.assertIn("'print'", js)
        self.assertIn("'print'", read('static', 'p_sys.js'))
        self.assertIn("['print', '打印']", read('static', 'p_sys.js'))
        py = read('app', 'server.py')
        self.assertIn("'print'", py)
        self.assertIn('p_print.js', read('static', 'index.html'))

class V1132_Page(unittest.TestCase):
    def test_p_print(self):
        js = read('static', 'p_print.js')
        self.assertIn('Pages.print', js)
        self.assertIn('prEditTpl', js)
        self.assertIn('print_templates', js)
        self.assertIn('pr-drop', js)
        self.assertIn('/api/print/files', js)
        self.assertIn('printHtml', js)

class V1132_Mobile(unittest.TestCase):
    def test_home2(self):
        js = read('static', 'm', 'm.js')
        self.assertIn('home2', js)
        self.assertIn('href="#out"', js)
        self.assertIn('href="#print/in"', js)
        self.assertIn('MP.print', js)
        self.assertIn('huge', js)
        css = read('static', 'm', 'm.css')
        self.assertIn('.huge', css)
        self.assertIn('.home2', css)

class V1132_Backend(unittest.TestCase):
    def test_module(self):
        py = read('app', 'printpage.py')
        self.assertIn('DEFAULT_TEMPLATES', py)
        self.assertIn('print_files', py)
        self.assertIn('index.json', py)
        self.assertIn("'out'", py)
        self.assertIn("'in'", py)
        self.assertIn('print_files', py)
        self.assertIn('index.json', py)
        logic = read('app', 'logic.py')
        self.assertIn('print_templates', logic)

    def test_merge_and_files(self):
        sys.path.insert(0, os.path.join(ROOT, 'app'))
        td = tempfile.mkdtemp(prefix='wh_print_')
        try:
            os.environ['WH_DATA'] = td
            # reload db paths
            import importlib
            import db as dbmod
            dbmod.DATA = td
            dbmod.DB_PATH = os.path.join(td, 'warehouse.db')
            dbmod.PHOTO_DIR = os.path.join(td, 'photos')
            import printpage
            importlib.reload(printpage)
            printpage.PRINT_DIR = os.path.join(td, 'print_files')
            printpage.INDEX = os.path.join(printpage.PRINT_DIR, 'index.json')
            t = printpage.merge_templates({})
            self.assertEqual(t['out']['title'], '出库单')
            self.assertEqual(t['in']['fields']['party']['label'], '供货方/来源')
            custom = printpage.clean_templates({'out': {'title': '发货单', 'fields': {'party': {'label': '客户', 'show': True}}}})
            self.assertEqual(custom['out']['title'], '发货单')
            self.assertEqual(custom['out']['fields']['party']['label'], '客户')
            # files index only under print_files
            printpage.ensure_dir()
            self.assertTrue(os.path.isdir(printpage.PRINT_DIR))
            self.assertTrue(os.path.isfile(printpage.INDEX))
            self.assertFalse(os.path.isfile(os.path.join(td, 'warehouse.db')))
        finally:
            shutil.rmtree(td, ignore_errors=True)

class V1132_NoRegress(unittest.TestCase):
    def test_cellsel_dirty(self):
        js = read('static', 'core.js')
        self.assertIn('CellSel', js)
        self.assertIn('dirtyLeave', js)
        self.assertIn('选用并完成', js)

if __name__ == '__main__':
    unittest.main()
