"""自动测试：python -m unittest tests.test_all -v（需要 openpyxl 仅用于格式对比）"""
import os, sys, json, tempfile, unittest, threading, urllib.request, urllib.parse, io, zipfile, shutil, datetime
TMP = tempfile.mkdtemp(prefix='whtest_')
os.environ['WH_DATA'] = TMP; os.environ['WH_QUIET'] = '1'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, 'app'), os.path.join(ROOT, 'tests')]
import db, logic, server, backup, u8, importers, xlsxio  # noqa
from http.server import ThreadingHTTPServer

C = None; URL = None
def setUpModule():
    global C, URL
    C = server.bootstrap(); server.first_run_seed(C); C.commit()
    srv = ThreadingHTTPServer(('127.0.0.1', 0), server.H); URL = 'http://127.0.0.1:%d' % srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
def tearDownModule(): shutil.rmtree(TMP, ignore_errors=True)

def call(path, body=None, pin='1002', raw=None):
    if raw is not None:
        rq = urllib.request.Request(URL + path, data=raw, headers={'Content-Type': 'application/octet-stream', 'X-PIN': pin})
    elif body is not None:
        b = dict(body); b.setdefault('pin', pin)
        rq = urllib.request.Request(URL + path, data=json.dumps(b).encode(), headers={'Content-Type': 'application/json'})
    else: rq = urllib.request.Request(URL + path)
    try:
        with urllib.request.urlopen(rq) as r:
            d = r.read(); return (r.status, json.loads(d) if 'json' in r.headers.get('Content-Type', '') else d)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')

def new_product(name, **kw):
    st, r = call('/api/product/save', {'data': dict({'name': name, 'unit': '个', 'category': '其他'}, **kw)}); assert st == 200, r; return r['id']
def stock(pid): return call('/api/products')[1]['items'] and next(p for p in call('/api/products')[1]['items'] if p['id'] == pid)['stock']

class T1_Daily(unittest.TestCase):
    def test_roundtrip_format_vs_original(self):
        """导入原表 10.17 → 系统下载 10.17：值/公式/样式/合并/列宽/行高/冻结与原表 d01b2823 完全一致"""
        import compare
        out = os.path.join(TMP, 'rt.xlsx'); open(out, 'wb').write(server.daily_xlsx(C, '2026-10-17')) and None
        n = len(logic.daily_rows(C, '2026-10-17'))
        r = compare.compare(os.path.join(ROOT, 'templates', '产品出入库情况_原表.xlsx'), 'Sheet1', out, max_row=4 + 2 * n)   # 后面多余的空行已去掉
        # 只有「领取人信息」不同：不写车牌（6922丁增 → 丁增）
        self.assertTrue(all(d[0][:1] == 'A' and d[0][1:2].isdigit() or d[0][:2] == 'AH' for d in r['value_diffs']), r['value_diffs'])
        self.assertTrue(all(d[1].endswith(d[2]) and d[1] != d[2] for d in r['value_diffs']), r['value_diffs']); self.assertEqual(r['n_value_diffs'], 2 * n)
        self.assertEqual(r['n_style_diffs'], 0, r['style_diffs'])
        self.assertTrue(r['merges_equal'])
        # 用户要的排版调整（1.1.1）：A 列按名字收窄；S 列、AW–BJ 数字列统一 5.5；两行小表头 12 → 15 磅。其余列宽、行高同原表
        wdf = r['width_diffs']; self.assertTrue(set(wdf) <= {'A', 'S', 'AW'}, wdf); self.assertLess(wdf['A'][1], 16.75)
        self.assertTrue(all(v[1] == 5.5 for k, v in wdf.items() if k != 'A'), wdf)
        self.assertEqual(r['height_diffs'], {3: (12, 15), 4: (12, 15)})
        self.assertEqual(r['freeze'][0], r['freeze'][1])
    def test_merge_and_crossday(self):
        cid = call('/api/courier/save', {'data': {'name': '测试配送A'}})[1]['id']
        call('/api/daily/save', {'data': {'courier_id': cid, 'out_date': '2026-10-20', 'vals': {'o40': 3, 'e40': 1}}})
        call('/api/daily/save', {'data': {'courier_id': cid, 'out_date': '2026-10-20', 'vals': {'o40': 2, 'f10': 1}, 'note': '第二趟'}})
        st, r = call('/api/daily/save', {'data': {'courier_id': cid, 'out_date': '2026-10-19', 'vals': {'o10': 4}, 'open': True}})
        rows = [x for x in logic.daily_rows(server.db_c(), '2026-10-20') if x['courier_id'] == cid]
        self.assertEqual(len(rows), 1); self.assertEqual(rows[0]['vals']['o40'], 5); self.assertEqual(rows[0]['vals']['e40'], 1)
        self.assertNotIn('o10', rows[0]['vals'])  # 未交回的不进当天
        # 交回：记到 10-20，备注写 19–20 合并
        call('/api/daily/save', {'data': {'id': r['id'], 'courier_id': cid, 'out_date': '2026-10-19', 'book_date': '2026-10-20', 'vals': {'o10': 4, 'e10': 4}}})
        rows = [x for x in logic.daily_rows(server.db_c(), '2026-10-20') if x['courier_id'] == cid]
        self.assertEqual(rows[0]['vals']['o10'], 4); self.assertIn('19–20 合并', rows[0]['note']); self.assertIn('第二趟', rows[0]['note'])
        st, x = call('/api/daily/export.xlsx?date=2026-10-20'); self.assertEqual(st, 200)
        sh = xlsxio.read_sheet(x); names = [v for k, v in sh['cells'].items() if k != '_f' and k.startswith('A')]
        self.assertIn('测试配送A', names)
    def test_more_than_15_people_clones_rows(self):
        ids = [call('/api/courier/save', {'data': {'name': '多人%02d' % i}})[1]['id'] for i in range(18)]
        for i in ids: call('/api/daily/save', {'data': {'courier_id': i, 'out_date': '2026-10-21', 'vals': {'o40': 1}}})
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(call('/api/daily/export.xlsx?date=2026-10-21')[1])); ws = wb.active
        got = [ws.cell(5 + 2 * k, 1).value for k in range(18)]
        self.assertEqual(got, ['多人%02d' % i for i in range(18)])
        self.assertTrue(str(ws['L%d' % (5 + 2 * 17)].value).startswith('='))  # 克隆行带公式
    def test_self_pickup_never_in_daily(self):
        p40 = logic.daily_map(server.db_c())['c40']
        call('/api/out/save', {'data': {'date': '2026-10-22', 'kind': '客户自提', 'customer': '某医院', 'source': 'app手工单', 'items': [{'product_id': p40, 'qty': 2}]}})
        self.assertFalse([x for x in logic.daily_rows(server.db_c(), '2026-10-22') if x['name'] == '客户自提'])
        self.assertNotIn('self_pickup_in_daily', call('/api/boot')[1]['settings'])

