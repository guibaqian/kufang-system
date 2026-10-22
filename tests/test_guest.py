"""访客借用登记（/m/guest）+ 启动器小工具：python -m unittest tests.test_guest -v"""
import os, sys, json, base64, unittest, urllib.request, urllib.error, io, ctypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, new_product, stock, setUpModule, tearDownModule, ROOT, TMP  # noqa
import test_all, server, guest

PNG = 'data:image/png;base64,' + base64.b64encode(bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082')).decode()

def g(path, body=None, headers=None):
    """访客请求：不带密码"""
    rq = urllib.request.Request(test_all.URL + path, data=None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode()),
                                headers=dict({'Content-Type': 'application/json'}, **(headers or {})))
    try:
        with urllib.request.urlopen(rq) as r: d = r.read(); return r.status, (json.loads(d) if 'json' in r.headers.get('Content-Type', '') else d)
    except urllib.error.HTTPError as e:
        t = e.read()
        try: return e.code, json.loads(t or b'{}')
        except Exception: return e.code, t

def form(pid, **kw):
    d = {'orgs': ['一院'], 'cust_name': '访客张三', 'cust_phone': '13800001111', 'sales_name': '王销售', 'sales_phone': '13900002222',
         'pickups': [{'name': '取货甲', 'phone': '13700003333'}, {'name': '取货乙', 'phone': ''}, {'name': '', 'phone': ''}],
         'escort': '李四', 'escort_phone': '139', 'remark': '急用',
         'items': [{'product_id': pid, 'qty': 2}, {'product_name': '小扳手', 'approx': 1}]}
    d.update(kw); return d

