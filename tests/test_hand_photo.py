"""手工单照片（每个配送员每天一组，可多张，按 日期+配送员 存，交接表重算不丢；删除要密码；不打印）
+ 全系统看大图（居中弹窗、原图、滚轮 / ＋− / 双击缩放、放大后拖动、‹ › / ← → 翻页、转 90°、Esc 关）。截图：screens/hand_photo_*.png、screens/viewer_*.png"""
import os, sys, io, base64, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule, ROOT  # noqa
import test_all, server
from test_nav import HAVE, CHROME, run
OUT = os.path.join(ROOT, 'screens'); D = '2026-10-19'

def slip(n, w=2400, h=1700):
    """造一张像手工单的照片（大图，带手写样的字）"""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new('RGB', (w, h), (246, 243, 232)); d = ImageDraw.Draw(im)
    f = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', 96); s = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc', 64)
    d.rectangle([60, 60, w - 60, h - 60], outline=(120, 110, 90), width=6)
    d.text((140, 120), '手工单  No.%04d' % (1020 + n), font=f, fill=(40, 40, 60))
    for i, t in enumerate(['客户：第二人民医院 %d 病区' % (n + 3), '40L 氧气 %d 瓶   10L %d 瓶' % (n + 1, n % 3), '湿化杯 %d 个   鼻氧管 %d 根' % (n * 2, n + 4), '经手：丁增    2026.10.19']):
        d.text((160, 380 + i * 230), t, font=s, fill=(30, 50, 120)); d.line([150, 470 + i * 230, w - 160, 470 + i * 230], fill=(180, 170, 150), width=3)
    b = io.BytesIO(); im.save(b, 'JPEG', quality=85); return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()

def cid(name): return next(k['id'] for k in call('/api/boot')[1]['couriers'] if k['name'] == name)

