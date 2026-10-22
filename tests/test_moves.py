"""库存变化记录（产品与库存 → 全部产品的每一笔变化，含盘点调整）、「库存流水里显示交接表批量配送」开关、
产品出入库情况 → 每日总出库量（看板）。截图：screens/moves_all.png、moves_toggle.png、daily_panel.png"""
import os, sys, unittest, subprocess, io, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule, ROOT, server  # noqa
import test_all, logic
from test_nav import HAVE, CHROME, run
OUT = os.path.join(ROOT, 'screens')
_done = []
def demo():
    if _done: return
    for n in '12': subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'demo_nextday.py'), test_all.URL, n], capture_output=True, check=True)
    _done.append(1)
def setting(v): st, r = call('/api/settings/save', {'data': {'moves_show_daily': v}}); assert st == 200, r

class M1_Moves(unittest.TestCase):
    @classmethod
    def setUpClass(cls): demo(); cls.m = logic.daily_map(server.db_c())

    def test_1_all_moves(self):
        st, r = call('/api/moves?from=2026-10-01'); self.assertEqual(st, 200)
        self.assertEqual(r['from'], '2026-10-01'); self.assertGreater(r['total'], 10)
        srcs = {x['src'] for x in r['items']}; self.assertTrue({'daily', 'count'} <= srcs, srcs)
        self.assertTrue(all(x['date'] >= '2026-10-01' for x in r['items']))
        self.assertEqual([x['date'] for x in r['items']], sorted([x['date'] for x in r['items']], reverse=True))   # 新的在上面
        d = next(x for x in r['items'] if x['src'] == 'daily'); self.assertTrue(d['label'].startswith('配送员 '), d); self.assertEqual(d['entity'], 'daily')
        st, rec = call('/api/record?entity=%s&id=%d' % (d['entity'], d['src_id'])); self.assertEqual(st, 200)   # 点一行能看原始记录
        k = next(x for x in r['items'] if x['src'] == 'count'); st, rec = call('/api/record?entity=count&id=%d' % k['src_id']); self.assertEqual(st, 200)
        # 筛选：来源、关键字（配送员）、分页
        r2 = call('/api/moves?from=2026-10-01&src=count')[1]; self.assertTrue(r2['items'] and all(x['src'] == 'count' for x in r2['items']))
        r3 = call('/api/moves?from=2026-10-01&q=' + urllib_q('丁增'))[1]; self.assertTrue(r3['items'] and all('丁增' in x['label'] for x in r3['items']))
        p1 = call('/api/moves?from=&limit=5&offset=0')[1]; p2 = call('/api/moves?from=&limit=5&offset=5')[1]
        self.assertEqual(len(p1['items']), 5); self.assertEqual(p1['total'], p2['total']); self.assertNotEqual(p1['items'][0], p2['items'][0])
        self.assertEqual(p1['total'], len(call('/api/moves?from=&limit=2000')[1]['items']))

    def test_2_balance_single_product(self):
        pid = self.m['shb']; r = call('/api/moves?from=&product_id=%d&limit=2000' % pid)[1]; self.assertTrue(r['single'])
        it = list(reversed(r['items']))   # 时间先后
        c = next(i for i, x in enumerate(it) if x['src'] == 'count' and x['date'] == '2026-10-18'); self.assertEqual(it[c]['bal'], 300)
        for a, b in zip(it[c:], it[c + 1:]):
            if b['src'] != 'count': self.assertAlmostEqual(b['bal'], a['bal'] + b['qty'])
        stock = next(p for p in call('/api/products')[1]['items'] if p['id'] == pid)['stock']['qty']
        self.assertAlmostEqual(it[-1]['bal'], stock)   # 最后的结存 = 系统库存
        self.assertIsNone(call('/api/moves?from=2026-10-01')[1]['items'][0].get('bal'))   # 全部产品时不给结存

    def test_3_xlsx_and_print(self):
        st, x = call('/api/moves.xlsx?from=2026-10-01'); self.assertEqual(st, 200); self.assertTrue(zipfile.ZipFile(io.BytesIO(x)).testzip() is None)
        j = call('/api/moves.xlsx?from=2026-10-01&fmt=json&product_id=%d' % self.m['shb'])[1]['sheets'][0]
        self.assertEqual(j['header'], ['日期', '产品', '来源', '说明', '批号', '数量', '结存']); self.assertIn('库存变化记录', j['title'])

    def test_4_toggle_hides_daily_display_only(self):
        pid = self.m['shb']; base = call('/api/moves?from=&product_id=%d&limit=2000' % pid)[1]
        nd = sum(1 for x in base['items'] if x['src'] == 'daily'); self.assertGreater(nd, 0)
        stock0 = next(p for p in call('/api/products')[1]['items'] if p['id'] == pid)['stock']['qty']
        setting(False)
        try:
            r = call('/api/moves?from=&product_id=%d&limit=2000' % pid)[1]
            self.assertFalse(any(x['src'] == 'daily' for x in r['items'])); self.assertEqual(r['hidden_daily'], nd)
            bal = {(x['src'], x['src_id'], x['date']): x['bal'] for x in base['items']}   # 结存照算（隐藏的那几笔也算进去）
            self.assertTrue(all(x['bal'] == bal[(x['src'], x['src_id'], x['date'])] for x in r['items']))
            self.assertEqual(next(p for p in call('/api/products')[1]['items'] if p['id'] == pid)['stock']['qty'], stock0)   # 库存不变
            t = call('/api/moves?from=&product_id=%d&limit=2000&daily=1' % pid)[1]; self.assertEqual(t['hidden_daily'], 0); self.assertEqual(t['total'], base['total'])   # 临时显示
            d = call('/api/product/moves?id=%d' % pid)[1]; self.assertFalse(any(m['src'] == 'daily' for m in d['moves'])); self.assertEqual(d['hidden_daily'], nd)
            d = call('/api/product/moves?id=%d&daily=1' % pid)[1]; self.assertTrue(any(m['src'] == 'daily' for m in d['moves'])); self.assertEqual(d['hidden_daily'], 0)
            post = call('/api/moves.xlsx?from=&fmt=json')[1]['sheets'][0]['post'][0]; self.assertTrue(post.startswith('已隐藏交接表批量配送'), post)
            self.assertFalse(call('/api/boot')[1]['settings']['moves_show_daily'])
        finally: setting(True)
        self.assertEqual(call('/api/moves?from=&product_id=%d&limit=2000' % pid)[1]['hidden_daily'], 0)

    def test_5_page_hide_daily_override(self):
        """本页 hide_daily=1 / daily=1 可覆盖设置（不改设置）"""
        pid = self.m['shb']; base = call('/api/moves?from=&product_id=%d&limit=2000' % pid)[1]
        nd = sum(1 for x in base['items'] if x['src'] == 'daily'); self.assertGreater(nd, 0)
        setting(True)
        r = call('/api/moves?from=&product_id=%d&limit=2000&hide_daily=1' % pid)[1]
        self.assertFalse(any(x['src'] == 'daily' for x in r['items'])); self.assertEqual(r['hidden_daily'], nd)
        self.assertEqual(call('/api/boot')[1]['settings']['moves_show_daily'], True)   # 设置没变
        setting(False)
        try:
            t = call('/api/moves?from=&product_id=%d&limit=2000&daily=1' % pid)[1]
            self.assertEqual(t['hidden_daily'], 0); self.assertEqual(t['total'], base['total'])
            self.assertFalse(call('/api/boot')[1]['settings']['moves_show_daily'])
        finally: setting(True)

    def test_6_daily_panel(self):
        r = call('/api/daily/panel?from=2026-10-17&to=2026-10-21')[1]
        self.assertEqual([d['date'] for d in r['days']], ['2026-10-17', '2026-10-18', '2026-10-19', '2026-10-20', '2026-10-21'])
        d = {x['date']: x for x in r['days']}
        tot = call('/api/daily?date=2026-10-19')[1]['total']   # 和财务表合计一致（待清点的不算）
        self.assertEqual(d['2026-10-19']['v']['o40'], tot['o40']); self.assertEqual(d['2026-10-19']['v']['R40'], tot['R40']); self.assertEqual(d['2026-10-19']['v']['net_shb'], tot['net_shb'])
        self.assertEqual(d['2026-10-19']['pending'], ['沈兴德'])                   # 有人待清点：标出来
        self.assertEqual(d['2026-10-19']['v'].get('hand:枕头'), 1)                 # 手工单产品
        self.assertTrue(d['2026-10-20']['pending'] and not d['2026-10-20']['v'])   # 10.21 早上还没录
        self.assertFalse(d['2026-10-18']['has'])
        self.assertIn('40L 实际配送', [c['name'] for c in r['cols']]); self.assertEqual(r['cols'][0], {'k': 'T40', 'name': '40L 钢瓶总出库'})   # 趋势图也能看总出库
        v, b = d['2026-10-19']['v'], d['2026-10-19']['cyl']['40']
        self.assertEqual(v['T40'], tot['R40'] + tot.get('hc40', 0) + tot.get('hn40', 0))                # 总出库 = 实际配送 + 手工单更换 + 手工单新送
        self.assertEqual((b['更换']['v'], b['新送']['v'], b['回收']['v']), (tot['J40'], tot['L40'], tot.get('r40', 0)))
        self.assertEqual(b['更换']['v'] + b['更换']['hand'] + b['新送']['v'] + b['新送']['hand'], v['T40']); self.assertEqual(b['新送']['parts'], [])   # 以后分 租用 / 购买
        self.assertNotIn('J40', v)

