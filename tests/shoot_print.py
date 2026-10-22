"""打印预览截图：把页面上「打印」排好的内容按 A4 横向打成 PDF，再转 PNG。
用法：python tests/shoot_print.py URL 输出名 hash [日期] [按钮id]"""
import sys, os, asyncio, subprocess
from playwright.async_api import async_playwright
BASE, NAME, HASH = sys.argv[1], sys.argv[2], sys.argv[3]
DATE = sys.argv[4] if len(sys.argv) > 4 else ''
BTN = sys.argv[5] if len(sys.argv) > 5 else '#dPrint'
SES = sys.argv[6] if len(sys.argv) > 6 else ''
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screens')
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        pg = await (await b.new_context(viewport={'width': 1440, 'height': 900}, locale='zh-CN')).new_page()
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto(BASE + '/'); await pg.wait_for_timeout(800)
        await pg.evaluate('h => location.hash = h', HASH); await pg.wait_for_timeout(1200)
        if DATE:
            await pg.evaluate("d => { const i = document.querySelector('#dDate'); i.value = d; i.dispatchEvent(new Event('change')); }", DATE); await pg.wait_for_timeout(1500)
        if SES: await pg.click('#ppSes button[data-s="%s"]' % SES); await pg.wait_for_timeout(800)
        await pg.evaluate('window.print = () => {}')
        await pg.click(BTN); await pg.wait_for_timeout(1500)
        await pg.evaluate("document.body.classList.add('printing')")
        z = await pg.evaluate("(document.querySelector('.print-host') || {dataset: {}}).dataset.zoom")
        await pg.emulate_media(media='print')
        pdf = os.path.join('/tmp', NAME + '.pdf')
        await pg.pdf(path=pdf, prefer_css_page_size=True, print_background=True)
        await b.close()
    n = subprocess.run(['pdfinfo', pdf], capture_output=True, text=True).stdout
    pages = [l for l in n.splitlines() if l.startswith(('Pages', 'Page size'))]
    subprocess.run(['pdftoppm', '-r', '150', '-png', '-singlefile', pdf, os.path.join(OUT, NAME)], check=True)
    print('saved', NAME + '.png', 'zoom', z, pages, 'errors', errs)
asyncio.run(main())
