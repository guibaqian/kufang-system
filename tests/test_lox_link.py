"""液氧表 → 液态氧原料入出库记录：卸到别处的记成出库并联动。python -m unittest tests.test_lox_link -v
截图（SHOTS=1）：screens/lox_*.png"""
import os, sys, copy, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import test_all, reports
from test_nav import HAVE, CHROME, run
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screens')

def tab(k): return call('/api/report?key=' + k)[1]
def save(tabs):
    st, r = call('/api/report/save', {'tabs': {k: {'rows': t['rows'], 'merges': t['merges'], 'version': t['version']} for k, t in tabs.items()}, 'summary': '测试'}); assert st == 200, r; return r

class L1_Sync(unittest.TestCase):
    def test_sync_and_missing(self):
        lox, led = tab('lox'), tab('ledger'); lox0, led0 = copy.deepcopy(lox), copy.deepcopy(led)
        r = reports.ranges('lox', lox)['main_end'] + 1
        reports._set(lox, 'A', r, '2026.10.19'); reports._set(lox, 'B', r, '测Z0001'); reports._set(lox, 'E', r, '市政府16.31'); reports._set(lox, 'E', r + 1, '创投D11.25')
        lox['rows'][r - 1]['lx'] = 'lxtest1'
        lr = reports.ranges('ledger', led)['main_end'] + 1
        reports._set(led, 'I', lr, '2026.10.19'); reports._set(led, 'J', lr, '出市政府'); reports._set(led, 'K', lr, 16.31)
        led['rows'][lr - 1]['link'] = {'k': 'lox', 'id': 'lxtest1', 'place': '市政府', 'date': '2026-10-19'}
        save({'lox': lox, 'ledger': led})
        lox = tab('lox'); reports._set(lox, 'E', r, '市政府16.5'); res = save({'lox': lox})
        self.assertEqual(res['synced'], ['ledger']); self.assertEqual(reports._v(tab('ledger'), 'K', lr), 16.5)   # 改液氧表 → 出库量跟着变
        lox = tab('lox'); reports._set(lox, 'A', r, '2026.10.20'); save({'lox': lox}); self.assertEqual(reports._v(tab('ledger'), 'I', lr), '2026.10.20')
        lox = tab('lox'); reports._set(lox, 'E', r, '网信办16.5'); save({'lox': lox})
        self.assertEqual(tab('ledger')['rows'][lr - 1]['link'].get('missing'), 1)                                   # 卸点没了 → 标出来，不乱改
        lox = tab('lox'); reports._set(lox, 'E', r, '市政府16.5'); save({'lox': lox}); self.assertNotIn('missing', tab('ledger')['rows'][lr - 1]['link'])
        lox, led = tab('lox'), tab('ledger'); lox0['version'], led0['version'] = lox['version'], led['version']; save({'lox': lox0, 'ledger': led0})

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class L2_Ui(unittest.TestCase):
    def test_delivery_and_manual_link(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL; shots = os.environ.get('SHOTS')
            try:
                pg = await (await br.new_context(viewport={'width': 1440, 'height': 860})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                async def pin():
                    try: await pg.wait_for_selector('.pin-in', timeout=1500)
                    except Exception: return
                    await pg.fill('.pin-in', '1002'); await pg.press('.pin-in', 'Enter'); await pg.wait_for_selector('.pin-in', state='detached')
                async def act(r, b):
                    sel = '#rGrid tr[data-r="%d"]' % r
                    await pg.evaluate("s => document.querySelector(s).scrollIntoView({block: 'center'})", sel); await pg.hover(sel); await pg.click(sel + ' button[data-%s]' % b, timeout=5000)
                led0 = tab('ledger'); n0 = reports.ranges('ledger', led0)['main_end']
                await pg.goto(U + '/#report/lox'); await pg.wait_for_selector('.rt-lox tr[data-r]')
                await pg.click('#rAdd'); await pg.wait_for_selector('#dvPlate')
                await pg.fill('#dvDate', '2026-10-18'); await pg.fill('#dvPlate', '陕J65758'); await pg.fill('#dvMed', '27.59')
                await pg.fill('.dv-place[data-i="0"]', '市政府'); await pg.fill('.dv-tons[data-i="0"]', '16.31')
                await pg.click('[data-addl]'); await pg.fill('.dv-place[data-i="1"]', '创投D'); await pg.fill('.dv-tons[data-i="1"]', '11.25')
                await pg.evaluate("document.querySelector('.ov.dv details').open = true"); await pg.fill('#dvNote', '4号院暂存公司'); await pg.dispatch_event('#dvNote', 'input')
                txt = await pg.inner_text('#dvLedW'); self.assertIn('出市政府 16.31', txt); self.assertNotIn('创投', txt.split('（')[0])
                self.assertEqual(await pg.inner_text('#dvSum'), '=16.31+11.25 = 27.56')
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'lox_1_dialog.png'))
                await pg.click('.ov.dv .btn.pri'); await pin(); await pg.wait_for_selector('.ov.dv', state='detached')
                await pg.wait_for_function("RP.k === 'lox' && !RP.dirty.lox && !RP.dirty.ledger")
                led = tab('ledger'); lox = tab('lox'); n1 = reports.ranges('ledger', led)['main_end']
                self.assertEqual(n1, n0 + 1); self.assertEqual([reports._v(led, c, n1) for c in 'IJK'], ['2026.10.18', '出市政府', 16.31])
                self.assertEqual(led['rows'][n1 - 1]['link']['k'], 'lox'); self.assertEqual(led['rows'][n1 - 1]['c']['L'].get('f'), 'L%d-K%d' % (n0, n1))
                r0 = next(i + 1 for i, x in enumerate(lox['rows']) if x and x.get('lx') == led['rows'][n1 - 1]['link']['id'])
                self.assertEqual([reports._v(lox, c, r0) for c in 'ABCL'], ['2026.10.18', '陕J65758', 27.59, '4号院暂存公司'])
                self.assertEqual(lox['rows'][r0 - 1]['c']['D'].get('f'), '16.31+11.25')
                # 液氧表：这车行上有「↗记录」，10 月自动合计含这车
                await pg.wait_for_selector('#rGrid tr[data-r="%d"] button[data-lxgo]' % r0, state='attached')
                s = await pg.evaluate("rAutoSums('lox')[0]"); self.assertEqual(s['after'], r0 + 1); self.assertAlmostEqual(s['vals']['D'], 112.67 + 27.56, places=2)
                await pg.evaluate("r => document.querySelector('#rGrid tr[data-r=\"' + r + '\"]').scrollIntoView({block: 'center'})", r0)
                await pg.hover('#rGrid tr[data-r="%d"]' % r0)
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'lox_2_loxtable.png'))
                # 点「↗记录」→ 入出库记录那一行（行上有 ↗ 回到液氧表）
                await act(r0, 'lxgo'); await pg.wait_for_function("RP.k === 'ledger'")
                await pg.wait_for_selector('#rGrid tr[data-r="%d"] button[data-src]' % n1, state='attached')
                self.assertEqual(await pg.text_content('#rGrid tr[data-r="%d"] button[data-src]' % n1), '↗')
                await pg.evaluate("r => document.querySelector('#rGrid tr[data-r=\"' + r + '\"]').scrollIntoView({block: 'center'})", n1)
                await pg.hover('#rGrid tr[data-r="%d"]' % n1); await pg.evaluate("r => rSelect(r, 'K')", n1)
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'lox_3_ledger.png'))
                await act(n1, 'src'); await pg.wait_for_function("RP.k === 'lox' && RP.sel && RP.sel.r === %d" % r0)
                # 以前的行默认不动；点「→记录」手动关联（华能9.98 已手填在入出库记录 246 行 → 认出来、接上，不重复记）
                self.assertIsNone(lox['rows'][86].get('lx'))
                await act(87, 'lxlnk'); await pg.wait_for_selector('[data-li="0"]')
                self.assertEqual(await pg.eval_on_selector('[data-li="0"]', 'e => e.value'), '246')
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'lox_4_manual_link.png'))
                await pg.click('.ov .btn.pri >> text=关联并保存'); await pin(); await pg.wait_for_function("!RP.dirty.lox && !RP.dirty.ledger")
                led = tab('ledger'); self.assertEqual(reports.ranges('ledger', led)['main_end'], n1); self.assertEqual(led['rows'][245]['link']['place'], '华能')
                await pg.wait_for_selector('#rGrid tr[data-r="87"] button[data-lxgo]', state='attached')
                # 删除液氧表这车：提示并可同时删入出库记录那行
                await act(r0, 'del'); await pg.wait_for_selector('#dlLinked')
                self.assertIn('液态氧原料入出库记录', await pg.inner_text('.ov .banner'))
                await pg.click('.ov .btn.pri >> text=删除并保存'); await pin(); await pg.wait_for_function("!RP.dirty.lox && !RP.dirty.ledger")
                self.assertEqual(reports.ranges('ledger', tab('ledger'))['main_end'], n0)
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

if __name__ == '__main__': unittest.main()
