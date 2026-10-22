"""「⋯」菜单永远看得全：不被表格滚动区裁掉、不被下一行（固定在右边的操作列）盖住；靠近窗口底部往上弹；点菜单项照常生效。
原因记录（v1.1.1）：操作列 td.ra 是 position:sticky + z-index:1，每一格自成一层，后面一行的格子盖住了前一行弹出的菜单（设置 → 配送员 ⋯ 看不见）。
截图：screens/menu_fix_*.png"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule, ROOT  # noqa
import test_all
from test_nav import HAVE, CHROME, run
OUT = os.path.join(ROOT, 'screens')
PAGES = [('settings_couriers', '#settings/couriers'), ('out_list', '#out/list'), ('loan_list', '#loan/list'), ('arrival', '#arrival'),
         ('daily_cyl', '#daily/cyl'), ('daily_sum', '#daily/sum'), ('misc', '#misc'), ('slip', '#slip'), ('trash', '#backup/trash')]
CHECK = """() => { const mu = document.querySelector('.ra-more.on .ra-menu'); if (!mu) return 'not open';
  const r = mu.getBoundingClientRect(); if (r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth) return 'off screen ' + JSON.stringify(r);
  for (const a of mu.querySelectorAll('a')) { const b = a.getBoundingClientRect(); const t = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
    if (!t || !a.contains(t)) return 'covered: ' + a.textContent + ' by ' + (t ? t.outerHTML.slice(0, 80) : 'null'); }
  return 'ok'; }"""

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class M1_Menus(unittest.TestCase):
    def test_menus_visible_everywhere(self):
        for i in range(3): call('/api/courier/save', {'data': {'name': '菜单测试%d' % i}})
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL; seen = 0
            try:
                pg = await (await br.new_context(viewport={'width': 1280, 'height': 640}, locale='zh-CN')).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(U + '/'); await pg.wait_for_timeout(600)
                for name, h in PAGES:
                    await pg.evaluate('h => location.hash = h', h); await pg.wait_for_timeout(1000)
                    dots = await pg.query_selector_all('.ra-dots')
                    if not dots: continue
                    for which, d in (('first', dots[0]), ('last', dots[-1])):
                        await d.scroll_into_view_if_needed(); await pg.wait_for_timeout(100)
                        await d.click(); await pg.wait_for_timeout(150)
                        self.assertEqual(await pg.evaluate(CHECK), 'ok', '%s %s' % (name, which)); seen += 1
                        if name in ('settings_couriers', 'daily_cyl') or which == 'last' and name == 'out_list':
                            await pg.screenshot(path=os.path.join(OUT, 'menu_fix_%s_%s.png' % (name, which)))
                        await pg.keyboard.press('Escape'); await pg.wait_for_timeout(80)
                        self.assertIsNone(await pg.query_selector('.ra-more.on'))
                # 点菜单项照常生效：设置 → 配送员 ⋯ → 删除 弹出确认
                await pg.evaluate("location.hash = '#settings/couriers'"); await pg.wait_for_timeout(900)
                await (await pg.query_selector_all('.ra-dots'))[-1].click(); await pg.click('.ra-more.on .ra-menu a'); await pg.wait_for_selector('.ov', timeout=3000)
                self.assertIsNone(await pg.query_selector('.ra-more.on'))
                # 靠近底部：往上弹
                await pg.click('.ov button:has-text("取消")'); await pg.wait_for_timeout(200); self.assertIsNone(await pg.query_selector('.ov'))
                await pg.set_viewport_size({'width': 1280, 'height': 420})
                await pg.evaluate("location.hash = '#daily/cyl'"); await pg.wait_for_timeout(900)
                d = (await pg.query_selector_all('#ppT .ra-dots'))[6]; await d.scroll_into_view_if_needed()
                await pg.evaluate("() => { const t = document.querySelector('.pp-tw'); const b = document.querySelectorAll('#ppT .ra-dots')[6].getBoundingClientRect(); t.scrollTop += b.bottom - innerHeight + 20; }"); await pg.wait_for_timeout(150)
                await d.click(); await pg.wait_for_timeout(150)
                self.assertEqual(await pg.evaluate(CHECK), 'ok', 'bottom flip')
                await pg.screenshot(path=os.path.join(OUT, 'menu_fix_daily_cyl_bottom_flip.png'))
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, []); self.assertGreater(seen, 8)
        run(go())

if __name__ == '__main__': unittest.main()
