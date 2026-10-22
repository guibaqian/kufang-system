"""报表 / 删除确认 / 记录来源 的浏览器测试（需要 playwright + Chrome）：python -m unittest tests.test_ui_links -v"""
import os, sys, unittest, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, new_product, setUpModule, tearDownModule  # noqa
import test_all, reports
from db import today as _today  # 盘点按今天记，测试单据也用今天（跨天运行不受影响）
from test_nav import HAVE, CHROME, run

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class U1_Report(unittest.TestCase):
    async def _pg(self):
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        self.b = await self.pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
        pg = await (await self.b.new_context(viewport={'width': 1440, 'height': 900})).new_page(); self.errs = []
        pg.on('pageerror', lambda e: self.errs.append(str(e)))
        return pg
    async def pin(self, pg):
        try: await pg.wait_for_selector('.pin-in', timeout=1500)
        except Exception: return
        await pg.fill('.pin-in', '1002'); await pg.press('.pin-in', 'Enter'); await pg.wait_for_selector('.pin-in', state='detached')
    async def btn(self, pg, text): await pg.click('.ov .dlg-f button:has-text("%s")' % text)
    async def row_of(self, pg, iso): return await pg.evaluate("iso => rConvRowOf(iso)", iso)

    def test_conv_add_delete_restore_link(self):
        async def go():
            pg = await self._pg(); U = test_all.URL
            await pg.goto(U + '/#report/conv'); await pg.wait_for_selector('#rAdd')
            # 1) 手动新增以前的某一天（插到按日期的位置），只填 40L
            await pg.click('#rAdd'); await pg.wait_for_selector('#caD')
            await pg.fill('#caD', '2026-03-05'); await pg.dispatch_event('#caD', 'change')
            await pg.fill('.oc input[data-c="B"]', '3'); await self.btn(pg, '保存'); await self.pin(pg)
            await pg.wait_for_function("rConvRowOf('2026-03-05')")
            r = await self.row_of(pg, '2026-03-05')
            prev = await pg.evaluate("r => rIso(rRaw(rTab('conv'), 'A', r - 1))", r); nxt = await pg.evaluate("r => rIso(rRaw(rTab('conv'), 'A', r + 1))", r)
            self.assertLess(prev, '2026-03-05'); self.assertGreater(nxt, '2026-03-05')
            self.assertEqual(await pg.evaluate("r => [rRaw(rTab('conv'),'B',r), rRaw(rTab('conv'),'D',r), rRaw(rTab('conv'),'H',r)]", r), [3, '', ''])  # 没有残留旧值
            srv = reports.get_raw(test_all.server.db_c(), 'conv'); self.assertEqual(reports._v(srv, 'B', r), 3)
            # 2) 写入入出库记录（联动）
            await pg.evaluate("r => { rPush(r); }", r); await pg.wait_for_selector('.ov .dlg-f button:has-text("写入并保存")'); await self.btn(pg, '写入并保存'); await self.pin(pg)
            await pg.wait_for_function("RP.k === 'ledger'")
            lr = await pg.evaluate("() => rTab('ledger').rows.findIndex(x => x && x.link && x.link.date === '2026-03-05') + 1"); self.assertGreater(lr, 0)
            self.assertTrue(await pg.query_selector('[data-src="%d"]' % lr))
            # 3) 删除换算表这一天：列出受影响的入出库记录，勾选一起删；输密码后马上保存
            await pg.evaluate("() => { RP.k = 'conv'; rRender(); }")
            r = await self.row_of(pg, '2026-03-05'); await pg.evaluate("r => document.querySelector('[data-del=\"' + r + '\"]').click()", r)
            await pg.wait_for_selector('.ov:has-text("确认删除")'); txt = await pg.inner_text('.ov .dlg-b')
            self.assertIn('入出库记录', txt); self.assertIn('批次剩余', txt); self.assertTrue(await pg.is_checked('#dlLinked'))
            await self.btn(pg, '删除并保存'); await self.pin(pg)
            await pg.wait_for_function("!rConvRowOf('2026-03-05') && !RP.dirty.conv")
            self.assertEqual(await pg.evaluate("() => rTab('ledger').rows.filter(x => x && x.link && x.link.date === '2026-03-05').length"), 0)
            # 4) 再新增同一天：提示回收站里有，可直接恢复（换算表 + 一起删的入出库记录都回来）
            await pg.click('#rAdd'); await pg.wait_for_selector('#caD'); await pg.fill('#caD', '2026-03-05'); await pg.dispatch_event('#caD', 'change')
            await pg.wait_for_selector('#caRs'); await pg.click('#caRs'); await self.pin(pg)
            await pg.wait_for_function("rConvRowOf('2026-03-05')")
            r = await self.row_of(pg, '2026-03-05'); self.assertEqual(await pg.evaluate("r => rRaw(rTab('conv'),'B',r)", r), 3)
            await pg.wait_for_function("RP.tabs.ledger && RP.tabs.ledger.rows.some(x => x && x.link && x.link.date === '2026-03-05' && !x.link.missing)")
            # 5) 已有这一天：不能重复新增，给「去改那一行」
            await pg.click('#rAdd'); await pg.wait_for_selector('#caD'); await pg.fill('#caD', '2026-03-05'); await pg.dispatch_event('#caD', 'change')
            await pg.wait_for_selector('#caGo'); await pg.click('#caGo')
            self.assertEqual(self.errs, []); await self.b.close(); await self.pw.stop()
        run(go())

    def test_prefs_and_view(self):
        async def go():
            pg = await self._pg(); U = test_all.URL
            await pg.goto(U + '/#report/ledger'); await pg.wait_for_selector('#rSetB')
            n0 = await pg.evaluate("() => document.querySelectorAll('#rGrid tbody tr').length")
            await pg.click('#rSetB'); await pg.wait_for_selector('#psCols')
            await pg.uncheck('#psCols input[data-v="B"]'); await pg.fill('#psCols input[data-l="K"]', '出库吨数')
            await pg.click('#psCols [data-up]:not([disabled]) >> nth=5')
            await pg.fill('#psFrom', '2026-09-01'); await pg.fill('#psTo', '2026-09-30')
            await self.btn(pg, '保存'); await self.pin(pg); await pg.wait_for_function("RP.prefs.ledger")
            heads = await pg.evaluate("() => [...document.querySelectorAll('#rGrid thead th')].map(x => x.textContent)")
            self.assertIn('出库吨数', heads); self.assertNotIn('入库日期', ''.join(heads[:1]))
            self.assertEqual(await pg.evaluate("() => rCols('ledger').includes('B')"), False)
            n1 = await pg.evaluate("() => document.querySelectorAll('#rGrid tbody tr').length"); self.assertLess(n1, n0); self.assertGreater(n1, 5)
            dates = await pg.evaluate("() => [...document.querySelectorAll('#rGrid tbody tr')].map(tr => rIso(rRaw(rTab('ledger'), 'I', +tr.dataset.r)))")
            self.assertTrue(all('2026-09-01' <= d <= '2026-09-30' for d in dates), dates)
            v = await pg.evaluate("() => rViewRows('ledger')"); self.assertEqual(len(v['header']), await pg.evaluate("() => rCols('ledger').length"))
            self.assertIn('出库吨数', v['header']); self.assertEqual(len(v['rows']), len(dates))
            p = call('/api/report/prefs')[1]['items']['ledger']; self.assertIn('B', p['hidden']); self.assertEqual(p['labels']['K'], '出库吨数')
            # 恢复默认
            await pg.click('#rSetB'); await pg.wait_for_selector('#psCols'); await self.btn(pg, '恢复默认'); await self.pin(pg)
            await pg.wait_for_function("!RP.prefs.ledger"); self.assertNotIn('ledger', call('/api/report/prefs')[1]['items'])
            self.assertEqual(self.errs, []); await self.b.close(); await self.pw.stop()
        run(go())

    def test_delete_confirm_and_drilldown(self):
        pid = new_product('界面联动瓶'); call('/api/count/save', {'product_id': pid, 'qty': 9})
        st, o = call('/api/out/save', {'data': {'date': _today(), 'kind': '销售出库', 'customer': '界面客户', 'items': [{'product_id': pid, 'qty': 4}]}}); assert st == 200, o
        async def go():
            pg = await self._pg(); U = test_all.URL
            await pg.goto(U + '/#stock'); await pg.wait_for_selector('#main .page')
            # 库存流水 → 点一条 → 原始出库单
            await pg.evaluate("pid => movesDlg({ id: pid, label: 'x' })", pid); await pg.wait_for_selector('tr.clk')
            await pg.click('tr.clk[data-src="out:%d"]' % o['id']); await pg.wait_for_selector('.ov:has-text("界面客户")')
            self.assertIn('-4', await pg.inner_text('.ov:last-of-type'))
            await pg.keyboard.press('Escape'); await pg.evaluate("() => document.querySelectorAll('.ov').forEach(x => x.remove())")
            # 删除确认：列出库存变化，必须勾选
            await pg.evaluate("id => { window._r = confirmDelete('out', id, '/api/out/delete'); }", o['id'])
            await pg.wait_for_selector('#cdOk'); txt = await pg.inner_text('.ov .dlg-b'); self.assertIn('5 → 9', txt)
            await self.btn(pg, '删除'); await pg.wait_for_timeout(200); self.assertTrue(await pg.query_selector('#cdOk'))   # 没勾不删
            await pg.check('#cdOk'); await self.btn(pg, '删除'); await self.pin(pg)
            self.assertTrue(await pg.evaluate("() => window._r"))
            self.assertTrue(call('/api/record?entity=out&id=%d' % o['id'])[1]['deleted'])
            self.assertEqual(self.errs, []); await self.b.close(); await self.pw.stop()
        run(go())

if __name__ == '__main__': unittest.main()