class H1_HandPhotos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        call('/api/paper/save', {'data': {'date': D, 'session': '早上', 'form': 'cyl', 'rows': [{'rid': 'a', 'plate': '6922', 'driver': '6922丁增', 'cells': {'R.o40': '30'}}]}})
        cls.k = cid('6922丁增')

    def test_1_api(self):
        ids = [call('/api/photo', {'data': slip(i), 'name': 'hand%d.jpg' % i})[1]['id'] for i in range(3)]
        self.assertEqual(call('/api/hand_photos/attach', {'date': D, 'courier_id': self.k, 'ids': ids}, pin='0000')[0], 401)   # 要密码
        st, r = call('/api/hand_photos/attach', {'date': D, 'courier_id': self.k, 'ids': ids}); self.assertEqual((st, r['n']), (200, 3))
        # 手机：一个码 10 分钟内可连传多张，电脑取到后一起存
        t = call('/api/upq/new', {'label': '手工单 丁增 10.19'})[1]['token']
        for i in range(4): self.assertEqual(call('/api/upq/photo', {'t': t, 'data': slip(10 + i)})[0], 200)
        got = [p['id'] for p in call('/api/upq/poll?t=' + t)[1]['items']]; self.assertEqual(len(got), 4)
        call('/api/hand_photos/attach', {'date': D, 'courier_id': self.k, 'ids': got})
        items = call('/api/hand_photos?date=%s&courier_id=%d' % (D, self.k))[1]['items']; self.assertEqual(len(items), 7)
        self.assertEqual(call('/api/daily?date=' + D)[1]['hand_photos'][str(self.k)], 7)
        # 交接表改了、重算了：照片还在（不跟 daily_entries 的 id）
        call('/api/paper/save', {'data': {'id': next(s['id'] for s in call('/api/paper?date=' + D)[1]['sheets'] if s['form'] == 'cyl'), 'date': D, 'session': '早上', 'form': 'cyl',
                                          'rows': [{'rid': 'a', 'plate': '6922', 'driver': '6922丁增', 'cells': {'R.o40': '31'}}]}})
        self.assertEqual(call('/api/daily?date=' + D)[1]['hand_photos'][str(self.k)], 7)
        # 别处的照片不会被挪过来
        other = call('/api/photo', {'data': slip(99), 'entity': 'misc', 'entity_id': 1})[1]['id']
        self.assertEqual(call('/api/hand_photos/attach', {'date': D, 'courier_id': self.k, 'ids': [other]})[1]['n'], 0)
        # 删除要密码
        self.assertEqual(call('/api/photo/delete', {'id': items[-1]['id']}, pin='0000')[0], 401)
        self.assertEqual(call('/api/photo/delete', {'id': items[-1]['id']})[0], 200)
        self.assertEqual(len(call('/api/hand_photos?date=%s&courier_id=%d' % (D, self.k))[1]['items']), 6)
        # 存的是原图（不是缩略图）：长边 2400 还在
        from PIL import Image
        p = os.path.join(server.db.PHOTO_DIR, items[0]['path']); self.assertEqual(max(Image.open(p).size), 2400)
        self.assertTrue(any('手工单照片' in (a[0] or '') for a in server.db_c().execute("SELECT summary FROM audit WHERE entity='photo'")))
        js = open(os.path.join(ROOT, 'static', 'core.js'), encoding='utf-8').read(); self.assertIn('maxSide || 2500; q = q || 0.85', js)
        up = open(os.path.join(ROOT, 'static', 'm', 'up.html'), encoding='utf-8').read(); self.assertIn('shrink(f, 2500, 0.85)', up); self.assertIn('multiple', up)

    @unittest.skipUnless(HAVE, '没有 playwright / Chrome')
    def test_2_ui(self):
        if not call('/api/hand_photos?date=%s&courier_id=%d' % (D, self.k))[1]['items']: self.test_1_api()
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox']); errs = []
            try:
                pg = await (await br.new_context(viewport={'width': 1400, 'height': 860}, locale='zh-CN')).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(test_all.URL + '/'); await pg.wait_for_timeout(500)
                await pg.evaluate("location.hash = '#daily/sum'"); await pg.wait_for_timeout(800)
                await pg.fill('#dDate', D); await pg.dispatch_event('#dDate', 'change'); await pg.wait_for_timeout(900)
                a = await pg.query_selector('#dSum a.hp.on'); self.assertIn('6', await a.inner_text())
                self.assertIsNone(await pg.query_selector('#dSum a.hp:not(.on)') and None)
                self.assertNotIn('data-hp', await pg.evaluate("() => dailyTable(D.dd, true)"))         # 打印里没有
                await pg.screenshot(path=os.path.join(OUT, 'hand_photo_1_badge.png'), clip={'x': 0, 'y': 120, 'width': 1400, 'height': 330})
                await a.click(); await pg.wait_for_selector('#hpG img'); await pg.wait_for_timeout(600)
                self.assertEqual(len(await pg.query_selector_all('#hpG img')), 6)
                await pg.screenshot(path=os.path.join(OUT, 'hand_photo_2_grid.png'))
                await (await pg.query_selector_all('#hpG img'))[1].click(); await pg.wait_for_selector('.iv-ov img'); await pg.wait_for_timeout(500)
                self.assertEqual(await pg.inner_text('.iv-n'), '2 / 6')
                nat = await pg.evaluate("() => document.querySelector('.iv-ov img').naturalWidth"); self.assertEqual(nat, 2400)   # 原图
                box = await pg.evaluate("() => { const r = document.querySelector('.iv').getBoundingClientRect(); return [r.width / innerWidth, r.height / innerHeight]; }")
                self.assertTrue(0.75 < box[0] < 0.85 and box[1] < 0.9, box)                                  # 居中弹窗，不是全屏
                await pg.screenshot(path=os.path.join(OUT, 'viewer_1_popup.png'))
                await pg.keyboard.press('ArrowRight'); await pg.wait_for_timeout(200); self.assertEqual(await pg.inner_text('.iv-n'), '3 / 6')
                await pg.keyboard.press('ArrowLeft'); await pg.keyboard.press('ArrowLeft'); await pg.wait_for_timeout(200); self.assertEqual(await pg.inner_text('.iv-n'), '1 / 6')
                st = await pg.query_selector('.iv-st'); b = await st.bounding_box()
                await pg.mouse.move(b['x'] + b['width'] * 0.3, b['y'] + b['height'] * 0.35)
                for _ in range(4): await pg.mouse.wheel(0, -200); await pg.wait_for_timeout(60)
                self.assertNotEqual(await pg.inner_text('.iv-pc'), '100%')
                t0 = await pg.evaluate("() => document.querySelector('.iv-ov img').style.transform")
                await pg.mouse.down(); await pg.mouse.move(b['x'] + b['width'] * 0.5, b['y'] + b['height'] * 0.55, steps=6); await pg.mouse.up()
                self.assertNotEqual(await pg.evaluate("() => document.querySelector('.iv-ov img').style.transform"), t0)   # 拖动了
                await pg.screenshot(path=os.path.join(OUT, 'viewer_2_zoomed.png'))
                await pg.click('.iv-b button[data-z="0"]'); self.assertEqual(await pg.inner_text('.iv-pc'), '100%')
                await pg.click('.iv-b button[data-z="1"]'); self.assertEqual(await pg.inner_text('.iv-pc'), '125%')
                await pg.dblclick('.iv-st img'); self.assertEqual(await pg.inner_text('.iv-pc'), '100%')
                await pg.click('.iv-b button[data-r]'); self.assertIn('rotate(90deg)', await pg.evaluate("() => document.querySelector('.iv-ov img').style.transform"))
                await pg.keyboard.press('Escape'); await pg.wait_for_timeout(100)
                self.assertIsNone(await pg.query_selector('.iv-ov')); self.assertTrue(await pg.query_selector('#hpG'))   # 只关大图，照片框还在
                # 别处的照片（如照片区 photoBox / 内嵌 onclick=bigImg(this.src)）也用同一个看图
                await pg.evaluate("() => { const d = dialog('照片', `<div class=\"photos\">${[...document.querySelectorAll('#hpG img')].slice(0, 3).map(i => `<img class=\"ph-i\" src=\"${i.getAttribute('src')}\" onclick=\"bigImg(this.src)\">`).join('')}</div>`); }")
                await (await pg.query_selector_all('.ov:last-child .photos img'))[2].click(); await pg.wait_for_selector('.iv-ov')
                self.assertEqual(await pg.inner_text('.iv-n'), '3 / 3')
                await pg.click('.iv-b button[data-c]'); self.assertIsNone(await pg.query_selector('.iv-ov'))
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

if __name__ == '__main__': unittest.main()
