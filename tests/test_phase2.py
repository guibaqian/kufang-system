"""第二阶段测试：借用归还 / 报表 / 称重单 / 领用出库单 / 打印数据"""
import os, sys, json, io, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, new_product, stock, setUpModule, tearDownModule, ROOT, TMP  # noqa
import test_all, server, logic, xlsxio

def pend(key):
    return [p for p in call('/api/pending')[1]['items'] if p.get('auto_key') == key] if True else []

class P0_DailyGrid(unittest.TestCase):
    def test_save_many_one_transaction(self):
        a = call('/api/courier/save', {'data': {'name': '表格甲'}})[1]['id']; b = call('/api/courier/save', {'data': {'name': '表格乙'}})[1]['id']
        st, r = call('/api/daily/save_many', {'items': [
            {'courier_id': a, 'out_date': '2026-10-24', 'book_date': '2026-10-24', 'vals': {'o40': 5, 'e40': 4}},
            {'courier_id': a, 'out_date': '2026-10-24', 'book_date': '2026-10-24', 'vals': {'o40': 2}, 'note': '第二趟'},
            {'courier_id': b, 'out_date': '2026-10-24', 'book_date': '2026-10-24', 'vals': {'o10': 3, 't_shb': 2}}]})
        self.assertEqual(st, 200, r); self.assertEqual(len(r['ids']), 3)
        rows = {x['courier_id']: x for x in logic.daily_rows(server.db_c(), '2026-10-24')}
        self.assertEqual(rows[a]['vals']['o40'], 7); self.assertEqual(rows[b]['vals']['t_shb'], 2)
        # 有一行错 → 整批不存
        st, e = call('/api/daily/save_many', {'items': [{'courier_id': a, 'out_date': '2026-10-25', 'vals': {'o40': 1}}, {'out_date': '2026-10-25', 'vals': {'o40': 1}}]})
        self.assertEqual(st, 400)
        self.assertFalse([x for x in logic.daily_rows(server.db_c(), '2026-10-25') if x['courier_id'] == a])
        st, e = call('/api/daily/save_many', {'items': [{'courier_id': a, 'out_date': '2026-10-26', 'book_date': '2026-10-25', 'vals': {'o40': 1}}]})
        self.assertEqual(st, 400)
        # 修改已有行（带 id）+ 不填密码被拒
        st, r2 = call('/api/daily/save_many', {'items': [{'id': r['ids'][0], 'courier_id': a, 'out_date': '2026-10-24', 'book_date': '2026-10-24', 'vals': {'o40': 6, 'e40': 4}}]})
        self.assertEqual(st, 200); self.assertEqual({x['courier_id']: x for x in logic.daily_rows(server.db_c(), '2026-10-24')}[a]['vals']['o40'], 8)
        st, e = call('/api/daily/save_many', {'items': []}, pin=''); self.assertIn(st, (401, 403))