class G1_Guest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pid = new_product('访客测试制氧机', unit='台')
        st, r = call('/api/count/save', {'product_id': cls.pid, 'qty': 10}); assert st == 200, r
    def setUp(self): guest.reset_limits()

    def test_form_minimal_no_pin(self):
        st, r = g('/api/guest/form'); self.assertEqual(st, 200)
        self.assertIn('一院', r['orgs']); p = next(x for x in r['products'] if x['id'] == self.pid)
        self.assertEqual(set(p), {'id', 'label', 'unit', 'uses'})   # 没有库存、没有记录
        st, html = g('/m/guest'); self.assertEqual(st, 200); self.assertIn('访客登记借用', html.decode('utf-8'))

    def test_scope_only_guest_routes(self):
        for path in ('/api/guest/products', '/api/guest/../loans', '/api/guest/loan/save', '/api/guest/home'):
            self.assertEqual(g(path)[0], 404, path)
        self.assertEqual(g('/api/guest/loan_req/confirm', {'id': 1})[0], 404)
        # 员工写接口仍然要密码
        self.assertEqual(call('/api/loan_req/confirm', {'id': 1}, pin='')[0], 401)
        self.assertEqual(call('/api/loan_req/reject', {'id': 1}, pin='')[0], 401)
        self.assertEqual(g('/api/guest/submit', b'not json')[0], 400)
        self.assertEqual(g('/api/guest/submit', b'[1,2]')[0], 400)

    def test_validation(self):
        for bad, msg in ((form(self.pid, cust_phone='abc'), '客户电话'), (form(self.pid, sales_phone='x1'), '销售人电话'), (form(self.pid, pickups=[{'name': 'a', 'phone': 'zz'}]), '取货人电话'), (form(self.pid, orgs=[]), '单位'),
                         (form(self.pid, items=[]), '至少'), (form(self.pid, items=[{'product_id': self.pid, 'qty': 0}]), '数量'),
                         (form(self.pid, orgs=['一院', '二院']), '归属'), (form(self.pid, items=[{'product_id': 999999, 'qty': 1}]), '不存在'),
                         (form(self.pid, photos=['data:image/png;base64,' + base64.b64encode(b'hello').decode()]), '图片')):
            st, r = g('/api/guest/submit', bad); self.assertEqual(st, 400, (msg, r)); self.assertIn(msg, r['error'])
            guest.reset_limits()

    def test_minimal_only_org_and_item(self):
        """只填单位 + 一样东西就能提交；姓名、电话都不用填"""
        st, r = g('/api/guest/submit', {'orgs': ['二院'], 'items': [{'product_id': self.pid, 'qty': 1}]}); self.assertEqual(st, 200, r)
        q = call('/api/loan_req/one?id=%d' % r['no'])[1]
        self.assertEqual((q['cust_name'], q['sales_name'], q['pickups'], q['escort']), ('', '', [], ''))
        st, x = call('/api/loan_req/confirm', {'id': r['no']}); self.assertEqual(st, 200, x)
        l = call('/api/loan/one?id=%d' % x['id'])[1]; self.assertEqual((l['orgs'], l['user_to'], l['pickups']), (['二院'], '', []))
        # 不是一院：随车人员不收
        rid = g('/api/guest/submit', form(self.pid, orgs=['二院']))[1]['no']; self.assertEqual(call('/api/loan_req/one?id=%d' % rid)[1]['escort'], '')
        call('/api/loan_req/reject', {'id': rid})

    def test_old_requests_migrated(self):
        """升级前的登记（只有姓名 / 电话）：当作客户"""
        import db
        c = db.connect()
        c.execute("INSERT INTO loan_requests(status,name,phone,orgs,items,created_at,created_by) VALUES('待确认','老访客','13511112222',?,?,0,'访客')",
                  (json.dumps(['一院'], ensure_ascii=False), json.dumps([{'product_id': self.pid, 'product_name': '访客测试制氧机', 'qty': 1, 'approx': 0, 'qty_text': '', 'org': ''}], ensure_ascii=False)))
        rid = c.execute('SELECT MAX(id) FROM loan_requests').fetchone()[0]; c.commit()
        guest.ensure_schema(c); guest.ensure_schema(c); c.commit(); c.close()     # 可重复跑
        q = call('/api/loan_req/one?id=%d' % rid)[1]; self.assertEqual((q['cust_name'], q['cust_phone']), ('老访客', '13511112222'))
        st, x = call('/api/loan_req/confirm', {'id': rid}); self.assertEqual(st, 200, x)
        l = call('/api/loan/one?id=%d' % x['id'])[1]; self.assertEqual((l['user_to'], l['cust_name'], l['cust_phone']), ('老访客', '老访客', '13511112222'))

    def test_submit_confirm_flow(self):
        before = stock(self.pid)['qty']
        n0 = call('/api/home')[1]['loan_req']
        st, r = g('/api/guest/submit', form(self.pid, photos=[PNG], signature=PNG)); self.assertEqual(st, 200, r); rid = r['no']
        self.assertEqual(stock(self.pid)['qty'], before)                       # 待确认：不动库存
        self.assertEqual(call('/api/home')[1]['loan_req'], n0 + 1)
        self.assertEqual(call('/api/boot')[1]['loan_req'], n0 + 1)
        q = call('/api/loan_req/one?id=%d' % rid)[1]
        self.assertEqual(q['status'], '待确认'); self.assertEqual(len(q['photos']), 2); self.assertIn('sign', [p['tag'] for p in q['photos']])
        self.assertEqual(q['escort'], '李四'); self.assertEqual(q['items'][1]['qty_text'], '若干')
        st, x = call('/api/loan_req/confirm', {'id': rid}); self.assertEqual(st, 200, x); self.assertTrue(x['slip_no'].startswith('JY'))
        self.assertEqual(stock(self.pid)['qty'], before - 2)                   # 确认后照常扣库存
        l = call('/api/loan/one?id=%d' % x['id'])[1]
        self.assertEqual(l['orgs'], ['一院']); self.assertEqual(l['user_to'], '访客张三'); self.assertEqual(l['escort'], '李四')
        self.assertEqual(len(l['photos']), 2); self.assertEqual(l['finalized'], 0)
        self.assertEqual((l['cust_name'], l['cust_phone'], l['salesperson'], l['sales_phone']), ('访客张三', '13800001111', '王销售', '13900002222'))
        self.assertEqual(l['pickups'], [{'name': '取货甲', 'phone': '13700003333'}, {'name': '取货乙', 'phone': ''}])   # 空的取货人去掉
        self.assertEqual(q['pickups'], l['pickups'])
        # 打印 / 导出里有；能按电话、取货人搜到
        slip = json.dumps(call('/api/loan/slip.xlsx?fmt=json&id=%d' % x['id'])[1], ensure_ascii=False)
        for t in ('客户 访客张三 13800001111', '销售 王销售 13900002222', '取货 取货甲 13700003333、取货乙'): self.assertIn(t, slip)
        self.assertIn('客户 / 销售 / 取货人', json.dumps(call('/api/loans.xlsx?fmt=json&status=')[1], ensure_ascii=False))
        for k in ('13700003333', '取货乙', '王销售', '13900002222', '13800001111'):
            self.assertIn(x['id'], [i['id'] for i in call('/api/loans?status=&q=' + urllib.request.quote(k))[1]['items']], k)
        self.assertEqual(call('/api/loan_req/one?id=%d' % rid)[1]['status'], '已确认')
        st, e = call('/api/loan_req/confirm', {'id': rid}); self.assertEqual(st, 400); self.assertIn('已经', e['error'])
        self.assertEqual(call('/api/home')[1]['loan_req'], n0)

    def test_edit_then_confirm_and_reject(self):
        before = stock(self.pid)['qty']
        rid = g('/api/guest/submit', form(self.pid))[1]['no']
        data = {'user_to': '访客张三', 'orgs': ['一院', '二院'], 'need_return': 1, 'items': [{'product_id': self.pid, 'qty': 3, 'org': '共用'}],
                'cust_name': '改过的客户', 'salesperson': '王销售', 'pickups': [{'name': '取货丙', 'phone': '1'}]}
        st, x = call('/api/loan_req/confirm', {'id': rid, 'data': data, 'photo_ids': []}); self.assertEqual(st, 200, x)
        self.assertEqual(stock(self.pid)['qty'], before - 3)
        l = call('/api/loan/one?id=%d' % x['id'])[1]; self.assertEqual((l['cust_name'], l['salesperson'], l['pickups'][0]['name']), ('改过的客户', '王销售', '取货丙'))
        rid2 = g('/api/guest/submit', form(self.pid))[1]['no']
        st, _ = call('/api/loan_req/reject', {'id': rid2, 'reason': '没货'}); self.assertEqual(st, 200)
        q = call('/api/loan_req/one?id=%d' % rid2)[1]; self.assertEqual((q['status'], q['reject_reason']), ('已拒绝', '没货'))
        self.assertEqual(stock(self.pid)['qty'], before - 3)
        self.assertEqual(call('/api/loan_req/confirm', {'id': rid2})[0], 400)
        self.assertIn(rid2, [i['id'] for i in call('/api/loan_req?status=' + urllib.request.quote('已拒绝'))[1]['items']])

    def test_rate_limit(self):
        codes = [g('/api/guest/submit', form(self.pid))[0] for _ in range(guest.LIMITS['submit'][0] + 1)]
        self.assertEqual(codes[:-1], [200] * guest.LIMITS['submit'][0]); self.assertEqual(codes[-1], 429)
        ids = [r['id'] for r in call('/api/loan_req')[1]['items']]
        for i in ids: call('/api/loan_req/reject', {'id': i})   # 清掉，免得影响别的测试

