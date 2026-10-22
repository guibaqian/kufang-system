# -*- coding: utf-8 -*-
"""1.1.43：已盘点批次不够接下一批；未盘点不强制；禁止新扣成负。"""
import os, sys, json, tempfile, unittest, threading, shutil
TMP = tempfile.mkdtemp(prefix='wh1143_')
os.environ['WH_DATA'] = TMP; os.environ['WH_QUIET'] = '1'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'app'), os.path.join(ROOT, 'tests')]
import logic, server
from http.server import ThreadingHTTPServer
import urllib.request

URL = None
def setUpModule():
    global URL
    C = server.bootstrap(); server.first_run_seed(C); C.commit()
    srv = ThreadingHTTPServer(('127.0.0.1', 0), server.H); URL = 'http://127.0.0.1:%d' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
def tearDownModule(): shutil.rmtree(TMP, ignore_errors=True)

def call(path, body=None, pin='1002'):
    if body is not None:
        b = dict(body); b.setdefault('pin', pin)
        rq = urllib.request.Request(URL + path, data=json.dumps(b).encode(), headers={'Content-Type': 'application/json'})
    else:
        rq = urllib.request.Request(URL + path)
    try:
        with urllib.request.urlopen(rq) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')

def new_product(name, **kw):
    st, r = call('/api/product/save', {'data': dict({'name': name, 'unit': '个', 'category': '其他'}, **kw)})
    assert st == 200, r; return r['id']

