"""次日清点 / 产品表跟钢瓶表 / ⋯菜单 截图：python tests/shoot_nextday.py URL 名字 日期 tab [场次] [动作]"""
import sys, os, asyncio
from playwright.async_api import async_playwright
U, NAME, DATE, TAB = sys.argv[1:5]
SES = sys.argv[5] if len(sys.argv) > 5 else ''
ACT = sys.argv[6] if len(sys.argv) > 6 else ''
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screens')
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        pg = await (await b.new_context(viewport={'width': 1440, 'height': 900}, locale='zh-CN')).new_page()
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(U + '/'); await pg.wait_for_timeout(800)
        await pg.evaluate("([d, t, s]) => { D.date = d; D.sesInit = 1; if (s) D.ses = s; location.hash = '#daily/' + t; }", [DATE, TAB, SES])
        await pg.wait_for_timeout(1500)
        if ACT == 'menu':   # 交接表某行 ⋯ 打开
            await pg.locator('#ppT tr.has .ra-dots').last.click(); await pg.wait_for_timeout(300)
        if ACT == 'swap':
            await pg.locator('#ppT tr.has .ra-dots').last.click(); await pg.wait_for_timeout(200); await pg.click('.ra-more.on a[data-act="swap"]'); await pg.wait_for_timeout(400)
        await pg.screenshot(path=os.path.join(OUT, NAME + '.png'), full_page=False)
        print('saved', NAME, 'errors', errs)
        await b.close()
asyncio.run(main())