from test_nav import HAVE, CHROME, run
SHOTS = os.path.join(ROOT, 'screens')

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class G3_Ui(unittest.TestCase):
    def test_phone_form_and_desktop_pending(self):
        guest.reset_limits(); pid = new_product('访客界面测试氧气袋', unit='个')
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL; shots = os.environ.get('SHOTS')
            try:
                ph = await (await br.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, device_scale_factor=2)).new_page(); ph.on('pageerror', lambda e: errs.append(str(e)))
                await ph.goto(U + '/m/guest'); await ph.wait_for_selector('#gO button')
                # 什么都不填就提交：只提示单位
                await ph.click('#gGo'); self.assertIn('单位', await ph.inner_text('.g-err'))
                await ph.click('#gO button[data-o="一院"]'); await ph.wait_for_selector('#gE', state='visible')       # 一院才有随车人员
                await ph.fill('#gQ', '访客界面测试'); await ph.click('#gD div[data-p]')
                await ph.fill('#gSn', '王销售'); await ph.fill('#gSp', '13900002222'); await ph.fill('#gCn', '张客户')
                await ph.click('#gPa'); await ph.fill('#gPn0', '取货甲'); await ph.fill('#gPp0', '13700003333')
                await ph.click('#gPa'); await ph.fill('#gPn1', '取货乙')
                self.assertEqual(await ph.input_value('#gPn0'), '取货甲')                                               # 加第二个取货人不丢第一个
                await ph.evaluate("document.querySelectorAll('.g-err').forEach(x => x.remove()); scrollTo(0, 0)")
                if shots: await ph.screenshot(path=os.path.join(SHOTS, 'guest_1_phone_form.png'), full_page=True)
                await ph.click('#gGo'); await ph.wait_for_selector('#gAgain')
                if shots: await ph.screenshot(path=os.path.join(SHOTS, 'guest_2_phone_done.png'))
                await ph.click('#gAgain'); await ph.wait_for_selector('#gO button')
                # 这台手机记住了单位、销售人；客户、取货人清空
                self.assertEqual(await ph.eval_on_selector_all('#gO button.on', 'b => b.map(x => x.dataset.o)'), ['一院'])
                self.assertEqual((await ph.input_value('#gSn'), await ph.input_value('#gSp'), await ph.input_value('#gCn')), ('王销售', '13900002222', ''))
                self.assertEqual(await ph.eval_on_selector('#gO button', 'b => b.dataset.o'), '一院')                   # 上次用的排最前
                h = await ph.eval_on_selector('#gO button', 'b => b.getBoundingClientRect().height'); self.assertGreaterEqual(h, 44)
                if shots: await ph.screenshot(path=os.path.join(SHOTS, 'guest_3_phone_again.png'))
                # 电脑：待确认列表显示客户 / 销售 / 取货人
                pg = await (await br.new_context(viewport={'width': 1280, 'height': 720})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(U + '/#loan/req'); await pg.wait_for_selector('[data-ok]')
                t = await pg.inner_text('#lnBody')
                for k in ('张客户', '销售 王销售 13900002222', '取货 取货甲 13700003333、取货乙'): self.assertIn(k.replace(' ', ''), t.replace(' ', '').replace('\u3000', ''), k)
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'guest_4_desktop_pending.png'))
                # 修改后确认：字段带到借用单表单
                rid = max(i['id'] for i in call('/api/loan_req')[1]['items'])
                await pg.click('[data-ed="%d"]' % rid); await pg.wait_for_selector('#cust_name')
                self.assertEqual((await pg.input_value('#cust_name'), await pg.input_value('#salesperson'), await pg.input_value('[data-pkn="1"]')), ('张客户', '王销售', '取货乙'))
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'guest_5_desktop_edit_confirm.png'))
                await pg.click('#lnSave')
                try: await pg.wait_for_selector('.pin-in', timeout=2000); await pg.fill('.pin-in', '1002'); await pg.press('.pin-in', 'Enter')
                except Exception: pass
                await pg.wait_for_function("location.hash === '#loan/req'")
                l = call('/api/loans?status=&q=' + urllib.request.quote('取货乙'))[1]['items'][0]
                self.assertEqual((l['cust_name'], l['salesperson'], [p['name'] for p in l['pickups']]), ('张客户', '王销售', ['取货甲', '取货乙']))
                await pg.goto(U + '/#loan/list'); await pg.fill('#llQ', '13700003333'); await pg.wait_for_timeout(600)
                self.assertIn('取货甲', await pg.inner_text('#llT'))
                if shots: await pg.screenshot(path=os.path.join(SHOTS, 'guest_6_desktop_loan_list.png'))
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

