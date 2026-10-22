"""纸质交接表 → 产品出入库情况（d01b2823 格式）"""
import os, sys, io, json, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, new_product, stock, setUpModule, tearDownModule, ROOT, TMP  # noqa
import server, logic, importers, paper

def rows_of(date): return {x['name']: x for x in logic.daily_rows(server.db_c(), date)}

class T_Paper(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(paper.parse_cell('10+2'), (12, False)); self.assertEqual(paper.parse_cell('5退'), (5, True))
        self.assertEqual(paper.parse_cell(' 13t '), (13, True)); self.assertEqual(paper.parse_cell('20-3'), (17, False)); self.assertEqual(paper.parse_cell(''), (None, False))
        self.assertRaises(ValueError, paper.parse_cell, '五')

    def test_rebuild_original_from_paper(self):
        """把原表 10.17（d01b2823）每人的数拆成「早上 + 中午」两张纸录进 11.17：汇总、下载与原表逐格一致（除标题日期）。
        次日清点：早上表的左边算前一天，所以左边（退库）都录在中午；再录 11.18 早上（空）表，11.17 才算定"""
        with open(os.path.join(ROOT, 'templates', '产品出入库情况_原表.xlsx'), 'rb') as fh: orig = fh.read()
        ppl = importers.parse_daily_xlsx(orig)['people']
        cs = {k['name']: k['id'] for k in call('/api/boot')[1]['couriers']}
        D = '2026-11-17'
        lay = paper.default_layout(server.db_c())['cyl']
        cylL = {c['k']: (c['k'] if c['t'] == 'f' else 'i_' + c['fk']) for c in lay['L']}; cylR = {c['k']: (c['k'] if c['t'] == 'f' else 't_' + c['fk']) for c in lay['R']}
        sheets = {(s, f): [] for s in ('早上', '中午') for f in ('cyl', 'prod')}
        for i, p in enumerate(ppl):
            v = p['vals']; cid = cs[p['name']]
            for ses in ('早上', '中午'):
                half = (lambda x: x - x // 2) if ses == '早上' else (lambda x: x // 2)
                cc, pc = {}, {}
                for k, fk in cylL.items():
                    if v.get(fk) and ses == '中午': cc['L.' + k] = str(int(v[fk]))
                for k, fk in cylR.items():
                    if v.get(fk) and half(int(v[fk])): cc['R.' + k] = ('%d+0' % half(int(v[fk])))
                for o in logic.OTHER:
                    if o[0] == 'xyg': continue                     # 小氧罐在钢瓶表上
                    if v.get('t_' + o[0]) and half(int(v['t_' + o[0]])): pc['R.' + o[0]] = str(half(int(v['t_' + o[0]])))
                    if v.get('i_' + o[0]) and ses == '中午': pc['L.' + o[0]] = '%d退' % int(v['i_' + o[0]])
                    elif ses == '中午' and not v.get('i_' + o[0]): pc['L.' + o[0]] = '3'      # 车上剩余：不算库存、不进财务表
                note = p['note'] if ses == '早上' else ''
                if cc or note: sheets[(ses, 'cyl')].append({'rid': 'r%d' % i, 'plate': p['name'], 'courier_id': cid, 'cells': cc, 'note_l': note})
                if pc: sheets[(ses, 'prod')].append({'rid': 'r%d' % i, 'plate': p['name'], 'courier_id': cid, 'cells': pc})
        for (ses, f), rs in sheets.items():
            st, r = call('/api/paper/save', {'data': {'date': D, 'session': ses, 'form': f, 'rows': rs}}); self.assertEqual(st, 200, r)
        self.assertTrue(all(x.get('pending') for x in rows_of(D).values()))                      # 11.18 早上还没录：待次日清点
        zero = [{'rid': 'r%d' % i, 'plate': p['name'], 'courier_id': cs[p['name']], 'cells': {'L.e40': '0'}} for i, p in enumerate(ppl)]   # 第二天早上清点到每个人（车上没有就写 0）
        for f in ('cyl', 'prod'): self.assertEqual(call('/api/paper/save', {'data': {'date': '2026-11-18', 'session': '早上', 'form': f, 'rows': zero if f == 'cyl' else []}})[0], 200)
        a, b = rows_of('2026-10-17'), rows_of(D)
        for p in ppl:
            if not p['vals'] and not p['note']: continue
            self.assertEqual({k: v for k, v in a[p['name']]['vals'].items() if not k.startswith('b_')}, {k: v for k, v in b[p['name']]['vals'].items() if not k.startswith('b_')}, p['name'])
            self.assertEqual(a[p['name']]['note'], b[p['name']]['note'])
        import compare
        out = os.path.join(TMP, 'paper.xlsx'); 
        with open(out, 'wb') as fh: fh.write(server.daily_xlsx(server.db_c(), D))
        r = compare.compare(os.path.join(ROOT, 'templates', '产品出入库情况_原表.xlsx'), 'Sheet1', out, max_row=4 + 2 * len(b))   # 去掉了后面多余的空行
        nd = [d for d in r['value_diffs'] if d[0] != 'A1']                                   # 标题日期不同；领取人信息不写车牌（6922丁增 → 丁增）
        self.assertTrue(all(d[1].endswith(d[2]) and d[1] != d[2] for d in nd), nd); self.assertEqual(r['n_value_diffs'], 1 + 2 * len(b))
        self.assertEqual(r['n_style_diffs'], 0); self.assertTrue(r['merges_equal'])

    def test_stock_ret_and_onboard(self):
        """产品表：右边新装 = 领取（扣库存）；左边写「退」= 入库（加回）；没写「退」= 车上剩余（不动库存）"""
        cid = call('/api/courier/save', {'data': {'name': '7777测试'}})[1]['id']
        pid = logic.daily_map(server.db_c())['shb']
        call('/api/count/save', {'product_id': pid, 'qty': 100, 'date': '2026-11-01'})
        q0 = stock(pid)['qty']
        st, r = call('/api/paper/save', {'data': {'date': '2026-11-20', 'session': '早上', 'form': 'prod', 'rows': [{'rid': 'a', 'plate': '7777', 'cells': {'R.shb': '10+2', 'L.shb': '4'}}]}})
        self.assertEqual(st, 200, r); self.assertEqual(stock(pid)['qty'], q0 - 12)
        row = rows_of('2026-11-20')['7777测试']; self.assertEqual(row['vals'].get('t_shb'), 12); self.assertFalse(row['vals'].get('i_shb'))
        sid = r['id']; ts = r['sheet']['updated_at']
        st, r = call('/api/paper/save', {'data': {'id': sid, 'date': '2026-11-20', 'session': '早上', 'form': 'prod', 'rows': [{'rid': 'a', 'plate': '7777', 'cells': {'R.shb': '12', 'L.shb': '5退'}}]}, 'base_ts': ts})
        self.assertEqual(st, 200, r); self.assertEqual(stock(pid)['qty'], q0 - 7)
        self.assertFalse(rows_of('2026-11-20')['7777测试']['vals'].get('i_shb'))                 # 次日清点：早上表左边（写没写退）= 前一天的次日车上剩余；写了退的当天入库
        self.assertEqual(rows_of('2026-11-19')['7777测试']['vals'].get('v1_shb'), 5)
        # 旧版本再存 → 409；同日同场次再建一张 → 409；看不懂的格子 → 400
        self.assertEqual(call('/api/paper/save', {'data': {'id': sid, 'date': '2026-11-20', 'session': '早上', 'form': 'prod', 'rows': []}, 'base_ts': ts})[0], 409)
        self.assertEqual(call('/api/paper/save', {'data': {'date': '2026-11-20', 'session': '早上', 'form': 'prod', 'rows': []}})[0], 409)
        self.assertEqual(call('/api/paper/save', {'data': {'date': '2026-11-21', 'session': '早上', 'form': 'prod', 'rows': [{'plate': '7777', 'cells': {'R.shb': '五'}}]}})[0], 400)
        # 手机：同一车牌并进那一行（中午场次新建一张），钢瓶两场相加
        call('/api/paper/row', {'data': {'date': '2026-11-20', 'session': '早上', 'form': 'cyl', 'row': {'plate': '7777', 'cells': {'R.o40': '20', 'L.e40': '18'}}}})
        call('/api/paper/row', {'data': {'date': '2026-11-20', 'session': '中午', 'form': 'cyl', 'row': {'plate': '7777', 'cells': {'R.o40': '5'}}}})
        st, r = call('/api/paper/row', {'data': {'date': '2026-11-20', 'session': '早上', 'form': 'cyl', 'row': {'plate': '7777', 'cells': {'R.o40': '21', 'L.e40': '18'}}}})
        row = rows_of('2026-11-20')['7777测试']['vals']; self.assertEqual(row['o40'], 26); self.assertFalse(row.get('e40'))
        self.assertEqual(rows_of('2026-11-19')['7777测试']['vals']['e40'], 18)                      # 早上退库算前一天
        # 在外未交回 → 交回记到 11.22（X–Y 合并）
        p = call('/api/paper?date=2026-11-20')[1]; sh = next(s for s in p['sheets'] if s['form'] == 'cyl' and s['session'] == '中午')
        rs = sh['rows']; rs[0]['open'] = True
        self.assertEqual(call('/api/paper/save', {'data': {'id': sh['id'], 'date': '2026-11-20', 'session': '中午', 'form': 'cyl', 'rows': rs}, 'base_ts': sh['updated_at']})[0], 200)
        self.assertEqual(rows_of('2026-11-20')['7777测试']['vals']['o40'], 21)
        self.assertEqual(call('/api/paper/settle', {'sheet_id': sh['id'], 'rid': rs[0]['rid'], 'book_date': '2026-11-22'})[0], 200)
        r22 = rows_of('2026-11-22')['7777测试']; self.assertEqual(r22['vals']['o40'], 5); self.assertIn('20–22', r22['note'])
        # 删除整张表 → 记录和库存一起退回；回收站恢复 → 回来
        st, _ = call('/api/paper/delete', {'id': sid}); self.assertEqual(st, 200); self.assertEqual(stock(pid)['qty'], q0)
        call('/api/restore', {'entity': 'paper', 'id': sid}); self.assertEqual(stock(pid)['qty'], q0 - 7)

    def test_new_plate_creates_courier(self):
        st, r = call('/api/paper/save', {'data': {'date': '2026-11-23', 'session': '晚上', 'form': 'cyl', 'rows': [{'rid': 'z', 'plate': '8888新', 'extra': True, 'cells': {'R.o10': '3'}}]}})
        self.assertEqual(st, 200, r)
        self.assertIn('8888新', [k['name'] for k in call('/api/boot')[1]['couriers']])
        self.assertEqual(rows_of('2026-11-23')['8888新']['vals']['o10'], 3)



def moves_of(pid, batch=None):
    q = 'SELECT * FROM moves WHERE product_id=? AND src="daily"' + (' AND batch_no=?' if batch is not None else '')
    return [dict(r) for r in server.db_c().execute(q, (pid,) + ((batch,) if batch is not None else ()))]

class T_Paper2(unittest.TestCase):
    def test_driver_per_row_and_prefill(self):
        """车牌不绑定配送员：每行自己填；新名字自动加名单；下次预填上次的人；以前的表不改"""
        call('/api/paper/save', {'data': {'date': '2026-12-01', 'session': '早上', 'form': 'cyl', 'rows': [{'rid': 'a', 'plate': '6720', 'driver': '新司机甲', 'cells': {'R.o40': '5'}}]}})
        self.assertEqual(rows_of('2026-12-01')['新司机甲']['vals']['o40'], 5)
        pl = {p['plate']: p for p in call('/api/paper?date=2026-12-02')[1]['plates']}; self.assertEqual(pl['6720']['name'], '新司机甲')
        call('/api/paper/save', {'data': {'date': '2026-12-02', 'session': '早上', 'form': 'cyl', 'rows': [{'rid': 'a', 'plate': '6720', 'driver': '新司机乙', 'cells': {'R.o40': '7'}}]}})
        self.assertEqual(rows_of('2026-12-02')['新司机乙']['vals']['o40'], 7)
        self.assertEqual(rows_of('2026-12-01')['新司机甲']['vals']['o40'], 5)                     # 历史不改
        self.assertEqual({p['plate']: p for p in call('/api/paper?date=2026-12-01')[1]['plates']}['6720']['name'], '新司机甲')
        self.assertEqual({p['plate']: p for p in call('/api/paper?date=2026-12-03')[1]['plates']}['6720']['name'], '新司机乙')
        # 加一行新车牌 → 以后的表也有这个车牌；隐藏车牌
        call('/api/paper/save', {'data': {'date': '2026-12-02', 'session': '中午', 'form': 'cyl', 'rows': [{'rid': 'x', 'plate': 'A1234', 'driver': '新司机乙', 'extra': True, 'cells': {'R.o10': '1'}}]}})
        ps = [p['plate'] for p in call('/api/paper?date=2026-12-03')[1]['plates']]; self.assertIn('A1234', ps)
        call('/api/paper/plates', {'plates': [p for p in ps if p != 'A1234']})
        self.assertNotIn('A1234', [p['plate'] for p in call('/api/paper?date=2026-12-03')[1]['plates']])

    def test_batch_default_override_and_trace(self):
        """小氧罐：整张表默认批次（先进先出预填），某行可单独指定；批次追溯跟着走"""
        c = server.db_c(); pid = logic.daily_map(c)['xyg']
        call('/api/product/save', {'data': {'id': pid, 'batch_managed': 1}})
        for bn, ex in (('XB-OLD', '2027-01-01'), ('XB-NEW', '2028-01-01')):
            call('/api/batch/save', {'data': {'product_id': pid, 'batch_no': bn, 'expiry': ex}})
            call('/api/count/save', {'product_id': pid, 'batch_no': bn, 'qty': 50, 'date': '2026-11-30'})
        p = call('/api/paper?date=2026-12-05')[1]; fifo = p['bm'][str(pid)]['fifo']; self.assertTrue(fifo)
        self.assertEqual(fifo, next(b['batch_no'] for b in p['bm'][str(pid)]['batches'] if b['remain'] > 0))
        st, r = call('/api/paper/save', {'data': {'date': '2026-12-05', 'session': '早上', 'form': 'cyl', 'rows': [
            {'rid': 'a', 'plate': '6922', 'driver': '批次甲', 'cells': {'R.xyg': '6'}},
            {'rid': 'b', 'plate': '9255', 'driver': '批次乙', 'cells': {'R.xyg': '4'}, 'batches': {str(pid): 'XB-NEW'}}]}})
        self.assertEqual(st, 200, r); self.assertEqual(r['sheet']['batches'][str(pid)], fifo)
        self.assertEqual(-sum(m['qty'] for m in moves_of(pid, fifo) if m['date'] == '2026-12-05'), 6)
        self.assertEqual(-sum(m['qty'] for m in moves_of(pid, 'XB-NEW') if m['date'] == '2026-12-05'), 4)
        tr = call('/api/batch/trace?product_id=%d&batch_no=XB-NEW' % pid)[1]['rows']     # 批次追溯：这辆车拿的是 XB-NEW
        self.assertTrue(any('批次乙' in json.dumps(x, ensure_ascii=False) for x in tr), tr)
        # 改整张表默认批次 → 默认那几行跟着换，例外行不动
        st, r2 = call('/api/paper/save', {'data': {'id': r['id'], 'date': '2026-12-05', 'session': '早上', 'form': 'cyl', 'rows': r['sheet']['rows'], 'batches': {str(pid): 'XB-NEW'}}, 'base_ts': r['sheet']['updated_at']})
        self.assertEqual(st, 200, r2)
        self.assertEqual(-sum(m['qty'] for m in moves_of(pid, 'XB-NEW') if m['date'] == '2026-12-05'), 10)
        self.assertEqual(call('/api/paper/save', {'data': {'id': r['id'], 'date': '2026-12-05', 'session': '早上', 'form': 'cyl', 'rows': [], 'batches': {str(pid): '没有这个'}}})[0], 400)
        # 两张表都记了小氧罐 → pids 都含它（前端标黄核对，不拦）
        st, _ = call('/api/paper/save', {'data': {'date': '2026-12-05', 'session': '早上', 'form': 'prod', 'rows': [{'rid': 'a', 'plate': '6922', 'driver': '批次甲', 'cells': {'R.xyg': '2'}}]}}); self.assertEqual(st, 200)
        shs = call('/api/paper?date=2026-12-05')[1]['sheets']
        self.assertTrue(all(pid in next(r for r in s['rows'] if r['plate'] == '6922')['pids'] for s in shs))
        self.assertEqual(rows_of('2026-12-05')['批次甲']['vals']['t_xyg'], 8)                    # 两张表相加

    def test_edit_past_sheet_cell_history(self):
        """对账后改以前的表：逐格记录 旧→新/谁/何时，库存与汇总重算，操作记录有"""
        pid = logic.daily_map(server.db_c())['shb']
        call('/api/paper/save', {'data': {'date': '2026-12-20', 'session': '早上', 'form': 'cyl', 'rows': [{'rid': 'a', 'plate': '6922', 'driver': '对账甲'}]}})   # 配送员在钢瓶表填，产品表跟着
        st, r = call('/api/paper/save', {'data': {'date': '2026-12-20', 'session': '早上', 'form': 'prod', 'rows': [{'rid': 'a', 'plate': '6922', 'driver': '对账甲', 'cells': {'R.shb': '10'}}]}})
        q0 = stock(pid)['qty']
        rows = r['sheet']['rows']; rows[0]['cells'] = {'R.shb': '12', 'L.shb': '3退'}; rows[0]['note_l'] = '对账补'
        st, r2 = call('/api/paper/save', {'data': {'id': r['id'], 'date': '2026-12-20', 'session': '早上', 'form': 'prod', 'rows': rows}, 'base_ts': r['sheet']['updated_at']}, pin='1003')
        self.assertEqual(st, 200, r2)
        ed = {e['k']: e for e in r2['sheet']['edits']}
        self.assertEqual((ed['R.shb']['old'], ed['R.shb']['new'], ed['R.shb']['by']), ('10', '12', '演示录入乙'))
        self.assertEqual((ed['L.shb']['old'], ed['L.shb']['new']), ('', '3退')); self.assertIn('note_l', ed)
        self.assertEqual(stock(pid)['qty'], q0 + 10 - (12 - 3))   # 原来领 10；改成领 12、退 3
        v = rows_of('2026-12-20')['对账甲']['vals']; self.assertEqual(v['t_shb'], 12)
        self.assertEqual(rows_of('2026-12-19')['对账甲']['vals']['v1_shb'], 3)                        # 早上表左边 = 前一天的次日车上剩余
        au = call('/api/audit?entity=paper&id=%d' % r['id'])[1]['items']
        self.assertTrue(any('10→12' in a['summary'] for a in au))

    def test_layout_editor_new_sheets_only(self):
        """表格设置：改列（改名/加产品列/删列/换顺序）只影响新表；旧表照旧显示和计算"""
        c = server.db_c()
        for d_, s_ in (('2026-12-10', '早上'), ('2026-12-11', '下午')):
            call('/api/paper/save', {'data': {'date': d_, 'session': s_, 'form': 'cyl', 'rows': [{'rid': 'a', 'plate': '6922', 'driver': '布局甲'}]}})
        st, r_old = call('/api/paper/save', {'data': {'date': '2026-12-10', 'session': '早上', 'form': 'prod', 'rows': [{'rid': 'a', 'plate': '6922', 'driver': '布局甲', 'cells': {'R.shb': '4', 'R.zt': '1'}}]}})
        lay = call('/api/paper/layout')[1]
        L = lay['layout']; newp = new_product('交接表新品%d' % id(self))
        L['prod']['R'] = [x for x in L['prod']['R'] if x['k'] != 'zt']                     # 删 枕头
        L['prod']['R'][0]['n'] = '湿化杯(新)'; L['prod']['R'].reverse()                     # 改名 + 换顺序
        L['prod']['R'].append({'n': '新品', 't': 'p', 'pid': newp}); L['prod']['L'].append({'n': '新品', 't': 'p', 'pid': newp})
        st, e = call('/api/paper/layout', {'layout': L, 'plates': lay['plates'], 'sessions': lay['sessions'] + [{'n': '下午', 'on': True}]}); self.assertEqual(st, 200, e)
        self.assertEqual(call('/api/paper/layout', {'layout': dict(L, prod=dict(L['prod'], R=[{'n': '', 't': 'p', 'pid': newp}]))})[0], 400)
        p = call('/api/paper?date=2026-12-11')[1]
        self.assertIn('下午', p['sessions']); self.assertEqual(p['layout']['prod']['R'][-1]['k'], 'p%d' % newp)
        old = next(x for x in call('/api/paper?date=2026-12-10')[1]['sheets'] if x['form'] == 'prod'); self.assertIn('zt', [x['k'] for x in old['layout']['R']])   # 旧表保留原样
        call('/api/count/save', {'product_id': newp, 'qty': 20, 'date': '2026-12-01'})
        st, r = call('/api/paper/save', {'data': {'date': '2026-12-11', 'session': '下午', 'form': 'prod', 'rows': [{'rid': 'a', 'plate': '6922', 'driver': '布局甲', 'cells': {'R.shb': '2', 'R.p%d' % newp: '5', 'L.p%d' % newp: '1退', 'R.zt': '9'}}]}})
        self.assertEqual(st, 200, r)
        self.assertEqual(stock(newp)['qty'], 16)                                              # 财务表没有这列：照扣库存，备注写「另：」
        row = rows_of('2026-12-11')['布局甲']; self.assertEqual(row['vals'].get('t_shb'), 2); self.assertFalse(row['vals'].get('t_zt')); self.assertIn('另：', row['note'])
        # 旧表还能改，按它自己的列
        rows = old['rows']; rows[0]['cells']['R.zt'] = '2'
        self.assertEqual(call('/api/paper/save', {'data': {'id': old['id'], 'date': '2026-12-10', 'session': '早上', 'form': 'prod', 'rows': rows}, 'base_ts': old['updated_at']})[0], 200)
        self.assertEqual(rows_of('2026-12-10')['布局甲']['vals']['t_zt'], 2)
        call('/api/paper/layout', {'layout': lay['default'], 'plates': lay['plates'], 'sessions': lay['sessions']})

if __name__ == '__main__': unittest.main()
