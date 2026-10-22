"""数据联动：换算表→入出库记录、报表行回收站、删除影响清单、记录来源查看、报表显示设置：python -m unittest tests.test_links -v"""
import os, sys, json, copy, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, new_product, stock, setUpModule, tearDownModule  # noqa
import test_all, server, reports, xlgrid, logic, db
from db import today as _today  # 盘点按今天记，测试单据也用今天（跨天运行不受影响）

def tab(k): return call('/api/report?key=' + k)[1]
def save_tabs(tabs, trash=None, summary='测试'):
    st, r = call('/api/report/save', {'tabs': {k: {'rows': t['rows'], 'merges': t['merges'], 'version': t['version']} for k, t in tabs.items()}, 'summary': summary, 'trash': trash or []})
    assert st == 200, r; return r
def conv_rows(t):
    rg = reports.ranges('conv', t); return {reports.norm_date(reports._v(t, 'A', r)): r for r in range(rg['start'], rg['main_end'] + 1) if reports.norm_date(reports._v(t, 'A', r))}
def add_conv(t, iso, vals):
    """照前端 rAddConvRow：复制最后一行的公式，日期 + 用量，其余清空"""
    rg = reports.ranges('conv', t); last = rg['main_end']; at = last + 1
    for r in range(rg['start'], last + 1):
        d = reports.norm_date(reports._v(t, 'A', r))
        if d and d > iso: at = r; break
    src = copy.deepcopy(t['rows'][last - 1]); xlgrid.insert_row(t, at, {'c': {}}); prev = last + (1 if at <= last else 0)
    dr = at - prev; new = {'c': {}}
    for col, cc in src['c'].items():
        if cc.get('f'): new['c'][col] = {'f': xlgrid.offset_formula(cc['f'], dr, 0)}
    new['c']['A'] = {'v': '%d.%d.%d' % (int(iso[:4]), int(iso[5:7]), int(iso[8:]))}
    for col, v in vals.items(): new['c'][col] = {'v': v}
    t['rows'][at - 1] = new; return at
def V(t, r): return xlgrid.Evaluator(t).cell('V', r)
def add_ledger(t, iso, qty, link=True):
    rg = reports.ranges('ledger', t); r = rg['main_end'] + 1
    while len(t['rows']) < r: t['rows'].append(None)
    x = {'c': {'I': {'v': '%d.%d.%d' % (int(iso[:4]), int(iso[5:7]), int(iso[8:]))}, 'J': {'v': '出创投'}, 'K': {'v': qty}, 'L': {'f': 'L%d-K%d' % (r - 1, r)}}}
    if link: x['link'] = {'k': 'conv', 'date': iso}
    if r <= len(t['rows']) and t['rows'][r - 1] is not None: xlgrid.insert_row(t, r, {'c': {}})
    t['rows'][r - 1] = x
    return r

