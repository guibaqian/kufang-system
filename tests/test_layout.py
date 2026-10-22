"""一屏布局：页面不滚动，只有表格自己滚。python -m unittest tests.test_layout -v   （SHOTS=1 存截图到 screens/）"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import test_all
from test_nav import HAVE, CHROME, run
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screens')
PAGES = ['report/lox', 'report/ledger', 'report/conv', 'report/yard4', 'report/stock', 'out/list', 'out/ly', 'arrival', 'stock', 'loan', 'misc', 'slip']
SIZES = [(1280, 720), (1920, 1080), (1024, 640)]

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class F1_Fit(unittest.TestCase):
    def test_one_scroller(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL; bad = []
            try:
                for w, h in SIZES:
                    pg = await (await br.new_context(viewport={'width': w, 'height': h})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                    for p in PAGES:
                        await pg.goto(U + '/#' + p); await pg.wait_for_selector('#main .page *'); await pg.wait_for_timeout(500)
                        st = await pg.evaluate("""() => { const se = document.scrollingElement, m = document.querySelector('#main'), g = document.querySelector('.fit-on');
                            return { fit: document.body.classList.contains('fit'), pageScroll: se.scrollHeight - innerHeight, mainScroll: m.scrollHeight - m.clientHeight,
                              grid: !!g, gridBottom: g ? Math.round(g.getBoundingClientRect().bottom) : 0, mainBottom: Math.round(m.getBoundingClientRect().bottom), gs: g ? g.scrollHeight - g.clientHeight : 0 }; }""")
                        tag = '%s@%dx%d' % (p, w, h)
                        if st['pageScroll'] > 1 and (st['fit'] or p.startswith('report/')): bad.append((tag, 'page scrolls', st))
                        if p.startswith('report/'):
                            if not st['grid'] or st['mainScroll'] > 1: bad.append((tag, 'grid not fitted', st)); continue
                            if st['mainBottom'] - st['gridBottom'] > 24: bad.append((tag, 'grid not at bottom', st))
                            # 鼠标滚轮在表格上：只滚表格，标题 / 工具栏不动
                            y0 = await pg.evaluate("document.querySelector('.ph h1').getBoundingClientRect().top")
                            box = await (await pg.query_selector('#rGrid')).bounding_box()
                            await pg.mouse.move(box['x'] + 200, box['y'] + 120)
                            s0 = await pg.evaluate("document.querySelector('#rGrid').scrollTop")
                            for _ in range(3): await pg.mouse.wheel(0, -2000 if s0 > 0 else 2000); await pg.wait_for_timeout(80)
                            for _ in range(3): await pg.mouse.wheel(0, 2000); await pg.wait_for_timeout(80)
                            y1 = await pg.evaluate("document.querySelector('.ph h1').getBoundingClientRect().top")
                            if abs(y1 - y0) > 0.5: bad.append((tag, 'title moved', y0, y1))
                            hd = await pg.evaluate("() => { const g = document.querySelector('#rGrid'), th = g.querySelector('thead th'); return Math.round(th.getBoundingClientRect().top - g.getBoundingClientRect().top); }")
                            if st['gs'] > 0 and abs(hd) > 2: bad.append((tag, 'header not sticky', hd))
                        elif st['grid'] and st['mainScroll'] > 1: bad.append((tag, 'list fitted but page still scrolls', st))
                        if os.environ.get('SHOTS') and p in ('report/lox', 'out/list'): await pg.screenshot(path=os.path.join(SHOTS, 'fit_%s_%dx%d.png' % (p.replace('/', '_'), w, h)))
                    await pg.context.close()
            finally:
                await br.close(); await pw.stop()
            self.maxDiff = None; self.assertEqual(bad, []); self.assertEqual(errs, [])
        run(go())

if __name__ == '__main__': unittest.main()