class P1_Loans(unittest.TestCase):
    def setUp(self):
        self.a = new_product('借测呼吸机%d' % id(self)); self.b = new_product('借测管路%d' % id(self))
        call('/api/count/save', {'product_id': self.a, 'qty': 10, 'date': '2026-09-01'})
        call('/api/count/save', {'product_id': self.b, 'qty': 100, 'date': '2026-09-01'})
    def save(self, **kw):
        d = dict({'date': '2026-10-05', 'handler': '张三', 'user_to': '李医生', 'orgs': ['一院', '二院'], 'escort': '王工', 'need_return': 1, 'source': 'U8单', 'u8_no': 'JC001',
                  'items': [{'product_id': self.a, 'qty': 2, 'org': '一院'}, {'product_id': self.a, 'qty': 1, 'org': '二院'}, {'product_id': self.b, 'approx': 1, 'qty_text': '若干', 'org': '共用'}]}, **kw)
        st, r = call('/api/loan/save', {'data': d}); self.assertEqual(st, 200, r); return r
    def test_slip_multi_org_partial_and_finalize(self):
        r = self.save(); lid = r['id']; self.assertRegex(r['slip_no'], r'^JY20261005-\d\d$')
        l = call('/api/loan/one?id=%d' % lid)[1]
        self.assertEqual(l['status'], '未归还'); self.assertEqual(l['finalized'], 0); self.assertEqual(l['orgs'], ['一院', '二院'])
        self.assertEqual(stock(self.a)['qty'], 7)
        ps = [p for p in call('/api/pending')[1]['items'] if p.get('link_type') == 'loan' and p.get('link_id') == lid]
        self.assertTrue(ps and ps[0]['status'] == '待补全')       # 若干未定数 → 待补全
        i1, i2, i3 = [i['id'] for i in l['items']]
        call('/api/loan/return', {'loan_id': lid, 'date': '2026-10-08', 'items': [{'loan_item_id': i1, 'qty': 1}]})
        l = call('/api/loan/one?id=%d' % lid)[1]; self.assertEqual(l['status'], '部分归还'); self.assertEqual(stock(self.a)['qty'], 8)
        st, e = call('/api/loan/return', {'loan_id': lid, 'items': [{'loan_item_id': i2, 'qty': 5}]}); self.assertEqual(st, 400)   # 还多了
        # 第二次：管路清点 30 根，借出时其实是 30
        call('/api/loan/return', {'loan_id': lid, 'date': '2026-10-09', 'items': [{'loan_item_id': i1, 'qty': 1}, {'loan_item_id': i2, 'qty': 1}, {'loan_item_id': i3, 'qty': 30, 'final_qty': 30}]})
        l = call('/api/loan/one?id=%d' % lid)[1]
        self.assertEqual(l['status'], '已归还'); self.assertEqual(l['finalized'], 1); self.assertEqual(len(l['returns']), 2)
        self.assertEqual(stock(self.a)['qty'], 10); self.assertEqual(stock(self.b)['qty'], 100)
        ps = [p for p in call('/api/pending')[1]['items'] if p.get('link_type') == 'loan' and p.get('link_id') == lid]
        self.assertNotEqual(ps[0]['status'], '待补全')
    def test_return_by_org_total_allocates_oldest_first(self):
        l1 = self.save(date='2026-10-01', orgs=['三院'], items=[{'product_id': self.a, 'qty': 2}])['id']
        l2 = self.save(date='2026-10-03', orgs=['三院'], items=[{'product_id': self.a, 'qty': 3}])['id']
        o = call('/api/loan/outstanding?org=' + test_all.urllib.parse.quote('三院'))[1]
        self.assertEqual(sum(x['left'] for x in o['by_product'] if x['product_id'] == self.a), 5)
        st, r = call('/api/loan/return', {'org': '三院', 'date': '2026-10-10', 'items': [{'product_id': self.a, 'qty': 4}]}); self.assertEqual(st, 200, r)
        self.assertEqual(len(r['ids']), 2)
        self.assertEqual(call('/api/loan/one?id=%d' % l1)[1]['status'], '已归还')
        self.assertEqual(call('/api/loan/one?id=%d' % l2)[1]['items'][0]['returned'], 2)
        st, r = call('/api/loan/return', {'org': '三院', 'items': [{'product_id': self.a, 'qty': 5}]}); self.assertEqual(st, 400)
        h = call('/api/loan/org?org=' + test_all.urllib.parse.quote('三院'))[1]
        self.assertEqual([t['left'] for t in h['totals'] if t['product_id'] == self.a], [1])
        # 导出与打印数据一致
        st, x = call('/api/loan/org.xlsx?org=' + test_all.urllib.parse.quote('三院')); self.assertEqual(st, 200)
        js = call('/api/loan/org.xlsx?fmt=json&org=' + test_all.urllib.parse.quote('三院'))[1]
        sh = xlsxio.read_sheet(x); self.assertEqual(sh['cells']['A1'], js['sheets'][0]['title'])
        self.assertEqual([sh['cells'].get('%s2' % c) for c in 'ABCDEFGHIJ'], js['sheets'][0]['header'])
    def test_item_org_must_belong(self):
        st, r = call('/api/loan/save', {'data': {'date': '2026-10-05', 'handler': '张三', 'orgs': ['一院'], 'items': [{'product_id': self.a, 'qty': 1, 'org': '五院'}]}})
        self.assertEqual(st, 400)
        st, r = call('/api/loan/save', {'data': {'date': '2026-10-05', 'handler': '张三', 'orgs': ['一院'], 'items': [{'product_id': self.a, 'qty': 0}]}})
        self.assertEqual(st, 400)   # 主件必须有数
    def test_delete_restore_and_return_undo(self):
        lid = self.save(items=[{'product_id': self.a, 'qty': 2, 'org': '一院'}])['id']
        it = call('/api/loan/one?id=%d' % lid)[1]['items'][0]['id']
        rid = call('/api/loan/return', {'loan_id': lid, 'items': [{'loan_item_id': it, 'qty': 2}]})[1]['ids'][0]
        self.assertEqual(stock(self.a)['qty'], 10)
        call('/api/loan/return/delete', {'id': rid}, pin='1001')
        self.assertEqual(call('/api/loan/one?id=%d' % lid)[1]['status'], '未归还'); self.assertEqual(stock(self.a)['qty'], 8)
        call('/api/restore', {'entity': 'loan_return', 'id': rid}, pin='1001')
        self.assertEqual(call('/api/loan/one?id=%d' % lid)[1]['status'], '已归还')
        call('/api/loan/delete', {'id': lid}, pin='1001'); self.assertEqual(stock(self.a)['qty'], 10)
    def test_batch_backfill(self):
        rows = [{'date': '2026-08-01', 'handler': '赵六', 'unit': '四院', 'product_id': self.a, 'qty': 1, 'returned': 1, 'return_date': '2026-08-05'},
                {'date': '2026-08-01', 'handler': '赵六', 'unit': '四院', 'product_name': '借测新小件', 'qty': '若干'},
                {'date': '2026-08-02', 'handler': '赵六', 'user_to': '护士长', 'product_id': self.b, 'qty': 3}]
        st, r = call('/api/loan/batch', {'rows': rows}); self.assertEqual(st, 200, r); self.assertEqual(len(r['ids']), 2)
        l = call('/api/loan/one?id=%d' % r['ids'][0])[1]
        self.assertEqual(len(l['items']), 2); self.assertEqual(l['items'][1]['approx'], 1); self.assertEqual(l['finalized'], 0)
        self.assertEqual(l['items'][0]['returned'], 1)
    def test_lists_and_exports(self):
        self.save()
        d = call('/api/loans?status=open')[1]; self.assertTrue(d['items']); self.assertTrue(any(o['org'] == '一院' for o in d['orgs']))
        self.assertTrue(call('/api/loans?status=unfinal')[1]['items'])
        self.assertTrue(call('/api/loans?source=' + test_all.urllib.parse.quote('U8单'))[1]['items'])
        for u in ('/api/loans.xlsx?status=open', '/api/loan/slip.xlsx?id=%d' % d['items'][0]['id']):
            st, x = call(u); self.assertEqual(st, 200); self.assertEqual(x[:2], b'PK')
            self.assertIn('sheets', call(u + '&fmt=json')[1])


