"""加照片弹窗（粘贴 / 选文件 / 手机扫码拍照）+ 手机临时上传码。python -m unittest tests.test_upq -v   （SHOTS=1 截图）"""
import os, sys, base64, zlib, struct, tempfile, time, unittest, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import test_all
from test_nav import HAVE, CHROME, run
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'screens')

def png(w=160, h=120, rgb=(47, 102, 224)):
    raw = b''.join(b'\x00' + bytes(rgb) * w for _ in range(h))
    ch = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b'')
DATA = 'data:image/png;base64,' + base64.b64encode(png()).decode()

class U1_Api(unittest.TestCase):
    def test_token_scope_expiry(self):
        st, r = call('/api/upq/new', {'label': '液氧表 第 84 行', 'entity': 'report', 'tag': 'lox'}, pin=''); self.assertEqual(st, 200, r)   # 不用密码
        t = r['token']; self.assertGreaterEqual(len(t), 16); self.assertEqual(r['ttl'], 600)
        st, i = call('/api/upq/info?t=' + t); self.assertEqual((i['label'], i['state']), ('液氧表 第 84 行', 'open'))
        st, p = call('/api/upq/photo', {'t': t, 'data': DATA, 'name': 'a.png'}, pin=''); self.assertEqual(st, 200, p)
        st, q = call('/api/upq/poll?t=' + t); self.assertEqual([x['id'] for x in q['items']], [p['id']])
        self.assertEqual(call('/api/upq/photo', {'t': 'nope' * 4, 'data': DATA}, pin='')[0], 404)            # 乱填的码
        self.assertEqual(call('/api/upq/photo', {'t': t, 'data': 'xx'}, pin='')[0], 400)                    # 不是图片
        self.assertEqual(call('/api/upq/done', {'t': t}, pin='')[0], 200)
        st, e = call('/api/upq/photo', {'t': t, 'data': DATA}, pin=''); self.assertEqual(st, 410); self.assertIn('用完', e['error'])   # 完成后作废
        self.assertEqual(call('/api/upq/poll?t=' + t)[1]['state'], 'done')
        # 过期
        t2 = call('/api/upq/new', {'label': 'x'}, pin='')[1]['token']
        import db; con = db.connect(); con.execute('UPDATE upload_tokens SET expires_at=? WHERE token=?', (time.time() - 1, t2)); con.commit(); con.close()
        st, e = call('/api/upq/photo', {'t': t2, 'data': DATA}, pin=''); self.assertEqual(st, 410); self.assertIn('过期', e['error'])
        # 留痕
        au = call('/api/audit?limit=50')
        self.assertEqual(au[0], 200)
        self.assertTrue(any('手机拍照上传' in (x.get('summary') or '') for x in (au[1].get('items') or [])), au[1])
        # 上传码只能传照片：拿它当密码做别的不行
        self.assertIn(call('/api/report/save', {'tabs': {}}, pin=t)[0], (401, 403))

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class U2_Ui(unittest.TestCase):
    def test_paste_file_phone(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL; shots = os.environ.get('SHOTS')
            f = tempfile.NamedTemporaryFile(suffix='.png', delete=False); f.write(png(rgb=(47, 138, 87))); f.close()
            try:
                pg = await (await br.new_context(viewport={'width': 1280, 'height': 720})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(U + '/#report/lox'); await pg.wait_for_selector('.rt-lox tr[data-r]')
                await pg.evaluate("() => { rAddAtt('lox', 84); }"); await pg.wait_for_selector('#pkDrop')
                # ① 粘贴
                await pg.evaluate("""d => fetch(d).then(r => r.blob()).then(b => { const dt = new DataTransfer(); dt.items.add(new File([b], 'shot.png', { type: 'image/png' }));
                    document.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true })); })""", DATA)
                await pg.wait_for_function("document.querySelectorAll('#pkPh img').length === 1")
                # ② 选择文件
                async with pg.expect_file_chooser() as fc: await pg.click('#pkFile')
                await (await fc.value).set_files(f.name); await pg.wait_for_function("document.querySelectorAll('#pkPh img').length === 2")
                # 删掉刚加的一张
                await pg.click('#pkPh [data-rm="0"]'); await pg.wait_for_function("document.querySelectorAll('#pkPh img').length === 1")
                # ③ 手机拍照上传
                await pg.click('#pkPhone'); await pg.wait_for_selector('#pkQr img')
                src = await pg.get_attribute('#pkQr img', 'src'); url = urllib.parse.unquote(src.split('text=')[1]); self.assertIn('/m/up.html#', url)
                tok = url.split('#')[1]
                await pg.wait_for_timeout(1100); self.assertIn('内有效', await pg.inner_text('#pkLeft'))
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'upload_1_desktop_popup.png'))
                ph = await (await br.new_context(viewport={'width': 390, 'height': 760}, is_mobile=True, has_touch=True)).new_page(); ph.on('pageerror', lambda e: errs.append(str(e)))
                await ph.goto(U + '/m/up.html#' + tok); await ph.wait_for_function("document.querySelector('#lab').textContent.includes('液氧表')")
                if shots: await ph.screenshot(path=os.path.join(SHOTS, 'upload_2_phone_page.png'))
                await ph.set_input_files('#cam', [f.name, f.name]); await ph.wait_for_function("document.querySelectorAll('#ph span').length === 2 && [...document.querySelectorAll('#ph span')].every(s => s.textContent.includes('✓'))")
                if shots: await ph.screenshot(path=os.path.join(SHOTS, 'upload_3_phone_uploaded.png'))
                await pg.wait_for_function("document.querySelectorAll('#pkPh img').length === 3", timeout=6000)    # 电脑上实时出现
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'upload_4_desktop_received.png'))
                await ph.click('#done'); await ph.wait_for_selector('text=已传 2 张')
                await pg.wait_for_selector('#pkDrop', state='detached', timeout=6000)                            # 手机点完成 → 电脑弹窗自动关
                n = await pg.evaluate("(rTab('lox').rows[83].att || []).length"); self.assertEqual(n, 3)
                self.assertEqual(await pg.evaluate("RP.dirty.lox"), True)
                # 弹窗关了，码作废
                self.assertEqual(call('/api/upq/photo', {'t': tok, 'data': DATA}, pin='')[0], 410)
                # photoBox 里的「+」也走这个弹窗（出库单笔）
                await pg.evaluate("App.guard = null"); await pg.goto(U + '/#out/single'); await pg.wait_for_selector('#phBox [data-add]')
                await pg.click('#phBox [data-add]'); await pg.wait_for_selector('#pkPhone'); await pg.click('.pk-ov [data-close]'); await pg.wait_for_selector('#pkDrop', state='detached')
            finally:
                await br.close(); await pw.stop(); os.unlink(f.name)
            self.assertEqual(errs, [])
        run(go())

if __name__ == '__main__': unittest.main()