class L1_ConvLedger(unittest.TestCase):
    def test_a_edit_conv_updates_ledger(self):
        c, l = tab('conv'), tab('ledger')
        r = add_conv(c, '2031-01-05', {'B': 10}); save_tabs({'conv': c})
        c = tab('conv'); v0 = V(c, r)
        lr = add_ledger(l, '2031-01-05', 0.01); res = save_tabs({'ledger': l})
        self.assertEqual(res['synced'], ['ledger'])           # 保存时就按换算表对齐
        l = tab('ledger'); self.assertAlmostEqual(reports._v(l, 'K', lr), round(v0, 2))
        c['rows'][r - 1]['c']['B'] = {'v': 20}; res = save_tabs({'conv': c})
        self.assertEqual(res['synced'], ['ledger']); self.assertTrue(res['sync_notes'])
        c2, l2 = tab('conv'), tab('ledger')
        self.assertGreater(V(c2, r), v0); self.assertAlmostEqual(reports._v(l2, 'K', lr), reports._r2(V(c2, r)))
        # 批次剩余 L 是公式，跟着变
        ev = xlgrid.Evaluator(l2); self.assertAlmostEqual(ev.cell('L', lr), ev.cell('L', lr - 1) - reports._v(l2, 'K', lr))

    def test_b_upgrade_migration_1018(self):
        """升级一次：以前已经改过的 10.18（10L=41）那行，入出库记录跟着重算"""
        c, l = tab('conv'), tab('ledger')
        r = add_conv(c, '2032-10-18', {'B': 382, 'D': 41}); save_tabs({'conv': c})
        lr = add_ledger(l, '2032-10-18', 9.99, link=False)   # 旧版本用「→记录」写进去的：没有联动标记，数是改之前的
        save_tabs({'ledger': l}, summary='换算表 2032.10.18 总计写入入出库记录')
        l = tab('ledger'); hand = add_ledger(l, '2032-10-20', '1.5+2', link=False); save_tabs({'ledger': l})  # 手填的不动
        before = json.dumps(tab('ledger')['rows'][:lr - 1], ensure_ascii=False)
        cn = server.db_c(); cn.execute("DELETE FROM meta WHERE k='report_links_v1'"); cn.commit()
        ch = reports.migrate_links(cn); cn.commit()
        self.assertEqual(len(ch), 1, ch); self.assertIn('2032-10-18', ch[0])
        self.assertEqual(json.dumps(tab('ledger')['rows'][:lr - 1], ensure_ascii=False), before)   # 以前的行一格都没动
        self.assertEqual(reports._v(tab('ledger'), 'K', hand), '1.5+2')
        l2 = tab('ledger'); c2 = tab('conv')
        self.assertEqual(l2['rows'][lr - 1].get('link'), {'k': 'conv', 'date': '2032-10-18'})
        self.assertAlmostEqual(reports._v(l2, 'K', lr), reports._r2(V(c2, r))); self.assertNotEqual(reports._v(l2, 'K', lr), 9.99)
        v = tab('ledger')['version']; server.upgrade(cn); self.assertEqual(tab('ledger')['version'], v)   # 只做一次

    def test_c_delete_restore_readd(self):
        c, l = tab('conv'), tab('ledger')
        r = add_conv(c, '2033-03-03', {'B': 7}); save_tabs({'conv': c}); c = tab('conv')
        lr = add_ledger(l, '2033-03-03', 0); save_tabs({'ledger': l}); l = tab('ledger'); k0 = reports._v(l, 'K', lr)
        # 只删换算表那行：入出库记录那行标「换算表里没有了」
        row = c['rows'][r - 1]; xlgrid.delete_row(c, r)
        res = save_tabs({'conv': c}, trash=[{'key': 'conv', 'r': r, 'row': row}])
        l = tab('ledger'); self.assertTrue(l['rows'][lr - 1]['link'].get('missing')); self.assertEqual(reports._v(l, 'K', lr), k0)
        tr = call('/api/report/trash?key=conv&date=2033-03-03')[1]['items']; self.assertEqual(len(tr), 1)
        self.assertIn('report_row', [x['entity'] for x in call('/api/trash')[1]['items']])
        # 删掉的那天可以重新加（不被回收站挡住）……
        c = tab('conv'); r2 = add_conv(c, '2033-03-03', {'B': 9}); save_tabs({'conv': c})
        self.assertIn('2033-03-03', conv_rows(tab('conv')))
        l = tab('ledger'); self.assertFalse(l['rows'][lr - 1]['link'].get('missing'))
        # ……这时候再从回收站恢复同一天：拒绝并说明
        st, e = call('/api/restore', {'entity': 'report_row', 'id': tr[0]['id']}); self.assertEqual(st, 400); self.assertIn('已经有', e['error'])
        # 删掉新加的，再从回收站恢复旧的：回到按日期的位置，联动接上，出库量按 B=7 重算
        c = tab('conv'); rr = conv_rows(c)['2033-03-03']; xlgrid.delete_row(c, rr); save_tabs({'conv': c})
        st, x = call('/api/restore', {'entity': 'report_row', 'id': tr[0]['id']}); self.assertEqual(st, 200, x)
        c = tab('conv'); self.assertEqual(conv_rows(c)['2033-03-03'], x['r']); self.assertEqual(reports._v(c, 'B', x['r']), 7)
        l = tab('ledger'); self.assertAlmostEqual(reports._v(l, 'K', lr), reports._r2(V(c, x['r'])))
        self.assertEqual(call('/api/restore', {'entity': 'report_row', 'id': tr[0]['id']})[0], 400)   # 恢复过了

    def test_d_delete_with_linked_ledger_and_restore_both(self):
        c, l = tab('conv'), tab('ledger')
        add_conv(c, '2034-04-04', {'B': 5}); save_tabs({'conv': c}); c = tab('conv')
        add_ledger(l, '2034-04-04', 0); save_tabs({'ledger': l}); l = tab('ledger')
        r = conv_rows(c)['2034-04-04']; lr = next(i for i, x in enumerate(l['rows'], 1) if x and (x.get('link') or {}).get('date') == '2034-04-04')
        n_led = len([x for x in l['rows'] if x]); lrow = l['rows'][lr - 1]; crow = c['rows'][r - 1]
        nxt = l['rows'][lr] if lr < len(l['rows']) else None
        xlgrid.delete_row(c, r); xlgrid.delete_row(l, lr)
        save_tabs({'conv': c, 'ledger': l}, trash=[{'key': 'conv', 'r': r, 'row': crow}, {'key': 'ledger', 'r': lr, 'row': lrow}])
        tid = call('/api/report/trash?key=conv&date=2034-04-04')[1]['items'][0]['id']
        st, x = call('/api/restore', {'entity': 'report_row', 'id': tid}); self.assertEqual(st, 200, x)
        self.assertEqual(len(x['also']), 1)      # 一起删的入出库记录行也回来了
        l = tab('ledger'); hit = [i for i, y in enumerate(l['rows'], 1) if y and (y.get('link') or {}).get('date') == '2034-04-04']
        self.assertEqual(len(hit), 1); ev = xlgrid.Evaluator(l); h = hit[0]
        self.assertEqual(l['rows'][h - 1]['c']['L']['f'].replace(' ', ''), 'L%d-K%d' % (h - 1, h))
        if isinstance(ev.cell('L', h - 1), (int, float)): self.assertAlmostEqual(ev.cell('L', h), ev.cell('L', h - 1) - reports._v(l, 'K', h))