import threading, urllib.request, urllib.parse, zipfile, tempfile, compare, reports
from web import readb
def getjson(path): st, r = call(path); assert st == 200, (path, r); return r

class P2_Reports(unittest.TestCase):
    def test_a_downloads_identical_to_templates(self):
        for k, cfg in reports.TABS.items():
            st, data = call('/api/report.xlsx?sums=0&key=' + k); self.assertEqual(st, 200)
            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f: f.write(data)
            res = compare.compare(os.path.join(ROOT, 'templates', reports.BOOKS[cfg['book']]), cfg['sheet'], f.name)
            self.assertEqual(res['n_value_diffs'], 0, (k, res['value_diffs'])); self.assertEqual(res['n_style_diffs'], 0, k)
            self.assertTrue(res['merges_equal'] and res['widths_equal'] and res['heights_equal'], (k, res))
            self.assertEqual(res['sheetnames'], [cfg['sheet']])
    def test_save_version_conflict_and_audit(self):
        t = getjson('/api/report?key=yard4'); v = t['version']
        rows = t['rows'] + [{'c': {'A': {'v': '2026.10.20'}, 'B': {'v': '测A001'}, 'D': {'v': 12.5}}}]
        st, r = call('/api/report/save', {'tabs': {'yard4': {'rows': rows, 'merges': t['merges'], 'version': v}}, 'summary': '测试加一行'}); self.assertEqual(st, 200, r)
        t2 = getjson('/api/report?key=yard4'); self.assertEqual(t2['version'], v + 1); self.assertEqual(t2['rows'][-1]['c']['B']['v'], '测A001')
        st, r = call('/api/report/save', {'tabs': {'yard4': {'rows': rows, 'merges': t['merges'], 'version': v}}}); self.assertEqual(st, 409)
        st, r = call('/api/report/save', {'tabs': {'stock': {'rows': [], 'merges': [], 'version': 0}}}); self.assertEqual(st, 400)
        au = getjson('/api/audit?entity=report')['items']
        self.assertTrue(any('测试加一行' in (a.get('summary') or '') for a in au), au[:3])
        st, x = call('/api/report.xlsx?key=yard4'); import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(x)).active; self.assertIn('测A001', [ws.cell(r, 2).value for r in range(1, ws.max_row + 1)])
        st, r = call('/api/report/reset', {'key': 'yard4'}); self.assertEqual(st, 200)
        self.assertNotIn('测A001', json.dumps(getjson('/api/report?key=yard4')['rows'], ensure_ascii=False))
    def test_stock_tab_follows_arrivals(self):
        pid = new_product('报表测氧气瓶')
        st, r = call('/api/arrival/save', {'data': {'date': '2026-10-21', 'product_id': pid, 'qty': 7, 'u8_status': '待入U8'}}); self.assertEqual(st, 200, r)
        aid = r.get('id') or r.get('ids', [None])[0]
        rows = getjson('/api/report?key=stock')['rows']; hit = [x for x in rows if (x['c'].get('B') or {}).get('v') == '报表测氧气瓶']
        self.assertEqual(len(hit), 1); self.assertEqual(hit[0]['c']['A']['v'], '2026.10.21'); self.assertEqual(hit[0]['c']['E']['v'], 7)
        if aid:
            call('/api/arrival/delete', {'id': aid})
            rows = getjson('/api/report?key=stock')['rows']; self.assertFalse([x for x in rows if (x['c'].get('B') or {}).get('v') == '报表测氧气瓶'])
    def test_import_report_workbook(self):
        raw = readb(os.path.join(ROOT, 'templates', reports.BOOKS['A']))
        st, r = call('/api/report/import?name=A.xlsx&keys=conv', raw=raw); self.assertEqual(st, 200, r)
        st, r = call('/api/report/import?name=x.xlsx', raw=readb(os.path.join(ROOT, 'templates', '称重计量单.docx'))); self.assertNotEqual(st, 200)
    def test_get_never_holds_write_lock(self):
        server.db_c().execute("DELETE FROM report_tabs WHERE key='lox'"); server.db_c().commit()
        getjson('/api/report?key=lox')   # GET 里懒播种（写库）
        out = {}
        def w(): out['r'] = call('/api/slip/save', {'data': {'plate': '锁测1', 'gross': 30000, 'tare': 10000, 'sn': 'LOCK-1'}})
        th = threading.Thread(target=w); th.start(); th.join(8)
        self.assertFalse(th.is_alive(), 'POST 被 GET 占的写锁卡住'); self.assertEqual(out['r'][0], 200)

