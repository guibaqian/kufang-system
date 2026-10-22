"""在无头 Chrome 里跑前端离线识别（O2OCR），给测试和调试用"""
import os, sys, base64, threading, functools, asyncio, json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = '/usr/bin/google-chrome'
LOAD = """async () => {
  const html = await (await fetch('/lib/ocr_bundle.html')).text();
  const host = document.createElement('div'); host.style.display = 'none'; host.innerHTML = html; document.body.appendChild(host);
  const first = host.querySelector('script:not([type])'); const s = document.createElement('script'); s.textContent = first.textContent; document.head.appendChild(s);
  await new Promise((res, rej) => { const s2 = document.createElement('script'); s2.src = '/lib/o2_ocr.js?' + Date.now(); s2.onload = res; s2.onerror = rej; document.head.appendChild(s2); });
  if (!window.TesseractOffline && window.Tesseract) window.TesseractOffline = window.Tesseract;
}"""
class Q(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
def serve():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Q, directory=os.path.join(ROOT, 'static')))
    threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv
async def run_daily(paths):
    from playwright.async_api import async_playwright
    srv = serve(); out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
        pg = await b.new_page(); logs = []
        pg.on('console', lambda m: logs.append(m.text))
        await pg.goto('http://127.0.0.1:%d/index.html' % srv.server_address[1]); await pg.evaluate('document.body.innerHTML=""')
        await pg.evaluate(LOAD)
        for path in paths:
            url = 'data:image/png;base64,' + base64.b64encode(open(path, 'rb').read()).decode()
            r = await pg.evaluate("async u => { const p = await O2OCR.recognizeDaily(u); return JSON.parse(JSON.stringify(p)); }", url)
            out.append(r)
        await b.close()
    srv.shutdown(); return out, logs
if __name__ == '__main__':
    r, logs = asyncio.run(run_daily(sys.argv[1:]))
    print(json.dumps(r, ensure_ascii=False, indent=1)); print('\n'.join(logs[-20:]))
