# -*- coding: utf-8 -*-
"""1.1.41：借出按产品要还/不用还 + 首页便签（localStorage 文案）。"""
import os, json, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def R(*a):
    with open(os.path.join(ROOT, *a), encoding='utf-8') as f:
        return f.read()

class V1141_Static(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ver = R('app', 'version.py')
        cls.loan = R('app', 'loans.py')
        cls.db = R('app', 'db.py')
        cls.pl = R('static', 'p_loan.js')
        cls.m = R('static', 'm', 'm.js')
        cls.app = R('static', 'app.js')
        cls.css = R('static', 'app.css')
        with open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8') as f:
            cls.vj = json.load(f)

    def test_version(self):
        # 升版后仍保留 1.1.41 changelog；当前 VERSION 可能更高
        self.assertIn("'version': '1.1.41'", self.ver)
        self.assertRegex(self.ver, r"VERSION = '1\.1\.\d+'")
        self.assertRegex(self.vj.get('version') or '', r'^1\.1\.\d+$')
        self.assertIn('按单个产品', self.ver)
        self.assertIn('便签', self.ver)

    def test_schema_item_nr(self):
        self.assertIn("('loan_items', 'need_return', 'INTEGER')", self.db)
        self.assertIn('def item_need_return', self.loan)
        self.assertIn('need_return=?', self.loan)
        self.assertIn('INSERT INTO loan_items(loan_id,product_id,product_name,qty,approx,qty_text,org,batch_no,note,need_return)', self.loan)

    def test_pc_per_item_ui(self):
        self.assertIn('data-nr=', self.pl)
        self.assertIn('>要还</button>', self.pl)
        self.assertIn('>不用还</button>', self.pl)
        self.assertNotIn("id=\"needR\"", self.pl)  # 整单段已去掉
        self.assertIn('need_return: 1', self.pl)
        self.assertIn("!i.need_return ? ' <span class=\"muted\">不用还</span>'", self.pl)

    def test_mobile_per_item_ui(self):
        self.assertIn('data-nr=', self.m)
        self.assertNotIn("id=\"lR\"", self.m)
        self.assertIn('need_return: 1', self.m)
        self.assertIn("need_return: i.need_return === 0", self.m)

    def test_home_sticky(self):
        self.assertIn('HOME_STICKY_KEY', self.app)
        self.assertIn('wh_home_sticky_notes', self.app)
        self.assertIn('homeStickyMount', self.app)
        self.assertIn('homeStickies', self.app)
        self.assertIn('localStorage', self.app)
        self.assertIn('.home-stickies', self.css)
        self.assertTrue('.hs-note.c-y' in self.css or '.sticky.c-y' in self.css)
        # 不挡四键
        self.assertIn('class="acts4"', self.app)
        # 页面模板里四键在便签之前（函数定义里可能先出现 homeStickies 名）
        i_acts = self.app.index('class="acts4"')
        i_sticky = self.app.index('id="homeStickies"')
        self.assertLess(i_acts, i_sticky)


# API 行为（临时库）
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, new_product, stock, setUpModule, tearDownModule  # noqa

class V1141_LoanItemNr(unittest.TestCase):
    def setUp(self):
        self.a = new_product('混单氧罐%d' % id(self))
        self.b = new_product('混单鼻吸管%d' % id(self))
        call('/api/count/save', {'product_id': self.a, 'qty': 20, 'date': '2026-09-01'})
        call('/api/count/save', {'product_id': self.b, 'qty': 50, 'date': '2026-09-01'})

    def test_mixed_need_return_per_item(self):
        st, r = call('/api/loan/save', {'data': {
            'date': '2026-10-21', 'handler': '张三', 'orgs': ['示例一院'],
            'items': [
                {'product_id': self.a, 'qty': 2, 'org': '示例一院', 'need_return': 1},
                {'product_id': self.b, 'qty': 5, 'org': '示例一院', 'need_return': 0},
            ]}})
        self.assertEqual(st, 200, r)
        l = call('/api/loan/one?id=%d' % r['id'])[1]
        self.assertEqual(l['need_return'], 1)
        self.assertEqual(l['status'], '未归还')
        by = {i['product_id']: i for i in l['items']}
        self.assertEqual(by[self.a]['need_return'], 1)
        self.assertEqual(by[self.b]['need_return'], 0)
        self.assertEqual(by[self.a]['left'], 2)
        self.assertEqual(by[self.b]['left'], 0)
        # 库存：两项都扣（不用还也是出库口径）
        self.assertEqual(stock(self.a)['qty'], 18)
        self.assertEqual(stock(self.b)['qty'], 45)
        # 未还清单只有要还项
        o = call('/api/loan/outstanding?loan_id=%d' % r['id'])[1]
        self.assertEqual([x['item_id'] for x in o['items']], [by[self.a]['id']])
        # 归还要还项 → 已归还；不用还项不参与
        call('/api/loan/return', {'loan_id': r['id'], 'date': '2026-10-22', 'items': [{'loan_item_id': by[self.a]['id'], 'qty': 2}]})
        l2 = call('/api/loan/one?id=%d' % r['id'])[1]
        self.assertEqual(l2['status'], '已归还')
        self.assertEqual(stock(self.a)['qty'], 20)
        self.assertEqual(stock(self.b)['qty'], 45)  # 不用还不回流

    def test_legacy_order_level_fallback(self):
        # 旧客户端只传整单 need_return=0，明细不带 → 全部不用还 → 领用
        st, r = call('/api/loan/save', {'data': {
            'date': '2026-10-21', 'handler': '张三', 'user_to': '李工', 'need_return': 0,
            'items': [{'product_id': self.a, 'qty': 1}, {'product_id': self.b, 'qty': 2}]}})
        self.assertEqual(st, 200, r)
        l = call('/api/loan/one?id=%d' % r['id'])[1]
        self.assertEqual(l['status'], '领用')
        self.assertEqual(l['need_return'], 0)
        self.assertTrue(all(i['need_return'] == 0 for i in l['items']))
        self.assertEqual(call('/api/loan/outstanding?loan_id=%d' % r['id'])[1]['items'], [])

    def test_all_need_return_still_open(self):
        st, r = call('/api/loan/save', {'data': {
            'date': '2026-10-21', 'handler': '张三', 'orgs': ['二院'],
            'items': [{'product_id': self.a, 'qty': 1, 'need_return': 1}]}})
        self.assertEqual(st, 200, r)
        l = call('/api/loan/one?id=%d' % r['id'])[1]
        self.assertEqual(l['status'], '未归还')
        self.assertIn(r['id'], [x['id'] for x in call('/api/loans?status=open')[1]['items']])

    def test_reject_return_on_no_return_item(self):
        st, r = call('/api/loan/save', {'data': {
            'date': '2026-10-21', 'handler': '张三', 'user_to': '王',
            'items': [{'product_id': self.a, 'qty': 1, 'need_return': 0}]}})
        self.assertEqual(st, 200, r)
        iid = call('/api/loan/one?id=%d' % r['id'])[1]['items'][0]['id']
        st2, e = call('/api/loan/return', {'loan_id': r['id'], 'items': [{'loan_item_id': iid, 'qty': 1}]})
        self.assertEqual(st2, 400)
        self.assertIn('不用还', str(e.get('error') or e))

if __name__ == '__main__':
    unittest.main()
