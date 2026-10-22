"""报表行操作：每行「＋」在下方插入一行（含最后一行、长备注）、顶部「＋ 新增一行」。python -m unittest tests.test_ui_rows -v
原因记录（v1.1.1）：在最后一行点「＋」时插入的是一个空行，而表格只画到「最后一个有内容的行」，新空行没画出来、也选不中，看起来像点了没反应。"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import test_all, reports
from test_nav import HAVE, CHROME, run

LONG = '不算，在8.31日28.12T已记录，这里只是备注一下，后面还有很长很长的说明文字用来测试备注撑开格子'

def srv(k): return call('/api/report?key=' + k)[1]
def nonempty(t, start): return [r for r in range(start, len(t['rows']) + 1) if any(reports._v(t, c, r) not in (None, '') for c in 'ABCDEF')]

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class R1_Rows(unittest.TestCase):
    def grid(self, k, start, rcol):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL
            try:
                pg = await (await br.new_context(viewport={'width': 1280, 'height': 800})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                async def pin():
                    try: await pg.wait_for_selector('.pin-in', timeout=1500)
                    except Exception: return   # 几分钟内已输过密码
                    await pg.fill('.pin-in', '1002'); await pg.press('.pin-in', 'Enter'); await pg.wait_for_selector('.pin-in', state='detached')
                async def shown(r):
                    return await pg.evaluate("""r => { const tr = document.querySelector('#rGrid tr[data-r="' + r + '"]'); if (!tr) return 'no row';
                        const g = document.querySelector('#rGrid').getBoundingClientRect(), b = tr.getBoundingClientRect();
                        if (!(b.top >= g.top - 1 && b.bottom <= g.bottom + 1 && b.top >= 0 && b.bottom <= innerHeight)) return 'not visible';
                        return tr.querySelector('td.sel') ? 'ok' : 'not selected'; }""", r)
                async def plus(r):   # 真实鼠标点击该行的「＋」（被别的东西挡住会报错）
                    sel = '#rGrid tr[data-r="%d"]' % r
                    await pg.evaluate("s => document.querySelector(s).scrollIntoView({block: 'center'})", sel)
                    await pg.hover(sel); await pg.click(sel + ' button[data-ins]', timeout=3000)
                await pg.goto(U + '/#report/' + k); await pg.wait_for_selector('#rGrid tr[data-r]')
                # 最后一行写一条长备注并保存（就是用户最近保存的那一行）
                last = await pg.evaluate("k => rRanges(k).last", k)
                await pg.evaluate("([k, r, c, v]) => { rSet(rTab(k), c, r, v); rDirty(k); rRender(true); }", [k, last, rcol, LONG])
                await pg.click('#rSave'); await pin(); await pg.wait_for_selector('#rSave[disabled]')
                n0 = len(nonempty(srv(k), start))
                # 1) 最后一行的「＋」：新行出现在它下面、看得见、被选中
                await plus(last); await pg.wait_for_timeout(200)
                self.assertEqual(await shown(last + 1), 'ok')
                await pg.keyboard.type('x1'); await pg.keyboard.press('Enter')
                # 2) 刚插入的空行（还没保存）再点「＋」也行
                await plus(last + 1); await pg.wait_for_timeout(200); self.assertEqual(await shown(last + 2), 'ok')
                await pg.keyboard.type('x2'); await pg.keyboard.press('Enter')
                # 3) 中间一行的「＋」
                a3, a4 = await pg.evaluate("k => [rRaw(rTab(k),'A',%d), rRaw(rTab(k),'A',%d)]" % (start + 1, start + 2), k)
                await plus(start + 1); await pg.wait_for_timeout(200); self.assertEqual(await shown(start + 2), 'ok')
                self.assertEqual(await pg.evaluate("k => [rRaw(rTab(k),'A',%d), rRaw(rTab(k),'A',%d), rRaw(rTab(k),'A',%d)]" % (start + 1, start + 2, start + 3), k), [a3, '', a4])
                await pg.keyboard.type('x3'); await pg.keyboard.press('Enter')
                # 4) 顶部「＋ 新增一行」（4号院）
                if k == 'yard4':
                    self.assertEqual((await pg.inner_text('#rAdd')).strip(), '＋ 新增一行')
                    await pg.click('#rAdd'); await pg.wait_for_function("RP.sel && RP.sel.k === 'yard4'"); await pg.wait_for_timeout(200)
                    r_new = await pg.evaluate("RP.sel.r"); self.assertEqual(await shown(r_new), 'ok')
                    await pg.keyboard.type('x4'); await pg.keyboard.press('Enter')
                await pg.click('#rSave'); await pin(); await pg.wait_for_selector('#rSave[disabled]')
                after = srv(k)
                self.assertEqual(len(nonempty(after, start)), n0 + (4 if k == 'yard4' else 3))
                vals = [reports._v(after, c, r) for r in range(start, len(after['rows']) + 1) for c in 'AB']
                for x in ['x1', 'x2', 'x3'] + (['x4'] if k == 'yard4' else []): self.assertIn(x, vals)
                self.assertEqual(reports._v(after, rcol, last + 1 if False else last + (1 if start + 1 < last else 0)), LONG)   # 中间插了一行，长备注那行下移一行
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

    def test_yard4(self): self.grid('yard4', 2, 'F')
    def test_lox(self): self.grid('lox', 13, 'L')

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class R2_AllGrids(unittest.TestCase):
    """每个可编辑表格的最后一行：行按钮都点得到（不被挡住）、点了有反应"""
    def test_last_row_actions_everywhere(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL
            try:
                pg = await (await br.new_context(viewport={'width': 1280, 'height': 800})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                # ---- 报表：五张表 ----
                for k in ['conv', 'ledger', 'stock', 'lox', 'yard4']:
                    await pg.goto(U + '/#report/' + k); await pg.wait_for_function("k => RP.k === k && RP.tabs[k] && document.querySelector('.rt-' + k + ' tr[data-r]')", arg=k); await pg.wait_for_timeout(200)
                    last = await pg.evaluate("k => rRanges(k).mainEnd", k)
                    sel = '#rGrid tr[data-r="%d"]' % last
                    await pg.evaluate("s => document.querySelector(s).scrollIntoView({block: 'center'})", sel); await pg.hover(sel)
                    btns = await pg.query_selector_all(sel + ' .r-acts button')
                    if k == 'stock': self.assertEqual(btns, []); continue          # 到货总数只读，没有行按钮
                    self.assertTrue(btns, k)
                    for b in btns: await b.click(trial=True, timeout=3000)          # 每个按钮都没被挡住
                    if k in ('lox', 'yard4', 'ledger'):                              # 「＋」：新行出现、被选中（入出库记录也可中间插）
                        await pg.click(sel + ' button[data-ins]'); await pg.wait_for_timeout(200)
                        self.assertTrue(await pg.query_selector('#rGrid tr[data-r="%d"] td.sel' % (last + 1)), k)
                        if k == 'ledger':
                            Lnew = await pg.evaluate("r => ((rTab('ledger').rows[r-1]||{}).c.L||{}).f||''", last + 1)
                            self.assertEqual(Lnew, 'L%d-K%d' % (last, last + 1), Lnew)
                            await pg.keyboard.press('Control+z'); await pg.wait_for_timeout(200)
                            self.assertIsNone(await pg.query_selector('#rGrid tr[data-r="%d"]' % (last + 1)))
                            # 找一行已有 L{n-1}-K{n} 的，在它上方插入，检查新行与该行 L 链
                            hit = await pg.evaluate("""() => {
                              const t = rTab('ledger'), rg = rRanges('ledger');
                              for (let r = rg.start + 2; r <= rg.mainEnd; r++) {
                                const f = (((t.rows[r-1]||{}).c.L||{}).f||'').replace(/\s/g,'');
                                if (f === 'L'+(r-1)+'-K'+r) return r;
                              }
                              return 0;
                            }""")
                            self.assertTrue(hit, 'need a chain-L row')
                            await pg.evaluate("r => rInsertBelow('ledger', r)", hit - 1); await pg.wait_for_timeout(200)
                            Lnew2, Lnxt = await pg.evaluate(
                                "([a,b]) => { const f=r=>((rTab('ledger').rows[r-1]||{}).c.L||{}).f||''; return [f(a),f(b)]; }",
                                [hit, hit + 1])
                            self.assertEqual(Lnew2, 'L%d-K%d' % (hit - 1, hit), Lnew2)
                            self.assertEqual(Lnxt, 'L%d-K%d' % (hit, hit + 1), Lnxt)
                        await pg.evaluate("k => rLoad(k).then(() => { App.guard = null; rRender(); })", k)  # 放弃这次插入
                    else:                                                           # 换算表无行上「＋」
                        pass
                    await pg.hover(sel); await pg.click(sel + ' button[data-del]'); await pg.wait_for_selector('.ov')   # 最后一行「✕」能打开删除确认
                    self.assertIn('确认删除', await pg.inner_text('.ov')); await pg.click('.ov .dlg-f button:has-text("取消")'); await pg.wait_for_selector('.ov', state='detached')
                # ---- 交接表：加一行，最后一行 ⋯ → 删除这一行 ----
                await pg.goto(U + '/#daily/cyl'); await pg.wait_for_selector('#ppAdd')
                n0 = await pg.evaluate("document.querySelectorAll('tr:has(td.pm)').length")
                await pg.click('#ppAdd'); await pg.wait_for_timeout(150)
                rows = await pg.query_selector_all('tr:has(td.pm)'); self.assertEqual(len(rows), n0 + 1)
                await rows[-1].scroll_into_view_if_needed(); await (await rows[-1].query_selector('.ra-dots')).click()
                d = await pg.query_selector('.ra-more.on a[data-act="del"]'); self.assertTrue(d)
                box = await d.bounding_box(); self.assertTrue(box['y'] + box['height'] <= 800, box)   # 菜单没跑到屏幕外
                await d.click(); await pg.wait_for_timeout(150)
                self.assertEqual(await pg.evaluate("document.querySelectorAll('tr:has(td.pm)').length"), n0)
                # 最后一个车牌行的 ⋯ 菜单也能打开
                rows = await pg.query_selector_all('tr:has(td.pm)'); await (await rows[-1].query_selector('.ra-dots')).click()
                for a in await pg.query_selector_all('.ra-more.on .ra-menu a'): await a.click(trial=True, timeout=3000)
                await pg.keyboard.press('Escape'); await pg.mouse.click(5, 5)
                # ---- 批量出库 / 补录借用本 / 到货：最后一行「✕」 ----
                for url, tb, add in [('/#out/batch', '#obAdd', '#obAdd'), ('/#loan/batch', '#lbAdd', '#lbAdd'), ('/#arrival', '#arAddL', '#arAddL')]:
                    await pg.evaluate('App.guard = null'); await pg.goto(U + url); await pg.wait_for_selector(add); await pg.click(add); await pg.wait_for_timeout(150)
                    xs = await pg.query_selector_all('#main [data-x]'); n = len(xs); self.assertGreater(n, 1, url)
                    await xs[-1].scroll_into_view_if_needed(); await xs[-1].click(); await pg.wait_for_timeout(150)
                    self.assertEqual(len(await pg.query_selector_all('#main [data-x]')), n - 1, url)
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

if __name__ == '__main__': unittest.main()