class T2_Stock(unittest.TestCase):
    def test_unknown_then_count_then_moves(self):
        pid = new_product('测试产品甲')
        self.assertFalse(stock(pid)['known'])  # 未盘点 → 未知
        call('/api/out/save', {'data': {'kind': '自提出库', 'customer': 'X', 'date': '2026-10-01', 'items': [{'product_id': pid, 'qty': 3}]}})
        self.assertFalse(stock(pid)['known'])  # 出库后仍是未知，不显示负数
        call('/api/count/save', {'product_id': pid, 'qty': 10, 'date': '2026-10-02'})
        self.assertEqual(stock(pid)['qty'], 10)  # 盘点前的出库不再计
        call('/api/out/save', {'data': {'kind': '自提出库', 'customer': 'X', 'date': '2026-10-03', 'items': [{'product_id': pid, 'qty': 4}]}})
        call('/api/arrival/save', {'data': {'date': '2026-10-04', 'product_id': pid, 'qty': 6, 'u8_status': '待入U8'}})
        self.assertEqual(stock(pid)['qty'], 12)
        call('/api/out/save', {'data': {'kind': '自提出库', 'customer': 'X', 'date': '2026-10-05', 'items': [{'product_id': pid, 'qty': 20}]}})
        s = stock(pid); self.assertTrue(s['warn'])  # 负数 → 页面显示「需复盘」
    def test_fifo_by_expiry(self):
        pid = new_product('测试批次品', batch_managed=1)
        call('/api/arrival/save', {'data': {'date': '2026-09-01', 'product_id': pid, 'qty': 5, 'batch_no': 'B-LATE', 'expiry': '2028-01-01'}})
        call('/api/arrival/save', {'data': {'date': '2026-09-02', 'product_id': pid, 'qty': 3, 'batch_no': 'B-EARLY', 'expiry': '2027-01-01'}})
        st, r = call('/api/out/save', {'data': {'kind': '自提出库', 'customer': 'Y', 'items': [{'product_id': pid, 'qty': 4}]}})
        o = call('/api/out/one?id=%d' % r['id'])[1]
        self.assertEqual([(i['batch_no'], i['qty']) for i in o['items']], [('B-EARLY', 3), ('B-LATE', 1)])
    def test_exact_match_no_prefix(self):
        a = new_product('鼻氧管'); b = new_product('鼻氧管加长')
        self.assertEqual(logic.find_product(server.db_c(), '鼻氧管加长')['id'], b)
        self.assertIsNone(logic.find_product(server.db_c(), '鼻氧'))