class P3_Slips(unittest.TestCase):
    def test_slip_flow(self):
        r0 = getjson('/api/slips'); sn = r0['next_sn']
        st, a = call('/api/slip/save', {'data': {'plate': '陕J65758', 'gross': '38000', 'tare': '15200', 'sn': sn, 'time': '2026-10-18T10:00:00', 'goods': '液氧'}})
        self.assertEqual(st, 200, a); self.assertEqual(a['net'], 22800)
        r1 = getjson('/api/slips'); self.assertGreater(r1['next_sn'], sn); self.assertIn('陕J65758', r1['plates'])
        st, e = call('/api/slip/save', {'data': {'plate': 'X', 'gross': 1, 'tare': 0, 'sn': sn}}); self.assertEqual(st, 409)
        st, e = call('/api/slip/save', {'data': {'plate': 'X', 'gross': 100, 'tare': 200}}); self.assertEqual(st, 400)
        st, e = call('/api/slip/save', {'data': {'plate': '', 'gross': 100, 'tare': 20}}); self.assertEqual(st, 400)
        st, d = call('/api/slip.docx?id=%d' % a['id']); self.assertEqual(st, 200)
        import re; xml = ''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', zipfile.ZipFile(io.BytesIO(d)).read('word/document.xml').decode()))
        self.assertNotIn('{{', xml); self.assertIn('22800', xml); self.assertIn('陕J65758', xml); self.assertIn(sn, xml)
        # 登记到液氧表 → 标记已用
        t = getjson('/api/report?key=lox')
        st, r = call('/api/report/save', {'tabs': {'lox': {'rows': t['rows'], 'merges': t['merges'], 'version': t['version']}}, 'slip_ids': [a['id']]}); self.assertEqual(st, 200, r)
        self.assertTrue([s for s in getjson('/api/slips')['items'] if s['id'] == a['id']][0]['used_at'])
        self.assertTrue(getjson('/api/slips.xlsx?fmt=json')['sheets'][0]['rows'])
        st, r = call('/api/slip/delete', {'id': a['id']}); self.assertEqual(st, 200)
        self.assertFalse([s for s in getjson('/api/slips')['items'] if s['id'] == a['id']])