class BatchOverflow1143(unittest.TestCase):
    def test_version_and_ui_markers(self):
        ver = open(os.path.join(ROOT, 'app', 'version.py'), encoding='utf-8').read()
        self.assertIn("VERSION = '1.1.43'", ver)
        self.assertIn('接下一批', ver)
        vj = json.load(open(os.path.join(ROOT, 'static', 'v.json'), encoding='utf-8'))
        self.assertEqual(vj['version'], '1.1.43')
        core = open(os.path.join(ROOT, 'static', 'core.js'), encoding='utf-8').read()
        self.assertIn('function batchPlanSplit(', core)
        self.assertIn('function resolveOutBatchItems(', core)
        self.assertIn('askBatchOverflow', core)
        po = open(os.path.join(ROOT, 'static', 'p_out.js'), encoding='utf-8').read()
        self.assertIn('resolveOutBatchItems', po)
        self.assertIn('接下一批', po)
        logic_src = open(os.path.join(ROOT, 'app', 'logic.py'), encoding='utf-8').read()
        self.assertIn('def batch_remain_trusted', logic_src)
        self.assertIn('ignore_out_id', logic_src)
        st = open(os.path.join(ROOT, 'static', 'p_stock.js'), encoding='utf-8').read()
        self.assertIn('负库存是错账', st)

    def test_untrusted_manual_batch_no_force_split(self):
        """未盘点：手选批整笔扣，不强制拆到下一批（可把该批扣穿）。"""
        pid = new_product('未盘供氧器', batch_managed=1)
        call('/api/arrival/save', {'data': {'date': '2026-10-01', 'product_id': pid, 'qty': 5, 'batch_no': 'U-A', 'expiry': '2027-01-01'}})
        call('/api/arrival/save', {'data': {'date': '2026-10-02', 'product_id': pid, 'qty': 8, 'batch_no': 'U-B', 'expiry': '2028-01-01'}})
        c = server.db_c()
        self.assertFalse(logic.batch_remain_trusted(c, pid))
        st, r = call('/api/out/save', {'data': {'kind': '客户自提', 'source': 'app手工单', 'customer': '甲', 'items': [{'product_id': pid, 'qty': 7, 'batch_no': 'U-A'}]}})
        self.assertEqual(st, 200, r)
        o = call('/api/out/one?id=%d' % r['id'])[1]
        self.assertEqual([(i['batch_no'], i['qty']) for i in o['items']], [('U-A', 7)])
        rem = {b['batch_no']: b['remain'] for b in logic.batch_stock(c, pid)}
        self.assertEqual(rem['U-A'], -2)

    def test_trusted_overflow_fifo_and_block_negative(self):
        """已盘点：空批 FIFO 拆行；指定批不够溢出；总不够拒绝（不新扣成负）。"""
        pid = new_product('已盘供氧器', batch_managed=1)
        call('/api/arrival/save', {'data': {'date': '2026-10-01', 'product_id': pid, 'qty': 3, 'batch_no': 'T-EARLY', 'expiry': '2027-01-01'}})
        call('/api/arrival/save', {'data': {'date': '2026-10-02', 'product_id': pid, 'qty': 5, 'batch_no': 'T-LATE', 'expiry': '2028-01-01'}})
        # 产品级盘点 → 可信
        call('/api/count/save', {'product_id': pid, 'qty': 8, 'date': '2026-10-03'})
        c = server.db_c()
        self.assertTrue(logic.batch_remain_trusted(c, pid))
        # 空批 FIFO
        st, r = call('/api/out/save', {'data': {'kind': '客户自提', 'source': 'app手工单', 'customer': '乙', 'items': [{'product_id': pid, 'qty': 4}]}})
        self.assertEqual(st, 200, r)
        o = call('/api/out/one?id=%d' % r['id'])[1]
        self.assertEqual([(i['batch_no'], i['qty']) for i in o['items']], [('T-EARLY', 3), ('T-LATE', 1)])
        # 指定 LATE 不够 6：先 LATE 剩4，再 EARLY 已空 → 只剩 LATE 的？ EARLY 已扣光. remain LATE=4. need 6 → short 2 → 400
        st2, r2 = call('/api/out/save', {'data': {'kind': '客户自提', 'source': 'app手工单', 'customer': '丙', 'items': [{'product_id': pid, 'qty': 6, 'batch_no': 'T-LATE'}]}})
        self.assertEqual(st2, 400, r2)
        self.assertIn('不够', r2.get('error') or r2.get('message') or str(r2))
        # 指定 LATE 扣 4 整批 OK
        st3, r3 = call('/api/out/save', {'data': {'kind': '客户自提', 'source': 'app手工单', 'customer': '丁', 'items': [{'product_id': pid, 'qty': 4, 'batch_no': 'T-LATE'}]}})
        self.assertEqual(st3, 200, r3)
        o3 = call('/api/out/one?id=%d' % r3['id'])[1]
        self.assertEqual([(i['batch_no'], i['qty']) for i in o3['items']], [('T-LATE', 4)])
        rem = {b['batch_no']: b['remain'] for b in logic.batch_stock(server.db_c(), pid)}
        self.assertEqual(rem['T-EARLY'], 0)
        self.assertEqual(rem['T-LATE'], 0)

    def test_trusted_prefer_overflow_to_next(self):
        pid = new_product('溢出选下批', batch_managed=1)
        call('/api/arrival/save', {'data': {'date': '2026-10-01', 'product_id': pid, 'qty': 2, 'batch_no': 'P1', 'expiry': '2027-06-01'}})
        call('/api/arrival/save', {'data': {'date': '2026-10-02', 'product_id': pid, 'qty': 10, 'batch_no': 'P2', 'expiry': '2027-01-01'}})
        call('/api/arrival/save', {'data': {'date': '2026-10-03', 'product_id': pid, 'qty': 10, 'batch_no': 'P3', 'expiry': '2029-01-01'}})
        call('/api/count/save', {'product_id': pid, 'qty': 22, 'date': '2026-10-04'})
        # prefer P1(2) + next_prefer P3 → 不走更早效期的 P2
        st, r = call('/api/out/save', {'data': {'kind': '客户自提', 'source': 'app手工单', 'customer': '戊',
            'items': [{'product_id': pid, 'qty': 5, 'batch_no': 'P1', 'next_batch_no': 'P3'}]}})
        self.assertEqual(st, 200, r)
        o = call('/api/out/one?id=%d' % r['id'])[1]
        self.assertEqual([(i['batch_no'], i['qty']) for i in o['items']], [('P1', 2), ('P3', 3)])

    def test_api_batches_trusted_flag(self):
        pid = new_product('旗标品', batch_managed=1)
        call('/api/arrival/save', {'data': {'date': '2026-10-01', 'product_id': pid, 'qty': 1, 'batch_no': 'F1'}})
        items = call('/api/batches')[1]['items']
        row = next(x for x in items if x['id'] == pid)
        self.assertFalse(row['batch_trusted'])
        call('/api/count/save', {'product_id': pid, 'qty': 1, 'date': '2026-10-02'})
        row2 = next(x for x in call('/api/batches')[1]['items'] if x['id'] == pid)
        self.assertTrue(row2['batch_trusted'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