class T3_Safety(unittest.TestCase):
    def test_pin_required_and_audit(self):
        st, r = call('/api/pending/save', {'data': {'taker': '张总', 'what': '制氧机'}}, pin='9999'); self.assertEqual(st, 401)
        st, r = call('/api/pending/save', {'data': {'taker': '张总', 'what': '制氧机'}}, pin='1003'); self.assertEqual(st, 200)
        a = call('/api/audit?entity=pending&id=%d' % r['id'])[1]['items']; self.assertEqual(a[0]['person'], '演示录入乙')
    def test_pin_unique(self):
        st, r = call('/api/person/save', {'data': {'name': '新人', 'new_pin': '1001'}}); self.assertEqual(st, 400)
    def test_soft_delete_restore(self):
        pid = new_product('测试删恢复'); call('/api/count/save', {'product_id': pid, 'qty': 5, 'date': '2026-10-01'})
        st, r = call('/api/out/save', {'data': {'kind': '自提出库', 'customer': 'Z', 'date': '2026-10-02', 'items': [{'product_id': pid, 'qty': 2}]}})
        self.assertEqual(stock(pid)['qty'], 3)
        call('/api/out/delete', {'id': r['id']}); self.assertEqual(stock(pid)['qty'], 5)
        self.assertTrue(any(t['entity'] == 'out' and t['id'] == r['id'] for t in call('/api/trash')[1]['items']))
        call('/api/restore', {'entity': 'out', 'id': r['id']}); self.assertEqual(stock(pid)['qty'], 3)
    def test_u8_type_optional_and_remembered(self):
        pid = new_product('测试U8类型')
        st, r = call('/api/out/save', {'data': {'kind': '销售出库', 'source': 'U8单', 'customer': 'W', 'items': [{'product_id': pid, 'qty': 1}]}}); self.assertEqual(st, 200)
        call('/api/out/save', {'data': {'kind': '销售出库', 'source': 'U8单', 'u8_no': '123', 'u8_type': '新类型甲', 'customer': 'W', 'items': [{'product_id': pid, 'qty': 1}]}})
        self.assertIn('新类型甲', call('/api/boot')[1]['settings']['u8_types'])
        self.assertFalse([p for p in call('/api/pending')[1]['items'] if '类型' in (p['what'] or '')])
    def test_misc_flow(self):
        st, r = call('/api/misc/save', {'data': {'name': '灰色管件', 'category': '工程', 'qty': '约20根'}}); self.assertEqual(st, 200)
        call('/api/misc/action', {'id': r['id'], 'action': 'convert', 'name': '灰色PVC管件', 'unit': '根', 'qty': 20})
        t = [x for x in call('/api/misc?status=' + urllib.parse.quote('已转入库'))[1]['items'] if x['id'] == r['id']][0]
        self.assertTrue(t['product_id']); self.assertEqual(stock(t['product_id'])['known'], False)  # 不猜库存，等盘点
    def test_backup_restore(self):
        st, r = call('/api/backup/now', {}); self.assertEqual(st, 200)
        z = call('/api/export.zip')[1]; self.assertIn('warehouse.db', zipfile.ZipFile(io.BytesIO(z)).namelist())
        new_product('备份后新加的')
        st, r = call('/api/import', raw=z, pin='1001'); self.assertEqual(st, 200, r)
        self.assertFalse([p for p in call('/api/products')[1]['items'] if p['name'] == '备份后新加的'])

class T4_Seed(unittest.TestCase):
    def test_u8_catalog_no_qty(self):
        c = server.db_c()
        self.assertGreater(c.execute('SELECT COUNT(*) FROM u8_items').fetchone()[0], 40)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM u8_items WHERE qty IS NOT NULL').fetchone()[0], 0)
        for code, name, spec in c.execute("SELECT code,name,spec FROM u8_items WHERE match='自动匹配'"):
            pass
        # 氩气瓶不能被自动配到氮气瓶
        bad = c.execute("SELECT COUNT(*) FROM u8_items u JOIN products p ON p.id=u.product_id WHERE u.name LIKE '%氩%' AND p.name LIKE '%氮%'").fetchone()[0]
        self.assertEqual(bad, 0)
    def test_migration(self):
        rep = db.meta_get(server.db_c(), 'migration_report')
        self.assertGreater(rep['out'], 50); self.assertFalse(rep.get('unmatched_items'))
    def test_api_smoke_get(self):
        for p in ['boot', 'home', 'products', 'out', 'daily', 'arrivals', 'batches', 'pending', 'misc', 'people', 'u8', 'audit', 'trash', 'backup/list', 'counts']:
            st, _ = call('/api/' + p); self.assertEqual(st, 200, p)
        for p in ['/', '/m/', '/core.js', '/m/m.js', '/lib/xlsx.full.min.js']:
            st, _ = call(p); self.assertEqual(st, 200, p)

if __name__ == '__main__': unittest.main(verbosity=2)
