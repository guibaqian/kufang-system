"""负数标红截图 + 检查：python tests/shoot_neg.py URL 日期 输出名"""
import sys, os, asyncio, json
from playwright.async_api import async_playwright
BASE, DATE, NAME = sys.argv[1], sys.argv[2], sys.argv[3]
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screens')
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        pg = await (await b.new_context(viewport={'width': 1440, 'height': 760}, locale='zh-CN')).new_page()
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(BASE + '/'); await pg.wait_for_timeout(800)
        await pg.evaluate('h => location.hash = h', '#daily/sum'); await pg.wait_for_timeout(1200)
        await pg.evaluate("d => { const i = document.querySelector('#dDate'); i.value = d; i.dispatchEvent(new Event('change')); }", DATE); await pg.wait_for_timeout(1500)
        neg = await pg.evaluate("[...document.querySelectorAll('td.cf.neg')].map(t => [t.textContent, t.title])")
        if neg: await pg.hover('td.cf.neg'); await pg.wait_for_timeout(300)
        await pg.screenshot(path=os.path.join(OUT, NAME + '.png'))
        await b.close()
    print(json.dumps({'neg': neg, 'errors': errs}, ensure_ascii=False))
asyncio.run(main())