class G2_Launcher(unittest.TestCase):
    def test_log_stream_without_console(self):
        import launcher, logging.handlers
        p = os.path.join(TMP, 'logs', 't.log'); os.makedirs(os.path.dirname(p), exist_ok=True)
        h = logging.handlers.RotatingFileHandler(p, maxBytes=2000, backupCount=2, encoding='utf-8')
        s = launcher.LogStream(h, None)                      # pythonw：没有控制台
        for i in range(200): print('第 %d 行 日志测试' % i, file=s)
        s.flush(); h.close()
        self.assertTrue(os.path.isfile(p + '.1'))            # 轮换了
        self.assertLessEqual(os.path.getsize(p), 2100)
        self.assertFalse(launcher._usable(None))
        self.assertFalse(launcher.disable_quickedit() and sys.platform != 'win32')

    def test_ping_and_is_ours(self):
        import launcher
        port = int(test_all.URL.rsplit(':', 1)[1])
        self.assertTrue(launcher.is_ours(port)); self.assertFalse(launcher.is_ours(1))

    def test_win_struct_layout(self):
        """在 Linux 上按 Win64 的类型大小重算结构体，确认 NOTIFYICONDATAW=976、WNDCLASSEXW=80"""
        import wintray
        from ctypes import wintypes as W
        sz = {W.DWORD: ctypes.c_uint32, W.UINT: ctypes.c_uint32, W.BOOL: ctypes.c_int32, W.WORD: ctypes.c_uint16, ctypes.c_int: ctypes.c_int32}
        def conv(tp):
            if hasattr(tp, '_length_'): return (ctypes.c_uint16 if tp._type_ is W.WCHAR else conv(tp._type_)) * tp._length_
            if isinstance(tp, type) and issubclass(tp, ctypes.Structure): return sim(tp)
            return sz.get(tp, tp)
        def sim(S):
            class X(ctypes.Structure): _fields_ = [(n, conv(t)) for n, t in S._fields_]
            return X
        if sys.platform == 'win32':
            self.assertEqual(ctypes.sizeof(wintray.NOTIFYICONDATAW), 976); self.assertEqual(ctypes.sizeof(wintray.WNDCLASSEXW), 80); return
        self.assertEqual(ctypes.sizeof(sim(wintray.NOTIFYICONDATAW)), 976)
        self.assertEqual(ctypes.sizeof(sim(wintray.WNDCLASSEXW)), 80)
        with self.assertRaises(OSError): wintray.Tray('x', [])

if __name__ == '__main__': unittest.main()
