# -*- coding: utf-8 -*-
"""1.1.29：换货=换出+换入（谁换谁）；保留 1.1.26 类型列表与「（不选）」
python -m unittest tests.test_out_kind_exchange -v
"""
import os, sys, tempfile, unittest, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))

class OutKindExchangeSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'app', 'logic.py'), encoding='utf-8') as f: cls.logic = f.read()
        with open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8') as f: cls.ver = f.read()
        with open(os.path.join(ROOT, 'app', 'db.py'), encoding='utf-8') as f: cls.db = f.read()
        with open(os.path.join(ROOT, 'app', 'moves.py'), encoding='utf-8') as f: cls.mv = f.read()
        with open(os.path.join(ROOT, 'app', 'server.py'), encoding='utf-8') as f: cls.srv = f.read()
        with open(os.path.join(ROOT, 'static', 'p_sys.js'), encoding='utf-8') as f: cls.psys = f.read()
        with open(os.path.join(ROOT, 'static', 'p_out.js'), encoding='utf-8') as f: cls.pout = f.read()
        with open(os.path.join(ROOT, 'static', 'm', 'm.js'), encoding='utf-8') as f: cls.mjs = f.read()
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f: cls.vj = f.read()

    def test_version_1129(self):
        self.assertIn("VERSION = '1.1.34'", self.ver)
        self.assertIn('1.1.34', self.vj)
        self.assertIn('谁换谁', self.ver)

    def test_default_out_kinds_has_exchange(self):
        self.assertIn("'换货'", self.logic)
        self.assertIn("['客户自提', '销售出库', '厂内自用', '领用出库', '换货', '其他出库']", self.logic)

    def test_side_column(self):
        self.assertIn("('out_items', 'side'", self.db)
        self.assertIn("side TEXT DEFAULT 'out'", self.db)
        self.assertIn("side == 'in'", self.logic)
        self.assertIn('换货 换入', self.logic)
        self.assertIn('换货 换出', self.logic)

    def test_ui_two_sides(self):
        self.assertIn('isExch', self.pout)
        self.assertIn('ex-pair', self.pout)
        self.assertIn('换出', self.pout)
        self.assertIn('换入', self.pout)
        self.assertIn('批量只适合单边出库', self.pout)
        self.assertIn("f.side === 'in'", self.mjs)
        self.assertIn('保存换货', self.mjs)

    def test_moves_labels(self):
        self.assertIn("('xout', '换出')", self.mv)
        self.assertIn("('xin', '换入')", self.mv)

    def test_export_direction(self):
        self.assertIn("'方向'", self.srv)

    def test_defaults_ui_keeps_blank_option(self):
        i_blank = self.psys.find('id="dfKind"><option value="">（不选）</option>')
        self.assertGreaterEqual(i_blank, 0)
        self.assertIn("'out_kind': '客户自提'", self.logic)

    def test_new_form_respects_blank_default(self):
        self.assertIn("df.out_kind === '' ? ''", self.pout)
        self.assertIn("df.out_kind === '' ? ''", self.mjs)


class ExchangeStock(unittest.TestCase):
    """真实 SQLite：换货扣发出、加收回；旧换货单仅发出仍可改"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['WH_DATA'] = self.tmp.name
        import importlib
        import db, logic
        importlib.reload(db); importlib.reload(logic)
        self.db, self.logic = db, logic
        self.c = db.init()
        self.a = logic.save_row(self.c, 'product', {'name': '新品A', 'unit': '个'}, '测', '测')
        self.b = logic.save_row(self.c, 'product', {'name': '旧品B', 'unit': '个'}, '测', '测')
        # 盘点锚点，否则 stock known=False
        logic.save_count(self.c, self.a, 10, '2026-10-01', '测')
        logic.save_count(self.c, self.b, 1, '2026-10-01', '测')
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.tmp.cleanup(); os.environ.pop('WH_DATA', None)

    def stock(self, pid):
        return self.logic.stock_all(self.c, [pid])[pid]['qty']

    def test_exchange_both_sides(self):
        oid = self.logic.save_out(self.c, {
            'date': '2026-10-21', 'kind': '换货', 'customer': '测试客户',
            'items': [
                {'product_id': self.a, 'qty': 2, 'side': 'out'},
                {'product_id': self.b, 'qty': 1, 'side': 'in'},
            ]
        }, '测')
        self.c.commit()
        self.assertEqual(self.stock(self.a), 8)   # 10-2
        self.assertEqual(self.stock(self.b), 2)   # 1+1
        mv = list(self.c.execute("SELECT product_id, qty, label FROM moves WHERE src='out' AND src_id=? ORDER BY qty", (oid,)))
        self.assertEqual(len(mv), 2)
        self.assertTrue(any('换出' in r[2] and r[1] < 0 for r in mv))
        self.assertTrue(any('换入' in r[2] and r[1] > 0 for r in mv))

    def test_new_exchange_requires_both(self):
        with self.assertRaises(ValueError):
            self.logic.save_out(self.c, {
                'date': '2026-10-21', 'kind': '换货', 'customer': 'X',
                'items': [{'product_id': self.a, 'qty': 1, 'side': 'out'}]
            }, '测')

    def test_legacy_out_only_editable(self):
        # 模拟 1.1.26 旧单：只有发出（直接写库，绕过新校验）
        from db import now, save_row
        oid = save_row(self.c, 'out', {'date': '2026-10-20', 'kind': '换货', 'customer': '旧客'}, '测', '旧换货')
        self.c.execute('INSERT INTO out_items(order_id,product_id,product_name,qty,batch_no,note,side) VALUES(?,?,?,?,?,?,?)',
                       (oid, self.a, '新品A', 1, '', '', 'out'))
        self.logic.rebuild_out(self.c, oid); self.c.commit()
        self.assertEqual(self.stock(self.a), 9)
        # 原样改备注/数量仍可（不强迫补换入）
        self.logic.save_out(self.c, {
            'id': oid, 'date': '2026-10-20', 'kind': '换货', 'customer': '旧客', 'remark': '改一下',
            'items': [{'product_id': self.a, 'qty': 1, 'side': 'out'}]
        }, '测')
        self.c.commit()
        self.assertEqual(self.stock(self.a), 9)
        its = self.logic.items_of(self.c, oid)
        self.assertEqual(len(its), 1)
        self.assertEqual((its[0].get('side') or 'out'), 'out')


if __name__ == '__main__':
    unittest.main()
