"""录入表格的行、列淡高亮：交接表（钢瓶、产品）输入框得到焦点、报表（液氧表、4号院）点选格子时，
当前行、当前列淡淡一层（主色约 6%），表头对应列只稍加深、字稍粗。截图：screens/grid_focus_*.png"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule, ROOT  # noqa
import test_all
from test_nav import HAVE, CHROME, run
OUT = os.path.join(ROOT, 'screens')
STATE = """sel => { const t = document.querySelector(sel); const me = t.querySelector('td:focus-within, td.sel');
  const n = c => t.querySelectorAll(c).length; const tr = t.querySelector('tr.hl-r');
  const bg = t.querySelector('td.hl-c') ? getComputedStyle(t.querySelector('td.hl-c')).backgroundImage : '';
  return { me: !!me, row: tr === (me && me.parentNode), col: n('td.hl-c'), head: n('th.hl-h'), bg }; }"""

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class G1_Focus(unittest.TestCase):
    def test_grids(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []
            try:
                pg = await (await br.new_context(viewport={'width': 1400, 'height': 800}, locale='zh-CN')).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(test_all.URL + '/'); await pg.wait_for_timeout(600)
                for tab in ('cyl', 'prod'):
                    await pg.evaluate('h => location.hash = h', '#daily/' + tab); await pg.wait_for_timeout(1000)
                    inp = (await pg.query_selector_all('#ppT tbody tr:nth-child(4) td.pc input'))[4]
                    await inp.click(); await pg.wait_for_timeout(100)
                    s = await pg.evaluate(STATE, '#ppT')
                    self.assertTrue(s['me'] and s['row'], s); self.assertGreater(s['col'], 3, s); self.assertGreaterEqual(s['head'], 2, s)
                    self.assertIn('0.06', s['bg'])   # 很淡
                    await pg.screenshot(path=os.path.join(OUT, 'grid_focus_%s.png' % tab))
                    await pg.keyboard.press('ArrowDown'); await pg.wait_for_timeout(80)
                    s2 = await pg.evaluate(STATE, '#ppT'); self.assertTrue(s2['row'], s2)
                    await pg.evaluate("() => document.activeElement.blur()"); await pg.wait_for_timeout(50)
                    self.assertEqual(await pg.evaluate("() => document.querySelectorAll('#ppT .hl-r,#ppT .hl-c,#ppT .hl-h').length"), 0)
                for k in ('lox', 'yard4'):
                    await pg.evaluate('h => location.hash = h', '#report/' + k); await pg.wait_for_timeout(1200)
                    td = await pg.query_selector('#rGrid tbody tr:nth-child(5) td[data-c="D"]') or (await pg.query_selector_all('#rGrid tbody td[data-c]'))[6]
                    await td.click(); await pg.wait_for_timeout(100)
                    s = await pg.evaluate(STATE, '#rGrid table')
                    self.assertTrue(s['me'] and s['row'], (k, s)); self.assertGreater(s['col'], 2, (k, s)); self.assertGreaterEqual(s['head'], 1, (k, s))
                    await pg.screenshot(path=os.path.join(OUT, 'grid_focus_%s.png' % k))
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

if __name__ == '__main__': unittest.main()
