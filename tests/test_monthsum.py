"""液氧表 / 4号院 按月自动合计行：python -m unittest tests.test_monthsum -v"""
import os, sys, re, io, zipfile, copy, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_all import call, setUpModule, tearDownModule  # noqa
import test_all, reports, xlgrid
from test_nav import HAVE, CHROME, run

def tab(k): return call('/api/report?key=' + k)[1]
def save(k, t):
    st, r = call('/api/report/save', {'tabs': {k: {'rows': t['rows'], 'merges': t['merges'], 'version': t['version']}}, 'summary': '测试'}); assert st == 200, r
def xl(k):
    b = call('/api/report.xlsx?key=' + k)[1]
    return xlgrid.read_sheet(b, reports.TABS[k]['sheet']), b
def oct_rows(t):
    return [r for r in range(reports.TABS['lox']['start'], len(t['rows']) + 1) if reports.norm_date(reports._v(t, 'A', r))[:7] == '2026-10']

class M1_Rules(unittest.TestCase):
    def test_lox_october(self):
        t = tab('lox'); s = reports.auto_sums('lox', t)
        self.assertEqual([x['month'] for x in s], ['2026-10'])                       # 9 月有手写合计、更早的月份不加
        o = s[0]; last = reports.ranges('lox', t)['main_end']
        self.assertEqual(o['after'], last)                                            # 放在 10 月最后一行（含拆分卸点的续行）下面
        ev = xlgrid.Evaluator(t)
        exp = {c: round(sum(n for n in (reports._numof(ev.cell(c, r) if (t['rows'][r - 1]['c'].get(c) or {}).get('f') else reports._v(t, c, r)) for r in range(84, last + 1)) if n is not None), 2) for c in 'CDF'}
        self.assertEqual(o['vals'], exp); self.assertAlmostEqual(o['vals']['C'], 27.32 + 27.9 + 28.63, places=2)  # 「彤华28.63」也算数
        self.assertEqual(reports._numof('彤华28.63'), 28.63); self.assertIsNone(reports._numof('81.57+28.1')); self.assertIsNone(reports._numof('不算，在8.31日28.12T已记账'))

    def test_yard4_skip_and_manual(self):
        t = tab('yard4'); s = reports.auto_sums('yard4', t)
        self.assertEqual(len(s), 1); self.assertEqual(s[0]['month'], '2026-10')
        self.assertEqual(s[0]['n'], 0); self.assertEqual(len(s[0]['skipped']), 1)      # 「不算」那行不计入
        self.assertEqual(s[0]['vals'], {'D': 0, 'E': 0, 'F': 0})

    def test_new_month_then_manual_total(self):
        t = tab('lox'); t0 = copy.deepcopy(t); r = reports.ranges('lox', t)['main_end'] + 1
        reports._set(t, 'A', r, '2026.11.2'); reports._set(t, 'B', r, '测A123'); reports._set(t, 'C', r, '彤华20'); t['rows'][r - 1]['c']['D'] = {'f': '12.5+7.5'}; reports._set(t, 'F', r, 19.9)
        reports._set(t, 'A', r + 1, '2026.11.5'); reports._set(t, 'D', r + 1, 10); reports._set(t, 'L', r + 1, '不算，测试')
        save('lox', t); t = tab('lox'); s = reports.auto_sums('lox', t)
        self.assertEqual([(x['month'], x['after']) for x in s], [('2026-10', r - 1), ('2026-11', r + 1)])
        self.assertEqual(s[1]['vals'], {'C': 20, 'D': 20, 'F': 19.9}); self.assertEqual(s[1]['skipped'], [r + 1])
        # 下载的 Excel：两行自动合计按位置插入，样式同手写合计行，后面的行顺延
        sh, b = xl('lox')
        self.assertEqual(reports._v(sh, 'A', r), '合计'); self.assertEqual(reports._v(sh, 'D', r), s[0]['vals']['D'])
        self.assertEqual(reports._v(sh, 'A', r + 1), '2026.11.2'); self.assertEqual(reports._v(sh, 'A', r + 3), '合计'); self.assertEqual(reports._v(sh, 'D', r + 3), 20)
        self.assertEqual(reports._v(sh, 'A', 83), '合计')                              # 手写合计原样
        x = zipfile.ZipFile(io.BytesIO(b)); p = [n for n in x.namelist() if n.startswith('xl/worksheets/')]
        sty = lambda xml, a: (re.search(r'<c r="%s"[^>]*?\bs="(\d+)"' % a, xml) or [None, None])[1]
        xmls = [x.read(n).decode() for n in p]; xml = next(m for m in xmls if '<c r="A83"' in m and sty(m, 'A83'))
        self.assertEqual(sty(xml, 'A%d' % r), sty(xml, 'A83')); self.assertEqual(sty(xml, 'D%d' % r), sty(xml, 'D83'))
        self.assertNotIn('合计', [reports._v(tab('lox'), 'A', rr) for rr in (r - 1, r)])  # 存的表里没有自动合计
        # 把下载的文件再导入：自动合计行被认出来去掉，不会变成手写合计（手写的 83 行保留）
        sh2 = copy.deepcopy(sh); self.assertEqual(reports.strip_auto_sums('lox', sh2), 2)
        self.assertEqual([reports._v(sh2, 'A', rr) for rr in (83, r - 1, r, r + 1)], ['合计', reports._v(t, 'A', r - 1), '2026.11.2', '2026.11.5'])
        sh3 = copy.deepcopy(sh); sh3['rows'][r - 1]['c']['D']['v'] = 1; self.assertEqual(reports.strip_auto_sums('lox', sh3), 1)   # 值被人改过的保留
        # 11 月手写了合计：自动的不再出现
        t = tab('lox'); reports._set(t, 'A', r + 2, '合计'); reports._set(t, 'D', r + 2, 99); save('lox', t)
        self.assertEqual([x['month'] for x in reports.auto_sums('lox', tab('lox'))], ['2026-10'])
        t = tab('lox'); t0['version'] = t['version']; save('lox', t0)

