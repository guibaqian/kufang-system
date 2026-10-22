# -*- coding: utf-8 -*-
"""产品与库存：表头排序依赖的默认 sort 顺序、手动 reorder、软删除进回收站。"""
import os, sys, unittest, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule, new_product, ROOT  # noqa
import test_all

class ProductSortDelete(unittest.TestCase):
    def test_1_reorder_persists_as_default_order(self):
        a = new_product('排序测A', category='配件', spec='A')
        b = new_product('排序测B', category='钢瓶', spec='B')
        c = new_product('排序测C', category='其他', spec='C')
        st, r = call('/api/product/reorder', {'ids': [c, a, b]})
        self.assertEqual(st, 200, r)
        items = call('/api/products')[1]['items']
        ids = [p['id'] for p in items if p['name'].startswith('排序测')]
        self.assertEqual(ids, [c, a, b], ids)
        # boot 里产品下拉也按 sort
        boot = call('/api/boot')[1]['products']
        bids = [p['id'] for p in boot if p['name'].startswith('排序测')]
        self.assertEqual(bids, [c, a, b], bids)
        # 只传子集：子集相对顺序改写，其余排到后面
        st, r = call('/api/product/reorder', {'ids': [b, a]})
        self.assertEqual(st, 200, r)
        ids = [p['id'] for p in call('/api/products')[1]['items'] if p['name'].startswith('排序测')]
        self.assertEqual(ids[:2], [b, a], ids)
        self.assertIn(c, ids)

    def test_2_delete_soft_and_trash_restore(self):
        pid = new_product('待删产品X', category='其他', remark='del-me')
        st, im = call('/api/impact?entity=product&id=%d' % pid)
        self.assertEqual(st, 200, im)
        self.assertFalse(im.get('block'), im)
        self.assertIn('待删产品X', im.get('title', ''))
        st, r = call('/api/product/delete', {'id': pid})
        self.assertEqual(st, 200, r)
        alive = [p for p in call('/api/products')[1]['items'] if p['id'] == pid]
        self.assertEqual(alive, [])
        trash = call('/api/trash')[1]['items']
        self.assertTrue(any(x['entity'] == 'product' and x['id'] == pid for x in trash), trash[:5])
        st, r = call('/api/restore', {'entity': 'product', 'id': pid})
        self.assertEqual(st, 200, r)
        self.assertTrue(any(p['id'] == pid for p in call('/api/products')[1]['items']))

    def test_3_ui_has_sortable_headers_and_delete_menu(self):
        js = open(os.path.join(ROOT, 'static', 'p_stock.js'), encoding='utf-8').read()
        self.assertIn("data-sk=", js)
        self.assertIn("ST.sort", js)
        self.assertIn('/api/product/reorder', js)
        self.assertIn("data-del=", js)
        self.assertIn("手动顺序", js)
        core = open(os.path.join(ROOT, 'static', 'core.js'), encoding='utf-8').read()
        self.assertIn('finish(false)', core)  # ✕ 关闭确认框会结束 Promise
        srv = open(os.path.join(ROOT, 'app', 'server.py'), encoding='utf-8').read()
        self.assertIn("/api/product/reorder", srv)
        ver = open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8').read()
        self.assertIn('点表头可按分类', ver)
        self.assertIn('行「⋯」可直接删除', ver)

if __name__ == '__main__':
    unittest.main(verbosity=2)
