"""设置中心：名称设置（只改显示）、版本号接口、分组设置。python -m unittest tests.test_settings -v"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import test_all, xlsxio, version
from test_nav import HAVE, CHROME, run

NAMES = {'出库': '发货', '液态原料换算表': '用量换算表', '客户自提': '自提', '访客登记借用': '来访借用', '液态氧原料入出库记录': '液氧出入库台账'}

def cells(b):
    sh = xlsxio.read_sheet(b); return {k: v for k, v in sh['cells'].items() if k != '_f'}

class S1_Api(unittest.TestCase):
    def tearDown(self): call('/api/settings/save', {'data': {'ui_names': {}, 'site_name': '库房出入库'}})

    def test_version(self):
        st, v = call('/api/version'); self.assertEqual(st, 200)
        self.assertEqual(v['version'], version.VERSION)
        self.assertRegex(v['build_date'], r'^\d{4}-\d\d-\d\d$')
        self.assertEqual([c['version'] for c in v['changelog']][:3], [c['version'] for c in version.CHANGELOG][:3])
        self.assertTrue(all(c['items'] for c in v['changelog']))
        self.assertTrue(os.path.isdir(v['data_dir'])); self.assertIsInstance(v['lan'], list)
        st, b = call('/api/boot'); self.assertEqual(b['version'], version.VERSION); self.assertEqual(b['build_date'], v['build_date'])

    def test_names_saved_cleaned_audited_reset(self):
        st, _ = call('/api/settings/save', {'data': {'ui_names': NAMES}}, pin='0000'); self.assertIn(st, (401, 403))
        before = cells(call('/api/report.xlsx?key=conv')[1]); before_l = cells(call('/api/report.xlsx?key=ledger')[1])
        st, r = call('/api/settings/save', {'data': {'ui_names': dict(NAMES, 空的='', 同名='同名', **{' 首页 ': ' 主页 '})}}); self.assertEqual(st, 200, r)
        b = call('/api/boot')[1]; m = b['settings']['ui_names']
        self.assertEqual(m, dict(NAMES, 首页='主页'))                       # 空的、没改的去掉，前后空格去掉
        self.assertEqual(b['settings']['out_kinds'][0], '客户自提')            # 选项的值（数据键）不变
        self.assertEqual(cells(call('/api/report.xlsx?key=conv')[1]), before)  # 下载的原表不变
        self.assertEqual(cells(call('/api/report.xlsx?key=ledger')[1]), before_l)
        a = call('/api/audit?entity=settings&limit=5')[1]['items'][0]
        self.assertIn('名称「出库」：默认 → 发货', a['summary'])
        self.assertEqual(call('/api/guest/form')[1]['names']['访客登记借用'], '来访借用')  # 访客页也拿得到
        call('/api/settings/save', {'data': {'ui_names': {}}})
        self.assertEqual(call('/api/boot')[1]['settings']['ui_names'], {})
        self.assertIn('恢复默认', call('/api/audit?entity=settings&limit=5')[1]['items'][0]['summary'])

    def test_grouped_settings_merge(self):
        call('/api/settings/save', {'data': {'print': {'company': '某某气体公司'}}})
        call('/api/settings/save', {'data': {'defaults': {'session': '中午'}, 'ocr': {'default_rate': 6}}})
        s = call('/api/boot')[1]['settings']
        self.assertEqual(s['print'], {'company': '某某气体公司', 'footer': True})
        self.assertEqual(s['defaults']['session'], '中午'); self.assertEqual(s['defaults']['out_kind'], '客户自提')
        self.assertEqual(s['ocr'], {'ask_push': True, 'default_rate': 6})
        call('/api/settings/save', {'data': {'guest_orgs': ['一院', ' 三院 ', '一院', '']}})
        self.assertEqual(call('/api/boot')[1]['settings']['guest_orgs'], ['一院', '三院'])
        self.assertIn('三院', [o['org'] for o in call('/api/loans')[1]['orgs']])
        self.assertIn('三院', call('/api/guest/form')[1]['orgs'])
        call('/api/settings/save', {'data': {'print': {'company': ''}, 'defaults': {'session': '早上'}, 'ocr': {'default_rate': 8}, 'guest_orgs': ['一院', '二院']}})

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class S2_Ui(unittest.TestCase):
    def tearDown(self): call('/api/settings/save', {'data': {'ui_names': {}, 'site_name': '库房出入库'}})

    def test_names_applied_everywhere(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL
            try:
                call('/api/settings/save', {'data': {'ui_names': NAMES, 'site_name': '一号库房'}})
                pg = await (await br.new_context(viewport={'width': 1440, 'height': 900})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto(U + '/#home'); await pg.wait_for_selector('#foot a')
                self.assertEqual(await pg.inner_text('#tabs a[data-p="out"]'), '发货')
                self.assertEqual(await pg.inner_text('#siteName'), '一号库房'); self.assertEqual(await pg.title(), '一号库房')
                self.assertIn(version.VERSION, await pg.inner_text('#foot'))
                # 下拉选项：显示新名，提交的值还是原值；输入框里的字不动
                await pg.evaluate("document.body.insertAdjacentHTML('beforeend', '<select id=tsel><option>客户自提</option><option>销售出库</option></select><input id=tin value=出库><span id=tsp>请先选「液态原料换算表」</span>')")
                await pg.wait_for_function("document.querySelector('#tsel option').textContent === '自提'")
                self.assertEqual(await pg.evaluate("document.querySelector('#tsel').value"), '客户自提')
                self.assertEqual(await pg.input_value('#tin'), '出库')
                self.assertEqual(await pg.inner_text('#tsp'), '请先选「用量换算表」')
                # 报表页签名、标题
                await pg.goto(U + '/#report/conv'); await pg.wait_for_selector('#rTabs button[data-k="conv"]')
                await pg.wait_for_function("document.querySelector('#rTabs button[data-k=\"conv\"]').textContent === '用量换算表'")
                # 报表全称：页签、打印标题都用同一个名称；其他页签是全称
                self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#rTabs button')].map(b => b.textContent)"), ['用量换算表', '液氧出入库台账', '库存及到货总数', '液氧表', '4号院'])
                await pg.evaluate("printHtml('<div class=\"ttl\">' + RT.conv.title + '</div><table><tr><td>1</td></tr></table>')")
                await pg.wait_for_function("document.querySelector('.print-host .ttl') && document.querySelector('.print-host .ttl').textContent === '用量换算表'")
                # 设置中心：每个分区都能打开；名称设置页里的「原名称」不被替换
                await pg.goto(U + '/#settings/about'); await pg.wait_for_selector('#abVer')
                self.assertEqual(await pg.inner_text('#abVer'), version.VERSION); self.assertIn('更新记录', await pg.inner_text('#sBody'))
                keys = await pg.evaluate("SETS.flatMap(g => g[1].map(x => x[0]))")
                self.assertGreaterEqual(len(keys), 16)
                for k in keys:
                    await pg.click('#sMenu a[data-sk="%s"]' % k)
                    await pg.wait_for_function("k => { const b = document.querySelector('#sBody'); return location.hash === '#settings/' + k && b && b.querySelector('h2'); }", arg=k)
                await pg.goto(U + '/#settings/names'); await pg.wait_for_selector('#nmSave')
                self.assertTrue(await pg.evaluate("[...document.querySelectorAll('.ntab td.o')].some(td => td.firstChild.textContent === '出库')"))
                self.assertEqual(await pg.input_value('[data-o="出库"]'), '发货')
                # 名称设置：报表名称每张报表一行、顺序同页签；所有原名称不重复；每行有灰字说明
                self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#nmRep [data-o]')].map(i => i.dataset.o)"), ['液态原料换算表', '液态氧原料入出库记录', '库存及到货总数', '液氧表', '4号院'])
                os_ = await pg.evaluate("[...document.querySelectorAll('[data-o]')].map(i => i.dataset.o)")
                self.assertEqual(len(os_), len(set(os_)), [o for o in os_ if os_.count(o) > 1])
                for gone in ('换算表', '入出库记录', '到货总数', '出库40L', '日期'): self.assertNotIn(gone, os_)
                self.assertEqual(await pg.evaluate("document.querySelectorAll('.ntab td.o').length"), await pg.evaluate("document.querySelectorAll('.ntab td.o .nmw').length"))
                self.assertIn('交接表汇总', await pg.inner_text('td.o:has([data-o="出库"]), tr:has([data-o="出库"]) td.o'))
                # 在界面上改一个名称并保存（输密码）
                await pg.fill('[data-o="首页"]', '主页'); await pg.click('#nmSave')
                await pg.wait_for_selector('.pin-in'); await pg.fill('.pin-in', '1002'); await pg.press('.pin-in', 'Enter')
                await pg.wait_for_function("document.querySelector('#tabs a[data-p=\"home\"]') && document.querySelector('#tabs a[data-p=\"home\"]').textContent === '主页'")
                self.assertEqual(call('/api/boot')[1]['settings']['ui_names'].get('首页'), '主页')
                # 手机端
                mp = await (await br.new_context(viewport={'width': 390, 'height': 800}, is_mobile=True)).new_page(); mp.on('pageerror', lambda e: errs.append(str(e)))
                await mp.goto(U + '/m/#home'); await mp.wait_for_selector('.mfoot')
                await mp.wait_for_function("document.querySelector('a.big.pri b').textContent === '发货'")
                self.assertIn(version.VERSION, await mp.inner_text('.mfoot'))
                await mp.goto(U + '/m/#settings'); await mp.wait_for_selector('#mVer'); self.assertEqual(await mp.inner_text('#mVer'), version.VERSION)
                # 访客页
                await mp.goto(U + '/m/guest'); await mp.wait_for_selector('.g-h h1')
                await mp.wait_for_function("document.querySelector('.g-h h1').textContent === '来访借用'")
                # 恢复默认（界面）
                await pg.goto(U + '/#settings/names'); await pg.wait_for_selector('#nmReset'); await pg.click('#nmReset')
                await pg.click('.ov .dlg-f button.pri')
                await pg.wait_for_function("document.querySelector('#tabs a[data-p=\"out\"]') && document.querySelector('#tabs a[data-p=\"out\"]').textContent === '出库'")
                self.assertEqual(call('/api/boot')[1]['settings']['ui_names'], {})
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class S3_TabOrder(unittest.TestCase):
    def tearDown(self): call('/api/settings/save', {'data': {'report_order': []}})
    def test_reorder_tabs(self):
        st, r = call('/api/settings/save', {'data': {'report_order': ['lox', 'conv', 'bogus', 'lox']}}); self.assertEqual(st, 200, r)
        self.assertEqual(call('/api/boot')[1]['settings']['report_order'], ['lox', 'conv'])
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL
            try:
                pg = await (await br.new_context(viewport={'width': 1280, 'height': 860})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                tabs = "[...document.querySelectorAll('#rTabs button')].map(b => b.dataset.k)"
                await pg.goto(U + '/#report'); await pg.wait_for_selector('#rTabs button.on')
                self.assertEqual(await pg.evaluate(tabs), ['lox', 'conv', 'ledger', 'stock', 'yard4'])
                self.assertEqual(await pg.get_attribute('#rTabs button.on', 'data-k'), 'lox')      # 默认打开第一个
                # 全称页签不溢出：都在卡片内
                self.assertTrue(await pg.evaluate("(() => { const c = document.querySelector('.r-card').getBoundingClientRect(); return [...document.querySelectorAll('#rTabs button')].every(b => b.getBoundingClientRect().right <= c.right + 1); })()"))
                # 设置里上下调整并保存
                await pg.goto(U + '/#settings/reportcols'); await pg.wait_for_selector('#roT')
                await pg.click('#roT tr[data-k="yard4"] [data-up]'); await pg.click('#roT tr[data-k="yard4"] [data-up]')
                self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#roT tbody tr')].map(t => t.dataset.k)"), ['lox', 'conv', 'yard4', 'ledger', 'stock'])
                await pg.click('#roSave'); await pg.wait_for_selector('.pin-in'); await pg.fill('.pin-in', '1002'); await pg.press('.pin-in', 'Enter')
                await pg.wait_for_function("S.boot.settings.report_order.join() === 'lox,conv,yard4,ledger,stock'")
                await pg.goto(U + '/#report/conv'); await pg.wait_for_selector('#rTabs button.on')
                self.assertEqual(await pg.evaluate(tabs), ['lox', 'conv', 'yard4', 'ledger', 'stock'])
                self.assertEqual(await pg.get_attribute('#rTabs button.on', 'data-k'), 'conv')
                a = call('/api/audit?entity=settings&limit=3')[1]['items'][0]['summary']; self.assertIn('报表页签顺序', a)
                await pg.goto(U + '/#settings/names'); await pg.wait_for_selector('#nmRep')
                self.assertEqual(await pg.evaluate("[...document.querySelectorAll('#nmRep [data-o]')].map(i => i.dataset.o)"), ['液氧表', '液态原料换算表', '4号院', '液态氧原料入出库记录', '库存及到货总数'])
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())



class NavOrder(unittest.TestCase):
    def tearDown(self): call('/api/settings/save', {'data': {'nav_order': [], 'nav_hidden': ['misc', 'slip', 'backup'], 'ui_names': {}}})
    def test_nav_order_save(self):
        st, r = call('/api/settings/save', {'data': {'nav_order': ['arrival', 'home', 'bogus', 'out', 'settings']}})
        self.assertEqual(st, 200, r)
        s = call('/api/boot')[1]['settings']['nav_order']
        self.assertEqual(s[:3], ['arrival', 'home', 'out'])
        self.assertNotIn('bogus', s)
        self.assertNotIn('settings', s)  # 设置不参与排序
        js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'app.js'), encoding='utf-8').read()
        self.assertIn('applyNav', js)
        self.assertIn('nav_hidden', js)
        sysjs = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'p_sys.js'), encoding='utf-8').read()
        self.assertIn("['nav', '顶部导航']", sysjs)
        self.assertIn('界面与顺序', sysjs)
        self.assertIn('data-nav-nm', sysjs)
        self.assertIn('显示为', sysjs)
        self.assertIn('data-nav-show', sysjs)
        self.assertIn('NAV_HIDE0', sysjs)

    def test_nav_hidden_default_and_toggle(self):
        """杂物/称重/备份默认隐藏；可清空隐藏列表全部显示；非法键丢掉；首页不可藏"""
        boot = call('/api/boot')[1]['settings']
        self.assertEqual(boot.get('nav_hidden'), ['misc', 'slip', 'backup'])
        st, r = call('/api/settings/save', {'data': {'nav_hidden': ['misc', 'bogus', 'home', 'slip']}})
        self.assertEqual(st, 200, r)
        h = call('/api/boot')[1]['settings']['nav_hidden']
        self.assertEqual(h, ['misc', 'slip'])  # bogus/home 去掉
        self.assertNotIn('home', h)
        st, r = call('/api/settings/save', {'data': {'nav_hidden': []}})
        self.assertEqual(st, 200, r)
        self.assertEqual(call('/api/boot')[1]['settings']['nav_hidden'], [])
        # applyNav 源码：隐藏项不进顶栏 HTML
        js = open(os.path.join(os.path.dirname(__file__), '..', 'static', 'app.js'), encoding='utf-8').read()
        self.assertIn('hid.includes(k)', js)
        self.assertIn("['misc', 'slip', 'backup']", js)

    def test_nav_hide_apply_in_browser(self):
        """浏览器：默认顶栏无杂物/称重/备份；设置显示后出现；#misc 路由仍可用"""
        if not HAVE: self.skipTest('没有 playwright / Chrome')
        async def go():
            from playwright.async_api import async_playwright
            U = test_all.URL
            call('/api/settings/save', {'data': {'nav_order': [], 'nav_hidden': ['misc', 'slip', 'backup']}})
            pw = await async_playwright().start()
            br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            try:
                pg = await br.new_page()
                await pg.goto(U + '/#home'); await pg.wait_for_timeout(800)
                tabs = await pg.evaluate("[...document.querySelectorAll('#tabs a')].map(a => a.dataset.p)")
                self.assertEqual(tabs, ['home', 'daily', 'out', 'loan', 'arrival', 'stock', 'report', 'settings'], tabs)
                self.assertNotIn('misc', tabs); self.assertNotIn('slip', tabs); self.assertNotIn('backup', tabs)
                # 直达隐藏页仍可用
                await pg.goto(U + '/#misc'); await pg.wait_for_timeout(600)
                self.assertIn('杂物', await pg.inner_text('#main h1'))
                # 打开显示后顶栏出现（整页重载，避免只改 hash 时沿用旧 boot）
                call('/api/settings/save', {'data': {'nav_hidden': []}})
                await pg.goto(U + '/?navtest=1#home', wait_until='networkidle'); await pg.wait_for_timeout(500)
                tabs2 = await pg.evaluate("[...document.querySelectorAll('#tabs a')].map(a => a.dataset.p)")
                self.assertIn('misc', tabs2); self.assertIn('slip', tabs2); self.assertIn('backup', tabs2)
                self.assertEqual(tabs2[-1], 'settings')
                # 日表显示名
                labs = await pg.evaluate("[...document.querySelectorAll('#tabs a')].map(a => a.textContent.trim())")
                self.assertIn('日表', labs)
            finally:
                await br.close(); await pw.stop()
        run(go())

    def test_nav_names_via_ui_names(self):
        """顶栏改名走 ui_names，与名称设置共用"""
        st, r = call('/api/settings/save', {'data': {'ui_names': {'出库': '发货', '到货': '收货', '首页': '主页'}}})
        self.assertEqual(st, 200, r)
        m = call('/api/boot')[1]['settings']['ui_names']
        self.assertEqual(m.get('出库'), '发货')
        self.assertEqual(m.get('到货'), '收货')
        self.assertEqual(m.get('首页'), '主页')
        call('/api/settings/save', {'data': {'ui_names': {}}})

if __name__ == '__main__': unittest.main()
