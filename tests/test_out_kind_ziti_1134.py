# -*- coding: utf-8 -*-
"""1.1.34：自提出库→客户自提合并；出库记录 U8 筛藏起；打印去浏览器页眉
python -m unittest tests.test_out_kind_ziti_1134 -v
"""
import os, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))

def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()

class SourcePins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logic = read('app', 'logic.py')
        cls.srv = read('app', 'server.py')
        cls.ver = read('app', 'version.py')
        cls.vj = read('static', 'v.json')
        cls.pout = read('static', 'p_out.js')
        cls.core = read('static', 'core.js')
        cls.psys = read('static', 'p_sys.js')

    def test_version(self):
        self.assertIn("VERSION = '1.1.34'", self.ver)
        self.assertIn('1.1.34', self.vj)
        self.assertIn('客户自提', self.ver)
        self.assertIn('U8单细分', self.ver)
        self.assertIn('页眉', self.ver)

    def test_out_kinds_no_ziti(self):
        self.assertIn("['客户自提', '销售出库', '厂内自用', '领用出库', '换货', '其他出库']", self.logic)
        # DEFAULT out_kinds 行不得再含自提出库（OUT_KIND_MERGE 字典除外）
        for ln in self.logic.splitlines():
            if "'out_kinds':" in ln and '[' in ln:
                # 只看列表字面量，注释里可提「自提出库」
                lit = ln.split('#')[0]
                self.assertNotIn("'自提出库'", lit)
        self.assertIn("'out_kind': '客户自提'", self.logic)
        self.assertIn('OUT_KIND_MERGE', self.logic)
        self.assertIn("normalize_out_kind", self.logic)

    def test_migrate_and_query(self):
        self.assertIn('migrate_out_kind_ziti_1134', self.srv)
        self.assertIn("kind='客户自提' WHERE kind='自提出库'", self.srv)
        self.assertIn('OUT_KIND_MERGE', self.srv)

    def test_u8_filter_hidden_until_u8_source(self):
        self.assertIn("OL.source === 'U8单'", self.pout)
        self.assertIn('U8单细分', self.pout)
        self.assertNotIn('<option value="">U8类型</option>', self.pout)
        self.assertIn('U8单细分建议', self.psys)

    def test_print_no_browser_header(self):
        self.assertIn('@page{size:${opt.landscape', self.core)
        self.assertIn('margin:0}', self.core)
        self.assertIn('prevTitle', self.core)
        self.assertIn('padding:${mg}', self.core)


class MigrateAndSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['WH_DATA'] = self.tmp.name
        import importlib
        import db, logic, server
        importlib.reload(db); importlib.reload(logic); importlib.reload(server)
        self.db, self.logic, self.server = db, logic, server
        self.c = db.init()
        self.pid = logic.save_row(self.c, 'product', {'name': '测瓶', 'unit': '个'}, '测', '测')
        logic.save_count(self.c, self.pid, 10, '2026-10-01', '测')
        # seed old kind + settings with 自提出库
        from db import save_row, meta_set, meta_get, now
        oid = save_row(self.c, 'out', {'date': '2026-10-10', 'kind': '自提出库', 'customer': '旧客', 'source': 'app手工单'}, '测', '旧自提')
        self.c.execute('INSERT INTO out_items(order_id,product_id,product_name,qty,batch_no,note) VALUES(?,?,?,?,?,?)',
                       (oid, self.pid, '测瓶', 1, '', ''))
        logic.rebuild_out(self.c, oid)
        meta_set(self.c, 'settings', {
            'out_kinds': ['自提出库', '销售出库', '客户自提', '厂内自用', '领用出库', '换货', '其他出库'],
            'defaults': {'session': '早上', 'out_kind': '自提出库', 'out_source': '', 'list_days': 0},
            'ui_names': {'自提出库': '自提'},
        })
        self.c.commit()
        self.oid = oid

    def tearDown(self):
        self.c.close(); self.tmp.cleanup(); os.environ.pop('WH_DATA', None)

    def test_normalize_and_settings_strip(self):
        self.assertEqual(self.logic.normalize_out_kind('自提出库'), '客户自提')
        s = self.logic.settings(self.c)
        self.assertNotIn('自提出库', s['out_kinds'])
        self.assertIn('客户自提', s['out_kinds'])
        self.assertEqual(s['defaults']['out_kind'], '客户自提')

    def test_migrate_rewrites_rows(self):
        info = self.server.migrate_out_kind_ziti_1134(self.c)
        self.c.commit()
        self.assertEqual(info['orders'], 1)
        row = self.c.execute('SELECT kind FROM out_orders WHERE id=?', (self.oid,)).fetchone()
        self.assertEqual(row['kind'], '客户自提')
        s = self.db.meta_get(self.c, 'settings')
        self.assertNotIn('自提出库', s.get('out_kinds') or [])
        self.assertEqual((s.get('defaults') or {}).get('out_kind'), '客户自提')
        self.assertIsNone(self.server.migrate_out_kind_ziti_1134(self.c))  # idempotent

    def test_save_accepts_old_name(self):
        oid = self.logic.save_out(self.c, {
            'date': '2026-10-21', 'kind': '自提出库', 'customer': '新客',
            'items': [{'product_id': self.pid, 'qty': 1}],
        }, '测')
        self.c.commit()
        row = self.c.execute('SELECT kind FROM out_orders WHERE id=?', (oid,)).fetchone()
        self.assertEqual(row['kind'], '客户自提')


if __name__ == '__main__':
    unittest.main()