@unittest.skipUnless(HAVE, '没有 playwright / Chrome')
class M2_Ui(unittest.TestCase):
    def test_grid_print_live_update(self):
        async def go():
            from playwright.async_api import async_playwright
            pw = await async_playwright().start(); br = await pw.chromium.launch(executable_path=CHROME, args=['--no-sandbox'])
            errs = []; U = test_all.URL
            try:
                pg = await (await br.new_context(viewport={'width': 1280, 'height': 800})).new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                for k in ('lox', 'yard4'):
                    await pg.goto(U + '/#report/' + k); await pg.wait_for_function("k => RP.k === k && document.querySelector('.rt-' + k)", arg=k)
                    py = reports.auto_sums(k, tab(k))
                    js = await pg.evaluate("k => rAutoSums(k).map(s => ({after: s.after, month: s.month, vals: s.vals, n: s.n, skipped: s.skipped}))", k)
                    self.assertEqual(js, py, k)                                                   # 前后端规则一致
                    a = py[0]['after']
                    tr = await pg.query_selector('#rGrid tr[data-r="%d"] + tr.r-auto' % a); self.assertTrue(tr, k)   # 紧跟在该月最后一行下面
                    self.assertEqual((await (await tr.query_selector('td')).inner_text()), '合计')
                    self.assertIn('自动合计', await tr.get_attribute('title'))
                    await (await tr.query_selector_all('td'))[2].click(); self.assertNotEqual(await pg.evaluate("RP.sel && RP.sel.r"), a + 1)   # 不能选中 / 编辑
                await pg.goto(U + '/#report/lox'); await pg.wait_for_function("RP.k === 'lox' && document.querySelector('.rt-lox tr.r-auto')")
                a = reports.auto_sums('lox', tab('lox'))[0]['after']; before = await pg.evaluate("rAutoSums('lox')[0].vals.D")
                # 改 10 月某行的拉萨过磅：自动合计马上变（还没保存）
                await pg.evaluate("r => { rCommit('lox', r, 'D', '30'); }", 84)
                after = await pg.evaluate("rAutoSums('lox')[0].vals.D")
                self.assertAlmostEqual(after - before, 30 - 28.7, places=2)
                self.assertIn('%.2f' % after, await pg.inner_text('#rGrid tr.r-auto'))
                # 打印也有这一行
                await pg.evaluate("window.print = () => {}; rPrint('lox', 0, true)")
                ptxt = await pg.inner_text('.print-host'); self.assertIn('%.2f' % after, ptxt)
                await pg.evaluate("rLoad('lox').then(() => { App.guard = null; rRender(); })")
            finally:
                await br.close(); await pw.stop()
            self.assertEqual(errs, [])
        run(go())

if __name__ == '__main__': unittest.main()
