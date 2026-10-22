# -*- coding: utf-8 -*-
"""1.1.30：名称设置撞名清理 + 换货半栏品名不竖排
python -m unittest tests.test_ui_names_scrub_1130 -v
"""
import os, sys, tempfile, unittest, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))


class Source1130(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8') as f: cls.ver = f.read()
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f: cls.vj = f.read()
        with open(os.path.join(ROOT, 'app', 'logic.py'), encoding='utf-8') as f: cls.logic = f.read()
        with open(os.path.join(ROOT, 'app', 'server.py'), encoding='utf-8') as f: cls.srv = f.read()
        with open(os.path.join(ROOT, 'static', 'app.css'), encoding='utf-8') as f: cls.css = f.read()
        with open(os.path.join(ROOT, 'static', 'p_out.js'), encoding='utf-8') as f: cls.pout = f.read()

    def test_version(self):
        self.assertIn("VERSION = '1.1.34'", self.ver)
        self.assertIn('1.1.34', self.vj)
        self.assertIn('待提出库', self.ver)
        self.assertIn('客户自提', self.ver)
        self.assertIn('竖排', self.ver)

    def test_scrub_helpers(self):
        self.assertIn('BAD_UI_NAME_KEYS', self.logic)
        self.assertIn('待提出库', self.logic)
        self.assertIn('migrate_ui_names_dupes', self.srv)
        self.assertIn("'客户自提'", self.logic)  # out_kinds chip (1.1.34 merged 自提出库)

    def test_ex_side_css_not_vertical(self):
        self.assertIn('.ex-side .lines .nm{flex:1 1 100%', self.css)
        self.assertIn('overflow-wrap:anywhere', self.css)
        self.assertIn('.ex-side .pick{min-width:0', self.css)
        self.assertIn('minmax(0,1fr)', self.css)
        self.assertIn('ex-pair', self.pout)
        self.assertIn('linesOut', self.pout)
        self.assertIn('linesIn', self.pout)


class ScrubRuntime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['WH_DATA'] = self.tmp.name
        import importlib
        import db, logic
        importlib.reload(db); importlib.reload(logic)
        self.db, self.logic = db, logic
        self.c = db.init()

    def tearDown(self):
        self.c.close(); self.tmp.cleanup()

    def test_clean_drops_dai_ti_alias(self):
        kinds = self.logic.DEFAULT_SETTINGS['out_kinds']
        m = self.logic.clean_names({
            '待提出库': '客户自提',
            '销售出库': '客户自提',
            '客户自提': '自提',
            '出库': '发货',
            '液态氧原料入出库记录': '液态氧原料出入库记录',
        }, self.logic.name_originals(self.logic.DEFAULT_SETTINGS), kinds)
        self.assertNotIn('待提出库', m)
        self.assertNotIn('销售出库', m)  # 出库类型互撞名
        self.assertEqual(m.get('客户自提'), '自提')  # 合法缩短
        self.assertEqual(m.get('出库'), '发货')
        self.assertIn('客户自提', kinds); self.assertNotIn('自提出库', kinds)

    def test_settings_read_scrubs_and_keeps_chip(self):
        from db import meta_set
        meta_set(self.c, 'settings', {
            'ui_names': {'待提出库': '自提出库', '液态氧原料入出库记录': '液态氧原料出入库记录'},
            'out_kinds': list(self.logic.DEFAULT_SETTINGS['out_kinds']),
        })
        s = self.logic.settings(self.c)
        self.assertNotIn('待提出库', s['ui_names'])
        self.assertIn('客户自提', s['out_kinds']); self.assertNotIn('自提出库', s['out_kinds'])
        self.assertEqual(s['ui_names'].get('液态氧原料入出库记录'), '液态氧原料出入库记录')

    def test_migrate_persists_drop(self):
        from db import meta_set, meta_get
        import server
        import importlib
        importlib.reload(server)
        meta_set(self.c, 'settings', {
            'ui_names': {'待提出库': '自提出库', '客户自提': '销售出库'},
            'out_kinds': list(self.logic.DEFAULT_SETTINGS['out_kinds']),
        })
        dropped = server.migrate_ui_names_dupes(self.c)
        self.assertIn('待提出库', dropped)
        self.assertIn('客户自提', dropped)
        s = meta_get(self.c, 'settings')
        self.assertNotIn('待提出库', s.get('ui_names') or {})
        self.assertIn('客户自提', s.get('out_kinds') or self.logic.DEFAULT_SETTINGS['out_kinds'])
        self.assertEqual(server.migrate_ui_names_dupes(self.c), [])  # once


if __name__ == '__main__':
    unittest.main()