class L2_Prefs(unittest.TestCase):
    def test_prefs_roundtrip(self):
        st, r = call('/api/report/prefs/save', {'key': 'ledger', 'data': {'hidden': ['B', 'x;drop', 'C'], 'order': ['I', 'J', 'K'], 'labels': {'K': '出库(吨)', 'bad': 'x'},
                                                                        'from': '2026-01-01', 'to': 'xx', 'filters': [{'c': 'J', 'q': '创投'}, {'c': 'J', 'q': ''}]}})
        self.assertEqual(st, 200, r)
        p = call('/api/report/prefs')[1]['items']['ledger']
        self.assertEqual(p['hidden'], ['B', 'C']); self.assertEqual(p['labels'], {'K': '出库(吨)'}); self.assertEqual(p['from'], '2026-01-01'); self.assertEqual(p['to'], '')
        self.assertEqual(p['filters'], [{'c': 'J', 'q': '创投'}])
        # 官方 Excel 不受影响
        self.assertEqual(call('/api/report.xlsx?key=ledger')[0], 200)
        self.assertEqual(call('/api/report/prefs/save', {'key': 'ledger', 'data': {}}, pin='')[0], 401)
        call('/api/report/prefs/reset', {'key': 'ledger'}); self.assertNotIn('ledger', call('/api/report/prefs')[1]['items'])

    def test_prefs_widths(self):
        st, r = call('/api/report/prefs/save', {'key': 'stock', 'data': {'widths': {'A': 80, 'B': 160, '@u8': 100, 'bad': 9, '@x': 50}}})
        self.assertEqual(st, 200, r)
        w = call('/api/report/prefs')[1]['items']['stock']['widths']
        self.assertEqual(w['A'], 80); self.assertEqual(w['B'], 160); self.assertEqual(w['@u8'], 100)
        self.assertNotIn('bad', w); self.assertNotIn('@x', w)
        # clamp
        st, r = call('/api/report/prefs/save', {'key': 'stock', 'data': {'widths': {'A': 5, 'B': 9999}}})
        w = call('/api/report/prefs')[1]['items']['stock']['widths']
        self.assertEqual(w['A'], 36); self.assertEqual(w['B'], 800)
        call('/api/report/prefs/reset', {'key': 'stock'}); self.assertNotIn('stock', call('/api/report/prefs')[1]['items'])

    def test_prefs_stock_header_filter(self):
        """库存及到货总数表头筛选：允许 @u8；与字母列共用 filters"""
        st, r = call('/api/report/prefs/save', {'key': 'stock', 'data': {
            'from': '2026-09-01', 'to': '2026-10-20',
            'filters': [{'c': 'B', 'q': '氧气'}, {'c': '@u8', 'q': '待入U8'}, {'c': '@ph', 'q': 'x'}, {'c': 'bad', 'q': 'y'}],
            'widths': {'A': 72}
        }})
        self.assertEqual(st, 200, r)
        p = call('/api/report/prefs')[1]['items']['stock']
        self.assertEqual(p['from'], '2026-09-01'); self.assertEqual(p['to'], '2026-10-20')
        self.assertEqual(p['filters'], [{'c': 'B', 'q': '氧气'}, {'c': '@u8', 'q': '待入U8'}])
        self.assertEqual(p['widths']['A'], 72)
        # 前端表头筛选标记存在
        js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'p_report.js'), encoding='utf-8').read()
        self.assertIn('rFilterPop', js); self.assertIn('data-ff', js); self.assertIn('rPersistFilt', js)
        self.assertIn("c === '@u8'", js)
        call('/api/report/prefs/reset', {'key': 'stock'}); self.assertNotIn('stock', call('/api/report/prefs')[1]['items'])