class P4_Lingyong(unittest.TestCase):
    def test_lingyong_sign_flow(self):
        pid = new_product('领用测扳手'); call('/api/count/save', {'product_id': pid, 'qty': 10, 'date': '2026-09-01'})
        st, r = call('/api/out/save', {'data': {'date': '2026-10-18', 'kind': '领用出库', 'recipient': '李工', 'purpose': '维修', 'items': [{'product_id': pid, 'qty': 2}]}}); self.assertEqual(st, 200, r)
        oid = r['id']; self.assertEqual(stock(pid)['qty'], 8)
        p = pend('out_sign:%d' % oid); self.assertEqual(len(p), 1); self.assertEqual(p[0]['status'], '待补全')
        s = getjson('/api/out/slip.xlsx?id=%d&fmt=json' % oid)['sheets'][0]
        self.assertTrue(any('李工' in x for x in s['pre'])); self.assertTrue(any('签字' in x for x in s['post'])); self.assertEqual(s['rows'][0][2], 2)
        st, x = call('/api/out/slip.xlsx?id=%d' % oid); self.assertEqual(st, 200); import openpyxl
        ws = openpyxl.load_workbook(io.BytesIO(x)).active; txt = ' '.join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
        self.assertIn('领用人签字', txt); self.assertIn('领用测扳手', txt)
        self.assertEqual([o['signed'] for o in getjson('/api/out/lingyong?sign=todo')['items'] if o['id'] == oid], [0])
        png = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
        ph = call('/api/photo', {'data': png, 'tag': 'sign'})[1]['id']
        st, r = call('/api/out/sign', {'id': oid, 'photo_ids': [ph]}); self.assertEqual(st, 200, r)
        self.assertEqual(pend('out_sign:%d' % oid)[0]['status'], '已补全')
        self.assertEqual([o['signed'] for o in getjson('/api/out/lingyong?sign=done')['items'] if o['id'] == oid], [1])
        # 修改出库单不丢签字照片
        o = getjson('/api/out/one?id=%d' % oid); d = {k: o[k] for k in ('id', 'date', 'kind', 'recipient', 'purpose')}; d['items'] = [{'product_id': pid, 'qty': 3}]
        st, r = call('/api/out/save', {'data': d, 'photo_ids': []}); self.assertEqual(st, 200, r)
        self.assertEqual([o['signed'] for o in getjson('/api/out/lingyong')['items'] if o['id'] == oid], [1])
        self.assertTrue(getjson('/api/out/lingyong?fmt=json')['sheets'][0]['rows'])

class P5_Printables(unittest.TestCase):
    def test_print_data_matches_download(self):
        pid = new_product('打印测批次'); call('/api/arrival/save', {'data': {'date': '2026-09-01', 'product_id': pid, 'qty': 5, 'batch_no': 'PR-1'}})
        for path in ('/api/count/sheet.xlsx', '/api/batch/trace.xlsx?product_id=%d' % pid, '/api/pending/list.xlsx', '/api/out/export.xlsx', '/api/slips.xlsx', '/api/out/lingyong?xlsx=1'):
            j = getjson(path + ('&' if '?' in path else '?') + 'fmt=json'); self.assertTrue(j['sheets'] and j['sheets'][0]['header'], path)
            st, x = call(path); self.assertEqual(st, 200, path); import openpyxl
            ws = openpyxl.load_workbook(io.BytesIO(x)).worksheets[0]
            vals = [[c.value for c in r] for r in ws.iter_rows()]
            self.assertIn([str(v) for v in j['sheets'][0]['header']], [[str(v) for v in r[:len(j['sheets'][0]['header'])]] for r in vals], path)