def urllib_q(s):
    import urllib.parse; return urllib.parse.quote(s)

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class M2_UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls): demo()
    def test_ui(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox']); errs = []
            try:
                pg = await (await br.new_context(viewport={'width': 1400, 'height': 820}, locale='zh-CN')).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(test_all.URL + '/#stock/moves'); await pg.wait_for_timeout(1500)
                n = await pg.evaluate("document.querySelectorAll('table.mv tbody tr').length"); self.assertGreater(n, 5)
                fit = await pg.evaluate("(() => { const t = document.querySelector('#mvT .tw'); return document.body.classList.contains('fit') && getComputedStyle(document.querySelector('table.mv thead th')).position; })()")
                self.assertEqual(fit, 'sticky')   # 一屏布局：只有表格滚，表头固定
                await pg.select_option('#mvS', 'daily'); await pg.wait_for_timeout(600)
                await pg.screenshot(path=os.path.join(OUT, 'moves_all.png'))
                await pg.click('table.mv tbody tr:first-child td:nth-child(4)'); await pg.wait_for_timeout(700)
                self.assertTrue(await pg.query_selector('.ov .kv'))   # 打开原始记录
                await pg.keyboard.press('Escape'); await pg.wait_for_timeout(200)
                await pg.evaluate("document.querySelectorAll('.ov').forEach(x => x.remove())")
                # 本页勾选「隐藏交接表批量配送」：只是不显示，有提示；取消勾选可再看（不改设置）
                setting(True)
                await pg.goto(test_all.URL + '/#stock/list'); await pg.wait_for_timeout(500); await pg.goto(test_all.URL + '/#stock/moves'); await pg.wait_for_timeout(500)
                await pg.reload(); await pg.wait_for_timeout(1500)
                await pg.select_option('#mvS', ''); await pg.wait_for_timeout(600)
                self.assertFalse(await pg.is_checked('#mvHideD'))
                await pg.check('#mvHideD'); await pg.wait_for_timeout(700)
                txt = await pg.inner_text('#mvT .hint'); self.assertIn('已隐藏交接表批量配送', txt)
                self.assertEqual(await pg.evaluate("[...document.querySelectorAll('table.mv tbody tr')].filter(r => r.textContent.includes('配送员 ')).length"), 0)
                await pg.screenshot(path=os.path.join(OUT, 'moves_toggle.png'))
                await pg.uncheck('#mvHideD'); await pg.wait_for_timeout(700)
                self.assertGreater(await pg.evaluate("[...document.querySelectorAll('table.mv tbody tr')].filter(r => r.textContent.includes('配送员 ')).length"), 0)
                self.assertTrue(call('/api/boot')[1]['settings']['moves_show_daily'])   # 本页勾选不改设置
                # 设置 → 其他 有全局开关；关掉后本页复选框默认勾上
                await pg.goto(test_all.URL + '/#settings/other'); await pg.wait_for_timeout(1200)
                self.assertTrue(await pg.is_checked('#sMvD'))
                setting(False)
                await pg.goto(test_all.URL + '/#stock/moves'); await pg.wait_for_timeout(1500)
                # MV 可能还留着上次本页的 daily=1，强制刷新页状态：走 list 再回来并清会话靠 reload 不够，直接看设置关掉时的提示路径
                await pg.evaluate("typeof MV!=='undefined' && (MV._inited=false, MV.hide_daily='', MV.daily='')")
                await pg.goto(test_all.URL + '/#stock/list'); await pg.wait_for_timeout(300)
                await pg.goto(test_all.URL + '/#stock/moves'); await pg.wait_for_timeout(1200)
                self.assertTrue(await pg.is_checked('#mvHideD'))
                self.assertIn('已隐藏交接表批量配送', await pg.inner_text('#mvT .hint, #mvT .empty'))
                setting(True)
                # 每日总出库量（看板）
                await pg.goto(test_all.URL + '/#daily/tot'); await pg.wait_for_timeout(1600)
                cards = await pg.evaluate("[...document.querySelectorAll('.dp-c')].map(c => c.querySelector('.dp-n').textContent + '=' + c.querySelector('.dp-v').textContent)")
                self.assertTrue(any(c.startswith('40L 钢瓶总出库') for c in cards), cards)
                await pg.click('.dp-c[data-k="T40"]'); await pg.wait_for_timeout(300)   # 点开：更换 / 新送 / 回收
                bd = await pg.inner_text('.dp-c[data-k="T40"] .dp-bd'); self.assertTrue(all(w in bd for w in ('更换', '新送', '回收', '实际配送')), bd)
                self.assertEqual(await pg.evaluate("document.querySelector('#dpK').value"), 'T40')
                self.assertIn('10月19日', await pg.inner_text('.dp .tools'))   # 默认最近一个算定的日子（10.20 还待清点）
                self.assertTrue(await pg.query_selector('.dp-w'))               # 19 号有人待清点：标出来
                self.assertGreater(await pg.evaluate("document.querySelectorAll('.dp-ch g.b').length"), 15)
                await pg.click('.dp-c[data-k="net_shb"]'); await pg.wait_for_timeout(300)
                self.assertEqual(await pg.evaluate("document.querySelector('#dpK').value"), 'net_shb')
                await pg.screenshot(path=os.path.join(OUT, 'daily_panel.png'), full_page=True)
                await pg.click('.dp-ch g.b[data-day="2026-10-17"]'); await pg.wait_for_timeout(1500)
                self.assertTrue(await pg.query_selector('#dTabs button.on[data-t="sum"]')); self.assertEqual(await pg.input_value('#dDate'), '2026-10-17')
                self.assertEqual(errs, [])
            finally: await br.close(); await pw.stop()
        run(go())

if __name__ == '__main__': unittest.main()