class L3_Impact(unittest.TestCase):
    def test_out_arrival_loan_impact_and_record(self):
        pid = new_product('联动测试瓶'); call('/api/count/save', {'product_id': pid, 'qty': 10})
        st, a = call('/api/arrival/save', {'data': {'date': _today(), 'name': '联动测试瓶', 'qty': 5, 'product_id': pid}})
        self.assertEqual(st, 200, a); aid = a.get('id') or a['ids'][0]
        im = call('/api/impact?entity=arrival&id=%d' % aid)[1]
        self.assertTrue(any('15 → 10' in e for e in im['effects']), im); self.assertTrue(any('到货总数' in e for e in im['effects']))
        st, o = call('/api/out/save', {'data': {'date': _today(), 'kind': '销售出库', 'customer': '联动客户', 'items': [{'product_id': pid, 'qty': 20}]}}); self.assertEqual(st, 200, o)
        im = call('/api/impact?entity=out&id=%d' % o['id'])[1]
        self.assertTrue(any('-5 → 15' in e for e in im['effects']), im)
        im = call('/api/impact?entity=arrival&id=%d' % aid)[1]; self.assertTrue(any('负数' in e for e in im['effects']), im)
        rec = call('/api/record?entity=out&id=%d' % o['id'])[1]
        self.assertEqual(rec['moves'][0]['qty'], -20); self.assertEqual(rec['items'][0]['qty'], 20)
        # 删除 → 库存加回；恢复 → 再扣
        self.assertEqual(call('/api/out/delete', {'id': o['id']})[0], 200); self.assertEqual(stock(pid)['qty'], 15)
        self.assertTrue(call('/api/record?entity=out&id=%d' % o['id'])[1]['deleted'])
        call('/api/restore', {'entity': 'out', 'id': o['id']}); self.assertEqual(stock(pid)['qty'], -5)

    def test_loan_return_impact(self):
        pid = new_product('联动借用机'); call('/api/count/save', {'product_id': pid, 'qty': 4})
        st, l = call('/api/loan/save', {'data': {'date': '2026-10-10', 'user_to': '联动李', 'orgs': ['一院'], 'need_return': 1, 'items': [{'product_id': pid, 'qty': 2, 'org': '一院'}]}}); self.assertEqual(st, 200, l)
        lid = l['id']; it = call('/api/loan/one?id=%d' % lid)[1]['items'][0]['id']
        self.assertEqual(call('/api/loan/return', {'loan_id': lid, 'date': '2026-10-12', 'items': [{'loan_item_id': it, 'qty': 2}]})[0], 200)
        rid = call('/api/loan/one?id=%d' % lid)[1]['returns'][0]['id']
        im = call('/api/impact?entity=loan_return&id=%d' % rid)[1]
        self.assertTrue(any('未还' in e for e in im['effects']), im); self.assertTrue(any('4 → 2' in e for e in im['effects']), im)
        im = call('/api/impact?entity=loan&id=%d' % lid)[1]; self.assertTrue(any('归还记录' in e for e in im['effects']), im)

    def test_paper_daily_cannot_be_deleted_alone(self):
        cid = call('/api/courier/save', {'data': {'name': '8888联动'}})[1]['id']
        st, r = call('/api/paper/save', {'data': {'date': '2026-12-01', 'session': '早上', 'form': 'prod', 'rows': [{'rid': 'a', 'plate': '8888', 'cells': {'R.shb': '3'}}]}}); self.assertEqual(st, 200, r)
        sid = r['id']; cn = server.db_c()
        did = cn.execute("SELECT id FROM daily_entries WHERE legacy LIKE ? AND deleted_at IS NULL", ('paper:%d:%%' % sid,)).fetchone()[0]
        im = call('/api/impact?entity=daily&id=%d' % did)[1]; self.assertIn('交接表', im['block']); self.assertEqual(im['links'][0]['entity'], 'paper')
        st, e = call('/api/daily/delete', {'id': did}); self.assertEqual(st, 400); self.assertIn('交接表', e['error'])
        rec = call('/api/record?entity=daily&id=%d' % did)[1]; self.assertEqual(rec['links'][0]['entity'], 'paper')
        im = call('/api/impact?entity=paper&id=%d' % sid)[1]; self.assertTrue(any('1 条' in x for x in im['effects']), im)
        self.assertEqual(call('/api/paper/delete', {'id': sid})[0], 200)
        st, e = call('/api/restore', {'entity': 'daily', 'id': did}); self.assertEqual(st, 400); self.assertIn('恢复那张交接表', e['error'])
        call('/api/restore', {'entity': 'paper', 'id': sid})
        self.assertEqual(cn.execute("SELECT COUNT(*) FROM daily_entries WHERE legacy LIKE ? AND deleted_at IS NULL", ('paper:%d:%%' % sid,)).fetchone()[0], 1)

    def test_slip_lox_link(self):
        st, s = call('/api/slip/save', {'data': {'plate': '藏A联动', 'gross': 30000, 'tare': 10000}}); self.assertEqual(st, 200, s)
        t = tab('lox'); rg = reports.ranges('lox', t); r = rg['last'] + 1
        while len(t['rows']) < r: t['rows'].append(None)
        t['rows'][r - 1] = {'c': {'A': {'v': '2026.10.19'}, 'B': {'v': '藏A联动'}, 'D': {'v': 20}}, 'link': {'k': 'slip', 'ids': [s['id']], 'net': 20000}}
        call('/api/report/save', {'tabs': {'lox': {'rows': t['rows'], 'merges': t['merges'], 'version': t['version']}}, 'slip_ids': [s['id']]})
        self.assertFalse(tab('lox')['slip_state'][str(r)]['warn'])
        im = call('/api/impact?entity=slip&id=%d' % s['id'])[1]; self.assertTrue(any('第 %d 行' % r in e for e in im['effects']), im)
        self.assertEqual(call('/api/record?entity=slip&id=%d' % s['id'])[1]['links'][0]['r'], r)
        call('/api/slip/save', {'data': {'id': s['id'], 'sn': s['sn'], 'plate': '藏A联动', 'gross': 31000, 'tare': 10000}})
        self.assertIn('净重已改', tab('lox')['slip_state'][str(r)]['warn'])
        call('/api/slip/delete', {'id': s['id']}); self.assertIn('已删除', tab('lox')['slip_state'][str(r)]['warn'])

if __name__ == '__main__': unittest.main()