class P6_RemarksAndEscort(unittest.TestCase):
    def test_remarks_saved_and_searchable(self):
        st, r = call('/api/pending/save', {'data': {'taker': '备注甲', 'what': '扳手', 'remark': '放在二楼柜子'}}); self.assertEqual(st, 200)
        self.assertEqual([x['remark'] for x in getjson('/api/pending')['items'] if x['id'] == r['id']], ['放在二楼柜子'])
        x = getjson('/api/pending/list.xlsx?fmt=json')['sheets'][0]; self.assertTrue(any('放在二楼柜子' in str(v) for row in x['rows'] for v in row))
        st, r = call('/api/misc/save', {'data': {'name': '灰色管件', 'category': '未知', 'remark': '工程队老王的'}}); self.assertEqual(st, 200)
        self.assertEqual([t['id'] for t in getjson('/api/misc?q=' + urllib.parse.quote('老王'))['items']], [r['id']])
        pid = new_product('备注测物品'); call('/api/count/save', {'product_id': pid, 'qty': 9, 'date': '2026-09-01', 'note': '盘点备注X'})
        self.assertTrue([c for c in getjson('/api/counts?product_id=%d' % pid)['items'] if c['note'] == '盘点备注X'])
        st, o = call('/api/out/save', {'data': {'date': '2026-10-18', 'kind': '自提出库', 'customer': '备注客户', 'items': [{'product_id': pid, 'qty': 1, 'note': '行备注Y'}]}}); self.assertEqual(st, 200, o)
        self.assertEqual([x['id'] for x in getjson('/api/out?q=' + urllib.parse.quote('行备注Y'))['items']], [o['id']])
        st, s1 = call('/api/slip/save', {'data': {'plate': '备A1', 'gross': 3000, 'tare': 1000, 'sn': 'RMK-1', 'note': '称重备注Z'}}); self.assertEqual(st, 200)
        self.assertEqual([x['id'] for x in getjson('/api/slips?q=' + urllib.parse.quote('称重备注Z'))['items']], [s1['id']])
    def test_loan_item_note_and_escort_column(self):
        pid = new_product('随车测物品'); call('/api/count/save', {'product_id': pid, 'qty': 10, 'date': '2026-09-01'})
        st, r = call('/api/loan/save', {'data': {'date': '2026-10-06', 'handler': '张三', 'orgs': ['某医院'], 'need_return': 1, 'remark': '单备注',
                                                 'items': [{'product_id': pid, 'qty': 2, 'note': '带充电器'}]}}); self.assertEqual(st, 200, r)
        self.assertEqual([l['id'] for l in getjson('/api/loans?q=' + urllib.parse.quote('带充电器'))['items']], [r['id']])
        h = getjson('/api/loan/org.xlsx?fmt=json&org=' + urllib.parse.quote('某医院'))['sheets'][0]
        self.assertNotIn('随车技术人员', h['header']); self.assertIn('备注', h['header'])
        self.assertTrue(any('带充电器' in str(v) for row in h['rows'] for v in row))
        st, r2 = call('/api/loan/save', {'data': {'date': '2026-10-07', 'handler': '张三', 'orgs': ['某医院'], 'escort': '王工', 'need_return': 1, 'items': [{'product_id': pid, 'qty': 1}]}})
        self.assertIn('随车技术人员', getjson('/api/loan/org.xlsx?fmt=json&org=' + urllib.parse.quote('某医院'))['sheets'][0]['header'])
        pre = getjson('/api/loan/slip.xlsx?fmt=json&id=%d' % r['id'])
        self.assertNotIn('随车技术人员', json.dumps(pre, ensure_ascii=False))
        st, rt = call('/api/loan/return', {'loan_id': r['id'], 'date': '2026-10-08', 'remark': '外包装破了', 'items': [{'loan_item_id': getjson('/api/loan/one?id=%d' % r['id'])['items'][0]['id'], 'qty': 1}]}); self.assertEqual(st, 200, rt)
        self.assertEqual([l['id'] for l in getjson('/api/loans?status=&q=' + urllib.parse.quote('外包装破了'))['items']], [r['id']])

if __name__ == '__main__': unittest.main()
