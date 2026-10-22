"""返回 / 后退导航 + 访客登记页（浏览器测试，需要 playwright + Chrome；没有就跳过）：python -m unittest tests.test_nav -v
修的问题：手机「借用归还」进去后怎么返回都回不去（返回键/手势在页面间打转）。"""
import os, sys, unittest, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, new_product, setUpModule, tearDownModule  # noqa
import test_all

CHROME = '/usr/bin/google-chrome'
try:
    import playwright  # noqa
    HAVE = os.path.exists(CHROME)
except ImportError: HAVE = False

def run(coro): return asyncio.new_event_loop().run_until_complete(coro)

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class N1_Nav(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pid = new_product('导航测试物品')
        st, r = call('/api/loan/save', {'data': {'user_to': '导航', 'orgs': ['二院'], 'items': [{'product_id': cls.pid, 'qty': 1}]}}); assert st == 200, r
        cls.lid = r['id']

    async def _ctx(self, phone=True):
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        self.b = await self.pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
        ctx = await self.b.new_context(viewport={'width': 390, 'height': 844} if phone else {'width': 1440, 'height': 900}, is_mobile=phone)
        pg = await ctx.new_page(); self.errs = []
        pg.on('pageerror', lambda e: self.errs.append(str(e)))
        pg.on('dialog', lambda d: asyncio.ensure_future(d.accept()))
        return pg
    async def _close(self): await self.b.close(); await self.pw.stop()
    async def h(self, pg): return await pg.evaluate('location.hash')
    async def title(self, pg): return await pg.evaluate("(document.querySelector('.top h1')||{}).textContent || (document.querySelector('.hello')? '首页' : '')")

    def test_phone_back(self):
        async def go():
            U = test_all.URL; pg = await self._ctx()
            await pg.goto('about:blank'); await pg.goto(U + '/m/'); await pg.wait_for_selector('a[href="#loan"]')
            # 1) 首页 → 借用归还 → 顶部「返回」→ 首页；再按系统后退离开系统（不会又回到借用归还）
            await pg.click('a[href="#loan"]'); await pg.wait_for_selector('.top .back')
            self.assertEqual(await self.title(pg), '借用归还')
            self.assertIn('返回', await pg.inner_text('.top .back'))
            await pg.click('.top .back'); await pg.wait_for_selector('.hello'); self.assertEqual(await self.h(pg), '')
            await pg.go_back(); await pg.wait_for_timeout(300); self.assertFalse((pg.url).startswith(U + '/m/'), pg.url)
            # 2) 系统后退：首页 → 借用归还 → 归还 → 后退 → 借用归还 → 后退 → 首页
            await pg.goto(U + '/m/'); await pg.wait_for_selector('.hello')
            await pg.click('a[href="#loan"]'); await pg.wait_for_selector('a.rec[href^="#ret/"]')
            await pg.click('a.rec[href="#ret/%d"]' % self.lid); await pg.wait_for_timeout(500); self.assertEqual(await self.title(pg), '归还')
            await pg.go_back(); await pg.wait_for_timeout(500); self.assertEqual(await self.h(pg), '#loan'); self.assertEqual(await self.title(pg), '借用归还')
            await pg.go_back(); await pg.wait_for_timeout(500); self.assertEqual(await self.h(pg), ''); self.assertEqual(await self.title(pg), '首页')
            # 3) 归还页「返回」回借用归还，再「返回」回首页
            await pg.goto(U + '/m/#ret/%d' % self.lid); await pg.wait_for_timeout(600)
            n = await pg.evaluate('history.length')
            await pg.click('.top .back'); await pg.wait_for_timeout(500); self.assertEqual(await self.h(pg), '#loan')
            await pg.click('.top .back'); await pg.wait_for_timeout(500); self.assertEqual(await self.title(pg), '首页')
            self.assertEqual(await pg.evaluate('history.length'), n)            # 没有新增历史记录（replace）
            # 4) 直接打开子页（收藏 / 扫码）：返回 → 首页；不会堆出循环
            await pg.goto(U + '/m/#misc'); await pg.wait_for_timeout(600)
            await pg.click('.top .back'); await pg.wait_for_timeout(400); self.assertEqual(await self.title(pg), '首页')
            # 5) 保存借出 → 完成页 → 回首页（真后退）→ 再后退离开，不会回到完成页/借用归还
            await pg.goto('about:blank'); await pg.goto(U + '/m/'); await pg.wait_for_selector('.hello')
            await pg.click('a[href="#loan"]'); await pg.wait_for_selector('#lQ')
            await pg.fill('#lU', '手机导航'); await pg.fill('#lQ', '导航测试'); await pg.wait_for_timeout(400)
            await pg.click('.drop > div'); await pg.wait_for_timeout(200)
            await pg.click('#lSave'); await pg.wait_for_selector('.pinpad')
            for k in '1002': await pg.click('.pinpad [data-k="%s"]' % k)
            await pg.wait_for_selector('#goHome')
            await pg.click('#again'); await pg.wait_for_selector('#lSave'); self.assertEqual(await self.h(pg), '#loan')
            await pg.click('.top .back'); await pg.wait_for_selector('.hello')
            self.assertEqual(await pg.evaluate('history.state && history.state.mIdx'), 0)
            await pg.go_back(); await pg.wait_for_timeout(300); self.assertTrue(pg.url.startswith('about:blank'), pg.url)
            # 6) 弹出的密码框在后退时一起关掉，不会挡住页面
            await pg.goto(U + '/m/'); await pg.wait_for_selector('.hello'); await pg.click('a[href="#pend"]'); await pg.wait_for_selector('#pT')
            await pg.evaluate("sessionStorage.removeItem('pin')"); await pg.fill('#pT', '某人'); await pg.click('#pSave'); await pg.wait_for_selector('.pinpad')
            await pg.go_back(); await pg.wait_for_timeout(400)
            self.assertEqual(await pg.evaluate("document.querySelectorAll('.ov').length"), 0); self.assertEqual(await self.title(pg), '首页')
            self.assertEqual(self.errs, [])
            await self._close()
        run(go())

    def test_desktop_tabs_back(self):
        async def go():
            U = test_all.URL; pg = await self._ctx(False)
            await pg.goto(U + '/#home'); await pg.wait_for_timeout(800)
            await pg.click('#tabs a[data-p="loan"]'); await pg.wait_for_selector('#lnTabs')
            for t in ('list', 'org', 'new', 'req'):
                await pg.click('#lnTabs button[data-t="%s"]' % t); await pg.wait_for_timeout(400)
            self.assertEqual(await self.h(pg), '#loan/req')
            await pg.go_back(); await pg.wait_for_timeout(500)
            self.assertEqual(await self.h(pg), '#home')                    # 页签不进历史：一次后退就回到首页
            await pg.click('#tabs a[data-p="out"]'); await pg.wait_for_timeout(600)
            for t in ('list', 'single', 'list'):
                b = await pg.query_selector('#outTabs button[data-t="%s"]' % t)
                if b: await b.click(); await pg.wait_for_timeout(400)
            await pg.go_back(); await pg.wait_for_timeout(500); self.assertEqual(await self.h(pg), '#home')
            # 设置页有手机地址和两个二维码
            await pg.goto(U + '/#settings/phone'); await pg.wait_for_selector('#phoneAddr')
            txt = await pg.inner_text('#phoneAddr'); self.assertIn('/m/', txt); self.assertIn('/m/guest', txt); self.assertIn('访客登记借用', txt)
            self.assertEqual(len(await pg.query_selector_all('#phoneAddr img')), 2)
            self.assertEqual(self.errs, [])
            await self._close()
        run(go())

    def test_guest_page_submit(self):
        async def go():
            U = test_all.URL; pg = await self._ctx()
            n0 = call('/api/loan_req')[1]['pending']
            await pg.goto(U + '/m/guest'); await pg.wait_for_selector('#gO')
            reqs = []; pg.on('request', lambda r: reqs.append(r.url))
            await pg.click('#gO button[data-o="一院"]'); await pg.wait_for_selector('#gEn')    # 一院 → 出现随车技术人员
            await pg.fill('#gCn', '页面访客'); await pg.fill('#gCp', '13900002222'); await pg.fill('#gEn', '随车王')
            await pg.fill('#gQ', '导航测试'); await pg.wait_for_timeout(200); await pg.click('#gD > div[data-p]')
            await pg.fill('#gQ', '临时绳子'); await pg.wait_for_timeout(200); await pg.click('#gD > div[data-new]')
            await pg.click('#gL [data-ap="1"]')                           # 第二样：若干
            await pg.click('#gMore'); box = await pg.query_selector('#gS'); await box.scroll_into_view_if_needed(); bb = await box.bounding_box()
            await pg.mouse.move(bb['x'] + 20, bb['y'] + 20); await pg.mouse.down(); await pg.mouse.move(bb['x'] + 120, bb['y'] + 80, steps=6); await pg.mouse.up()
            await pg.click('#gGo'); await pg.wait_for_selector('.ok-big')
            self.assertIn('已提交', await pg.inner_text('.ok-big'))
            self.assertTrue(all('/api/guest/' in u or '/api/' not in u for u in reqs), reqs)   # 访客页只调访客接口
            r = call('/api/loan_req')[1]; self.assertEqual(r['pending'], n0 + 1)
            q = r['items'][0]; self.assertEqual(q['cust_name'], '页面访客'); self.assertEqual(q['cust_phone'], '13900002222'); self.assertEqual(q['escort'], '随车王')
            self.assertEqual([i['approx'] for i in q['items']], [0, 1]); self.assertEqual([p['tag'] for p in q['photos']], ['sign'])
            call('/api/loan_req/reject', {'id': q['id']})
            self.assertEqual(self.errs, [])
            await self._close()
        run(go())

if __name__ == '__main__': unittest.main()
